"""Stagger Keys - offset animation in time across a selection.

Select controls in the order they should move (for example down a tail,
spine or finger chain) and stagger their keys so each one starts a few
frames after the one before it - the quickest way to block in overlap.

    stagger(frames=2)       first control stays, 2nd +2, 3rd +4, ...
    offset_all(frames=-1)   every selected control moves 1 frame earlier

``show()`` opens the window.  Each operation is one undo step.  From the ATK
Toolbar the common amounts are also in the button's right-click menu.
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

TOOL_NAME = "Stagger Keys"
TOOL_VERSION = "1.0.0"
WINDOW_OBJECT_NAME = "atkStaggerKeysUI"


# ---------------------------------------------------------------------------
# Pure helper (no Maya calls - covered by the unit tests)
# ---------------------------------------------------------------------------

def stagger_offsets(count, frames, reverse=False):
    """Return the frame offset for each of ``count`` objects.

    The first object keeps its timing and every following object moves
    ``frames`` further than the one before it.  ``reverse`` flips the order,
    so the last selected object is the one that stays put.
    """
    offsets = [index * frames for index in range(max(0, int(count)))]
    if reverse:
        offsets.reverse()
    return offsets


# ---------------------------------------------------------------------------
# Scene operations
# ---------------------------------------------------------------------------

def _selection():
    return cmds.ls(selection=True, long=True) or []


def _curves_for(node, selected_keys_only):
    """Editable anim curves on ``node`` (optionally only those with selected keys)."""
    try:
        if selected_keys_only:
            curves = cmds.keyframe(node, query=True, selected=True, name=True) or []
        else:
            curves = cmds.keyframe(node, query=True, name=True) or []
    except RuntimeError:
        return []
    editable = []
    for curve in curves:
        try:
            if cmds.lockNode(curve, query=True, lock=True)[0]:
                continue
        except Exception:
            pass
        editable.append(curve)
    return editable


def _shift(node, delta, selected_keys_only):
    """Move ``node``'s keys by ``delta`` frames.  Returns the curves moved."""
    if not delta:
        return 0
    moved = 0
    for curve in _curves_for(node, selected_keys_only):
        kwargs = {"edit": True, "relative": True, "timeChange": delta, "option": "over"}
        if selected_keys_only:
            # Only the keys highlighted in the Graph Editor.
            indices = cmds.keyframe(curve, query=True, selected=True, indexValue=True) or []
            if not indices:
                continue
            kwargs["index"] = [(int(i), int(i)) for i in indices]
        try:
            cmds.keyframe(curve, **kwargs)
            moved += 1
        except RuntimeError as exc:
            cmds.warning("Stagger Keys: skipped {} ({})".format(curve, exc))
    return moved


def _has_selected_keys():
    return bool(cmds.keyframe(query=True, selected=True, name=True))


def _report(message):
    print("Stagger Keys: " + message)
    try:
        cmds.inViewMessage(amg="<hl>Stagger Keys</hl>  " + message,
                           pos="midCenter", fade=True)
    except Exception:
        pass
    return message


def _apply(offsets, nodes, selected_keys_only, chunk):
    moved_nodes = 0
    cmds.undoInfo(openChunk=True, chunkName=chunk)
    try:
        for node, delta in zip(nodes, offsets):
            if _shift(node, delta, selected_keys_only):
                moved_nodes += 1
    finally:
        cmds.undoInfo(closeChunk=True)
    return moved_nodes


def stagger(frames=1, reverse=False, selected_keys_only=None):
    """Stagger the selected objects' keys by ``frames`` per object.

    Selection order sets the order: the first selected object keeps its
    timing, the second moves ``frames``, the third ``2 * frames`` and so on
    (``reverse`` starts from the last selected object instead).  When keys
    are selected in the Graph Editor only those keys move, unless
    ``selected_keys_only`` is passed explicitly.  Returns the number of
    objects whose keys moved.
    """
    nodes = _selection()
    if len(nodes) < 2:
        cmds.warning("Stagger Keys: select two or more animated objects, "
                     "in the order they should move.")
        return 0
    if not frames:
        return 0
    if selected_keys_only is None:
        selected_keys_only = _has_selected_keys()

    offsets = stagger_offsets(len(nodes), frames, reverse)
    moved = _apply(offsets, nodes, selected_keys_only, "ATKStaggerKeys")
    if not moved:
        cmds.warning("Stagger Keys: no keys to move on the selection.")
        return 0
    _report("staggered {} object(s) by {} frame(s) each.".format(moved, frames))
    return moved


def offset_all(frames=1, selected_keys_only=None):
    """Move every selected object's keys by the same ``frames``."""
    nodes = _selection()
    if not nodes:
        cmds.warning("Stagger Keys: select one or more animated objects.")
        return 0
    if not frames:
        return 0
    if selected_keys_only is None:
        selected_keys_only = _has_selected_keys()

    moved = _apply([frames] * len(nodes), nodes, selected_keys_only, "ATKOffsetKeys")
    if not moved:
        cmds.warning("Stagger Keys: no keys to move on the selection.")
        return 0
    _report("moved {} object(s) by {} frame(s).".format(moved, frames))
    return moved


# Toolbar right-click actions (no arguments).
def stagger_plus_1():
    return stagger(1)


def stagger_plus_2():
    return stagger(2)


def stagger_minus_1():
    return stagger(-1)


def offset_plus_1():
    return offset_all(1)


def offset_minus_1():
    return offset_all(-1)


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
}
QPushButton:hover { background-color: #636363; border-color: #888888; color: #ffffff; }
QPushButton:pressed { background-color: #444444; }
QPushButton#btn_primary {
    background-color: #2e6da4; color: #ffffff; border: 1px solid #4088c0;
    font-weight: bold; font-size: 13px; min-height: 34px;
}
QPushButton#btn_primary:hover { background-color: #3a7ec0; }
QPushButton#btn_primary:pressed { background-color: #205080; }
QRadioButton, QCheckBox { color: #cccccc; }
"""


def _maya_main_window():
    ptr = omui.MQtUtil.mainWindow()
    return wrapInstance(int(ptr), QtWidgets.QWidget) if ptr is not None else None


class StaggerKeysDialog(QtWidgets.QDialog):

    def __init__(self, parent=None):
        super(StaggerKeysDialog, self).__init__(parent)
        self.setObjectName(WINDOW_OBJECT_NAME)
        self.setWindowTitle("{} {}".format(TOOL_NAME, TOOL_VERSION))
        self.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.WindowTitleHint
                            | QtCore.Qt.WindowCloseButtonHint)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self.setMinimumWidth(320)
        self.setStyleSheet(_STYLESHEET)
        self._build_ui()

    def _label(self, text, name):
        label = QtWidgets.QLabel(text)
        label.setObjectName(name)
        label.setWordWrap(True)
        return label

    def _separator(self):
        line = QtWidgets.QFrame()
        line.setObjectName("separator")
        line.setFrameShape(QtWidgets.QFrame.HLine)
        return line

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(6)

        layout.addWidget(self._label(TOOL_NAME, "lbl_title"))
        layout.addWidget(self._label(
            "Select controls in the order they should move, then stagger "
            "their keys to block in overlap. If keys are selected in the "
            "Graph Editor, only those keys move.", "lbl_subtitle"))
        layout.addSpacing(4)
        layout.addWidget(self._separator())

        layout.addWidget(self._label("MODE", "lbl_section"))
        self.stagger_radio = QtWidgets.QRadioButton("Stagger by selection order")
        self.stagger_radio.setToolTip(
            "The first selected control stays; each following control moves\n"
            "the frame amount further than the one before it.")
        self.offset_radio = QtWidgets.QRadioButton("Offset all the same amount")
        self.offset_radio.setToolTip("Every selected control moves by the frame amount.")
        self.stagger_radio.setChecked(True)
        layout.addWidget(self.stagger_radio)
        layout.addWidget(self.offset_radio)

        self.reverse_check = QtWidgets.QCheckBox("Reverse order (last selected stays)")
        layout.addWidget(self.reverse_check)
        self.offset_radio.toggled.connect(
            lambda checked: self.reverse_check.setEnabled(not checked))

        layout.addWidget(self._label("FRAMES", "lbl_section"))
        frames_row = QtWidgets.QHBoxLayout()
        self.frames_spin = QtWidgets.QSpinBox()
        self.frames_spin.setRange(1, 500)
        self.frames_spin.setValue(1)
        self.frames_spin.setSuffix(" frame(s)")
        frames_row.addWidget(self.frames_spin)
        frames_row.addStretch(1)
        layout.addLayout(frames_row)

        button_row = QtWidgets.QHBoxLayout()
        earlier = QtWidgets.QPushButton("◀  Earlier")
        earlier.setToolTip("Move keys earlier in time.")
        earlier.clicked.connect(lambda _checked=False: self._run(-1))
        later = QtWidgets.QPushButton("Later  ▶")
        later.setObjectName("btn_primary")
        later.setToolTip("Move keys later in time.")
        later.clicked.connect(lambda _checked=False: self._run(1))
        button_row.addWidget(earlier)
        button_row.addWidget(later)
        layout.addLayout(button_row)

        layout.addWidget(self._label(
            "Each click is one undo step. Click again to add more offset.",
            "lbl_desc"))
        self.status_label = self._label("", "lbl_status")
        layout.addWidget(self.status_label)

    def _run(self, direction):
        frames = self.frames_spin.value() * direction
        try:
            if self.offset_radio.isChecked():
                moved = offset_all(frames)
                message = "Moved {} object(s) by {} frame(s).".format(moved, frames)
            else:
                moved = stagger(frames, reverse=self.reverse_check.isChecked())
                message = "Staggered {} object(s) by {} frame(s) each.".format(moved, frames)
            if not moved:
                message = "Nothing moved - check the selection."
        except Exception as exc:  # keep the window alive on any Maya error
            cmds.warning("Stagger Keys failed: {}".format(exc))
            message = "Error: {}".format(exc)
        self.status_label.setText(message)


_dialog = None  # keeps the window alive when launched without a Maya parent


def show():
    """Show the Stagger Keys window, replacing any existing one."""
    global _dialog
    for widget in QtWidgets.QApplication.allWidgets():
        if widget.objectName() == WINDOW_OBJECT_NAME:
            widget.close()
            widget.deleteLater()
    _dialog = StaggerKeysDialog(parent=_maya_main_window())
    _dialog.show()
    _dialog.raise_()
    _dialog.activateWindow()
    return _dialog


def launch():
    """ATK toolbar entry point."""
    return show()


if __name__ == "__main__":
    show()
