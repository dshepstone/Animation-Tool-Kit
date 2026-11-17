"""Key Cleanup - tidy animation curves before polish or hand-off.

Four clean-up passes for the selected controls (or the whole scene):

    remove_redundant_keys()   delete keys that sit inside a flat hold
    delete_static_channels()  delete curves whose keys never change value
    snap_keys_to_frames()     move sub-frame keys onto whole frames
    euler_filter()            remove 360-degree rotation flips

Each pass is one undo step and reports what it changed.  ``show()`` opens the
window; every pass can also be called directly or bound to a hotkey:

    import key_cleanup
    key_cleanup.remove_redundant_keys()

From the ATK Toolbar the passes are also in the button's right-click menu.
"""

from __future__ import absolute_import, division, print_function

import maya.cmds as cmds
from maya import OpenMayaUI as omui

try:
    from PySide6 import QtCore, QtWidgets
    from shiboken6 import wrapInstance
except ImportError:  # Maya 2022-2024
    from PySide2 import QtCore, QtWidgets
    from shiboken2 import wrapInstance

TOOL_NAME = "Key Cleanup"
TOOL_VERSION = "1.0.0"
WINDOW_OBJECT_NAME = "atkKeyCleanupUI"

# Time-driven curves only.  Driven-key curves (animCurveU*) belong to the rig.
TIME_CURVE_TYPES = ("animCurveTL", "animCurveTA", "animCurveTT", "animCurveTU")

DEFAULT_TOLERANCE = 0.001
_FLAT_ANGLE = 0.05          # degrees; a tangent flatter than this is "flat"
_ROTATE_ATTRS = ("rotateX", "rotateY", "rotateZ")


# ---------------------------------------------------------------------------
# Pure helpers (no Maya calls - covered by the unit tests)
# ---------------------------------------------------------------------------

def redundant_key_indices(values, in_flat, out_flat, tolerance=DEFAULT_TOLERANCE):
    """Return the indices of keys that add nothing to a curve.

    A key is redundant when it sits inside a truly flat hold: it has the same
    value as the keys on either side, and both curve segments it touches are
    flat.  That means the previous key's out tangent, this key's in and out
    tangents, and the next key's in tangent must all be flat.  Equal values
    alone are not enough: a sloped tangent on a neighbour bends the curve
    through this key, and removing it would change the motion.

    ``in_flat`` / ``out_flat`` hold one boolean per key.  The first and last
    key of every hold are kept, which keeps the hold's length and the timing
    of the moves on either side of it.
    """
    count = len(values)
    if len(in_flat) != count or len(out_flat) != count:
        return []
    redundant = []
    for i in range(1, count - 1):
        if abs(values[i] - values[i - 1]) > tolerance:
            continue
        if abs(values[i] - values[i + 1]) > tolerance:
            continue
        if not (out_flat[i - 1] and in_flat[i] and out_flat[i] and in_flat[i + 1]):
            continue
        redundant.append(i)
    return redundant


def is_static(values, in_flat=None, out_flat=None, tolerance=DEFAULT_TOLERANCE):
    """True when the curve never changes value.

    Every key must hold the same value (within ``tolerance``) *and*, when
    there is more than one key, every tangent must be flat: equal key values
    joined by sloped tangents still move between the keys.  Pass the tangent
    flags whenever they are known; without them a multi-key curve is never
    reported as static.
    """
    if not values:
        return False
    if max(values) - min(values) > tolerance:
        return False
    if len(values) == 1:
        return True
    if in_flat is None or out_flat is None:
        return False
    if len(in_flat) != len(values) or len(out_flat) != len(values):
        return False
    return all(in_flat) and all(out_flat)


def _tangent_flags(curve, count):
    """Return ``(in_flat, out_flat)`` for a curve, or ``(None, None)`` if unknown."""
    try:
        in_angles = cmds.keyTangent(curve, query=True, inAngle=True) or []
        out_angles = cmds.keyTangent(curve, query=True, outAngle=True) or []
    except Exception:
        return None, None
    if len(in_angles) != count or len(out_angles) != count:
        return None, None
    return ([abs(a) <= _FLAT_ANGLE for a in in_angles],
            [abs(a) <= _FLAT_ANGLE for a in out_angles])


def subframe_times(times, epsilon=1e-4):
    """Return the key times that do not sit on a whole frame."""
    return [t for t in times if abs(t - round(t)) > epsilon]


def in_range(time, time_range):
    """True when ``time`` is inside ``time_range`` (None = no limit)."""
    if time_range is None:
        return True
    return time_range[0] - 1e-6 <= time <= time_range[1] + 1e-6


# ---------------------------------------------------------------------------
# Scene queries
# ---------------------------------------------------------------------------

def target_curves(scope="selected"):
    """Return the editable time-based anim curves for ``scope``.

    ``"selected"`` uses the keys selected in the Graph Editor when there are
    any, otherwise every curve on the selected objects.  ``"scene"`` uses
    every time-based anim curve in the scene.
    """
    if scope == "scene":
        found = cmds.ls(type=TIME_CURVE_TYPES) or []
    else:
        found = cmds.keyframe(query=True, selected=True, name=True) or []
        if not found:
            for node in cmds.ls(selection=True) or []:
                try:
                    found.extend(cmds.keyframe(node, query=True, name=True) or [])
                except RuntimeError:
                    continue

    curves = []
    seen = set()
    for curve in found:
        if curve in seen:
            continue
        seen.add(curve)
        try:
            if cmds.nodeType(curve) not in TIME_CURVE_TYPES:
                continue
            if cmds.lockNode(curve, query=True, lock=True)[0]:
                continue
        except Exception:
            continue
        curves.append(curve)
    return curves


def playback_range():
    """Return the playback range as ``(start, end)``."""
    return (cmds.playbackOptions(query=True, minTime=True),
            cmds.playbackOptions(query=True, maxTime=True))


def timeline_selection_range():
    """Return the shift-dragged Time Slider range, or None when there is none."""
    try:
        import maya.mel as mel
        slider = mel.eval("$atkKeyCleanupTmp = $gPlayBackSlider")
        if not cmds.timeControl(slider, query=True, rangeVisible=True):
            return None
        start, end = cmds.timeControl(slider, query=True, rangeArray=True)
    except Exception:
        return None
    # rangeArray's end is the frame after the highlight.
    return (start, max(start, end - 1))


def _is_referenced(node):
    try:
        return bool(cmds.referenceQuery(node, isNodeReferenced=True))
    except Exception:
        return False


def _driven_plug(curve):
    plugs = cmds.listConnections(curve + ".output", plugs=True,
                                 source=False, destination=True) or []
    return plugs[0] if plugs else ""


class _UndoChunk(object):
    def __init__(self, name):
        self.name = name

    def __enter__(self):
        cmds.undoInfo(openChunk=True, chunkName=self.name)

    def __exit__(self, *exc):
        cmds.undoInfo(closeChunk=True)
        return False


def _report(message):
    print("Key Cleanup: " + message)
    try:
        cmds.inViewMessage(amg="<hl>Key Cleanup</hl>  " + message,
                           pos="midCenter", fade=True)
    except Exception:
        pass
    return message


def _no_curves(scope):
    if scope == "scene":
        message = "no animation curves in the scene."
    else:
        message = "select animated objects or Graph Editor keys first."
    cmds.warning("Key Cleanup: " + message)
    return message


# ---------------------------------------------------------------------------
# Clean-up passes
# ---------------------------------------------------------------------------

def remove_redundant_keys(scope="selected", time_range=None,
                          tolerance=DEFAULT_TOLERANCE, curves=None):
    """Delete keys that sit inside a flat hold.  Returns the number removed."""
    if curves is None:
        curves = target_curves(scope)
    if not curves:
        _no_curves(scope)
        return 0

    removed = 0
    touched = 0
    with _UndoChunk("ATKKeyCleanupRedundant"):
        for curve in curves:
            times = cmds.keyframe(curve, query=True, timeChange=True) or []
            values = cmds.keyframe(curve, query=True, valueChange=True) or []
            if len(times) < 3 or len(times) != len(values):
                continue
            in_flat, out_flat = _tangent_flags(curve, len(times))
            if in_flat is None:
                continue  # tangents unknown: never guess, keep every key
            doomed = [times[i] for i in redundant_key_indices(values, in_flat, out_flat, tolerance)
                      if in_range(times[i], time_range)]
            if not doomed:
                continue
            try:
                cmds.cutKey(curve, time=[(t, t) for t in doomed], clear=True)
            except RuntimeError as exc:
                cmds.warning("Key Cleanup: skipped {} ({})".format(curve, exc))
                continue
            removed += len(doomed)
            touched += 1

    _report("removed {} redundant key(s) on {} curve(s).".format(removed, touched))
    return removed


def delete_static_channels(scope="selected", tolerance=DEFAULT_TOLERANCE, curves=None):
    """Delete curves whose keys all hold one value.  Returns the number deleted.

    The attribute keeps its value; it just stops being animated.  Referenced
    curves are skipped (Maya cannot delete referenced nodes).
    """
    if curves is None:
        curves = target_curves(scope)
    if not curves:
        _no_curves(scope)
        return 0

    deleted = 0
    skipped = 0
    with _UndoChunk("ATKKeyCleanupStatic"):
        for curve in curves:
            values = cmds.keyframe(curve, query=True, valueChange=True) or []
            in_flat, out_flat = _tangent_flags(curve, len(values))
            if not is_static(values, in_flat, out_flat, tolerance):
                continue
            if _is_referenced(curve):
                skipped += 1
                continue
            try:
                cmds.delete(curve)
                deleted += 1
            except RuntimeError as exc:
                cmds.warning("Key Cleanup: skipped {} ({})".format(curve, exc))

    message = "deleted {} static channel(s).".format(deleted)
    if skipped:
        message += " {} referenced curve(s) left alone.".format(skipped)
    _report(message)
    return deleted


def snap_keys_to_frames(scope="selected", time_range=None, curves=None):
    """Move sub-frame keys onto whole frames.  Returns the number snapped."""
    if curves is None:
        curves = target_curves(scope)
    if not curves:
        _no_curves(scope)
        return 0

    snapped = 0
    with _UndoChunk("ATKKeyCleanupSnap"):
        for curve in curves:
            times = cmds.keyframe(curve, query=True, timeChange=True) or []
            off_frame = [t for t in subframe_times(times) if in_range(t, time_range)]
            if not off_frame:
                continue
            kwargs = {"timeMultiple": 1.0}
            if time_range is not None:
                kwargs["time"] = (time_range[0], time_range[1])
            try:
                cmds.snapKey(curve, **kwargs)
                snapped += len(off_frame)
            except RuntimeError as exc:
                cmds.warning("Key Cleanup: could not snap {} ({})".format(curve, exc))

    _report("snapped {} sub-frame key(s) to whole frames.".format(snapped))
    return snapped


def euler_filter(scope="selected", curves=None):
    """Run Maya's Euler filter per object.  Returns the number of objects filtered."""
    if curves is None:
        curves = target_curves(scope)
    if not curves:
        _no_curves(scope)
        return 0

    by_node = {}
    for curve in curves:
        plug = _driven_plug(curve)
        if "." not in plug:
            continue
        node, attr = plug.split(".", 1)
        if attr not in _ROTATE_ATTRS:
            continue
        # The filter needs all three rotate curves of the object, not only
        # the ones that happen to be selected.
        if node not in by_node:
            try:
                by_node[node] = cmds.keyframe(
                    node, query=True, name=True, attribute=_ROTATE_ATTRS) or []
            except RuntimeError:
                by_node[node] = []

    filtered = 0
    with _UndoChunk("ATKKeyCleanupEuler"):
        for node, rotate_curves in by_node.items():
            if not rotate_curves:
                continue
            try:
                cmds.filterCurve(rotate_curves)
                filtered += 1
            except RuntimeError as exc:
                cmds.warning("Key Cleanup: Euler filter skipped {} ({})".format(node, exc))

    _report("Euler filter applied to {} object(s).".format(filtered))
    return filtered


def clean_all(scope="selected", time_range=None, tolerance=DEFAULT_TOLERANCE):
    """Run every pass as a single undo step.  Returns a dict of counts."""
    curves = target_curves(scope)
    if not curves:
        _no_curves(scope)
        return {}
    with _UndoChunk("ATKKeyCleanupAll"):
        counts = {
            "snapped": snap_keys_to_frames(scope, time_range, curves=curves),
            "euler": euler_filter(scope, curves=curves),
            "static": delete_static_channels(scope, tolerance, curves=curves),
        }
        remaining = [c for c in curves if cmds.objExists(c)]
        counts["redundant"] = (remove_redundant_keys(
            scope, time_range, tolerance, curves=remaining) if remaining else 0)
    _report("{redundant} redundant key(s), {static} static channel(s), "
            "{snapped} sub-frame key(s), {euler} object(s) Euler filtered.".format(**counts))
    return counts


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

_STYLESHEET = """
QDialog { background-color: #3c3c3c; color: #cccccc; }
QLabel { color: #cccccc; background: transparent; }
QLabel#lbl_title { font-size: 14px; font-weight: bold; color: #ffffff; }
QLabel#lbl_subtitle { font-size: 11px; color: #999999; }
QLabel#lbl_section { font-size: 9px; font-weight: bold; color: #777777; }
QLabel#lbl_desc { font-size: 10px; color: #848484; padding-left: 2px; }
QLabel#lbl_status { font-size: 11px; color: #a0ff7a; }
QFrame#separator { background-color: #525252; border: none; max-height: 1px; min-height: 1px; }
QPushButton {
    background-color: #555555; color: #dddddd; border: 1px solid #666666;
    border-radius: 4px; padding: 6px 12px; font-size: 12px; min-height: 26px;
    text-align: left;
}
QPushButton:hover { background-color: #636363; border-color: #888888; color: #ffffff; }
QPushButton:pressed { background-color: #444444; }
QPushButton#btn_primary {
    background-color: #2e6da4; color: #ffffff; border: 1px solid #4088c0;
    font-weight: bold; font-size: 13px; min-height: 34px; text-align: center;
}
QPushButton#btn_primary:hover { background-color: #3a7ec0; }
QPushButton#btn_primary:pressed { background-color: #205080; }
QRadioButton, QCheckBox { color: #cccccc; }
"""

_PASSES = (
    ("Remove Redundant Keys",
     "Deletes keys that sit inside a flat hold. The first and last key of "
     "each hold stay, so timing is unchanged.", "redundant"),
    ("Delete Static Channels",
     "Deletes curves whose keys never change value. The attribute keeps "
     "its value.", "static"),
    ("Snap Keys to Whole Frames",
     "Moves sub-frame keys (left by retiming or scaling) onto whole frames.", "snap"),
    ("Euler Filter",
     "Removes 360-degree rotation flips on the rotate channels.", "euler"),
)


def _maya_main_window():
    ptr = omui.MQtUtil.mainWindow()
    return wrapInstance(int(ptr), QtWidgets.QWidget) if ptr is not None else None


class KeyCleanupDialog(QtWidgets.QDialog):

    def __init__(self, parent=None):
        super(KeyCleanupDialog, self).__init__(parent)
        self.setObjectName(WINDOW_OBJECT_NAME)
        self.setWindowTitle("{} {}".format(TOOL_NAME, TOOL_VERSION))
        self.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.WindowTitleHint
                            | QtCore.Qt.WindowCloseButtonHint)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self.setMinimumWidth(340)
        self.setStyleSheet(_STYLESHEET)
        self._build_ui()

    def _separator(self):
        line = QtWidgets.QFrame()
        line.setObjectName("separator")
        line.setFrameShape(QtWidgets.QFrame.HLine)
        return line

    def _label(self, text, name):
        label = QtWidgets.QLabel(text)
        label.setObjectName(name)
        label.setWordWrap(True)
        return label

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(6)

        layout.addWidget(self._label(TOOL_NAME, "lbl_title"))
        layout.addWidget(self._label(
            "Tidy animation curves on the selected controls, the selected "
            "Graph Editor keys, or the whole scene. Every button is one undo.",
            "lbl_subtitle"))
        layout.addSpacing(4)
        layout.addWidget(self._separator())

        layout.addWidget(self._label("SCOPE", "lbl_section"))
        scope_row = QtWidgets.QHBoxLayout()
        self.selected_radio = QtWidgets.QRadioButton("Selected")
        self.scene_radio = QtWidgets.QRadioButton("Whole scene")
        self.selected_radio.setChecked(True)
        scope_row.addWidget(self.selected_radio)
        scope_row.addWidget(self.scene_radio)
        scope_row.addStretch(1)
        layout.addLayout(scope_row)

        layout.addWidget(self._label("FRAME RANGE", "lbl_section"))
        self.range_combo = QtWidgets.QComboBox()
        self.range_combo.addItems(["All keys", "Playback range", "Timeline selection"])
        self.range_combo.setToolTip(
            "Limits Remove Redundant Keys and Snap Keys to this range.\n"
            "Timeline selection is the shift-dragged Time Slider range.")
        layout.addWidget(self.range_combo)

        tol_row = QtWidgets.QHBoxLayout()
        tol_row.addWidget(QtWidgets.QLabel("Value tolerance"))
        self.tolerance_spin = QtWidgets.QDoubleSpinBox()
        self.tolerance_spin.setDecimals(4)
        self.tolerance_spin.setRange(0.0, 10.0)
        self.tolerance_spin.setSingleStep(0.001)
        self.tolerance_spin.setValue(DEFAULT_TOLERANCE)
        self.tolerance_spin.setToolTip(
            "Two keys count as the same value when they differ by less than this.")
        tol_row.addWidget(self.tolerance_spin)
        tol_row.addStretch(1)
        layout.addLayout(tol_row)

        layout.addSpacing(4)
        layout.addWidget(self._separator())
        layout.addWidget(self._label("CLEAN-UP PASSES", "lbl_section"))

        for text, description, key in _PASSES:
            button = QtWidgets.QPushButton(text)
            button.setToolTip(description)
            button.clicked.connect(lambda _checked=False, k=key: self._run(k))
            layout.addWidget(button)
            layout.addWidget(self._label(description, "lbl_desc"))

        layout.addSpacing(6)
        run_all = QtWidgets.QPushButton("Run All Passes")
        run_all.setObjectName("btn_primary")
        run_all.setToolTip("Runs all four passes as a single undo step.")
        run_all.clicked.connect(lambda _checked=False: self._run("all"))
        layout.addWidget(run_all)

        self.status_label = self._label("", "lbl_status")
        layout.addWidget(self.status_label)

    # -- options ----------------------------------------------------------
    def _scope(self):
        return "scene" if self.scene_radio.isChecked() else "selected"

    def _time_range(self):
        index = self.range_combo.currentIndex()
        if index == 1:
            return playback_range()
        if index == 2:
            selection = timeline_selection_range()
            if selection is None:
                cmds.warning("Key Cleanup: no Time Slider range is highlighted; "
                             "using the playback range.")
                return playback_range()
            return selection
        return None

    def _run(self, key):
        scope = self._scope()
        tolerance = self.tolerance_spin.value()
        try:
            if key == "redundant":
                count = remove_redundant_keys(scope, self._time_range(), tolerance)
                message = "Removed {} redundant key(s).".format(count)
            elif key == "static":
                count = delete_static_channels(scope, tolerance)
                message = "Deleted {} static channel(s).".format(count)
            elif key == "snap":
                count = snap_keys_to_frames(scope, self._time_range())
                message = "Snapped {} sub-frame key(s).".format(count)
            elif key == "euler":
                count = euler_filter(scope)
                message = "Euler filtered {} object(s).".format(count)
            else:
                counts = clean_all(scope, self._time_range(), tolerance)
                if counts:
                    message = ("{redundant} redundant, {static} static, {snapped} "
                               "snapped, {euler} Euler filtered.".format(**counts))
                else:
                    message = "Nothing to clean - check the selection."
        except Exception as exc:  # keep the window alive on any Maya error
            cmds.warning("Key Cleanup failed: {}".format(exc))
            message = "Error: {}".format(exc)
        self.status_label.setText(message)


_dialog = None  # keeps the window alive when launched without a Maya parent


def show():
    """Show the Key Cleanup window, replacing any existing one."""
    global _dialog
    for widget in QtWidgets.QApplication.allWidgets():
        if widget.objectName() == WINDOW_OBJECT_NAME:
            widget.close()
            widget.deleteLater()
    _dialog = KeyCleanupDialog(parent=_maya_main_window())
    _dialog.show()
    _dialog.raise_()
    _dialog.activateWindow()
    return _dialog


def launch():
    """ATK toolbar entry point."""
    return show()


if __name__ == "__main__":
    show()
