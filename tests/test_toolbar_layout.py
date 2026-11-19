"""Toolbar layout engine (atk_toolbar/atk_layout.py): pure Python, no Maya, no Qt."""
import ast
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
LAYOUT = ROOT / "atk_toolbar" / "atk_layout.py"
LOADER = ROOT / "atk_toolbar" / "atk_loader.py"


def _load_layout():
    spec = importlib.util.spec_from_file_location("atk_test_layout", LAYOUT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


L = _load_layout()

GROUPS = ["timing", "viewport", "rigging", "pipeline"]


def _tool(tid, group):
    return {"id": tid, "label": tid.title(), "group": group}


REGISTRY = [
    _tool("ticks", "timing"), _tool("tween", "timing"), _tool("tangent", "timing"),
    _tool("noise", "timing"),
    _tool("snap", "viewport"), _tool("pivot", "viewport"),
    _tool("reset", "rigging"), _tool("mirror", "rigging"),
    _tool("save", "pipeline"), _tool("library", "pipeline"),
]
IDS = [t["id"] for t in REGISTRY]


def _real_registry():
    """TOOL_REGISTRY ids and groups parsed from atk_loader.py (no Maya import)."""
    tree = ast.parse(LOADER.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "TOOL_REGISTRY":
            out = []
            for entry in node.value.elts:
                d = {k.value: v for k, v in zip(entry.keys, entry.values)}
                out.append({"id": d["id"].value, "label": d["label"].value,
                            "group": d["group"].value})
            return out
    raise AssertionError("TOOL_REGISTRY not found")


def plan(settings=None, usage=None, **kw):
    s = L.default_settings(REGISTRY, GROUPS)
    s.update(settings or {})
    kw.setdefault("group_order", GROUPS)
    return L.plan_layout(REGISTRY, s, usage or {}, **kw)


def kinds(p):
    return [[(i.kind, i.id) for i in line] for line in p.lines]


def flat(p):
    return [(i.kind, i.id) for line in p.lines for i in line]


class FullPresetTests(unittest.TestCase):
    def test_default_is_full_registry_order_with_group_separators(self):
        p = plan()
        self.assertEqual(p.preset, "full")
        self.assertEqual(len(p.lines), 1)
        expected = []
        prev = None
        for t in REGISTRY:
            if prev and t["group"] != prev:
                expected.append(("sep", "sep"))
            expected.append(("tool", t["id"]))
            prev = t["group"]
        self.assertEqual(flat(p), expected)
        # Small (24 px) is the default icon size.
        self.assertEqual(p.icon_size, 24)
        self.assertEqual(p.button_size, 32)
        self.assertEqual(p.spacing, 2)
        self.assertEqual(p.align, "center")

    def test_separators_off(self):
        p = plan(show_separators=False)
        self.assertNotIn(("sep", "sep"), flat(p))
        self.assertEqual([i for _k, i in flat(p)], IDS)

    def test_hidden_tools_are_left_out(self):
        p = plan({"hidden": ["snap", "pivot"]})
        ids = [i for k, i in flat(p) if k == "tool"]
        self.assertNotIn("snap", ids)
        # The whole viewport group is gone: no double separator left behind.
        self.assertNotIn([("sep", "sep"), ("sep", "sep")],
                         [flat(p)[n:n + 2] for n in range(len(flat(p)))])

    def test_works_with_the_real_registry(self):
        reg = _real_registry()
        s = L.default_settings(reg, GROUPS)
        p = L.plan_layout(reg, s, {}, group_order=GROUPS)
        self.assertEqual([i.id for line in p.lines for i in line if i.kind == "tool"],
                         [t["id"] for t in reg])
        self.assertEqual(sum(1 for line in p.lines for i in line if i.kind == "sep"), 3)


class ExpertTests(unittest.TestCase):
    def test_expert_shrinks_icons_tightens_spacing_drops_separators(self):
        for size, small in ((24, 20), (32, 24), (48, 32)):
            p = plan({"expert": True}, icon_size=size)
            self.assertEqual(p.icon_size, small)
            self.assertTrue(p.expert)
            self.assertEqual(p.spacing, 0)
            self.assertEqual(p.button_pad, 4)
            self.assertNotIn(("sep", "sep"), flat(p))

    def test_expert_combines_with_every_preset(self):
        for preset in L.PRESETS:
            p = plan({"preset": preset, "expert": True})
            self.assertEqual(p.preset, preset)
            self.assertNotIn(("sep", "sep"), flat(p))
            self.assertEqual(sorted(p.tool_ids()), sorted(IDS))


class MostUsedTests(unittest.TestCase):
    def test_top_n_inline_rest_in_more(self):
        usage = {"library": 9, "snap": 5, "noise": 5, "reset": 1}
        p = plan({"preset": "most_used", "most_used_count": 3}, usage)
        tools = [i for k, i in flat(p) if k == "tool"]
        # Shown in registry order so buttons do not jump around.
        self.assertEqual(tools, ["noise", "snap", "library"])
        more = [i for line in p.lines for i in line if i.kind == "more"]
        self.assertEqual(len(more), 1)
        self.assertEqual(list(more[0].tools),
                         [t for t in IDS if t not in ("noise", "snap", "library")])
        self.assertEqual(flat(p)[-1], ("more", "more"))

    def test_ties_break_by_registry_order(self):
        usage = {"mirror": 2, "pivot": 2, "tween": 2}
        self.assertEqual(L.rank_most_used(["mirror", "pivot", "tween", "ticks"], usage, IDS),
                         ["tween", "pivot", "mirror", "ticks"])
        p = plan({"preset": "most_used", "most_used_count": 3}, usage)
        self.assertEqual([i for k, i in flat(p) if k == "tool"], ["tween", "pivot", "mirror"])

    def test_no_usage_falls_back_to_first_n(self):
        p = plan({"preset": "most_used", "most_used_count": 4})
        self.assertEqual([i for k, i in flat(p) if k == "tool"], IDS[:4])

    def test_no_more_button_when_everything_fits(self):
        p = plan({"preset": "most_used", "most_used_count": 25})
        self.assertNotIn("more", [k for k, _i in flat(p)])

    def test_hidden_tools_never_in_more(self):
        p = plan({"preset": "most_used", "most_used_count": 3, "hidden": ["save"]})
        self.assertNotIn("save", p.tool_ids())

    def test_count_is_clamped(self):
        s = L.normalize_settings({"most_used_count": 999}, REGISTRY, GROUPS)
        self.assertEqual(s["most_used_count"], L.MOST_USED_MAX)
        s = L.normalize_settings({"most_used_count": 0}, REGISTRY, GROUPS)
        self.assertEqual(s["most_used_count"], L.MOST_USED_MIN)
        s = L.normalize_settings({"most_used_count": "7"}, REGISTRY, GROUPS)
        self.assertEqual(s["most_used_count"], L.MOST_USED_DEFAULT)


class CustomPresetTests(unittest.TestCase):
    def test_user_order_and_selection(self):
        order = ["save", "snap", "ticks"] + [t for t in IDS if t not in ("save", "snap", "ticks")]
        p = plan({"preset": "custom", "order": order, "hidden": ["noise", "library"]})
        tools = [i for k, i in flat(p) if k == "tool"]
        self.assertEqual(tools[:3], ["save", "snap", "ticks"])
        self.assertNotIn("noise", tools)
        self.assertNotIn("library", tools)
        self.assertNotIn(("sep", "sep"), flat(p))

    def test_folded_custom_group_sits_at_its_first_tool(self):
        p = plan({"preset": "custom", "custom_groups": [
            {"name": "Keys", "tools": ["noise", "tween"], "open": False}]})
        f = flat(p)
        self.assertEqual(f[0], ("tool", "ticks"))
        self.assertEqual(f[1], ("group", "custom:0"))
        self.assertNotIn(("tool", "tween"), f)
        self.assertNotIn(("tool", "noise"), f)
        group = p.lines[0][1]
        self.assertEqual(group.label, "Keys")
        self.assertEqual(group.tools, ("noise", "tween"))   # the group's own order

    def test_open_custom_group_shows_tools_inline(self):
        p = plan({"preset": "custom", "custom_groups": [
            {"name": "Keys", "tools": ["noise", "tween"], "open": True}]})
        f = flat(p)
        self.assertEqual(f[:5], [("tool", "ticks"), ("sep", "sep"), ("tool", "noise"),
                                 ("tool", "tween"), ("sep", "sep")])
        self.assertEqual([i for k, i in f if k == "tool"].count("noise"), 1)

    def test_group_of_hidden_tools_is_skipped(self):
        p = plan({"preset": "custom", "hidden": ["save"], "custom_groups": [
            {"name": "Out", "tools": ["save"], "open": False}]})
        self.assertNotIn("group", [k for k, _ in flat(p)])


class GroupedPresetTests(unittest.TestCase):
    def test_all_folded_by_default(self):
        p = plan({"preset": "grouped"})
        self.assertEqual(flat(p), [
            ("group", "group:timing"), ("sep", "sep"), ("group", "group:viewport"),
            ("sep", "sep"), ("group", "group:rigging"), ("sep", "sep"),
            ("group", "group:pipeline")])
        timing = p.lines[0][0]
        self.assertEqual(timing.label, "Timing")
        self.assertEqual(timing.group, "timing")
        self.assertEqual(timing.tools, ("ticks", "tween", "tangent", "noise"))

    def test_open_group_is_inline(self):
        p = plan({"preset": "grouped", "group_open": {"viewport": True}})
        self.assertEqual(flat(p)[:4], [("group", "group:timing"), ("sep", "sep"),
                                       ("tool", "snap"), ("tool", "pivot")])

    def test_custom_groups_follow_built_ins(self):
        p = plan({"preset": "grouped", "custom_groups": [
            {"name": "Faves", "tools": ["snap", "save"], "open": False}]})
        self.assertEqual(flat(p)[-1], ("group", "custom:0"))
        self.assertEqual(p.lines[0][-1].tools, ("snap", "save"))

    def test_empty_group_is_skipped(self):
        p = plan({"preset": "grouped", "hidden": ["reset", "mirror"]})
        self.assertNotIn(("group", "group:rigging"), flat(p))

    def test_group_uses_user_order(self):
        order = ["noise"] + [t for t in IDS if t != "noise"]
        p = plan({"preset": "grouped", "order": order})
        self.assertEqual(p.lines[0][0].tools[0], "noise")


class LinesTests(unittest.TestCase):
    def test_rows_wrap_in_order(self):
        for n in (1, 2, 3):
            p = plan({"lines": n}, show_separators=False)
            self.assertEqual(len(p.lines), n)
            self.assertEqual([i.id for line in p.lines for i in line], IDS)
            sizes = [len(line) for line in p.lines]
            self.assertLessEqual(max(sizes) - min(sizes), 2)

    def test_same_lines_for_vertical(self):
        h = plan({"lines": 2}, orientation="horizontal")
        v = plan({"lines": 2}, orientation="vertical")
        self.assertEqual(h.lines, v.lines)

    def test_no_separator_at_line_ends(self):
        for n in (1, 2, 3):
            for preset in L.PRESETS:
                p = plan({"lines": n, "preset": preset, "most_used_count": 3})
                for line in p.lines:
                    self.assertTrue(line)
                    self.assertNotEqual(line[0].kind, "sep")
                    self.assertNotEqual(line[-1].kind, "sep")

    def test_never_more_lines_than_items(self):
        p = plan({"preset": "grouped", "lines": 3, "hidden": IDS[4:]})
        self.assertEqual(len(p.lines), 1)

    def test_extra_slots_count_toward_wrapping(self):
        p = plan({"lines": 2}, show_separators=False, extra_slots={"ticks": 6})
        self.assertEqual([i.id for i in p.lines[0]], ["ticks", "tween"])

    def test_lines_clamped(self):
        self.assertEqual(L.normalize_settings({"lines": 9}, REGISTRY, GROUPS)["lines"], 3)
        self.assertEqual(L.normalize_settings({"lines": 0}, REGISTRY, GROUPS)["lines"], 1)
        self.assertEqual(L.normalize_settings({"lines": True}, REGISTRY, GROUPS)["lines"], 1)

    def test_everything_hidden_gives_one_empty_line(self):
        p = plan({"hidden": IDS})
        self.assertEqual(p.lines, [[]])


class AlignmentTests(unittest.TestCase):
    def test_mapping(self):
        for value, expected in (("left", "start"), ("top", "start"), ("center", "center"),
                                ("right", "end"), ("bottom", "end"), ("junk", "center"),
                                (None, "center")):
            self.assertEqual(plan(align=value).align, expected)
            self.assertEqual(plan(align=value, orientation="vertical").align, expected)


class MeasureTests(unittest.TestCase):
    # Geometry checks are written for Medium (32 px) icons.
    def test_single_row(self):
        p = plan(show_separators=False, icon_size=32)
        along, across = L.measure(p)
        self.assertEqual(along, 10 * 40 + 9 * 2)
        self.assertEqual(across, 40)

    def test_separators_and_extra_slots(self):
        p = plan(extra_slots={"tangent": 3}, icon_size=32)
        along, _ = L.measure(p, extra_slots={"tangent": 3})
        widgets = 13 + 3
        self.assertEqual(along, 13 * 40 + 3 * 1 + (widgets - 1) * 2)

    def test_rows_stack_across(self):
        p = plan({"lines": 3}, show_separators=False, icon_size=32)
        along, across = L.measure(p)
        self.assertEqual(across, 3 * 40 + 2 * 2)
        self.assertEqual(along, 4 * 40 + 3 * 2)

    def test_fold_label_width(self):
        p = plan({"preset": "grouped"}, show_separators=False)
        self.assertEqual(L.measure(p, fold_extra=30)[0], L.measure(p)[0] + 4 * 30)


class StorageTests(unittest.TestCase):
    def test_round_trip(self):
        s = L.default_settings(REGISTRY, GROUPS)
        s.update(preset="grouped", expert=True, lines=2, hidden=["noise"],
                 custom_groups=[{"name": "Keys", "tools": ["tween"], "open": True}])
        s["group_open"]["rigging"] = True
        self.assertEqual(L.decode_settings(L.encode_settings(s), REGISTRY, GROUPS), s)

    def test_bad_json_falls_back_to_defaults(self):
        default = L.default_settings(REGISTRY, GROUPS)
        for raw in (None, "", "not json", "[]", "42", '"x"', "{}",
                    '{"version": 2, "preset": "custom"}', '{"version": "1"}', 7):
            self.assertEqual(L.decode_settings(raw, REGISTRY, GROUPS), default, raw)

    def test_bad_fields_fall_back_one_by_one(self):
        raw = json.dumps({"version": 1, "preset": "weird", "expert": "yes",
                          "order": ["save", "gone", 3, "save"], "hidden": "noise",
                          "group_open": {"timing": 1, "viewport": True, "nope": True},
                          "custom_groups": [{"name": "  A  b "}, {"name": "a B"}, "x",
                                            {"name": ""}, {"name": "C", "tools": ["gone"]}],
                          "lines": 2})
        s = L.decode_settings(raw, REGISTRY, GROUPS)
        self.assertEqual(s["preset"], "full")
        self.assertFalse(s["expert"])
        self.assertEqual(s["order"], ["save"] + [t for t in IDS if t != "save"])
        self.assertEqual(s["hidden"], [])
        self.assertEqual(s["group_open"], {"timing": False, "viewport": True,
                                           "rigging": False, "pipeline": False})
        self.assertEqual([g["name"] for g in s["custom_groups"]], ["A b", "C"])
        self.assertEqual(s["custom_groups"][1]["tools"], [])
        self.assertEqual(s["lines"], 2)
        self.assertEqual(s["valign"], "top")

    def test_valign(self):
        for value in ("top", "center", "bottom"):
            s = L.normalize_settings({"valign": value}, REGISTRY, GROUPS)
            self.assertEqual(s["valign"], value)
        self.assertEqual(L.normalize_settings({"valign": "left"}, REGISTRY, GROUPS)["valign"], "top")

    def test_new_registry_tools_are_appended_and_shown(self):
        old = L.encode_settings(dict(L.default_settings(REGISTRY[:-1], GROUPS),
                                     order=list(reversed(IDS[:-1]))))
        s = L.decode_settings(old, REGISTRY, GROUPS)
        self.assertEqual(s["order"][-1], "library")
        self.assertNotIn("library", s["hidden"])

    def test_custom_groups_limited(self):
        groups = [{"name": "G%d" % i, "tools": []} for i in range(20)]
        s = L.normalize_settings({"custom_groups": groups}, REGISTRY, GROUPS)
        self.assertEqual(len(s["custom_groups"]), L.MAX_CUSTOM_GROUPS)
        long_name = L.normalize_settings({"custom_groups": [{"name": "x" * 99}]},
                                         REGISTRY, GROUPS)
        self.assertEqual(len(long_name["custom_groups"][0]["name"]), L.MAX_GROUP_NAME)


class MigrationTests(unittest.TestCase):
    def test_old_hidden_prefs_seed_the_layout(self):
        s = L.load_settings(None, REGISTRY, ["snap", "unknown", "save"], GROUPS)
        self.assertEqual(s["hidden"], ["snap", "save"])
        self.assertEqual(s["preset"], "full")
        p = L.plan_layout(REGISTRY, s, {}, group_order=GROUPS)
        self.assertNotIn("snap", p.tool_ids())

    def test_stored_layout_wins_over_old_prefs(self):
        raw = L.encode_settings(L.default_settings(REGISTRY, GROUPS))
        s = L.load_settings(raw, REGISTRY, ["snap"], GROUPS)
        self.assertEqual(s["hidden"], [])

    def test_unreadable_stored_layout_does_not_raise(self):
        s = L.load_settings("{broken", REGISTRY, ["snap"], GROUPS)
        self.assertEqual(s, L.default_settings(REGISTRY, GROUPS))


class ExportImportTests(unittest.TestCase):
    def test_round_trip(self):
        s = L.default_settings(REGISTRY, GROUPS)
        s.update(preset="custom", hidden=["noise"], lines=3)
        text = L.export_layout(s, 48, "right")
        settings, size, align = L.import_layout(text, REGISTRY, GROUPS)
        self.assertEqual(settings, s)
        self.assertEqual((size, align), (48, "right"))

    def test_rejects_other_files(self):
        for text in ("nope", "[]", '{"kind": "other"}',
                     json.dumps({"kind": L.EXPORT_KIND, "version": 99})):
            with self.assertRaises(ValueError):
                L.import_layout(text, REGISTRY, GROUPS)

    def test_bad_values_in_a_layout_file_fall_back(self):
        text = json.dumps({"kind": L.EXPORT_KIND, "version": 1, "layout": "x",
                           "icon_size": 1000, "align": "diagonal"})
        settings, size, align = L.import_layout(text, REGISTRY, GROUPS)
        self.assertEqual(settings, L.default_settings(REGISTRY, GROUPS))
        self.assertEqual((size, align), (24, "center"))


class UsageTests(unittest.TestCase):
    def test_round_trip_and_bump(self):
        counts = L.bump_usage({}, "snap")
        counts = L.bump_usage(counts, "snap")
        counts = L.bump_usage(counts, "save")
        self.assertEqual(L.decode_usage(L.encode_usage(counts)), {"snap": 2, "save": 1})

    def test_bump_ignores_bad_ids(self):
        self.assertEqual(L.bump_usage({"a": 1}, None), {"a": 1})
        self.assertEqual(L.bump_usage({"a": 1}, ""), {"a": 1})

    def test_bad_usage_is_empty(self):
        for raw in (None, "", "x", "[]", '{"version": 2, "counts": {"a": 1}}',
                    '{"version": 1, "counts": []}'):
            self.assertEqual(L.decode_usage(raw), {}, raw)

    def test_bad_counts_are_dropped(self):
        raw = json.dumps({"version": 1, "counts": {"a": 3, "b": -1, "c": "4",
                                                   "d": True, "e": 0, "f": 2.5}})
        self.assertEqual(L.decode_usage(raw), {"a": 3})


if __name__ == "__main__":
    unittest.main()
