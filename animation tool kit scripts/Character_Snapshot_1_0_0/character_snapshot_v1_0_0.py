#!/usr/bin/env python3
"""
character_snapshot_v1_0_0.py

Description:
    A standalone Animation Tool Kit utility for capturing, storing, and managing
    "Character Snapshots" of any rig referenced into a Maya scene.

    A Character Snapshot is a JSON-serialisable record describing every keyable
    control on a rig, its world-space axis orientation, its mirror partner, its
    side classification (left / right / middle) and arbitrary user metadata
    (rig name, description, mirror axis, custom categories).

    Snapshots are stored on a hidden scene node so they travel with the .ma /
    .mb file, and can also be exported to / imported from .json files for sharing
    between scenes.

    The tool is designed to act as a *registry* of rig information that other
    Animation Tool Kit tools can query at runtime — they do not need to ship
    their own rig-detection logic, they simply ask "what controls belong to
    'Chris_v01'?" and get an authoritative answer.

Public API (importable by other ATK tools):
    from character_snapshot_v1_0_0 import (
        CharacterSnapshot,
        list_prefixes,
        load_snapshot,
        get_controls_for,
        get_partner,
        get_side,
        is_excluded,
        rename_prefix,
    )

Install:
    Drag and drop the install_character_snapshot.mel file onto the Maya
    viewport. This copies this script and the snapshot.png icon into the
    user's Maya scripts / icons folder and adds a shelf button.

Author:
    David Shepstone

Version:
    1.0.0 - Initial release. Built on the rig-snapshot, manual-pair editor, and
            multi-prefix snapshot manager systems originally developed for
            digetMirrorControl v2.2.5 by Mikkel Diget Eriksen / David Shepstone.
            Fully independent — does not depend on the mirror tool being
            installed, and uses a separate scene node so the two tools can
            coexist without conflict.
"""

import json
import re
import datetime

from PySide6 import QtCore, QtGui, QtWidgets
from shiboken6 import wrapInstance

import maya.OpenMayaUI as omui
import maya.cmds as cmds
import maya.OpenMaya as om


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TOOL_NAME       = "Character Snapshot"
TOOL_VERSION    = "1.0.0"

SNAPSHOT_NODE   = "characterSnapshotData"
SNAPSHOT_ATTR   = "characterSnapshots"     # multi-prefix store
DEFAULT_PREFIX  = "__scene__"

SCHEMA_VERSION  = 1


# ---------------------------------------------------------------------------
# Naming / token helpers — these are intentionally identical in behaviour to
# the helpers used by digetMirrorControl so JSON files exported from the
# mirror tool can be imported here (and vice versa) without surprises.
# ---------------------------------------------------------------------------

def _detect_prefix(ctrl):
    """Return the namespace prefix of *ctrl* (e.g. 'Chris_v01') or DEFAULT_PREFIX."""
    leaf = ctrl.split("|")[-1]
    if ":" in leaf:
        return leaf.rsplit(":", 1)[0]
    return DEFAULT_PREFIX


def _swap_side_token(base_name, left_token, right_token):
    """
    Swap left/right tokens in *base_name* using word-boundary-aware matching.

    Returns the swapped name, or None if no token was found.
    Boundaries are '_' and string start/end so substrings inside other words
    (e.g. 'rt' inside 'shirt') are NOT matched.
    """
    lt = re.escape(left_token)
    rt = re.escape(right_token)

    def _boundary_pattern(tok):
        return r'(?:(?<=_)|(?<=\A))' + tok + r'(?=_|\Z)'

    pat_rt = _boundary_pattern(rt)
    m = re.search(pat_rt, base_name, re.IGNORECASE)
    if m:
        return base_name[:m.start()] + left_token + base_name[m.end():]

    pat_lt = _boundary_pattern(lt)
    m = re.search(pat_lt, base_name, re.IGNORECASE)
    if m:
        return base_name[:m.start()] + right_token + base_name[m.end():]

    return None


def _has_side_token(ctrl, token):
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


def _swap_prefix_in_name(name, old_prefix, new_prefix):
    """
    Replace the leading namespace portion of a control name.

    Handles full DAG paths (|root|Chris_v01:ac_lf_handIK) and short names
    alike, leaving the leaf base-name intact.

    Returns the rewritten name. If old_prefix is not present, returns the
    original name unchanged.
    """
    if old_prefix == new_prefix:
        return name
    leaf = name.split("|")[-1]
    if ":" not in leaf:
        # No namespace — only matches if old_prefix is DEFAULT_PREFIX
        if old_prefix == DEFAULT_PREFIX and new_prefix != DEFAULT_PREFIX:
            new_leaf = "{}:{}".format(new_prefix, leaf)
            parent   = name[:-len(leaf)] if len(leaf) < len(name) else ""
            return parent + new_leaf
        return name

    ns, base = leaf.rsplit(":", 1)
    if ns != old_prefix:
        return name
    if new_prefix == DEFAULT_PREFIX:
        new_leaf = base
    else:
        new_leaf = "{}:{}".format(new_prefix, base)
    parent = name[:-len(leaf)] if len(leaf) < len(name) else ""
    return parent + new_leaf


# ---------------------------------------------------------------------------
# Maya helpers
# ---------------------------------------------------------------------------

def maya_main_window():
    ptr = omui.MQtUtil.mainWindow()
    return wrapInstance(int(ptr), QtWidgets.QWidget)


def _get_all_nurbs_controls():
    """Return full DAG paths of all NURBS-curve transforms with keyable attrs."""
    all_shapes = cmds.ls(type="nurbsCurve") or []
    seen   = set()
    result = []
    for shape in all_shapes:
        parents = cmds.listRelatives(shape, parent=True, fullPath=True) or []
        for full_path in parents:
            if full_path in seen:
                continue
            try:
                if cmds.listAttr(full_path, keyable=True):
                    result.append(full_path)
                    seen.add(full_path)
            except Exception:
                pass
    return result


def _get_controls_for_prefix_in_scene(prefix):
    """All scene NURBS controls whose namespace matches *prefix*."""
    all_ctrls = _get_all_nurbs_controls()
    if prefix is None:
        return all_ctrls
    return [c for c in all_ctrls if _detect_prefix(c) == prefix]


# ---------------------------------------------------------------------------
# Dark stylesheet — visually consistent with the rest of the ATK toolset.
# ---------------------------------------------------------------------------

DARK_STYLESHEET = """
QDialog { background-color: #2b2b2b; color: #d4d4d4; font-size: 12px; }
QMenuBar { background-color: #333333; color: #d4d4d4; border-bottom: 1px solid #444444; padding: 2px 0px; }
QMenuBar::item:selected { background-color: #4a90d9; color: #ffffff; border-radius: 3px; }
QMenu { background-color: #353535; color: #d4d4d4; border: 1px solid #555555; padding: 4px; }
QMenu::item { padding: 5px 25px 5px 20px; }
QMenu::item:selected { background-color: #4a90d9; color: #ffffff; border-radius: 3px; }
QMenu::separator { height: 1px; background: #555555; margin: 4px 8px; }
QGroupBox {
    font-weight: bold; font-size: 11px;
    border: 1px solid #555555; border-radius: 6px;
    margin-top: 10px; padding: 14px 8px 8px 8px;
}
QGroupBox::title {
    subcontrol-origin: margin; subcontrol-position: top left;
    padding: 2px 10px; border-radius: 3px; left: 8px;
}
QLabel { color: #cccccc; }
QPushButton {
    background-color: #404040; color: #d4d4d4;
    border: 1px solid #555555; border-radius: 4px;
    padding: 5px 14px; min-height: 22px; font-size: 11px;
}
QPushButton:hover  { background-color: #505050; border-color: #6a6a6a; }
QPushButton:pressed { background-color: #353535; }
QPushButton:disabled { background-color: #333333; color: #666666; border-color: #444444; }
QPushButton#primaryBtn {
    background-color: #3a7abd; color: #ffffff; font-weight: bold;
    border: 1px solid #4a90d9; border-radius: 5px; min-height: 28px;
}
QPushButton#primaryBtn:hover { background-color: #4a90d9; }
QPushButton#snapshotBtn {
    background-color: #3a5a3a; color: #b0dab0; border: 1px solid #4a7a4a;
}
QPushButton#snapshotBtn:hover { background-color: #4a6a4a; border-color: #5a9a5a; }
QPushButton#dangerBtn {
    background-color: #5a2a2a; color: #e8a0a0; border: 1px solid #7a4040;
}
QPushButton#dangerBtn:hover { background-color: #6a3030; border-color: #9a5050; }
QComboBox, QLineEdit {
    background-color: #383838; color: #d4d4d4;
    border: 1px solid #555555; border-radius: 4px;
    padding: 4px 8px; min-height: 20px;
}
QComboBox:hover, QLineEdit:focus { border-color: #4a90d9; }
QComboBox::drop-down { border: none; width: 20px; }
QComboBox QAbstractItemView {
    background-color: #383838; color: #d4d4d4;
    selection-background-color: #4a90d9; border: 1px solid #555555;
}
QCheckBox { color: #cccccc; spacing: 6px; }
QCheckBox::indicator {
    width: 14px; height: 14px;
    border: 1px solid #666666; border-radius: 3px; background-color: #383838;
}
QCheckBox::indicator:checked { background-color: #4a90d9; border-color: #5a9ada; }
QListWidget, QTableWidget, QTreeWidget {
    background-color: #333333; color: #d4d4d4;
    border: 1px solid #555555; border-radius: 4px;
    alternate-background-color: #383838;
}
QListWidget::item, QTableWidget::item { padding: 4px 6px; }
QListWidget::item:selected, QTableWidget::item:selected { background-color: #4a90d9; color: #ffffff; }
QHeaderView::section {
    background-color: #3a3a3a; color: #d4d4d4;
    border: 0; border-right: 1px solid #2a2a2a;
    padding: 4px 8px;
}
QPlainTextEdit, QTextEdit {
    background-color: #2f2f2f; color: #d4d4d4;
    border: 1px solid #555555; border-radius: 4px;
    padding: 6px; font-family: monospace;
}
QToolTip {
    background-color: #404040; color: #e0e0e0;
    border: 1px solid #666666; border-radius: 3px;
    padding: 4px 8px;
}
QFrame#separator { background-color: #444444; max-height: 1px; }
"""


# ---------------------------------------------------------------------------
# CharacterSnapshot — core data class
# ---------------------------------------------------------------------------

class CharacterSnapshot(object):
    """
    A serialisable record describing a single character rig.

    Schema
    ------
    {
      "schema_version":  1,
      "prefix":          "Chris_v01",
      "rig_name":        "Chris",
      "description":     "Hero rig used for shot 010-040",
      "created":         "2026-04-27T10:30:00",
      "modified":        "2026-04-27T10:30:00",
      "left_token":      "lf",
      "right_token":     "rt",
      "mirror_axis":     "X",
      "controls": {
        "Chris_v01:ac_lf_handIK": {
          "side":           "left",
          "partner":        "Chris_v01:ac_rt_handIK",
          "category":       "arm",        # optional, user-assigned
          "dominant_axes":  {"x": "X",  "y": "Y",  "z": "Z"},
          "partner_dominant_axes": {"x": "-X", "y": "Y", "z": "Z"},
          "attributes":     ["translateX", "translateY", "rotateZ", ...]
        },
        ...
      },
      "manual_pairs":      {"src_leaf": "partner_leaf", ...},
      "excluded_controls": ["leaf1", "leaf2", ...],
      "categories":        {"arm": [...], "leg": [...], "spine": [...]},
      "metadata":          {}      # arbitrary user/tool data
    }
    """

    def __init__(self):
        self.prefix            = DEFAULT_PREFIX
        self.rig_name          = ""
        self.description       = ""
        self.created           = self._timestamp()
        self.modified          = self.created
        self.left_token        = "lf"
        self.right_token       = "rt"
        self.mirror_axis       = "X"
        self.controls          = {}
        self.manual_pairs      = {}
        self.excluded_controls = []
        self.categories        = {}
        self.metadata          = {}

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    @staticmethod
    def _timestamp():
        return datetime.datetime.now().isoformat(timespec="seconds")

    def to_dict(self):
        return {
            "schema_version":    SCHEMA_VERSION,
            "prefix":            self.prefix,
            "rig_name":          self.rig_name,
            "description":       self.description,
            "created":           self.created,
            "modified":          self.modified,
            "left_token":        self.left_token,
            "right_token":       self.right_token,
            "mirror_axis":       self.mirror_axis,
            "controls":          self.controls,
            "manual_pairs":      self.manual_pairs,
            "excluded_controls": self.excluded_controls,
            "categories":        self.categories,
            "metadata":          self.metadata,
        }

    @classmethod
    def from_dict(cls, d):
        snap                   = cls()
        snap.prefix            = d.get("prefix",            DEFAULT_PREFIX)
        snap.rig_name          = d.get("rig_name",          "")
        snap.description       = d.get("description",       "")
        snap.created           = d.get("created",           snap.created)
        snap.modified          = d.get("modified",          snap.created)
        snap.left_token        = d.get("left_token",        "lf")
        snap.right_token       = d.get("right_token",       "rt")
        snap.mirror_axis       = d.get("mirror_axis",       "X")
        snap.controls          = d.get("controls",          {})
        snap.manual_pairs      = d.get("manual_pairs",      {})
        snap.excluded_controls = d.get("excluded_controls", [])
        snap.categories        = d.get("categories",        {})
        snap.metadata          = d.get("metadata",          {})
        return snap

    # ------------------------------------------------------------------
    # Scene-node persistence
    # ------------------------------------------------------------------

    @staticmethod
    def _ensure_node():
        node = SNAPSHOT_NODE
        if not cmds.objExists(node):
            node = cmds.createNode("transform", name=node)
            cmds.setAttr("{}.visibility".format(node), 0)
        return node

    @classmethod
    def _load_store(cls):
        """Return the {prefix: snapshot_dict} store, or {} if none."""
        if not cmds.objExists(SNAPSHOT_NODE):
            return {}
        if not cmds.attributeQuery(SNAPSHOT_ATTR, node=SNAPSHOT_NODE, exists=True):
            return {}
        raw = cmds.getAttr("{}.{}".format(SNAPSHOT_NODE, SNAPSHOT_ATTR))
        if not raw:
            return {}
        try:
            store = json.loads(raw)
            if isinstance(store, dict):
                return store
        except Exception:
            pass
        return {}

    @classmethod
    def _save_store(cls, store):
        node = cls._ensure_node()
        if not cmds.attributeQuery(SNAPSHOT_ATTR, node=node, exists=True):
            cmds.addAttr(node, longName=SNAPSHOT_ATTR, dataType="string")
        cmds.setAttr(
            "{}.{}".format(node, SNAPSHOT_ATTR),
            json.dumps(store, indent=2),
            type="string",
        )

    def save_to_scene(self):
        """Write this snapshot to the scene store under self.prefix."""
        self.modified = self._timestamp()
        store = self._load_store()
        store[self.prefix] = self.to_dict()
        self._save_store(store)
        om.MGlobal.displayInfo(
            "[{}] Snapshot saved — '{}' ({} controls).".format(
                TOOL_NAME, self.prefix, len(self.controls)
            )
        )

    @classmethod
    def load_from_scene(cls, prefix):
        store = cls._load_store()
        data  = store.get(prefix)
        if data is None:
            return None
        try:
            return cls.from_dict(data)
        except Exception as exc:
            om.MGlobal.displayError(
                "[{}] Failed to load snapshot for '{}': {}".format(TOOL_NAME, prefix, exc)
            )
            return None

    @classmethod
    def list_prefixes(cls):
        return sorted(cls._load_store().keys())

    @classmethod
    def delete_prefix(cls, prefix):
        store = cls._load_store()
        if prefix in store:
            del store[prefix]
            cls._save_store(store)
            om.MGlobal.displayInfo(
                "[{}] Deleted snapshot '{}'.".format(TOOL_NAME, prefix)
            )
            return True
        return False

    # ------------------------------------------------------------------
    # JSON file import / export
    # ------------------------------------------------------------------

    def export_to_file(self, filepath):
        with open(filepath, "w") as f:
            json.dump(self.to_dict(), f, indent=2)
        om.MGlobal.displayInfo(
            "[{}] Exported '{}' to: {}".format(TOOL_NAME, self.prefix, filepath)
        )
        return True

    @classmethod
    def import_from_file(cls, filepath):
        """
        Import a snapshot JSON file. Accepts:
          - native CharacterSnapshot dicts (with 'schema_version')
          - digetMirrorControl-exported wrapped dicts: {'prefix': ..., 'snapshot': {...}}
          - raw mirror RigSnapshot dicts (no 'schema_version', has 'controls')

        Returns the CharacterSnapshot instance (NOT yet saved to scene), or None.
        """
        try:
            with open(filepath, "r") as f:
                file_data = json.load(f)
        except Exception as exc:
            om.MGlobal.displayError(
                "[{}] Failed to read JSON: {}".format(TOOL_NAME, exc)
            )
            return None

        # digetMirrorControl wrapped format
        if isinstance(file_data, dict) and "prefix" in file_data and "snapshot" in file_data \
                and "schema_version" not in file_data:
            mirror_prefix = file_data["prefix"]
            inner         = file_data["snapshot"]
            snap = cls._adopt_mirror_snapshot(inner, mirror_prefix)
        elif isinstance(file_data, dict) and "schema_version" in file_data:
            snap = cls.from_dict(file_data)
        elif isinstance(file_data, dict) and "controls" in file_data:
            # raw mirror RigSnapshot
            mirror_prefix = DEFAULT_PREFIX
            for ctrl_key in file_data.get("controls", {}):
                p = _detect_prefix(ctrl_key)
                if p != DEFAULT_PREFIX:
                    mirror_prefix = p
                    break
            snap = cls._adopt_mirror_snapshot(file_data, mirror_prefix)
        else:
            om.MGlobal.displayError(
                "[{}] Unrecognised snapshot file format.".format(TOOL_NAME)
            )
            return None

        return snap

    @classmethod
    def _adopt_mirror_snapshot(cls, mirror_dict, prefix):
        """Convert a digetMirrorControl RigSnapshot dict into a CharacterSnapshot."""
        snap            = cls()
        snap.prefix     = prefix
        snap.rig_name   = prefix.split(":")[-1] if prefix != DEFAULT_PREFIX else ""
        snap.left_token  = mirror_dict.get("left_token",  "lf")
        snap.right_token = mirror_dict.get("right_token", "rt")
        snap.mirror_axis = mirror_dict.get("mirror_axis", "X")

        # Down-convert the mirror schema's per-attribute dict into a flat list
        # of attribute names so the character snapshot stays compact.
        mc = mirror_dict.get("controls", {})
        for ctrl_key, ctrl_data in mc.items():
            attrs_payload = ctrl_data.get("attributes", {})
            if isinstance(attrs_payload, dict):
                attr_names = sorted(attrs_payload.keys())
            else:
                attr_names = list(attrs_payload)
            snap.controls[ctrl_key] = {
                "side":                  ctrl_data.get("side",    "middle"),
                "partner":               ctrl_data.get("partner", None),
                "category":              ctrl_data.get("category", ""),
                "dominant_axes":         ctrl_data.get("dominant_axes",         {}),
                "partner_dominant_axes": ctrl_data.get("partner_dominant_axes", {}),
                "attributes":            attr_names,
            }

        snap.manual_pairs      = dict(mirror_dict.get("manual_pairs", {}))
        snap.excluded_controls = list(mirror_dict.get("excluded_controls", []))
        snap.metadata["imported_from"] = "digetMirrorControl"
        return snap

    # ------------------------------------------------------------------
    # Building a snapshot from scene controls
    # ------------------------------------------------------------------

    @classmethod
    def build(cls, ctrl_list, prefix=None, rig_name="", description="",
              left_token="lf", right_token="rt", mirror_axis="X"):
        """
        Sample *ctrl_list* and build a CharacterSnapshot.

        Reads each control's world-space axis vectors at its current pose
        (rotations are temporarily zeroed for accurate axis sampling, then
        restored), classifies each as left / right / middle by token, and
        records every keyable / unlocked scalar attribute.
        """
        snap              = cls()
        snap.prefix       = prefix or DEFAULT_PREFIX
        snap.rig_name     = rig_name
        snap.description  = description
        snap.left_token   = left_token
        snap.right_token  = right_token
        snap.mirror_axis  = mirror_axis

        if snap.prefix == DEFAULT_PREFIX and ctrl_list:
            for c in ctrl_list:
                p = _detect_prefix(c)
                if p != DEFAULT_PREFIX:
                    snap.prefix = p
                    if not snap.rig_name:
                        snap.rig_name = p.split(":")[-1]
                    break

        classification = cls._classify(ctrl_list, left_token, right_token)
        vector_data    = cls._sample_axis_vectors(ctrl_list)

        for ctrl in ctrl_list:
            side    = classification.get(ctrl, "middle")
            partner = cls._find_partner(ctrl, left_token, right_token)
            if partner and not cmds.objExists(partner):
                partner = None

            vd  = vector_data.get(ctrl, {})
            pvd = vector_data.get(partner, {}) if partner else {}

            attr_names = []
            raw_attrs  = cmds.listAttr(ctrl, keyable=True, unlocked=True) or []
            for attr in raw_attrs:
                try:
                    val = cmds.getAttr("{}.{}".format(ctrl, attr))
                except Exception:
                    continue
                if isinstance(val, (int, float)):
                    attr_names.append(attr)

            snap.controls[ctrl] = {
                "side":                  side,
                "partner":               partner,
                "category":              "",
                "dominant_axes":         cls._dominant_axes(vd),
                "partner_dominant_axes": cls._dominant_axes(pvd),
                "attributes":            attr_names,
            }

        return snap

    # ------------------------------------------------------------------
    # Internal sampling / classification helpers
    # ------------------------------------------------------------------

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
        """Briefly zero each control's rotation to read clean world-axis vectors."""
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

        auto_key = cmds.autoKeyframe(state=True, query=True)
        if auto_key:
            cmds.autoKeyframe(state=False)
        for ctrl in ctrl_list:
            for ax in saved[ctrl]:
                try:
                    cmds.setAttr("{}.rotate{}".format(ctrl, ax), 0)
                except Exception:
                    pass

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
        if not vector or all(v == 0 for v in vector):
            return "X"
        denom = sum(abs(v) for v in vector)
        if denom == 0:
            return "X"
        pct  = [abs(v) / denom for v in vector]
        idx  = pct.index(max(pct))
        lab  = ["X", "Y", "Z"][idx]
        return ("-" + lab) if vector[idx] < 0 else lab

    @classmethod
    def _dominant_axes(cls, vd):
        if not vd:
            return {"x": "X", "y": "Y", "z": "Z"}
        return {
            "x": cls._dominant_axis_of(vd.get("x_axis", [1, 0, 0])),
            "y": cls._dominant_axis_of(vd.get("y_axis", [0, 1, 0])),
            "z": cls._dominant_axis_of(vd.get("z_axis", [0, 0, 1])),
        }

    # ------------------------------------------------------------------
    # Manual pair / exclusion helpers
    # ------------------------------------------------------------------

    def get_manual_partner(self, ctrl):
        leaf = ctrl.split("|")[-1]
        if leaf in self.manual_pairs:
            return self.manual_pairs[leaf]
        for src, prt in self.manual_pairs.items():
            if prt == leaf:
                return src
        return None

    def is_excluded(self, ctrl):
        return ctrl.split("|")[-1] in self.excluded_controls

    def add_manual_pair(self, source_leaf, partner_leaf):
        self.manual_pairs[source_leaf] = partner_leaf

    def remove_manual_pair(self, source_leaf):
        self.manual_pairs.pop(source_leaf, None)
        for k in [k for k, v in self.manual_pairs.items() if v == source_leaf]:
            del self.manual_pairs[k]

    def set_excluded(self, ctrl_leaf, excluded=True):
        if excluded:
            if ctrl_leaf not in self.excluded_controls:
                self.excluded_controls.append(ctrl_leaf)
        else:
            if ctrl_leaf in self.excluded_controls:
                self.excluded_controls.remove(ctrl_leaf)

    def get_partner(self, ctrl):
        """Manual pair first, then token-swap heuristic."""
        manual = self.get_manual_partner(ctrl)
        if manual:
            return manual
        return self._find_partner(ctrl, self.left_token, self.right_token)

    def get_side(self, ctrl):
        leaf = ctrl.split("|")[-1]
        ctrl_data = self.controls.get(ctrl)
        if ctrl_data is None:
            for k, v in self.controls.items():
                if k.split("|")[-1] == leaf:
                    ctrl_data = v
                    break
        if ctrl_data is None:
            return None
        return ctrl_data.get("side", "middle")

    def list_controls(self, side=None, category=None):
        """Return control keys filtered by side and/or category."""
        result = []
        for ctrl, data in self.controls.items():
            if side is not None and data.get("side") != side:
                continue
            if category is not None and data.get("category", "") != category:
                continue
            result.append(ctrl)
        return result

    # ------------------------------------------------------------------
    # Prefix replacement (Studio Library style search & replace)
    # ------------------------------------------------------------------

    def rename_prefix(self, new_prefix):
        """
        Rewrite every control name, manual-pair entry, and excluded entry to
        use *new_prefix* instead of self.prefix.

        This is the primary use case for "the same rig referenced in another
        scene under a different namespace": import the JSON, then call
        rename_prefix("ScenesRefName") to remap all stored references.
        """
        if not new_prefix:
            new_prefix = DEFAULT_PREFIX
        if new_prefix == self.prefix:
            return False

        old = self.prefix

        # Controls dict — keys + nested 'partner' values
        new_controls = {}
        for ctrl_key, ctrl_data in self.controls.items():
            new_key = _swap_prefix_in_name(ctrl_key, old, new_prefix)
            data    = dict(ctrl_data)
            partner = data.get("partner")
            if partner:
                data["partner"] = _swap_prefix_in_name(partner, old, new_prefix)
            new_controls[new_key] = data
        self.controls = new_controls

        # Manual pairs — both key and value
        new_manual = {}
        for src, prt in self.manual_pairs.items():
            new_src = _swap_prefix_in_name(src, old, new_prefix)
            new_prt = _swap_prefix_in_name(prt, old, new_prefix)
            new_manual[new_src] = new_prt
        self.manual_pairs = new_manual

        # Excluded controls
        self.excluded_controls = [
            _swap_prefix_in_name(c, old, new_prefix)
            for c in self.excluded_controls
        ]

        # Categories — list of leaf names
        for cat, members in list(self.categories.items()):
            self.categories[cat] = [
                _swap_prefix_in_name(c, old, new_prefix) for c in members
            ]

        self.prefix   = new_prefix
        self.modified = self._timestamp()
        return True

    # ------------------------------------------------------------------
    # Health check / report
    # ------------------------------------------------------------------

    def analyse_pairing(self):
        """Return (paired_count, unpaired_leaves)."""
        paired   = set()
        unpaired = []
        for ctrl_key, ctrl_data in self.controls.items():
            leaf = ctrl_key.split("|")[-1]
            if ctrl_data.get("side", "middle") == "middle":
                continue
            if leaf in paired:
                continue
            partner = self.get_manual_partner(ctrl_key) or ctrl_data.get("partner")
            if partner and cmds.objExists(partner):
                paired.add(leaf)
                paired.add(partner.split("|")[-1])
            else:
                unpaired.append(leaf)
        return len(paired) // 2, unpaired

    def control_count(self):
        return len(self.controls)

    def pair_count(self):
        n = 0
        for ctrl, data in self.controls.items():
            if data.get("side") == "left":
                partner = data.get("partner")
                if partner and partner in self.controls:
                    n += 1
        return n


# ---------------------------------------------------------------------------
# Public module-level API for use by other Animation Tool Kit tools.
# These are thin wrappers so callers don't need to know the class.
# ---------------------------------------------------------------------------

def list_prefixes():
    """Return a sorted list of every stored character prefix."""
    return CharacterSnapshot.list_prefixes()


def load_snapshot(prefix):
    """Return the CharacterSnapshot stored under *prefix*, or None."""
    return CharacterSnapshot.load_from_scene(prefix)


def get_controls_for(prefix, side=None, category=None):
    """Return the list of control names recorded for *prefix*, optionally filtered."""
    snap = load_snapshot(prefix)
    if snap is None:
        return []
    return snap.list_controls(side=side, category=category)


def get_partner(prefix, ctrl):
    """Return the mirror partner for *ctrl* using the snapshot's data."""
    snap = load_snapshot(prefix)
    if snap is None:
        return None
    return snap.get_partner(ctrl)


def get_side(prefix, ctrl):
    snap = load_snapshot(prefix)
    if snap is None:
        return None
    return snap.get_side(ctrl)


def is_excluded(prefix, ctrl):
    snap = load_snapshot(prefix)
    if snap is None:
        return False
    return snap.is_excluded(ctrl)


def rename_prefix(old_prefix, new_prefix):
    """
    Rename a stored snapshot's prefix in place. Returns True on success.
    Useful when the same rig has been referenced into a new scene under a
    different namespace.
    """
    snap = load_snapshot(old_prefix)
    if snap is None:
        return False
    if not snap.rename_prefix(new_prefix):
        return False
    # Remove old key from store and insert the renamed snapshot
    store = CharacterSnapshot._load_store()
    store.pop(old_prefix, None)
    store[new_prefix] = snap.to_dict()
    CharacterSnapshot._save_store(store)
    return True


# ---------------------------------------------------------------------------
# ManualPairEditorDialog — adapted from digetMirrorControl ManualPairEditor
# ---------------------------------------------------------------------------

class ManualPairEditorDialog(QtWidgets.QDialog):
    """
    Per-rig editor for assigning mirror partners that the automatic token-swap
    cannot resolve, and for excluding controls entirely.

    Workflow:
      1. Select a control in the Maya viewport.
      2. Click  ⊕ Src  or  ⊕ Prt  to assign it to a row.
      3. Or type a namespace:nodeName directly into the Partner field.
      4. Click "Exclude" to permanently skip a control.
      5. Click "Save to Scene" — pairs are written into the snapshot.
    """

    STATUS_UNPAIRED = "unpaired"
    STATUS_MANUAL   = "manual"
    STATUS_AUTO_OK  = "auto_ok"
    STATUS_EXCLUDED = "excluded"

    COL_STATUS, COL_SOURCE, COL_ARROW, COL_PARTNER, COL_PICK, COL_EXCL = range(6)

    _BG = {
        STATUS_UNPAIRED: QtGui.QColor(80,  30,  30),
        STATUS_MANUAL:   QtGui.QColor(30,  50,  80),
        STATUS_AUTO_OK:  QtGui.QColor(30,  55,  30),
        STATUS_EXCLUDED: QtGui.QColor(45,  45,  45),
    }

    def __init__(self, prefix, parent=None):
        super().__init__(parent or maya_main_window())
        self._prefix    = prefix
        self._snapshot  = CharacterSnapshot.load_from_scene(prefix) or CharacterSnapshot()
        if self._snapshot.prefix == DEFAULT_PREFIX and prefix:
            self._snapshot.prefix = prefix
        self._rows_data = []
        self.setWindowTitle("Manual Pair Editor — {}".format(prefix or "(no rig)"))
        self.setMinimumWidth(860)
        self.resize(960, 620)
        self.setStyleSheet(DARK_STYLESHEET)
        self._build_ui()
        self._refresh()

    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        self.info_label = QtWidgets.QLabel()
        self.info_label.setWordWrap(True)
        root.addWidget(self.info_label)

        hint = QtWidgets.QLabel(
            "<i>Select a control in the Maya viewport, then click "
            "<b>⊕ Src</b> or <b>⊕ Prt</b> to assign it to a row. "
            "Or type a <tt>namespace:nodeName</tt> directly in the field.</i>"
        )
        hint.setWordWrap(True)
        root.addWidget(hint)

        sep = QtWidgets.QFrame()
        sep.setFrameShape(QtWidgets.QFrame.HLine)
        sep.setFrameShadow(QtWidgets.QFrame.Sunken)
        root.addWidget(sep)

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
        flt_row.addWidget(self._auto_select_chk)
        root.addLayout(flt_row)

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
        self.table.setAlternatingRowColors(False)
        root.addWidget(self.table)

        self.summary_label = QtWidgets.QLabel()
        root.addWidget(self.summary_label)

        btn_row = QtWidgets.QHBoxLayout()
        self.refresh_btn      = QtWidgets.QPushButton("↺  Refresh")
        self.clear_manual_btn = QtWidgets.QPushButton("Clear All Manual Pairs")
        self.save_btn         = QtWidgets.QPushButton("Save to Scene")
        self.save_btn.setObjectName("primaryBtn")
        self.close_btn        = QtWidgets.QPushButton("Close")
        btn_row.addWidget(self.refresh_btn)
        btn_row.addWidget(self.clear_manual_btn)
        btn_row.addStretch()
        btn_row.addWidget(self.save_btn)
        btn_row.addWidget(self.close_btn)
        root.addLayout(btn_row)

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

    @staticmethod
    def _leaf(ctrl):
        return ctrl.split("|")[-1]

    def _refresh(self):
        self._snapshot = CharacterSnapshot.load_from_scene(self._prefix) or CharacterSnapshot()
        if self._snapshot.prefix == DEFAULT_PREFIX and self._prefix:
            self._snapshot.prefix = self._prefix

        left_token  = self._snapshot.left_token
        right_token = self._snapshot.right_token
        manual      = dict(self._snapshot.manual_pairs)
        excluded    = list(self._snapshot.excluded_controls)

        if self._prefix:
            scene_ctrls = _get_controls_for_prefix_in_scene(self._prefix)
        else:
            scene_ctrls = _get_all_nurbs_controls()

        # Combine scene-current controls with controls recorded in the snapshot
        # so a rig that's not currently referenced can still be edited.
        combined = list(scene_ctrls)
        scene_leaves = {self._leaf(c) for c in scene_ctrls}
        for snap_ctrl in self._snapshot.controls.keys():
            if self._leaf(snap_ctrl) not in scene_leaves:
                combined.append(snap_ctrl)

        rows = []
        seen = set()

        for ctrl in combined:
            leaf = self._leaf(ctrl)
            if leaf in seen:
                continue

            if leaf in excluded:
                rows.append({
                    "status":      self.STATUS_EXCLUDED,
                    "source":      leaf,
                    "partner":     "",
                    "source_full": ctrl,
                    "editable":    False,
                })
                seen.add(leaf)
                continue

            if leaf in manual:
                rows.append({
                    "status":      self.STATUS_MANUAL,
                    "source":      leaf,
                    "partner":     manual[leaf],
                    "source_full": ctrl,
                    "editable":    True,
                })
                seen.add(leaf)
                seen.add(manual[leaf])
                continue

            if leaf in manual.values():
                seen.add(leaf)
                continue

            partner = self._snapshot.get_partner(ctrl)
            if partner and cmds.objExists(partner):
                p_leaf = self._leaf(partner)
                rows.append({
                    "status":      self.STATUS_AUTO_OK,
                    "source":      leaf,
                    "partner":     p_leaf,
                    "source_full": ctrl,
                    "editable":    False,
                })
                seen.add(leaf)
                seen.add(p_leaf)
            else:
                base = leaf.split(":")[-1].lower()
                if (left_token.lower() in base) or (right_token.lower() in base):
                    rows.append({
                        "status":      self.STATUS_UNPAIRED,
                        "source":      leaf,
                        "partner":     "",
                        "source_full": ctrl,
                        "editable":    True,
                    })
                seen.add(leaf)

        self._rows_data = rows

        n_unpaired = sum(1 for r in rows if r["status"] == self.STATUS_UNPAIRED)
        n_manual   = sum(1 for r in rows if r["status"] == self.STATUS_MANUAL)
        n_auto     = sum(1 for r in rows if r["status"] == self.STATUS_AUTO_OK)
        n_excl     = sum(1 for r in rows if r["status"] == self.STATUS_EXCLUDED)

        if n_unpaired:
            self.info_label.setText(
                "<span style='color:#e06060;'><b>{} control{} need manual pairing.</b></span>  "
                "Auto: {} · Manual: {} · Excluded: {}".format(
                    n_unpaired, "s" if n_unpaired != 1 else "", n_auto, n_manual, n_excl
                )
            )
        else:
            self.info_label.setText(
                "<span style='color:#60c060;'><b>All controls paired ✔</b></span>  "
                "Auto: {} · Manual: {} · Excluded: {}".format(n_auto, n_manual, n_excl)
            )

        self._apply_filter()

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
        self.summary_label.setText("Showing {} row{}.".format(n, "s" if n != 1 else ""))

    def _insert_row(self, rd):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setRowHeight(row, 30)
        bg = self._BG.get(rd["status"], QtGui.QColor(50, 50, 50))

        def _item(text, align=QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft, editable=False):
            it = QtWidgets.QTableWidgetItem(text)
            it.setTextAlignment(align)
            it.setBackground(bg)
            if not editable:
                it.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable)
            return it

        badge_map = {
            self.STATUS_UNPAIRED: ("✗", "#e06060"),
            self.STATUS_MANUAL:   ("★", "#6090e0"),
            self.STATUS_AUTO_OK:  ("✔", "#60c060"),
            self.STATUS_EXCLUDED: ("○", "#888888"),
        }
        badge_txt, badge_col = badge_map.get(rd["status"], ("?", "#fff"))
        badge_item = _item(badge_txt, QtCore.Qt.AlignCenter)
        badge_item.setForeground(QtGui.QColor(badge_col))
        badge_item.setData(QtCore.Qt.UserRole, rd)
        self.table.setItem(row, self.COL_STATUS, badge_item)

        src_item = _item(rd["source"])
        src_item.setToolTip(rd.get("source_full", rd["source"]))
        self.table.setItem(row, self.COL_SOURCE, src_item)

        arr_item = _item("↔", QtCore.Qt.AlignCenter)
        self.table.setItem(row, self.COL_ARROW, arr_item)

        if rd["editable"]:
            le = QtWidgets.QLineEdit(rd["partner"])
            le.setPlaceholderText("Select in Maya → click ⊕ Prt  (or type name)")
            le.setStyleSheet("background: #2a3a4a; border: 1px solid #4a6a8a;")
            le.textChanged.connect(lambda txt, r=rd: r.update({"partner": txt}))
            self.table.setCellWidget(row, self.COL_PARTNER, le)
        else:
            prt_item = _item(rd["partner"])
            if rd["status"] == self.STATUS_EXCLUDED:
                prt_item.setForeground(QtGui.QColor("#666"))
            self.table.setItem(row, self.COL_PARTNER, prt_item)

        if rd["editable"]:
            pick_w   = QtWidgets.QWidget()
            pick_lay = QtWidgets.QHBoxLayout(pick_w)
            pick_lay.setContentsMargins(2, 2, 2, 2)
            pick_lay.setSpacing(3)
            btn_src = QtWidgets.QPushButton("⊕ Src")
            btn_prt = QtWidgets.QPushButton("⊕ Prt")
            btn_src.setFixedHeight(22)
            btn_prt.setFixedHeight(22)
            pick_lay.addWidget(btn_src)
            pick_lay.addWidget(btn_prt)
            btn_src.clicked.connect(lambda _c=False, r=row: self._pick_from_selection(r, True))
            btn_prt.clicked.connect(lambda _c=False, r=row: self._pick_from_selection(r, False))
            self.table.setCellWidget(row, self.COL_PICK, pick_w)

        excl_w   = QtWidgets.QWidget()
        excl_lay = QtWidgets.QHBoxLayout(excl_w)
        excl_lay.setContentsMargins(2, 2, 2, 2)
        if rd["status"] == self.STATUS_EXCLUDED:
            btn = QtWidgets.QPushButton("Un-Excl")
            btn.clicked.connect(lambda _c=False, leaf=rd["source"]: self._toggle_excluded(leaf, False))
        else:
            btn = QtWidgets.QPushButton("Exclude")
            btn.clicked.connect(lambda _c=False, leaf=rd["source"]: self._toggle_excluded(leaf, True))
        btn.setFixedHeight(22)
        excl_lay.addWidget(btn)
        self.table.setCellWidget(row, self.COL_EXCL, excl_w)

    # ------------------------------------------------------------------

    def _on_row_selected(self, current, previous):
        if not self._auto_select_chk.isChecked() or current is None:
            return
        row = current.row()
        badge_item = self.table.item(row, self.COL_STATUS)
        if badge_item is None:
            return
        rd = badge_item.data(QtCore.Qt.UserRole)
        if rd is None:
            return
        to_select = []
        full = rd.get("source_full", rd.get("source", ""))
        if full and cmds.objExists(full):
            to_select.append(full)
        elif rd.get("source") and cmds.objExists(rd["source"]):
            to_select.append(rd["source"])
        partner = rd.get("partner", "").strip()
        if partner and cmds.objExists(partner):
            to_select.append(partner)
        if to_select:
            cmds.select(to_select, replace=True)

    def _pick_from_selection(self, table_row, pick_source):
        sel = cmds.ls(selection=True, long=False) or []
        if not sel:
            om.MGlobal.displayWarning(
                "[{}] Nothing selected in Maya. "
                "Select a control in the viewport first.".format(TOOL_NAME)
            )
            return
        picked = sel[0].split("|")[-1]
        badge_item = self.table.item(table_row, self.COL_STATUS)
        if badge_item is None:
            return
        rd = badge_item.data(QtCore.Qt.UserRole)
        if rd is None:
            return
        if pick_source:
            rd["source"] = picked
            it = self.table.item(table_row, self.COL_SOURCE)
            if it:
                it.setText(picked)
        else:
            rd["partner"] = picked
            w = self.table.cellWidget(table_row, self.COL_PARTNER)
            if isinstance(w, QtWidgets.QLineEdit):
                w.setText(picked)

    def _toggle_excluded(self, leaf, exclude):
        self._collect_pending_edits()
        self._snapshot.set_excluded(leaf, exclude)
        if exclude:
            self._snapshot.remove_manual_pair(leaf)
        self._snapshot.save_to_scene()
        self._refresh()

    def _collect_pending_edits(self):
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
            partner = ""
            w = self.table.cellWidget(row, self.COL_PARTNER)
            if isinstance(w, QtWidgets.QLineEdit):
                partner = w.text().strip()
            else:
                partner = rd.get("partner", "").strip()
            visible_sources.add(source)
            if partner:
                new_manual[source] = partner
        for src in list(self._snapshot.manual_pairs.keys()):
            if src in visible_sources:
                del self._snapshot.manual_pairs[src]
        self._snapshot.manual_pairs.update(new_manual)

    def _on_save(self):
        self._collect_pending_edits()
        self._snapshot.save_to_scene()
        QtWidgets.QMessageBox.information(
            self, "Saved",
            "{} manual pair{} saved to scene.".format(
                len(self._snapshot.manual_pairs),
                "s" if len(self._snapshot.manual_pairs) != 1 else "",
            )
        )
        self._refresh()

    def _on_refresh(self):
        self._refresh()

    def _on_clear_manual(self):
        result = QtWidgets.QMessageBox.question(
            self, "Clear Manual Pairs",
            "Remove ALL manual pair assignments?\n"
            "(Exclusions are not affected. Auto-matched pairs still work.)",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
        )
        if result == QtWidgets.QMessageBox.Yes:
            self._snapshot.manual_pairs.clear()
            self._snapshot.save_to_scene()
            self._refresh()


# ---------------------------------------------------------------------------
# RenamePrefixDialog — search/replace prefix on a stored snapshot
# ---------------------------------------------------------------------------

class RenamePrefixDialog(QtWidgets.QDialog):
    """
    Prompt the user for a new prefix and rewrite every reference inside a
    stored snapshot. Mirrors Studio Library's pose prefix search/replace.
    """

    def __init__(self, current_prefix, parent=None):
        super().__init__(parent or maya_main_window())
        self.current_prefix = current_prefix
        self.setWindowTitle("Update / Replace Prefix")
        self.setStyleSheet(DARK_STYLESHEET)
        self.setMinimumWidth(460)
        self._build_ui()

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        info = QtWidgets.QLabel(
            "<b>Update / Replace Prefix</b><br>"
            "<span style='color:#999;font-size:11px;'>"
            "Use this when the same rig is referenced in another scene under "
            "a different namespace prefix. Every stored control name, manual "
            "pair, and excluded entry will be rewritten to use the new prefix."
            "</span>"
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        form = QtWidgets.QFormLayout()
        form.setSpacing(6)

        self.current_le = QtWidgets.QLineEdit(self.current_prefix)
        self.current_le.setReadOnly(True)
        self.current_le.setStyleSheet("color: #888;")
        form.addRow("Current Prefix:", self.current_le)

        self.new_le = QtWidgets.QLineEdit()
        self.new_le.setPlaceholderText("e.g. Chris_anim_v02")
        form.addRow("New Prefix:", self.new_le)

        # Helpful hint: list scene namespaces
        hint_row = QtWidgets.QHBoxLayout()
        self.suggest_cb = QtWidgets.QComboBox()
        self.suggest_cb.addItem("(detect from scene…)")
        self._populate_suggestions()
        self.suggest_cb.currentTextChanged.connect(self._on_suggestion_chosen)
        hint_row.addWidget(QtWidgets.QLabel("Scene namespaces:"))
        hint_row.addWidget(self.suggest_cb, 1)
        layout.addLayout(form)
        layout.addLayout(hint_row)

        sep = QtWidgets.QFrame()
        sep.setFrameShape(QtWidgets.QFrame.HLine)
        layout.addWidget(sep)

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch()
        self.ok_btn     = QtWidgets.QPushButton("Apply")
        self.ok_btn.setObjectName("primaryBtn")
        self.cancel_btn = QtWidgets.QPushButton("Cancel")
        btn_row.addWidget(self.ok_btn)
        btn_row.addWidget(self.cancel_btn)
        layout.addLayout(btn_row)

        self.ok_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)
        self.new_le.returnPressed.connect(self.accept)

    def _populate_suggestions(self):
        try:
            ns_list = cmds.namespaceInfo(listOnlyNamespaces=True, recurse=True) or []
        except Exception:
            ns_list = []
        for ns in sorted(ns_list):
            if ns in ("UI", "shared"):
                continue
            self.suggest_cb.addItem(ns)

    def _on_suggestion_chosen(self, text):
        if text and not text.startswith("("):
            self.new_le.setText(text)

    def get_new_prefix(self):
        return self.new_le.text().strip() or DEFAULT_PREFIX


# ---------------------------------------------------------------------------
# CharacterSnapshotManager — main window
# ---------------------------------------------------------------------------

class CharacterSnapshotManager(QtWidgets.QDialog):
    """
    Independent main window for the Character Snapshot tool.

    Lists every stored character snapshot, lets the user create new ones from
    the current selection, edit metadata, run manual-pair editing, export to
    JSON, import from JSON, rename prefixes, and delete snapshots.
    """

    dlg_instance              = None
    manual_pair_editor_instance = None

    @classmethod
    def show_dialog(cls):
        if not cls.dlg_instance:
            cls.dlg_instance = cls()
        if cls.dlg_instance.isHidden():
            cls.dlg_instance.show()
        else:
            cls.dlg_instance.raise_()
            cls.dlg_instance.activateWindow()
        cls.dlg_instance._refresh_list()

    def __init__(self, parent=maya_main_window()):
        super().__init__(parent)
        self.setWindowTitle("{} v{}".format(TOOL_NAME, TOOL_VERSION))
        flags = self.windowFlags()
        flags ^= QtCore.Qt.WindowMinimizeButtonHint
        flags ^= QtCore.Qt.WindowMaximizeButtonHint
        self.setWindowFlags(flags)

        self.setStyleSheet(DARK_STYLESHEET)
        self.setMinimumSize(820, 560)
        self.resize(900, 640)

        self._current_prefix = None

        self._create_menus()
        self._build_ui()
        self._wire()
        self._refresh_list()

    # ------------------------------------------------------------------
    # Menu bar
    # ------------------------------------------------------------------

    def _create_menus(self):
        self.menu_bar = QtWidgets.QMenuBar(self)

        file_menu = self.menu_bar.addMenu("File")
        new_act = QtGui.QAction("New Snapshot from Selection…", self)
        new_act.triggered.connect(self.create_snapshot)
        file_menu.addAction(new_act)
        file_menu.addSeparator()

        imp_act = QtGui.QAction("Import Snapshot from JSON…", self)
        imp_act.triggered.connect(self.import_snapshot)
        file_menu.addAction(imp_act)

        exp_act = QtGui.QAction("Export Selected to JSON…", self)
        exp_act.triggered.connect(self.export_selected)
        file_menu.addAction(exp_act)

        file_menu.addSeparator()
        del_act = QtGui.QAction("Delete Selected Snapshot", self)
        del_act.triggered.connect(self.delete_selected)
        file_menu.addAction(del_act)

        edit_menu = self.menu_bar.addMenu("Edit")

        ren_act = QtGui.QAction("Update / Replace Prefix…", self)
        ren_act.triggered.connect(self.rename_selected_prefix)
        edit_menu.addAction(ren_act)

        manual_act = QtGui.QAction("Manual Pair Editor…", self)
        manual_act.triggered.connect(self.open_manual_pairs)
        edit_menu.addAction(manual_act)

        edit_menu.addSeparator()
        select_act = QtGui.QAction("Select Rig Controls in Maya", self)
        select_act.triggered.connect(self.select_controls_in_scene)
        edit_menu.addAction(select_act)

        help_menu = self.menu_bar.addMenu("Help")
        howto_act = QtGui.QAction("How To Use…", self)
        howto_act.triggered.connect(self.show_help)
        help_menu.addAction(howto_act)
        about_act = QtGui.QAction("About {}".format(TOOL_NAME), self)
        about_act.triggered.connect(self.show_about)
        help_menu.addAction(about_act)

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)
        root.setMenuBar(self.menu_bar)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        root.addWidget(splitter, 1)

        # ---- Left: snapshot list + list-level buttons ----
        left = QtWidgets.QWidget()
        left_lay = QtWidgets.QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(6)

        list_header = QtWidgets.QLabel("<b>Stored Character Snapshots</b>")
        left_lay.addWidget(list_header)

        self.list_widget = QtWidgets.QListWidget()
        self.list_widget.setAlternatingRowColors(True)
        left_lay.addWidget(self.list_widget, 1)

        list_btn_row = QtWidgets.QHBoxLayout()
        self.new_btn     = QtWidgets.QPushButton("◉  New from Selection")
        self.new_btn.setObjectName("snapshotBtn")
        self.refresh_btn = QtWidgets.QPushButton("↺  Refresh")
        list_btn_row.addWidget(self.new_btn)
        list_btn_row.addWidget(self.refresh_btn)
        left_lay.addLayout(list_btn_row)

        list_btn_row2 = QtWidgets.QHBoxLayout()
        self.import_btn = QtWidgets.QPushButton("📥  Import JSON")
        self.export_btn = QtWidgets.QPushButton("📤  Export JSON")
        list_btn_row2.addWidget(self.import_btn)
        list_btn_row2.addWidget(self.export_btn)
        left_lay.addLayout(list_btn_row2)

        list_btn_row3 = QtWidgets.QHBoxLayout()
        self.delete_btn = QtWidgets.QPushButton("🗑  Delete")
        self.delete_btn.setObjectName("dangerBtn")
        list_btn_row3.addWidget(self.delete_btn)
        list_btn_row3.addStretch()
        left_lay.addLayout(list_btn_row3)

        splitter.addWidget(left)

        # ---- Right: detail panel for the selected snapshot ----
        right = QtWidgets.QWidget()
        right_lay = QtWidgets.QVBoxLayout(right)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.setSpacing(6)

        # Metadata group
        meta_grp = QtWidgets.QGroupBox("Snapshot Details")
        meta_grp.setStyleSheet(
            "QGroupBox { border-color: #4a6a9a; }"
            "QGroupBox::title { color: #8ab4f8; background-color: #2f3a4a; }"
        )
        meta_form = QtWidgets.QFormLayout(meta_grp)
        meta_form.setLabelAlignment(QtCore.Qt.AlignRight)
        meta_form.setSpacing(6)

        self.prefix_le      = QtWidgets.QLineEdit()
        self.prefix_le.setReadOnly(True)
        self.prefix_le.setToolTip("Namespace prefix used as the unique key for this snapshot.")
        self.prefix_le.setStyleSheet("color:#aaa;")

        self.rig_name_le    = QtWidgets.QLineEdit()
        self.rig_name_le.setPlaceholderText("e.g. Chris")

        self.description_te = QtWidgets.QPlainTextEdit()
        self.description_te.setMaximumHeight(80)
        self.description_te.setPlaceholderText("Optional notes about this rig…")

        self.left_token_le  = QtWidgets.QLineEdit()
        self.left_token_le.setPlaceholderText("lf")
        self.right_token_le = QtWidgets.QLineEdit()
        self.right_token_le.setPlaceholderText("rt")
        self.mirror_axis_cb = QtWidgets.QComboBox()
        self.mirror_axis_cb.addItems(["X", "Y", "Z"])

        token_row = QtWidgets.QHBoxLayout()
        token_row.addWidget(QtWidgets.QLabel("Left:"))
        token_row.addWidget(self.left_token_le)
        token_row.addWidget(QtWidgets.QLabel("Right:"))
        token_row.addWidget(self.right_token_le)
        token_row.addWidget(QtWidgets.QLabel("Axis:"))
        token_row.addWidget(self.mirror_axis_cb)

        meta_form.addRow("Prefix:",      self.prefix_le)
        meta_form.addRow("Rig Name:",    self.rig_name_le)
        meta_form.addRow("Description:", self.description_te)
        meta_form.addRow("Mirror:",      token_row)

        meta_btn_row = QtWidgets.QHBoxLayout()
        self.save_meta_btn = QtWidgets.QPushButton("💾  Save Details")
        self.save_meta_btn.setObjectName("primaryBtn")
        self.rename_btn    = QtWidgets.QPushButton("⇆  Update / Replace Prefix…")
        meta_btn_row.addWidget(self.save_meta_btn)
        meta_btn_row.addWidget(self.rename_btn)
        meta_btn_row.addStretch()
        meta_form.addRow("", meta_btn_row)
        right_lay.addWidget(meta_grp)

        # Stats / actions group
        stats_grp = QtWidgets.QGroupBox("Rig Contents")
        stats_grp.setStyleSheet(
            "QGroupBox { border-color: #4a6a4a; }"
            "QGroupBox::title { color: #90c890; background-color: #2f3a2f; }"
        )
        stats_lay = QtWidgets.QVBoxLayout(stats_grp)

        self.stats_label = QtWidgets.QLabel()
        self.stats_label.setWordWrap(True)
        stats_lay.addWidget(self.stats_label)

        actions_row = QtWidgets.QHBoxLayout()
        self.manual_btn = QtWidgets.QPushButton("⇌  Manual Pair Editor")
        self.manual_btn.setObjectName("snapshotBtn")
        self.select_btn = QtWidgets.QPushButton("Select Rig Controls in Scene")
        self.resnap_btn = QtWidgets.QPushButton("↻  Re-Snapshot")
        actions_row.addWidget(self.manual_btn)
        actions_row.addWidget(self.select_btn)
        actions_row.addWidget(self.resnap_btn)
        actions_row.addStretch()
        stats_lay.addLayout(actions_row)

        right_lay.addWidget(stats_grp, 1)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([300, 600])

        # Status bar
        self.status_label = QtWidgets.QLabel("")
        self.status_label.setStyleSheet("color: #888; font-size: 10px;")
        root.addWidget(self.status_label)

        self._set_detail_enabled(False)

    def _wire(self):
        self.list_widget.currentItemChanged.connect(self._on_list_selection)
        self.new_btn.clicked.connect(self.create_snapshot)
        self.refresh_btn.clicked.connect(self._refresh_list)
        self.import_btn.clicked.connect(self.import_snapshot)
        self.export_btn.clicked.connect(self.export_selected)
        self.delete_btn.clicked.connect(self.delete_selected)
        self.save_meta_btn.clicked.connect(self._save_details)
        self.rename_btn.clicked.connect(self.rename_selected_prefix)
        self.manual_btn.clicked.connect(self.open_manual_pairs)
        self.select_btn.clicked.connect(self.select_controls_in_scene)
        self.resnap_btn.clicked.connect(self.resnap_selected)

    # ------------------------------------------------------------------
    # List management
    # ------------------------------------------------------------------

    def _refresh_list(self):
        prev = self._current_prefix
        self.list_widget.blockSignals(True)
        self.list_widget.clear()
        prefixes = list_prefixes()
        for pfx in prefixes:
            snap = CharacterSnapshot.load_from_scene(pfx)
            n_ctrls = snap.control_count() if snap else 0
            n_pairs = snap.pair_count()    if snap else 0
            label   = pfx if pfx != DEFAULT_PREFIX else "(no namespace)"
            text = "{}     {} controls · {} pairs".format(label, n_ctrls, n_pairs)
            it = QtWidgets.QListWidgetItem(text)
            it.setData(QtCore.Qt.UserRole, pfx)
            if snap and snap.rig_name:
                it.setToolTip("{} — {}".format(snap.rig_name, snap.description or "no description"))
            self.list_widget.addItem(it)

        if not prefixes:
            placeholder = QtWidgets.QListWidgetItem("  No snapshots stored yet.")
            placeholder.setFlags(QtCore.Qt.NoItemFlags)
            self.list_widget.addItem(placeholder)

        self.list_widget.blockSignals(False)

        # Restore previous selection if still present
        if prev:
            for i in range(self.list_widget.count()):
                if self.list_widget.item(i).data(QtCore.Qt.UserRole) == prev:
                    self.list_widget.setCurrentRow(i)
                    break

        if self.list_widget.currentItem() is None and self.list_widget.count():
            first = self.list_widget.item(0)
            if first.flags() & QtCore.Qt.ItemIsEnabled:
                self.list_widget.setCurrentRow(0)

        self.status_label.setText("{} snapshot{} stored.".format(
            len(prefixes), "s" if len(prefixes) != 1 else ""))

    def _on_list_selection(self, current, previous):
        if current is None:
            self._current_prefix = None
            self._set_detail_enabled(False)
            return
        prefix = current.data(QtCore.Qt.UserRole)
        if prefix is None:
            return
        self._current_prefix = prefix
        self._load_details_into_panel(prefix)
        self._set_detail_enabled(True)

    def _set_detail_enabled(self, enabled):
        for w in (self.rig_name_le, self.description_te,
                  self.left_token_le, self.right_token_le, self.mirror_axis_cb,
                  self.save_meta_btn, self.rename_btn, self.manual_btn,
                  self.select_btn, self.resnap_btn, self.export_btn,
                  self.delete_btn):
            w.setEnabled(enabled)
        if not enabled:
            self.prefix_le.setText("")
            self.rig_name_le.setText("")
            self.description_te.setPlainText("")
            self.left_token_le.setText("")
            self.right_token_le.setText("")
            self.stats_label.setText("")

    def _load_details_into_panel(self, prefix):
        snap = load_snapshot(prefix)
        if snap is None:
            self._set_detail_enabled(False)
            return
        self.prefix_le.setText(prefix if prefix != DEFAULT_PREFIX else "(no namespace)")
        self.rig_name_le.setText(snap.rig_name or "")
        self.description_te.setPlainText(snap.description or "")
        self.left_token_le.setText(snap.left_token or "lf")
        self.right_token_le.setText(snap.right_token or "rt")
        idx = self.mirror_axis_cb.findText(snap.mirror_axis or "X")
        self.mirror_axis_cb.setCurrentIndex(idx if idx >= 0 else 0)

        n_ctrls   = snap.control_count()
        n_pairs   = snap.pair_count()
        n_manual  = len(snap.manual_pairs)
        n_excl    = len(snap.excluded_controls)
        scene_cnt = len(_get_controls_for_prefix_in_scene(prefix)) if prefix != DEFAULT_PREFIX else 0
        match_pct = 0
        if n_ctrls and scene_cnt:
            in_scene = sum(1 for c in snap.controls if cmds.objExists(c) or
                           cmds.objExists(c.split("|")[-1]))
            match_pct = int(100 * in_scene / n_ctrls) if n_ctrls else 0

        text = (
            "<table cellpadding='2'>"
            "<tr><td><b>Controls:</b></td><td>{}</td></tr>"
            "<tr><td><b>Auto pairs:</b></td><td>{}</td></tr>"
            "<tr><td><b>Manual pairs:</b></td><td>{}</td></tr>"
            "<tr><td><b>Excluded:</b></td><td>{}</td></tr>"
            "<tr><td><b>Created:</b></td><td>{}</td></tr>"
            "<tr><td><b>Modified:</b></td><td>{}</td></tr>"
            "<tr><td><b>Scene match:</b></td><td>{} controls present in scene "
            "({}%)</td></tr>"
            "</table>"
        ).format(
            n_ctrls, n_pairs, n_manual, n_excl,
            snap.created, snap.modified,
            scene_cnt, match_pct,
        )
        self.stats_label.setText(text)

    # ------------------------------------------------------------------
    # Snapshot creation / re-snapshot
    # ------------------------------------------------------------------

    def create_snapshot(self):
        sel = cmds.ls(selection=True, long=True)
        if sel:
            prefix    = _detect_prefix(sel[0])
            ctrl_list = _get_controls_for_prefix_in_scene(prefix)
            if not ctrl_list:
                ctrl_list = sel
        else:
            QtWidgets.QMessageBox.warning(
                self, "Nothing Selected",
                "Select at least one control on the rig you want to snapshot, "
                "then try again.\n\n"
                "Tip: selecting any single controller is enough — every other "
                "control sharing the same namespace will be auto-included."
            )
            return

        rig_name = ""
        if prefix != DEFAULT_PREFIX:
            rig_name = prefix.split(":")[-1]

        existing = load_snapshot(prefix)
        if existing is not None:
            box = QtWidgets.QMessageBox(self)
            box.setWindowTitle("Snapshot Exists")
            box.setText(
                "A snapshot already exists for '{}' with {} controls.\n"
                "Replace it with a fresh capture of {} controls?".format(
                    prefix, existing.control_count(), len(ctrl_list)
                )
            )
            replace_btn = box.addButton("Replace", QtWidgets.QMessageBox.AcceptRole)
            cancel_btn  = box.addButton("Cancel",  QtWidgets.QMessageBox.RejectRole)
            box.setDefaultButton(replace_btn)
            box.exec()
            if box.clickedButton() is cancel_btn:
                return
            # Preserve user-entered metadata across re-snapshot
            rig_name      = existing.rig_name      or rig_name
            description   = existing.description
            left_token    = existing.left_token
            right_token   = existing.right_token
            mirror_axis   = existing.mirror_axis
            manual_pairs  = dict(existing.manual_pairs)
            excluded      = list(existing.excluded_controls)
        else:
            description, left_token, right_token, mirror_axis = "", "lf", "rt", "X"
            manual_pairs, excluded = {}, []

        snap = CharacterSnapshot.build(
            ctrl_list, prefix=prefix, rig_name=rig_name,
            description=description, left_token=left_token,
            right_token=right_token, mirror_axis=mirror_axis,
        )
        snap.manual_pairs      = manual_pairs
        snap.excluded_controls = excluded
        snap.save_to_scene()

        self._refresh_list()
        # Select the newly created prefix
        for i in range(self.list_widget.count()):
            if self.list_widget.item(i).data(QtCore.Qt.UserRole) == prefix:
                self.list_widget.setCurrentRow(i)
                break

        # Pairing report
        unique_pairs, unpaired = snap.analyse_pairing()
        if not unpaired:
            QtWidgets.QMessageBox.information(
                self, "Snapshot Created",
                "✔  '{}' captured: {} controls, {} pairs.".format(
                    prefix, snap.control_count(), unique_pairs
                )
            )
        else:
            sample  = unpaired[:10]
            surplus = len(unpaired) - len(sample)
            names   = "\n".join("  • {}".format(n) for n in sample)
            if surplus > 0:
                names += "\n  … and {} more".format(surplus)
            box = QtWidgets.QMessageBox(self)
            box.setWindowTitle("Snapshot — Unpaired Controls")
            box.setText(
                "'{}' captured ({} controls, {} pairs).\n\n"
                "⚠  {} control{} could not be auto-paired:\n\n{}\n\n"
                "Open the Manual Pair Editor now?".format(
                    prefix, snap.control_count(), unique_pairs,
                    len(unpaired), "s" if len(unpaired) != 1 else "", names
                )
            )
            yes_btn = box.addButton("Open Manual Pairs", QtWidgets.QMessageBox.AcceptRole)
            no_btn  = box.addButton("Dismiss",           QtWidgets.QMessageBox.RejectRole)
            box.exec()
            if box.clickedButton() is yes_btn:
                self.open_manual_pairs()

    def resnap_selected(self):
        prefix = self._current_prefix
        if not prefix:
            return
        existing = load_snapshot(prefix)
        if existing is None:
            return
        ctrl_list = _get_controls_for_prefix_in_scene(prefix)
        if not ctrl_list:
            QtWidgets.QMessageBox.warning(
                self, "No Controls in Scene",
                "No controls with the prefix '{}' are currently in the scene.\n"
                "Reference the rig into your scene first, then try again.".format(prefix)
            )
            return
        snap = CharacterSnapshot.build(
            ctrl_list, prefix=prefix, rig_name=existing.rig_name,
            description=existing.description, left_token=existing.left_token,
            right_token=existing.right_token, mirror_axis=existing.mirror_axis,
        )
        snap.manual_pairs      = dict(existing.manual_pairs)
        snap.excluded_controls = list(existing.excluded_controls)
        snap.categories        = dict(existing.categories)
        snap.metadata          = dict(existing.metadata)
        snap.created           = existing.created
        snap.save_to_scene()
        self._refresh_list()
        QtWidgets.QMessageBox.information(
            self, "Re-Snapshot Complete",
            "Re-captured '{}' — {} controls.".format(prefix, snap.control_count())
        )

    # ------------------------------------------------------------------
    # Save metadata / rename / delete / import / export
    # ------------------------------------------------------------------

    def _save_details(self):
        prefix = self._current_prefix
        if not prefix:
            return
        snap = load_snapshot(prefix)
        if snap is None:
            return
        snap.rig_name    = self.rig_name_le.text().strip()
        snap.description = self.description_te.toPlainText().strip()
        snap.left_token  = self.left_token_le.text().strip() or "lf"
        snap.right_token = self.right_token_le.text().strip() or "rt"
        snap.mirror_axis = self.mirror_axis_cb.currentText() or "X"
        snap.save_to_scene()
        self._refresh_list()
        self.status_label.setText("Saved details for '{}'.".format(prefix))

    def rename_selected_prefix(self):
        prefix = self._current_prefix
        if not prefix:
            QtWidgets.QMessageBox.warning(
                self, "No Selection",
                "Select a snapshot from the list first."
            )
            return
        dlg = RenamePrefixDialog(prefix, parent=self)
        if dlg.exec() != QtWidgets.QDialog.Accepted:
            return
        new_prefix = dlg.get_new_prefix()
        if not new_prefix or new_prefix == prefix:
            return
        if new_prefix in list_prefixes():
            QtWidgets.QMessageBox.warning(
                self, "Prefix In Use",
                "A snapshot already exists for '{}'.\n\n"
                "Delete it first if you want to overwrite.".format(new_prefix)
            )
            return
        if not rename_prefix(prefix, new_prefix):
            QtWidgets.QMessageBox.warning(
                self, "Rename Failed",
                "Could not rename '{}' → '{}'.".format(prefix, new_prefix)
            )
            return
        self._current_prefix = new_prefix
        self._refresh_list()
        for i in range(self.list_widget.count()):
            if self.list_widget.item(i).data(QtCore.Qt.UserRole) == new_prefix:
                self.list_widget.setCurrentRow(i)
                break
        QtWidgets.QMessageBox.information(
            self, "Prefix Updated",
            "Renamed '{}' → '{}'.\n\n"
            "All control references inside the snapshot were rewritten.".format(
                prefix, new_prefix
            )
        )

    def delete_selected(self):
        prefix = self._current_prefix
        if not prefix:
            return
        result = QtWidgets.QMessageBox.question(
            self, "Delete Snapshot",
            "Delete the snapshot for '{}'?\n\nThis cannot be undone.\n"
            "Consider exporting it first.".format(prefix),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
        )
        if result != QtWidgets.QMessageBox.Yes:
            return
        CharacterSnapshot.delete_prefix(prefix)
        self._current_prefix = None
        self._refresh_list()

    def export_selected(self):
        prefix = self._current_prefix
        if not prefix:
            QtWidgets.QMessageBox.warning(
                self, "No Selection", "Select a snapshot to export.")
            return
        snap = load_snapshot(prefix)
        if snap is None:
            return
        safe_name = prefix.replace(":", "_") if prefix != DEFAULT_PREFIX else "scene_snapshot"
        filepath, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export Character Snapshot — {}".format(prefix),
            safe_name + ".json",
            "JSON Files (*.json);;All Files (*)",
        )
        if not filepath:
            return
        snap.export_to_file(filepath)
        QtWidgets.QMessageBox.information(
            self, "Exported", "Exported '{}' to:\n{}".format(prefix, filepath))

    def import_snapshot(self):
        filepath, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Import Character Snapshot",
            "", "JSON Files (*.json);;All Files (*)",
        )
        if not filepath:
            return
        snap = CharacterSnapshot.import_from_file(filepath)
        if snap is None:
            return

        # Check for collision
        if snap.prefix in list_prefixes():
            box = QtWidgets.QMessageBox(self)
            box.setWindowTitle("Prefix Collision")
            box.setText(
                "A snapshot already exists for '{}'.\n\n"
                "Replace the existing one, or import under a new prefix?".format(
                    snap.prefix
                )
            )
            replace_btn = box.addButton("Replace",          QtWidgets.QMessageBox.AcceptRole)
            rename_btn  = box.addButton("Import As New…",   QtWidgets.QMessageBox.ActionRole)
            cancel_btn  = box.addButton("Cancel",           QtWidgets.QMessageBox.RejectRole)
            box.exec()
            clicked = box.clickedButton()
            if clicked is cancel_btn:
                return
            if clicked is rename_btn:
                dlg = RenamePrefixDialog(snap.prefix, parent=self)
                if dlg.exec() != QtWidgets.QDialog.Accepted:
                    return
                new_prefix = dlg.get_new_prefix()
                if not new_prefix or new_prefix == snap.prefix:
                    return
                snap.rename_prefix(new_prefix)
                if snap.prefix in list_prefixes():
                    QtWidgets.QMessageBox.warning(
                        self, "Prefix In Use",
                        "'{}' is also already taken — import cancelled.".format(snap.prefix)
                    )
                    return

        snap.save_to_scene()
        self._refresh_list()
        for i in range(self.list_widget.count()):
            if self.list_widget.item(i).data(QtCore.Qt.UserRole) == snap.prefix:
                self.list_widget.setCurrentRow(i)
                break
        QtWidgets.QMessageBox.information(
            self, "Imported",
            "Imported '{}' ({} controls).".format(snap.prefix, snap.control_count()),
        )

    # ------------------------------------------------------------------
    # Manual pairs / scene helpers
    # ------------------------------------------------------------------

    def open_manual_pairs(self):
        prefix = self._current_prefix
        if not prefix:
            QtWidgets.QMessageBox.warning(
                self, "No Selection", "Select a snapshot to edit manual pairs.")
            return
        cls = CharacterSnapshotManager
        if cls.manual_pair_editor_instance and not cls.manual_pair_editor_instance.isHidden():
            cls.manual_pair_editor_instance.close()
        cls.manual_pair_editor_instance = ManualPairEditorDialog(prefix=prefix, parent=self)
        cls.manual_pair_editor_instance.show()

    def select_controls_in_scene(self):
        prefix = self._current_prefix
        if not prefix:
            return
        snap = load_snapshot(prefix)
        if snap is None:
            return
        scene_ctrls = _get_controls_for_prefix_in_scene(prefix)
        if not scene_ctrls:
            # Fallback to whatever the snapshot has that exists
            scene_ctrls = [c for c in snap.controls if cmds.objExists(c)]
        if not scene_ctrls:
            QtWidgets.QMessageBox.warning(
                self, "No Controls Found",
                "No controls with the prefix '{}' are currently in the scene.".format(prefix)
            )
            return
        cmds.select(scene_ctrls, replace=True)
        self.status_label.setText("Selected {} controls in scene.".format(len(scene_ctrls)))

    # ------------------------------------------------------------------
    # Help / About
    # ------------------------------------------------------------------

    def show_help(self):
        text = (
            "<h3>Character Snapshot — How To Use</h3><hr>"
            "<h4>① Create a Snapshot</h4>"
            "<ol>"
            "<li>Reference the rig into your scene.</li>"
            "<li>Select <i>any single</i> controller on the rig.</li>"
            "<li>Click <b>◉ New from Selection</b> — every controller sharing the "
            "same namespace prefix is captured automatically.</li>"
            "</ol>"
            "<h4>② Edit Metadata</h4>"
            "<p>Fill in the <b>Rig Name</b>, <b>Description</b>, and mirror tokens / axis "
            "in the right-hand panel and click <b>💾 Save Details</b>.</p>"
            "<h4>③ Manual Pair Editor</h4>"
            "<p>For controls whose mirror partner can't be detected by the "
            "<tt>lf</tt>↔<tt>rt</tt> token-swap heuristic, open the "
            "<b>⇌ Manual Pair Editor</b> and assign partners by selecting them "
            "in the viewport and clicking <b>⊕ Src</b> / <b>⊕ Prt</b>.</p>"
            "<h4>④ Export / Import JSON</h4>"
            "<p>Snapshots live in the scene file by default, but you can also "
            "<b>📤 Export</b> them as <tt>.json</tt> for sharing between scenes "
            "and <b>📥 Import</b> them back. Mirror-tool exports are accepted "
            "and converted automatically.</p>"
            "<h4>⑤ Update / Replace Prefix</h4>"
            "<p>If the same rig is referenced into another scene under a "
            "<i>different</i> namespace, import the JSON and use "
            "<b>⇆ Update / Replace Prefix…</b> to rewrite every stored "
            "control name to use the new prefix in one operation. "
            "Behaves like Studio Library's pose prefix search/replace.</p>"
            "<h4>⑥ Use From Other Tools</h4>"
            "<p>Other Animation Tool Kit tools can query rig data via the "
            "module API:</p>"
            "<pre style='color:#a0d0ff;'>"
            "import character_snapshot_v1_0_0 as cs\n"
            "for prefix in cs.list_prefixes():\n"
            "    snap = cs.load_snapshot(prefix)\n"
            "    print(prefix, snap.rig_name, snap.control_count())\n"
            "    left  = cs.get_controls_for(prefix, side='left')\n"
            "    partner = cs.get_partner(prefix, 'Chris_v01:ac_lf_handIK')\n"
            "</pre>"
        )
        box = QtWidgets.QMessageBox(self)
        box.setWindowTitle("How To Use — {}".format(TOOL_NAME))
        box.setTextFormat(QtCore.Qt.RichText)
        box.setText(text)
        box.setStandardButtons(QtWidgets.QMessageBox.Ok)
        box.exec()

    def show_about(self):
        text = (
            "<h3>{name}</h3>"
            "<p style='color:#8ab4f8;'>Version {ver}</p><hr>"
            "<p>An Animation Tool Kit utility for capturing, storing, and "
            "managing rig metadata as portable Character Snapshots.</p>"
            "<p>Built on the snapshot, manual-pair editor, and multi-prefix "
            "manager systems originally developed for "
            "<i>digetMirrorControl</i>.</p>"
            "<h4>Author</h4>"
            "<p>David Shepstone</p>"
            "<p style='color:#888; font-size:10px;'>Python · PySide6 · Maya 2025+</p>"
        ).format(name=TOOL_NAME, ver=TOOL_VERSION)
        box = QtWidgets.QMessageBox(self)
        box.setWindowTitle("About {}".format(TOOL_NAME))
        box.setTextFormat(QtCore.Qt.RichText)
        box.setText(text)
        box.setStandardButtons(QtWidgets.QMessageBox.Ok)
        box.exec()


# ---------------------------------------------------------------------------
# Standalone test entry point
# ---------------------------------------------------------------------------

def show_dialog():
    """Convenience launcher used by the shelf button."""
    CharacterSnapshotManager.show_dialog()


if __name__ == "__main__":
    try:
        _existing.close()       # type: ignore
        _existing.deleteLater() # type: ignore
    except Exception:
        pass
    _existing = CharacterSnapshotManager()
    _existing.show()
