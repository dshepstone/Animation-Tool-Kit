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
    2.4.0 - Troubleshoot Rig Setup (Tools menu / button):
             * Fixes rigs whose hands / fingers would not mirror even with a
               Character Snapshot. The snapshot's axis-DOMINANCE heuristic
               misfires on oblique controls (thumbs), on controls near 45°
               in the default pose (A-pose fingers) and on rigs where one
               side has extra 180° offset groups (orientation-mirrored
               controls under behaviour-mirrored parents).
             * Solves the exact mirror relationship of every control from its
               real transform frames at the default pose — exact per-channel
               copy/negate rules where the axes line up, and "matrix"
               mirroring (values solved through the frame matrices) where
               they don't (permuted / oblique axes, differing rotate orders,
               asymmetric defaults).
             * Probes custom attributes (curls, spreads) behaviourally to
               find copy vs negate, and reports attributes that exist on one
               side only or are wired differently per side.
             * Verifies every result in the scene, restores the animator's
               pose, and stores the fix in the Character Snapshot metadata
               (kept on re-snapshot). Mirror, Flip and Mirror Middle use it
               automatically; Edit Rules shows "(rig fix: …)".
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

import datetime
import json
import math

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
      - get_fix_entry / get_fix_rule       → Troubleshoot Rig Setup results
                                              (exact rules / matrix mirroring)
      - save()                             → persists edits to the scene

    Rule precedence: user override → rig fix → auto-detected → heuristic.
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
        self.reload_fix()
        self._dirty = False

    def reload_fix(self):
        """Re-read the Troubleshoot Rig Setup data from the snapshot."""
        meta = getattr(self._cs, "metadata", None) or {}
        fix  = meta.get(_CS_META_RIG_FIX) if isinstance(meta, dict) else None
        ctrls = fix.get("controls") if isinstance(fix, dict) else None
        self._fix = ctrls if isinstance(ctrls, dict) else {}

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
        override = self.get_override(ctrl, attr)
        if override in RULES:
            return override
        return self.get_auto_rule(ctrl, attr)

    def get_auto_rule(self, ctrl, attr, include_fix=True):
        """Rule used when there is no user override: the Troubleshoot Rig
        Setup result when one is stored, else the snapshot's auto rule."""
        if include_fix:
            fixed = self.get_fix_rule(ctrl, attr)
            if fixed in RULES:
                return fixed
        try:
            return self._cs.get_auto_mirror_rule(ctrl, attr)
        except Exception:
            return None

    # -- Rig fix (Troubleshoot Rig Setup) ------------------------------------

    def get_fix_entry(self, ctrl, partner=None):
        """Stored rig-fix entry for *ctrl* as the mirror SOURCE, or None.
        When *partner* is given the entry must have been solved for it."""
        entry = self._fix.get(_ctrl_base(ctrl))
        if not isinstance(entry, dict):
            return None
        if partner is not None and entry.get("partner") != _ctrl_base(partner):
            return None
        return entry

    def get_fix_rule(self, ctrl, attr):
        entry = self.get_fix_entry(ctrl)
        if not entry:
            return None
        return (entry.get("rules") or {}).get(attr)

    def is_fix_matrix(self, ctrl, attr=None):
        entry = self.get_fix_entry(ctrl)
        if not entry or entry.get("mode") != RIG_FIX_MATRIX:
            return False
        return attr is None or attr in _TR_ATTRS

    def fix_count(self):
        return len(self._fix)

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
# Rig Troubleshooter — exact mirror-frame analysis
# ---------------------------------------------------------------------------
#
# The snapshot's automatic channel rules come from an axis-DOMINANCE
# heuristic: each control's local axes are reduced to the closest world
# axis and the two sides are compared. That breaks down on rigs with "odd"
# setups, for example:
#   * controls whose axes sit close to 45° in the default pose (A-pose
#     fingers: 0.717 vs 0.696 — a fraction of a degree of asymmetry flips
#     the classification),
#   * oblique controls such as thumbs, where the dominance mapping picks
#     different local axes on each side and produces wrong copy/negate
#     rules,
#   * one side built with extra 180° offset groups (e.g. R_*_offset_group_1
#     under a behaviour-mirrored offsetGrp) so the right-side controls are
#     orientation-mirrored while their parents are behaviour-mirrored,
#   * custom attributes (curls, spreads) whose driver networks differ in
#     sign between the sides, or exist on one side only.
#
# The troubleshooter replaces guesswork with exact math. At the rig's
# default pose it samples, for every control, the frame its rotate channels
# act in (R0 · jointOrient · parent) and the parent space its translate
# channels act in, and solves the mirror relationship between partners:
#
#     D_dst = M · D_src · M⁻¹        M = F_dst · S · F_src⁻¹
#     Δt_dst = Δt_src · N            N = P_src · S · P_dst⁻¹
#
# (S = reflection across the mirror axis, row-vector convention.) When M
# and N are signed identities each channel is an exact copy/negate;
# otherwise the control is mirrored through the matrices at run time
# ("matrix" mode) — which also covers permuted axes, differing rotate
# orders and asymmetric default values. Custom attributes are probed
# behaviourally: the tool nudges the attribute on one side, measures what
# moves, and finds whether copying or negating it on the partner produces
# the mirrored motion. Every result is verified in the scene before it is
# offered, and the fix is stored in the Character Snapshot metadata so
# every mirror operation (and a re-snapshot) keeps using it.

_CS_META_RIG_FIX  = "mirror_controls_rig_fix"
RIG_FIX_SCHEMA    = 1

RIG_FIX_CHANNEL   = "channel"
RIG_FIX_MATRIX    = "matrix"

_TRANSLATE_ATTRS  = ("translateX", "translateY", "translateZ")
_ROTATE_ATTRS     = ("rotateX", "rotateY", "rotateZ")
_TR_ATTRS         = _TRANSLATE_ATTRS + _ROTATE_ATTRS

# Maya rotateOrder enum → axis application order (row-vector convention:
# xyz means the X rotation is applied first).
_ROTATE_ORDERS = {0: (0, 1, 2), 1: (1, 2, 0), 2: (2, 0, 1),
                  3: (0, 2, 1), 4: (1, 0, 2), 5: (2, 1, 0)}

# Behavioural comparison tolerance: relative error between the partner's
# measured motion and the exact mirror of the source's motion. Loose enough
# to accept slightly mismatched driver multipliers (e.g. 0.017 vs 0.01745),
# tight enough to reject the wrong sign.
_PROBE_MATCH_TOL = 0.12


def _m3_identity():
    return [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]


def _m3_mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)]
            for i in range(3)]


def _m3_det(m):
    return (m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
            - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
            + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]))


def _m3_inv(m):
    det = _m3_det(m)
    if abs(det) < 1e-12:
        return None
    inv = [[0.0] * 3 for _ in range(3)]
    for i in range(3):
        for j in range(3):
            a = [[m[r][c] for c in range(3) if c != i] for r in range(3) if r != j]
            inv[i][j] = (-1) ** (i + j) * (a[0][0] * a[1][1] - a[0][1] * a[1][0]) / det
    return inv


def _m3_transpose(m):
    return [[m[j][i] for j in range(3)] for i in range(3)]


def _m3_from_m4(m16):
    return [[float(m16[0]), float(m16[1]), float(m16[2])],
            [float(m16[4]), float(m16[5]), float(m16[6])],
            [float(m16[8]), float(m16[9]), float(m16[10])]]


def _m3_normalize_rows(m):
    out = []
    for row in m:
        n = math.sqrt(sum(v * v for v in row)) or 1.0
        out.append([v / n for v in row])
    return out


def _m3_flat(m):
    return [round(v, 9) for row in m for v in row]


def _m3_unflat(v):
    return [[float(x) for x in v[0:3]],
            [float(x) for x in v[3:6]],
            [float(x) for x in v[6:9]]]


def _m3_max_diff(a, b):
    return max(abs(a[i][j] - b[i][j]) for i in range(3) for j in range(3))


def _mirror_m3(axis):
    """Reflection matrix across the plane perpendicular to world *axis*."""
    idx = "XYZ".index((axis or "X").upper()[-1])
    s = _m3_identity()
    s[idx][idx] = -1.0
    return s


def _euler_to_m3(angles_deg, ro=0):
    """Maya Euler rotation (degrees, rotateOrder enum) → 3x3 matrix."""
    rx, ry, rz = [math.radians(a) for a in angles_deg]
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)
    mats = {
        0: [[1.0, 0.0, 0.0], [0.0, cx, sx], [0.0, -sx, cx]],
        1: [[cy, 0.0, -sy], [0.0, 1.0, 0.0], [sy, 0.0, cy]],
        2: [[cz, sz, 0.0], [-sz, cz, 0.0], [0.0, 0.0, 1.0]],
    }
    m = _m3_identity()
    for axis in _ROTATE_ORDERS.get(ro, (0, 1, 2)):
        m = _m3_mul(m, mats[axis])
    return m


def _m3_to_euler(m, ro=0, hint=None):
    """3x3 rotation matrix → Maya Euler angles (degrees) for *ro*.

    Of the two equivalent Euler solutions the one closest to *hint* (the
    control's current values) is returned, with ±360° multiples chosen to
    keep animation curves continuous.
    """
    i, j, k = _ROTATE_ORDERS.get(ro, (0, 1, 2))
    q = _m3_transpose(m)
    e = 1.0 if (i, j, k) in ((0, 1, 2), (1, 2, 0), (2, 0, 1)) else -1.0
    cb = math.sqrt(q[k][j] ** 2 + q[k][k] ** 2)
    b = math.atan2(-e * q[k][i], cb)
    if cb > 1e-9:
        a = math.atan2(e * q[k][j], q[k][k])
        c = math.atan2(e * q[j][i], q[i][i])
    else:                                   # gimbal lock
        c = 0.0
        a = math.atan2(-e * q[j][k], q[j][j])
    ref = list(hint) if hint is not None else [0.0, 0.0, 0.0]
    best, best_d = None, None
    for sa, sb, sc in ((a, b, c), (a + math.pi, math.pi - b, c + math.pi)):
        vals = [0.0, 0.0, 0.0]
        vals[i], vals[j], vals[k] = math.degrees(sa), math.degrees(sb), math.degrees(sc)
        vals = [v + 360.0 * round((h - v) / 360.0) for v, h in zip(vals, ref)]
        d = sum(abs(v - h) for v, h in zip(vals, ref))
        if best is None or d < best_d:
            best, best_d = vals, d
    return best


def _signed_unit_diag(m, tol=0.02):
    """[±1, ±1, ±1] when *m* is a signed identity within *tol*, else None."""
    signs = []
    for i in range(3):
        for j in range(3):
            v = m[i][j]
            if i == j:
                if abs(abs(v) - 1.0) > tol:
                    return None
            elif abs(v) > tol:
                return None
        signs.append(1 if m[i][i] > 0 else -1)
    return signs


def analyse_mirror_frames(src, dst, mirror_axis="X", tol=0.02):
    """Solve the exact mirror relationship between two controls.

    *src* / *dst* are frame samples taken at the rig's default pose (see
    RigTroubleshooter._sample_frame):
        frame  – 3x3 frame the rotate channels act in, including the
                 control's default rotation (R0 · jointOrient · parent)
        parent – 3x3 parent space the translate channels act in
        ro     – rotateOrder enum,  t0 / r0 – default translate / rotate

    For a centre control pass the same sample as *src* and *dst*.

    Returns {"M", "N", "rules", "mode", "reasons"} or None when a frame is
    degenerate. "rules" holds exact copy/negate decisions for the translate
    / rotate channels when the axes line up; "mode" is "matrix" when they
    don't (permuted / oblique axes, differing rotate orders, asymmetric
    default values) and the values must be mirrored through M and N.
    """
    s = _mirror_m3(mirror_axis)
    f_src_inv = _m3_inv(src["frame"])
    p_dst_inv = _m3_inv(dst["parent"])
    if f_src_inv is None or p_dst_inv is None:
        return None
    m = _m3_mul(_m3_mul(dst["frame"], s), f_src_inv)
    n = _m3_mul(_m3_mul(src["parent"], s), p_dst_inv)

    rules, reasons = {}, []
    trans_signs = _signed_unit_diag(n, tol)
    rot_signs   = _signed_unit_diag(m, tol)

    if trans_signs is None:
        reasons.append("translate axes are not aligned with the partner's")
    else:
        for i, attr in enumerate(_TRANSLATE_ATTRS):
            sign = trans_signs[i]
            t0s = src.get("t0", [0.0, 0.0, 0.0])[i]
            t0d = dst.get("t0", [0.0, 0.0, 0.0])[i]
            if abs(t0d - sign * t0s) > max(1e-3, 0.01 * abs(t0s)):
                reasons.append("{} default values are not mirror images".format(attr))
            rules[attr] = RULE_COPY if sign > 0 else RULE_NEGATE

    if rot_signs is None:
        reasons.append("rotate axes are not aligned with the partner's")
    else:
        if src.get("ro", 0) != dst.get("ro", 0):
            reasons.append("rotate orders differ")
        # Conjugating a rotation by a signed-diagonal matrix keeps its axis
        # and flips the angle when (axis sign × det) is negative.
        det_sign = 1 if _m3_det(m) > 0 else -1
        for i, attr in enumerate(_ROTATE_ATTRS):
            sign = rot_signs[i] * det_sign
            r0s = src.get("r0", [0.0, 0.0, 0.0])[i]
            r0d = dst.get("r0", [0.0, 0.0, 0.0])[i]
            if abs(r0d - sign * r0s) > 1e-2:
                reasons.append("{} default values are not mirror images".format(attr))
            rules[attr] = RULE_COPY if sign > 0 else RULE_NEGATE

    return {
        "M":       _m3_flat(m),
        "N":       _m3_flat(n),
        "rules":   rules,
        "mode":    RIG_FIX_MATRIX if reasons else RIG_FIX_CHANNEL,
        "reasons": reasons,
    }


def matrix_mirror_values(entry, src_vals, dst_hint=None):
    """Mirror translate / rotate values through a matrix-mode fix entry.

    *src_vals* maps channel names to the source control's values (rotations
    in degrees); channels it lacks (locked) use the source's defaults.
    *dst_hint* holds the destination's current values so the closest Euler
    solution is chosen. Returns {attr: value} for all six channels.
    """
    out = {}
    m   = _m3_unflat(entry["M"])
    n   = _m3_unflat(entry["N"])
    t0s = entry.get("t0_src") or [0.0, 0.0, 0.0]
    t0d = entry.get("t0_dst") or [0.0, 0.0, 0.0]
    r0s = entry.get("r0_src") or [0.0, 0.0, 0.0]
    r0d = entry.get("r0_dst") or [0.0, 0.0, 0.0]
    ro_s = entry.get("ro_src", 0)
    ro_d = entry.get("ro_dst", 0)

    dt = [src_vals.get(a, t0s[i]) - t0s[i] for i, a in enumerate(_TRANSLATE_ATTRS)]
    for j, attr in enumerate(_TRANSLATE_ATTRS):
        out[attr] = t0d[j] + sum(dt[i] * n[i][j] for i in range(3))

    m_inv = _m3_inv(m)
    r0s_inv = _m3_inv(_euler_to_m3(r0s, ro_s))
    if m_inv is not None and r0s_inv is not None:
        rs = [src_vals.get(a, r0s[i]) for i, a in enumerate(_ROTATE_ATTRS)]
        # Rotation relative to the default pose, mirrored, re-applied on top
        # of the destination's default pose.
        d_src = _m3_mul(_euler_to_m3(rs, ro_s), r0s_inv)
        d_dst = _m3_mul(_m3_mul(m, d_src), m_inv)
        r_dst = _m3_mul(d_dst, _euler_to_m3(r0d, ro_d))
        hint = None
        if dst_hint:
            hint = [dst_hint.get(a, r0d[i]) for i, a in enumerate(_ROTATE_ATTRS)]
        for attr, val in zip(_ROTATE_ATTRS, _m3_to_euler(r_dst, ro_d, hint)):
            out[attr] = val
    return out


def _ctrl_base(ctrl):
    """Namespace-free leaf name — the key rig-fix entries are stored under
    (survives namespace / prefix changes)."""
    return ctrl.split("|")[-1].split(":")[-1]


def _angle_to_degrees():
    """Factor converting Maya UI angle values to degrees."""
    try:
        unit = cmds.currentUnit(query=True, angle=True) or "deg"
    except Exception:
        unit = "deg"
    return 180.0 / math.pi if unit.startswith("rad") else 1.0


def _mirror_values_with_fix(entry, attrs, src_data, dst_data, to_deg):
    """Matrix-mode helper used at mirror time: returns {attr: value} in UI
    units for the translate / rotate channels present in *attrs*."""
    src_vals = {}
    for a in _TR_ATTRS:
        if a in src_data:
            v = src_data[a]
            src_vals[a] = v * to_deg if a in _ROTATE_ATTRS else v
    hint = {a: dst_data[a] * to_deg for a in _ROTATE_ATTRS if a in dst_data}
    mirrored = matrix_mirror_values(entry, src_vals, hint)
    out = {}
    for a in attrs:
        if a in mirrored:
            out[a] = mirrored[a] / to_deg if a in _ROTATE_ATTRS else mirrored[a]
    return out


class RigTroubleshooter(object):
    """Diagnose and fix rigs whose controls don't mirror with plain rules.

    Usage (also driven by RigTroubleshootDialog):
        ts = RigTroubleshooter(adapter, prefix)
        report = ts.run(progress_cb)        # analyse — scene is restored
        ts.apply(report)                    # store the fix in the snapshot

    run() temporarily puts the rig in its snapshot default pose (autokey
    and undo recording suspended), analyses every pair / centre control,
    verifies each result in the scene and restores the animator's pose.
    """

    TRANSLATE_PROBE = 1.0      # linear UI units
    ROTATE_PROBE    = 10.0     # degrees
    CUSTOM_PROBE    = 5.0      # unbounded custom attributes

    def __init__(self, adapter, prefix, controls=None, probe_custom=True,
                 include_middles=True, mirror_axis=None):
        self.adapter         = adapter
        self.prefix          = prefix
        self.probe_custom    = probe_custom
        self.include_middles = include_middles
        self.mirror_axis     = (mirror_axis or adapter.mirror_axis or "X").upper()
        self._only           = controls      # optional subset (full paths)
        self._to_deg         = _angle_to_degrees()
        self._cancelled      = False
        self._leaf_to_dag    = {}

    # -- Scene helpers ------------------------------------------------------

    @staticmethod
    def _world(node):
        m = cmds.xform(node, query=True, worldSpace=True, matrix=True)
        return [m[12], m[13], m[14]], _m3_normalize_rows(_m3_from_m4(m))

    @staticmethod
    def _is_settable(plug):
        try:
            if not cmds.objExists(plug):
                return False
            if cmds.getAttr(plug, lock=True):
                return False
            src = cmds.listConnections(plug, source=True, destination=False,
                                       skipConversionNodes=True) or []
            # Anim curves are fine (setAttr works until the time changes);
            # anything else driving the plug makes it unsettable.
            return all(cmds.nodeType(s).startswith("animCurve") for s in src)
        except Exception:
            return False

    @staticmethod
    def _numeric_attrs(ctrl):
        """Keyable, unlocked scalar attributes (bool / enum excluded)."""
        out = []
        for attr in cmds.listAttr(ctrl, keyable=True, unlocked=True) or []:
            plug = "{}.{}".format(ctrl, attr)
            try:
                if cmds.getAttr(plug, type=True) in ("bool", "enum"):
                    continue
                if isinstance(cmds.getAttr(plug), (int, float)):
                    out.append(attr)
            except Exception:
                continue
        return out

    def _sample_frame(self, ctrl):
        """Frame sample for analyse_mirror_frames() at the current pose."""
        parents = cmds.listRelatives(ctrl, parent=True, fullPath=True) or []
        if parents:
            parent = _m3_from_m4(cmds.xform(parents[0], query=True,
                                            worldSpace=True, matrix=True))
        else:
            parent = _m3_identity()
        try:
            if cmds.attributeQuery("offsetParentMatrix", node=ctrl, exists=True):
                opm = cmds.getAttr("{}.offsetParentMatrix".format(ctrl))
                parent = _m3_mul(_m3_from_m4(opm), parent)
        except Exception:
            pass
        ro = int(cmds.getAttr("{}.rotateOrder".format(ctrl)) or 0)
        t0 = [float(cmds.getAttr("{}.translate{}".format(ctrl, a))) for a in "XYZ"]
        r0 = [float(cmds.getAttr("{}.rotate{}".format(ctrl, a))) * self._to_deg
              for a in "XYZ"]
        jo = _m3_identity()
        if cmds.nodeType(ctrl) == "joint":
            jo_vals = cmds.getAttr("{}.jointOrient".format(ctrl))[0]
            jo = _euler_to_m3([v * self._to_deg for v in jo_vals], 0)
        frame = _m3_mul(_m3_mul(_euler_to_m3(r0, ro), jo),
                        _m3_normalize_rows(parent))
        return {"frame": frame, "parent": parent, "ro": ro, "t0": t0, "r0": r0}

    def _counterpart(self, node):
        """Mirror counterpart of any rig node (control or driven node)."""
        partner = self.adapter.find_partner(node)
        if partner:
            return _resolve_long(partner)
        leaf = node.split("|")[-1]
        ns, base = (leaf.rsplit(":", 1) if ":" in leaf else ("", leaf))
        ns_prefix = ns + ":" if ns else ""
        for cand in _mirror_name_candidates(base, self.adapter.left_token,
                                            self.adapter.right_token):
            matches = cmds.ls(ns_prefix + cand, long=True) or []
            if len(matches) == 1:
                return matches[0]
        # Centre nodes (no side token) mirror onto themselves.
        if not _mirror_name_candidates(base, self.adapter.left_token,
                                       self.adapter.right_token):
            return _resolve_long(node)
        return None

    @staticmethod
    def _downstream_dag(plug, max_nodes=150, max_dag=24):
        """Transforms / joints driven (through utility nodes) by *plug*."""
        dag, seen = [], set()
        try:
            queue = cmds.listConnections(plug, source=False, destination=True,
                                         skipConversionNodes=False) or []
        except Exception:
            queue = []
        while queue and len(seen) < max_nodes and len(dag) < max_dag:
            node = queue.pop(0)
            if node in seen:
                continue
            seen.add(node)
            try:
                inherited = cmds.nodeType(node, inherited=True) or []
            except Exception:
                continue
            if "transform" in inherited:          # includes joints
                dag.extend(cmds.ls(node, long=True) or [])
                continue
            if ("geometryFilter" in inherited or "shape" in inherited
                    or "animCurve" in inherited or "objectSet" in inherited):
                continue
            queue.extend(cmds.listConnections(node, source=False, destination=True,
                                              skipConversionNodes=False) or [])
        return dag

    def _measure(self, nodes):
        return {n: self._world(n) for n in nodes if cmds.objExists(n)}

    @staticmethod
    def _effects(before, after):
        """Per node: (world position delta, world-space delta rotation)."""
        out = {}
        for n, (p0, r0) in before.items():
            if n not in after:
                continue
            p1, r1 = after[n]
            out[n] = ([p1[i] - p0[i] for i in range(3)],
                      _m3_mul(_m3_transpose(r0), r1))
        return out

    def _set_and_measure(self, values, nodes):
        """Set {plug: value}, measure *nodes*, restore. None if a value
        could not be set (locked, clamped by limits / min-max, driven)."""
        saved = {}
        try:
            for plug, val in values.items():
                saved[plug] = cmds.getAttr(plug)
            before = self._measure(nodes)
            for plug, val in values.items():
                cmds.setAttr(plug, val)
                got = cmds.getAttr(plug)
                if abs(got - val) > 1e-4 * max(1.0, abs(val)):
                    return None
            after = self._measure(nodes)
            return self._effects(before, after)
        except Exception:
            return None
        finally:
            for plug, val in saved.items():
                try:
                    cmds.setAttr(plug, val)
                except Exception:
                    pass

    def _compare(self, src_eff, dst_eff, mapping):
        """Relative error between the partner's measured motion and the
        exact mirror of the source's motion. None = source didn't move."""
        s = _mirror_m3(self.mirror_axis)
        pos_err = pos_mag = rot_err = rot_mag = 0.0
        ident = _m3_identity()
        for n_src, n_dst in mapping:
            if n_src not in src_eff or n_dst not in dst_eff:
                continue
            dp_s, g_s = src_eff[n_src]
            dp_d, g_d = dst_eff[n_dst]
            exp_p = [dp_s[j] * s[j][j] for j in range(3)]
            exp_g = _m3_mul(_m3_mul(s, g_s), s)
            pos_mag += math.sqrt(sum(v * v for v in dp_s))
            pos_err += math.sqrt(sum((dp_d[j] - exp_p[j]) ** 2 for j in range(3)))
            rot_mag += _m3_max_diff(g_s, ident)
            rot_err += _m3_max_diff(g_d, exp_g)
        ratios = []
        if pos_mag > 1e-4:
            ratios.append(pos_err / pos_mag)
        if rot_mag > 1e-5:
            ratios.append(rot_err / rot_mag)
        if not ratios:
            return None
        return max(ratios)

    # -- Probing -------------------------------------------------------------

    def _probe_delta(self, ctrl, attr):
        plug = "{}.{}".format(ctrl, attr)
        if attr in _TRANSLATE_ATTRS:
            return self.TRANSLATE_PROBE
        if attr in _ROTATE_ATTRS:
            return self.ROTATE_PROBE / self._to_deg
        delta = self.CUSTOM_PROBE
        try:
            node = ctrl
            if cmds.attributeQuery(attr, node=node, minExists=True) and \
                    cmds.attributeQuery(attr, node=node, maxExists=True):
                lo = cmds.attributeQuery(attr, node=node, minimum=True)[0]
                hi = cmds.attributeQuery(attr, node=node, maximum=True)[0]
                delta = max(1e-3, 0.25 * (hi - lo))
                cur = cmds.getAttr(plug)
                if cur + delta > hi:
                    delta = -delta
            elif cmds.attributeQuery(attr, node=node, maxExists=True):
                hi = cmds.attributeQuery(attr, node=node, maximum=True)[0]
                if cmds.getAttr(plug) + delta > hi:
                    delta = -delta
        except Exception:
            pass
        return delta

    def _probe_channel(self, src, dst, attr):
        """Behavioural copy/negate test for one channel.

        Returns (rule, error) where rule is copy / negate, "none" when the
        channel moves nothing measurable, or "mismatch" when neither sign
        reproduces the mirrored motion.
        """
        src_plug = "{}.{}".format(src, attr)
        dst_plug = "{}.{}".format(dst, attr)
        if not (self._is_settable(src_plug) and self._is_settable(dst_plug)):
            return "none", None
        watch = [src] + [n for n in self._downstream_dag(src_plug) if n != src]
        mapping = [(src, dst)]
        for n in watch[1:]:
            cp = self._counterpart(n)
            if cp and len(cmds.ls(cp, long=True) or []) == 1:
                mapping.append((n, cmds.ls(cp, long=True)[0]))
        delta = self._probe_delta(src, attr)
        v_src = cmds.getAttr(src_plug)
        src_eff = self._set_and_measure({src_plug: v_src + delta},
                                        [a for a, _ in mapping])
        if src_eff is None:
            return "none", None
        v_dst = cmds.getAttr(dst_plug)
        errors = {}
        for rule, d in ((RULE_COPY, delta), (RULE_NEGATE, -delta)):
            dst_eff = self._set_and_measure({dst_plug: v_dst + d},
                                            [b for _, b in mapping])
            if dst_eff is None:
                continue
            err = self._compare(src_eff, dst_eff, mapping)
            if err is None:
                return "none", None
            errors[rule] = err
        if not errors:
            return "none", None
        best = min(errors, key=errors.get)
        other = [v for k, v in errors.items() if k != best]
        if errors[best] <= _PROBE_MATCH_TOL and (not other or other[0] > 2.0 * errors[best]):
            return best, errors[best]
        return "mismatch", errors[best]

    def _mirror_test_values(self, entry, src, dst, test_vals):
        """Destination values the fix would write for *test_vals*."""
        if entry["mode"] == RIG_FIX_MATRIX:
            src_data = {a: cmds.getAttr("{}.{}".format(src, a)) for a in _TR_ATTRS}
            src_data.update(test_vals)
            dst_data = {a: cmds.getAttr("{}.{}".format(dst, a)) for a in _TR_ATTRS}
            return _mirror_values_with_fix(entry, list(test_vals), src_data,
                                           dst_data, self._to_deg)
        out = {}
        for a, v in test_vals.items():
            rule = entry["rules"].get(a)
            if rule == RULE_COPY:
                out[a] = v
            elif rule == RULE_NEGATE:
                out[a] = -v
        return out

    def _verify(self, entry, src, dst):
        """Pose the source, write what the fix would write to the partner and
        compare the world-space motion. Returns error ratio, or None when
        the control's own channels move nothing measurable."""
        test = {}
        offsets = {"translateX": 1.0, "translateY": 0.7, "translateZ": 0.4,
                   "rotateX": 12.0, "rotateY": 8.0, "rotateZ": 5.0}
        for a, off in offsets.items():
            sp, dp = "{}.{}".format(src, a), "{}.{}".format(dst, a)
            if self._is_settable(sp) and self._is_settable(dp):
                scale = self.TRANSLATE_PROBE if a in _TRANSLATE_ATTRS else 1.0 / self._to_deg
                test[a] = cmds.getAttr(sp) + off * scale
        if not test:
            return None
        src_eff = self._set_and_measure(
            {"{}.{}".format(src, a): v for a, v in test.items()}, [src])
        if src_eff is None:
            return None
        dst_vals = self._mirror_test_values(entry, src, dst, test)
        dst_eff = self._set_and_measure(
            {"{}.{}".format(dst, a): v for a, v in dst_vals.items()}, [dst])
        if dst_eff is None:
            return None
        return self._compare(src_eff, dst_eff, [(src, dst)])

    # -- Default pose ---------------------------------------------------------

    def _enter_default_pose(self, ctrls):
        saved, n_missing = {}, 0
        for ctrl in ctrls:
            data = self.adapter._cs._control_data(ctrl) or {}
            defaults = data.get("default_values") or {}
            if not defaults:
                n_missing += 1
                continue
            for attr, val in defaults.items():
                plug = "{}.{}".format(ctrl, attr)
                try:
                    if cmds.getAttr(plug, lock=True):
                        continue
                    cur = cmds.getAttr(plug)
                    if isinstance(cur, (int, float)) and abs(cur - val) > 1e-9:
                        saved[plug] = cur
                        cmds.setAttr(plug, val)
                except Exception:
                    continue
        return saved, n_missing

    @staticmethod
    def _restore(saved):
        for plug, val in saved.items():
            try:
                cmds.setAttr(plug, val)
            except Exception:
                pass

    # -- Main entry point -----------------------------------------------------

    def cancel(self):
        self._cancelled = True

    def _collect(self):
        """(pairs, middles) of scene controls to analyse."""
        all_ctrls = []
        for key in self.adapter.cs_controls():
            resolved = self.adapter._cs._resolve_to_scene(key)
            if resolved:
                all_ctrls.append(_resolve_long(resolved))
        self._leaf_to_dag = {c.split("|")[-1]: c for c in all_ctrls}
        wanted = None
        if self._only:
            wanted = set()
            for c in self._only:
                wanted.add(c)
                p = self.adapter.find_partner(c)
                if p:
                    wanted.add(_resolve_long(p))
        pairs, middles, done = [], [], set()
        for ctrl in all_ctrls:
            if ctrl in done or self.adapter.is_excluded(ctrl):
                continue
            if wanted is not None and ctrl not in wanted:
                continue
            side = self.adapter.get_side(ctrl) or "middle"
            partner = self.adapter.find_partner(ctrl)
            partner = self._leaf_to_dag.get(partner.split("|")[-1],
                                            _resolve_long(partner)) if partner else None
            if partner and cmds.objExists(partner) and partner != ctrl:
                if side == "right":
                    ctrl, partner = partner, ctrl
                pairs.append((ctrl, partner))
                done.update((ctrl, partner))
            elif side == "middle" and self.include_middles:
                middles.append(ctrl)
                done.add(ctrl)
        return pairs, middles

    def run(self, progress_cb=None):
        """Analyse the rig. Returns a report dict (see apply())."""
        pairs, middles = self._collect()
        report = {
            "prefix":  self.prefix,
            "axis":    self.mirror_axis,
            "pairs":   len(pairs),
            "middles": len(middles),
            "entries": {},       # base name → fix entry
            "changes": [],       # (ctrl, attr, before, after, reason)
            "matrix":  [],       # (ctrl, partner, reasons)
            "issues":  [],       # (severity, ctrl, message)
            "verified": 0,
            "failed":   0,
            "unverified": 0,
            "cancelled": False,
        }
        all_ctrls = [c for p in pairs for c in p] + middles
        auto_key = cmds.autoKeyframe(query=True, state=True)
        undo_on  = cmds.undoInfo(query=True, state=True)
        cmds.autoKeyframe(state=False)
        cmds.undoInfo(stateWithoutFlush=False)
        saved = {}
        try:
            saved, n_missing = self._enter_default_pose(all_ctrls)
            if n_missing:
                report["issues"].append((
                    "warning", "(rig)",
                    "{} controls have no default pose stored in the snapshot — "
                    "they were analysed in their current pose. Re-take the "
                    "Character Snapshot at the default pose for best "
                    "results.".format(n_missing)))
            jobs = [(a, b) for a, b in pairs] + [(m, m) for m in middles]
            for idx, (src, dst) in enumerate(jobs):
                if self._cancelled:
                    report["cancelled"] = True
                    break
                if progress_cb:
                    progress_cb(idx, len(jobs), _ctrl_base(src))
                try:
                    self._analyse_job(src, dst, report)
                except Exception as exc:
                    report["issues"].append((
                        "error", _ctrl_base(src),
                        "Analysis failed: {}".format(exc)))
        finally:
            self._restore(saved)
            cmds.undoInfo(stateWithoutFlush=undo_on)
            cmds.autoKeyframe(state=auto_key)
        return report

    def _effective_rule(self, ctrl, attr, is_middle=False):
        """Rule Mirror Controls would have used before this fix."""
        ov = self.adapter.get_override(ctrl, attr)
        if ov in RULES:
            return ov
        if is_middle:
            # Classic Mirror Middle: negate translate on the mirror axis and
            # every rotation, copy everything else.
            if attr in _ROTATE_ATTRS or attr == "translate" + self.mirror_axis:
                return RULE_NEGATE
            return RULE_COPY
        rule = self.adapter.get_auto_rule(ctrl, attr, include_fix=False)
        return rule if rule in RULES else "heuristic"

    def _analyse_job(self, src, dst, report):
        is_middle = src == dst
        s_src = self._sample_frame(src)
        s_dst = s_src if is_middle else self._sample_frame(dst)
        fwd = analyse_mirror_frames(s_src, s_dst, self.mirror_axis)
        if fwd is None:
            report["issues"].append(("error", _ctrl_base(src),
                                     "Degenerate transform (zero scale?) — skipped."))
            return
        entry = self._make_entry(fwd, s_src, s_dst, dst)
        method = "frames"

        if not is_middle:
            # A default pose that isn't symmetric can't mirror onto itself;
            # results stay relative to each side's default.
            s = _mirror_m3(self.mirror_axis)
            p_src, p_dst = self._world(src)[0], self._world(dst)[0]
            gap = math.sqrt(sum((p_dst[j] - p_src[j] * s[j][j]) ** 2 for j in range(3)))
            size = max(1.0, math.sqrt(sum(v * v for v in p_src)))
            if gap > 0.01 * size:
                report["issues"].append((
                    "warning", _ctrl_base(src),
                    "Default pose is not symmetric — {} sits {:.3g} units from "
                    "the mirror image of this control. Check the rig's default "
                    "pose (and the snapshot's default values).".format(
                        _ctrl_base(dst), gap)))

        # --- verify the frame solution in the scene ---
        err = self._verify(entry, src, dst)
        if err is None or err > _PROBE_MATCH_TOL:
            # The control's channels are routed through extra nodes (or
            # don't move the control itself) — fall back to behavioural
            # per-channel probing on everything they drive.
            probed, ok = {}, True
            for attr in _TR_ATTRS:
                rule, _e = self._probe_channel(src, dst, attr)
                if rule in (RULE_COPY, RULE_NEGATE):
                    probed[attr] = rule
                elif rule == "mismatch":
                    ok = False
            if probed and ok:
                entry["mode"]  = RIG_FIX_CHANNEL
                entry["rules"] = dict(entry["rules"], **probed)
                method = "probe"
                err = self._verify(entry, src, dst)
                if err is None:
                    err = 0.0
        verified = err is not None and err <= _PROBE_MATCH_TOL
        entry["verified"] = bool(verified)
        entry["method"]   = method
        if verified:
            report["verified"] += 1
        elif err is None:
            report["unverified"] += 1
        else:
            report["failed"] += 1
            report["issues"].append((
                "warning", _ctrl_base(src),
                "Could not reproduce an exact mirror (error {:.0%}). The "
                "control is probably driven by constraints or space switches "
                "— check its channels in Edit Rules.".format(err)))

        # --- custom attributes (curls, spreads, switches…) ---
        src_attrs = set(self._numeric_attrs(src))
        dst_attrs = set(self._numeric_attrs(dst))
        if not is_middle:
            for attr in sorted(src_attrs ^ dst_attrs):
                if attr in _TR_ATTRS:
                    continue
                owner = src if attr in src_attrs else dst
                other = dst if owner == src else src
                report["issues"].append((
                    "info", _ctrl_base(owner),
                    "'{}' exists only on this side (missing on {}) — it "
                    "cannot be mirrored.".format(attr, _ctrl_base(other))))
            if self.probe_custom:
                for attr in sorted(src_attrs & dst_attrs):
                    if attr in _TR_ATTRS or attr.startswith("scale"):
                        continue
                    rule, e = self._probe_channel(src, dst, attr)
                    if rule in (RULE_COPY, RULE_NEGATE):
                        entry["rules"][attr] = rule
                    elif rule == "mismatch":
                        report["issues"].append((
                            "warning", _ctrl_base(src),
                            "'{}' drives the two sides differently — neither "
                            "copy nor negate reproduces a mirror (error "
                            "{:.0%}). Compare the driver networks on both "
                            "sides.".format(attr, e or 0.0)))

        # --- record the forward entry and the reverse direction ---
        self._record(report, src, dst, entry, fwd)
        if not is_middle:
            rev = analyse_mirror_frames(s_dst, s_src, self.mirror_axis)
            if rev is not None:
                r_entry = self._make_entry(rev, s_dst, s_src, src)
                if entry["mode"] == RIG_FIX_CHANNEL:
                    # Copy/negate is symmetric — keep probed decisions too.
                    r_entry["mode"]  = RIG_FIX_CHANNEL
                    r_entry["rules"] = dict(entry["rules"])
                else:
                    r_entry["rules"].update({a: r for a, r in entry["rules"].items()
                                             if a not in _TR_ATTRS})
                r_entry["verified"] = entry["verified"]
                r_entry["method"]   = method
                self._record(report, dst, src, r_entry, rev, reverse=True)

    def _make_entry(self, analysis, s_src, s_dst, dst):
        return {
            "partner": _ctrl_base(dst),
            "mode":    analysis["mode"],
            "rules":   dict(analysis["rules"]) if analysis["mode"] == RIG_FIX_CHANNEL else
                       {},
            "M":       analysis["M"],
            "N":       analysis["N"],
            "t0_src":  [round(v, 6) for v in s_src["t0"]],
            "t0_dst":  [round(v, 6) for v in s_dst["t0"]],
            "r0_src":  [round(v, 6) for v in s_src["r0"]],
            "r0_dst":  [round(v, 6) for v in s_dst["r0"]],
            "ro_src":  s_src["ro"],
            "ro_dst":  s_dst["ro"],
        }

    def _record(self, report, src, dst, entry, analysis, reverse=False):
        base = _ctrl_base(src)
        report["entries"][base] = entry
        if entry["mode"] == RIG_FIX_MATRIX:
            if not reverse:
                report["matrix"].append((base, entry["partner"], analysis["reasons"]))
        animatable = set(self._numeric_attrs(src))
        for attr, rule in sorted(entry["rules"].items()):
            if attr not in animatable:
                continue
            before = self._effective_rule(src, attr, is_middle=(src == dst))
            if before != rule:
                report["changes"].append((base, attr, before, rule,
                                          "exact frame analysis" if attr in _TR_ATTRS
                                          and entry.get("method") == "frames"
                                          else "behaviour probe"))
        for attr in _TR_ATTRS + tuple(entry["rules"]):
            override = self.adapter.get_override(src, attr)
            if override not in RULES:
                continue
            fixed = entry["rules"].get(attr)
            if entry["mode"] == RIG_FIX_MATRIX and attr in _TR_ATTRS:
                fixed = "matrix"
            if fixed and fixed != override:
                report["issues"].append((
                    "info", base,
                    "Manual override '{}' on {} conflicts with the detected "
                    "'{}' and would take priority — Apply clears it when "
                    "'Clear conflicting overrides' is ticked.".format(
                        override, attr, fixed)))

    # -- Persist --------------------------------------------------------------

    def apply(self, report, clear_conflicting_overrides=True, clear_flip_signs=True):
        """Store *report*'s entries in the Character Snapshot metadata.

        Existing entries for controls not analysed this run are kept, so a
        "selected controls only" run can refine an earlier whole-rig fix.
        Returns (n_entries, n_overrides_cleared, n_flip_signs_cleared).
        """
        cs = self.adapter._cs
        meta = cs.metadata if isinstance(cs.metadata, dict) else {}
        fix = meta.get(_CS_META_RIG_FIX)
        if not isinstance(fix, dict) or fix.get("schema") != RIG_FIX_SCHEMA:
            fix = {"schema": RIG_FIX_SCHEMA, "controls": {}}
        fix["mirror_axis"] = report["axis"]
        fix["updated"] = datetime.datetime.now().isoformat(timespec="seconds")
        fix["controls"].update(report["entries"])
        meta[_CS_META_RIG_FIX] = fix

        n_ov = n_flip = 0
        if clear_conflicting_overrides:
            overrides = meta.get("channel_flip_overrides")
            if isinstance(overrides, dict):
                for key in list(overrides):
                    entry = report["entries"].get(key.split(":")[-1])
                    per = overrides.get(key)
                    if not entry or not isinstance(per, dict):
                        continue
                    for attr in list(per):
                        fixed = entry["rules"].get(attr)
                        if (fixed and per[attr] != fixed) or \
                                (entry["mode"] == RIG_FIX_MATRIX and attr in _TR_ATTRS):
                            del per[attr]
                            n_ov += 1
                    if not per:
                        overrides.pop(key, None)
        if clear_flip_signs:
            flips = meta.get(_CS_META_FLIP_SIGNS)
            if isinstance(flips, list):
                keep = [f for f in flips
                        if not report["entries"].get(f.split(":")[-1], {}).get("verified")]
                n_flip = len(flips) - len(keep)
                meta[_CS_META_FLIP_SIGNS] = keep
                self.adapter._flip_signs = set(keep)
        cs.metadata = meta
        cs.save_to_scene()
        self.adapter.reload_fix()
        return len(report["entries"]), n_ov, n_flip


def clear_rig_fix(adapter):
    """Remove every stored rig-fix entry from the adapter's snapshot."""
    cs = adapter._cs
    meta = cs.metadata if isinstance(cs.metadata, dict) else {}
    if meta.pop(_CS_META_RIG_FIX, None) is None:
        return False
    cs.metadata = meta
    cs.save_to_scene()
    adapter.reload_fix()
    return True


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
QPushButton#snapshotBtn:disabled { background-color: #333333; color: #666666; border-color: #444444; }
QPushButton#flipSignBtn {
    background-color: #5a4a30;
    color: #e8c87a;
    border: 1px solid #7a6a40;
}
QPushButton#flipSignBtn:hover { background-color: #6a5a40; border-color: #9a8a60; }
QPushButton#troubleshootBtn {
    background-color: #4a3a5a;
    color: #d8c0f0;
    border: 1px solid #6a5a8a;
}
QPushButton#troubleshootBtn:hover { background-color: #5a4a6a; border-color: #8a7aaa; }
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
            "<b>(rig fix)</b> = verified by Troubleshoot Rig Setup  ·  "
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

            if self.adapter.is_fix_matrix(ctrl, attr_name):
                auto_label = "(rig fix: matrix)"
            elif self.adapter.get_fix_rule(ctrl, attr_name) in RULES:
                auto_label = "(rig fix: {})".format(auto_rule)
            elif auto_rule in RULES:
                auto_label = "(auto: {})".format(auto_rule)
            else:
                auto_label = "(auto: heuristic)"
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
# RigTroubleshootDialog — "Troubleshoot Rig Setup" UI
# ---------------------------------------------------------------------------

class RigTroubleshootDialog(QtWidgets.QDialog):
    """
    Front end for RigTroubleshooter.

    Runs the analysis (the rig is temporarily put in its snapshot default
    pose and restored afterwards), lists every rule it corrects, every
    control that needs matrix mirroring and every setup problem it found,
    then stores the fix in the Character Snapshot on "Apply Fix".
    """

    HEADERS = ["Control", "Channel", "Before", "After", "Details"]

    def __init__(self, adapter, prefix, owner=None, parent=None):
        super().__init__(parent or maya_main_window())
        self.adapter = adapter
        self.prefix  = prefix
        self.owner   = owner            # MirrorControls — refreshed after apply
        self._troubleshooter = None
        self._report = None
        self.setWindowTitle("Troubleshoot Rig Setup  —  Mirror Controls")
        self.setStyleSheet(DARK_STYLESHEET)
        self.resize(760, 620)
        self._build_ui()
        self._refresh_header()

    # ------------------------------------------------------------------

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self.header_label = QtWidgets.QLabel()
        self.header_label.setWordWrap(True)
        layout.addWidget(self.header_label)

        intro = QtWidgets.QLabel(
            "Use this when mirroring gives wrong results even with a Character "
            "Snapshot — typically hands and fingers built with extra offset "
            "groups, 180° flips or near-45° axes, oblique thumbs, or curl "
            "attributes wired differently on each side.<br>"
            "The analysis puts the rig in its <b>snapshot default pose</b>, "
            "solves the exact mirror relationship of every control from its "
            "real transform frames, probes custom attributes behaviourally, "
            "verifies each result in the scene and then restores your pose. "
            "Nothing is changed until you click <b>Apply Fix</b>."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("color:#aaaaaa;")
        layout.addWidget(intro)

        opt_grp = QtWidgets.QGroupBox("Options")
        opt_lay = QtWidgets.QGridLayout(opt_grp)
        self.scope_all_rb = QtWidgets.QRadioButton("Whole rig")
        self.scope_sel_rb = QtWidgets.QRadioButton("Selected controls (and their partners)")
        self.scope_all_rb.setChecked(True)
        self.probe_cb = QtWidgets.QCheckBox("Probe custom attributes (curl, spread, …)")
        self.probe_cb.setChecked(True)
        self.probe_cb.setToolTip(
            "Nudge each custom attribute on one side, measure what it moves\n"
            "and find whether copying or negating it on the partner gives\n"
            "the mirrored motion. Slower, but catches driver networks that\n"
            "are wired with opposite signs on each side.")
        self.middle_cb = QtWidgets.QCheckBox("Include centre controls")
        self.middle_cb.setChecked(True)
        self.clear_ov_cb = QtWidgets.QCheckBox("On apply: clear conflicting channel overrides")
        self.clear_ov_cb.setChecked(True)
        self.clear_ov_cb.setToolTip(
            "Manual copy/negate overrides always take priority. Overrides\n"
            "that contradict the verified fix (often added while trying to\n"
            "fix the rig by hand) are removed when this is ticked.")
        self.clear_flip_cb = QtWidgets.QCheckBox("On apply: clear Flip Sign on fixed controls")
        self.clear_flip_cb.setChecked(True)
        opt_lay.addWidget(self.scope_all_rb, 0, 0)
        opt_lay.addWidget(self.scope_sel_rb, 0, 1)
        opt_lay.addWidget(self.probe_cb, 1, 0)
        opt_lay.addWidget(self.middle_cb, 1, 1)
        opt_lay.addWidget(self.clear_ov_cb, 2, 0)
        opt_lay.addWidget(self.clear_flip_cb, 2, 1)
        layout.addWidget(opt_grp)

        self.run_btn = QtWidgets.QPushButton("Run Analysis")
        self.run_btn.setObjectName("mirrorBtn")
        layout.addWidget(self.run_btn)

        self.summary_label = QtWidgets.QLabel(
            "<span style='color:#888;'>Not analysed yet.</span>")
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        self.tree = QtWidgets.QTreeWidget()
        self.tree.setColumnCount(len(self.HEADERS))
        self.tree.setHeaderLabels(self.HEADERS)
        self.tree.setAlternatingRowColors(True)
        self.tree.setUniformRowHeights(True)
        hdr = self.tree.header()
        hdr.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        for col in (1, 2, 3):
            hdr.setSectionResizeMode(col, QtWidgets.QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(4, QtWidgets.QHeaderView.Stretch)
        layout.addWidget(self.tree, 1)

        btn_row = QtWidgets.QHBoxLayout()
        self.apply_btn = QtWidgets.QPushButton("Apply Fix to Snapshot")
        self.apply_btn.setObjectName("snapshotBtn")
        self.apply_btn.setEnabled(False)
        self.clear_btn = QtWidgets.QPushButton("Clear Stored Fix")
        self.clear_btn.setToolTip(
            "Remove the rig fix from the Character Snapshot and go back to\n"
            "the snapshot's automatically detected rules.")
        close_btn = QtWidgets.QPushButton("Close")
        btn_row.addWidget(self.apply_btn)
        btn_row.addWidget(self.clear_btn)
        btn_row.addStretch()
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        self.run_btn.clicked.connect(self._on_run)
        self.apply_btn.clicked.connect(self._on_apply)
        self.clear_btn.clicked.connect(self._on_clear)
        close_btn.clicked.connect(self.close)

    def _refresh_header(self):
        n_fix = self.adapter.fix_count()
        pfx = self.prefix if self.prefix and self.prefix != DEFAULT_PREFIX else "(scene)"
        state = ("<span style='color:#80c080;'>rig fix stored for {} "
                 "controls</span>".format(n_fix) if n_fix else
                 "<span style='color:#888;'>no rig fix stored</span>")
        self.header_label.setText(
            "<b>Character:</b> {}  ·  <b>Mirror axis:</b> {}  ·  {}".format(
                pfx, self.adapter.mirror_axis, state))
        self.clear_btn.setEnabled(bool(n_fix))

    # ------------------------------------------------------------------

    def _on_run(self):
        controls = None
        if self.scope_sel_rb.isChecked():
            controls = cmds.ls(selection=True, long=True) or []
            if not controls:
                QtWidgets.QMessageBox.warning(
                    self, "Nothing Selected",
                    "Select the controls to troubleshoot (e.g. one hand's "
                    "finger controls), or choose 'Whole rig'.")
                return

        ts = RigTroubleshooter(
            self.adapter, self.prefix, controls=controls,
            probe_custom=self.probe_cb.isChecked(),
            include_middles=self.middle_cb.isChecked(),
        )
        progress = QtWidgets.QProgressDialog(
            "Analysing rig…", "Cancel", 0, 100, self)
        progress.setWindowTitle("Troubleshoot Rig Setup")
        progress.setWindowModality(QtCore.Qt.WindowModal)
        progress.setMinimumDuration(0)

        def _cb(i, total, name):
            progress.setMaximum(max(1, total))
            progress.setValue(i)
            progress.setLabelText("Analysing {}  ({}/{})".format(name, i + 1, total))
            QtWidgets.QApplication.processEvents()
            if progress.wasCanceled():
                ts.cancel()

        self.run_btn.setEnabled(False)
        try:
            report = ts.run(_cb)
        finally:
            progress.close()
            self.run_btn.setEnabled(True)

        self._troubleshooter = ts
        self._report = report
        self._populate(report)
        self.apply_btn.setEnabled(bool(report["entries"]) and not report["cancelled"])

    def _populate(self, report):
        self.tree.clear()
        changes, matrix, issues = report["changes"], report["matrix"], report["issues"]

        n_ctrl_changed = len({c for c, _a, _b, _n, _r in changes})
        parts = [
            "<b>{}</b> pairs and <b>{}</b> centre controls analysed".format(
                report["pairs"], report["middles"]),
            "<span style='color:#80c080;'>{} verified</span>".format(report["verified"]),
        ]
        if report["failed"]:
            parts.append("<span style='color:#e8a060;'>{} could not be verified"
                         "</span>".format(report["failed"]))
        if report["unverified"]:
            parts.append("{} not testable (driven channels)".format(report["unverified"]))
        parts.append("<b>{}</b> channel rules corrected on {} controls".format(
            len(changes), n_ctrl_changed))
        if matrix:
            parts.append("<b>{}</b> controls need matrix mirroring".format(len(matrix)))
        if report["cancelled"]:
            parts.append("<span style='color:#e86060;'>cancelled — partial "
                         "results, not applicable</span>")
        self.summary_label.setText("  ·  ".join(parts))

        def _section(text, color):
            item = QtWidgets.QTreeWidgetItem([" " + text, "", "", "", ""])
            font = item.font(0)
            font.setBold(True)
            item.setFont(0, font)
            item.setFirstColumnSpanned(True)
            item.setForeground(0, QtGui.QColor(color))
            self.tree.addTopLevelItem(item)
            return item

        if changes:
            sec = _section("Channel rule corrections ({})".format(len(changes)), "#8ab4f8")
            by_ctrl = {}
            for ctrl, attr, before, after, reason in changes:
                by_ctrl.setdefault(ctrl, []).append((attr, before, after, reason))
            for ctrl in sorted(by_ctrl):
                entry = report["entries"].get(ctrl, {})
                c_item = QtWidgets.QTreeWidgetItem(
                    [ctrl, "", "", "", "→ {}{}".format(
                        entry.get("partner", ""),
                        "" if entry.get("verified") else "   (not verified)")])
                sec.addChild(c_item)
                for attr, before, after, reason in by_ctrl[ctrl]:
                    row = QtWidgets.QTreeWidgetItem(["", attr, before, after, reason])
                    row.setForeground(3, QtGui.QColor(
                        "#e8a060" if after == RULE_NEGATE else "#d4d4d4"))
                    c_item.addChild(row)
            sec.setExpanded(True)

        if matrix:
            sec = _section("Matrix-mirrored controls ({})".format(len(matrix)), "#c0a0e0")
            for ctrl, partner, reasons in matrix:
                sec.addChild(QtWidgets.QTreeWidgetItem(
                    [ctrl, "t / r", "", "matrix",
                     "→ {}: {}".format(partner, "; ".join(reasons))]))
            sec.setExpanded(True)

        if issues:
            sec = _section("Setup problems & notes ({})".format(len(issues)), "#e8c87a")
            colors = {"error": "#e86060", "warning": "#e8a060", "info": "#aaaaaa"}
            for severity, ctrl, msg in issues:
                row = QtWidgets.QTreeWidgetItem([ctrl, severity, "", "", msg])
                row.setToolTip(4, msg)
                row.setForeground(1, QtGui.QColor(colors.get(severity, "#aaaaaa")))
                sec.addChild(row)
            sec.setExpanded(True)

        if not (changes or matrix or issues):
            _section("No problems found — every analysed control already "
                     "mirrors correctly with the snapshot's rules.", "#80c080")

    def _on_apply(self):
        if not self._report or not self._troubleshooter:
            return
        n_entries, n_ov, n_flip = self._troubleshooter.apply(
            self._report,
            clear_conflicting_overrides=self.clear_ov_cb.isChecked(),
            clear_flip_signs=self.clear_flip_cb.isChecked(),
        )
        self.apply_btn.setEnabled(False)
        self._refresh_header()
        if self.owner is not None:
            self.owner._on_rig_fix_changed(self.adapter)
        extra = []
        if n_ov:
            extra.append("{} conflicting channel override{} cleared".format(
                n_ov, "s" if n_ov != 1 else ""))
        if n_flip:
            extra.append("{} Flip Sign override{} cleared".format(
                n_flip, "s" if n_flip != 1 else ""))
        om.MGlobal.displayInfo(
            "[Mirror Controls] Rig fix stored for {} controls{}.".format(
                n_entries, (" — " + ", ".join(extra)) if extra else ""))
        QtWidgets.QMessageBox.information(
            self, "Rig Fix Applied",
            "The rig fix was stored in the Character Snapshot for {} "
            "controls.{}\n\nMirror, Flip and Mirror Middle now use it "
            "automatically. It is kept when the snapshot is re-taken; run the "
            "troubleshooter again if the rig itself changes.".format(
                n_entries, ("\n" + "\n".join(extra)) if extra else ""))

    def _on_clear(self):
        result = QtWidgets.QMessageBox.question(
            self, "Clear Stored Fix",
            "Remove the stored rig fix and return to the snapshot's "
            "automatically detected channel rules?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.Cancel,
        )
        if result != QtWidgets.QMessageBox.Yes:
            return
        clear_rig_fix(self.adapter)
        self._refresh_header()
        if self.owner is not None:
            self.owner._on_rig_fix_changed(self.adapter)


# ---------------------------------------------------------------------------
# MirrorControls  (main dialog)
# ---------------------------------------------------------------------------

class MirrorControls(QtWidgets.QDialog):

    dlg_instance                = None
    snapshot_editor_instance    = None
    manual_pair_editor_instance = None
    troubleshoot_instance       = None

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
        self.setWindowTitle("Mirror Controls  v2.4.0")
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

        troubleshoot_action = QtGui.QAction("Troubleshoot Rig Setup…", self)
        troubleshoot_action.setToolTip(
            "Diagnose and fix controls that don't mirror correctly even with\n"
            "a snapshot (fingers / thumbs with extra offset groups, 180° flips,\n"
            "near-45° axes, curl attributes wired differently per side).")
        troubleshoot_action.triggered.connect(self.open_troubleshooter)
        tools_menu.addAction(troubleshoot_action)

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

        self.troubleshoot_btn = self._make_icon_btn(
            "Troubleshoot Rig Setup",
            "Hands or fingers still mirror wrong with a snapshot?\n\n"
            "Analyses every control's real transform frames at the default\n"
            "pose, probes custom attributes (curls, spreads), verifies each\n"
            "result in the scene and stores the fix in the Character\n"
            "Snapshot so every mirror uses it.",
            "troubleshootBtn"
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
        snap_lay.addWidget(self.troubleshoot_btn)

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
        self.troubleshoot_btn.clicked.connect(self.open_troubleshooter)
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

    def open_troubleshooter(self):
        """Open the Troubleshoot Rig Setup dialog for the active rig."""
        if _try_import_character_snapshot() is None:
            self._show_character_snapshot_missing()
            return
        prefix = self._active_prefix or self.get_active_prefix()
        sel = cmds.ls(selection=True, long=True) or []
        if sel:
            prefix = self._resolve_prefix_for_controls(sel)
        adapter = self._load_snapshot_for_mirroring(prefix, announce=False)
        if adapter is None:
            result = QtWidgets.QMessageBox.question(
                self, "No Character Snapshot",
                "Troubleshoot Rig Setup analyses the rig recorded in its "
                "Character Snapshot, and none was found{}.\n\n"
                "Pose the rig at its default pose, select a control and take "
                "a Character Snapshot now?".format(
                    " for '{}'".format(prefix) if prefix and prefix != DEFAULT_PREFIX else ""
                ),
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            )
            if result == QtWidgets.QMessageBox.Yes:
                self.take_snapshot()
            return
        cls = MirrorControls
        if cls.troubleshoot_instance and not cls.troubleshoot_instance.isHidden():
            cls.troubleshoot_instance.close()
        cls.troubleshoot_instance = RigTroubleshootDialog(
            adapter, prefix, owner=self, parent=self)
        cls.troubleshoot_instance.show()

    def _on_rig_fix_changed(self, adapter):
        """Called by the troubleshooter after a fix is applied / cleared."""
        self._refresh_snapshot_status()
        editor = MirrorControls.snapshot_editor_instance
        if editor is not None and not editor.isHidden():
            fresh = self._load_snapshot_for_mirroring(editor._prefix, announce=False)
            if fresh is not None:
                editor.update_adapter(fresh)

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
        fix = (cs_snap.metadata or {}).get(_CS_META_RIG_FIX)
        n_fix = len(fix.get("controls") or {}) if isinstance(fix, dict) else 0
        fix_part = "  ·  rig fix: {} controls".format(n_fix) if n_fix else ""
        self.snapshot_status_label.setText(
            "<span style='color:#80c080;'>✔  <b>{}</b> — "
            "{} controls, {} pairs  (axis: {}){}{}</span>".format(
                pfx_label, n_ctrls, n_pairs, cs_snap.mirror_axis, flip_part,
                fix_part
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
        override → Troubleshoot Rig Setup fix → auto-detected from the
        default pose) is used directly (copy / negate / ignore). Controls the
        troubleshooter marked for matrix mirroring (axes that don't line up
        with the partner's) have their translate / rotate values solved
        through the stored frame matrices instead. Attributes with no stored
        rule — or no snapshot at all — run the original axis-vector
        heuristic.
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

        # Troubleshoot Rig Setup: controls whose axes don't line up with the
        # partner's are mirrored through the solved frame matrices.
        matrix_vals = {}
        if snapshot is not None:
            fix = snapshot.get_fix_entry(ctrl, partner)
            if fix and fix.get("mode") == RIG_FIX_MATRIX:
                matrix_vals = _mirror_values_with_fix(
                    fix, [a for a in data[ctrl] if a in _TR_ATTRS],
                    data[ctrl], data.get(partner, {}), _angle_to_degrees())

        for attr, value in data[ctrl].items():
            target = "{}.{}".format(partner, attr)

            if attr in matrix_vals and snapshot.get_override(ctrl, attr) not in RULES:
                mirrored = matrix_vals[attr]
                self.set_attr(target, -mirrored if flip_this_ctrl else mirrored)
                continue

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

    def _mirror_middle_attrs(self, ctrl, attrs, mirror_axis, snapshot=None):
        """Flip a centre control's pose across the mirror axis in place.

        Uses the Troubleshoot Rig Setup fix when one is stored for the
        control (exact rules, or matrix mirroring for controls whose axes
        don't line up with the world); otherwise the classic rule —
        negate translate on the mirror axis and every rotation.
        """
        fix = snapshot.get_fix_entry(ctrl, ctrl) if snapshot is not None else None
        matrix_vals = {}
        if fix and fix.get("mode") == RIG_FIX_MATRIX:
            matrix_vals = _mirror_values_with_fix(
                fix, [a for a in attrs if a in _TR_ATTRS], attrs, attrs,
                _angle_to_degrees())
        for attr, value in attrs.items():
            plug = "{}.{}".format(ctrl, attr)
            if fix:
                override = snapshot.get_override(ctrl, attr)
                if attr in matrix_vals and override not in RULES:
                    self.set_attr(plug, matrix_vals[attr])
                    continue
                rule = snapshot.get_rule(ctrl, attr)
                if rule == RULE_IGNORE:
                    continue
                if rule in (RULE_COPY, RULE_NEGATE):
                    self.set_attr(plug, -value if rule == RULE_NEGATE else value)
                    continue
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
                self._mirror_middle_attrs(ctrl, middle_data.get(ctrl, {}),
                                          mirror_axis, snapshot)
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

            "<h4>⑧ Troubleshoot Rig Setup</h4>"
            "<p>If hands, fingers or other controls still mirror wrong with a "
            "snapshot, click <b>Troubleshoot Rig Setup</b>. It puts the rig in "
            "its snapshot default pose, solves each control's exact mirror "
            "relationship from its transform frames (catching extra 180° "
            "offset groups, near-45° finger axes and oblique thumbs), probes "
            "custom attributes such as curls, verifies every result and then "
            "restores your pose. Review the corrections and click <b>Apply "
            "Fix</b> — it is stored in the Character Snapshot and used by "
            "every mirror operation. Use <i>Selected controls</i> to fix just "
            "one area, e.g. a hand.</p>"

            "<h4>⑨ Preserve Translation / Rotation</h4>"
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
            "<p style='color:#8ab4f8;'>Version 2.4.0</p>"
            "<p style='color:#888; font-size:10px;'>Formerly digetMirrorControl</p>"
            "<hr>"

            "<h4>Contributors</h4>"
            "<table cellpadding='2'>"
            "<tr><td style='color:#90c890;'>Original Author:</td>"
            "<td>Mikkel Diget Eriksen (2022)</td></tr>"
            "<tr><td style='color:#90c890;'>Updated by:</td>"
            "<td>David Shepstone</td></tr>"
            "</table>"

            "<h4>What's New in 2.4.0</h4>"
            "<ul>"
            "<li><b>Troubleshoot Rig Setup</b> — fixes rigs whose hands and "
            "fingers won't mirror even with a snapshot. Every control's exact "
            "mirror relationship is solved from its real transform frames, "
            "custom attributes such as curls are probed behaviourally, each "
            "result is verified in the scene and the fix is stored in the "
            "Character Snapshot.</li>"
            "<li><b>Matrix mirroring</b> for controls whose axes don't line "
            "up with their partner's (oblique thumbs, permuted axes, "
            "differing rotate orders).</li>"
            "</ul>"

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
