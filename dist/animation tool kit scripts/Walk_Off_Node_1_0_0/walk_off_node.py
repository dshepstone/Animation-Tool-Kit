# =============================================================================
# walk_off_node.py
#
# Walk Off Node — Maya Animation Utility (Animation Tool Kit)
#
# Turns a treadmill walk cycle into a walk that travels through the scene.
#
# In a typical cycle setup the character's controls (IK feet, hands, COG /
# waist ...) loop in place with cycle infinity, while the rig's base / layout
# node (the top of the hierarchy) slides forward to carry the character along.
# This tool:
#
#   1. Samples the WORLD-SPACE position and rotation of every chosen control
#      on every frame of the range — exactly where the feet and hands really
#      are while the base node is pulling the treadmill.
#   2. Removes the base node's slide animation (it holds still).
#   3. Keys the sampled world positions back onto the controls and removes
#      their cycle infinity, so the feet plant and the character walks off
#      the node.
#
# Usage: launch from the ATK toolbar, or
#   import walk_off_node; walk_off_node.show()
#
# Scripting:
#   walk_off_node.walk_off_node(controls, base_nodes, start, end)
#
# Requirements: Maya 2022+ (PySide6 or PySide2)
# =============================================================================

import maya.cmds as cmds
import maya.mel as mel

try:
    from PySide6 import QtCore, QtWidgets
    from shiboken6 import wrapInstance
except ImportError:  # Maya 2022–2024
    from PySide2 import QtCore, QtWidgets
    from shiboken2 import wrapInstance

from maya import OpenMayaUI as omui

VERSION = "1.0.0"
WINDOW_OBJECT_NAME = "atkWalkOffNodeUI"

_TRANSLATE = ("translateX", "translateY", "translateZ")
_ROTATE = ("rotateX", "rotateY", "rotateZ")
_SCALE = ("scaleX", "scaleY", "scaleZ")
_TRANSFORM_ATTRS = _TRANSLATE + _ROTATE + _SCALE

BASE_HOLD_START = "hold"   # base node keeps its pose from the first frame
BASE_ZERO = "zero"         # base node is reset to the origin


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _short(node):
    return node.split("|")[-1]


def _long_names(nodes):
    """Full DAG paths for transforms in nodes, de-duplicated, order kept."""
    out = []
    for node in nodes or []:
        for name in cmds.ls(node, long=True, type="transform") or []:
            if name not in out:
                out.append(name)
    return out


def playback_range():
    return (int(round(cmds.playbackOptions(q=True, min=True))),
            int(round(cmds.playbackOptions(q=True, max=True))))


def timeline_selection_range():
    """Highlighted (shift-dragged) Time Slider range, or None if there is none."""
    try:
        slider = mel.eval("$atkTmp = $gPlayBackSlider")
        if not cmds.timeControl(slider, q=True, rangeVisible=True):
            return None
        start, end = cmds.timeControl(slider, q=True, rangeArray=True)
        # rangeArray end is exclusive (one past the last highlighted frame)
        return int(round(start)), int(round(end)) - 1
    except Exception:
        return None


def _settable(node, attr):
    plug = node + "." + attr
    try:
        if not cmds.attributeQuery(attr, node=node, exists=True):
            return False
        return (not cmds.getAttr(plug, lock=True)) and cmds.getAttr(plug, settable=True)
    except Exception:
        return False


def _keyed_attrs(node, attrs):
    """Subset of attrs on node that carry keys."""
    return [a for a in attrs
            if cmds.keyframe(node + "." + a, q=True, keyframeCount=True)]


def _custom_keyed_attrs(node):
    """Keyed, keyable, non-transform attributes (foot roll, IK/FK blends ...)."""
    attrs = []
    for attr in cmds.listAttr(node, keyable=True, scalar=True) or []:
        if attr in _TRANSFORM_ATTRS or attr == "visibility":
            continue
        try:
            if cmds.keyframe(node + "." + attr, q=True, keyframeCount=True):
                attrs.append(attr)
        except Exception:
            pass
    return attrs


def _frames(start, end, step):
    frames = list(range(start, end + 1, max(1, int(step))))
    if frames[-1] != end:
        frames.append(end)   # always land the last frame of the range
    return frames


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

def walk_off_node(controls, base_nodes, start, end, step=1, include_rotation=True,
                  bake_custom_attrs=True, remove_cycle=True, base_mode=BASE_HOLD_START):
    """Bake controls to their world-space path, then remove the base slide.

    controls          -- controls that should walk off (IK feet, hands, COG ...)
    base_nodes        -- base / layout node(s) whose animation slides the rig
    start, end        -- inclusive frame range to bake
    step              -- key every Nth frame (1 = every frame, recommended)
    include_rotation  -- also match world-space rotation (turns, curved paths)
    bake_custom_attrs -- bake keyed custom attributes (foot roll etc.) across
                         the range so they keep animating with the cycle removed
    remove_cycle      -- set pre/post infinity to constant on baked curves
    base_mode         -- BASE_HOLD_START or BASE_ZERO

    Returns the number of keys written.
    """
    start, end = int(start), int(end)
    if end < start:
        raise ValueError("End frame must be after the start frame.")
    controls = _long_names(controls)
    base_nodes = _long_names(base_nodes)
    if not controls:
        raise ValueError("Load the controls that should walk off (feet, hands, COG ...).")
    if not base_nodes:
        raise ValueError("Set the base / layout node that slides the character.")
    controls = [c for c in controls if c not in base_nodes]
    if not controls:
        raise ValueError("The base node cannot also be one of the controls.")

    # Parents before children, so a parent control is already re-keyed when
    # its child's world position is converted back into local values.
    controls.sort(key=lambda n: n.count("|"))

    channels = {}
    for ctrl in controls:
        attrs = [a for a in _TRANSLATE if _settable(ctrl, a)]
        if include_rotation:
            attrs += [a for a in _ROTATE if _settable(ctrl, a)]
        if not attrs:
            cmds.warning("Walk Off Node: '{}' has no settable translate/rotate "
                         "channels — skipped.".format(_short(ctrl)))
        channels[ctrl] = attrs
    controls = [c for c in controls if channels[c]]
    if not controls:
        raise ValueError("None of the controls have settable translate/rotate channels.")

    frames = _frames(start, end, step)
    original_time = cmds.currentTime(q=True)
    autokey = cmds.autoKeyframe(q=True, state=True)
    keys_written = 0

    cmds.undoInfo(openChunk=True, chunkName="walk_off_node")
    cmds.autoKeyframe(state=False)
    try:
        cmds.refresh(suspend=True)
        try:
            # 1. Sample where everything really is, cycle and slide included.
            samples = {c: {} for c in controls}
            for f in frames:
                cmds.currentTime(f, update=True)
                for ctrl in controls:
                    samples[ctrl][f] = (
                        cmds.xform(ctrl, q=True, ws=True, t=True),
                        cmds.xform(ctrl, q=True, ws=True, ro=True),
                    )

            # 2. Bake keyed custom attributes (foot roll ...) while the cycle
            #    still drives them, so they survive the infinity removal.
            if bake_custom_attrs:
                for ctrl in controls:
                    custom = [a for a in _custom_keyed_attrs(ctrl) if _settable(ctrl, a)]
                    if not custom:
                        continue
                    cmds.bakeResults([ctrl + "." + a for a in custom], time=(start, end),
                                     sampleBy=max(1, int(step)), preserveOutsideKeys=True,
                                     simulation=False)
                    if remove_cycle:
                        cmds.setInfinity(ctrl, attribute=custom,
                                         preInfinite="constant", postInfinite="constant")

            # 3. Remove the base node's slide.
            for base in base_nodes:
                _remove_base_animation(base, start, base_mode)

            # 4. Replace the treadmill keys with the world-space path.
            for ctrl in controls:
                attrs = channels[ctrl]
                cmds.cutKey(ctrl, attribute=attrs, time=(start, end), clear=True)

            set_rotation = any(a in _ROTATE for attrs in channels.values() for a in attrs)
            for f in frames:
                cmds.currentTime(f, update=True)
                for ctrl in controls:
                    t, r = samples[ctrl][f]
                    attrs = channels[ctrl]
                    _apply_world(ctrl, t, r if set_rotation else None, attrs)
                    for attr in attrs:
                        cmds.setKeyframe(ctrl, attribute=attr, time=f)
                        keys_written += 1

            if remove_cycle:
                for ctrl in controls:
                    cmds.setInfinity(ctrl, attribute=channels[ctrl],
                                     preInfinite="constant", postInfinite="constant")

            # Keep rotations continuous after world -> local conversion.
            for ctrl in controls:
                rot = [a for a in channels[ctrl] if a in _ROTATE]
                curves = cmds.keyframe(ctrl, attribute=rot, q=True, name=True) if rot else None
                if curves:
                    try:
                        cmds.filterCurve(curves, filter="euler")
                    except Exception:
                        pass
        finally:
            cmds.refresh(suspend=False)
    finally:
        cmds.currentTime(original_time, update=True)
        cmds.autoKeyframe(state=autokey)
        cmds.undoInfo(closeChunk=True)

    print("Walk Off Node: baked {} control(s) over frames {}-{} ({} keys); "
          "base slide removed from {}.".format(
              len(controls), start, end, keys_written,
              ", ".join(_short(b) for b in base_nodes)))
    return keys_written


def _apply_world(ctrl, t, r, attrs):
    """Place ctrl at world translate t / rotate r, respecting locked axes."""
    if any(a in _TRANSLATE for a in attrs):
        _apply_component(ctrl, "t", t, _TRANSLATE, attrs)
    if r is not None and any(a in _ROTATE for a in attrs):
        _apply_component(ctrl, "ro", r, _ROTATE, attrs)


def _apply_component(ctrl, flag, value, axes, attrs):
    """xform in world space; if some axes are locked, keep only the free ones."""
    if all(a in attrs for a in axes):
        try:
            cmds.xform(ctrl, ws=True, **{flag: value})
        except RuntimeError:
            pass
        return
    # Partially locked: xform always writes all three axes, so unlock briefly,
    # solve, then put the locked axes back to their local values and relock.
    before = [cmds.getAttr(ctrl + "." + a) for a in axes]
    locks = [cmds.getAttr(ctrl + "." + a, lock=True) for a in axes]
    for a, locked in zip(axes, locks):
        if locked:
            cmds.setAttr(ctrl + "." + a, lock=False)
    try:
        cmds.xform(ctrl, ws=True, **{flag: value})
    except RuntimeError:
        pass
    finally:
        for a, old, locked in zip(axes, before, locks):
            if a not in attrs:
                try:
                    cmds.setAttr(ctrl + "." + a, old)
                except RuntimeError:
                    pass
            if locked:
                cmds.setAttr(ctrl + "." + a, lock=True)


def _remove_base_animation(base, start, mode):
    """Delete the base node's transform keys and hold it still."""
    keyed = _keyed_attrs(base, _TRANSFORM_ATTRS)
    if not keyed:
        incoming = cmds.listConnections(base, source=True, destination=False,
                                        plugs=True, connections=True) or []
        driven = [incoming[i] for i in range(0, len(incoming), 2)
                  if incoming[i].split(".")[-1] in _TRANSFORM_ATTRS]
        if driven:
            cmds.warning("Walk Off Node: '{}' is driven by constraints/expressions, not "
                         "keys — remove those connections by hand.".format(_short(base)))
        else:
            cmds.warning("Walk Off Node: '{}' has no transform keys; nothing to "
                         "remove.".format(_short(base)))
        return
    hold = {}
    for attr in keyed:
        if mode == BASE_ZERO:
            hold[attr] = 1.0 if attr in _SCALE else 0.0
        else:
            hold[attr] = cmds.getAttr(base + "." + attr, time=start)
    cmds.cutKey(base, attribute=keyed, clear=True)
    for attr, value in hold.items():
        try:
            cmds.setAttr(base + "." + attr, value)
        except RuntimeError:
            cmds.warning("Walk Off Node: could not set {}.{}.".format(_short(base), attr))


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

_HELP_TEXT = """\
WALK OFF NODE

Turns a treadmill walk cycle into a walk that travels through the scene.

SETUP THIS IS FOR
  The controls (IK feet, IK hands, COG / waist, ...) cycle in place,
  usually with Cycle infinity, while the base / layout node at the top
  of the rig slides forward to carry the character.

HOW TO USE
  1. Select the controls that should walk off (feet, hands, waist,
     COG, pole vectors, ...) and click "Load Selected".
  2. Select the base / layout node that is sliding and click "Set".
  3. Choose the frame range.  "Playback" uses the playback range;
     "Timeline Selection" uses a shift-dragged Time Slider range.
  4. Click "Walk Off Node".

WHAT HAPPENS
  - Every control's world-space position (and rotation) is sampled
    on every frame, with the cycle and the slide both playing.
  - Keyed custom attributes (foot roll, toe tap ...) are baked across
    the range so they keep animating once the cycle is removed.
  - The base node's keys are deleted.  It holds its first-frame pose
    (or is zeroed, if you choose that).
  - The controls' keys in the range are replaced by the sampled world
    path, and their infinity is set to constant (cycle removed).
  Feet now plant and push off, and the character walks off the node.
  The whole operation is a single Undo.

TIPS
  - Include every control that is NOT a child of another included
    control and should travel with the body: feet, hands in IK, the
    COG / waist, IK pole vectors, a look-at target, etc.  Controls
    that are children of the COG (spine, head, FK arms) follow it
    and do not need baking.
  - Keep "Key every" at 1 for clean contacts.  Larger steps make
    lighter curves but can let a planted foot slide between keys.
  - Extend the range past the cycle's length (e.g. 4 cycles) to get
    a longer walk; the cycle is evaluated through its infinity.
"""


def _maya_main_window():
    ptr = omui.MQtUtil.mainWindow()
    return wrapInstance(int(ptr), QtWidgets.QWidget) if ptr is not None else None


class WalkOffNodeDialog(QtWidgets.QDialog):

    def __init__(self, parent=None):
        super(WalkOffNodeDialog, self).__init__(parent)
        self.setObjectName(WINDOW_OBJECT_NAME)
        self.setWindowTitle("Walk Off Node")
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.Tool)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self.setMinimumWidth(330)
        self._build_ui()
        if timeline_selection_range() is not None:
            self._use_timeline_selection()
        else:
            self._use_playback()

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        intro = QtWidgets.QLabel(
            "Bakes cycling controls to where they really are in world space, "
            "removes the base node's slide and the cycle, so the character "
            "walks off the node.")
        intro.setWordWrap(True)
        intro.setStyleSheet("color: #a8a8a8;")
        layout.addWidget(intro)

        # 1. Controls
        ctrl_box = QtWidgets.QGroupBox("1. Controls that walk off")
        cl = QtWidgets.QVBoxLayout(ctrl_box)
        self.ctrl_list = QtWidgets.QListWidget()
        self.ctrl_list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.ctrl_list.setFixedHeight(110)
        self.ctrl_list.setToolTip("IK feet, IK hands, COG / waist, pole vectors ...")
        cl.addWidget(self.ctrl_list)
        row = QtWidgets.QHBoxLayout()
        for text, fn in (("Load Selected", self._load_controls),
                         ("Add Selected", self._add_controls),
                         ("Remove", self._remove_controls)):
            btn = QtWidgets.QPushButton(text)
            btn.clicked.connect(fn)
            row.addWidget(btn)
        cl.addLayout(row)
        layout.addWidget(ctrl_box)

        # 2. Base node
        base_box = QtWidgets.QGroupBox("2. Base / layout node (sliding)")
        bl = QtWidgets.QHBoxLayout(base_box)
        self.base_edit = QtWidgets.QLineEdit()
        self.base_edit.setPlaceholderText("e.g. Character_Root / layout_ctrl")
        bl.addWidget(self.base_edit)
        btn_base = QtWidgets.QPushButton("Set")
        btn_base.clicked.connect(self._set_base)
        bl.addWidget(btn_base)
        layout.addWidget(base_box)

        # 3. Range
        range_box = QtWidgets.QGroupBox("3. Frame range")
        rl = QtWidgets.QGridLayout(range_box)
        self.start_spin = QtWidgets.QSpinBox()
        self.end_spin = QtWidgets.QSpinBox()
        for spin in (self.start_spin, self.end_spin):
            spin.setRange(-100000, 100000)
        rl.addWidget(QtWidgets.QLabel("Start"), 0, 0)
        rl.addWidget(self.start_spin, 0, 1)
        rl.addWidget(QtWidgets.QLabel("End"), 0, 2)
        rl.addWidget(self.end_spin, 0, 3)
        btn_pb = QtWidgets.QPushButton("Playback")
        btn_pb.clicked.connect(self._use_playback)
        btn_tl = QtWidgets.QPushButton("Timeline Selection")
        btn_tl.setToolTip("Use the shift-dragged (highlighted) Time Slider range.")
        btn_tl.clicked.connect(self._use_timeline_selection)
        rl.addWidget(btn_pb, 1, 0, 1, 2)
        rl.addWidget(btn_tl, 1, 2, 1, 2)
        layout.addWidget(range_box)

        # Options
        opt_box = QtWidgets.QGroupBox("Options")
        ol = QtWidgets.QGridLayout(opt_box)
        ol.addWidget(QtWidgets.QLabel("Key every"), 0, 0)
        self.step_spin = QtWidgets.QSpinBox()
        self.step_spin.setRange(1, 10)
        self.step_spin.setSuffix(" frame(s)")
        ol.addWidget(self.step_spin, 0, 1)
        self.rot_check = QtWidgets.QCheckBox("Match world rotation")
        self.rot_check.setChecked(True)
        self.custom_check = QtWidgets.QCheckBox("Bake keyed custom attributes (foot roll ...)")
        self.custom_check.setChecked(True)
        self.cycle_check = QtWidgets.QCheckBox("Remove cycle (infinity to constant)")
        self.cycle_check.setChecked(True)
        ol.addWidget(self.rot_check, 1, 0, 1, 2)
        ol.addWidget(self.custom_check, 2, 0, 1, 2)
        ol.addWidget(self.cycle_check, 3, 0, 1, 2)
        ol.addWidget(QtWidgets.QLabel("Base node after"), 4, 0)
        self.base_mode = QtWidgets.QComboBox()
        self.base_mode.addItem("Hold first-frame pose", BASE_HOLD_START)
        self.base_mode.addItem("Reset to origin", BASE_ZERO)
        ol.addWidget(self.base_mode, 4, 1)
        layout.addWidget(opt_box)

        self.run_btn = QtWidgets.QPushButton("Walk Off Node")
        self.run_btn.setMinimumHeight(34)
        self.run_btn.setStyleSheet(
            "QPushButton { background-color: #2e6da4; color: white; font-weight: bold;"
            " border-radius: 4px; } QPushButton:hover { background-color: #3a80c0; }")
        self.run_btn.clicked.connect(self._run)
        layout.addWidget(self.run_btn)

        footer = QtWidgets.QHBoxLayout()
        btn_help = QtWidgets.QPushButton("Help")
        btn_help.clicked.connect(self._show_help)
        footer.addWidget(btn_help)
        footer.addStretch()
        footer.addWidget(QtWidgets.QLabel("v" + VERSION))
        layout.addLayout(footer)

    # -- Slots ---------------------------------------------------------------

    def _controls(self):
        return [self.ctrl_list.item(i).data(QtCore.Qt.UserRole)
                for i in range(self.ctrl_list.count())]

    def _fill_controls(self, nodes):
        self.ctrl_list.clear()
        for node in nodes:
            item = QtWidgets.QListWidgetItem(_short(node))
            item.setData(QtCore.Qt.UserRole, node)
            item.setToolTip(node)
            self.ctrl_list.addItem(item)

    def _load_controls(self):
        sel = _long_names(cmds.ls(sl=True))
        if not sel:
            cmds.warning("Walk Off Node: select the feet, hands and waist controls first.")
        self._fill_controls(sel)

    def _add_controls(self):
        current = self._controls()
        self._fill_controls(current + [n for n in _long_names(cmds.ls(sl=True))
                                       if n not in current])

    def _remove_controls(self):
        for item in self.ctrl_list.selectedItems():
            self.ctrl_list.takeItem(self.ctrl_list.row(item))

    def _set_base(self):
        sel = _long_names(cmds.ls(sl=True))
        if not sel:
            cmds.warning("Walk Off Node: select the base / layout node first.")
            return
        self.base_edit.setText(sel[0])

    def _use_playback(self):
        start, end = playback_range()
        self.start_spin.setValue(start)
        self.end_spin.setValue(end)

    def _use_timeline_selection(self):
        rng = timeline_selection_range()
        if rng is None:
            cmds.warning("Walk Off Node: shift-drag a range on the Time Slider first.")
            return
        self.start_spin.setValue(rng[0])
        self.end_spin.setValue(rng[1])

    def _run(self):
        base = self.base_edit.text().strip()
        try:
            walk_off_node(
                self._controls(), [base] if base else [],
                self.start_spin.value(), self.end_spin.value(),
                step=self.step_spin.value(),
                include_rotation=self.rot_check.isChecked(),
                bake_custom_attrs=self.custom_check.isChecked(),
                remove_cycle=self.cycle_check.isChecked(),
                base_mode=self.base_mode.currentData(),
            )
        except ValueError as exc:
            cmds.warning("Walk Off Node: {}".format(exc))
            QtWidgets.QMessageBox.warning(self, "Walk Off Node", str(exc))

    def _show_help(self):
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Walk Off Node — Help")
        dlg.resize(500, 560)
        lay = QtWidgets.QVBoxLayout(dlg)
        text = QtWidgets.QPlainTextEdit(_HELP_TEXT)
        text.setReadOnly(True)
        text.setStyleSheet("font-family: Consolas, Menlo, monospace;")
        lay.addWidget(text)
        dlg.show()


_dialog = None


def show():
    """Open the Walk Off Node window, replacing any existing one."""
    global _dialog
    for widget in QtWidgets.QApplication.topLevelWidgets():
        if widget.objectName() == WINDOW_OBJECT_NAME:
            widget.close()
    _dialog = WalkOffNodeDialog(parent=_maya_main_window())
    _dialog.show()
    _dialog.raise_()
    return _dialog
