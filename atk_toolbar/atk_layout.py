"""ATK Layout — decides what the toolbar shows and where (no Qt, no Maya).

The toolbar asks :func:`plan_layout` for a :class:`LayoutPlan` and only
renders it.  Everything here is plain Python so it can be unit-tested without
Maya or a display (see ``tests/test_toolbar_layout.py``).

Stored data
-----------
Two versioned JSON strings, kept in Maya optionVars by the toolbar:

``atk_toolbar_layout``::

    {"version": 1, "preset": "full", "expert": false, "most_used_count": 10,
     "order": [...tool ids...], "hidden": [...tool ids...],
     "group_open": {"timing": false, ...},
     "custom_groups": [{"name": "Blocking", "tools": [...], "open": false}],
     "lines": 1, "valign": "top"}

Icon size and the horizontal alignment keep their own optionVars
(``atk_toolbar_icon_size``, ``atk_toolbar_icon_alignment``); ``valign`` is
the alignment of a vertical (left/right) bar.

``atk_toolbar_usage``::

    {"version": 1, "counts": {"anim_snap": 12, ...}}

Anything unreadable falls back to the defaults; nothing here raises on bad
data, and stored data is only ever read with ``json.loads``.
"""

import json
import math
from collections import namedtuple

SETTINGS_VERSION = 1
USAGE_VERSION = 1
EXPORT_KIND = "atk_toolbar_layout"

PRESETS = ("full", "most_used", "custom", "grouped")
PRESET_LABELS = {
    "full": "Full",
    "most_used": "Most used",
    "custom": "Custom",
    "grouped": "Grouped",
}

GROUP_LABELS = {
    "timing": "Timing",
    "viewport": "Viewport",
    "rigging": "Rigging",
    "pipeline": "Pipeline",
}

MOST_USED_MIN, MOST_USED_MAX, MOST_USED_DEFAULT = 3, 25, 10
LINES_MIN, LINES_MAX = 1, 3
MAX_CUSTOM_GROUPS = 8
MAX_GROUP_NAME = 32

ICON_SIZES = (24, 32, 48)
ICON_SIZE_DEFAULT = 24       # Small; the natural 32 px icons are Medium
ALIGNMENTS = ("left", "center", "right")          # horizontal bar
VALIGNMENTS = ("top", "center", "bottom")         # vertical bar

# Expert mode drops the icons one step.
_EXPERT_ICON = {48: 32, 32: 24, 24: 20}

# Button padding (button side = icon + pad) and layout spacing.
BUTTON_PAD, BUTTON_PAD_EXPERT = 8, 4
SPACING, SPACING_EXPERT = 2, 0
SEPARATOR_PX = 1


class Item(namedtuple("Item", "kind id label group tools")):
    """One entry on a toolbar line.

    kind  -- "tool", "group" (fold-out), "more" (fold-out) or "sep"
    id    -- tool id, "group:<key>", "custom:<n>", "more" or "sep"
    label -- text for group / More buttons
    group -- the tool's group, or the built-in group a group button folds
    tools -- tool ids inside a fold-out (empty for tools and separators)
    """
    __slots__ = ()


SEP = Item("sep", "sep", "", None, ())


class LayoutPlan(namedtuple("LayoutPlan",
                            "lines align icon_size expert spacing button_pad preset")):
    """What the toolbar should show.

    lines      -- list of lists of Item: rows on a horizontal bar,
                  columns on a vertical one
    align      -- "start", "center" or "end" (left/top, centre, right/bottom)
    icon_size  -- icon pixels to draw
    expert     -- True when expert mode is on
    spacing    -- layout spacing in pixels
    button_pad -- button side minus icon side
    preset     -- the preset that produced the plan
    """
    __slots__ = ()

    @property
    def button_size(self):
        return self.icon_size + self.button_pad

    def tool_ids(self):
        """Every tool id the plan shows, inline or in a fold-out."""
        seen = []
        for line in self.lines:
            for item in line:
                ids = (item.id,) if item.kind == "tool" else item.tools
                for tid in ids:
                    if tid not in seen:
                        seen.append(tid)
        return seen


# ---------------------------------------------------------------------------
# Registry helpers
# ---------------------------------------------------------------------------

def registry_ids(registry):
    return [t["id"] for t in registry]


def registry_groups(registry, group_order=None):
    """Groups in toolbar order: ``group_order`` first, then any others."""
    groups = []
    for g in list(group_order or ()) + [t["group"] for t in registry]:
        if g not in groups and any(t["group"] == g for t in registry):
            groups.append(g)
    return groups


def group_label(group):
    return GROUP_LABELS.get(group, str(group).replace("_", " ").title())


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

def default_settings(registry, group_order=None):
    """The Full layout every new install starts with."""
    return {
        "version": SETTINGS_VERSION,
        "preset": "full",
        "expert": False,
        "most_used_count": MOST_USED_DEFAULT,
        "order": registry_ids(registry),
        "hidden": [],
        "group_open": {g: False for g in registry_groups(registry, group_order)},
        "custom_groups": [],
        "lines": 1,
        "valign": "top",
    }


def _clean_int(value, lo, hi, default):
    if isinstance(value, bool) or not isinstance(value, int):
        return default
    return min(max(value, lo), hi)


def _clean_ids(value, known):
    """Known string ids from a list, in order, without repeats."""
    out = []
    if isinstance(value, list):
        for v in value:
            if isinstance(v, str) and v in known and v not in out:
                out.append(v)
    return out


def _clean_name(value):
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())[:MAX_GROUP_NAME]


def normalize_settings(data, registry, group_order=None):
    """Return a complete, valid settings dict built from ``data``.

    Each field that is missing, the wrong type or out of range takes its
    default; unknown tool ids are dropped and tools new to the registry are
    added (shown) at the end of the custom order.
    """
    out = default_settings(registry, group_order)
    if not isinstance(data, dict):
        return out
    known = set(out["order"])

    if data.get("preset") in PRESETS:
        out["preset"] = data["preset"]
    if isinstance(data.get("expert"), bool):
        out["expert"] = data["expert"]
    out["most_used_count"] = _clean_int(data.get("most_used_count"), MOST_USED_MIN,
                                        MOST_USED_MAX, MOST_USED_DEFAULT)
    out["lines"] = _clean_int(data.get("lines"), LINES_MIN, LINES_MAX, 1)
    if data.get("valign") in VALIGNMENTS:
        out["valign"] = data["valign"]

    order = _clean_ids(data.get("order"), known)
    out["order"] = order + [tid for tid in out["order"] if tid not in order]
    out["hidden"] = _clean_ids(data.get("hidden"), known)

    group_open = data.get("group_open")
    if isinstance(group_open, dict):
        for g in out["group_open"]:
            if isinstance(group_open.get(g), bool):
                out["group_open"][g] = group_open[g]

    groups, names = [], set()
    raw_groups = data.get("custom_groups")
    if isinstance(raw_groups, list):
        for g in raw_groups:
            if not isinstance(g, dict) or len(groups) >= MAX_CUSTOM_GROUPS:
                continue
            name = _clean_name(g.get("name"))
            if not name or name.lower() in names:
                continue
            names.add(name.lower())
            groups.append({
                "name": name,
                "tools": _clean_ids(g.get("tools"), known),
                "open": g.get("open") is True,
            })
    out["custom_groups"] = groups
    return out


def decode_settings(raw, registry, group_order=None):
    """Settings from a stored JSON string; defaults when it can't be used."""
    try:
        data = json.loads(raw) if isinstance(raw, str) else None
    except (TypeError, ValueError):
        data = None
    if not isinstance(data, dict) or data.get("version") != SETTINGS_VERSION:
        return default_settings(registry, group_order)
    return normalize_settings(data, registry, group_order)


def encode_settings(settings):
    data = dict(settings)
    data["version"] = SETTINGS_VERSION
    return json.dumps(data, sort_keys=True)


def migrate_hidden(registry, hidden_ids, group_order=None):
    """First layout data for users upgrading from 1.1.16 or older.

    ``hidden_ids`` are the tools the old ``atk_hidden_<id>`` optionVars hid.
    """
    settings = default_settings(registry, group_order)
    settings["hidden"] = _clean_ids(list(hidden_ids or ()), set(settings["order"]))
    return settings


def load_settings(raw, registry, legacy_hidden=(), group_order=None):
    """Settings from the stored optionVar value.

    ``raw`` is None when the optionVar does not exist yet: the old per-tool
    hide preferences are migrated then.
    """
    if raw is None:
        return migrate_hidden(registry, legacy_hidden, group_order)
    return decode_settings(raw, registry, group_order)


# ---------------------------------------------------------------------------
# Export / import
# ---------------------------------------------------------------------------

def export_layout(settings, icon_size=ICON_SIZE_DEFAULT, align="center"):
    """JSON text for Export layout."""
    payload = {
        "kind": EXPORT_KIND,
        "version": SETTINGS_VERSION,
        "layout": dict(settings, version=SETTINGS_VERSION),
        "icon_size": icon_size if icon_size in ICON_SIZES else ICON_SIZE_DEFAULT,
        "align": align if align in ALIGNMENTS else "center",
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def import_layout(text, registry, group_order=None):
    """Parse an exported layout file.

    Returns ``(settings, icon_size, align)``.  Raises ``ValueError`` with a
    short message when the file is not an ATK layout.
    """
    try:
        payload = json.loads(text)
    except (TypeError, ValueError):
        raise ValueError("The file is not valid JSON.")
    if not isinstance(payload, dict) or payload.get("kind") != EXPORT_KIND:
        raise ValueError("The file is not an ATK layout.")
    if payload.get("version") != SETTINGS_VERSION:
        raise ValueError("This layout is from a newer ATK.")
    settings = normalize_settings(payload.get("layout"), registry, group_order)
    icon_size = payload.get("icon_size")
    if icon_size not in ICON_SIZES or isinstance(icon_size, bool):
        icon_size = ICON_SIZE_DEFAULT
    align = payload.get("align")
    if align not in ALIGNMENTS:
        align = "center"
    return settings, icon_size, align


# ---------------------------------------------------------------------------
# Usage counts
# ---------------------------------------------------------------------------

def decode_usage(raw):
    """Launch counts from the stored JSON string ({} when unusable)."""
    try:
        data = json.loads(raw) if isinstance(raw, str) else None
    except (TypeError, ValueError):
        return {}
    if not isinstance(data, dict) or data.get("version") != USAGE_VERSION:
        return {}
    counts = data.get("counts")
    if not isinstance(counts, dict):
        return {}
    return {k: v for k, v in counts.items()
            if isinstance(k, str) and isinstance(v, int)
            and not isinstance(v, bool) and v > 0}


def encode_usage(counts):
    return json.dumps({"version": USAGE_VERSION, "counts": dict(counts)},
                      sort_keys=True)


def bump_usage(counts, tool_id, amount=1):
    """Return a copy of ``counts`` with one more launch of ``tool_id``."""
    out = dict(counts or {})
    if isinstance(tool_id, str) and tool_id:
        out[tool_id] = int(out.get(tool_id, 0)) + amount
    return out


def rank_most_used(tool_ids, counts, registry_order=None):
    """Tool ids by launch count, most first; ties keep registry order."""
    order = list(registry_order or tool_ids)
    pos = {tid: i for i, tid in enumerate(order)}
    counts = counts or {}
    return sorted(tool_ids,
                  key=lambda tid: (-int(counts.get(tid, 0)), pos.get(tid, len(order))))


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

def normalize_align(align):
    """Map left/top/start, center, right/bottom/end to start/center/end."""
    if align in ("left", "top", "start"):
        return "start"
    if align in ("right", "bottom", "end"):
        return "end"
    return "center"


def effective_icon_size(icon_size, expert):
    if icon_size not in ICON_SIZES:
        icon_size = ICON_SIZE_DEFAULT
    if expert:
        return _EXPERT_ICON.get(icon_size, max(16, int(icon_size * 0.75)))
    return icon_size


def _with_separators(tools, by_group):
    """Tool items, with a separator wherever the group changes."""
    items, prev = [], None
    for t in tools:
        if by_group and prev is not None and t["group"] != prev:
            items.append(SEP)
        items.append(Item("tool", t["id"], t.get("label", t["id"]), t["group"], ()))
        prev = t["group"]
    return items


def _fold_item(kind, item_id, label, group, tools):
    return Item(kind, item_id, label, group, tuple(t["id"] for t in tools))


def _plan_items(registry, settings, usage, group_order, separators):
    by_id = {t["id"]: t for t in registry}
    hidden = set(settings["hidden"])
    visible = [t for t in registry if t["id"] not in hidden]
    user_order = [by_id[tid] for tid in settings["order"]
                  if tid in by_id and tid not in hidden]
    preset = settings["preset"]

    if preset == "most_used":
        ranked = rank_most_used([t["id"] for t in visible], usage,
                                [t["id"] for t in registry])
        top = set(ranked[:settings["most_used_count"]])
        items = _with_separators([t for t in visible if t["id"] in top], separators)
        rest = [t for t in visible if t["id"] not in top]
        if rest:
            if separators and items:
                items.append(SEP)
            items.append(_fold_item("more", "more", "More", None, rest))
        return items

    custom_groups = []
    for i, g in enumerate(settings["custom_groups"]):
        members = [by_id[tid] for tid in g["tools"] if tid in by_id and tid not in hidden]
        if members:
            custom_groups.append((i, g, members))

    def custom_block(i, g, members):
        if g["open"]:
            block = [SEP] if separators else []
            block += _with_separators(members, False)
            return block + ([SEP] if separators else [])
        return [_fold_item("group", "custom:%d" % i, g["name"], None, members)]

    if preset == "custom":
        # Each custom group sits where its first tool (in the user's order)
        # would be; tools in a group are not repeated on the bar.
        items, placed = [], set()
        grouped_ids = {m["id"] for _i, _g, members in custom_groups for m in members}
        pos = {t["id"]: n for n, t in enumerate(user_order)}
        for t in user_order:
            for i, g, members in custom_groups:
                first = min(members, key=lambda m: pos.get(m["id"], 0))
                if first["id"] != t["id"]:
                    continue
                for item in custom_block(i, g, members):
                    if item.kind == "tool":
                        if item.id in placed:
                            continue
                        placed.add(item.id)
                    items.append(item)
            if t["id"] not in grouped_ids:
                items.append(Item("tool", t["id"], t.get("label", t["id"]), t["group"], ()))
        return items

    if preset == "grouped":
        items = []
        blocks = []
        for g in registry_groups(registry, group_order):
            members = [t for t in user_order if t["group"] == g]
            if not members:
                continue
            if settings["group_open"].get(g):
                blocks.append(_with_separators(members, False))
            else:
                blocks.append([_fold_item("group", "group:" + g, group_label(g), g, members)])
        for i, g, members in custom_groups:
            blocks.append([b for b in custom_block(i, g, members) if b.kind != "sep"])
        for block in blocks:
            if items and separators:
                items.append(SEP)
            items.extend(block)
        return items

    # full: today's layout, registry order with group separators.
    return _with_separators(visible, separators)


def _clean_separators(items):
    """No separators at the ends and never two in a row."""
    out = []
    for item in items:
        if item.kind == "sep" and (not out or out[-1].kind == "sep"):
            continue
        out.append(item)
    while out and out[-1].kind == "sep":
        out.pop()
    return out


def _slots(item, extra_slots):
    if item.kind == "sep":
        return 0
    if item.kind == "tool":
        return 1 + int(extra_slots.get(item.id, 0))
    return 1


def split_lines(items, lines, extra_slots=None):
    """Wrap items in order onto up to ``lines`` lines of similar length."""
    extra_slots = extra_slots or {}
    items = _clean_separators(items)
    total = sum(_slots(i, extra_slots) for i in items)
    lines = max(LINES_MIN, min(int(lines), LINES_MAX))
    if total == 0:
        return [[]]
    per_line = int(math.ceil(total / float(lines)))
    out, current, used = [], [], 0
    for item in items:
        slots = _slots(item, extra_slots)
        if (slots and used >= per_line and len(out) < lines - 1):
            out.append(current)
            current, used = [], 0
        current.append(item)
        used += slots
    out.append(current)
    return [l for l in (_clean_separators(line) for line in out) if l]


def plan_layout(registry, settings, usage=None, orientation="horizontal",
                icon_size=ICON_SIZE_DEFAULT, align="center", show_separators=True,
                group_order=None, extra_slots=None):
    """Turn the registry and the layout settings into a :class:`LayoutPlan`.

    ``orientation`` does not change which tools show; it only decides
    whether the lines are rows or columns, which the renderer handles.  It is
    accepted so callers pass the whole picture and future layouts can use it.
    """
    settings = normalize_settings(settings, registry, group_order)
    expert = settings["expert"]
    separators = bool(show_separators) and not expert
    items = _plan_items(registry, settings, usage or {}, group_order, separators)
    return LayoutPlan(
        lines=split_lines(items, settings["lines"], extra_slots),
        align=normalize_align(align),
        icon_size=effective_icon_size(icon_size, expert),
        expert=expert,
        spacing=SPACING_EXPERT if expert else SPACING,
        button_pad=BUTTON_PAD_EXPERT if expert else BUTTON_PAD,
        preset=settings["preset"],
    )


def measure(plan, extra_slots=None, fold_extra=0):
    """Pixel size of the tool area: ``(along, across)``.

    ``along`` runs down the bar (width of a horizontal bar, height of a
    vertical one) and is the longest line; ``across`` is all lines stacked.
    ``fold_extra`` is added to each group / More button along the bar (the
    text label they carry outside expert mode).
    """
    extra_slots = extra_slots or {}
    btn, sp = plan.button_size, plan.spacing
    along = 0
    for line in plan.lines:
        length, widgets = 0, 0
        for item in line:
            if item.kind == "sep":
                length += SEPARATOR_PX
                widgets += 1
            else:
                n = _slots(item, extra_slots)
                length += n * btn
                widgets += n
                if item.kind in ("group", "more"):
                    length += fold_extra
        length += max(0, widgets - 1) * sp
        along = max(along, length)
    n_lines = len([l for l in plan.lines if l]) or 1
    across = n_lines * btn + (n_lines - 1) * sp
    return along, across
