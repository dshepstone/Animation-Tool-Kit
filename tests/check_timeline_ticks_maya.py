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
    assert any(image.pixelColor(x, 20).alpha() for x in range(image.width()))
    timeline.resize(900, 60)
    app.processEvents()
    assert bar.overlay.size() == timeline.size()
    if len(sys.argv) > 1:
        assert bar.grab().save(sys.argv[1])
    bar.close()
    assert not bar.timer.isActive()
    app.processEvents()
    print("PASS: real Qt click, overlay paint, resize, close and timer cleanup")


if __name__ == "__main__":
    try:
        main()
    finally:
        maya.standalone.uninitialize()
