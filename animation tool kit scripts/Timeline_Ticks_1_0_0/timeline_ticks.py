"""Compact, scene-persistent coloured timeline annotations for Maya 2022+.

Run ``import timeline_ticks; timeline_ticks.show()`` inside Maya.
Annotations identify an animation curve UUID and a time in seconds. The runtime
tracker follows exact key edits, removes deleted labels and supports Undo/Redo.
"""
import json
from functools import partial

TYPES = {
    "Key": ("K", "#ef6464"),
    "Extreme": ("E", "#f5cf58"),
    "Breakdown": ("B", "#60a5fa"),
    "Inbetween": ("I", "#78cc95"),
}
PALETTE = (("Yellow", "#f5cf58"), ("Red", "#ef6464"),
           ("Blue", "#60a5fa"), ("Green", "#78cc95"))
ATTR = "atkTimelineTicks"
_window = None
_tracker = None


def time_token(seconds):
    """Stable subframe identity independent of Maya's display time unit."""
    return "%.9f" % seconds


def decode(raw):
    data = json.loads(raw)
    if not isinstance(data, dict) or data.get("version") != 1:
        raise ValueError("Unsupported Timeline Ticks scene data")
    marks = data.get("marks")
    if not isinstance(marks, dict):
        raise ValueError("Invalid Timeline Ticks scene data")
    for identity, mark in marks.items():
        if not isinstance(identity, str) or not isinstance(mark, dict):
            raise ValueError("Invalid tick annotation")
        if mark.get("kind") not in TYPES or mark.get("color") not in dict(PALETTE).values():
            raise ValueError("Invalid tick style")
    return marks


def frame_x(frame, start, end, width):
    """Native tick position: frame-cell start inside Maya's 8px end gutters.

    The current-time highlight occupies a whole cell, but its key tick is at
    the leading edge. Using the cell centre puts annotations half a frame late.
    Qt widget coordinates are logical pixels, including on high-DPI displays.
    """
    gutter = min(8.0, width / 2.0)
    span = max(end - start + 1.0, 1.0)
    return gutter + (frame - start) * max(width - 2 * gutter, 0.0) / span


class SceneStore:
    def __init__(self, cmds):
        self.cmds = cmds

    def node(self):
        nodes = self.cmds.ls("*." + ATTR, objectsOnly=True, type="network") or []
        if len(nodes) > 1:
            raise ValueError("Multiple Timeline Ticks stores found; resolve imported stores first")
        return nodes[0] if nodes else None

    def read(self):
        node = self.node()
        return decode(self.cmds.getAttr(node + "." + ATTR)) if node else {}

    def write(self, marks):
        node = self.node()
        if node is None:
            node = self.cmds.createNode("network", name="ATK_TimelineTicks", skipSelect=True)
            self.cmds.addAttr(node, longName=ATTR, dataType="string")
        self.cmds.setAttr(node + "." + ATTR,
                          json.dumps({"version": 1, "marks": marks}, sort_keys=True),
                          type="string")


class Controller:
    def __init__(self, cmds, slider, seconds):
        self.cmds, self.slider, self.seconds = cmds, slider, seconds
        self.store = SceneStore(cmds)

    def curves(self):
        # Use the Time Slider's actual curve list (including animation layers).
        curves = self.cmds.timeControl(self.slider, q=True, animCurveNames=True) or []
        return sorted(set(c for c in curves
                          if self.cmds.nodeType(c) in ("animCurveTA", "animCurveTL", "animCurveTT", "animCurveTU")))

    def identity(self, curve, frame):
        return (self.cmds.ls(curve, uuid=True)[0] + "@" +
                time_token(self.seconds(frame)))

    def targets(self, scope):
        cmds = self.cmds
        curves = self.curves()
        if scope == "Selected keys":
            return [(c, t) for c in curves for t in
                    (cmds.keyframe(c, q=True, selected=True, timeChange=True) or [])]
        if scope == "Highlighted range":
            if not cmds.timeControl(self.slider, q=True, rangeVisible=True):
                return []
            start, end = cmds.timeControl(self.slider, q=True, rangeArray=True)
            # Maya returns an exclusive upper bound; preserve subframe keys.
            return [(c, t) for c in curves for t in
                    (cmds.keyframe(c, q=True, timeChange=True, time=(start, end)) or [])
                    if start <= t < end]
        now = cmds.currentTime(q=True)
        return [(c, t) for c in curves for t in
                (cmds.keyframe(c, q=True, timeChange=True, time=(now, now)) or [])]

    def apply(self, scope, kind=None, color=None, clear=False):
        if _tracker is not None:
            _tracker.flush()
        targets = self.targets(scope)
        if not targets:
            return 0
        marks = self.store.read()  # Validate before changing animation.
        cmds = self.cmds
        cmds.undoInfo(openChunk=True, chunkName="Timeline Ticks")
        try:
            for curve, frame in targets:
                identity = self.identity(curve, frame)
                if clear:
                    marks.pop(identity, None)
                else:
                    previous = marks.get(identity, {"kind": "Key", "color": TYPES["Key"][1]})
                    style = kind or previous["kind"]
                    marks[identity] = {"kind": style, "color": color or TYPES[style][1]}
                    # A colour-only edit must not change native breakdown state.
                    if kind is not None:
                        cmds.keyframe(curve, edit=True, time=(frame, frame),
                                      breakdown=(kind == "Breakdown"))
            self.store.write(marks)
        finally:
            cmds.undoInfo(closeChunk=True)
        if _tracker is not None:
            _tracker.capture()
        return len(targets)

    def visible_marks(self):
        marks = self.store.read()
        result = {}
        for curve in self.curves():
            uuid = self.cmds.ls(curve, uuid=True)[0]
            for frame in self.cmds.keyframe(curve, q=True, timeChange=True) or []:
                mark = marks.get(uuid + "@" + time_token(self.seconds(frame)))
                if mark:
                    result.setdefault(frame, set()).add((mark["kind"], mark["color"]))
        return result


def _ui_classes():
    try:
        from PySide6 import QtCore, QtGui, QtWidgets
        import shiboken6 as shiboken
    except ImportError:
        from PySide2 import QtCore, QtGui, QtWidgets
        import shiboken2 as shiboken

    class Overlay(QtWidgets.QWidget):
        def __init__(self, parent):
            super().__init__(parent)
            self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
            self.setAttribute(QtCore.Qt.WA_NoSystemBackground)
            self.marks = {}
            self.frame_range = (1, 120)
            parent.installEventFilter(self)
            self.setGeometry(parent.rect())
            self.show()

        def eventFilter(self, obj, event):
            if event.type() in (QtCore.QEvent.Resize, QtCore.QEvent.Show):
                self.setGeometry(self.parentWidget().rect())
                self.raise_()
            return False

        def paintEvent(self, event):
            painter = QtGui.QPainter(self)
            try:
                font = painter.font()
                font.setPixelSize(9)
                font.setBold(True)
                painter.setFont(font)
                start, end = self.frame_range
                for frame, styles in sorted(self.marks.items()):
                    if not start <= frame < end + 1:
                        continue
                    x = round(frame_x(frame, start, end, self.width()))
                    # Keep every colour on the tick; mixed channel styles
                    # share vertical segments rather than shifting sideways.
                    top = 8
                    tick_height = max(1, self.height() - 16)
                    for index, (kind, color) in enumerate(sorted(styles)):
                        y1 = top + round(index * tick_height / len(styles))
                        y2 = top + round((index + 1) * tick_height / len(styles))
                        painter.fillRect(x - 1, y1, 3, max(1, y2 - y1),
                                         QtGui.QColor(color))
                    # One readable letter; mixed channel classifications use '+'.
                    label = TYPES[next(iter(styles))[0]][0] if len(styles) == 1 else "+"
                    painter.setPen(QtGui.QColor(sorted(styles)[0][1]))
                    painter.drawText(int(x) - 3, 8, label)
            finally:
                painter.end()

    class TickBar(QtWidgets.QDialog):
        def __init__(self, parent, timeline, controller):
            super().__init__(parent)
            self.setObjectName("ATKTimelineTicksBar")
            self.setWindowTitle("Timeline Ticks")
            self.setWindowFlags(self.windowFlags() | QtCore.Qt.Tool)
            self.controller = controller
            self.overlay = Overlay(timeline)
            self._last_state = None
            self._last_error = None
            layout = QtWidgets.QVBoxLayout(self)
            layout.setContentsMargins(8, 8, 8, 6)
            layout.setSpacing(5)
            types = QtWidgets.QHBoxLayout()
            for kind, (letter, color) in TYPES.items():
                button = QtWidgets.QPushButton(kind)
                button.setMinimumHeight(25)
                button.setStyleSheet("QPushButton {border-bottom: 3px solid %s;}" % color)
                button.setToolTip("Label existing keys as %s and apply its default colour" % kind)
                button.clicked.connect(partial(self.apply, kind=kind))
                types.addWidget(button)
            layout.addLayout(types)
            row = QtWidgets.QHBoxLayout()
            self.scope = QtWidgets.QComboBox()
            self.scope.addItems(["Current frame", "Highlighted range", "Selected keys"])
            self.scope.setToolTip("Affects only existing keys on curves shown in the Time Slider")
            row.addWidget(self.scope)
            for name, color in PALETTE:
                button = QtWidgets.QPushButton()
                button.setFixedSize(23, 23)
                button.setAccessibleName(name)
                button.setToolTip("Colour %s; keep the existing classification" % name.lower())
                button.setStyleSheet("background-color: %s; border: 1px solid #888; border-radius: 3px;" % color)
                button.clicked.connect(partial(self.apply, color=color))
                row.addWidget(button)
            clear = QtWidgets.QPushButton("Clear")
            clear.setToolTip("Remove annotations in the chosen scope; keep animation and native breakdown state")
            clear.clicked.connect(partial(self.apply, clear=True))
            row.addWidget(clear)
            layout.addLayout(row)
            self.status = QtWidgets.QLabel("Select controls, choose scope, then a type or colour.")
            self.status.setStyleSheet("color: #aaa; font-size: 10px;")
            self.status.setToolTip("Labels follow moved keys and disappear with deleted keys.\n"
                                   "Breakdown sets Maya's native breakdown state; other types clear it.\n"
                                   "Closing this bar hides its coloured tick overlay.")
            layout.addWidget(self.status)
            self.timer = QtCore.QTimer(self)
            self.timer.timeout.connect(self.refresh)
            self.timer.start(400)
            self.refresh()
            self.adjustSize()

        def apply(self, checked=False, **options):
            try:
                count = self.controller.apply(self.scope.currentText(), **options)
                self.status.setText("Updated %d curve keys. Undo supported." % count if count else
                                    "No existing keys in this scope on visible curves.")
                self.refresh()
            except Exception as exc:
                self.status.setText("Could not update ticks. See Script Editor.")
                self.controller.cmds.warning("Timeline Ticks: " + str(exc))
                self.refresh()

        def refresh(self):
            try:
                cmds = self.controller.cmds
                # No scene writes or undo changes in this refresh path.
                marks = self.controller.visible_marks()
                frame_range = (cmds.playbackOptions(q=True, minTime=True),
                               cmds.playbackOptions(q=True, maxTime=True))
                state = (marks, frame_range)
                if state != self._last_state:
                    self.overlay.marks, self.overlay.frame_range = state
                    self.overlay.update()
                    self._last_state = state
                self._last_error = None
            except Exception as exc:
                # Never leave misleading ticks from another scene on screen.
                self.overlay.marks = {}
                self.overlay.update()
                if str(exc) != self._last_error:
                    self.controller.cmds.warning("Timeline Ticks: " + str(exc))
                    self._last_error = str(exc)

        def closeEvent(self, event):
            self.timer.stop()
            self.overlay.close()
            self.overlay.deleteLater()
            super().closeEvent(event)

    return TickBar, QtWidgets, shiboken


def _quick_apply(**options):
    """Toolbar/menu action without opening the floating settings bar."""
    global _window
    if _window is None or not _window.timer.isActive():
        window = show()
        window.hide()  # Keep the transparent overlay and refresh active.
    else:
        window = _window
    controller = window.controller
    scope = ("Highlighted range" if controller.cmds.timeControl(
        controller.slider, q=True, rangeVisible=True) else "Current frame")
    count = controller.apply(scope, **options)
    window.refresh()
    if not count:
        controller.cmds.warning("Timeline Ticks: no existing keys on visible curves in " + scope.lower())
    return count


def apply_yellow():
    return _quick_apply(color="#f5cf58")


def apply_red():
    return _quick_apply(color="#ef6464")


def apply_blue():
    return _quick_apply(color="#60a5fa")


def mark_key():
    return _quick_apply(kind="Key")


def mark_extreme():
    return _quick_apply(kind="Extreme")


def mark_breakdown():
    return _quick_apply(kind="Breakdown")


def mark_inbetween():
    return _quick_apply(kind="Inbetween")


def clear_ticks():
    return _quick_apply(clear=True)


def start_tracking():
    """Track even hidden/unselected curves, independently of the floating UI."""
    global _tracker
    if _tracker is None:
        import maya.cmds as cmds
        from timeline_ticks_tracking import KeyTracker
        tracker = KeyTracker(SceneStore(cmds), cmds)
        tracker.start()
        _tracker = tracker
    return _tracker


def shutdown():
    """Release every callback and window before reloading the tool module."""
    global _window, _tracker
    if _tracker is not None:
        _tracker.stop()
        _tracker = None
    if _window is not None:
        _window.close()
        _window.deleteLater()
        _window = None


def show():
    """Open one compact bar, parented to Maya; no scene scripts installed."""
    global _window
    import maya.cmds as cmds
    import maya.mel as mel
    import maya.api.OpenMaya as om
    from maya.OpenMayaUI import MQtUtil

    if cmds.about(batch=True):
        raise RuntimeError("Timeline Ticks requires interactive Maya")
    start_tracking()
    if _window is not None:
        _window.close()
        _window.deleteLater()
        _window = None
    TickBar, QtWidgets, shiboken = _ui_classes()
    slider = mel.eval("$atkTicksSlider = $gPlayBackSlider")
    ptr = MQtUtil.findControl(slider)
    if not ptr:
        raise RuntimeError("Show Maya's Time Slider before opening Timeline Ticks")
    parent = shiboken.wrapInstance(int(MQtUtil.mainWindow()), QtWidgets.QWidget)
    timeline = shiboken.wrapInstance(int(ptr), QtWidgets.QWidget)
    seconds = lambda frame: om.MTime(frame, om.MTime.uiUnit()).asUnits(om.MTime.kSeconds)
    _window = TickBar(parent, timeline, Controller(cmds, slider, seconds))
    _window.show()
    _window.raise_()
    return _window
