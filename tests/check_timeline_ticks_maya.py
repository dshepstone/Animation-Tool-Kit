"""Run with mayapy. Uses real Maya curves/storage/undo and real offscreen Qt."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] /
                       "animation tool kit scripts/Timeline_Ticks_1_0_0"))
import timeline_ticks as ticks
TickBar, QtWidgets, shiboken = ticks._ui_classes()
# Create a QApplication before standalone can create a QCoreApplication.
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
import maya.standalone
maya.standalone.initialize(name="python")
import maya.cmds as cmds
import maya.api.OpenMaya as om


class SliderCommands:
    """Only interactive timeControl is substituted in standalone Maya."""
    def __getattr__(self, name):
        return getattr(cmds, name)

    def timeControl(self, slider, **flags):
        if flags.get("animCurveNames"):
            return cmds.keyframe("tickTest", q=True, name=True) or []
        if flags.get("rangeVisible"):
            return True
        if flags.get("rangeArray"):
            return [1, 12]


def main():
    cmds.file(new=True, force=True)
    cmds.undoInfo(state=True)
    cmds.createNode("transform", name="tickTest")
    for frame in (1, 5, 10.5, 12):
        cmds.setKeyframe("tickTest", attribute="translateX", time=frame, value=frame)
    cmds.currentTime(5)
    c = ticks.Controller(SliderCommands(), "slider",
                         lambda frame: om.MTime(frame, om.MTime.uiUnit()).asUnits(om.MTime.kSeconds))
    curve = c.curves()[0]
    assert c.apply("Current frame", kind="Breakdown") == 1
    assert cmds.keyframe(curve, q=True, time=(5, 5), breakdown=True) == [5.0]
    assert len(c.store.read()) == 1
    cmds.undo()
    assert c.store.read() == {}
    assert not cmds.keyframe(curve, q=True, time=(5, 5), breakdown=True)
    cmds.redo()
    assert len(c.store.read()) == 1
    assert c.apply("Highlighted range", kind="Extreme") == 3
    c.apply("Current frame", color="#60a5fa")
    identity = c.identity(curve, 5)
    assert c.store.read()[identity] == {"kind": "Extreme", "color": "#60a5fa"}
    count = cmds.keyframe(curve, q=True, keyframeCount=True)
    with tempfile.TemporaryDirectory(prefix="atk_ticks_") as folder:
        scene = str(Path(folder) / "ticks.ma")
        cmds.file(rename=scene)
        cmds.file(save=True, type="mayaAscii")
        before = c.store.read()
        cmds.file(new=True, force=True)
        cmds.file(scene, open=True, force=True)
        assert c.store.read() == before
        assert cmds.keyframe(curve, q=True, keyframeCount=True) == count
    cmds.currentUnit(time="ntsc")
    assert len(c.visible_marks()) == 3, "Changing FPS lost annotation identities"
    cmds.currentUnit(time="film")
    cmds.currentTime(5)
    assert c.apply("Current frame", clear=True) == 1
    assert identity not in c.store.read()
    cmds.undo()
    assert identity in c.store.read()
    print("PASS: real Maya breakdown, undo/redo, subframes, save/reopen, FPS, clear")

    TickBar, QtWidgets, shiboken = ticks._ui_classes()
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    try:
        from PySide6 import QtGui
    except ImportError:
        from PySide2 import QtGui
    # Standalone Maya may not populate Qt's system font database.
    font_path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/segoeui.ttf"
    if font_path.exists():
        QtGui.QFontDatabase.addApplicationFont(str(font_path))
        app.setFont(QtGui.QFont("Segoe UI", 9))
    app.setStyle("Fusion")
    palette = app.palette()
    palette.setColor(QtGui.QPalette.Window, QtGui.QColor("#303030"))
    palette.setColor(QtGui.QPalette.WindowText, QtGui.QColor("#dedede"))
    palette.setColor(QtGui.QPalette.Button, QtGui.QColor("#454545"))
    palette.setColor(QtGui.QPalette.ButtonText, QtGui.QColor("#dedede"))
    palette.setColor(QtGui.QPalette.Base, QtGui.QColor("#292929"))
    palette.setColor(QtGui.QPalette.Text, QtGui.QColor("#dedede"))
    app.setPalette(palette)
    parent = QtWidgets.QWidget()
    parent.resize(720, 90)
    timeline = QtWidgets.QWidget(parent)
    timeline.setGeometry(0, 30, 720, 56)
    cmds.playbackOptions(minTime=1, maxTime=24)
    bar = TickBar(parent, timeline, c)
    parent.show()
    bar.show()
    app.processEvents()
    # Exercise a real Qt click and transparent tick rendering.
    next(b for b in bar.findChildren(QtWidgets.QPushButton) if b.text() == "Key").click()
    app.processEvents()
    assert c.store.read()[identity]["kind"] == "Key"
    assert bar.overlay.marks
    image = bar.overlay.grab().toImage()
    tick_x = round(ticks.frame_x(5, 1, 24, bar.overlay.width()))
    assert image.pixelColor(tick_x, 20).name() == "#ef6464"
    old_centre_x = round(4.5 * bar.overlay.width() / 24)
    assert image.pixelColor(old_centre_x, 20).name() != "#ef6464"
    # Mixed classifications share the same x coordinate on the native tick.
    bar.overlay.marks = {5: {("Key", "#ef6464"), ("Extreme", "#f5cf58")}}
    mixed = bar.overlay.grab().toImage()
    assert mixed.pixelColor(tick_x, 10).name() == "#f5cf58"
    assert mixed.pixelColor(tick_x, bar.overlay.height() - 10).name() == "#ef6464"
    bar.refresh()
    timeline.resize(900, 60)
    app.processEvents()
    assert bar.overlay.size() == timeline.size()
    if len(sys.argv) > 1:
        assert bar.grab().save(sys.argv[1])
    bar.close()
    assert not bar.timer.isActive()
    app.processEvents()
    print("PASS: real Qt click, overlay paint, resize, close and timer cleanup")

    from unittest.mock import patch
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from atk_toolbar import atk_toolbar as toolbar
    tool = next(t for t in toolbar.atk_loader.TOOL_REGISTRY if t["id"] == "timeline_ticks")
    widget = toolbar.ATKToolbarWidget.__new__(toolbar.ATKToolbarWidget)
    QtWidgets.QWidget.__init__(widget)
    with patch.object(toolbar.atk_loader, "is_tool_installed", return_value=True), \
            patch.object(toolbar.atk_loader, "launch_tool_fn") as launch:
        buttons = widget._make_inline_color_buttons(tool, 28, True)
        assert len(buttons) == 3
        for button, (_, _, function) in zip(buttons, tool["inline_colors"]):
            button.click()
            launch.assert_called_with("timeline_ticks", function)
        layout = QtWidgets.QHBoxLayout(widget)
        for button in buttons:
            layout.addWidget(button)
        widget.show()
        app.processEvents()
        if len(sys.argv) > 1:
            assert widget.grab().save(str(Path(sys.argv[1]).with_name("timeline_ticks_main_bar.png")))
        captured = []
        class CapturingMenu(QtWidgets.QMenu):
            def exec(self, pos):
                captured.append(self)

        with patch.object(toolbar.QtWidgets, "QMenu", CapturingMenu):
            widget._tool_context_menu(tool, buttons[0], buttons[0].rect().center(), True)
        actions = {a.text(): a for a in captured[0].actions()}
        for label in ("Colour Yellow", "Colour Red", "Colour Blue", "Mark as Key", "Mark as Extreme",
                      "Mark as Breakdown", "Mark as Inbetween", "Clear Tick Annotations"):
            assert label in actions
        actions["Colour Blue"].trigger()
        launch.assert_called_with("timeline_ticks", "apply_blue")
    with patch.object(toolbar.atk_loader, "get_visible_tools", return_value=[tool]):
        assert toolbar._count_layout_items()[0] == 6  # launcher, 3 colours, gear, logo
    widget.close()
    print("PASS: three main-bar colour buttons, click dispatch, menu actions and layout count")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
        raise
    finally:
        maya.standalone.uninitialize()
