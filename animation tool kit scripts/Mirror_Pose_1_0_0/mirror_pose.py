"""Mirror Pose - flip a character's whole pose in one click.

Part of the Animation Tool Kit (ATK). Left and right controls swap their
poses, and centre controls (spine, chest, pelvis, neck, head, COG...) are
flipped across the character's mirror plane, so a run or walk pose becomes
its true mirror image.

How it works
------------
For every control the tool needs the frame its channels act in at the
rig's rest pose. It briefly puts the character in its rest pose (undo and
auto-key are suspended), samples each control's parent space, joint orient,
rotate axis and rotate order, then puts the pose back exactly as it was.

With those rest frames the mirror is exact rather than a guess per channel:

    rotation:     F_dst = F0_dst . S . F0_src^-1 . F_src . S
    translation:  dt_dst = dt_src . P_src . S . P_dst^-1

(row-vector convention, as Maya uses; S is the reflection across the
character's mirror plane, F the frame the rotate channels act in, P the
parent space the translate channels act in, 0 = rest pose.) The same
formula handles behaviour-mirrored rigs, orientation-mirrored rigs, rotated
joint orients and centre controls, so no per-rig set-up is needed.

The mirror plane is fitted from the rest positions of the left / right
pairs, so it is right even when the rig is built facing along X. Controls
at the top of the hierarchy that place the whole character in the shot
(world / global / main ...) are left where they are; mirroring them would
move the character instead of mirroring the pose.

Pairing uses the Character Snapshot tool's data when a snapshot exists for
the rig (manual pairs, exclusions, rest pose), and otherwise matches common
left / right name tokens (lf/rt, l/r, left/right, L_/R_, armL ...).

Usage
-----
    import mirror_pose
    mirror_pose.show()                 # the Mirror Pose window
    mirror_pose.mirror_pose()          # whole character of the selection
    mirror_pose.mirror_selected()      # only the selected controls (and
                                       # their partners)

Anything that stops the mirror is explained in a pop-up; nothing fails
silently.

Version: 1.0.0
"""

import math
import re

try:
    import maya.cmds as cmds
except ImportError:                     # pure-math helpers stay importable
    cmds = None

__version__ = "1.0.0"

TOOL_TITLE = "Mirror Pose"

_TRANSLATE = ("translateX", "translateY", "translateZ")
_ROTATE = ("rotateX", "rotateY", "rotateZ")
_SCALE = ("scaleX", "scaleY", "scaleZ")
_TRS = _TRANSLATE + _ROTATE + _SCALE

# Maya rotateOrder enum -> order the axes are applied in (row vectors:
# xyz applies X first).
ROTATE_ORDERS = {0: (0, 1, 2), 1: (1, 2, 0), 2: (2, 0, 1),
                 3: (0, 2, 1), 4: (1, 0, 2), 5: (2, 1, 0)}

# Left / right naming conventions tried when no Character Snapshot exists.
SIDE_TOKEN_PAIRS = [
    ("lf", "rt"), ("lt", "rt"), ("lf", "rf"), ("l", "r"),
    ("left", "right"), ("lft", "rgt"),
]

# Name hints for controls that place the whole character in the shot.
PLACEMENT_HINTS = ("world", "global", "master", "placement", "main", "local",
                   "god", "root", "traj", "all")

# A control above at least this share of the character's other controls is
# treated as a placement control (if its name or position says so).
_PLACEMENT_COVERAGE = 0.8

# Snap the fitted mirror plane to a world axis when within this many degrees.
_AXIS_SNAP_DEG = 5.0


# ---------------------------------------------------------------------------
# 3x3 matrix helpers (lists of rows, row-vector convention)
# ---------------------------------------------------------------------------

def m3_identity():
    return [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]


def m3_mul(*mats):
    out = mats[0]
    for b in mats[1:]:
        a = out
        out = [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)]
               for i in range(3)]
    return out


def m3_det(m):
    return (m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
            - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
            + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]))


def m3_inv(m):
    d = m3_det(m)
    if abs(d) < 1e-12:
        return None
    c = [[0.0] * 3 for _ in range(3)]
    for i in range(3):
        for j in range(3):
            r = [x for x in range(3) if x != j]
            s = [x for x in range(3) if x != i]
            minor = m[r[0]][s[0]] * m[r[1]][s[1]] - m[r[0]][s[1]] * m[r[1]][s[0]]
            c[i][j] = ((-1) ** (i + j)) * minor / d
    return c


def m3_from_m4(m16):
    """Upper-left 3x3 of a flat 16-value Maya matrix."""
    return [list(m16[0:3]), list(m16[4:7]), list(m16[8:11])]


def m3_normalize_rows(m):
    out = []
    for row in m:
        length = math.sqrt(sum(v * v for v in row)) or 1.0
        out.append([v / length for v in row])
    return out


def vec_mul_m3(v, m):
    return [sum(v[i] * m[i][j] for i in range(3)) for j in range(3)]


def reflection(normal):
    """Reflection across the plane through the origin with this normal."""
    n = list(normal)
    length = math.sqrt(sum(v * v for v in n)) or 1.0
    n = [v / length for v in n]
    return [[(1.0 if i == j else 0.0) - 2.0 * n[i] * n[j] for j in range(3)]
            for i in range(3)]


def _axis_rot(axis, angle_rad):
    c, s = math.cos(angle_rad), math.sin(angle_rad)
    if axis == 0:
        return [[1.0, 0.0, 0.0], [0.0, c, s], [0.0, -s, c]]
    if axis == 1:
        return [[c, 0.0, -s], [0.0, 1.0, 0.0], [s, 0.0, c]]
    return [[c, s, 0.0], [-s, c, 0.0], [0.0, 0.0, 1.0]]


def euler_to_m3(angles_deg, rotate_order=0):
    """Maya Euler angles (degrees) for a rotateOrder -> 3x3 matrix."""
    m = m3_identity()
    for axis in ROTATE_ORDERS.get(rotate_order, (0, 1, 2)):
        m = m3_mul(m, _axis_rot(axis, math.radians(angles_deg[axis])))
    return m


def _closest_turn(value, hint):
    return value + 360.0 * round((hint - value) / 360.0)


def m3_to_euler(m, rotate_order=0, hint=None):
    """3x3 rotation -> Maya Euler angles (degrees) for a rotateOrder.

    Of the two equivalent solutions, and their 360 degree turns, the one
    closest to *hint* (the control's current values) is returned so
    animation curves don't jump.
    """
    i, j, k = ROTATE_ORDERS.get(rotate_order, (0, 1, 2))
    # Column-vector form of the same rotation: Rk . Rj . Ri.
    q = [[m[c][r] for c in range(3)] for r in range(3)]
    parity = 1.0 if (i, j, k) in ((0, 1, 2), (1, 2, 0), (2, 0, 1)) else -1.0
    cos_b = math.sqrt(q[k][j] ** 2 + q[k][k] ** 2)
    b = math.atan2(-parity * q[k][i], cos_b)
    if cos_b > 1e-9:
        a = math.atan2(parity * q[k][j], q[k][k])
        c = math.atan2(parity * q[j][i], q[i][i])
    else:                                       # gimbal lock
        c = 0.0
        a = math.atan2(-parity * q[j][k], q[j][j])
    ref = list(hint) if hint is not None else [0.0, 0.0, 0.0]
    best, best_dist = None, None
    for sa, sb, sc in ((a, b, c), (a + math.pi, math.pi - b, c + math.pi)):
        vals = [0.0, 0.0, 0.0]
        vals[i], vals[j], vals[k] = (math.degrees(sa), math.degrees(sb),
                                     math.degrees(sc))
        vals = [_closest_turn(v, h) for v, h in zip(vals, ref)]
        dist = sum(abs(v - h) for v, h in zip(vals, ref))
        if best is None or dist < best_dist - 1e-9:
            best, best_dist = vals, dist
    return best


# ---------------------------------------------------------------------------
# Mirror math
# ---------------------------------------------------------------------------

def rest_frame(sample):
    """Frame the rotate channels act in at rest: Ra . R(r0) . B."""
    return m3_mul(sample["ra"], euler_to_m3(sample["r0"], sample["ro"]),
                  sample["base"])


def mirror_rotation(src_rot, src, dst, S, hint=None):
    """Rotate values for *dst* that mirror *src* posed at *src_rot*.

    *src* / *dst* are rest samples: {"base": JO . parent rotation,
    "ra": rotate-axis matrix, "ro": rotateOrder, "r0": rest rotate}.
    For a centre control pass the same sample twice.
    """
    f_src = m3_mul(src["ra"], euler_to_m3(src_rot, src["ro"]), src["base"])
    f0_src_inv = m3_inv(rest_frame(src))
    base_dst_inv = m3_inv(dst["base"])
    ra_dst_inv = m3_inv(dst["ra"])
    if f0_src_inv is None or base_dst_inv is None or ra_dst_inv is None:
        return None
    r_dst = m3_mul(ra_dst_inv, rest_frame(dst), S, f0_src_inv, f_src, S,
                   base_dst_inv)
    return m3_to_euler(r_dst, dst["ro"], hint)


def mirror_translation(src_t, src, dst, S):
    """Translate values for *dst* that mirror *src* at *src_t*.

    The move away from the rest pose is taken into world space through the
    source's rest parent space, reflected, and brought back through the
    destination's.
    """
    p_dst_inv = m3_inv(dst["parent"])
    if p_dst_inv is None:
        return None
    delta = [src_t[i] - src["t0"][i] for i in range(3)]
    moved = vec_mul_m3(delta, m3_mul(src["parent"], S, p_dst_inv))
    return [dst["t0"][i] + moved[i] for i in range(3)]


def fit_mirror_normal(pair_positions):
    """Mirror-plane normal from rest positions of (left, right) pairs.

    Falls back to world X when there are no usable pairs, and snaps to the
    nearest world axis when the fitted normal is within a few degrees of it.
    """
    total = [0.0, 0.0, 0.0]
    for left, right in pair_positions:
        d = [left[i] - right[i] for i in range(3)]
        length = math.sqrt(sum(v * v for v in d))
        if length < 1e-6:
            continue
        if total != [0.0, 0.0, 0.0] and sum(d[i] * total[i] for i in range(3)) < 0:
            d = [-v for v in d]
        total = [total[i] + d[i] / length for i in range(3)]
    length = math.sqrt(sum(v * v for v in total))
    if length < 1e-6:
        return [1.0, 0.0, 0.0]
    n = [v / length for v in total]
    axis = max(range(3), key=lambda a: abs(n[a]))
    if abs(n[axis]) >= math.cos(math.radians(_AXIS_SNAP_DEG)):
        n = [0.0, 0.0, 0.0]
        n[axis] = 1.0
    return n


# ---------------------------------------------------------------------------
# Naming
# ---------------------------------------------------------------------------

def base_name(node):
    """Leaf name without DAG path or namespace."""
    return node.split("|")[-1].split(":")[-1]


def namespace_of(node):
    leaf = node.split("|")[-1]
    return leaf.rsplit(":", 1)[0] if ":" in leaf else ""


def _match_case(sample, word):
    if sample.isupper():
        return word.upper()
    if sample[0].isupper():
        return word.capitalize()
    return word.lower()


def _token_spans(name, token):
    """Spans where *token* is a whole side token in *name*.

    '_' / string edges match any case (lf_arm, arm_L, L_arm); camelCase
    edges match Title or UPPER case tokens of two or more letters
    (armLeft, handLF_ctrl) and upper-case single-letter suffixes (armL,
    handR_ctrl), so 'rt' inside 'shirt' never matches.
    """
    spans = []
    pat = r"(?:(?<=_)|(?<=\A))" + re.escape(token) + r"(?=_|\Z)"
    for m in re.finditer(pat, name, re.IGNORECASE):
        spans.append(m.span())
    if len(token) >= 2:
        for variant in {token.capitalize(), token.upper()}:
            pat = r"(?<=[a-z0-9])" + re.escape(variant) + r"(?=[A-Z0-9_]|\Z)"
            for m in re.finditer(pat, name):
                if m.span() not in spans:
                    spans.append(m.span())
    else:
        # Single-letter camelCase suffix: armL, handR_ctrl, legL1.
        pat = r"(?<=[a-z])" + re.escape(token.upper()) + r"(?=[0-9_]|\Z)"
        for m in re.finditer(pat, name):
            if m.span() not in spans:
                spans.append(m.span())
    return sorted(spans)


def side_of(name):
    """'left', 'right' or 'middle' from a control's base name."""
    for left, right in SIDE_TOKEN_PAIRS:
        has_l = bool(_token_spans(name, left))
        has_r = bool(_token_spans(name, right))
        if has_l != has_r:
            return "left" if has_l else "right"
    return "middle"


def partner_candidates(name):
    """Possible mirror names for *name*, best guess first."""
    out = []
    for left, right in SIDE_TOKEN_PAIRS:
        for tok, other in ((left, right), (right, left)):
            for start, end in _token_spans(name, tok):
                cand = name[:start] + _match_case(name[start:end], other) + name[end:]
                if cand != name and cand not in out:
                    out.append(cand)
    return out


def is_placement_name(name):
    """True for names such as world_ctrl, Main, global01_ctl or worldCtrl.

    Each '_' segment (digits ignored) is compared whole, or by its first
    camelCase word, so 'spine_pelvisMain_ctrl' is not a placement name.
    """
    for seg in name.split("_"):
        seg = re.sub(r"\d+", "", seg)
        if not seg:
            continue
        first = re.match(r"[A-Za-z][a-z]*", seg)
        words = {seg.lower(), first.group(0).lower() if first else ""}
        if words & set(PLACEMENT_HINTS):
            return True
    return False


# ---------------------------------------------------------------------------
# Failure report
# ---------------------------------------------------------------------------

def _show_report(title, problems, details="", icon="warning"):
    """Pop up why the mirror stopped (or what it skipped).

    The text also goes to the Script Editor, and a one-line warning to
    Maya's command line.
    """
    problems = [p for p in problems if p] or ["Unknown reason (see Script Editor)."]
    LAST_REPORT.append(title + ":")
    LAST_REPORT.extend(problems)
    lines = ["{}: {}".format(TOOL_TITLE, title), ""]
    lines += ["  - {}".format(p) for p in problems]
    if details:
        lines += ["", details]
    print("\n" + "=" * 70 + "\n" + "\n".join(lines) + "\n" + "=" * 70)
    try:
        cmds.warning("{}: {} {}".format(TOOL_TITLE, title, problems[0]))
    except Exception:
        pass
    try:
        if cmds.about(batch=True):
            return
    except Exception:
        pass
    message = "\n\n".join(u"• {}".format(p) for p in problems)
    if details:
        message += "\n\n" + details
    try:
        cmds.confirmDialog(title="{} - {}".format(TOOL_TITLE, title),
                           message=message, button=["OK"], defaultButton="OK",
                           cancelButton="OK", dismissString="OK", icon=icon)
    except Exception:
        pass


def _in_view(message):
    try:
        cmds.inViewMessage(amg=message, pos="topCenter", fade=True,
                           fadeStayTime=1800)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Scene helpers
# ---------------------------------------------------------------------------

def _to_degrees():
    try:
        unit = cmds.currentUnit(query=True, angle=True) or "deg"
    except Exception:
        unit = "deg"
    return 180.0 / math.pi if unit.startswith("rad") else 1.0


def _curve_controls():
    """Every transform / joint that carries a NURBS curve shape."""
    out = []
    for shape in cmds.ls(type="nurbsCurve", long=True, noIntermediate=True) or []:
        for parent in cmds.listRelatives(shape, parent=True, fullPath=True) or []:
            if parent not in out:
                out.append(parent)
    return out


def _character_key(node):
    """Namespace, or the top DAG node for rigs without a namespace."""
    ns = namespace_of(node)
    if ns:
        return "ns:" + ns
    parts = [p for p in node.split("|") if p]
    return "root:" + (parts[0] if parts else node)


def _settable(plug):
    try:
        if not cmds.objExists(plug) or cmds.getAttr(plug, lock=True):
            return False
        inputs = cmds.listConnections(plug, source=True, destination=False,
                                      skipConversionNodes=True) or []
        return all(cmds.nodeType(n).startswith("animCurve") for n in inputs)
    except Exception:
        return False


def _numeric_attrs(ctrl):
    """Keyable scalar attributes (float / int / bool / enum)."""
    out = []
    for attr in cmds.listAttr(ctrl, keyable=True, scalar=True) or []:
        if attr == "visibility":
            continue
        try:
            if isinstance(cmds.getAttr("{}.{}".format(ctrl, attr)),
                          (int, float, bool)):
                out.append(attr)
        except Exception:
            continue
    return out


def _attr_default(ctrl, attr):
    if attr.startswith("scale"):
        fallback = 1.0
    else:
        fallback = 0.0
    try:
        values = cmds.attributeQuery(attr, node=ctrl, listDefault=True)
        if values:
            return float(values[0])
    except Exception:
        pass
    return fallback


def _load_snapshot(ctrl):
    """Character Snapshot for this control's rig, or None."""
    try:
        import character_snapshot_v1_0_0 as cs
    except Exception:
        return None
    try:
        prefix = cs.find_prefix_for_control(ctrl)
        return cs.load_snapshot(prefix) if prefix else None
    except Exception:
        return None


def _snapshot_defaults(snap, ctrl):
    if snap is None:
        return {}
    try:
        data = snap._control_data(ctrl) or {}
    except Exception:
        return {}
    return data.get("default_values") or {}


def _sample(ctrl, to_deg):
    """Rest-pose sample of the spaces a control's channels act in."""
    parents = cmds.listRelatives(ctrl, parent=True, fullPath=True) or []
    if parents:
        parent = m3_from_m4(cmds.xform(parents[0], query=True, worldSpace=True,
                                       matrix=True))
    else:
        parent = m3_identity()
    try:
        if cmds.attributeQuery("offsetParentMatrix", node=ctrl, exists=True):
            opm = cmds.getAttr("{}.offsetParentMatrix".format(ctrl))
            parent = m3_mul(m3_from_m4(opm), parent)
    except Exception:
        pass
    base = m3_normalize_rows(parent)
    ra = m3_identity()
    if cmds.nodeType(ctrl) == "joint":
        jo = cmds.getAttr("{}.jointOrient".format(ctrl))[0]
        base = m3_mul(euler_to_m3([v * to_deg for v in jo], 0), base)
    try:
        rax = cmds.getAttr("{}.rotateAxis".format(ctrl))[0]
        ra = euler_to_m3([v * to_deg for v in rax], 0)
    except Exception:
        pass
    return {
        "parent": parent,
        "base": base,
        "ra": ra,
        "ro": int(cmds.getAttr("{}.rotateOrder".format(ctrl)) or 0),
        "t0": [float(cmds.getAttr("{}.{}".format(ctrl, a))) for a in _TRANSLATE],
        "r0": [float(cmds.getAttr("{}.{}".format(ctrl, a))) * to_deg
               for a in _ROTATE],
        "pos": cmds.xform(ctrl, query=True, worldSpace=True, rotatePivot=True),
    }


# ---------------------------------------------------------------------------
# Character analysis
# ---------------------------------------------------------------------------

class _Character(object):
    """One character's controls, pairs, centres and placement controls."""

    def __init__(self, controls, snapshot, keep_placement=True,
                 flip_one_sided=True):
        self.controls = list(controls)
        self.snapshot = snapshot
        self.flip_one_sided = flip_one_sided
        self.by_leaf = {c.split("|")[-1]: c for c in self.controls}
        self.by_base = {}
        for c in self.controls:
            self.by_base.setdefault(base_name(c), c)
        self.partner = {}
        self.centres = []
        self.unmatched = []
        self.excluded = []
        self.placement = self._find_placement() if keep_placement else []
        self._pair_up()

    def _excluded(self, ctrl):
        try:
            return bool(self.snapshot and self.snapshot.is_excluded(ctrl))
        except Exception:
            return False

    def _find_partner(self, ctrl):
        if self.snapshot is not None:
            try:
                found = self.snapshot.find_partner_in_scene(ctrl)
            except Exception:
                found = None
            if found:
                hit = (self.by_leaf.get(found.split("|")[-1])
                       or self.by_base.get(base_name(found)))
                if hit and hit != ctrl:
                    return hit
        ns = namespace_of(ctrl)
        for cand in partner_candidates(base_name(ctrl)):
            hit = (self.by_leaf.get((ns + ":" if ns else "") + cand)
                   or self.by_base.get(cand))
            if hit and hit != ctrl:
                return hit
        return None

    def _find_placement(self):
        """Top-of-hierarchy controls that place the character in the shot."""
        others = len(self.controls) - 1
        out = []
        if others <= 0:
            return out
        for ctrl in self.controls:
            prefix = ctrl + "|"
            below = sum(1 for c in self.controls if c.startswith(prefix))
            if below < _PLACEMENT_COVERAGE * others:
                continue
            above = any(ctrl.startswith(c + "|") for c in self.controls)
            if not above or is_placement_name(base_name(ctrl)):
                out.append(ctrl)
        return out

    def _pair_up(self):
        for ctrl in self.controls:
            if ctrl in self.placement:
                continue
            if self._excluded(ctrl):
                self.excluded.append(ctrl)
                continue
            if ctrl in self.partner:
                continue
            partner = self._find_partner(ctrl)
            if partner and partner not in self.partner \
                    and partner not in self.placement \
                    and not self._excluded(partner):
                self.partner[ctrl] = partner
                self.partner[partner] = ctrl
            elif side_of(base_name(ctrl)) == "middle":
                self.centres.append(ctrl)
            else:
                # One-sided parts with no partner (a hair strand only on the
                # right) flip in place like centre controls, unless turned off.
                self.unmatched.append(ctrl)
                if self.flip_one_sided:
                    self.centres.append(ctrl)

    def left_right_pairs(self):
        done, out = set(), []
        for a, b in self.partner.items():
            if a in done:
                continue
            done.update((a, b))
            if side_of(base_name(a)) == "right" or side_of(base_name(b)) == "left":
                a, b = b, a
            out.append((a, b))
        return out


# ---------------------------------------------------------------------------
# Main entry points
# ---------------------------------------------------------------------------

_OPT_AXIS = "atkMirrorPose_axis"
_OPT_KEEP_PLACEMENT = "atkMirrorPose_keepPlacement"
_OPT_FLIP_ONE_SIDED = "atkMirrorPose_flipOneSided"
AXIS_CHOICES = ("Auto", "X", "Y", "Z")

# Lines describing the last run, shown in the window's status area.
LAST_REPORT = []


def get_options():
    """Saved options: {"axis", "keep_placement", "flip_one_sided"}."""
    opts = {"axis": "Auto", "keep_placement": True, "flip_one_sided": True}
    try:
        if cmds.optionVar(exists=_OPT_AXIS):
            axis = cmds.optionVar(query=_OPT_AXIS)
            if axis in AXIS_CHOICES:
                opts["axis"] = axis
        for key, var in (("keep_placement", _OPT_KEEP_PLACEMENT),
                         ("flip_one_sided", _OPT_FLIP_ONE_SIDED)):
            if cmds.optionVar(exists=var):
                opts[key] = bool(cmds.optionVar(query=var))
    except Exception:
        pass
    return opts


def set_options(axis=None, keep_placement=None, flip_one_sided=None):
    try:
        if axis in AXIS_CHOICES:
            cmds.optionVar(stringValue=(_OPT_AXIS, axis))
        if keep_placement is not None:
            cmds.optionVar(intValue=(_OPT_KEEP_PLACEMENT, int(keep_placement)))
        if flip_one_sided is not None:
            cmds.optionVar(intValue=(_OPT_FLIP_ONE_SIDED, int(flip_one_sided)))
    except Exception:
        pass


def mirror_pose():
    """Mirror the whole pose of every character with a selected control."""
    return _run(selected_only=False)


def mirror_selected():
    """Mirror only the selected controls (pairs swap, centres flip)."""
    return _run(selected_only=True)


def _gather_characters(selection):
    """{character key: [controls]} for the characters in the selection."""
    all_ctrls = _curve_controls()
    keys = []
    for node in selection:
        key = _character_key(node)
        if key not in keys:
            keys.append(key)
    out = {}
    for key in keys:
        ctrls = [c for c in all_ctrls if _character_key(c) == key]
        if ctrls:
            out[key] = ctrls
    return out


def _run(selected_only, options=None):
    del LAST_REPORT[:]
    opts = get_options()
    opts.update(options or {})
    try:
        return _mirror(selected_only, opts)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        reason = str(exc).strip() or exc.__class__.__name__
        _show_report("Could not mirror the pose",
                     ["Maya raised an error: {}".format(reason)],
                     "The pose was put back as it was. The full error is in "
                     "the Script Editor.")
        return None


def _mirror(selected_only, opts):
    selection = cmds.ls(selection=True, long=True, type="transform") or []
    if not selection:
        _show_report("Nothing selected", [
            "Select any control on the character you want to mirror, then "
            "click Mirror Pose again.",
        ], icon="information")
        return None

    characters = _gather_characters(selection)
    if not characters:
        _show_report("No rig controls found", [
            "The selection is not part of a rig with curve controls. Select "
            "a control (a NURBS curve) on the character.",
        ])
        return None

    to_deg = _to_degrees()
    sel_set = set(selection)
    summary, problems = [], []

    for key, controls in characters.items():
        snap = _load_snapshot(controls[0])
        char = _Character(controls, snap,
                          keep_placement=opts.get("keep_placement", True),
                          flip_one_sided=opts.get("flip_one_sided", True))
        if selected_only:
            targets = set()
            for c in controls:
                if c in sel_set:
                    targets.add(c)
                    if c in char.partner:
                        targets.add(char.partner[c])
        else:
            targets = set(char.partner) | set(char.centres)
        targets &= set(char.partner) | set(char.centres)
        if not targets:
            continue

        result = _mirror_character(char, targets, to_deg,
                                   axis=opts.get("axis", "Auto"))
        name = key.split(":", 1)[1]
        if result["written"]:
            summary.append("{}: {} control{} mirrored".format(
                name, result["written"], "" if result["written"] == 1 else "s"))
        if not char.partner:
            problems.append(
                "{}: no left / right pairs were found, so only centre controls "
                "were flipped. Check the side names (lf/rt, l/r, left/right) or "
                "add manual pairs in Character Snapshot.".format(name))
        # One-sided controls and locked / driven channels are normal on
        # production rigs: list them in the Script Editor, no pop-up.
        notes = []
        if char.unmatched:
            notes.append("{} one-sided control{} {} (no partner): {}".format(
                             len(char.unmatched),
                             "" if len(char.unmatched) == 1 else "s",
                             "flipped in place" if char.flip_one_sided
                             else "left as they were",
                             ", ".join(base_name(c) for c in char.unmatched)))
        if result["skipped"]:
            notes.append("{} locked or driven channel{} left as they were: "
                         "{}".format(len(result["skipped"]),
                                     "" if len(result["skipped"]) == 1 else "s",
                                     ", ".join(result["skipped"])))
        for note in notes:
            print("[{}] {}: {}".format(TOOL_TITLE, name, note))
        LAST_REPORT.append("{}: pairs from {}; {} pairs, {} centre / one-sided, "
                           "kept in place: {}".format(
                               name,
                               "Character Snapshot + names" if snap else "names",
                               len(char.left_right_pairs()), len(char.centres),
                               ", ".join(base_name(c) for c in char.placement)
                               or "none"))
        for note in notes:
            LAST_REPORT.append("{}: {}".format(name, note))
        if result["failed"]:
            problems.append("{}: could not solve the mirror for {}".format(
                name, ", ".join(base_name(c) for c in result["failed"][:6])))
        print("[{}] {}: pairs from {}, plane normal {}, {} pairs, {} centres, "
              "kept in place: {}".format(
                          TOOL_TITLE, name,
                          "Character Snapshot + names" if snap else "names",
                          [round(v, 3) for v in result["normal"]],
                          len(char.left_right_pairs()), len(char.centres),
                          ", ".join(base_name(c) for c in char.placement)
                          or "none"))

    if not summary and problems:
        _show_report("Could not mirror the pose", problems)
        return None
    if not summary:
        _show_report("Nothing to mirror", [
            "None of the selected controls has a mirror partner or is a centre "
            "control." if selected_only else
            "No mirrorable controls were found on the selected character.",
        ])
        return None

    LAST_REPORT[:0] = summary
    _in_view("<hl>Mirror Pose</hl>  " + "; ".join(summary))
    if problems:
        _show_report("Mirrored with warnings", problems,
                     "Undo (Ctrl+Z) puts the original pose back.")
    return summary


def _mirror_character(char, targets, to_deg, axis="Auto"):
    """Sample the rest pose, solve and write the mirrored pose.

    Auto-key is put back to the user's setting whatever happens.
    """
    auto_key = cmds.autoKeyframe(query=True, state=True)
    try:
        return _mirror_character_inner(char, targets, to_deg, auto_key, axis)
    finally:
        cmds.autoKeyframe(state=auto_key)


def _mirror_character_inner(char, targets, to_deg, auto_key, axis="Auto"):
    controls = char.controls
    # 1. Current pose of every control (and the values to restore).
    current = {}
    for ctrl in controls:
        values = {}
        for attr in _numeric_attrs(ctrl):
            try:
                values[attr] = cmds.getAttr("{}.{}".format(ctrl, attr))
            except Exception:
                continue
        current[ctrl] = values
    rotate_now = {c: [float(cmds.getAttr("{}.{}".format(c, a))) * to_deg
                      for a in _ROTATE] for c in controls}
    translate_now = {c: [float(cmds.getAttr("{}.{}".format(c, a)))
                         for a in _TRANSLATE] for c in controls}

    # 2. Rest pose: sample, then restore. Undo and auto-key are off so the
    #    round trip leaves no trace.
    undo_on = cmds.undoInfo(query=True, state=True)
    samples = {}
    changed = {}
    rest_values = {}
    cmds.autoKeyframe(state=False)
    cmds.undoInfo(stateWithoutFlush=False)
    try:
        for ctrl in controls:
            defaults = _snapshot_defaults(char.snapshot, ctrl)
            rest_values[ctrl] = rest = {}
            for attr in _TRS:
                if attr not in current[ctrl]:
                    continue
                value = defaults.get(attr)
                if value is None:
                    value = _attr_default(ctrl, attr)
                rest[attr] = float(value)
                plug = "{}.{}".format(ctrl, attr)
                if abs(float(current[ctrl][attr]) - rest[attr]) > 1e-9 \
                        and _settable(plug):
                    changed[plug] = current[ctrl][attr]
                    cmds.setAttr(plug, rest[attr])
        for ctrl in controls:
            try:
                smp = _sample(ctrl, to_deg)
            except Exception:
                continue
            # A locked channel that could not go to rest still counts as
            # being at rest, so its offset is mirrored like any other.
            rest = rest_values.get(ctrl, {})
            for i, attr in enumerate(_TRANSLATE):
                if attr in rest:
                    smp["t0"][i] = rest[attr]
            for i, attr in enumerate(_ROTATE):
                if attr in rest:
                    smp["r0"][i] = rest[attr] * to_deg
            samples[ctrl] = smp
    finally:
        for plug, value in changed.items():
            try:
                cmds.setAttr(plug, value)
            except Exception:
                pass
        cmds.undoInfo(stateWithoutFlush=undo_on)

    pair_pos = [(samples[a]["pos"], samples[b]["pos"])
                for a, b in char.left_right_pairs()
                if a in samples and b in samples]
    if axis in ("X", "Y", "Z"):
        normal = [1.0 if a == axis else 0.0 for a in "XYZ"]
    else:
        normal = fit_mirror_normal(pair_pos)
    S = reflection(normal)

    # 3. Solve every target from the captured pose.
    plan, failed = {}, []
    for dst in targets:
        src = char.partner.get(dst, dst)
        if src not in samples or dst not in samples:
            failed.append(dst)
            continue
        new = {}
        rot = mirror_rotation(rotate_now[src], samples[src], samples[dst], S,
                              hint=rotate_now[dst])
        trn = mirror_translation(translate_now[src], samples[src],
                                 samples[dst], S)
        if rot is None or trn is None:
            failed.append(dst)
            continue
        for i, attr in enumerate(_ROTATE):
            new[attr] = rot[i] / to_deg
        for i, attr in enumerate(_TRANSLATE):
            new[attr] = trn[i]
        if src != dst:
            # Scale and custom attributes (curls, IK/FK, foot roll ...) swap.
            for attr, value in current[src].items():
                if attr in _TRANSLATE or attr in _ROTATE:
                    continue
                if attr in current[dst]:
                    new[attr] = value
        plan[dst] = new

    # 4. Write in one undo chunk, keying like auto-key would.
    skipped, set_plugs = [], []
    cmds.undoInfo(openChunk=True, chunkName="Mirror Pose")
    try:
        cmds.autoKeyframe(state=False)
        for dst, values in plan.items():
            for attr, value in values.items():
                plug = "{}.{}".format(dst, attr)
                old = current[dst].get(attr)
                if old is not None and abs(float(old) - float(value)) < 1e-7:
                    continue
                if not _settable(plug):
                    if attr in current[dst]:
                        skipped.append("{}.{}".format(base_name(dst), attr))
                    continue
                try:
                    if isinstance(old, bool):
                        value = bool(round(value))
                    elif isinstance(old, int):
                        value = int(round(value))
                    cmds.setAttr(plug, value)
                    set_plugs.append(plug)
                except Exception:
                    skipped.append("{}.{}".format(base_name(dst), attr))
        if auto_key:
            for plug in set_plugs:
                try:
                    if cmds.keyframe(plug, query=True, keyframeCount=True):
                        cmds.setKeyframe(plug)
                except Exception:
                    pass
    finally:
        cmds.autoKeyframe(state=auto_key)
        cmds.undoInfo(closeChunk=True)

    return {"written": len(plan), "skipped": skipped, "failed": failed,
            "normal": normal}


# ---------------------------------------------------------------------------
# Window
# ---------------------------------------------------------------------------

WINDOW_OBJECT_NAME = "atkMirrorPoseWindow"

_STYLE = """
QDialog { background-color: #2b2b2b; color: #d4d4d4; font-size: 12px; }
QLabel { color: #d4d4d4; background: transparent; }
QLabel#title { font-size: 15px; font-weight: bold; color: #ffffff; }
QLabel#hint { color: #9a9a9a; font-size: 11px; }
QGroupBox { border: 1px solid #444; border-radius: 6px; margin-top: 10px;
            padding: 8px 8px 6px 8px; color: #FFB74D; font-weight: bold; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
QComboBox, QPlainTextEdit { background-color: #363636; color: #e0e0e0;
            border: 1px solid #555; border-radius: 4px; padding: 3px 6px; }
QCheckBox { color: #d4d4d4; }
QPushButton { background-color: #4a4a4a; color: #e8e8e8; border: 1px solid #5c5c5c;
              border-radius: 5px; padding: 6px 12px; }
QPushButton:hover { background-color: #5a5a5a; }
QPushButton#primary { background-color: #3d7fc4; border-color: #4f93d8;
                      font-size: 14px; font-weight: bold; padding: 10px; }
QPushButton#primary:hover { background-color: #4a8fd6; }
"""


def _snapshot_status():
    """One line on where pairs will come from for the current selection."""
    try:
        sel = cmds.ls(selection=True, long=True, type="transform") or []
    except Exception:
        sel = []
    if not sel:
        return "Select a control on the character to mirror."
    snap = _load_snapshot(sel[0])
    ns = namespace_of(sel[0]) or "this rig"
    if snap is not None:
        return ("Character Snapshot found for {}: its manual pairs, exclusions "
                "and rest pose are used.".format(ns))
    return ("No Character Snapshot for {}: pairs come from the control "
            "names (L_/R_, lf/rt, left/right ...).".format(ns))


def _maya_main_window(QtWidgets):
    try:
        import maya.OpenMayaUI as omui
        from shiboken6 import wrapInstance
        ptr = omui.MQtUtil.mainWindow()
        return wrapInstance(int(ptr), QtWidgets.QWidget) if ptr else None
    except Exception:
        return None


def _build_window():
    from PySide6 import QtCore, QtWidgets

    class MirrorPoseWindow(QtWidgets.QDialog):
        def __init__(self, parent=None):
            super(MirrorPoseWindow, self).__init__(parent)
            self.setObjectName(WINDOW_OBJECT_NAME)
            self.setWindowTitle("Mirror Pose  v{}".format(__version__))
            self.setWindowFlags(self.windowFlags() | QtCore.Qt.Tool)
            self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
            self.setStyleSheet(_STYLE)
            self.setMinimumWidth(380)
            self._build()
            self._load_options()
            self.refresh_status()

        def _build(self):
            lay = QtWidgets.QVBoxLayout(self)
            title = QtWidgets.QLabel("Mirror Pose")
            title.setObjectName("title")
            hint = QtWidgets.QLabel(
                "Left and right swap, and the spine, pelvis, chest, neck and "
                "head flip, so a run or walk pose becomes its mirror image.")
            hint.setObjectName("hint")
            hint.setWordWrap(True)
            lay.addWidget(title)
            lay.addWidget(hint)

            self.mirror_btn = QtWidgets.QPushButton("Mirror Whole Pose")
            self.mirror_btn.setObjectName("primary")
            self.mirror_btn.clicked.connect(lambda: self._run(False))
            self.selected_btn = QtWidgets.QPushButton("Mirror Selected Controls Only")
            self.selected_btn.clicked.connect(lambda: self._run(True))
            lay.addWidget(self.mirror_btn)
            lay.addWidget(self.selected_btn)

            box = QtWidgets.QGroupBox("Options")
            form = QtWidgets.QGridLayout(box)
            form.addWidget(QtWidgets.QLabel("Mirror axis:"), 0, 0)
            self.axis_cb = QtWidgets.QComboBox()
            self.axis_cb.addItems(["Auto", "X", "Y", "Z"])
            self.axis_cb.setToolTip(
                "Auto finds the mirror plane from the rig's left / right "
                "pairs. Pick X, Y or Z to force a world axis.")
            form.addWidget(self.axis_cb, 0, 1)
            self.placement_chk = QtWidgets.QCheckBox(
                "Keep world / main controls in place")
            self.placement_chk.setToolTip(
                "Controls that place the whole character (world, global, "
                "main ...) are not mirrored, so the character stays where it is.")
            self.one_sided_chk = QtWidgets.QCheckBox(
                "Flip one-sided controls in place")
            self.one_sided_chk.setToolTip(
                "Controls with a side name but no partner (hair only on one "
                "side) flip in place like the spine. Off: they keep their pose.")
            form.addWidget(self.placement_chk, 1, 0, 1, 2)
            form.addWidget(self.one_sided_chk, 2, 0, 1, 2)
            for w in (self.axis_cb, self.placement_chk, self.one_sided_chk):
                sig = (w.currentIndexChanged if isinstance(w, QtWidgets.QComboBox)
                       else w.toggled)
                sig.connect(self._save_options)
            lay.addWidget(box)

            pairing = QtWidgets.QGroupBox("Pairing")
            pl = QtWidgets.QVBoxLayout(pairing)
            self.snap_lbl = QtWidgets.QLabel()
            self.snap_lbl.setWordWrap(True)
            row = QtWidgets.QHBoxLayout()
            refresh = QtWidgets.QPushButton("Refresh")
            refresh.clicked.connect(self.refresh_status)
            snap_btn = QtWidgets.QPushButton("Open Character Snapshot")
            snap_btn.setToolTip("Take a snapshot or add manual pairs for "
                                "controls whose names don't match.")
            snap_btn.clicked.connect(self._open_snapshot)
            row.addWidget(refresh)
            row.addWidget(snap_btn)
            pl.addWidget(self.snap_lbl)
            pl.addLayout(row)
            lay.addWidget(pairing)

            self.report = QtWidgets.QPlainTextEdit()
            self.report.setReadOnly(True)
            self.report.setPlaceholderText("The result of each run shows here.")
            self.report.setMinimumHeight(110)
            lay.addWidget(self.report)

        def _load_options(self):
            opts = get_options()
            self.axis_cb.setCurrentText(opts["axis"])
            self.placement_chk.setChecked(opts["keep_placement"])
            self.one_sided_chk.setChecked(opts["flip_one_sided"])

        def _save_options(self, *args):
            set_options(axis=self.axis_cb.currentText(),
                        keep_placement=self.placement_chk.isChecked(),
                        flip_one_sided=self.one_sided_chk.isChecked())

        def refresh_status(self):
            self.snap_lbl.setText(_snapshot_status())

        def _run(self, selected_only):
            self._save_options()
            _run(selected_only)
            self.report.setPlainText("\n".join(LAST_REPORT))
            self.refresh_status()

        def _open_snapshot(self):
            try:
                import character_snapshot_v1_0_0 as cs
                cs.show_dialog()
            except Exception as exc:
                _show_report("Could not open Character Snapshot", [
                    "The Character Snapshot tool is not installed or failed "
                    "to open: {}".format(exc)])

    return MirrorPoseWindow


_window = None


def show():
    """Open the Mirror Pose window (toolbar button)."""
    global _window
    try:
        from PySide6 import QtWidgets
        for widget in QtWidgets.QApplication.allWidgets():
            if widget.objectName() == WINDOW_OBJECT_NAME:
                widget.close()
        window_cls = _build_window()
        _window = window_cls(parent=_maya_main_window(QtWidgets))
        _window.show()
        _window.raise_()
        _window.activateWindow()
        return _window
    except Exception as exc:
        import traceback
        traceback.print_exc()
        _show_report("Could not open the window", [
            "Maya raised an error: {}".format(str(exc).strip() or
                                              exc.__class__.__name__)],
            "Right-click the toolbar button and choose Mirror Whole Pose to "
            "mirror without the window.")
        return None
