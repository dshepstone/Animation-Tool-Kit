#!/usr/bin/env python3
"""
digetMirrorControl.py - Python Script

Description:
    A tool for mirroring the controllers from one side to the other or to flip the pose.
    Now includes a Rig Snapshot system: take a snapshot of a rig's controls at rest pose
    so the tool can store accurate per-control mirror rules (copy / negate / ignore) for
    every keyable attribute, including custom channels.  Rules can be reviewed and edited
    in a dedicated Snapshot Editor window before being saved back to the scene.

    If no snapshot is present the tool falls back to the original axis-vector heuristic.

Requires:
    Nothing (PySide6 / Maya 2025+)

Install:
    1. Place this file in the Maya scripts folder
       (%USERPROFILE%/Documents/maya/scripts)

    2. In the Maya Script Editor, run:
         from digetMirrorControl import DigetMirrorControl
         DigetMirrorControl.show_dialog()

    3. Create a shelf button by selecting all code (Ctrl+A) and dragging it to the shelf.

Usage:
    1. Pose the rig in its rest / bind pose.
    2. Select all rig controls (or leave nothing selected to capture every NURBS control).
    3. File > Take Snapshot  —  the tool reads each control's world-space axis vectors and
       assigns a default mirror rule (copy / negate / ignore) to every keyable attribute.
    4. File > Edit Snapshot…  —  review or override any rule per attribute, then Save to Scene.
    5. Use the main mirror controls as normal.  The snapshot is used automatically.

Authors:
    Original: Mikkel Diget Eriksen (2022)
    Updated by: David Shepstone

Version:
    2.2.5 - Four critical mirror-failure fixes:
             1. Token-swap false positives: _find_partner() and get_partner() used
                naive str.find() which matched side tokens embedded inside words
                (e.g. "rt" in "upperteeth", "shirt", "earTip").  Replaced with a
                shared _swap_side_token() helper using regex word-boundary matching
                where boundaries are '_' or string start/end.  Added _has_side_token()
                companion to replace all naive `token in ctrl` classification checks
                throughout get_controllers() and mirror_control().
             2. Scene-mode DAG path mismatch: in scene mode (no selection),
                ctrl_list contains full DAG paths (|A|B|C) but get_partner()
                returns short namespace:name strings.  The check
                `partner not in vector_data` always failed because key formats
                differ.  Added a leaf→DAG lookup map (_leaf_to_dag) that resolves
                short partner names to their full DAG paths before the lookup.
             3. Selection-mode DAG ambiguity: cmds.ls(selection=True) returned
                short names, and get_partner() returns short names.  On rigs with
                deeply nested finger chains (ac_lf_index3 at multiple DAG depths),
                Maya raised "More than one object matches name" when these were
                passed to cmds.xform / cmds.listAttr / cmds.getAttr.  Fixed by
                using cmds.ls(selection=True, long=True) and resolving partner
                names through a leaf→DAG map built from _get_all_nurbs_controls().
             4. _collect_pending_edits() read partner values from the rd dict
                stored in QTableWidgetItem.data(UserRole) which PySide6 can
                return as a detached copy.  Now reads directly from the live
                QLineEdit cell widget, fixing "Save to Scene" reporting 0 pairs
                and "Exclude" wiping all unsaved manual pair entries.
    2.2.4 - Fixed bug in ManualPairEditorDialog where clicking Exclude wiped all
             unsaved manual pair edits from the table. Root cause: _toggle_excluded
             called save_to_scene() before the QLineEdit partner values had been
             committed to self._snapshot.manual_pairs, so the subsequent refresh
             reloaded the old snapshot and discarded everything typed since the
             last Save. Fix: extracted _collect_pending_edits() helper that commits
             all live table widget values into the snapshot first; _toggle_excluded
             now calls this before saving, as does _on_save().
    2.2.3 - ManualPairEditorDialog: clicking a row now selects the source control
             (and partner if already assigned) in the Maya viewport, making it easy
             to identify controls before pairing. Controlled by a 'Select in viewport
             on click' checkbox in the filter bar (on by default).
    2.2.2 - ManualPairEditorDialog now filters out centre/middle controls from the
             unpaired list — only controls whose leaf name contains the left or right
             token are shown (e.g. ac_lf_thumb, ac_rt_index).  Controls like
             ac_cn_chest, ac_cn_jaw, spine, etc. are silently skipped since they
             have no mirror partner by design.
    2.2.1 - Fixed _get_all_nurbs_controls() in DigetMirrorControl to return full DAG
             paths (same fix applied to the diagnostic tool) — resolves 'More than one
             object matches name' crash when opening ManualPairEditorDialog on rigs with
             deeply nested finger chains.
             Replaced post-snapshot dialog with a smart pairing report: if all controls
             pair successfully the user is offered the Snapshot Editor; if any are
             unpaired a warning lists them by name and defaults to opening Manual Pairs.
             Extracted _analyse_snapshot_pairing() helper so take_snapshot and
             _do_re_snapshot share the same logic.
    2.2.0 - Added ManualPairEditorDialog: per-rig manual pair overrides and control exclusions.
             Controls that auto-pair correctly never appear — only controls needing attention
             are shown. Users select in the Maya viewport and click ⊕ Pick to assign source
             or partner. Manual pairs and exclusions persist in the scene snapshot.
             get_partner() now checks manual_pairs before the token-swap heuristic.
             mirror_control() now skips excluded controls.
    2.1.1 - Fixed DAG path handling in get_partner() and RigSnapshot._find_partner():
             controls passed as full paths (parent|child) now correctly resolve their
             mirror partner by operating on the leaf node name only.
             Added Replace / Merge / Cancel guard when Take Snapshot would overwrite an
             existing snapshot — Merge updates only the re-sampled controls and preserves
             all other rules in the scene snapshot.
    2.1.0 - Added RigSnapshot system: per-control axis sampling, per-attribute mirror rules,
             and SnapshotEditorDialog for reviewing / overriding rules.
             Fixed duplicate create_menus() definition present in v2.0.0.
"""

import json
import re

from PySide6 import QtCore, QtGui, QtWidgets
from shiboken6 import wrapInstance

import maya.OpenMayaUI as omui
import maya.cmds as cmds
import maya.OpenMaya as om


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SNAPSHOT_NODE = "digetMirrorControlSettings"
SNAPSHOT_ATTR = "rigSnapshot"
SNAPSHOT_MULTI_ATTR = "rigSnapshots"
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
# Shared token-swap helper
# ---------------------------------------------------------------------------

def _swap_side_token(base_name, left_token, right_token):
    """
    Swap the left/right token in *base_name* (no namespace, no DAG prefix)
    and return the result, or None if no token was found.

    Word-boundary-aware: only matches when the token appears as a delimited
    segment.  In rig naming conventions the delimiter is '_', so the regex
    treats '_' and string start/end as word boundaries.

    Examples with tokens lf / rt:
        ac_lf_armFK     →  ac_rt_armFK       (matched)
        ac_rt_handIK    →  ac_lf_handIK      (matched)
        ac_cn_upperteeth →  None              ("rt" inside "upperteeth" — ignored)
        shirt_main       →  None              ("rt" inside "shirt" — ignored)
        ac_lf_earTip     →  ac_rt_earTip      (matches "lf" between delimiters)
    """
    lt = re.escape(left_token)
    rt = re.escape(right_token)

    # Build patterns that match the token as a delimited segment.
    # Boundaries: start of string, end of string, or '_'.
    def _boundary_pattern(tok):
        return r'(?:(?<=_)|(?<=\A))' + tok + r'(?=_|\Z)'

    # Try right → left first
    pat_rt = _boundary_pattern(rt)
    m = re.search(pat_rt, base_name, re.IGNORECASE)
    if m:
        # Preserve the casing convention of the original token position
        return base_name[:m.start()] + left_token + base_name[m.end():]

    # Then left → right
    pat_lt = _boundary_pattern(lt)
    m = re.search(pat_lt, base_name, re.IGNORECASE)
    if m:
        return base_name[:m.start()] + right_token + base_name[m.end():]

    return None


def _has_side_token(ctrl, token):
    """
    Return True if the control's leaf base-name contains *token* as a
    delimited segment (bounded by '_' or string edges), case-insensitive.

    This must be used instead of ``token.lower() in ctrl.lower()`` to avoid
    false positives like "rt" matching inside "upperteeth" or "shirt".
    """
    leaf = ctrl.split("|")[-1]
    base = leaf.split(":")[-1] if ":" in leaf else leaf
    pat = r'(?:(?<=_)|(?<=\A))' + re.escape(token) + r'(?=_|\Z)'
    return bool(re.search(pat, base, re.IGNORECASE))


def _resolve_long(name):
    """
    Resolve a possibly-ambiguous short or namespace-qualified name to a
    unique full DAG path using ``cmds.ls(name, long=True)``.

    Returns the full path if exactly one match is found, otherwise returns
    the original name unchanged (let Maya raise later if truly ambiguous).
    """
    try:
        matches = cmds.ls(name, long=True)
    except Exception:
        return name
    if matches and len(matches) == 1:
        return matches[0]
    return name


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
# RigSnapshot
# ---------------------------------------------------------------------------

class RigSnapshot(object):
    """
    Captures world-space axis data for every control in a rig at rest pose
    and assigns a per-attribute mirror rule (copy / negate / ignore).

    Stored as a JSON string on the digetMirrorControlSettings scene node so
    the data travels with the Maya file.

    Schema
    ------
    {
      "left_token":  "lf",
      "right_token": "rt",
      "mirror_axis": "X",
      "controls": {
        "lf_arm_ctrl": {
          "side":    "left",
          "partner": "rt_arm_ctrl",
          "dominant_axes": {"x": "X",  "y": "Y",  "z": "-Z"},
          "partner_dominant_axes": {"x": "-X", "y": "Y", "z": "Z"},
          "attributes": {
            "translateX": {"type": "translate", "rule": "negate", "user_override": false},
            "rotateY":    {"type": "rotate",    "rule": "negate", "user_override": false},
            "fingerCurl": {"type": "custom",    "rule": "copy",   "user_override": false}
          }
        }
      }
    }
    """

    def __init__(self):
        self.left_token        = "lf"
        self.right_token       = "rt"
        self.mirror_axis       = "X"
        self.controls          = {}   # ctrl_name -> control data dict
        self.manual_pairs      = {}   # {source_leaf: partner_leaf} — user-defined overrides
        self.excluded_controls = []   # [leaf_name, ...] — skip entirely during mirror

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self):
        return {
            "left_token":        self.left_token,
            "right_token":       self.right_token,
            "mirror_axis":       self.mirror_axis,
            "controls":          self.controls,
            "manual_pairs":      self.manual_pairs,
            "excluded_controls": self.excluded_controls,
        }

    @classmethod
    def from_dict(cls, d):
        snap                   = cls()
        snap.left_token        = d.get("left_token",        "lf")
        snap.right_token       = d.get("right_token",       "rt")
        snap.mirror_axis       = d.get("mirror_axis",       "X")
        snap.controls          = d.get("controls",          {})
        snap.manual_pairs      = d.get("manual_pairs",      {})
        snap.excluded_controls = d.get("excluded_controls", [])
        return snap

    # ------------------------------------------------------------------
    # Scene persistence — multi-prefix storage
    # ------------------------------------------------------------------

    @staticmethod
    def _ensure_node():
        """Return the settings node, creating it if needed."""
        node = SNAPSHOT_NODE
        if not cmds.objExists(node):
            node = cmds.createNode("transform", name=node)
            cmds.setAttr("{}.visibility".format(node), 0)
        return node

    @classmethod
    def _load_multi_store(cls):
        """
        Load the entire multi-prefix dict from the scene node.
        Auto-migrates legacy single-snapshot data (rigSnapshot attr)
        into the new multi-prefix format on first access.

        Returns a dict: {prefix_str: snapshot_dict, ...}
        """
        if not cmds.objExists(SNAPSHOT_NODE):
            return {}

        # --- New multi-prefix attribute ---
        if cmds.attributeQuery(SNAPSHOT_MULTI_ATTR, node=SNAPSHOT_NODE, exists=True):
            raw = cmds.getAttr("{}.{}".format(SNAPSHOT_NODE, SNAPSHOT_MULTI_ATTR))
            if raw:
                try:
                    store = json.loads(raw)
                    if isinstance(store, dict):
                        return store
                except Exception:
                    pass

        # --- Legacy single-snapshot migration ---
        if cmds.attributeQuery(SNAPSHOT_ATTR, node=SNAPSHOT_NODE, exists=True):
            raw = cmds.getAttr("{}.{}".format(SNAPSHOT_NODE, SNAPSHOT_ATTR))
            if raw:
                try:
                    legacy = json.loads(raw)
                    # Detect prefix from control names in the legacy snapshot
                    prefix = DEFAULT_PREFIX
                    for ctrl_key in legacy.get("controls", {}):
                        p = _detect_prefix(ctrl_key)
                        if p != DEFAULT_PREFIX:
                            prefix = p
                            break
                    store = {prefix: legacy}
                    # Save in new format and remove legacy attr
                    cls._save_multi_store(store)
                    om.MGlobal.displayInfo(
                        "[digetMirrorControl] Migrated legacy snapshot to "
                        "prefix '{}' in new multi-rig format.".format(prefix)
                    )
                    return store
                except Exception:
                    pass

        return {}

    @classmethod
    def _save_multi_store(cls, store):
        """Write the full {prefix: snapshot_dict} dict to the scene node."""
        node = cls._ensure_node()
        if not cmds.attributeQuery(SNAPSHOT_MULTI_ATTR, node=node, exists=True):
            cmds.addAttr(node, longName=SNAPSHOT_MULTI_ATTR, dataType="string")
        cmds.setAttr(
            "{}.{}".format(node, SNAPSHOT_MULTI_ATTR),
            json.dumps(store, indent=2),
            type="string",
        )

    def save_to_scene(self, prefix=None):
        """
        Save this snapshot under *prefix* in the multi-prefix store.

        If prefix is None, attempts to auto-detect from the control names
        in this snapshot. Falls back to DEFAULT_PREFIX.
        """
        if prefix is None:
            prefix = DEFAULT_PREFIX
            for ctrl_key in self.controls:
                p = _detect_prefix(ctrl_key)
                if p != DEFAULT_PREFIX:
                    prefix = p
                    break

        store = self._load_multi_store()
        store[prefix] = self.to_dict()
        self._save_multi_store(store)
        om.MGlobal.displayInfo(
            "[digetMirrorControl] Snapshot saved — {} controls under prefix '{}'.".format(
                len(self.controls), prefix
            )
        )

    @classmethod
    def merge_into_scene(cls, new_snap, prefix=None):
        """
        Load the existing snapshot for *prefix* and overlay new_snap.
        Controls in new_snap replace their counterparts; others are kept.
        """
        if prefix is None:
            prefix = DEFAULT_PREFIX
            for ctrl_key in new_snap.controls:
                p = _detect_prefix(ctrl_key)
                if p != DEFAULT_PREFIX:
                    prefix = p
                    break

        existing = cls.load_from_scene(prefix)
        if existing is None:
            new_snap.save_to_scene(prefix)
            return new_snap

        existing.controls.update(new_snap.controls)
        existing.left_token  = new_snap.left_token
        existing.right_token = new_snap.right_token
        existing.mirror_axis = new_snap.mirror_axis
        existing.save_to_scene(prefix)
        return existing

    @classmethod
    def load_from_scene(cls, prefix=None):
        """
        Return a RigSnapshot for *prefix*, or None.

        If prefix is None, returns the first available snapshot (backward
        compat for code that hasn't been updated to pass a prefix).
        """
        store = cls._load_multi_store()
        if not store:
            return None

        if prefix is not None:
            data = store.get(prefix)
            if data is None:
                return None
            try:
                return cls.from_dict(data)
            except Exception:
                return None

        # No prefix specified — return first available
        for _pfx, data in store.items():
            try:
                return cls.from_dict(data)
            except Exception:
                continue
        return None

    # ------------------------------------------------------------------
    # Multi-prefix management
    # ------------------------------------------------------------------

    @classmethod
    def list_prefixes(cls):
        """Return a sorted list of all stored snapshot prefixes."""
        store = cls._load_multi_store()
        return sorted(store.keys())

    @classmethod
    def delete_prefix(cls, prefix):
        """Remove the snapshot for *prefix* from the scene."""
        store = cls._load_multi_store()
        if prefix in store:
            del store[prefix]
            cls._save_multi_store(store)
            om.MGlobal.displayInfo(
                "[digetMirrorControl] Deleted snapshot for prefix '{}'.".format(prefix)
            )
            return True
        return False

    @classmethod
    def export_prefix(cls, prefix, filepath):
        """Export the snapshot for *prefix* as a standalone JSON file."""
        store = cls._load_multi_store()
        data  = store.get(prefix)
        if data is None:
            om.MGlobal.displayWarning(
                "[digetMirrorControl] No snapshot found for prefix '{}'.".format(prefix)
            )
            return False
        export_data = {"prefix": prefix, "snapshot": data}
        with open(filepath, "w") as f:
            json.dump(export_data, f, indent=2)
        om.MGlobal.displayInfo(
            "[digetMirrorControl] Exported '{}' snapshot to: {}".format(prefix, filepath)
        )
        return True

    @classmethod
    def import_from_file(cls, filepath):
        """
        Import a JSON snapshot file and save it to the scene.

        Returns (prefix, snapshot) on success, or (None, None) on failure.
        """
        try:
            with open(filepath, "r") as f:
                file_data = json.load(f)
        except Exception as exc:
            om.MGlobal.displayError(
                "[digetMirrorControl] Failed to read JSON: {}".format(exc)
            )
            return None, None

        # Support both wrapped format {"prefix":..., "snapshot":...}
        # and raw snapshot dict (for backward compat)
        if "prefix" in file_data and "snapshot" in file_data:
            prefix = file_data["prefix"]
            snap_dict = file_data["snapshot"]
        else:
            snap_dict = file_data
            prefix = DEFAULT_PREFIX
            for ctrl_key in snap_dict.get("controls", {}):
                p = _detect_prefix(ctrl_key)
                if p != DEFAULT_PREFIX:
                    prefix = p
                    break

        try:
            snap = cls.from_dict(snap_dict)
        except Exception as exc:
            om.MGlobal.displayError(
                "[digetMirrorControl] Invalid snapshot data: {}".format(exc)
            )
            return None, None

        snap.save_to_scene(prefix)
        om.MGlobal.displayInfo(
            "[digetMirrorControl] Imported snapshot for '{}' ({} controls).".format(
                prefix, len(snap.controls)
            )
        )
        return prefix, snap

    # ------------------------------------------------------------------
    # Building a snapshot
    # ------------------------------------------------------------------

    @classmethod
    def build(cls, ctrl_list, left_token, right_token, mirror_axis="X"):
        """
        Sample ctrl_list at current pose (temporarily zero-ing rotations to read
        clean world-space axis vectors), build pair assignments, and infer a
        default mirror rule for every keyable attribute.

        Parameters
        ----------
        ctrl_list    : list of str  – Maya control transform names
        left_token   : str          – e.g. "lf"
        right_token  : str          – e.g. "rt"
        mirror_axis  : str          – "X", "Y", or "Z"
        """
        snap             = cls()
        snap.left_token  = left_token
        snap.right_token = right_token
        snap.mirror_axis = mirror_axis

        # 1. Classify each control as left / right / middle
        classification = cls._classify(ctrl_list, left_token, right_token)

        # 2. Sample world-space axis vectors (briefly zero each ctrl's rotation)
        vector_data = cls._sample_axis_vectors(ctrl_list)

        # 3. Build per-control records
        for ctrl in ctrl_list:
            side    = classification.get(ctrl, "middle")
            partner = cls._find_partner(ctrl, left_token, right_token)
            if partner and not cmds.objExists(partner):
                partner = None

            vd  = vector_data.get(ctrl, {})
            pvd = vector_data.get(partner, {}) if partner else {}

            dom  = cls._dominant_axes(vd)
            pdom = cls._dominant_axes(pvd)

            # Collect all keyable, unlocked, scalar attributes
            attributes = {}
            raw_attrs  = cmds.listAttr(ctrl, keyable=True, unlocked=True) or []
            for attr in raw_attrs:
                try:
                    val = cmds.getAttr("{}.{}".format(ctrl, attr))
                except Exception:
                    continue
                if not isinstance(val, (int, float)):
                    continue
                attr_type = cls._attr_type(attr)
                rule      = cls._infer_rule(attr, attr_type, dom, pdom, mirror_axis)
                attributes[attr] = {
                    "type":          attr_type,
                    "rule":          rule,
                    "user_override": False,
                }

            snap.controls[ctrl] = {
                "side":                  side,
                "partner":               partner,
                "dominant_axes":         dom,
                "partner_dominant_axes": pdom,
                "attributes":            attributes,
            }

        return snap

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _attr_type(attr):
        al = attr.lower()
        if "translate" in al:
            return "translate"
        if "rotate" in al:
            return "rotate"
        if "scale" in al:
            return "scale"
        return "custom"

    @staticmethod
    def _classify(ctrl_list, left_token, right_token):
        result = {}
        lt = left_token.lower()
        rt = right_token.lower()
        for ctrl in ctrl_list:
            short = ctrl.split(":")[-1].lower()
            if lt in short and rt not in short:
                result[ctrl] = "left"
            elif rt in short and lt not in short:
                result[ctrl] = "right"
            else:
                result[ctrl] = "middle"
        return result

    @staticmethod
    def _find_partner(ctrl, left_token, right_token):
        """
        Swap left/right token to get the mirror partner name.

        Handles full DAG paths (parent|child) by stripping to the leaf node
        name before doing the token swap, then returning a namespace-qualified
        short name that Maya can resolve unambiguously.

        Uses word-boundary-aware matching so that tokens like "rt" are only
        replaced when they appear as delimited segments (bounded by '_', start,
        or end of string), NOT when embedded inside words like "shirt" or
        "upperteeth".
        """
        # Work on the leaf node only — discard any "|parent" prefix
        leaf = ctrl.split("|")[-1]

        if ":" in leaf:
            ns, base = leaf.rsplit(":", 1)
            ns_prefix = ns + ":"
        else:
            ns_prefix = ""
            base = leaf

        swapped = _swap_side_token(base, left_token, right_token)
        if swapped is None:
            return None
        return ns_prefix + swapped

    @staticmethod
    def _sample_axis_vectors(ctrl_list):
        """
        Temporarily zero each control's rotation so the world matrix
        gives us clean axis direction vectors, then restore.
        """
        # Save current rotation values
        saved = {}
        for ctrl in ctrl_list:
            saved[ctrl] = {}
            for ax in ["X", "Y", "Z"]:
                attr = "{}.rotate{}".format(ctrl, ax)
                try:
                    if cmds.listAttr(attr, keyable=True, unlocked=True):
                        saved[ctrl][ax] = cmds.getAttr(attr)
                except Exception:
                    pass

        # Zero rotations (disable autokey temporarily)
        auto_key = cmds.autoKeyframe(state=True, query=True)
        if auto_key:
            cmds.autoKeyframe(state=False)
        for ctrl in ctrl_list:
            for ax in saved[ctrl]:
                try:
                    cmds.setAttr("{}.rotate{}".format(ctrl, ax), 0)
                except Exception:
                    pass

        # Read world matrix
        vector_data = {}
        for ctrl in ctrl_list:
            try:
                wm = cmds.xform(ctrl, matrix=True, worldSpace=True, query=True)
                wm = [round(v, 4) for v in wm]
                vector_data[ctrl] = {
                    "x_axis": wm[0:3],
                    "y_axis": wm[4:7],
                    "z_axis": wm[8:11],
                }
            except Exception:
                vector_data[ctrl] = {}

        # Restore rotations
        for ctrl in ctrl_list:
            for ax, val in saved[ctrl].items():
                try:
                    cmds.setAttr("{}.rotate{}".format(ctrl, ax), val)
                except Exception:
                    pass
        if auto_key:
            cmds.autoKeyframe(state=True)

        return vector_data

    @staticmethod
    def _dominant_axis_of(vector):
        """Return the world axis label ("X", "-Y", etc.) that vector points most along."""
        if not vector or all(v == 0 for v in vector):
            return "X"
        denom = sum(abs(v) for v in vector)
        if denom == 0:
            return "X"
        pct   = [abs(v) / denom for v in vector]
        idx   = pct.index(max(pct))
        label = ["X", "Y", "Z"][idx]
        return ("-" + label) if vector[idx] < 0 else label

    @classmethod
    def _dominant_axes(cls, vd):
        """Return {"x": "X", "y": "Y", "z": "-Z"} style dict from vector_data entry."""
        if not vd:
            return {"x": "X", "y": "Y", "z": "Z"}
        return {
            "x": cls._dominant_axis_of(vd.get("x_axis", [1, 0, 0])),
            "y": cls._dominant_axis_of(vd.get("y_axis", [0, 1, 0])),
            "z": cls._dominant_axis_of(vd.get("z_axis", [0, 0, 1])),
        }

    @classmethod
    def _infer_rule(cls, attr, attr_type, dom, pdom, mirror_axis):
        """
        Determine copy / negate / ignore for a single attribute by comparing the
        control's dominant-axis orientation with its partner's.

        Custom and scale channels always default to copy.
        The logic mirrors the existing runtime heuristic so the default snapshot
        rules match what the tool would have done without a snapshot.
        """
        if attr_type in ("custom", "scale"):
            return RULE_COPY

        al = attr.lower()

        # Which local axis does this attribute act on?
        if   al.endswith("x"):  chan = "X"
        elif al.endswith("y"):  chan = "Y"
        elif al.endswith("z"):  chan = "Z"
        else:                   return RULE_COPY

        x_dom     = dom.get("x", "X")
        y_dom     = dom.get("y", "Y")
        z_dom     = dom.get("z", "Z")
        opp_x_dom = pdom.get("x", "X")
        opp_y_dom = pdom.get("y", "Y")
        opp_z_dom = pdom.get("z", "Z")

        # Which *local* channel aligns most with the chosen world mirror axis?
        def mirror_local(m_ax, xd, yd, zd):
            if m_ax == xd or ("-" + m_ax) == xd:  return "X"
            if m_ax == yd or ("-" + m_ax) == yd:  return "Y"
            if m_ax == zd or ("-" + m_ax) == zd:  return "Z"
            return m_ax

        mirror_local_ax = mirror_local(mirror_axis, x_dom, y_dom, z_dom)
        same_ori        = (x_dom == opp_x_dom and y_dom == opp_y_dom and z_dom == opp_z_dom)

        if same_ori:
            # Standard symmetric controls (same local-to-world mapping)
            if attr_type == "translate":
                return RULE_NEGATE if chan == mirror_local_ax else RULE_COPY
            if attr_type == "rotate":
                return RULE_COPY   if chan == mirror_local_ax else RULE_NEGATE

        else:
            # Controls whose local axes are differently oriented (e.g. wrist IK)
            local_map     = {"X": x_dom,     "Y": y_dom,     "Z": z_dom}
            opp_local_map = {"X": opp_x_dom, "Y": opp_y_dom, "Z": opp_z_dom}
            ctrl_world    = local_map.get(chan, chan)
            part_world    = opp_local_map.get(chan, chan)

            def is_mirror_same(m_ax, a, b):
                return (m_ax == a and m_ax == b) or \
                       ("-" + m_ax == a and "-" + m_ax == b)

            def is_same_not_mirror(m_ax, a, b):
                same = (a == b)
                not_mirror = (a != m_ax) and (a != "-" + m_ax)
                return same and not_mirror

            if attr_type == "translate":
                if is_mirror_same(mirror_axis, ctrl_world, part_world):
                    return RULE_NEGATE
                if ctrl_world == part_world:
                    return RULE_COPY if (chan == mirror_local_ax or chan == mirror_axis) else RULE_NEGATE
                return RULE_NEGATE

            if attr_type == "rotate":
                if is_same_not_mirror(mirror_axis, ctrl_world, part_world):
                    return RULE_NEGATE if (chan == mirror_local_ax or chan == mirror_axis) else RULE_COPY
                return RULE_COPY

        return RULE_COPY

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def get_rule(self, ctrl, attr):
        """
        Return the stored rule for ctrl.attr, or None if not in snapshot.
        None signals the caller to fall back to the runtime heuristic.
        """
        ctrl_data = self.controls.get(ctrl)
        if ctrl_data is None:
            return None
        attr_data = ctrl_data.get("attributes", {}).get(attr)
        if attr_data is None:
            return None
        return attr_data.get("rule", RULE_COPY)

    def set_rule(self, ctrl, attr, rule, user_override=True):
        """Update a rule (called by the editor)."""
        if ctrl in self.controls:
            attrs = self.controls[ctrl].setdefault("attributes", {})
            if attr in attrs:
                attrs[attr]["rule"]          = rule
                attrs[attr]["user_override"] = user_override

    # ------------------------------------------------------------------
    # Manual pair helpers
    # ------------------------------------------------------------------

    def get_manual_partner(self, ctrl):
        """
        Return the manually-assigned mirror partner for ctrl, or None.
        Checks both directions (src→prt and prt→src).
        ctrl may be a full DAG path or a short/namespace-qualified name.
        """
        leaf = ctrl.split("|")[-1]
        if leaf in self.manual_pairs:
            return self.manual_pairs[leaf]
        # Reverse lookup — partner points back to source
        for src, prt in self.manual_pairs.items():
            if prt == leaf:
                return src
        return None

    def is_excluded(self, ctrl):
        """Return True if this control should be skipped during mirroring."""
        leaf = ctrl.split("|")[-1]
        return leaf in self.excluded_controls

    def add_manual_pair(self, source_leaf, partner_leaf):
        self.manual_pairs[source_leaf] = partner_leaf

    def remove_manual_pair(self, source_leaf):
        self.manual_pairs.pop(source_leaf, None)
        # Also remove if it appears as a value (reverse pair)
        to_remove = [k for k, v in self.manual_pairs.items() if v == source_leaf]
        for k in to_remove:
            del self.manual_pairs[k]

    def set_excluded(self, ctrl_leaf, excluded=True):
        if excluded:
            if ctrl_leaf not in self.excluded_controls:
                self.excluded_controls.append(ctrl_leaf)
        else:
            if ctrl_leaf in self.excluded_controls:
                self.excluded_controls.remove(ctrl_leaf)


# ---------------------------------------------------------------------------
# SnapshotEditorDialog
# ---------------------------------------------------------------------------

class SnapshotEditorDialog(QtWidgets.QDialog):
    """
    Displays the snapshot's controls grouped into pairs and middle controls.
    Every attribute row has a dropdown for its mirror rule (copy / negate / ignore).
    Changes are written back to the in-memory snapshot immediately; the user
    must click "Save to Scene" to persist them.
    """

    HEADERS = ["Name", "Type", "Rule"]

    def __init__(self, snapshot, re_snapshot_callback=None, parent=None):
        super().__init__(parent or maya_main_window())
        self.snapshot              = snapshot
        self.re_snapshot_callback  = re_snapshot_callback   # callable () -> RigSnapshot | None
        self._prefix               = None   # set by the main dialog after creation
        self.setWindowTitle("Rig Snapshot Editor")
        self.resize(680, 560)
        self._build_ui()
        self._populate()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # --- Info bar ---
        self.info_label = QtWidgets.QLabel()
        self.info_label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(self.info_label)

        sep = QtWidgets.QFrame()
        sep.setFrameShape(QtWidgets.QFrame.HLine)
        sep.setFrameShadow(QtWidgets.QFrame.Sunken)
        layout.addWidget(sep)

        # --- Hint ---
        hint = QtWidgets.QLabel(
            "Rules are per-attribute.  "
            "<b>copy</b> = transfer value as-is  ·  "
            "<b>negate</b> = transfer negated value  ·  "
            "<b>ignore</b> = skip this attribute"
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # --- Tree ---
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setColumnCount(3)
        self.tree.setHeaderLabels(self.HEADERS)
        self.tree.setAlternatingRowColors(True)
        self.tree.setUniformRowHeights(True)
        hdr = self.tree.header()
        hdr.setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        hdr.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(2, QtWidgets.QHeaderView.Fixed)
        self.tree.header().resizeSection(2, 90)
        layout.addWidget(self.tree)

        # --- Buttons ---
        btn_row = QtWidgets.QHBoxLayout()
        self.re_snap_btn = QtWidgets.QPushButton("↺  Re-Snapshot")
        self.re_snap_btn.setToolTip(
            "Re-sample the rig with current token and axis settings,\n"
            "replacing all rules (user overrides will be lost)."
        )
        self.expand_btn  = QtWidgets.QPushButton("Expand All")
        self.collapse_btn = QtWidgets.QPushButton("Collapse All")
        self.save_btn    = QtWidgets.QPushButton("Save to Scene")
        self.close_btn   = QtWidgets.QPushButton("Close")

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
    # Tree population
    # ------------------------------------------------------------------

    def _populate(self):
        self.tree.clear()
        snap = self.snapshot

        # Update info label
        n_ctrls = len(snap.controls)
        n_pairs = sum(
            1 for d in snap.controls.values()
            if d.get("partner") and d.get("side") == "left"
               and snap.controls.get(d["partner"]) is not None
        )
        self.info_label.setText(
            "<b>{} controls</b>  ·  <b>{} pairs</b>  ·  "
            "Mirror axis: <b>{}</b>  ·  "
            "Left token: <b>{}</b>  ·  Right token: <b>{}</b>".format(
                n_ctrls, n_pairs,
                snap.mirror_axis, snap.left_token, snap.right_token,
            )
        )

        # --- Identify pairs ---
        seen    = set()
        pairs   = []     # list of (lf_ctrl, rt_ctrl)
        middles = []

        for ctrl, data in snap.controls.items():
            if ctrl in seen:
                continue
            side    = data.get("side",    "middle")
            partner = data.get("partner", None)
            if side == "left" and partner and partner in snap.controls:
                pairs.append((ctrl, partner))
                seen.add(ctrl)
                seen.add(partner)
            elif side == "right" and partner and partner in snap.controls:
                if partner not in seen:
                    pairs.append((partner, ctrl))
                seen.add(ctrl)
                seen.add(partner)
            else:
                if ctrl not in seen:
                    middles.append(ctrl)
                    seen.add(ctrl)

        # --- Paired Controls section ---
        if pairs:
            section = self._make_section_header("Paired Controls ({} pairs)".format(len(pairs)))
            self.tree.addTopLevelItem(section)
            for lf, rt in sorted(pairs):
                pair_item = self._make_pair_item(lf, rt)
                self.tree.addTopLevelItem(pair_item)
                pair_item.setExpanded(True)
                for i in range(pair_item.childCount()):
                    pair_item.child(i).setExpanded(False)

        # --- Middle Controls section ---
        if middles:
            section = self._make_section_header("Middle Controls ({})".format(len(middles)))
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
        lf_short = lf.split(":")[-1]
        rt_short = rt.split(":")[-1]
        pair_item = QtWidgets.QTreeWidgetItem(
            ["  {} ↔ {}".format(lf_short, rt_short), "", ""]
        )
        pair_item.setFlags(QtCore.Qt.ItemIsEnabled)
        font = pair_item.font(0)
        font.setItalic(True)
        pair_item.setFont(0, font)

        for ctrl in [lf, rt]:
            ctrl_item = self._make_ctrl_item(ctrl)
            pair_item.addChild(ctrl_item)

        return pair_item

    def _make_ctrl_item(self, ctrl):
        side       = self.snapshot.controls.get(ctrl, {}).get("side", "middle")
        ctrl_item  = QtWidgets.QTreeWidgetItem([ctrl, side, ""])
        ctrl_item.setFlags(QtCore.Qt.ItemIsEnabled)
        font = ctrl_item.font(0)
        font.setBold(True)
        ctrl_item.setFont(0, font)

        attrs = self.snapshot.controls.get(ctrl, {}).get("attributes", {})
        for attr_name in sorted(attrs.keys()):
            attr_data  = attrs[attr_name]
            attr_type  = attr_data.get("type",  "custom")
            rule       = attr_data.get("rule",  RULE_COPY)
            is_override = attr_data.get("user_override", False)

            row = QtWidgets.QTreeWidgetItem([attr_name, attr_type, ""])
            row.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable)
            if is_override:
                font = row.font(0)
                font.setItalic(True)
                row.setFont(0, font)
                row.setToolTip(0, "User override")
            ctrl_item.addChild(row)

            combo = QtWidgets.QComboBox()
            combo.addItems(RULES)
            combo.setCurrentText(rule)
            # Colour-code for quick scanning
            self._style_combo(combo, rule)
            combo.currentTextChanged.connect(
                lambda new_rule, c=ctrl, a=attr_name, cb=combo:
                    self._on_rule_changed(c, a, new_rule, cb)
            )
            self.tree.setItemWidget(row, 2, combo)

        return ctrl_item

    @staticmethod
    def _style_combo(combo, rule):
        palette = combo.palette()
        if rule == RULE_NEGATE:
            combo.setStyleSheet("QComboBox { color: #e8a060; }")
        elif rule == RULE_IGNORE:
            combo.setStyleSheet("QComboBox { color: #888888; }")
        else:
            combo.setStyleSheet("")

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_rule_changed(self, ctrl, attr, new_rule, combo):
        self.snapshot.set_rule(ctrl, attr, new_rule, user_override=True)
        self._style_combo(combo, new_rule)
        # Mark the row label italic to indicate it's been overridden
        ctrl_data = self.snapshot.controls.get(ctrl, {})
        attrs     = ctrl_data.get("attributes", {})
        if attr in attrs:
            attrs[attr]["user_override"] = True

    def _on_re_snapshot(self):
        if not self.re_snapshot_callback:
            return
        new_snap = self.re_snapshot_callback()
        if new_snap:
            self.snapshot = new_snap
            self._populate()

    def _on_save(self):
        self.snapshot.save_to_scene(self._prefix)
        pfx_label = self._prefix if self._prefix and self._prefix != DEFAULT_PREFIX else "(scene)"
        QtWidgets.QMessageBox.information(
            self, "Saved", "Snapshot saved for '{}'.".format(pfx_label)
        )

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def update_snapshot(self, snapshot):
        self.snapshot = snapshot
        self._populate()


# ---------------------------------------------------------------------------
# ManualPairEditorDialog
# ---------------------------------------------------------------------------

class ManualPairEditorDialog(QtWidgets.QDialog):
    """
    Window for manually assigning mirror partners to controls that the
    token-swap heuristic cannot resolve (missing partner, wrong name, etc.).

    Smart display
    -------------
    Controls that auto-pair correctly are NEVER shown unless the user
    switches to "All" view — they don't need attention so they don't
    clutter the table.  Only controls with problems are shown by default.

    Workflow
    --------
    1.  Select a control in the Maya viewport.
    2.  Click  ⊕ Src  to assign it as the SOURCE for a row, or
        click  ⊕ Prt  to assign it as the PARTNER.
    3.  Alternatively type the namespace:nodeName directly in the field.
    4.  Click "Exclude" to permanently skip a control during mirroring.
    5.  Click "Save to Scene" — pairs are written into the snapshot node.

    Status badges
    -------------
      ✗  red    Unpaired  — no partner found by any method
      ★  blue   Manual    — user-defined override pair
      ✔  green  Auto OK   — token-swap found a valid partner (hidden by default)
      ○  grey   Excluded  — skipped during mirror
    """

    STATUS_UNPAIRED = "unpaired"
    STATUS_MANUAL   = "manual"
    STATUS_AUTO_OK  = "auto_ok"
    STATUS_EXCLUDED = "excluded"

    COL_STATUS  = 0
    COL_SOURCE  = 1
    COL_ARROW   = 2
    COL_PARTNER = 3
    COL_PICK    = 4
    COL_EXCL    = 5

    # Background colours per status (subtle, theme-friendly)
    _BG = {
        STATUS_UNPAIRED: QtGui.QColor(80,  30,  30),
        STATUS_MANUAL:   QtGui.QColor(30,  50,  80),
        STATUS_AUTO_OK:  QtGui.QColor(30,  55,  30),
        STATUS_EXCLUDED: QtGui.QColor(45,  45,  45),
    }

    def __init__(self, main_dialog, prefix=None, parent=None):
        super().__init__(parent or maya_main_window())
        self.main_dialog = main_dialog
        self._prefix     = prefix
        self._snapshot   = RigSnapshot.load_from_scene(prefix)
        self._rows_data  = []
        self.setWindowTitle("Manual Pair Editor  —  digetMirrorControl")
        self.setMinimumWidth(860)
        self.resize(960, 620)
        self._build_ui()
        self._refresh()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # --- Info bar ---
        self.info_label = QtWidgets.QLabel()
        self.info_label.setWordWrap(True)
        root.addWidget(self.info_label)

        # --- How-to hint ---
        hint = QtWidgets.QLabel(
            "<i>Select a control in the Maya viewport, then click "
            "<b>⊕ Src</b> or <b>⊕ Prt</b> to assign it to a row.  "
            "Or type a <tt>namespace:nodeName</tt> directly in the field.</i>"
        )
        hint.setWordWrap(True)
        root.addWidget(hint)

        sep = QtWidgets.QFrame()
        sep.setFrameShape(QtWidgets.QFrame.HLine)
        sep.setFrameShadow(QtWidgets.QFrame.Sunken)
        root.addWidget(sep)

        # --- Filter bar ---
        flt_row = QtWidgets.QHBoxLayout()
        flt_row.addWidget(QtWidgets.QLabel("View:"))
        self._flt_issues   = QtWidgets.QRadioButton("Needs Attention")
        self._flt_issues.setChecked(True)
        self._flt_all      = QtWidgets.QRadioButton("All Controls")
        self._flt_manual   = QtWidgets.QRadioButton("Manual Overrides")
        self._flt_excluded = QtWidgets.QRadioButton("Excluded")
        for rb in (self._flt_issues, self._flt_all, self._flt_manual, self._flt_excluded):
            flt_row.addWidget(rb)
        flt_row.addStretch()

        self._auto_select_chk = QtWidgets.QCheckBox("Select in viewport on click")
        self._auto_select_chk.setChecked(True)
        self._auto_select_chk.setToolTip(
            "When checked, clicking a row automatically selects\n"
            "the source control in the Maya viewport so you can\n"
            "see which control it is before assigning a partner."
        )
        flt_row.addWidget(self._auto_select_chk)
        root.addLayout(flt_row)

        # --- Table ---
        self.table = QtWidgets.QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["", "Source Control", "", "Mirror Partner", "Pick", ""]
        )
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(self.COL_STATUS,  QtWidgets.QHeaderView.Fixed)
        hdr.setSectionResizeMode(self.COL_SOURCE,  QtWidgets.QHeaderView.Stretch)
        hdr.setSectionResizeMode(self.COL_ARROW,   QtWidgets.QHeaderView.Fixed)
        hdr.setSectionResizeMode(self.COL_PARTNER, QtWidgets.QHeaderView.Stretch)
        hdr.setSectionResizeMode(self.COL_PICK,    QtWidgets.QHeaderView.Fixed)
        hdr.setSectionResizeMode(self.COL_EXCL,    QtWidgets.QHeaderView.Fixed)
        self.table.setColumnWidth(self.COL_STATUS, 28)
        self.table.setColumnWidth(self.COL_ARROW,  22)
        self.table.setColumnWidth(self.COL_PICK,   130)
        self.table.setColumnWidth(self.COL_EXCL,   80)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(False)   # we control bg per-row
        root.addWidget(self.table)

        # --- Summary ---
        self.summary_label = QtWidgets.QLabel()
        root.addWidget(self.summary_label)

        # --- Buttons ---
        btn_row = QtWidgets.QHBoxLayout()
        self.refresh_btn      = QtWidgets.QPushButton("↺  Refresh")
        self.clear_manual_btn = QtWidgets.QPushButton("Clear All Manual Pairs")
        self.save_btn         = QtWidgets.QPushButton("Save to Scene")
        self.close_btn        = QtWidgets.QPushButton("Close")
        self.save_btn.setDefault(True)
        btn_row.addWidget(self.refresh_btn)
        btn_row.addWidget(self.clear_manual_btn)
        btn_row.addStretch()
        btn_row.addWidget(self.save_btn)
        btn_row.addWidget(self.close_btn)
        root.addLayout(btn_row)

        # Connections
        self._flt_issues.toggled.connect(self._apply_filter)
        self._flt_all.toggled.connect(self._apply_filter)
        self._flt_manual.toggled.connect(self._apply_filter)
        self._flt_excluded.toggled.connect(self._apply_filter)
        self.refresh_btn.clicked.connect(self._on_refresh)
        self.clear_manual_btn.clicked.connect(self._on_clear_manual)
        self.save_btn.clicked.connect(self._on_save)
        self.close_btn.clicked.connect(self.close)
        self.table.currentItemChanged.connect(self._on_row_selected)

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------

    def _leaf(self, ctrl):
        return ctrl.split("|")[-1]

    def _refresh(self):
        """Re-scan scene controls and rebuild rows_data from scratch."""
        self._snapshot = RigSnapshot.load_from_scene(self._prefix) or RigSnapshot()

        left_token  = self.main_dialog.get_left_name()
        right_token = self.main_dialog.get_right_name()

        manual_pairs      = dict(self._snapshot.manual_pairs)
        excluded_controls = list(self._snapshot.excluded_controls)

        # Only show controls belonging to this prefix's character rig.
        if self._prefix:
            all_ctrls = self.main_dialog._get_controls_for_prefix(self._prefix)
        else:
            all_ctrls = self.main_dialog._get_all_nurbs_controls()

        rows = []
        seen = set()   # leaves already accounted for

        for ctrl in all_ctrls:
            leaf = self._leaf(ctrl)
            if leaf in seen:
                continue

            # Excluded
            if leaf in excluded_controls:
                rows.append({
                    "status":      self.STATUS_EXCLUDED,
                    "source":      leaf,
                    "partner":     "",
                    "source_full": ctrl,
                    "editable":    False,
                })
                seen.add(leaf)
                continue

            # Manual pair
            if leaf in manual_pairs:
                partner_leaf = manual_pairs[leaf]
                rows.append({
                    "status":      self.STATUS_MANUAL,
                    "source":      leaf,
                    "partner":     partner_leaf,
                    "source_full": ctrl,
                    "editable":    True,
                })
                seen.add(leaf)
                seen.add(partner_leaf)
                continue

            # Also check if this leaf is the partner in an existing manual pair
            if leaf in manual_pairs.values():
                seen.add(leaf)
                continue

            # Auto-pair
            auto_partner = self.main_dialog.get_partner(
                ctrl, left_token, right_token, snapshot=self._snapshot
            )
            if auto_partner and cmds.objExists(auto_partner):
                auto_leaf = self._leaf(auto_partner)
                rows.append({
                    "status":      self.STATUS_AUTO_OK,
                    "source":      leaf,
                    "partner":     auto_leaf,
                    "source_full": ctrl,
                    "editable":    False,
                })
                seen.add(leaf)
                seen.add(auto_leaf)
            else:
                # Only flag as unpaired if the control actually has a side token —
                # centre controls (cn, spine, chest, jaw, etc.) don't have a mirror
                # partner by design and should never appear in this editor.
                base_name = leaf.split(":")[-1].lower()
                has_side_token = (
                    left_token.lower()  in base_name or
                    right_token.lower() in base_name
                )
                if has_side_token:
                    rows.append({
                        "status":      self.STATUS_UNPAIRED,
                        "source":      leaf,
                        "partner":     "",
                        "source_full": ctrl,
                        "editable":    True,
                    })
                # Controls without a side token are silently skipped — they are
                # centre/middle controls that don't mirror and need no action.
                seen.add(leaf)

        self._rows_data = rows

        # Build info label
        n_unpaired = sum(1 for r in rows if r["status"] == self.STATUS_UNPAIRED)
        n_manual   = sum(1 for r in rows if r["status"] == self.STATUS_MANUAL)
        n_auto     = sum(1 for r in rows if r["status"] == self.STATUS_AUTO_OK)
        n_excl     = sum(1 for r in rows if r["status"] == self.STATUS_EXCLUDED)

        if n_unpaired:
            self.info_label.setText(
                "<span style='color:#e06060;'><b>{} control{} need manual pairing.</b></span>  "
                "Auto-matched: {}  ·  Manual overrides: {}  ·  Excluded: {}".format(
                    n_unpaired, "s" if n_unpaired != 1 else "",
                    n_auto, n_manual, n_excl
                )
            )
        else:
            self.info_label.setText(
                "<span style='color:#60c060;'><b>All controls are paired ✔</b></span>  "
                "Auto-matched: {}  ·  Manual overrides: {}  ·  Excluded: {}".format(
                    n_auto, n_manual, n_excl
                )
            )

        self._apply_filter()

    # ------------------------------------------------------------------
    # Filter + table rendering
    # ------------------------------------------------------------------

    def _visible_statuses(self):
        if self._flt_issues.isChecked():
            return {self.STATUS_UNPAIRED, self.STATUS_MANUAL}
        if self._flt_manual.isChecked():
            return {self.STATUS_MANUAL}
        if self._flt_excluded.isChecked():
            return {self.STATUS_EXCLUDED}
        return {self.STATUS_UNPAIRED, self.STATUS_MANUAL,
                self.STATUS_AUTO_OK, self.STATUS_EXCLUDED}

    def _apply_filter(self):
        visible = self._visible_statuses()
        self.table.setRowCount(0)
        for rd in self._rows_data:
            if rd["status"] in visible:
                self._insert_row(rd)
        n = self.table.rowCount()
        self.summary_label.setText(
            "Showing {} row{}.".format(n, "s" if n != 1 else "")
        )

    def _insert_row(self, rd):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setRowHeight(row, 30)

        status = rd["status"]
        bg     = self._BG.get(status, QtGui.QColor(50, 50, 50))

        # Helper: create a plain item with the row background
        def _item(text, align=QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft, editable=False):
            it = QtWidgets.QTableWidgetItem(text)
            it.setTextAlignment(align)
            it.setBackground(bg)
            if not editable:
                it.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable)
            return it

        # Col 0 — status badge
        badge_map = {
            self.STATUS_UNPAIRED: ("✗", "#e06060"),
            self.STATUS_MANUAL:   ("★", "#6090e0"),
            self.STATUS_AUTO_OK:  ("✔", "#60c060"),
            self.STATUS_EXCLUDED: ("○", "#888888"),
        }
        badge_txt, badge_color = badge_map.get(status, ("?", "#ffffff"))
        badge_item = _item(badge_txt, QtCore.Qt.AlignCenter)
        badge_item.setForeground(QtGui.QColor(badge_color))
        badge_item.setData(QtCore.Qt.UserRole, rd)   # stash row dict here
        badge_item.setToolTip({
            self.STATUS_UNPAIRED: "Unpaired — no partner found automatically",
            self.STATUS_MANUAL:   "Manual override pair",
            self.STATUS_AUTO_OK:  "Auto-matched — no action needed",
            self.STATUS_EXCLUDED: "Excluded — skipped during mirror",
        }.get(status, ""))
        self.table.setItem(row, self.COL_STATUS, badge_item)

        # Col 1 — source (always read-only display; Pick Src updates the underlying rd)
        src_item = _item(rd["source"])
        src_item.setToolTip(rd.get("source_full", rd["source"]))
        self.table.setItem(row, self.COL_SOURCE, src_item)

        # Col 2 — arrow
        arr_item = _item("↔", QtCore.Qt.AlignCenter)
        self.table.setItem(row, self.COL_ARROW, arr_item)

        # Col 3 — partner field
        if rd["editable"]:
            le = QtWidgets.QLineEdit(rd["partner"])
            le.setPlaceholderText("Select in Maya → click ⊕ Prt  (or type name)")
            le.setStyleSheet("background: #2a3a4a; border: 1px solid #4a6a8a;")
            le.textChanged.connect(lambda txt, r=rd: r.update({"partner": txt}))
            self.table.setCellWidget(row, self.COL_PARTNER, le)
        else:
            prt_item = _item(rd["partner"])
            if status == self.STATUS_EXCLUDED:
                prt_item.setForeground(QtGui.QColor("#666"))
            self.table.setItem(row, self.COL_PARTNER, prt_item)

        # Col 4 — pick buttons (only for editable rows)
        if rd["editable"]:
            pick_w   = QtWidgets.QWidget()
            pick_lay = QtWidgets.QHBoxLayout(pick_w)
            pick_lay.setContentsMargins(2, 2, 2, 2)
            pick_lay.setSpacing(3)

            btn_src = QtWidgets.QPushButton("⊕ Src")
            btn_src.setFixedHeight(22)
            btn_src.setToolTip(
                "Select the SOURCE control in the Maya viewport,\n"
                "then click this button to populate the Source field."
            )
            btn_prt = QtWidgets.QPushButton("⊕ Prt")
            btn_prt.setFixedHeight(22)
            btn_prt.setToolTip(
                "Select the PARTNER control in the Maya viewport,\n"
                "then click this button to populate the Partner field."
            )
            pick_lay.addWidget(btn_src)
            pick_lay.addWidget(btn_prt)

            # Capture row index at connection time via the badge item reference
            btn_src.clicked.connect(
                lambda _chk=False, r=row: self._pick_from_selection(r, pick_source=True)
            )
            btn_prt.clicked.connect(
                lambda _chk=False, r=row: self._pick_from_selection(r, pick_source=False)
            )
            self.table.setCellWidget(row, self.COL_PICK, pick_w)

        # Col 5 — Exclude / Un-exclude button
        excl_w   = QtWidgets.QWidget()
        excl_lay = QtWidgets.QHBoxLayout(excl_w)
        excl_lay.setContentsMargins(2, 2, 2, 2)
        if status == self.STATUS_EXCLUDED:
            btn_unex = QtWidgets.QPushButton("Un-Excl")
            btn_unex.setFixedHeight(22)
            btn_unex.setToolTip("Remove from exclusion list")
            btn_unex.clicked.connect(
                lambda _chk=False, leaf=rd["source"]: self._toggle_excluded(leaf, False)
            )
            excl_lay.addWidget(btn_unex)
        else:
            btn_excl = QtWidgets.QPushButton("Exclude")
            btn_excl.setFixedHeight(22)
            btn_excl.setToolTip(
                "Permanently skip this control during mirror operations.\n"
                "Useful for rig-internal controls, duplicate offset nodes, etc."
            )
            btn_excl.clicked.connect(
                lambda _chk=False, leaf=rd["source"]: self._toggle_excluded(leaf, True)
            )
            excl_lay.addWidget(btn_excl)
        self.table.setCellWidget(row, self.COL_EXCL, excl_w)

    # ------------------------------------------------------------------
    # Interaction
    # ------------------------------------------------------------------

    def _on_row_selected(self, current, previous):
        """
        Called whenever the active table row changes.
        If 'Select in viewport' is checked, select the source control in Maya
        so the user can see exactly which control they are looking at.
        Also tries to select the partner control at the same time when one is
        already assigned — both nodes are selected so the user can frame them
        together in the viewport with 'F'.
        """
        if not self._auto_select_chk.isChecked():
            return
        if current is None:
            return

        # Retrieve the row data from the badge item in column 0
        row       = current.row()
        badge_item = self.table.item(row, self.COL_STATUS)
        if badge_item is None:
            return
        rd = badge_item.data(QtCore.Qt.UserRole)
        if rd is None:
            return

        to_select = []

        # Source — prefer full DAG path stored in source_full, fall back to leaf
        source_full = rd.get("source_full", rd.get("source", ""))
        if source_full and cmds.objExists(source_full):
            to_select.append(source_full)
        elif rd.get("source") and cmds.objExists(rd["source"]):
            to_select.append(rd["source"])

        # Partner — select it too if it's already set and exists
        partner = rd.get("partner", "").strip()
        if partner and cmds.objExists(partner):
            to_select.append(partner)

        if to_select:
            cmds.select(to_select, replace=True)
            om.MGlobal.displayInfo(
                "[ManualPairEditor] Selected: {}".format(
                    "  +  ".join(n.split("|")[-1] for n in to_select)
                )
            )

    def _pick_from_selection(self, table_row, pick_source):
        """Read current Maya selection and populate Source or Partner for table_row."""
        sel = cmds.ls(selection=True, long=False) or []
        if not sel:
            om.MGlobal.displayWarning(
                "[ManualPairEditor] Nothing selected in Maya. "
                "Select a control in the viewport first."
            )
            return
        # Use first selected, strip any DAG prefix
        picked = sel[0].split("|")[-1]

        badge_item = self.table.item(table_row, self.COL_STATUS)
        if badge_item is None:
            return
        rd = badge_item.data(QtCore.Qt.UserRole)
        if rd is None:
            return

        if pick_source:
            rd["source"] = picked
            src_item = self.table.item(table_row, self.COL_SOURCE)
            if src_item:
                src_item.setText(picked)
        else:
            rd["partner"] = picked
            widget = self.table.cellWidget(table_row, self.COL_PARTNER)
            if isinstance(widget, QtWidgets.QLineEdit):
                widget.setText(picked)

        om.MGlobal.displayInfo(
            "[ManualPairEditor] Assigned '{}' as {}.".format(
                picked, "Source" if pick_source else "Partner"
            )
        )

    def _toggle_excluded(self, leaf, exclude):
        """
        Add/remove a control from the exclusion list and refresh.

        IMPORTANT: pending table edits (typed-but-not-yet-saved pairs) are
        committed to the snapshot BEFORE saving so that clicking Exclude does
        not discard unsaved manual pair entries from other rows.
        """
        # Commit any pending table edits first — this is the bug fix.
        self._collect_pending_edits()

        self._snapshot.set_excluded(leaf, exclude)
        # Also remove from manual pairs if excluding
        if exclude:
            self._snapshot.remove_manual_pair(leaf)
        self._snapshot.save_to_scene(self._prefix)
        self._refresh()

    # ------------------------------------------------------------------
    # Save / refresh
    # ------------------------------------------------------------------

    def _collect_pending_edits(self):
        """
        Read every editable row's current source/partner values from the
        live table widgets and commit them into self._snapshot.manual_pairs.

        This must be called before any save_to_scene() call so that edits
        typed into QLineEdit partner fields are not lost when the snapshot
        is written and the table is subsequently refreshed.

        IMPORTANT: partner values are read directly from the QLineEdit cell
        widgets — NOT from the rd dict stored in UserRole data.  PySide6's
        QTableWidgetItem.data() can return a detached copy of the original
        dict, so the textChanged lambda that updates the captured rd object
        may not be visible when reading back through data().
        """
        new_manual = {}
        visible_sources = set()

        for row in range(self.table.rowCount()):
            badge_item = self.table.item(row, self.COL_STATUS)
            if badge_item is None:
                continue
            rd = badge_item.data(QtCore.Qt.UserRole)
            if rd is None or not rd.get("editable"):
                continue

            source = rd.get("source", "").strip()
            if not source:
                continue

            # Read partner directly from the live QLineEdit widget —
            # this is the authoritative value, not rd["partner"].
            partner = ""
            widget = self.table.cellWidget(row, self.COL_PARTNER)
            if isinstance(widget, QtWidgets.QLineEdit):
                partner = widget.text().strip()
            else:
                # Fallback for non-widget rows (shouldn't happen for editable)
                partner = rd.get("partner", "").strip()

            visible_sources.add(source)
            if partner:
                new_manual[source] = partner
            # Blank partner → intentionally removing that pair; don't write it

        # Remove stale entries for sources visible in this view, then apply fresh ones
        for src in list(self._snapshot.manual_pairs.keys()):
            if src in visible_sources:
                del self._snapshot.manual_pairs[src]
        self._snapshot.manual_pairs.update(new_manual)

    def _on_save(self):
        """Collect all editable rows and save manual pairs to snapshot."""
        self._collect_pending_edits()
        self._snapshot.save_to_scene(self._prefix)

        n = len(self._snapshot.manual_pairs)
        QtWidgets.QMessageBox.information(
            self, "Saved",
            "{} manual pair{} saved to scene.".format(
                n, "s" if n != 1 else "",
            )
        )
        self._refresh()

    def _on_refresh(self):
        self._snapshot = RigSnapshot.load_from_scene(self._prefix) or RigSnapshot()
        self._refresh()

    def _on_clear_manual(self):
        result = QtWidgets.QMessageBox.question(
            self, "Clear Manual Pairs",
            "Remove ALL manual pair assignments?\n"
            "(Exclusions are not affected.  Auto-matched pairs still work.)",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
        )
        if result == QtWidgets.QMessageBox.Yes:
            self._snapshot.manual_pairs.clear()
            self._snapshot.save_to_scene(self._prefix)
            self._refresh()


# ---------------------------------------------------------------------------
# SnapshotManagerDialog
# ---------------------------------------------------------------------------

class SnapshotManagerDialog(QtWidgets.QDialog):
    """
    Manage per-character snapshots: view stored prefixes, export to JSON,
    import from JSON, or delete individual character snapshots.
    """

    prefixes_changed = QtCore.Signal()   # emitted after any add/delete/import

    def __init__(self, parent=None):
        super().__init__(parent or maya_main_window())
        self.setWindowTitle("Snapshot Manager  —  digetMirrorControl")
        self.setMinimumWidth(520)
        self.resize(560, 380)
        self.setStyleSheet(DARK_STYLESHEET)
        self._build_ui()
        self._refresh_list()

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        info = QtWidgets.QLabel(
            "<b>Stored Character Snapshots</b><br>"
            "<span style='color:#999;font-size:11px;'>"
            "Each character rig is stored under its namespace prefix.  "
            "Export to share with other scenes, or delete to clean up.</span>"
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        # --- List ---
        self.list_widget = QtWidgets.QListWidget()
        self.list_widget.setAlternatingRowColors(True)
        self.list_widget.setStyleSheet(
            "QListWidget { background: #333; border: 1px solid #555; border-radius: 4px; }"
            "QListWidget::item { padding: 6px 10px; color: #d4d4d4; }"
            "QListWidget::item:selected { background: #4a90d9; color: #fff; }"
            "QListWidget::item:alternate { background: #383838; }"
        )
        layout.addWidget(self.list_widget)

        # --- Buttons ---
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.setSpacing(6)

        self.export_btn = QtWidgets.QPushButton("📤  Export JSON")
        self.export_btn.setToolTip("Export the selected character's snapshot\nto a .json file for use in other scenes.")
        self.import_btn = QtWidgets.QPushButton("📥  Import JSON")
        self.import_btn.setToolTip("Import a snapshot from a .json file.\nThe character prefix is read from the file.")
        self.delete_btn = QtWidgets.QPushButton("🗑  Delete")
        self.delete_btn.setToolTip("Remove the selected character's snapshot\nfrom this scene.")
        self.delete_btn.setStyleSheet(
            "QPushButton { color: #e08080; } QPushButton:hover { background: #4a2020; }"
        )

        btn_row.addWidget(self.export_btn)
        btn_row.addWidget(self.import_btn)
        btn_row.addStretch()
        btn_row.addWidget(self.delete_btn)
        layout.addLayout(btn_row)

        # --- Close ---
        close_row = QtWidgets.QHBoxLayout()
        close_row.addStretch()
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(self.close)
        close_row.addWidget(close_btn)
        layout.addLayout(close_row)

        # Connections
        self.export_btn.clicked.connect(self._on_export)
        self.import_btn.clicked.connect(self._on_import)
        self.delete_btn.clicked.connect(self._on_delete)

    def _refresh_list(self):
        self.list_widget.clear()
        prefixes = RigSnapshot.list_prefixes()
        for pfx in prefixes:
            snap = RigSnapshot.load_from_scene(pfx)
            n_ctrls = len(snap.controls) if snap else 0
            label = pfx if pfx != DEFAULT_PREFIX else "(no namespace)"
            item = QtWidgets.QListWidgetItem(
                "{}   —   {} controls".format(label, n_ctrls)
            )
            item.setData(QtCore.Qt.UserRole, pfx)
            self.list_widget.addItem(item)

        if not prefixes:
            item = QtWidgets.QListWidgetItem("  No snapshots stored yet")
            item.setFlags(QtCore.Qt.NoItemFlags)
            self.list_widget.addItem(item)

    def _selected_prefix(self):
        item = self.list_widget.currentItem()
        if item is None:
            return None
        return item.data(QtCore.Qt.UserRole)

    def _on_export(self):
        pfx = self._selected_prefix()
        if pfx is None:
            QtWidgets.QMessageBox.warning(
                self, "No Selection", "Select a character from the list to export."
            )
            return
        safe_name = pfx.replace(":", "_") if pfx != DEFAULT_PREFIX else "scene_snapshot"
        filepath, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export Snapshot — {}".format(pfx),
            safe_name + ".json",
            "JSON Files (*.json);;All Files (*)"
        )
        if filepath:
            RigSnapshot.export_prefix(pfx, filepath)
            QtWidgets.QMessageBox.information(
                self, "Exported",
                "Snapshot for '{}' exported to:\n{}".format(pfx, filepath)
            )

    def _on_import(self):
        filepath, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Import Snapshot",
            "", "JSON Files (*.json);;All Files (*)"
        )
        if not filepath:
            return
        prefix, snap = RigSnapshot.import_from_file(filepath)
        if prefix is not None:
            self._refresh_list()
            self.prefixes_changed.emit()
            QtWidgets.QMessageBox.information(
                self, "Imported",
                "Snapshot for '{}' imported ({} controls).".format(
                    prefix, len(snap.controls)
                )
            )

    def _on_delete(self):
        pfx = self._selected_prefix()
        if pfx is None:
            QtWidgets.QMessageBox.warning(
                self, "No Selection", "Select a character from the list to delete."
            )
            return
        result = QtWidgets.QMessageBox.question(
            self, "Delete Snapshot",
            "Delete the snapshot for '{}'?\n\n"
            "This cannot be undone.  Consider exporting first.".format(pfx),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
        )
        if result == QtWidgets.QMessageBox.Yes:
            RigSnapshot.delete_prefix(pfx)
            self._refresh_list()
            self.prefixes_changed.emit()


# ---------------------------------------------------------------------------
# DigetMirrorControl  (main dialog)
# ---------------------------------------------------------------------------

class DigetMirrorControl(QtWidgets.QDialog):

    dlg_instance             = None
    snapshot_editor_instance = None
    manual_pair_editor_instance = None
    snapshot_manager_instance = None

    @classmethod
    def show_dialog(cls):
        if not cls.dlg_instance:
            cls.dlg_instance = DigetMirrorControl()
        if cls.dlg_instance.isHidden():
            cls.dlg_instance.show()
        else:
            cls.dlg_instance.raise_()
            cls.dlg_instance.activateWindow()

    def __init__(self, parent=maya_main_window()):
        super().__init__(parent)
        self.setWindowTitle("digetMirrorControl  v2.2.5")
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
        self._refresh_prefix_combobox()
        self._refresh_snapshot_status()

    # ------------------------------------------------------------------
    # Menus
    # ------------------------------------------------------------------

    def _create_menus(self):
        self.menu_bar = QtWidgets.QMenuBar(self)

        # ---- File menu ----
        file_menu = self.menu_bar.addMenu("File")

        set_base_action = QtGui.QAction("Set Base Control", self)
        set_base_action.setToolTip(
            "Store the selected control as the reference base,\n"
            "along with the current L/R naming tokens, on the scene node."
        )
        set_base_action.triggered.connect(self.set_base_control)
        file_menu.addAction(set_base_action)

        # ---- Tools menu ----
        tools_menu = self.menu_bar.addMenu("Tools")

        take_snap_action = QtGui.QAction("  Take Snapshot", self)
        take_snap_action.setToolTip(
            "Sample selected (or all scene) controls at rest pose\n"
            "and store per-attribute mirror rules in the scene.\n\n"
            "If controls are selected, only those are sampled.\n"
            "If nothing is selected, every NURBS control is sampled."
        )
        take_snap_action.triggered.connect(self.take_snapshot)
        tools_menu.addAction(take_snap_action)

        edit_snap_action = QtGui.QAction("  Edit Snapshot Rules…", self)
        edit_snap_action.setToolTip(
            "Open the Snapshot Editor to review, override, or change\n"
            "per-attribute mirror rules (copy / negate / ignore)\n"
            "for every control in the stored snapshot."
        )
        edit_snap_action.triggered.connect(self.open_snapshot_editor)
        tools_menu.addAction(edit_snap_action)

        tools_menu.addSeparator()

        manual_action = QtGui.QAction("  Manual Pair Editor…", self)
        manual_action.setToolTip(
            "Open the Manual Pair Editor to assign mirror partners for\n"
            "controls the auto-pairing heuristic cannot resolve,\n"
            "and to exclude rig-internal controls from mirroring."
        )
        manual_action.triggered.connect(self.open_manual_pair_editor)
        tools_menu.addAction(manual_action)

        tools_menu.addSeparator()

        flip_sign_action = QtGui.QAction("±  Flip Sign Rules (Selected)", self)
        flip_sign_action.setToolTip(
            "Toggle copy ↔ negate for all transform attributes\n"
            "on the currently selected controls.\n\n"
            "Use this when a control mirrors with the wrong sign\n"
            "due to how the rig was built (e.g. negated axes on one side).\n"
            "Changes are saved to the snapshot immediately."
        )
        flip_sign_action.triggered.connect(self.flip_sign_rules)
        tools_menu.addAction(flip_sign_action)

        tools_menu.addSeparator()

        manage_action = QtGui.QAction("📋  Manage Character Snapshots…", self)
        manage_action.setToolTip(
            "View all stored character snapshots by prefix.\n"
            "Export snapshots to JSON for other scenes,\n"
            "import from JSON, or delete character data."
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

        about_action = QtGui.QAction("About digetMirrorControl", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    # ------------------------------------------------------------------
    # Widgets
    # ------------------------------------------------------------------

    def _make_icon_btn(self, icon_text, label, tooltip, obj_name=None):
        """Create a styled button with a unicode icon prefix."""
        btn = QtWidgets.QPushButton("{}  {}".format(icon_text, label))
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
            "  Not Selected — Process all except selected"
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
            "(Only applies when no snapshot is loaded.)"
        )

        self.preserve_rotation_cb = QtWidgets.QCheckBox("Preserve Rotation")
        self.preserve_rotation_cb.setChecked(True)
        self.preserve_rotation_cb.setToolTip(
            "If checked, rotation channels are copied exactly\n"
            "rather than negated.\n"
            "(Only applies when no snapshot is loaded.)"
        )

        # ---- Naming ----
        self.left_ctrl_name_le = QtWidgets.QLineEdit()
        self.left_ctrl_name_le.setPlaceholderText("lf")
        self.left_ctrl_name_le.setToolTip(
            "Left-side naming token used in the rig's control names.\n"
            "Example: 'lf' matches ac_lf_handIK\n"
            "Leave blank to use the default 'lf'."
        )
        self.right_ctrl_name_le = QtWidgets.QLineEdit()
        self.right_ctrl_name_le.setPlaceholderText("rt")
        self.right_ctrl_name_le.setToolTip(
            "Right-side naming token used in the rig's control names.\n"
            "Example: 'rt' matches ac_rt_handIK\n"
            "Leave blank to use the default 'rt'."
        )

        # ---- Mirror button ----
        self.mirror_btn = QtWidgets.QPushButton("⟳   Mirror")
        self.mirror_btn.setObjectName("mirrorBtn")
        self.mirror_btn.setToolTip(
            "Execute the mirror operation with the current settings.\n\n"
            "If controls are selected, only those are processed.\n"
            "If nothing is selected, all scene controls are mirrored."
        )

        # ---- Snapshot Tools ----
        self.take_snap_btn = self._make_icon_btn(
            "◉", "Take Snapshot",
            "Sample selected (or all) controls at rest pose and\n"
            "store per-attribute mirror rules in the scene.\n\n"
            "This must be done once per rig before the snapshot\n"
            "system can provide accurate mirroring.",
            "snapshotBtn"
        )
        self.edit_snap_btn = self._make_icon_btn(
            "✎", "Edit Rules",
            "Open the Snapshot Editor to review or override\n"
            "per-attribute mirror rules (copy / negate / ignore).",
            "snapshotBtn"
        )
        self.manual_pairs_btn = self._make_icon_btn(
            "⇌", "Manual Pairs",
            "Open the Manual Pair Editor to fix controls that\n"
            "the automatic name-matching could not resolve.\n\n"
            "Also lets you exclude rig-internal nodes that\n"
            "should never be mirrored.",
            "snapshotBtn"
        )
        self.flip_sign_btn = self._make_icon_btn(
            "±", "Flip Sign",
            "Toggle copy ↔ negate for all transform attributes\n"
            "on the currently selected controls.\n\n"
            "Use when a control mirrors with the wrong sign due\n"
            "to how the rig was built (e.g. negated axes on one side).\n"
            "Changes are saved to the snapshot immediately.",
            "flipSignBtn"
        )

        # ---- Character prefix selector ----
        self.prefix_cb = QtWidgets.QComboBox()
        self.prefix_cb.setToolTip(
            "Select which character rig's snapshot to use for mirroring.\n\n"
            "Auto-detected from selection when taking a snapshot.\n"
            "Each character namespace gets its own stored snapshot."
        )
        self.manage_snaps_btn = self._make_icon_btn(
            "📋", "Manage",
            "Open the Snapshot Manager to view, export,\nimport, or delete character snapshots.",
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
        snap_grp = QtWidgets.QGroupBox("Snapshot Tools")
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
        prefix_row.addWidget(self.manage_snaps_btn)
        snap_lay.addLayout(prefix_row)

        snap_btn_row1 = QtWidgets.QHBoxLayout()
        snap_btn_row1.addWidget(self.take_snap_btn)
        snap_btn_row1.addWidget(self.edit_snap_btn)
        snap_btn_row1.addWidget(self.manual_pairs_btn)
        snap_lay.addLayout(snap_btn_row1)

        snap_btn_row2 = QtWidgets.QHBoxLayout()
        snap_btn_row2.addWidget(self.flip_sign_btn)
        snap_btn_row2.addStretch()
        snap_lay.addLayout(snap_btn_row2)

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
        self.take_snap_btn.clicked.connect(self.take_snapshot)
        self.edit_snap_btn.clicked.connect(self.open_snapshot_editor)
        self.manual_pairs_btn.clicked.connect(self.open_manual_pair_editor)
        self.flip_sign_btn.clicked.connect(self.flip_sign_rules)
        self.prefix_cb.currentTextChanged.connect(self._on_prefix_changed)
        self.manage_snaps_btn.clicked.connect(self.open_snapshot_manager)

    # ------------------------------------------------------------------
    # Prefix management
    # ------------------------------------------------------------------

    def get_active_prefix(self):
        """Return the currently selected character prefix, or None."""
        txt = self.prefix_cb.currentText()
        if not txt or txt == "(none)":
            return None
        return txt

    def _refresh_prefix_combobox(self):
        """Re-populate the prefix combobox from stored snapshots."""
        old = self.prefix_cb.currentText()
        self.prefix_cb.blockSignals(True)
        self.prefix_cb.clear()

        prefixes = RigSnapshot.list_prefixes()
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

        self.prefix_cb.blockSignals(False)
        self._active_prefix = self.get_active_prefix()

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
        result = []
        for ctrl in all_ctrls:
            p = _detect_prefix(ctrl)
            if p == prefix:
                result.append(ctrl)
        return result

    def open_snapshot_manager(self):
        """Open the Snapshot Manager dialog."""
        cls = DigetMirrorControl
        if cls.snapshot_manager_instance and not cls.snapshot_manager_instance.isHidden():
            cls.snapshot_manager_instance.raise_()
            cls.snapshot_manager_instance.activateWindow()
            cls.snapshot_manager_instance._refresh_list()
        else:
            cls.snapshot_manager_instance = SnapshotManagerDialog(parent=self)
            cls.snapshot_manager_instance.prefixes_changed.connect(
                self._refresh_prefix_combobox
            )
            cls.snapshot_manager_instance.prefixes_changed.connect(
                self._refresh_snapshot_status
            )
            cls.snapshot_manager_instance.show()

    # ------------------------------------------------------------------
    # Snapshot — take & edit
    # ------------------------------------------------------------------

    def take_snapshot(self):
        """
        Sample selected (or all scene) controls and build + save a snapshot.

        Prefix auto-detection:
        - If one or more controls are selected, the namespace prefix is
          detected from the first selected control. All NURBS controls
          sharing that namespace are then included in the snapshot.
        - If nothing is selected, all scene controls are sampled and
          grouped by their detected prefix.
        """
        left_token   = self.get_left_name()
        right_token  = self.get_right_name()
        mirror_axis  = self.get_mirror_axis()

        sel = cmds.ls(selection=True, long=True)
        if sel:
            # Detect prefix from first selected control
            prefix = _detect_prefix(sel[0])

            # Expand to ALL controls sharing that prefix
            ctrl_list = self._get_controls_for_prefix(prefix)
            if not ctrl_list:
                ctrl_list = sel  # fallback: just use what's selected

            om.MGlobal.displayInfo(
                "[digetMirrorControl] Taking snapshot for '{}' — "
                "{} controls…".format(prefix, len(ctrl_list))
            )
        else:
            # No selection — use active prefix if one is set, otherwise scan all
            active = self._active_prefix or self.get_active_prefix()
            if active and active != DEFAULT_PREFIX:
                prefix = active
                ctrl_list = self._get_controls_for_prefix(prefix)
            else:
                ctrl_list = self._get_all_nurbs_controls()

            if not ctrl_list:
                om.MGlobal.displayError(
                    "[digetMirrorControl] No NURBS controls found in scene."
                )
                return

            if not active or active == DEFAULT_PREFIX:
                # Detect prefix from the controls
                prefix = DEFAULT_PREFIX
                for c in ctrl_list:
                    p = _detect_prefix(c)
                    if p != DEFAULT_PREFIX:
                        prefix = p
                        break
                # Re-filter to just this prefix to avoid mixing characters
                filtered = self._get_controls_for_prefix(prefix)
                if filtered:
                    ctrl_list = filtered

            om.MGlobal.displayInfo(
                "[digetMirrorControl] Taking snapshot for '{}' — "
                "{} scene controls…".format(prefix, len(ctrl_list))
            )

        snap = RigSnapshot.build(ctrl_list, left_token, right_token, mirror_axis)

        # --- Overwrite guard ---
        existing = RigSnapshot.load_from_scene(prefix)
        if existing is not None:
            n_existing = len(existing.controls)
            n_new      = len(snap.controls)
            is_subset  = n_new < n_existing

            msg = (
                "A snapshot already exists with {} controls.\n"
                "You are about to snapshot {} control{}.\n\n"
                "Replace  —  discard existing snapshot entirely.\n"
                "Merge    —  update only these {} control{}, keep the rest.\n"
                "Cancel   —  abort."
            ).format(
                n_existing,
                n_new, "s" if n_new != 1 else "",
                n_new, "s" if n_new != 1 else "",
            )

            replace_btn = QtWidgets.QPushButton("Replace")
            merge_btn   = QtWidgets.QPushButton("Merge")
            cancel_btn  = QtWidgets.QPushButton("Cancel")

            box = QtWidgets.QMessageBox(self)
            box.setWindowTitle("Snapshot Already Exists")
            box.setText(msg)
            box.addButton(replace_btn, QtWidgets.QMessageBox.AcceptRole)
            box.addButton(merge_btn,   QtWidgets.QMessageBox.ActionRole)
            box.addButton(cancel_btn,  QtWidgets.QMessageBox.RejectRole)
            if is_subset:
                box.setDefaultButton(merge_btn)
            else:
                box.setDefaultButton(replace_btn)
            box.exec()

            clicked = box.clickedButton()
            if clicked is cancel_btn:
                return
            elif clicked is merge_btn:
                snap = RigSnapshot.merge_into_scene(snap, prefix)
            else:
                snap.save_to_scene(prefix)
        else:
            snap.save_to_scene(prefix)

        self._active_prefix = prefix
        self._refresh_prefix_combobox()
        # Select the newly created prefix in the combobox
        label = prefix if prefix != DEFAULT_PREFIX else "(no namespace)"
        idx = self.prefix_cb.findText(label)
        if idx >= 0:
            self.prefix_cb.setCurrentIndex(idx)
        self._refresh_snapshot_status()

        # --- Analyse pairing results using shared helper ---
        unique_pairs, unpaired = self._analyse_snapshot_pairing(snap)
        n_unpaired = len(unpaired)

        # Build the post-snapshot message
        if n_unpaired == 0:
            msg = (
                "✔  All {} controls paired successfully  ({} pairs).\n\n"
                "Would you like to open the Snapshot Editor to review "
                "per-attribute mirror rules?".format(len(snap.controls), unique_pairs)
            )
            btns = QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
            box  = QtWidgets.QMessageBox(
                QtWidgets.QMessageBox.Information, "Snapshot Complete", msg, btns, self
            )
            box.setDefaultButton(QtWidgets.QMessageBox.No)
            if box.exec() == QtWidgets.QMessageBox.Yes:
                self._open_editor_with_snapshot(snap)

        else:
            # Show up to 10 unpaired names, then a count for the rest
            sample  = unpaired[:10]
            surplus = n_unpaired - len(sample)
            names   = "\n".join("  •  {}".format(n) for n in sample)
            if surplus > 0:
                names += "\n  … and {} more".format(surplus)

            msg = (
                "Snapshot saved — {} controls, {} pair{} found.\n\n"
                "⚠  {} control{} could not be automatically paired:\n\n"
                "{}\n\n"
                "These controls need manual partner assignment.\n"
                "Open the Manual Pairs editor now?".format(
                    len(snap.controls),
                    unique_pairs, "s" if unique_pairs != 1 else "",
                    n_unpaired,   "s" if n_unpaired   != 1 else "",
                    names,
                )
            )
            open_manual_btn    = QtWidgets.QPushButton("Open Manual Pairs…")
            open_snapshot_btn  = QtWidgets.QPushButton("Open Snapshot Editor…")
            dismiss_btn        = QtWidgets.QPushButton("Dismiss")

            box = QtWidgets.QMessageBox(
                QtWidgets.QMessageBox.Warning, "Snapshot — Pairing Issues", msg, parent=self
            )
            box.addButton(open_manual_btn,   QtWidgets.QMessageBox.AcceptRole)
            box.addButton(open_snapshot_btn, QtWidgets.QMessageBox.ActionRole)
            box.addButton(dismiss_btn,       QtWidgets.QMessageBox.RejectRole)
            box.setDefaultButton(open_manual_btn)
            box.exec()

            clicked = box.clickedButton()
            if clicked is open_manual_btn:
                self.open_manual_pair_editor()
            elif clicked is open_snapshot_btn:
                self._open_editor_with_snapshot(snap)

    def open_snapshot_editor(self):
        """Open the editor for the active prefix's snapshot."""
        prefix = self._active_prefix or self.get_active_prefix()
        snap = RigSnapshot.load_from_scene(prefix)
        if snap is None:
            result = QtWidgets.QMessageBox.question(
                self,
                "No Snapshot",
                "No snapshot found{}.\n"
                "Would you like to take one now?".format(
                    " for '{}'".format(prefix) if prefix and prefix != DEFAULT_PREFIX else ""
                ),
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            )
            if result == QtWidgets.QMessageBox.Yes:
                self.take_snapshot()
            return
        self._open_editor_with_snapshot(snap, prefix)

    def open_manual_pair_editor(self):
        """Open the Manual Pair Editor window."""
        cls = DigetMirrorControl
        if cls.manual_pair_editor_instance and not cls.manual_pair_editor_instance.isHidden():
            cls.manual_pair_editor_instance.raise_()
            cls.manual_pair_editor_instance.activateWindow()
            cls.manual_pair_editor_instance._on_refresh()
        else:
            prefix = self._active_prefix or self.get_active_prefix()
            cls.manual_pair_editor_instance = ManualPairEditorDialog(
                main_dialog=self,
                prefix=prefix,
                parent=self,
            )
            cls.manual_pair_editor_instance.show()

    def _open_editor_with_snapshot(self, snap, prefix=None):
        cls = DigetMirrorControl
        if cls.snapshot_editor_instance and not cls.snapshot_editor_instance.isHidden():
            cls.snapshot_editor_instance.update_snapshot(snap)
            cls.snapshot_editor_instance._prefix = prefix
            cls.snapshot_editor_instance.raise_()
            cls.snapshot_editor_instance.activateWindow()
        else:
            cls.snapshot_editor_instance = SnapshotEditorDialog(
                snap,
                re_snapshot_callback=self._do_re_snapshot,
                parent=self,
            )
            cls.snapshot_editor_instance._prefix = prefix
            cls.snapshot_editor_instance.show()

    def _do_re_snapshot(self):
        """Callback used by the SnapshotEditorDialog to re-build the snapshot."""
        left_token  = self.get_left_name()
        right_token = self.get_right_name()
        mirror_axis = self.get_mirror_axis()
        prefix      = self._active_prefix or self.get_active_prefix()

        sel = cmds.ls(selection=True, long=True)
        if sel:
            prefix = _detect_prefix(sel[0])
            ctrl_list = self._get_controls_for_prefix(prefix)
            if not ctrl_list:
                ctrl_list = sel
        else:
            # No selection — re-snapshot the active prefix's controls only
            if prefix:
                ctrl_list = self._get_controls_for_prefix(prefix)
            else:
                ctrl_list = self._get_all_nurbs_controls()

        if not ctrl_list:
            om.MGlobal.displayError("[digetMirrorControl] No controls found for re-snapshot.")
            return None
        snap = RigSnapshot.build(ctrl_list, left_token, right_token, mirror_axis)
        snap.save_to_scene(prefix)
        self._refresh_prefix_combobox()
        self._refresh_snapshot_status()
        # Report any newly unpaired controls in the Script Editor
        _, unpaired = self._analyse_snapshot_pairing(snap)
        if unpaired:
            om.MGlobal.displayWarning(
                "[digetMirrorControl] Re-snapshot: {} control{} still unpaired: {}".format(
                    len(unpaired),
                    "s" if len(unpaired) != 1 else "",
                    ", ".join(unpaired[:20]),
                )
            )
        return snap

    def _analyse_snapshot_pairing(self, snap):
        """
        Inspect snap and return (paired_count, unpaired_leaves).
        paired_count  : int   — number of unique confirmed pairs
        unpaired_leaves : list of str — leaf names with no valid partner
        """
        paired   = set()
        unpaired = []

        for ctrl_key, ctrl_data in snap.controls.items():
            leaf = ctrl_key.split("|")[-1]
            side = ctrl_data.get("side", "middle")

            if side == "middle":
                continue

            # Avoid reporting both directions as unpaired
            if leaf in paired:
                continue

            auto_partner = ctrl_data.get("partner")
            manual       = snap.get_manual_partner(ctrl_key)
            partner      = manual or auto_partner

            if partner and cmds.objExists(partner):
                partner_leaf = partner.split("|")[-1]
                paired.add(leaf)
                paired.add(partner_leaf)
            else:
                unpaired.append(leaf)

        unique_pairs = len(paired) // 2
        return unique_pairs, unpaired

    def _refresh_snapshot_status(self):
        prefix = self._active_prefix or self.get_active_prefix()
        snap = RigSnapshot.load_from_scene(prefix) if prefix else RigSnapshot.load_from_scene()
        if snap is None:
            self.snapshot_status_label.setText(
                "<span style='color:#888888;'>⚠  No snapshot — using axis heuristic</span>"
            )
        else:
            n_ctrls = len(snap.controls)
            n_pairs = sum(
                1 for d in snap.controls.values()
                if d.get("partner") and d.get("side") == "left"
                   and snap.controls.get(d["partner"]) is not None
            )
            pfx_label = prefix if prefix and prefix != DEFAULT_PREFIX else "(scene)"
            self.snapshot_status_label.setText(
                "<span style='color:#80c080;'>✔  <b>{}</b> — "
                "{} controls, {} pairs  (axis: {})</span>".format(
                    pfx_label, n_ctrls, n_pairs, snap.mirror_axis
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

    def get_controllers(self, side_con=None, prefix=None):
        left_token  = self.get_left_name()
        right_token = self.get_right_name()
        # Filter by prefix when specified to avoid mixing characters
        if prefix:
            all_ctrls = self._get_controls_for_prefix(prefix)
        else:
            all_ctrls = self._get_all_nurbs_controls()
        left_ctrls  = []
        right_ctrls = []
        middle_ctrls = []
        for ctrl in all_ctrls:
            has_lt = _has_side_token(ctrl, left_token)
            has_rt = _has_side_token(ctrl, right_token)
            if has_lt and not has_rt:
                left_ctrls.append(ctrl)
            elif has_rt and not has_lt:
                right_ctrls.append(ctrl)
            else:
                middle_ctrls.append(ctrl)

        pair_dict    = {"controls": {}, "pairNumber": {}}
        pair_number  = 0
        paired_left  = []
        paired_right = []
        for l in left_ctrls:
            l_name = l.split(":")[-1].lower()
            root   = l_name.replace(left_token.lower(), "")
            found  = False
            for r in right_ctrls:
                r_name = r.split(":")[-1].lower()
                if root and root in r_name:
                    pair_dict["controls"][l] = pair_number
                    pair_dict["controls"][r] = pair_number
                    pair_dict["pairNumber"][pair_number] = [l, r]
                    paired_left.append(l)
                    paired_right.append(r)
                    pair_number += 1
                    found = True
                    break
            if not found:
                middle_ctrls.append(l)
        for r in right_ctrls:
            if r not in paired_right:
                middle_ctrls.append(r)

        return {
            "left":   left_ctrls,
            "right":  right_ctrls,
            "middle": middle_ctrls,
            "all":    list(set(all_ctrls)),
            "pair":   pair_dict,
        }

    # ------------------------------------------------------------------
    # Axis vector helpers  (retained for heuristic fallback)
    # ------------------------------------------------------------------

    def get_vectors_dominating_axis(self, vector):
        denominator = sum(abs(val) for val in vector)
        pct         = [abs(val) / denominator for val in vector]
        index       = pct.index(max(pct))
        labels      = ["X", "Y", "Z"]
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
            wm = cmds.xform(ctrl, matrix=True, worldSpace=True, query=True)
            wm = [round(v, 3) for v in wm]
            vector_dict[ctrl] = {
                "x_axis": wm[0:3],
                "y_axis": wm[4:7],
                "z_axis": wm[8:11],
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
            attributes = cmds.listAttr(ctrl, keyable=True, unlocked=True)
            if attributes:
                for attr in attributes:
                    value = cmds.getAttr("{}.{}".format(ctrl, attr))
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
            if cmds.listAttr("{}.rotate{}".format(ctrl, ax), keyable=True, unlocked=True):
                self.set_attr("{}.rotate{}".format(ctrl, ax), 0)
        if auto_key:
            cmds.autoKeyframe(state=True)

    def rotate_ctrl_to_data(self, ctrl, data):
        auto_key = cmds.autoKeyframe(state=True, query=True)
        if auto_key:
            cmds.autoKeyframe(state=False)
        for ax in ["X", "Y", "Z"]:
            key = "rotate{}".format(ax)
            if key in data[ctrl]:
                self.set_attr("{}.{}".format(ctrl, key), data[ctrl][key])
        if auto_key:
            cmds.autoKeyframe(state=True)

    def get_partner(self, ctrl, left_token, right_token, snapshot=None):
        """
        Return the mirror partner name for ctrl.

        Priority order:
          1.  Manual pair stored in snapshot.manual_pairs  (user-defined)
          2.  Token-swap heuristic on the leaf node name   (automatic)

        Handles full DAG paths (parent|child) by stripping to the leaf node
        name before doing the token swap.  Returns a namespace-qualified
        short name that Maya can resolve unambiguously.

        Uses word-boundary-aware matching so tokens embedded in words
        (e.g. "rt" inside "shirt") are not falsely swapped.
        """
        # 1. Check manual pairs in snapshot
        if snapshot is not None:
            manual = snapshot.get_manual_partner(ctrl)
            if manual:
                return manual

        # 2. Token-swap on leaf name
        leaf = ctrl.split("|")[-1]

        if ":" in leaf:
            ns, base = leaf.rsplit(":", 1)
            ns_prefix = ns + ":"
        else:
            ns_prefix = ""
            base = leaf

        swapped = _swap_side_token(base, left_token, right_token)
        if swapped is None:
            return None
        return ns_prefix + swapped

    # ------------------------------------------------------------------
    # mirror_pair  — snapshot-aware
    # ------------------------------------------------------------------

    def mirror_pair(self, ctrl, partner, data, vector_data, mirror_axis, snapshot=None):
        """
        Copy / negate attributes from ctrl to partner.

        If a snapshot is supplied and contains an entry for ctrl, each attribute's
        stored rule is used directly (copy / negate / ignore).  User overrides in
        the editor are also honoured here.

        If the snapshot has no entry for the attribute — or no snapshot at all —
        the original axis-vector heuristic runs as a fallback.
        """
        if ctrl not in vector_data or partner not in vector_data:
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

        for attr, value in data[ctrl].items():
            target = "{}.{}".format(partner, attr)

            # --- Snapshot path ---
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

    # ------------------------------------------------------------------
    # mirror_control  — main entry point
    # ------------------------------------------------------------------

    def mirror_control(self):
        cmds.undoInfo(openChunk=True)

        left_token  = self.get_left_name()
        right_token = self.get_right_name()
        mirror_axis = self.get_mirror_axis()
        op          = self.get_operation()

        # Load snapshot for the appropriate prefix.
        # Selection-mode: detect prefix from the first selected control.
        # Scene-mode: use the active prefix from the combobox.
        sel = cmds.ls(selection=True, long=True)
        if sel:
            prefix = _detect_prefix(sel[0])
        else:
            prefix = self._active_prefix or self.get_active_prefix()

        snapshot = RigSnapshot.load_from_scene(prefix) if prefix else RigSnapshot.load_from_scene()

        if sel:
            # ---- Selection mode ----
            # Build a leaf→DAG lookup from all NURBS controls so we can
            # resolve the short partner names returned by get_partner()
            # to unambiguous full DAG paths.  This avoids "More than one
            # object matches name" errors on rigs with deeply nested
            # finger chains where multiple nodes share the same leaf name.
            _all_ctrls = self._get_all_nurbs_controls()
            _sel_leaf_to_dag = {}
            for c in _all_ctrls:
                _sel_leaf_to_dag[c.split("|")[-1]] = c

            processed = set()
            for ctrl in sel:
                if ctrl in processed:
                    continue

                # Skip excluded controls
                if snapshot and snapshot.is_excluded(ctrl):
                    om.MGlobal.displayInfo(
                        "[digetMirrorControl] Skipping excluded control '{}'".format(ctrl)
                    )
                    continue

                partner = self.get_partner(ctrl, left_token, right_token, snapshot=snapshot)
                if not partner or not cmds.objExists(partner):
                    om.MGlobal.displayWarning(
                        "No valid partner found for '{}'".format(ctrl)
                    )
                    continue

                # Resolve partner to full DAG path
                partner = _sel_leaf_to_dag.get(partner, _resolve_long(partner))

                processed.add(ctrl)
                # Check if partner is in selection (compare full paths)
                if partner in sel:
                    processed.add(partner)

                if op == OperationType.left_to_right:
                    if not _has_side_token(ctrl, left_token):
                        continue
                elif op == OperationType.right_to_left:
                    if not _has_side_token(ctrl, right_token):
                        continue
                elif op == OperationType.mirror_middle:
                    if _has_side_token(ctrl, left_token) or _has_side_token(ctrl, right_token):
                        continue
                elif op in (OperationType.flip, OperationType.flip_to_frame):
                    if op == OperationType.flip_to_frame:
                        self.set_time(self.get_flip_frame())

                vector_data = self.get_vector_data([ctrl, partner])
                data        = self.get_attribute_data([ctrl])
                self.mirror_pair(ctrl, partner, data, vector_data, mirror_axis, snapshot)

        else:
            # ---- Scene mode ----
            controls  = self.get_controllers([left_token, right_token], prefix=prefix)
            ctrl_list = controls["all"]

            if not ctrl_list:
                self.no_nurbs_in_scene()
                cmds.undoInfo(closeChunk=True)
                return

            # Filter out excluded controls before heavy processing
            if snapshot and snapshot.excluded_controls:
                ctrl_list = [
                    c for c in ctrl_list
                    if not snapshot.is_excluded(c)
                ]

            vector_data = self.get_vector_data(ctrl_list)
            data        = self.get_attribute_data(ctrl_list)

            # Build a leaf-name → full-DAG-path lookup so that partner names
            # returned by get_partner() (which are short namespace:name strings)
            # can be resolved to the full DAG paths used as keys in vector_data
            # and data.  Without this mapping, `partner not in vector_data`
            # always fails because the formats don't match.
            _leaf_to_dag = {}
            for c in ctrl_list:
                _leaf_to_dag[c.split("|")[-1]] = c

            def _resolve(partner_short):
                """Resolve short partner name to full DAG path, or return as-is."""
                if partner_short in vector_data:
                    return partner_short          # already a full path
                return _leaf_to_dag.get(partner_short, partner_short)

            if op == OperationType.left_to_right:
                valid = [c for c in ctrl_list if _has_side_token(c, left_token)]
                for ctrl in valid:
                    partner = self.get_partner(ctrl, left_token, right_token, snapshot=snapshot)
                    partner = _resolve(partner) if partner else None
                    if not partner or partner not in vector_data:
                        continue
                    self.mirror_pair(ctrl, partner, data, vector_data, mirror_axis, snapshot)

            elif op == OperationType.right_to_left:
                valid = [c for c in ctrl_list if _has_side_token(c, right_token)]
                for ctrl in valid:
                    partner = self.get_partner(ctrl, left_token, right_token, snapshot=snapshot)
                    partner = _resolve(partner) if partner else None
                    if not partner or partner not in vector_data:
                        continue
                    self.mirror_pair(ctrl, partner, data, vector_data, mirror_axis, snapshot)

            elif op in (OperationType.flip, OperationType.flip_to_frame):
                if op == OperationType.flip_to_frame:
                    self.set_time(self.get_flip_frame())
                for ctrl in ctrl_list:
                    partner = self.get_partner(ctrl, left_token, right_token, snapshot=snapshot)
                    partner = _resolve(partner) if partner else None
                    if not partner or partner not in vector_data:
                        continue
                    self.mirror_pair(ctrl, partner, data, vector_data, mirror_axis, snapshot)

            elif op == OperationType.mirror_middle:
                valid = [c for c in ctrl_list
                         if not _has_side_token(c, left_token) and
                            not _has_side_token(c, right_token)]
                for ctrl in valid:
                    for attr, value in data[ctrl].items():
                        if "translate" in attr:
                            if mirror_axis.upper() in attr:
                                self.set_attr("{}.{}".format(ctrl, attr), -value)
                            else:
                                self.set_attr("{}.{}".format(ctrl, attr), value)
                        elif "rotate" in attr:
                            self.set_attr("{}.{}".format(ctrl, attr), -value)
                        else:
                            self.set_attr("{}.{}".format(ctrl, attr), value)

            else:   # Selected (default) / Left to Right fallback
                valid = [c for c in ctrl_list if _has_side_token(c, left_token)]
                for ctrl in valid:
                    partner = self.get_partner(ctrl, left_token, right_token, snapshot=snapshot)
                    partner = _resolve(partner) if partner else None
                    if not partner or partner not in vector_data:
                        continue
                    self.mirror_pair(ctrl, partner, data, vector_data, mirror_axis, snapshot)

        cmds.undoInfo(closeChunk=True)

    # ------------------------------------------------------------------
    # Scene-node helpers
    # ------------------------------------------------------------------

    def set_base_control(self):
        sel = cmds.ls(selection=True)
        if not sel:
            om.MGlobal.displayError("Please select a base control before using 'Set Base Control'.")
            return
        base_ctrl = sel[0]
        node      = SNAPSHOT_NODE
        if not cmds.objExists(node):
            node = cmds.createNode("transform", name=node)
            cmds.setAttr("{}.visibility".format(node), 0)
        for attr, val in [("baseControl",  base_ctrl),
                          ("leftToken",    self.get_left_name()),
                          ("rightToken",   self.get_right_name())]:
            if not cmds.attributeQuery(attr, node=node, exists=True):
                cmds.addAttr(node, longName=attr, dataType="string")
            cmds.setAttr("{}.{}".format(node, attr), val, type="string")
        om.MGlobal.displayInfo(
            "Base control and naming tokens stored on node '{}'.".format(node)
        )

    def no_nurbs_in_scene(self):
        om.MGlobal.displayError("Couldn't find nurbsCurve or nurbsSurface in scene.")

    # ------------------------------------------------------------------
    # Flip Sign Rules
    # ------------------------------------------------------------------

    def flip_sign_rules(self):
        """
        Toggle copy ↔ negate for all transform attributes on the currently
        selected controls.  Useful when a control mirrors with the wrong sign
        due to how the rig was built (e.g. negated axes on one side).

        Requires a snapshot to be present. Changes are saved immediately.
        """
        sel = cmds.ls(selection=True, long=True)
        if not sel:
            QtWidgets.QMessageBox.warning(
                self, "Nothing Selected",
                "Please select one or more rig controls in the Maya viewport\n"
                "whose mirror sign you want to reverse, then try again."
            )
            return

        prefix = _detect_prefix(sel[0])
        snap = RigSnapshot.load_from_scene(prefix)
        if snap is None:
            QtWidgets.QMessageBox.warning(
                self, "No Snapshot",
                "No snapshot found for '{}'.\n\n"
                "Use  ◉ Take Snapshot  first, then try again.".format(prefix)
            )
            return

        flipped = []
        for ctrl in sel:
            leaf = ctrl.split("|")[-1]
            ctrl_data = snap.controls.get(leaf)
            if ctrl_data is None:
                continue
            attrs = ctrl_data.get("attributes", {})
            changed = False
            for attr_name, attr_info in attrs.items():
                rule = attr_info.get("rule", RULE_COPY)
                if rule == RULE_COPY:
                    attr_info["rule"] = RULE_NEGATE
                    attr_info["user_override"] = True
                    changed = True
                elif rule == RULE_NEGATE:
                    attr_info["rule"] = RULE_COPY
                    attr_info["user_override"] = True
                    changed = True
                # RULE_IGNORE stays ignored
            if changed:
                flipped.append(leaf.split(":")[-1] if ":" in leaf else leaf)

        if flipped:
            snap.save_to_scene(prefix)
            self._refresh_snapshot_status()
            om.MGlobal.displayInfo(
                "[digetMirrorControl] Flipped sign rules for {} control{}: {}".format(
                    len(flipped), "s" if len(flipped) != 1 else "",
                    ", ".join(flipped[:15]) + ("…" if len(flipped) > 15 else "")
                )
            )
            QtWidgets.QMessageBox.information(
                self, "Sign Rules Flipped",
                "Toggled copy ↔ negate on {} control{}:\n\n{}{}".format(
                    len(flipped), "s" if len(flipped) != 1 else "",
                    "\n".join("  •  {}".format(n) for n in flipped[:20]),
                    "\n  … and {} more".format(len(flipped) - 20) if len(flipped) > 20 else "",
                )
            )
        else:
            QtWidgets.QMessageBox.information(
                self, "No Changes",
                "None of the selected controls were found in the snapshot.\n\n"
                "Make sure you have taken a snapshot that includes these controls."
            )

    # ------------------------------------------------------------------
    # Help
    # ------------------------------------------------------------------

    def show_help(self):
        help_text = (
            "<h3>digetMirrorControl — How To Use</h3>"
            "<hr>"

            "<h4>① Quick Start — Mirror a Pose</h4>"
            "<ol>"
            "<li>Select the rig controls you want to mirror (or leave the selection "
            "empty to process all controls in the scene).</li>"
            "<li>Choose the <b>Operation</b> (e.g. Left to Right, Flip, Selected).</li>"
            "<li>Click the <b>⟳ Mirror</b> button.</li>"
            "</ol>"

            "<h4>② Snapshot System (Recommended)</h4>"
            "<p>The snapshot system gives more accurate results than the default "
            "axis-vector heuristic by storing per-attribute rules for every control.</p>"
            "<ol>"
            "<li>Pose the rig at its <b>rest / bind pose</b> (all controls zeroed).</li>"
            "<li>Click <b>◉ Take Snapshot</b> — this samples every control and "
            "assigns default copy/negate/ignore rules.</li>"
            "<li>The snapshot is stored in the Maya scene file and persists across saves.</li>"
            "</ol>"

            "<h4>③ Editing Snapshot Rules</h4>"
            "<p>Click <b>✎ Edit Rules</b> to open the Snapshot Editor.  Each attribute "
            "on each control has a dropdown (copy / negate / ignore).  Changes are "
            "written back when you click <b>Save to Scene</b>.</p>"

            "<h4>④ Manual Pair Editor</h4>"
            "<p>If the automatic name-matching cannot find a mirror partner for a control "
            "(e.g. the rig uses non-standard naming), open the <b>⇌ Manual Pairs</b> editor.</p>"
            "<ul>"
            "<li>Select a control in the Maya viewport, then click <b>⊕ Src</b> or <b>⊕ Prt</b> "
            "to assign it as source or partner.</li>"
            "<li>Use <b>Exclude</b> to permanently skip internal rig nodes.</li>"
            "<li>Click <b>Save to Scene</b> to persist your assignments.</li>"
            "</ul>"

            "<h4>⑤ Flip Sign Rules</h4>"
            "<p>If a control mirrors with the <b>wrong sign</b> (values are positive when "
            "they should be negative, or vice versa) due to how the rig was built:</p>"
            "<ol>"
            "<li>Select the problematic control(s) in the Maya viewport.</li>"
            "<li>Click <b>± Flip Sign</b> — this toggles all copy ↔ negate rules "
            "for those controls.</li>"
            "<li>Changes are saved to the snapshot immediately.</li>"
            "</ol>"

            "<h4>⑥ Per-Character Snapshots</h4>"
            "<p>Snapshots are stored <b>per character rig</b>, keyed by namespace prefix "
            "(e.g. <tt>ProRigs_Chris_v01_10_L</tt>).  Multiple rigs in one scene each "
            "get their own independent snapshot data.</p>"
            "<ul>"
            "<li><b>Auto-detection:</b> when you select any controller and click "
            "Take Snapshot, the tool detects the namespace from your selection and "
            "automatically expands to capture <i>all</i> controls sharing that namespace.</li>"
            "<li><b>Character dropdown:</b> use the <b>Character</b> combobox in the "
            "Snapshot Tools section to switch between stored character rigs.</li>"
            "<li><b>Manage:</b> click <b>📋 Manage</b> (or Tools &gt; Manage Character "
            "Snapshots) to export snapshots as <tt>.json</tt> files, import them into "
            "other scenes, or delete character data you no longer need.</li>"
            "<li><b>Legacy migration:</b> if you open a scene with an older single-snapshot "
            "format, it is automatically migrated to the new per-character system on first "
            "access — no action needed.</li>"
            "</ul>"

            "<h4>⑦ Naming Convention</h4>"
            "<p>The tool detects left/right controls by looking for naming tokens "
            "as delimited segments in the control name (separated by underscores).</p>"
            "<p>Default tokens: <b>lf</b> and <b>rt</b><br>"
            "Example: <tt>ac_<b>lf</b>_handIK</tt> ↔ <tt>ac_<b>rt</b>_handIK</tt></p>"
            "<p>If your rig uses different tokens (e.g. <tt>L</tt> / <tt>R</tt>), "
            "type them in the Naming Convention fields.</p>"

            "<h4>⑧ Preserve Translation / Rotation</h4>"
            "<p>These checkboxes only apply when <b>no snapshot</b> is loaded.  "
            "When checked, the corresponding channels are copied exactly rather "
            "than being negated by the axis heuristic.</p>"
        )
        box = QtWidgets.QMessageBox(self)
        box.setWindowTitle("How To Use — digetMirrorControl")
        box.setTextFormat(QtCore.Qt.RichText)
        box.setText(help_text)
        box.setStandardButtons(QtWidgets.QMessageBox.Ok)
        box.exec()

    # ------------------------------------------------------------------
    # About
    # ------------------------------------------------------------------

    def show_about(self):
        about_text = (
            "<h3>digetMirrorControl</h3>"
            "<p style='color:#8ab4f8;'>Version 2.2.5</p>"
            "<hr>"

            "<h4>Contributors</h4>"
            "<table cellpadding='2'>"
            "<tr><td style='color:#90c890;'>Original Author:</td>"
            "<td>Mikkel Diget Eriksen (2022)</td></tr>"
            "<tr><td style='color:#90c890;'>Updated by:</td>"
            "<td>David Shepstone</td></tr>"
            "</table>"

            "<h4>What's New in 2.2.5</h4>"
            "<ul>"
            "<li><b>Per-character snapshots</b> — snapshot data is now stored per rig "
            "namespace prefix.  Multiple characters in one scene each get independent "
            "snapshots.  Select any one control to auto-detect and capture the full rig.  "
            "Export/import snapshots as JSON via the Snapshot Manager.</li>"
            "<li><b>± Flip Sign Rules</b> — toggle copy ↔ negate on selected controls "
            "when the rig mirrors with the wrong sign.</li>"
            "<li><b>Word-boundary token matching</b> — side tokens (lf/rt) are no "
            "longer falsely matched inside words like 'shirt' or 'upperteeth'.</li>"
            "<li><b>DAG path resolution</b> — fixed scene-mode and selection-mode "
            "failures on rigs with deeply nested controls (finger chains).</li>"
            "<li><b>Manual Pair Editor fixes</b> — Save to Scene and Exclude "
            "now correctly preserve all pending edits.</li>"
            "<li><b>Redesigned UI</b> — dark theme, organized sections, tooltips "
            "on every control, Help menu with full documentation.</li>"
            "</ul>"

            "<h4>Previous Highlights</h4>"
            "<ul>"
            "<li><b>v2.2.0</b> — Manual Pair Editor for per-rig partner overrides "
            "and control exclusions.</li>"
            "<li><b>v2.1.0</b> — Rig Snapshot system with per-attribute mirror rules "
            "(copy / negate / ignore) and the Snapshot Editor.</li>"
            "</ul>"

            "<p style='color:#888; font-size:10px;'>Python · PySide6 · Maya 2025+</p>"
        )
        box = QtWidgets.QMessageBox(self)
        box.setWindowTitle("About digetMirrorControl")
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
    mirror_control = DigetMirrorControl()
    mirror_control.show()
