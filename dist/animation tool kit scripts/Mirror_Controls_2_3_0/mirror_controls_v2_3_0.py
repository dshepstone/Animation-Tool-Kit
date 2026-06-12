#!/usr/bin/env python3
"""
mirror_controls_v2_3_0.py - Python Script

Description:
    A tool for mirroring the controllers from one side to the other or to flip
    the pose. The Animation Tool Kit Character Snapshot tool
    (character_snapshot_v1_0_0) is the single source of truth for snapshot
    data: control lists, side classification, mirror partners (automatic and
    manual), exclusions, per-channel copy/negate rules and sign-flip
    overrides all live in the Character Snapshot scene store. Mirror Controls
    no longer keeps its own snapshot system — it queries the Character
    Snapshot module and only falls back to a local axis-vector heuristic when
    the user explicitly chooses to continue without a snapshot.

Requires:
    character_snapshot_v1_0_0.py on the Maya script path (installed by the
    Character Snapshot tool). PySide6 / Maya 2025+.

Install:
    1. Place this file in the Maya scripts folder
       (%USERPROFILE%/Documents/maya/scripts)

    2. In the Maya Script Editor, run:
         from mirror_controls_v2_3_0 import MirrorControls
         MirrorControls.show_dialog()

    3. Create a shelf button by selecting all code (Ctrl+A) and dragging it to the shelf.

Usage:
    1. Pose the rig in its rest / default pose.
    2. Select any control on the rig.
    3. Click "Take Snapshot" (or use the Character Snapshot tool) to capture
       the rig once. The snapshot records every controller, its mirror
       partner, and per-channel flip rules detected from the default pose.
    4. Use the main mirror controls as normal. Manual pairs and channel-rule
       overrides are edited through the Character Snapshot data and shared by
       every ATK tool.

Authors:
    Original: Mikkel Diget Eriksen (2022)
    Updated by: David Shepstone

Version:
    2.3.3 - UI cleanup pass:
             * Removed the redundant "Take Snapshot" button — snapshot
               capture lives in the Tools menu and in the Character Snapshot
               tool (which the Manage button opens); the missing-snapshot
               prompts still offer to take one.
             * Snapshot action buttons consolidated into a single row
               (Edit Rules / Manual Pairs / Flip Sign).
             * Replaced emoji button icons (which render as empty boxes in
               Maya's UI font on Windows) with plain text labels; the
               character-list refresh button now uses a proper Qt icon.
    2.3.2 - Character Snapshot is now the single source of truth.
             * Removed the duplicated legacy RigSnapshot system (snapshot
               builder, Manual Pair Editor, Snapshot Manager). "Take
               Snapshot" now builds a Character Snapshot; "Manual Pairs"
               opens the Character Snapshot Manual Pair Editor; "Manage"
               opens the Character Snapshot tool. Existing legacy
               RigSnapshot scene data is migrated into Character Snapshots
               automatically (non-destructively) on first launch.
             * Partner matching is fully centralised: manual pair → recorded
               partner → multi-convention token swap (lt/rt, l/r,
               left/right, lf/rf, L_/R_, _L/_R, camelCase Left/Right, …),
               every result validated against the scene.
             * Channel flip rules: the snapshot's auto-detected per-channel
               copy/negate rules (derived from the rig's default pose) now
               drive mirroring; "Edit Rules" edits per-channel overrides
               stored in the Character Snapshot — previously the editor
               wrote to legacy data that runtime mirroring never read.
             * Fixed Flip in selection mode: it copied one side over the
               other instead of swapping both sides. Both directions are now
               applied from values captured before any write.
             * Fixed Mirror Middle in selection mode (it warned "no partner"
               and did nothing).
             * Implemented the "Not Selected" operation (direction radio
               buttons were previously ignored).
             * Undo chunks are closed in a try/finally so an error mid-mirror
               can no longer corrupt the undo queue.
             * Missing-snapshot popup now uses the standard ATK wording and
               never fails silently; mirroring reports a summary (mirrored /
               unmatched counts) to the Script Editor.
    2.3.1 - Mirror Controls relies on the Character Snapshot tool for
            snapshot data; ± Flip Sign stores per-control sign overrides in
            the Character Snapshot metadata.
    2.3.0 - Renamed tool from "digetMirrorControl" to "Mirror Controls";
            first Character Snapshot integration.
    2.2.x - Word-boundary token matching, DAG-path resolution fixes, Manual
            Pair Editor, per-character snapshots (see git history).
    2.1.0 - RigSnapshot system with per-attribute mirror rules.
"""

import json

from PySide6 import QtCore, QtGui, QtWidgets
from shiboken6 import wrapInstance

import maya.OpenMayaUI as omui
import maya.cmds as cmds
import maya.OpenMaya as om


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Legacy scene node written by digetMirrorControl / Mirror Controls <= 2.3.1.
# Only read for one-time migration into the Character Snapshot store — no new
# data is ever written to it.
LEGACY_SNAPSHOT_NODE       = "digetMirrorControlSettings"
LEGACY_SNAPSHOT_ATTR       = "rigSnapshot"
LEGACY_SNAPSHOT_MULTI_ATTR = "rigSnapshots"

DEFAULT_PREFIX = "__scene__"

RULE_COPY   = "copy"
RULE_NEGATE = "negate"
RULE_IGNORE = "ignore"
RULES       = [RULE_COPY, RULE_NEGATE, RULE_IGNORE]


# ---------------------------------------------------------------------------
# Prefix detection
# ---------------------------------------------------------------------------

def _detect_prefix(ctrl):
    """
    Extract the namespace prefix from a Maya control name.

    Given ``ProRigs_Chris_v01_10_L:ac_lf_handIK`` → ``ProRigs_Chris_v01_10_L``
    Given ``ac_lf_handIK`` (no namespace)           → ``__scene__`` (default)

    Works with both full DAG paths and short names.
    """
    leaf = ctrl.split("|")[-1]
    if ":" in leaf:
        return leaf.rsplit(":", 1)[0]
    return DEFAULT_PREFIX


# ---------------------------------------------------------------------------
# Character Snapshot integration
# ---------------------------------------------------------------------------
#
# The Character Snapshot module owns ALL matching logic. The thin helpers
# below delegate to it; the only local fallback is a minimal single-pair
# token swap used when the module is not installed at all (the user is then
# warned and offered to install/launch it before mirroring).

def _try_import_character_snapshot():
    """Import character_snapshot_v1_0_0. Return the module, or None if missing."""
    try:
        import character_snapshot_v1_0_0 as cs_mod
        return cs_mod
    except Exception:
        return None


def _mirror_name_candidates(base_name, left_token, right_token):
    """Mirror-name candidates for *base_name* — delegates to the Character
    Snapshot module so the matching behaviour is identical everywhere. Falls
    back to a basic underscore-boundary swap of the configured tokens when
    the module is unavailable."""
    cs_mod = _try_import_character_snapshot()
    if cs_mod is not None and hasattr(cs_mod, "mirror_name_candidates"):
        try:
            return cs_mod.mirror_name_candidates(base_name, left_token, right_token)
        except Exception:
            pass
    swapped = _basic_swap_side_token(base_name, left_token, right_token)
    return [swapped] if swapped else []


def _basic_swap_side_token(base_name, left_token, right_token):
    """Minimal word-boundary token swap (fallback when the Character
    Snapshot module is missing). Boundaries are '_' and string edges so
    'rt' inside 'shirt' is never matched."""
    import re
    for tok, other in ((right_token, left_token), (left_token, right_token)):
        pat = r'(?:(?<=_)|(?<=\A))' + re.escape(tok) + r'(?=_|\Z)'
        m = re.search(pat, base_name, re.IGNORECASE)
        if m:
            return base_name[:m.start()] + other + base_name[m.end():]
    return None


def _has_side_token(ctrl, token):
    """True if the control's leaf base-name contains *token* as a delimited
    segment. Delegates to the Character Snapshot module when available."""
    cs_mod = _try_import_character_snapshot()
    if cs_mod is not None and hasattr(cs_mod, "_has_side_token"):
        try:
            return cs_mod._has_side_token(ctrl, token)
        except Exception:
            pass
    import re
    leaf = ctrl.split("|")[-1]
    base = leaf.split(":")[-1] if ":" in leaf else leaf
    pat = r'(?:(?<=_)|(?<=\A))' + re.escape(token) + r'(?=_|\Z)'
    return bool(re.search(pat, base, re.IGNORECASE))


def _resolve_long(name):
    """Resolve a possibly-ambiguous short name to a unique full DAG path."""
    try:
        matches = cmds.ls(name, long=True)
    except Exception:
        return name
    if matches and len(matches) == 1:
        return matches[0]
    return name


def _load_character_snapshot_for(prefix):
    """Return the stored CharacterSnapshot for *prefix*, or None."""
    cs_mod = _try_import_character_snapshot()
    if cs_mod is None:
        return None
    if not prefix:
        return None
    try:
        return cs_mod.load_snapshot(prefix)
    except Exception:
        return None


def _list_character_snapshot_prefixes():
    """Return the list of stored CharacterSnapshot prefixes, or []."""
    cs_mod = _try_import_character_snapshot()
    if cs_mod is None:
        return []
    try:
        return list(cs_mod.list_prefixes())
    except Exception:
        return []


# Key under which Mirror Controls stores its per-rig flip-sign overrides
# inside the CharacterSnapshot.metadata dict. The list contains leaf names of
# controls whose mirrored numeric channels should be sign-inverted.
_CS_META_FLIP_SIGNS = "mirror_controls_flip_signs"


class _CharacterSnapshotAdapter(object):
    """Mirror Controls' view onto a CharacterSnapshot.

    All snapshot queries the mirror code makes go through this adapter so
    there is exactly one integration point with the Character Snapshot tool:
      - manual_pairs / excluded_controls   (read directly)
      - find_partner(ctrl)                 → scene-validated partner lookup
      - get_side(ctrl)                     → left / right / middle
      - is_excluded(ctrl)
      - get_rule(ctrl, attr)               → effective channel rule
                                              (user override → auto-detected
                                              → None = runtime heuristic)
      - set_rule / clear_rule              → per-channel overrides stored in
                                              the snapshot metadata
      - is_flip_sign / toggle_flip_sign    → whole-control sign inversion
      - save()                             → persists edits to the scene
    """

    def __init__(self, char_snapshot):
        self._cs               = char_snapshot
        self.manual_pairs      = char_snapshot.manual_pairs
        self.excluded_controls = char_snapshot.excluded_controls
        self.left_token        = char_snapshot.left_token
        self.right_token       = char_snapshot.right_token
        self.mirror_axis       = char_snapshot.mirror_axis
        # Read flip-sign overrides; tolerate missing or malformed metadata.
        meta = getattr(char_snapshot, "metadata", None) or {}
        raw  = meta.get(_CS_META_FLIP_SIGNS, [])
        self._flip_signs = set(raw) if isinstance(raw, list) else set()
        self._dirty = False

    # -- Pairing / classification ------------------------------------------

    def get_manual_partner(self, ctrl):
        return self._cs.get_manual_partner(ctrl)

    def find_partner(self, ctrl):
        """Scene-validated partner: manual pair → recorded partner →
        multi-convention token swap. None when nothing resolves."""
        try:
            return self._cs.find_partner_in_scene(ctrl)
        except Exception:
            return None

    def get_side(self, ctrl):
        try:
            return self._cs.get_side(ctrl)
        except Exception:
            return None

    def is_excluded(self, ctrl):
        return self._cs.is_excluded(ctrl)

    # -- Channel rules -------------------------------------------------------

    def get_rule(self, ctrl, attr):
        """Effective copy/negate/ignore rule for ctrl.attr, or None to let
        the runtime axis-vector heuristic decide."""
        try:
            return self._cs.get_mirror_rule(ctrl, attr)
        except Exception:
            return None

    def get_auto_rule(self, ctrl, attr):
        try:
            return self._cs.get_auto_mirror_rule(ctrl, attr)
        except Exception:
            return None

    def get_override(self, ctrl, attr):
        try:
            return self._cs.get_mirror_rule_override(ctrl, attr)
        except Exception:
            return None

    def set_rule(self, ctrl, attr, rule):
        self._cs.set_mirror_rule_override(ctrl, attr, rule)
        self._dirty = True

    def clear_rule(self, ctrl, attr):
        self._cs.clear_mirror_rule_override(ctrl, attr)
        self._dirty = True

    def cs_controls(self):
        """The CharacterSnapshot controls dict (read-only use)."""
        return self._cs.controls

    def control_count(self):
        return self._cs.control_count()

    def pair_count(self):
        return self._cs.pair_count()

    def validate_against_scene(self):
        try:
            return self._cs.validate_against_scene()
        except Exception:
            return None

    # -- Flip-sign interface ----------------------------------------------

    def is_flip_sign(self, ctrl):
        """Return True if ctrl's mirrored numeric channels should be inverted."""
        return ctrl.split("|")[-1] in self._flip_signs

    def toggle_flip_sign(self, ctrl):
        """Flip this control's sign-override bit. Returns the new state."""
        leaf = ctrl.split("|")[-1]
        if leaf in self._flip_signs:
            self._flip_signs.discard(leaf)
            new_state = False
        else:
            self._flip_signs.add(leaf)
            new_state = True
        self._dirty = True
        return new_state

    def list_attribute_names(self, ctrl):
        """Attribute names recorded for ctrl in the CharacterSnapshot."""
        data = self._cs._control_data(ctrl)
        if not data:
            return []
        attrs = data.get("attributes", [])
        return sorted(attrs.keys()) if isinstance(attrs, dict) else list(attrs)

    # -- Persistence -------------------------------------------------------

    def save(self):
        """Persist flip-sign / rule-override edits back to the scene store."""
        if not self._dirty:
            return
        meta = self._cs.metadata if isinstance(self._cs.metadata, dict) else {}
        meta[_CS_META_FLIP_SIGNS] = sorted(self._flip_signs)
        self._cs.metadata = meta
        try:
            self._cs.save_to_scene()
            self._dirty = False
        except Exception as exc:
            om.MGlobal.displayError(
                "[Mirror Controls] Failed to persist snapshot edits: {}".format(exc)
            )


# ---------------------------------------------------------------------------
# Legacy RigSnapshot migration (read-only)
# ---------------------------------------------------------------------------

def _read_legacy_rig_snapshot_store():
    """Read the legacy digetMirrorControlSettings store.

    Returns {prefix: snapshot_dict}. Handles both the multi-prefix attribute
    and the very old single-snapshot attribute. Never writes anything.
    """
    if not cmds.objExists(LEGACY_SNAPSHOT_NODE):
        return {}
    try:
        if cmds.attributeQuery(LEGACY_SNAPSHOT_MULTI_ATTR,
                               node=LEGACY_SNAPSHOT_NODE, exists=True):
            raw = cmds.getAttr("{}.{}".format(LEGACY_SNAPSHOT_NODE,
                                              LEGACY_SNAPSHOT_MULTI_ATTR))
            if raw:
                store = json.loads(raw)
                if isinstance(store, dict):
                    return store
    except Exception:
        pass
    try:
        if cmds.attributeQuery(LEGACY_SNAPSHOT_ATTR,
                               node=LEGACY_SNAPSHOT_NODE, exists=True):
            raw = cmds.getAttr("{}.{}".format(LEGACY_SNAPSHOT_NODE,
                                              LEGACY_SNAPSHOT_ATTR))
            if raw:
                legacy = json.loads(raw)
                if isinstance(legacy, dict) and legacy.get("controls"):
                    prefix = DEFAULT_PREFIX
                    for ctrl_key in legacy["controls"]:
                        p = _detect_prefix(ctrl_key)
                        if p != DEFAULT_PREFIX:
                            prefix = p
                            break
                    return {prefix: legacy}
    except Exception:
        pass
    return {}


def _migrate_legacy_snapshots():
    """Convert legacy RigSnapshot scene data into Character Snapshots.

    Non-destructive and idempotent: prefixes that already have a Character
    Snapshot are skipped and the legacy node is left untouched. Manual pairs,
    exclusions, tokens and per-attribute rules are all carried over via
    CharacterSnapshot._adopt_mirror_snapshot. Returns the migrated prefixes.
    """
    cs_mod = _try_import_character_snapshot()
    if cs_mod is None:
        return []
    migrated = []
    for prefix, data in _read_legacy_rig_snapshot_store().items():
        try:
            if cs_mod.load_snapshot(prefix) is not None:
                continue
            snap = cs_mod.CharacterSnapshot._adopt_mirror_snapshot(data, prefix)
            snap.save_to_scene()
            migrated.append(prefix)
        except Exception as exc:
            om.MGlobal.displayWarning(
                "[Mirror Controls] Could not migrate legacy snapshot "
                "'{}': {}".format(prefix, exc)
            )
    if migrated:
        om.MGlobal.displayInfo(
            "[Mirror Controls] Migrated legacy Rig Snapshot data into "
            "Character Snapshots: {}".format(", ".join(migrated))
        )
    return migrated


# ---------------------------------------------------------------------------
# OperationType
# ---------------------------------------------------------------------------

class OperationType(object):
    left_to_right = "Left to Right"
    right_to_left = "Right to Left"
    flip          = "Flip"
    flip_to_frame = "Flip to Frame"
    mirror_middle = "Mirror Middle"
    selected      = "Selected"
    not_selected  = "Not Selected"


# ---------------------------------------------------------------------------
# Dark theme stylesheet
# ---------------------------------------------------------------------------

DARK_STYLESHEET = """
QDialog {
    background-color: #2b2b2b;
    color: #d4d4d4;
    font-size: 12px;
}
QMenuBar {
    background-color: #333333;
    color: #d4d4d4;
    border-bottom: 1px solid #444444;
    padding: 2px 0px;
}
QMenuBar::item:selected { background-color: #4a90d9; color: #ffffff; border-radius: 3px; }
QMenu {
    background-color: #353535;
    color: #d4d4d4;
    border: 1px solid #555555;
    padding: 4px;
}
QMenu::item { padding: 5px 25px 5px 20px; }
QMenu::item:selected { background-color: #4a90d9; color: #ffffff; border-radius: 3px; }
QMenu::separator { height: 1px; background: #555555; margin: 4px 8px; }
QGroupBox {
    font-weight: bold;
    font-size: 11px;
    border: 1px solid #555555;
    border-radius: 6px;
    margin-top: 10px;
    padding: 14px 8px 8px 8px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 2px 10px;
    border-radius: 3px;
    left: 8px;
}
QLabel { color: #cccccc; }
QPushButton {
    background-color: #404040;
    color: #d4d4d4;
    border: 1px solid #555555;
    border-radius: 4px;
    padding: 5px 14px;
    min-height: 22px;
    font-size: 11px;
}
QPushButton:hover  { background-color: #505050; border-color: #6a6a6a; }
QPushButton:pressed { background-color: #353535; }
QPushButton:disabled { background-color: #333333; color: #666666; border-color: #444444; }
QPushButton#mirrorBtn {
    background-color: #3a7abd;
    color: #ffffff;
    font-size: 14px;
    font-weight: bold;
    min-height: 34px;
    border: 1px solid #4a90d9;
    border-radius: 5px;
}
QPushButton#mirrorBtn:hover { background-color: #4a90d9; }
QPushButton#mirrorBtn:pressed { background-color: #2e6299; }
QPushButton#snapshotBtn {
    background-color: #3a5a3a;
    color: #b0dab0;
    border: 1px solid #4a7a4a;
}
QPushButton#snapshotBtn:hover { background-color: #4a6a4a; border-color: #5a9a5a; }
QPushButton#flipSignBtn {
    background-color: #5a4a30;
    color: #e8c87a;
    border: 1px solid #7a6a40;
}
QPushButton#flipSignBtn:hover { background-color: #6a5a40; border-color: #9a8a60; }
QComboBox {
    background-color: #383838;
    color: #d4d4d4;
    border: 1px solid #555555;
    border-radius: 4px;
    padding: 4px 8px;
    min-height: 20px;
}
QComboBox:hover { border-color: #4a90d9; }
QComboBox::drop-down { border: none; width: 20px; }
QComboBox QAbstractItemView {
    background-color: #383838;
    color: #d4d4d4;
    selection-background-color: #4a90d9;
    border: 1px solid #555555;
}
QLineEdit {
    background-color: #383838;
    color: #d4d4d4;
    border: 1px solid #555555;
    border-radius: 4px;
    padding: 4px 8px;
    min-height: 20px;
}
QLineEdit:focus { border-color: #4a90d9; }
QCheckBox { color: #cccccc; spacing: 6px; }
QCheckBox::indicator {
    width: 14px; height: 14px;
    border: 1px solid #666666;
    border-radius: 3px;
    background-color: #383838;
}
QCheckBox::indicator:checked { background-color: #4a90d9; border-color: #5a9ada; }
QCheckBox::indicator:hover   { border-color: #4a90d9; }
QRadioButton { color: #cccccc; spacing: 6px; }
QRadioButton::indicator { width: 14px; height: 14px; }
QDoubleSpinBox {
    background-color: #383838;
    color: #d4d4d4;
    border: 1px solid #555555;
    border-radius: 4px;
    padding: 4px 8px;
}
QTreeWidget {
    background-color: #333333;
    color: #d4d4d4;
    border: 1px solid #555555;
    border-radius: 4px;
    alternate-background-color: #383838;
}
QFrame#separator { background-color: #444444; max-height: 1px; }
QToolTip {
    background-color: #404040;
    color: #e0e0e0;
    border: 1px solid #666666;
    border-radius: 3px;
    padding: 4px 8px;
    font-size: 11px;
}
"""


# ---------------------------------------------------------------------------
# Maya helpers
# ---------------------------------------------------------------------------

def maya_main_window():
    ptr = omui.MQtUtil.mainWindow()
    return wrapInstance(int(ptr), QtWidgets.QWidget)


# ---------------------------------------------------------------------------
# SnapshotEditorDialog — per-channel flip rule editor (Character Snapshot)
# ---------------------------------------------------------------------------

class SnapshotEditorDialog(QtWidgets.QDialog):
    """
    Channel flip-rule editor backed by the Character Snapshot.

    Lists every control recorded in the rig's Character Snapshot (grouped
    into mirror pairs and middle controls) with a per-attribute dropdown:

        (auto: …)  — use the rule auto-detected from the rig's default pose
                     at snapshot time, or the runtime axis heuristic when no
                     rule was stored
        copy       — always transfer the value as-is
        negate     — always invert the sign
        ignore     — never touch this channel

    Choosing copy / negate / ignore stores a per-channel override inside the
    Character Snapshot, so the correction is shared by every ATK tool that
    reads the snapshot. Choosing the (auto…) entry removes the override.
    Click "Save to Scene" to persist.
    """

    HEADERS = ["Name", "Side", "Rule"]

    def __init__(self, adapter, prefix=None, re_snapshot_callback=None, parent=None):
        super().__init__(parent or maya_main_window())
        self.adapter              = adapter
        self._prefix              = prefix
        self.re_snapshot_callback = re_snapshot_callback   # callable () -> adapter | None
        self.setWindowTitle("Channel Flip Rules  —  Mirror Controls")
        self.setStyleSheet(DARK_STYLESHEET)
        self.resize(680, 560)
        self._build_ui()
        self._populate()

    # ------------------------------------------------------------------

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        self.info_label = QtWidgets.QLabel()
        self.info_label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(self.info_label)

        sep = QtWidgets.QFrame()
        sep.setFrameShape(QtWidgets.QFrame.HLine)
        sep.setFrameShadow(QtWidgets.QFrame.Sunken)
        layout.addWidget(sep)

        hint = QtWidgets.QLabel(
            "Rules are per-attribute.  "
            "<b>(auto)</b> = rule detected from the default-pose snapshot  ·  "
            "<b>copy</b> = transfer value as-is  ·  "
            "<b>negate</b> = transfer negated value  ·  "
            "<b>ignore</b> = skip this attribute"
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.tree = QtWidgets.QTreeWidget()
        self.tree.setColumnCount(3)
        self.tree.setHeaderLabels(self.HEADERS)
        self.tree.setAlternatingRowColors(True)
        self.tree.setUniformRowHeights(True)
        hdr = self.tree.header()
        hdr.setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        hdr.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(2, QtWidgets.QHeaderView.Fixed)
        self.tree.header().resizeSection(2, 130)
        layout.addWidget(self.tree)

        btn_row = QtWidgets.QHBoxLayout()
        self.re_snap_btn = QtWidgets.QPushButton("Re-Snapshot")
        self.re_snap_btn.setToolTip(
            "Re-sample the rig at its current pose, replacing the stored\n"
            "default-pose values and auto-detected rules.\n"
            "Manual pairs, exclusions and rule overrides are preserved."
        )
        self.expand_btn   = QtWidgets.QPushButton("Expand All")
        self.collapse_btn = QtWidgets.QPushButton("Collapse All")
        self.save_btn     = QtWidgets.QPushButton("Save to Scene")
        self.close_btn    = QtWidgets.QPushButton("Close")

        btn_row.addWidget(self.re_snap_btn)
        btn_row.addWidget(self.expand_btn)
        btn_row.addWidget(self.collapse_btn)
        btn_row.addStretch()
        btn_row.addWidget(self.save_btn)
        btn_row.addWidget(self.close_btn)
        layout.addLayout(btn_row)

        self.re_snap_btn.clicked.connect(self._on_re_snapshot)
        self.expand_btn.clicked.connect(self.tree.expandAll)
        self.collapse_btn.clicked.connect(self.tree.collapseAll)
        self.save_btn.clicked.connect(self._on_save)
        self.close_btn.clicked.connect(self.close)

    # ------------------------------------------------------------------

    def _populate(self):
        self.tree.clear()
        controls = self.adapter.cs_controls()

        n_ctrls = len(controls)
        n_pairs = self.adapter.pair_count()
        self.info_label.setText(
            "<b>{} controls</b>  ·  <b>{} pairs</b>  ·  "
            "Mirror axis: <b>{}</b>  ·  "
            "Left token: <b>{}</b>  ·  Right token: <b>{}</b>".format(
                n_ctrls, n_pairs, self.adapter.mirror_axis,
                self.adapter.left_token, self.adapter.right_token,
            )
        )

        # Partner names are stored as namespace-qualified short names while
        # the control keys are full DAG paths — resolve through leaf names.
        leaf_to_key = {k.split("|")[-1]: k for k in controls}

        seen    = set()
        pairs   = []
        middles = []
        for ctrl, data in controls.items():
            if ctrl in seen:
                continue
            side        = data.get("side", "middle")
            partner     = data.get("partner")
            partner_key = leaf_to_key.get(partner.split("|")[-1]) if partner else None
            if side == "left" and partner_key:
                pairs.append((ctrl, partner_key))
                seen.add(ctrl)
                seen.add(partner_key)
            elif side == "right" and partner_key:
                if partner_key not in seen:
                    pairs.append((partner_key, ctrl))
                seen.add(ctrl)
                seen.add(partner_key)
            else:
                middles.append(ctrl)
                seen.add(ctrl)

        if pairs:
            section = self._make_section_header(
                "Paired Controls ({} pairs)".format(len(pairs)))
            self.tree.addTopLevelItem(section)
            for lf, rt in sorted(pairs):
                pair_item = self._make_pair_item(lf, rt)
                self.tree.addTopLevelItem(pair_item)
                pair_item.setExpanded(True)
                for i in range(pair_item.childCount()):
                    pair_item.child(i).setExpanded(False)

        if middles:
            section = self._make_section_header(
                "Middle Controls ({})".format(len(middles)))
            self.tree.addTopLevelItem(section)
            for ctrl in sorted(middles):
                ctrl_item = self._make_ctrl_item(ctrl)
                self.tree.addTopLevelItem(ctrl_item)
                ctrl_item.setExpanded(False)

    def _make_section_header(self, text):
        item = QtWidgets.QTreeWidgetItem([" {}".format(text), "", ""])
        item.setFlags(QtCore.Qt.ItemIsEnabled)
        font = item.font(0)
        font.setBold(True)
        item.setFont(0, font)
        bg = QtGui.QColor(60, 60, 60)
        for col in range(3):
            item.setBackground(col, bg)
        return item

    def _make_pair_item(self, lf, rt):
        lf_short = lf.split("|")[-1].split(":")[-1]
        rt_short = rt.split("|")[-1].split(":")[-1]
        pair_item = QtWidgets.QTreeWidgetItem(
            ["  {} ↔ {}".format(lf_short, rt_short), "", ""]
        )
        pair_item.setFlags(QtCore.Qt.ItemIsEnabled)
        font = pair_item.font(0)
        font.setItalic(True)
        pair_item.setFont(0, font)
        for ctrl in (lf, rt):
            pair_item.addChild(self._make_ctrl_item(ctrl))
        return pair_item

    def _make_ctrl_item(self, ctrl):
        controls  = self.adapter.cs_controls()
        data      = controls.get(ctrl, {})
        side      = data.get("side", "middle")
        leaf      = ctrl.split("|")[-1]
        ctrl_item = QtWidgets.QTreeWidgetItem([leaf, side, ""])
        ctrl_item.setFlags(QtCore.Qt.ItemIsEnabled)
        font = ctrl_item.font(0)
        font.setBold(True)
        ctrl_item.setFont(0, font)

        attrs = data.get("attributes", [])
        attr_names = sorted(attrs.keys()) if isinstance(attrs, dict) else sorted(attrs)
        for attr_name in attr_names:
            auto_rule = self.adapter.get_auto_rule(ctrl, attr_name)
            override  = self.adapter.get_override(ctrl, attr_name)

            row = QtWidgets.QTreeWidgetItem([attr_name, "", ""])
            row.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable)
            if override in RULES:
                font = row.font(0)
                font.setItalic(True)
                row.setFont(0, font)
                row.setToolTip(0, "User override")
            ctrl_item.addChild(row)

            auto_label = "(auto: {})".format(auto_rule) if auto_rule in RULES \
                         else "(auto: heuristic)"
            combo = QtWidgets.QComboBox()
            combo.addItem(auto_label)
            combo.addItems(RULES)
            combo.setCurrentText(override if override in RULES else auto_label)
            self._style_combo(combo, override if override in RULES else None)
            combo.currentTextChanged.connect(
                lambda new_text, c=ctrl, a=attr_name, cb=combo:
                    self._on_rule_changed(c, a, new_text, cb)
            )
            self.tree.setItemWidget(row, 2, combo)

        return ctrl_item

    @staticmethod
    def _style_combo(combo, rule):
        if rule == RULE_NEGATE:
            combo.setStyleSheet("QComboBox { color: #e8a060; }")
        elif rule == RULE_IGNORE:
            combo.setStyleSheet("QComboBox { color: #888888; }")
        elif rule == RULE_COPY:
            combo.setStyleSheet("QComboBox { color: #d4d4d4; }")
        else:
            combo.setStyleSheet("QComboBox { color: #8a9a8a; }")

    # ------------------------------------------------------------------

    def _on_rule_changed(self, ctrl, attr, new_text, combo):
        if new_text in RULES:
            self.adapter.set_rule(ctrl, attr, new_text)
            self._style_combo(combo, new_text)
        else:
            # "(auto: …)" selected — remove the override.
            self.adapter.clear_rule(ctrl, attr)
            self._style_combo(combo, None)

    def _on_re_snapshot(self):
        if not self.re_snapshot_callback:
            return
        new_adapter = self.re_snapshot_callback()
        if new_adapter:
            self.adapter = new_adapter
            self._populate()

    def _on_save(self):
        self.adapter._dirty = True   # force write even if only combos touched
        self.adapter.save()
        pfx_label = self._prefix if self._prefix and self._prefix != DEFAULT_PREFIX else "(scene)"
        QtWidgets.QMessageBox.information(
            self, "Saved",
            "Channel rules saved to the Character Snapshot for '{}'.".format(pfx_label)
        )

    # ------------------------------------------------------------------

    def update_adapter(self, adapter, prefix=None):
        self.adapter = adapter
        if prefix is not None:
            self._prefix = prefix
        self._populate()


# ---------------------------------------------------------------------------
# MirrorControls  (main dialog)
# ---------------------------------------------------------------------------

class MirrorControls(QtWidgets.QDialog):

    dlg_instance                = None
    snapshot_editor_instance    = None
    manual_pair_editor_instance = None

    @classmethod
    def show_dialog(cls):
        if not cls.dlg_instance:
            cls.dlg_instance = MirrorControls()
        if cls.dlg_instance.isHidden():
            cls.dlg_instance.show()
        else:
            cls.dlg_instance.raise_()
            cls.dlg_instance.activateWindow()

    def __init__(self, parent=None):
        # Resolve the Maya main window lazily — evaluating it in the default
        # argument runs at import time and crashes when the UI isn't up yet.
        super().__init__(parent or maya_main_window())
        self.setWindowTitle("Mirror Controls  v2.3.3")
        flags = self.windowFlags()
        flags ^= QtCore.Qt.WindowMinimizeButtonHint
        flags ^= QtCore.Qt.WindowMaximizeButtonHint
        self.setWindowFlags(flags)
        self._saved_geometry = None
        self._active_prefix  = None    # set by combobox or auto-detected

        self.setStyleSheet(DARK_STYLESHEET)
        self.setMinimumWidth(380)

        self._create_menus()
        self.create_widgets()
        self.create_layout()
        self.create_connections()
        # One-time, non-destructive: adopt any legacy RigSnapshot data into
        # the Character Snapshot store so old scenes keep their pairs/rules.
        _migrate_legacy_snapshots()
        self._refresh_prefix_combobox()
        self._refresh_snapshot_status()

    # ------------------------------------------------------------------
    # Menus
    # ------------------------------------------------------------------

    def _create_menus(self):
        self.menu_bar = QtWidgets.QMenuBar(self)

        # ---- Tools menu ----
        tools_menu = self.menu_bar.addMenu("Tools")

        take_snap_action = QtGui.QAction("Take Snapshot", self)
        take_snap_action.setToolTip(
            "Capture a Character Snapshot of the selected rig at its\n"
            "default pose. Records every controller, its mirror partner\n"
            "and per-channel flip rules."
        )
        take_snap_action.triggered.connect(self.take_snapshot)
        tools_menu.addAction(take_snap_action)

        edit_snap_action = QtGui.QAction("Edit Channel Flip Rules…", self)
        edit_snap_action.setToolTip(
            "Review the auto-detected per-channel copy / negate rules and\n"
            "store manual overrides in the Character Snapshot."
        )
        edit_snap_action.triggered.connect(self.open_snapshot_editor)
        tools_menu.addAction(edit_snap_action)

        tools_menu.addSeparator()

        manual_action = QtGui.QAction("Manual Pair Editor…", self)
        manual_action.setToolTip(
            "Open the Character Snapshot Manual Pair Editor to assign\n"
            "mirror partners that automatic matching cannot resolve,\n"
            "and to exclude rig-internal controls from mirroring."
        )
        manual_action.triggered.connect(self.open_manual_pair_editor)
        tools_menu.addAction(manual_action)

        tools_menu.addSeparator()

        flip_sign_action = QtGui.QAction("Flip Sign (Selected)", self)
        flip_sign_action.setToolTip(
            "Toggle whole-control sign inversion for the selected controls.\n"
            "Use this when a control mirrors with the wrong sign due to how\n"
            "the rig was built. Stored in the Character Snapshot."
        )
        flip_sign_action.triggered.connect(self.flip_sign_rules)
        tools_menu.addAction(flip_sign_action)

        tools_menu.addSeparator()

        manage_action = QtGui.QAction("Open Character Snapshot Tool…", self)
        manage_action.setToolTip(
            "Open the Character Snapshot tool — the central manager for\n"
            "rig snapshots (create, export/import JSON, rename prefixes,\n"
            "manual pairs, delete)."
        )
        manage_action.triggered.connect(self.open_snapshot_manager)
        tools_menu.addAction(manage_action)

        # ---- Help menu ----
        help_menu = self.menu_bar.addMenu("Help")

        how_to_action = QtGui.QAction("How To Use…", self)
        how_to_action.setToolTip("Step-by-step guide for every feature")
        how_to_action.triggered.connect(self.show_help)
        help_menu.addAction(how_to_action)

        help_menu.addSeparator()

        about_action = QtGui.QAction("About Mirror Controls", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    # ------------------------------------------------------------------
    # Widgets
    # ------------------------------------------------------------------

    def _make_icon_btn(self, label, tooltip, obj_name=None):
        """Create a styled, tooltipped button. Plain text labels only —
        emoji icons render as empty boxes in Maya's UI font on Windows."""
        btn = QtWidgets.QPushButton(label)
        btn.setToolTip(tooltip)
        if obj_name:
            btn.setObjectName(obj_name)
        return btn

    def create_widgets(self):
        # ---- Mirror Controls ----
        self.mirror_axis_cb = QtWidgets.QComboBox()
        self.mirror_axis_cb.addItems(["X", "Y", "Z"])
        self.mirror_axis_cb.setToolTip(
            "The world axis across which the pose is mirrored.\n"
            "Most bipedal rigs mirror across X."
        )

        self.operation_cb = QtWidgets.QComboBox()
        self.operation_cb.addItems([
            OperationType.left_to_right,
            OperationType.right_to_left,
            OperationType.flip,
            OperationType.flip_to_frame,
            OperationType.mirror_middle,
            OperationType.selected,
            OperationType.not_selected,
        ])
        self.operation_cb.setToolTip(
            "Choose the mirror operation:\n\n"
            "  Left to Right — Copy left-side values to right-side partners\n"
            "  Right to Left — Copy right-side values to left-side partners\n"
            "  Flip — Swap both sides simultaneously\n"
            "  Flip to Frame — Flip and jump to the specified frame\n"
            "  Mirror Middle — Mirror centre controls (no L/R token)\n"
            "  Selected — Process only the currently selected controls\n"
            "  Not Selected — Process all except selected (direction below)"
        )
        self.operation_cb.setCurrentText(OperationType.selected)

        self.mirror_frame_dsb = QtWidgets.QDoubleSpinBox()
        self.mirror_frame_dsb.setRange(-1000000, 1000000)
        self.mirror_frame_dsb.setDecimals(1)
        self.mirror_frame_dsb.setValue(self.get_min_time())
        self.mirror_frame_dsb.setSingleStep(1)
        self.mirror_frame_dsb.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        self.mirror_frame_dsb.setVisible(False)

        self.left_to_right_rb = QtWidgets.QRadioButton("Left To Right")
        self.left_to_right_rb.setChecked(True)
        self.right_to_left_rb = QtWidgets.QRadioButton("Right To Left")
        self.flip_rb           = QtWidgets.QRadioButton("Flip")
        self.left_to_right_rb.setVisible(False)
        self.right_to_left_rb.setVisible(False)
        self.flip_rb.setVisible(False)

        self.preserve_translation_cb = QtWidgets.QCheckBox("Preserve Translation")
        self.preserve_translation_cb.setChecked(True)
        self.preserve_translation_cb.setToolTip(
            "If checked, translation channels are copied exactly\n"
            "rather than negated on the mirror axis.\n"
            "(Only applies to channels without a snapshot rule.)"
        )

        self.preserve_rotation_cb = QtWidgets.QCheckBox("Preserve Rotation")
        self.preserve_rotation_cb.setChecked(True)
        self.preserve_rotation_cb.setToolTip(
            "If checked, rotation channels are copied exactly\n"
            "rather than negated.\n"
            "(Only applies to channels without a snapshot rule.)"
        )

        # ---- Naming ----
        self.left_ctrl_name_le = QtWidgets.QLineEdit()
        self.left_ctrl_name_le.setPlaceholderText("lf")
        self.left_ctrl_name_le.setToolTip(
            "Left-side naming token used in the rig's control names.\n"
            "Example: 'lf' matches ac_lf_handIK\n"
            "Leave blank to use the default 'lf'.\n\n"
            "When a Character Snapshot exists its stored tokens are used;\n"
            "common conventions (L/R, left/right, lt/rt, …) are also tried\n"
            "automatically."
        )
        self.right_ctrl_name_le = QtWidgets.QLineEdit()
        self.right_ctrl_name_le.setPlaceholderText("rt")
        self.right_ctrl_name_le.setToolTip(
            "Right-side naming token used in the rig's control names.\n"
            "Example: 'rt' matches ac_rt_handIK\n"
            "Leave blank to use the default 'rt'."
        )

        # ---- Mirror button ----
        self.mirror_btn = QtWidgets.QPushButton("Mirror")
        self.mirror_btn.setObjectName("mirrorBtn")
        self.mirror_btn.setToolTip(
            "Execute the mirror operation with the current settings.\n\n"
            "If controls are selected, only those are processed.\n"
            "If nothing is selected, all rig controls are mirrored."
        )

        # ---- Snapshot Tools ----
        # Snapshot capture is intentionally NOT a button here — it lives in
        # the Tools menu and in the Character Snapshot tool (Manage button),
        # which is the source of truth for snapshot data.
        self.edit_snap_btn = self._make_icon_btn(
            "Edit Rules",
            "Review the auto-detected per-channel copy / negate rules\n"
            "and store manual overrides in the Character Snapshot.",
            "snapshotBtn"
        )
        self.manual_pairs_btn = self._make_icon_btn(
            "Manual Pairs",
            "Open the Character Snapshot Manual Pair Editor to fix\n"
            "controls that automatic name-matching could not resolve.\n\n"
            "Also lets you exclude rig-internal nodes that\n"
            "should never be mirrored.",
            "snapshotBtn"
        )
        self.flip_sign_btn = self._make_icon_btn(
            "Flip Sign",
            "Toggle whole-control sign inversion for the selected\n"
            "controls.\n\n"
            "Use when a control mirrors with the wrong sign due\n"
            "to how the rig was built (e.g. negated axes on one side).\n"
            "Stored in the Character Snapshot immediately.",
            "flipSignBtn"
        )

        # ---- Character prefix selector ----
        self.prefix_cb = QtWidgets.QComboBox()
        self.prefix_cb.setToolTip(
            "Select which character rig's Character Snapshot to use.\n\n"
            "Auto-detected from the selection when mirroring.\n"
            "Each character namespace gets its own stored snapshot."
        )
        # Use a Qt standard icon — arrow/emoji glyphs render as empty
        # boxes in Maya's UI font on Windows.
        self.refresh_prefix_btn = QtWidgets.QPushButton()
        self.refresh_prefix_btn.setIcon(
            self.style().standardIcon(QtWidgets.QStyle.SP_BrowserReload))
        self.refresh_prefix_btn.setFixedWidth(28)
        self.refresh_prefix_btn.setToolTip("Refresh the character list")
        self.manage_snaps_btn = self._make_icon_btn(
            "Manage",
            "Open the Character Snapshot tool to take snapshots and to\n"
            "create, export, import, rename or delete character data.",
            "snapshotBtn"
        )

        # ---- Snapshot status ----
        self.snapshot_status_label = QtWidgets.QLabel()
        self.snapshot_status_label.setAlignment(QtCore.Qt.AlignLeft)
        self.snapshot_status_label.setWordWrap(True)

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def create_layout(self):
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)
        main_layout.setMenuBar(self.menu_bar)

        # ── Mirror Controls group ──
        mirror_grp = QtWidgets.QGroupBox("Mirror Controls")
        mirror_grp.setStyleSheet(
            "QGroupBox { border-color: #4a6a9a; }"
            "QGroupBox::title { color: #8ab4f8; background-color: #2f3a4a; }"
        )
        mirror_lay = QtWidgets.QVBoxLayout(mirror_grp)
        mirror_lay.setSpacing(6)

        form = QtWidgets.QFormLayout()
        form.setLabelAlignment(QtCore.Qt.AlignRight)
        form.setSpacing(6)
        form.addRow("Mirror Axis:", self.mirror_axis_cb)
        form.addRow("Operation:", self.operation_cb)
        form.addRow("", self.mirror_frame_dsb)

        rb_row = QtWidgets.QHBoxLayout()
        rb_row.addWidget(self.left_to_right_rb)
        rb_row.addWidget(self.right_to_left_rb)
        rb_row.addWidget(self.flip_rb)
        form.addRow("", rb_row)

        opt_row = QtWidgets.QHBoxLayout()
        opt_row.addWidget(self.preserve_translation_cb)
        opt_row.addWidget(self.preserve_rotation_cb)
        form.addRow("Fallback:", opt_row)
        mirror_lay.addLayout(form)

        mirror_lay.addWidget(self.mirror_btn)
        main_layout.addWidget(mirror_grp)

        # ── Naming Convention group ──
        naming_grp = QtWidgets.QGroupBox("Naming Convention")
        naming_grp.setStyleSheet(
            "QGroupBox { border-color: #6a5a8a; }"
            "QGroupBox::title { color: #c0a0e0; background-color: #3a2f4a; }"
        )
        naming_lay = QtWidgets.QFormLayout(naming_grp)
        naming_lay.setLabelAlignment(QtCore.Qt.AlignRight)
        naming_lay.setSpacing(6)
        naming_lay.addRow("Left Token:", self.left_ctrl_name_le)
        naming_lay.addRow("Right Token:", self.right_ctrl_name_le)
        main_layout.addWidget(naming_grp)

        # ── Snapshot Tools group ──
        snap_grp = QtWidgets.QGroupBox("Character Snapshot")
        snap_grp.setStyleSheet(
            "QGroupBox { border-color: #4a6a4a; }"
            "QGroupBox::title { color: #90c890; background-color: #2f3a2f; }"
        )
        snap_lay = QtWidgets.QVBoxLayout(snap_grp)
        snap_lay.setSpacing(6)

        # Character prefix selector
        prefix_row = QtWidgets.QHBoxLayout()
        prefix_row.addWidget(QtWidgets.QLabel("Character:"))
        prefix_row.addWidget(self.prefix_cb, 1)
        prefix_row.addWidget(self.refresh_prefix_btn)
        prefix_row.addWidget(self.manage_snaps_btn)
        snap_lay.addLayout(prefix_row)

        snap_btn_row = QtWidgets.QHBoxLayout()
        snap_btn_row.addWidget(self.edit_snap_btn)
        snap_btn_row.addWidget(self.manual_pairs_btn)
        snap_btn_row.addWidget(self.flip_sign_btn)
        snap_lay.addLayout(snap_btn_row)

        # Status
        snap_lay.addWidget(self.snapshot_status_label)
        main_layout.addWidget(snap_grp)

        # ── Info footer ──
        info = QtWidgets.QLabel(
            "<span style='color:#777;font-size:10px;'>"
            "Select controls before mirroring, or leave selection empty to mirror all."
            "</span>"
        )
        info.setAlignment(QtCore.Qt.AlignCenter)
        info.setWordWrap(True)
        main_layout.addWidget(info)

    # ------------------------------------------------------------------
    # Connections
    # ------------------------------------------------------------------

    def create_connections(self):
        self.operation_cb.currentTextChanged.connect(self.on_operation_change)
        self.mirror_btn.clicked.connect(self.mirror_control)
        self.edit_snap_btn.clicked.connect(self.open_snapshot_editor)
        self.manual_pairs_btn.clicked.connect(self.open_manual_pair_editor)
        self.flip_sign_btn.clicked.connect(self.flip_sign_rules)
        self.prefix_cb.currentTextChanged.connect(self._on_prefix_changed)
        self.refresh_prefix_btn.clicked.connect(self._on_refresh_prefixes)
        self.manage_snaps_btn.clicked.connect(self.open_snapshot_manager)

    # ------------------------------------------------------------------
    # Prefix management
    # ------------------------------------------------------------------

    def get_active_prefix(self):
        """Return the currently selected character prefix, or None."""
        txt = self.prefix_cb.currentText()
        if not txt or txt == "(none)":
            return None
        if txt == "(no namespace)":
            return DEFAULT_PREFIX
        return txt

    def _resolve_prefix_for_controls(self, controls):
        """
        Resolve the Character Snapshot prefix for *controls*.

        Priority:
          1) Namespace detected from selection (fast path).
          2) Active combobox prefix (if it has a stored snapshot).
          3) Scan stored snapshots and find one that contains the selected
             control name(s), matching both full key and leaf key.
        """
        controls = controls or []
        if not controls:
            return self._active_prefix or self.get_active_prefix()

        detected = _detect_prefix(controls[0])
        if _load_character_snapshot_for(detected) is not None:
            return detected

        active = self._active_prefix or self.get_active_prefix()
        if active and _load_character_snapshot_for(active) is not None:
            return active

        leaves = {c.split("|")[-1] for c in controls}
        for pfx in _list_character_snapshot_prefixes():
            snap = _load_character_snapshot_for(pfx)
            if snap is None:
                continue
            ctrl_keys = set((snap.controls or {}).keys())
            ctrl_leaves = {k.split("|")[-1] for k in ctrl_keys}
            if leaves & ctrl_keys or leaves & ctrl_leaves:
                return pfx

        return detected

    def _refresh_prefix_combobox(self):
        """Re-populate the prefix combobox from Character Snapshot prefixes."""
        old = self.prefix_cb.currentText()
        self.prefix_cb.blockSignals(True)
        self.prefix_cb.clear()

        prefixes = _list_character_snapshot_prefixes()
        if not prefixes:
            self.prefix_cb.addItem("(none)")
        else:
            for pfx in prefixes:
                label = pfx if pfx != DEFAULT_PREFIX else "(no namespace)"
                self.prefix_cb.addItem(label)

            # Restore previous selection if still available
            idx = self.prefix_cb.findText(old)
            if idx >= 0:
                self.prefix_cb.setCurrentIndex(idx)
            else:
                # If no previous selection, try to auto-select the rig under
                # the current viewport selection.
                sel = cmds.ls(selection=True, long=True) or []
                auto_prefix = self._resolve_prefix_for_controls(sel)
                if auto_prefix:
                    auto_label = (
                        "(no namespace)" if auto_prefix == DEFAULT_PREFIX else auto_prefix
                    )
                    auto_idx = self.prefix_cb.findText(auto_label)
                    if auto_idx >= 0:
                        self.prefix_cb.setCurrentIndex(auto_idx)

        self.prefix_cb.blockSignals(False)
        self._active_prefix = self.get_active_prefix()

    def _on_refresh_prefixes(self):
        self._refresh_prefix_combobox()
        self._refresh_snapshot_status()

    def _on_prefix_changed(self, text):
        """Called when the user changes the character prefix dropdown."""
        if text == "(none)" or text == "(no namespace)":
            self._active_prefix = DEFAULT_PREFIX if text == "(no namespace)" else None
        else:
            self._active_prefix = text
        self._refresh_snapshot_status()

    def _get_controls_for_prefix(self, prefix):
        """
        Return all NURBS controls whose namespace matches *prefix*.
        If prefix is DEFAULT_PREFIX, returns controls with no namespace.
        """
        all_ctrls = self._get_all_nurbs_controls()
        return [c for c in all_ctrls if _detect_prefix(c) == prefix]

    def open_snapshot_manager(self):
        """Open the Character Snapshot tool (the central snapshot manager)."""
        cs_mod = _try_import_character_snapshot()
        if cs_mod is None:
            self._show_character_snapshot_missing()
            return
        try:
            cs_mod.show_dialog()
        except Exception as exc:
            om.MGlobal.displayError(
                "[Mirror Controls] Could not launch Character Snapshot: {}".format(exc)
            )

    def _show_character_snapshot_missing(self):
        QtWidgets.QMessageBox.critical(
            self, "Character Snapshot Tool Not Found",
            "The Character Snapshot module (character_snapshot_v1_0_0) could "
            "not be imported.\n\n"
            "Mirror Controls relies on the Character Snapshot tool for all "
            "snapshot and matching data. Please install it from the Animation "
            "Tool Kit (Character_Snapshot_1_0_0 folder) and try again."
        )

    # ------------------------------------------------------------------
    # Snapshot — take & edit  (delegates to Character Snapshot)
    # ------------------------------------------------------------------

    def _resolve_snapshot_targets(self):
        """Determine (prefix, ctrl_list) for snapshotting.

        Selection: prefix detected from the first selected control, expanded
        to every control sharing that namespace. No selection: the active
        combobox prefix, or all scene controls grouped under the first
        detected prefix. Returns (None, []) when nothing usable is found.
        """
        sel = cmds.ls(selection=True, long=True)
        if sel:
            prefix = _detect_prefix(sel[0])
            ctrl_list = self._get_controls_for_prefix(prefix) or sel
            return prefix, ctrl_list

        active = self._active_prefix or self.get_active_prefix()
        if active and active != DEFAULT_PREFIX:
            return active, self._get_controls_for_prefix(active)

        ctrl_list = self._get_all_nurbs_controls()
        if not ctrl_list:
            return None, []
        prefix = DEFAULT_PREFIX
        for c in ctrl_list:
            p = _detect_prefix(c)
            if p != DEFAULT_PREFIX:
                prefix = p
                break
        # Re-filter to just this prefix to avoid mixing characters
        filtered = self._get_controls_for_prefix(prefix)
        return prefix, (filtered or ctrl_list)

    def take_snapshot(self):
        """Capture a Character Snapshot for the selected rig.

        The snapshot should be taken at the rig's DEFAULT POSE — the stored
        pose values drive the automatic per-channel flip detection. Manual
        pairs, exclusions and metadata of an existing snapshot are preserved
        on replace.
        """
        cs_mod = _try_import_character_snapshot()
        if cs_mod is None:
            self._show_character_snapshot_missing()
            return

        left_token  = self.get_left_name()
        right_token = self.get_right_name()
        mirror_axis = self.get_mirror_axis()

        prefix, ctrl_list = self._resolve_snapshot_targets()
        if not ctrl_list:
            QtWidgets.QMessageBox.warning(
                self, "No Controls Found",
                "No NURBS controls were found to snapshot.\n"
                "Select a control on the rig you want to capture and try again."
            )
            return

        om.MGlobal.displayInfo(
            "[Mirror Controls] Taking Character Snapshot for '{}' — "
            "{} controls…".format(prefix, len(ctrl_list))
        )

        existing = cs_mod.load_snapshot(prefix)
        rig_name     = prefix.split(":")[-1] if prefix != DEFAULT_PREFIX else ""
        description  = ""
        manual_pairs = {}
        excluded     = []
        metadata     = {}
        created      = None
        if existing is not None:
            result = QtWidgets.QMessageBox.question(
                self, "Snapshot Already Exists",
                "A Character Snapshot already exists for '{}' with {} "
                "controls.\n\n"
                "Replace it with a fresh capture of the current pose?\n"
                "(Manual pairs, exclusions and rule overrides are kept.)".format(
                    prefix, existing.control_count()
                ),
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.Cancel,
            )
            if result != QtWidgets.QMessageBox.Yes:
                return
            rig_name     = existing.rig_name or rig_name
            description  = existing.description
            manual_pairs = dict(existing.manual_pairs)
            excluded     = list(existing.excluded_controls)
            metadata     = dict(existing.metadata or {})
            created      = existing.created
            # Reuse the rig's stored tokens when the UI is at its defaults so
            # re-snapshotting doesn't silently revert a custom convention.
            if not self.left_ctrl_name_le.text().strip():
                left_token = existing.left_token
            if not self.right_ctrl_name_le.text().strip():
                right_token = existing.right_token

        snap = cs_mod.CharacterSnapshot.build(
            ctrl_list, prefix=prefix, rig_name=rig_name,
            description=description, left_token=left_token,
            right_token=right_token, mirror_axis=mirror_axis,
        )
        snap.manual_pairs      = manual_pairs
        snap.excluded_controls = excluded
        snap.metadata          = metadata
        if created:
            snap.created = created
        snap.save_to_scene()

        self._active_prefix = prefix
        self._refresh_prefix_combobox()
        label = prefix if prefix != DEFAULT_PREFIX else "(no namespace)"
        idx = self.prefix_cb.findText(label)
        if idx >= 0:
            self.prefix_cb.setCurrentIndex(idx)
        self._refresh_snapshot_status()

        # --- Pairing report ---
        unique_pairs, unpaired = snap.analyse_pairing()
        if not unpaired:
            msg = (
                "✔  All {} controls paired successfully  ({} pairs).\n\n"
                "Would you like to review the per-channel flip rules?".format(
                    snap.control_count(), unique_pairs)
            )
            btns = QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
            box  = QtWidgets.QMessageBox(
                QtWidgets.QMessageBox.Information, "Snapshot Complete", msg, btns, self
            )
            box.setDefaultButton(QtWidgets.QMessageBox.No)
            if box.exec() == QtWidgets.QMessageBox.Yes:
                self.open_snapshot_editor()
        else:
            sample  = unpaired[:10]
            surplus = len(unpaired) - len(sample)
            names   = "\n".join("  •  {}".format(n) for n in sample)
            if surplus > 0:
                names += "\n  … and {} more".format(surplus)
            msg = (
                "Snapshot saved — {} controls, {} pair{} found.\n\n"
                "⚠  {} control{} could not be automatically paired:\n\n"
                "{}\n\n"
                "These controls need manual partner assignment.\n"
                "Open the Manual Pair Editor now?".format(
                    snap.control_count(),
                    unique_pairs, "s" if unique_pairs != 1 else "",
                    len(unpaired), "s" if len(unpaired) != 1 else "",
                    names,
                )
            )
            box = QtWidgets.QMessageBox(
                QtWidgets.QMessageBox.Warning, "Snapshot — Pairing Issues", msg, parent=self
            )
            open_manual_btn = box.addButton("Open Manual Pairs…", QtWidgets.QMessageBox.AcceptRole)
            box.addButton("Dismiss", QtWidgets.QMessageBox.RejectRole)
            box.setDefaultButton(open_manual_btn)
            box.exec()
            if box.clickedButton() is open_manual_btn:
                self.open_manual_pair_editor()

    def open_snapshot_editor(self):
        """Open the channel flip-rule editor for the active rig's snapshot."""
        prefix = self._active_prefix or self.get_active_prefix()
        sel = cmds.ls(selection=True, long=True) or []
        if sel:
            prefix = self._resolve_prefix_for_controls(sel)
        adapter = self._load_snapshot_for_mirroring(prefix, announce=False)
        if adapter is None:
            result = QtWidgets.QMessageBox.question(
                self, "No Character Snapshot",
                "No Character Snapshot found{}.\n"
                "Would you like to take one now?".format(
                    " for '{}'".format(prefix) if prefix and prefix != DEFAULT_PREFIX else ""
                ),
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            )
            if result == QtWidgets.QMessageBox.Yes:
                self.take_snapshot()
            return
        self._open_editor_with_adapter(adapter, prefix)

    def open_manual_pair_editor(self):
        """Open the Character Snapshot Manual Pair Editor."""
        cs_mod = _try_import_character_snapshot()
        if cs_mod is None:
            self._show_character_snapshot_missing()
            return

        prefix = self._active_prefix or self.get_active_prefix()
        sel = cmds.ls(selection=True, long=True) or []
        if sel:
            prefix = self._resolve_prefix_for_controls(sel)

        if not prefix or cs_mod.load_snapshot(prefix) is None:
            result = QtWidgets.QMessageBox.question(
                self, "No Character Snapshot",
                "Manual pairs are stored in the rig's Character Snapshot, "
                "and none was found{}.\n\n"
                "Take a Character Snapshot now?".format(
                    " for '{}'".format(prefix) if prefix and prefix != DEFAULT_PREFIX else ""
                ),
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            )
            if result == QtWidgets.QMessageBox.Yes:
                self.take_snapshot()
            return

        cls = MirrorControls
        if (cls.manual_pair_editor_instance
                and not cls.manual_pair_editor_instance.isHidden()):
            cls.manual_pair_editor_instance.close()
        try:
            cls.manual_pair_editor_instance = cs_mod.ManualPairEditorDialog(
                prefix=prefix, parent=self
            )
            cls.manual_pair_editor_instance.show()
        except Exception as exc:
            om.MGlobal.displayError(
                "[Mirror Controls] Could not open the Manual Pair Editor: {}".format(exc)
            )

    def _open_editor_with_adapter(self, adapter, prefix=None):
        cls = MirrorControls
        if cls.snapshot_editor_instance and not cls.snapshot_editor_instance.isHidden():
            cls.snapshot_editor_instance.update_adapter(adapter, prefix)
            cls.snapshot_editor_instance.raise_()
            cls.snapshot_editor_instance.activateWindow()
        else:
            cls.snapshot_editor_instance = SnapshotEditorDialog(
                adapter,
                prefix=prefix,
                re_snapshot_callback=self._do_re_snapshot,
                parent=self,
            )
            cls.snapshot_editor_instance.show()

    def _do_re_snapshot(self):
        """Re-capture the active rig's Character Snapshot (used by the rule
        editor). Returns a fresh adapter, or None."""
        cs_mod = _try_import_character_snapshot()
        if cs_mod is None:
            self._show_character_snapshot_missing()
            return None

        prefix, ctrl_list = self._resolve_snapshot_targets()
        if not ctrl_list:
            om.MGlobal.displayError("[Mirror Controls] No controls found for re-snapshot.")
            return None

        existing = cs_mod.load_snapshot(prefix)
        left_token  = existing.left_token  if existing else self.get_left_name()
        right_token = existing.right_token if existing else self.get_right_name()
        mirror_axis = existing.mirror_axis if existing else self.get_mirror_axis()

        snap = cs_mod.CharacterSnapshot.build(
            ctrl_list, prefix=prefix,
            rig_name=existing.rig_name if existing else "",
            description=existing.description if existing else "",
            left_token=left_token, right_token=right_token,
            mirror_axis=mirror_axis,
        )
        if existing is not None:
            snap.manual_pairs      = dict(existing.manual_pairs)
            snap.excluded_controls = list(existing.excluded_controls)
            snap.metadata          = dict(existing.metadata or {})
            snap.created           = existing.created
        snap.save_to_scene()
        self._refresh_prefix_combobox()
        self._refresh_snapshot_status()

        _, unpaired = snap.analyse_pairing()
        if unpaired:
            om.MGlobal.displayWarning(
                "[Mirror Controls] Re-snapshot: {} control{} still unpaired: {}".format(
                    len(unpaired),
                    "s" if len(unpaired) != 1 else "",
                    ", ".join(unpaired[:20]),
                )
            )
        return _CharacterSnapshotAdapter(snap)

    def _refresh_snapshot_status(self):
        prefix = self._active_prefix or self.get_active_prefix()
        cs_snap = _load_character_snapshot_for(prefix) if prefix else None
        if cs_snap is None:
            self.snapshot_status_label.setText(
                "<span style='color:#888888;'>⚠  No Character Snapshot "
                "— using axis heuristic</span>"
            )
            return

        n_ctrls = cs_snap.control_count() if hasattr(cs_snap, "control_count") \
                  else len(cs_snap.controls)
        n_pairs = cs_snap.pair_count() if hasattr(cs_snap, "pair_count") else 0
        n_flips = len((cs_snap.metadata or {}).get(_CS_META_FLIP_SIGNS, []))
        pfx_label = prefix if prefix and prefix != DEFAULT_PREFIX else "(scene)"
        flip_part = "  ·  {} sign-flip{}".format(
            n_flips, "s" if n_flips != 1 else ""
        ) if n_flips else ""
        self.snapshot_status_label.setText(
            "<span style='color:#80c080;'>✔  <b>{}</b> — "
            "{} controls, {} pairs  (axis: {}){}</span>".format(
                pfx_label, n_ctrls, n_pairs, cs_snap.mirror_axis, flip_part
            )
        )

    # ------------------------------------------------------------------
    # Getters
    # ------------------------------------------------------------------

    def get_mirror_axis(self):
        return self.mirror_axis_cb.currentText()

    def get_operation(self):
        return self.operation_cb.currentText()

    def get_left_name(self):
        txt = self.left_ctrl_name_le.text().strip()
        return txt if txt else "lf"

    def get_right_name(self):
        txt = self.right_ctrl_name_le.text().strip()
        return txt if txt else "rt"

    def get_min_time(self):
        return cmds.playbackOptions(minTime=True, query=True)

    def get_max_time(self):
        return cmds.playbackOptions(maxTime=True, query=True)

    def get_flip_frame(self):
        return self.mirror_frame_dsb.value()

    # ------------------------------------------------------------------
    # Operation change
    # ------------------------------------------------------------------

    def on_operation_change(self):
        text = self.get_operation()
        self.mirror_frame_dsb.setVisible(text == OperationType.flip_to_frame)
        is_not_selected = text == OperationType.not_selected
        self.left_to_right_rb.setVisible(is_not_selected)
        self.right_to_left_rb.setVisible(is_not_selected)
        self.flip_rb.setVisible(is_not_selected)

    # ------------------------------------------------------------------
    # Control discovery
    # ------------------------------------------------------------------

    def _get_all_nurbs_controls(self):
        """
        Return full DAG paths of all NURBS-curve parent transforms with keyable attrs.

        Full paths are mandatory — rigs with deeply nested finger chains can have
        controls with the same short/namespace-qualified name at multiple DAG levels.
        Using short names causes Maya to raise 'More than one object matches name'.
        """
        all_shapes = cmds.ls(type="nurbsCurve") or []
        seen   = set()
        result = []
        for shape in all_shapes:
            parents = cmds.listRelatives(shape, parent=True, fullPath=True) or []
            for full_path in parents:
                if full_path not in seen:
                    try:
                        if cmds.listAttr(full_path, keyable=True):
                            result.append(full_path)
                            seen.add(full_path)
                    except Exception:
                        pass
        return result

    def _control_side(self, ctrl, left_token, right_token, snapshot=None):
        """Return 'left' / 'right' / 'middle' for *ctrl*.

        The Character Snapshot's stored classification wins; controls the
        snapshot doesn't know fall back to boundary-aware token matching.
        """
        if snapshot is not None:
            side = snapshot.get_side(ctrl)
            if side in ("left", "right", "middle"):
                return side
        has_l = _has_side_token(ctrl, left_token)
        has_r = _has_side_token(ctrl, right_token)
        if has_l and not has_r:
            return "left"
        if has_r and not has_l:
            return "right"
        return "middle"

    # ------------------------------------------------------------------
    # Axis vector helpers  (heuristic fallback when no snapshot rule)
    # ------------------------------------------------------------------

    def get_vectors_dominating_axis(self, vector):
        denominator = sum(abs(val) for val in vector)
        if denominator == 0:
            return "X"
        pct    = [abs(val) / denominator for val in vector]
        index  = pct.index(max(pct))
        labels = ["X", "Y", "Z"]
        return ("-" + labels[index]) if vector[index] < 0 else labels[index]

    def get_mirror_axis_dominent_vector(self, mirror_axis, x_dom, y_dom, z_dom):
        if mirror_axis == x_dom or ("-" + mirror_axis) == x_dom:
            return "X"
        elif mirror_axis == y_dom or ("-" + mirror_axis) == y_dom:
            return "Y"
        elif mirror_axis == z_dom or ("-" + mirror_axis) == z_dom:
            return "Z"
        return mirror_axis

    def get_vector_data(self, ctrl_list):
        vector_dict = {}
        cur_pos     = {}
        for ctrl in ctrl_list:
            cur_pos[ctrl] = self.get_attribute_data([ctrl])
            self.rotate_ctrl_to_zero(ctrl)
        for ctrl in ctrl_list:
            try:
                wm = cmds.xform(ctrl, matrix=True, worldSpace=True, query=True)
                wm = [round(v, 3) for v in wm]
                vector_dict[ctrl] = {
                    "x_axis": wm[0:3],
                    "y_axis": wm[4:7],
                    "z_axis": wm[8:11],
                }
            except Exception:
                vector_dict[ctrl] = {
                    "x_axis": [1, 0, 0],
                    "y_axis": [0, 1, 0],
                    "z_axis": [0, 0, 1],
                }
        for ctrl in ctrl_list:
            self.rotate_ctrl_to_data(ctrl, cur_pos[ctrl])
        return vector_dict

    def is_mirror_same_as_dominants(self, mirror_axis, dominent, opp_dominent):
        return ((mirror_axis == dominent and mirror_axis == opp_dominent) or
                ("-" + mirror_axis == dominent and "-" + mirror_axis == opp_dominent))

    def is_dominants_same_and_not_mirror(self, mirror_axis, dominent, opp_dominent):
        pos_mirror = dominent == opp_dominent and dominent != mirror_axis
        neg_mirror = dominent == opp_dominent and dominent != ("-" + mirror_axis)
        return pos_mirror and neg_mirror

    # ------------------------------------------------------------------
    # Attribute helpers
    # ------------------------------------------------------------------

    def get_attribute_data(self, ctrl_list):
        data = {}
        for ctrl in ctrl_list:
            data[ctrl] = {}
            try:
                attributes = cmds.listAttr(ctrl, keyable=True, unlocked=True)
            except Exception:
                attributes = None
            if attributes:
                for attr in attributes:
                    try:
                        value = cmds.getAttr("{}.{}".format(ctrl, attr))
                    except Exception:
                        continue
                    if isinstance(value, (int, float)):
                        data[ctrl][attr] = value
        return data

    def set_attr(self, attr, value):
        try:
            cmds.setAttr(attr, value)
        except Exception:
            pass

    def set_time(self, time):
        cmds.currentTime(time)

    def rotate_ctrl_to_zero(self, ctrl):
        auto_key = cmds.autoKeyframe(state=True, query=True)
        if auto_key:
            cmds.autoKeyframe(state=False)
        for ax in ["X", "Y", "Z"]:
            try:
                if cmds.listAttr("{}.rotate{}".format(ctrl, ax),
                                 keyable=True, unlocked=True):
                    self.set_attr("{}.rotate{}".format(ctrl, ax), 0)
            except Exception:
                pass
        if auto_key:
            cmds.autoKeyframe(state=True)

    def rotate_ctrl_to_data(self, ctrl, data):
        auto_key = cmds.autoKeyframe(state=True, query=True)
        if auto_key:
            cmds.autoKeyframe(state=False)
        for ax in ["X", "Y", "Z"]:
            key = "rotate{}".format(ax)
            if ctrl in data and key in data[ctrl]:
                self.set_attr("{}.{}".format(ctrl, key), data[ctrl][key])
        if auto_key:
            cmds.autoKeyframe(state=True)

    def get_partner(self, ctrl, left_token, right_token, snapshot=None):
        """
        Return the scene-validated mirror partner for *ctrl*, or None.

        Priority order:
          1. Character Snapshot — manual pair → recorded partner →
             multi-convention token swap (centralised in the Character
             Snapshot module, every candidate validated against the scene).
          2. Local token-swap fallback when no snapshot is available
             (heuristic mode), also scene-validated.
        """
        if snapshot is not None:
            if snapshot.is_excluded(ctrl):
                return None
            partner = snapshot.find_partner(ctrl)
            if partner:
                return partner

        leaf = ctrl.split("|")[-1]
        if ":" in leaf:
            ns, base = leaf.rsplit(":", 1)
            ns_prefix = ns + ":"
        else:
            ns_prefix = ""
            base = leaf
        for cand in _mirror_name_candidates(base, left_token, right_token):
            if cmds.objExists(ns_prefix + cand):
                return ns_prefix + cand
        return None

    # ------------------------------------------------------------------
    # mirror_pair  — snapshot-aware
    # ------------------------------------------------------------------

    def mirror_pair(self, ctrl, partner, data, vector_data, mirror_axis, snapshot=None):
        """
        Copy / negate attributes from ctrl to partner.

        If a snapshot is supplied, each attribute's effective rule (user
        override → auto-detected from the default pose) is used directly
        (copy / negate / ignore). Attributes with no stored rule — or no
        snapshot at all — run the original axis-vector heuristic.
        """
        if ctrl not in vector_data or partner not in vector_data:
            return
        if ctrl not in data:
            return

        x_axis     = vector_data[ctrl]["x_axis"]
        y_axis     = vector_data[ctrl]["y_axis"]
        z_axis     = vector_data[ctrl]["z_axis"]
        opp_x_axis = vector_data[partner]["x_axis"]
        opp_y_axis = vector_data[partner]["y_axis"]
        opp_z_axis = vector_data[partner]["z_axis"]

        x_dom     = self.get_vectors_dominating_axis(x_axis)
        y_dom     = self.get_vectors_dominating_axis(y_axis)
        z_dom     = self.get_vectors_dominating_axis(z_axis)
        opp_x_dom = self.get_vectors_dominating_axis(opp_x_axis)
        opp_y_dom = self.get_vectors_dominating_axis(opp_y_axis)
        opp_z_dom = self.get_vectors_dominating_axis(opp_z_axis)
        mirror_attr = self.get_mirror_axis_dominent_vector(
            mirror_axis, x_dom, y_dom, z_dom
        )

        # Per-control sign-flip override (stored in the Character Snapshot).
        # When the user clicks "± Flip Sign" the leaf is added to the
        # snapshot's flip-sign list. We invert mirrored numeric channels here
        # so every downstream code path (snapshot rule or heuristic fallback)
        # automatically writes the opposite sign to the partner control.
        # Scale, bool and enum channels are left alone.
        flip_this_ctrl = bool(
            snapshot is not None
            and getattr(snapshot, "is_flip_sign", None)
            and snapshot.is_flip_sign(ctrl)
        )

        for attr, value in data[ctrl].items():
            target = "{}.{}".format(partner, attr)

            if flip_this_ctrl:
                attr_lc = attr.lower()
                src_attr = "{}.{}".format(ctrl, attr)
                try:
                    attr_type = cmds.getAttr(src_attr, type=True)
                except Exception:
                    attr_type = None
                is_numeric = isinstance(value, (int, float))
                is_bool_or_enum = attr_type in ("bool", "enum")
                if (
                    is_numeric
                    and not is_bool_or_enum
                    and "visibility" not in attr_lc
                    and not attr_lc.startswith("scale")
                ):
                    value = -value

            # --- Snapshot rule path ---
            if snapshot is not None:
                rule = snapshot.get_rule(ctrl, attr)
                if rule is not None:
                    if rule == RULE_IGNORE:
                        continue
                    elif rule == RULE_NEGATE:
                        self.set_attr(target, -value)
                    else:   # RULE_COPY
                        self.set_attr(target, value)
                    continue
                # Attribute not in snapshot — fall through to heuristic

            # --- Heuristic fallback (original v2.0.0 logic) ---
            attr_lower = attr.lower()

            # wrist IK special cases
            if ("rotatex" in attr_lower or "rotatey" in attr_lower) and "handik" in partner.lower():
                self.set_attr(target, value)
                continue
            if "translate" in attr_lower and "handik" in partner.lower():
                if self.preserve_translation_cb.isChecked():
                    self.set_attr(target, value)
                else:
                    if mirror_axis.upper() in attr:
                        self.set_attr(target, -value)
                    else:
                        self.set_attr(target, value)
                continue

            # Generic preserve options
            if "rotate" in attr_lower and self.preserve_rotation_cb.isChecked():
                self.set_attr(target, value)
                continue
            if "translate" in attr_lower and self.preserve_translation_cb.isChecked():
                self.set_attr(target, value)
                continue

            # Scale
            if "scale" in attr_lower:
                self.set_attr(target, value)
                continue

            # Same orientation
            if (x_dom == opp_x_dom and y_dom == opp_y_dom and z_dom == opp_z_dom):
                if "rotate{}".format(mirror_attr) in attr:
                    self.set_attr(target, value)
                elif "rotate" in attr_lower:
                    self.set_attr(target, -value)
                elif "translate{}".format(mirror_attr) in attr:
                    self.set_attr(target, -value)
                else:
                    self.set_attr(target, value)

            elif "translate" in attr_lower:
                if self.is_mirror_same_as_dominants(mirror_axis, x_dom, opp_x_dom):
                    self.set_attr(target, -value)
                elif self.is_mirror_same_as_dominants(mirror_axis, y_dom, opp_y_dom):
                    self.set_attr(target, -value)
                elif self.is_mirror_same_as_dominants(mirror_axis, z_dom, opp_z_dom):
                    self.set_attr(target, -value)
                elif x_dom == opp_x_dom:
                    self.set_attr(target, value if (mirror_attr in attr or "X" in attr) else -value)
                elif y_dom == opp_y_dom:
                    self.set_attr(target, value if (mirror_attr in attr or "Y" in attr) else -value)
                elif z_dom == opp_z_dom:
                    self.set_attr(target, value if (mirror_attr in attr or "Z" in attr) else -value)
                else:
                    self.set_attr(target, -value)

            elif "rotate" in attr_lower:
                if self.is_dominants_same_and_not_mirror(mirror_axis, x_dom, opp_x_dom):
                    self.set_attr(target, -value if (mirror_attr in attr or "X" in attr) else value)
                elif self.is_dominants_same_and_not_mirror(mirror_axis, y_dom, opp_y_dom):
                    self.set_attr(target, -value if (mirror_attr in attr or "Y" in attr) else value)
                elif self.is_dominants_same_and_not_mirror(mirror_axis, z_dom, opp_z_dom):
                    self.set_attr(target, -value if (mirror_attr in attr or "Z" in attr) else value)
                else:
                    self.set_attr(target, value)

            else:
                # Custom / unknown attribute — copy as-is in heuristic mode too
                self.set_attr(target, value)

    def _mirror_middle_attrs(self, ctrl, attrs, mirror_axis):
        """Flip a centre control's pose across the mirror axis in place."""
        for attr, value in attrs.items():
            if "translate" in attr:
                if mirror_axis.upper() in attr:
                    self.set_attr("{}.{}".format(ctrl, attr), -value)
                else:
                    self.set_attr("{}.{}".format(ctrl, attr), value)
            elif "rotate" in attr:
                self.set_attr("{}.{}".format(ctrl, attr), -value)
            else:
                self.set_attr("{}.{}".format(ctrl, attr), value)

    # ------------------------------------------------------------------
    # mirror_control  — main entry point
    # ------------------------------------------------------------------

    def mirror_control(self):
        """Run the selected mirror operation.

        Works in three modes:
          * Selection mode — operate on the selected controls.
          * Scene mode (no selection) — operate on every control of the
            active rig.
          * Not Selected — operate on every rig control EXCEPT the selected
            ones, in the direction chosen by the radio buttons.

        All pairing questions are answered by the Character Snapshot; when
        none exists the user is prompted to create one (and may explicitly
        continue with the axis-vector heuristic).
        """
        left_token  = self.get_left_name()
        right_token = self.get_right_name()
        mirror_axis = self.get_mirror_axis()
        op          = self.get_operation()

        sel = cmds.ls(selection=True, long=True) or []
        if sel:
            prefix = self._resolve_prefix_for_controls(sel)
        else:
            prefix = self._active_prefix or self.get_active_prefix()

        # Resolve snapshot BEFORE opening an undo chunk so the reminder
        # popup (if shown) doesn't leave an empty undo entry on cancel.
        snapshot = self._load_snapshot_for_mirroring(prefix)
        if snapshot is None:
            if not self._prompt_create_character_snapshot(prefix):
                return
        else:
            left_token  = snapshot.left_token or left_token
            right_token = snapshot.right_token or right_token

        # ---- Build the working pool + effective operation ----
        if op == OperationType.not_selected:
            if not sel:
                QtWidgets.QMessageBox.warning(
                    self, "Nothing Selected",
                    "The 'Not Selected' operation needs a selection to exclude.\n"
                    "Select the controls you want to leave untouched, then try again."
                )
                return
            pool_source = (self._get_controls_for_prefix(prefix)
                           if prefix else self._get_all_nurbs_controls())
            sel_set    = set(sel)
            sel_leaves = {c.split("|")[-1] for c in sel}
            ctrl_pool = [c for c in pool_source
                         if c not in sel_set and c.split("|")[-1] not in sel_leaves]
            if self.right_to_left_rb.isChecked():
                eff_op = OperationType.right_to_left
            elif self.flip_rb.isChecked():
                eff_op = OperationType.flip
            else:
                eff_op = OperationType.left_to_right
        elif sel:
            ctrl_pool = list(sel)
            eff_op    = op
        else:
            if op == OperationType.selected:
                QtWidgets.QMessageBox.warning(
                    self, "Nothing Selected",
                    "The 'Selected' operation needs at least one selected control.\n"
                    "Select the controls you want to mirror, then try again."
                )
                return
            ctrl_pool = (self._get_controls_for_prefix(prefix)
                         if prefix else self._get_all_nurbs_controls())
            eff_op = op

        if not ctrl_pool:
            self.no_nurbs_in_scene()
            return

        is_flip = eff_op in (OperationType.flip, OperationType.flip_to_frame)
        in_selection_mode = bool(sel) and op != OperationType.not_selected

        # Leaf → full DAG path lookup so short partner names resolve to the
        # unambiguous paths used as data keys (rigs with nested finger chains
        # can have identical leaf names at several DAG depths).
        _all_ctrls   = self._get_all_nurbs_controls()
        _leaf_to_dag = {c.split("|")[-1]: c for c in _all_ctrls}

        def _to_dag(name):
            return _leaf_to_dag.get(name.split("|")[-1], _resolve_long(name))

        # ---- Plan the work: (source, target) actions + middle flips ----
        actions   = []
        middles   = []
        unmatched = []
        excluded  = 0
        processed = set()
        pool_set  = set(ctrl_pool)

        for ctrl in ctrl_pool:
            if ctrl in processed:
                continue
            if snapshot is not None and snapshot.is_excluded(ctrl):
                excluded += 1
                continue

            side = self._control_side(ctrl, left_token, right_token, snapshot)

            if eff_op == OperationType.left_to_right and side != "left":
                continue
            if eff_op == OperationType.right_to_left and side != "right":
                continue
            if eff_op == OperationType.mirror_middle:
                if side == "middle":
                    middles.append(ctrl)
                    processed.add(ctrl)
                continue
            if is_flip and side == "middle" and not in_selection_mode:
                # Scene-wide flips leave middles untouched (no partner).
                continue

            partner = self.get_partner(ctrl, left_token, right_token, snapshot=snapshot)
            if not partner or not cmds.objExists(partner):
                # Only sided controls (or explicit selections) are reported —
                # centre controls have no partner by design.
                if side != "middle" or in_selection_mode:
                    unmatched.append(ctrl.split("|")[-1])
                processed.add(ctrl)
                continue

            partner = _to_dag(partner)
            processed.add(ctrl)
            if partner in pool_set:
                processed.add(partner)

            actions.append((ctrl, partner))
            if is_flip:
                actions.append((partner, ctrl))

        if not actions and not middles:
            self._report_mirror_result(eff_op, 0, unmatched, excluded)
            return

        cmds.undoInfo(openChunk=True)
        try:
            if eff_op == OperationType.flip_to_frame:
                self.set_time(self.get_flip_frame())

            # Capture EVERYTHING before any write so Flip is a true swap and
            # chained pairs can't read half-mirrored values.
            nodes = []
            for src, dst in actions:
                for n in (src, dst):
                    if n not in nodes:
                        nodes.append(n)
            vector_data = self.get_vector_data(nodes) if nodes else {}
            data        = self.get_attribute_data(nodes) if nodes else {}
            middle_data = self.get_attribute_data(middles) if middles else {}

            for src, dst in actions:
                self.mirror_pair(src, dst, data, vector_data, mirror_axis, snapshot)
            for ctrl in middles:
                self._mirror_middle_attrs(ctrl, middle_data.get(ctrl, {}), mirror_axis)
        finally:
            cmds.undoInfo(closeChunk=True)

        n_mirrored = (len(actions) // 2 if is_flip else len(actions)) + len(middles)
        self._report_mirror_result(eff_op, n_mirrored, unmatched, excluded)

    def _report_mirror_result(self, op, n_mirrored, unmatched, excluded):
        """Summarise the mirror run — the tool must never finish silently."""
        parts = ["[Mirror Controls] {}: {} control{} mirrored".format(
            op, n_mirrored, "" if n_mirrored == 1 else "s")]
        if excluded:
            parts.append("{} excluded".format(excluded))
        if unmatched:
            parts.append("{} unmatched".format(len(unmatched)))
        summary = ", ".join(parts) + "."

        if unmatched:
            om.MGlobal.displayWarning(
                summary + "  No mirror partner found for: {}{}  "
                "Assign partners in the Character Snapshot Manual Pair Editor.".format(
                    ", ".join(unmatched[:10]),
                    " …" if len(unmatched) > 10 else "",
                )
            )
        elif n_mirrored == 0:
            om.MGlobal.displayWarning(
                summary + "  Nothing matched the current operation — check the "
                "operation direction, the selection and the rig's Character Snapshot."
            )
        else:
            om.MGlobal.displayInfo(summary)

    # ------------------------------------------------------------------
    # Snapshot resolution  (Character Snapshot only)
    # ------------------------------------------------------------------

    def _load_snapshot_for_mirroring(self, prefix, announce=True):
        """Return a Character Snapshot adapter for *prefix*, or None.

        Mirror Controls relies exclusively on the Animation Tool Kit
        Character Snapshot — capture or import one via the Character
        Snapshot tool to give Mirror Controls authoritative pair / exclusion
        / channel-rule data. Returns None when no Character Snapshot exists
        for *prefix*; the caller is expected to prompt the user.

        A stored snapshot whose controls have mostly vanished from the scene
        (renamed namespace, different rig version) triggers a staleness
        warning so animators know their match data needs attention.
        """
        if not prefix:
            return None
        cs_snap = _load_character_snapshot_for(prefix)
        if cs_snap is None:
            return None
        adapter = _CharacterSnapshotAdapter(cs_snap)
        if announce:
            om.MGlobal.displayInfo(
                "[Mirror Controls] Using Character Snapshot for '{}'.".format(prefix)
            )
            report = adapter.validate_against_scene()
            if report and report.get("stale"):
                om.MGlobal.displayWarning(
                    "[Mirror Controls] {}".format(report.get("message", ""))
                )
        return adapter

    def _prompt_create_character_snapshot(self, prefix):
        """Show the "no Character Snapshot" reminder. Return True if mirroring
        should continue (with the axis-vector heuristic), False if the user
        cancelled or asked to open the Character Snapshot tool instead.
        """
        label = prefix if prefix and prefix != DEFAULT_PREFIX else "this rig"
        cs_mod = _try_import_character_snapshot()
        cs_available = cs_mod is not None

        box = QtWidgets.QMessageBox(self)
        box.setWindowTitle("Mirror Controls — Character Snapshot Required")
        box.setIcon(QtWidgets.QMessageBox.Warning)
        box.setTextFormat(QtCore.Qt.RichText)
        message = (
            "<p><b>Character Snapshot data was not found for {}.</b></p>"
            "<p>Please create a Character Snapshot in the character's "
            "default pose before using mirror matching. This allows ATK to "
            "identify matching controls more reliably.</p>"
            "<p>You can continue without a snapshot — the tool will fall "
            "back to the axis-vector naming heuristic, which may misfire on "
            "rigs with non-standard naming or geometry.</p>"
        ).format(label)
        box.setText(message)

        open_btn = box.addButton("Open Character Snapshot…",
                                 QtWidgets.QMessageBox.AcceptRole)
        if not cs_available:
            open_btn.setEnabled(False)
            open_btn.setToolTip("character_snapshot_v1_0_0 module not found on sys.path.")
        continue_btn = box.addButton("Continue Without Snapshot",
                                     QtWidgets.QMessageBox.DestructiveRole)
        box.addButton("Cancel", QtWidgets.QMessageBox.RejectRole)
        box.setDefaultButton(open_btn if cs_available else continue_btn)
        box.exec()

        clicked = box.clickedButton()
        if clicked is open_btn and cs_available:
            try:
                cs_mod.show_dialog()
            except Exception as exc:
                om.MGlobal.displayError(
                    "[Mirror Controls] Could not launch Character Snapshot: {}".format(exc)
                )
            return False
        if clicked is continue_btn:
            return True
        # cancel or dialog dismissed
        return False

    def no_nurbs_in_scene(self):
        om.MGlobal.displayError(
            "[Mirror Controls] Couldn't find any NURBS controls to mirror."
        )
        QtWidgets.QMessageBox.warning(
            self, "No Controls Found",
            "No NURBS controls were found to mirror.\n"
            "Reference the rig into the scene (or check the Character "
            "selection) and try again."
        )

    # ------------------------------------------------------------------
    # Flip Sign Rules
    # ------------------------------------------------------------------

    def flip_sign_rules(self):
        """
        Toggle the per-control sign-flip override for the currently selected
        controls. When a control is flipped, Mirror Controls inverts mirrored
        numeric channel values before mirroring — useful when a rig setup
        causes a particular control to mirror with the wrong sign.

        The action also applies an immediate live fix to the selected control:
        translate on the mirror axis is negated (for example, tx on X rigs).
        This gives instant feedback and a keyable corrected channel value.

        Overrides are stored in the Character Snapshot's metadata (under
        'mirror_controls_flip_signs'), so a Character Snapshot must exist for
        the selected rig.
        """
        sel = cmds.ls(selection=True, long=True)
        if not sel:
            QtWidgets.QMessageBox.warning(
                self, "Nothing Selected",
                "Please select one or more rig controls in the Maya viewport\n"
                "whose mirror sign you want to reverse, then try again."
            )
            return

        prefix   = self._resolve_prefix_for_controls(sel)
        snapshot = self._load_snapshot_for_mirroring(prefix, announce=False)
        if snapshot is None:
            label = prefix if prefix and prefix != DEFAULT_PREFIX else "this rig"
            cs_mod = _try_import_character_snapshot()

            box = QtWidgets.QMessageBox(self)
            box.setWindowTitle("Mirror Controls — Character Snapshot Required")
            box.setIcon(QtWidgets.QMessageBox.Warning)
            box.setTextFormat(QtCore.Qt.RichText)
            box.setText(
                "<p><b>Character Snapshot data was not found for {}.</b></p>"
                "<p>The ± Flip Sign override is stored on the Character "
                "Snapshot for the rig, so please create a Character Snapshot "
                "in the character's default pose first.</p>".format(label)
            )
            open_btn   = box.addButton("Open Character Snapshot…",
                                       QtWidgets.QMessageBox.AcceptRole)
            open_btn.setEnabled(cs_mod is not None)
            cancel_btn = box.addButton("Cancel", QtWidgets.QMessageBox.RejectRole)
            box.setDefaultButton(open_btn if cs_mod is not None else cancel_btn)
            box.exec()
            if box.clickedButton() is open_btn and cs_mod is not None:
                try:
                    cs_mod.show_dialog()
                except Exception as exc:
                    om.MGlobal.displayError(
                        "[Mirror Controls] Could not launch Character Snapshot: {}".format(exc)
                    )
            return

        flipped_on  = []
        flipped_off = []
        cmds.undoInfo(openChunk=True)
        try:
            for ctrl in sel:
                leaf = ctrl.split("|")[-1]
                new_state = snapshot.toggle_flip_sign(ctrl)
                self._apply_live_flip_fix(ctrl, snapshot)
                label = leaf.split(":")[-1] if ":" in leaf else leaf
                (flipped_on if new_state else flipped_off).append(label)
        finally:
            cmds.undoInfo(closeChunk=True)

        snapshot.save()
        self._refresh_snapshot_status()

        total = len(flipped_on) + len(flipped_off)
        om.MGlobal.displayInfo(
            "[Mirror Controls] Toggled flip-sign on {} control{} ({} on, {} off).".format(
                total, "s" if total != 1 else "", len(flipped_on), len(flipped_off)
            )
        )

        sections = []
        if flipped_on:
            sections.append("<b>Sign flipped on:</b><br>" +
                            "<br>".join("  •  {}".format(n) for n in flipped_on[:20]) +
                            ("<br>  … and {} more".format(len(flipped_on) - 20)
                             if len(flipped_on) > 20 else ""))
        if flipped_off:
            sections.append("<b>Sign restored on:</b><br>" +
                            "<br>".join("  •  {}".format(n) for n in flipped_off[:20]) +
                            ("<br>  … and {} more".format(len(flipped_off) - 20)
                             if len(flipped_off) > 20 else ""))

        info = QtWidgets.QMessageBox(self)
        info.setWindowTitle("Sign Flip Toggled")
        info.setIcon(QtWidgets.QMessageBox.Information)
        info.setTextFormat(QtCore.Qt.RichText)
        info.setText("<br><br>".join(sections) if sections else
                     "No controls were toggled.")
        info.setStandardButtons(QtWidgets.QMessageBox.Ok)
        info.exec()

    def _apply_live_flip_fix(self, ctrl, snapshot):
        """
        Immediately negate ctrl's translate value on the mirror axis.
        """
        axis = (getattr(snapshot, "mirror_axis", None) or self.get_mirror_axis() or "X").upper()
        if axis not in ("X", "Y", "Z"):
            axis = "X"
        attr = "{}.translate{}".format(ctrl, axis)
        if not cmds.objExists(attr):
            return
        try:
            if cmds.getAttr(attr, lock=True):
                return
        except Exception:
            return
        try:
            val = cmds.getAttr(attr)
            if isinstance(val, (list, tuple)):
                val = val[0]
            if isinstance(val, (int, float)):
                self.set_attr(attr, -val)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Help
    # ------------------------------------------------------------------

    def show_help(self):
        help_text = (
            "<h3>Mirror Controls — How To Use</h3>"
            "<hr>"

            "<h4>① Quick Start — Mirror a Pose</h4>"
            "<ol>"
            "<li>Select the rig controls you want to mirror (or leave the selection "
            "empty to process all controls of the active rig).</li>"
            "<li>Choose the <b>Operation</b> (e.g. Left to Right, Flip, Selected).</li>"
            "<li>Click the <b>Mirror</b> button.</li>"
            "</ol>"

            "<h4>② Character Snapshot (Required for Reliable Matching)</h4>"
            "<p>Mirror Controls reads all of its matching data from the Animation "
            "Tool Kit <b>Character Snapshot</b>: control lists, left/right "
            "classification, mirror partners (automatic and manual), exclusions "
            "and per-channel flip rules.</p>"
            "<ol>"
            "<li>Pose the rig at its <b>default pose</b> (all controls zeroed).</li>"
            "<li>Select any control on the rig and use Tools &gt; <b>Take Snapshot</b> (or the Character Snapshot tool via <b>Manage</b>).</li>"
            "<li>The snapshot is stored in the Maya scene and persists across saves.</li>"
            "</ol>"

            "<h4>③ Automatic Matching</h4>"
            "<p>Partners are found from the snapshot's manual pairs first, then the "
            "partner recorded at snapshot time, then by swapping naming tokens.  "
            "Common conventions are tried automatically: <tt>lf/rt</tt>, "
            "<tt>lt/rt</tt>, <tt>L/R</tt> (any position), <tt>left/right</tt> "
            "(any casing, including camelCase), <tt>lf/rf</tt> and more.</p>"

            "<h4>④ Manual Pair Editor</h4>"
            "<p>If automatic matching cannot find a partner, click "
            "<b>Manual Pairs</b> — this opens the Character Snapshot Manual "
            "Pair Editor.  Pairs you save there are validated against the scene "
            "and shared by every ATK tool.</p>"

            "<h4>⑤ Channel Flip Rules</h4>"
            "<p>Each channel's copy/negate behaviour is auto-detected from the "
            "default-pose snapshot (e.g. if the left IK hand rests at "
            "<tt>tx&nbsp;=&nbsp;+5</tt> and the right at <tt>tx&nbsp;=&nbsp;−5</tt>, "
            "translateX is negated when mirrored).  Click <b>Edit Rules</b> to "
            "review and override any channel (copy / negate / ignore).  "
            "<b>Flip Sign</b> inverts every mirrored channel of the selected "
            "controls as a whole-control override.</p>"

            "<h4>⑥ Per-Character Snapshots</h4>"
            "<p>Snapshots are stored <b>per character rig</b>, keyed by namespace "
            "prefix.  Use the <b>Character</b> dropdown to switch rigs and "
            "<b>Manage</b> to open the Character Snapshot tool (export/import "
            "JSON, rename prefixes, delete).</p>"

            "<h4>⑦ Naming Convention</h4>"
            "<p>The Left/Right token fields are used when taking a snapshot and as "
            "a fallback when mirroring without one.  Tokens match as delimited "
            "segments only — <tt>rt</tt> never matches inside <tt>shirt</tt>.</p>"

            "<h4>⑧ Preserve Translation / Rotation</h4>"
            "<p>These checkboxes only apply to channels with <b>no snapshot "
            "rule</b>.  When checked, the corresponding channels are copied "
            "exactly rather than negated by the axis heuristic.</p>"
        )
        box = QtWidgets.QMessageBox(self)
        box.setWindowTitle("How To Use — Mirror Controls")
        box.setTextFormat(QtCore.Qt.RichText)
        box.setText(help_text)
        box.setStandardButtons(QtWidgets.QMessageBox.Ok)
        box.exec()

    # ------------------------------------------------------------------
    # About
    # ------------------------------------------------------------------

    def show_about(self):
        about_text = (
            "<h3>Mirror Controls</h3>"
            "<p style='color:#8ab4f8;'>Version 2.3.3</p>"
            "<p style='color:#888; font-size:10px;'>Formerly digetMirrorControl</p>"
            "<hr>"

            "<h4>Contributors</h4>"
            "<table cellpadding='2'>"
            "<tr><td style='color:#90c890;'>Original Author:</td>"
            "<td>Mikkel Diget Eriksen (2022)</td></tr>"
            "<tr><td style='color:#90c890;'>Updated by:</td>"
            "<td>David Shepstone</td></tr>"
            "</table>"

            "<h4>What's New in 2.3.3</h4>"
            "<ul>"
            "<li><b>UI cleanup</b> — removed the redundant Take Snapshot "
            "button (still in the Tools menu and the Character Snapshot "
            "tool), consolidated the snapshot buttons into one row, and "
            "replaced emoji icons that rendered as empty boxes in Maya's "
            "UI font.</li>"
            "</ul>"

            "<h4>What's New in 2.3.2</h4>"
            "<ul>"
            "<li><b>Character Snapshot is the single source of truth</b> — the "
            "duplicated legacy snapshot system was removed; snapshots, manual "
            "pairs, exclusions and channel rules are all read from and written "
            "to the Character Snapshot scene data (legacy data is migrated "
            "automatically).</li>"
            "<li><b>Multi-convention automatic matching</b> — lt/rt, L/R, "
            "left/right, lf/rf and more are tried automatically, with "
            "scene-validated results.</li>"
            "<li><b>Automatic channel-flip detection</b> from the rig's "
            "default pose, with per-channel manual overrides and the "
            "± Flip Sign whole-control override.</li>"
            "<li><b>Fixes</b> — Flip now truly swaps both sides in selection "
            "mode, Mirror Middle works on selections, 'Not Selected' is "
            "implemented, undo chunks are exception-safe, and every run "
            "reports a clear summary.</li>"
            "</ul>"

            "<p style='color:#888; font-size:10px;'>Python · PySide6 · Maya 2025+</p>"
        )
        box = QtWidgets.QMessageBox(self)
        box.setWindowTitle("About Mirror Controls")
        box.setTextFormat(QtCore.Qt.RichText)
        box.setText(about_text)
        box.setStandardButtons(QtWidgets.QMessageBox.Ok)
        box.exec()

    # ------------------------------------------------------------------
    # Window geometry persistence
    # ------------------------------------------------------------------

    def showEvent(self, e):
        super().showEvent(e)
        if self._saved_geometry:
            self.restoreGeometry(self._saved_geometry)
        self._refresh_prefix_combobox()
        self._refresh_snapshot_status()

    def closeEvent(self, e):
        super().closeEvent(e)
        self._saved_geometry = self.saveGeometry()


# ---------------------------------------------------------------------------
# Standalone test entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    try:
        mirror_control.close()       # type: ignore
        mirror_control.deleteLater() # type: ignore
    except Exception:
        pass
    mirror_control = MirrorControls()
    mirror_control.show()
