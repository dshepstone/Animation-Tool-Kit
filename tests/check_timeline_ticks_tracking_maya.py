"""Real Maya key editing regression checks. Run with mayapy (no UI required)."""
import importlib.util
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "animation tool kit scripts/Timeline_Ticks_1_0_0"))
import maya.standalone
maya.standalone.initialize(name="python")
import maya.cmds as cmds
import maya.api.OpenMaya as om
import timeline_ticks as ticks


class Commands:
    def __getattr__(self, name):
        return getattr(cmds, name)

    def timeControl(self, slider, **flags):
        return cmds.keyframe("tickTest.translateX", q=True, name=True) or []


def setup():
    cmds.file(new=True, force=True)
    cmds.undoInfo(state=True)
    cmds.createNode("transform", name="tickTest")
    for frame in (1, 5, 10, 15):
        cmds.setKeyframe("tickTest", attribute="translateX", time=frame, value=0)
    controller = ticks.Controller(Commands(), "slider",
        lambda t: om.MTime(t, om.MTime.uiUnit()).asUnits(om.MTime.kSeconds))
    cmds.currentTime(5)
    controller.apply("Current frame", kind="Key")
    cmds.currentTime(10)
    controller.apply("Current frame", kind="Extreme")
    ticks._tracker.flush()
    return controller, controller.curves()[0]


def labels(controller):
    ticks._tracker.flush()
    return {round(t, 6): next(iter(styles))[0] for t, styles in controller.visible_marks().items()}


def main():
    tracker = ticks.start_tracking()
    assert ticks.start_tracking() is tracker
    c, curve = setup()
    cmds.select(clear=True)  # Tracking must not depend on selected controls.
    cmds.keyframe(curve, edit=True, time=(5, 5), relative=True, timeChange=2)
    undo_name = cmds.undoInfo(q=True, undoName=True)
    assert labels(c) == {7: "Key", 10: "Extreme"}, labels(c)
    assert cmds.undoInfo(q=True, undoName=True) == undo_name, "Tracker added an undo step"
    cmds.undo()
    assert labels(c) == {5: "Key", 10: "Extreme"}, labels(c)
    cmds.redo()
    assert labels(c) == {7: "Key", 10: "Extreme"}
    print("PASS: unselected key move, undo/redo and unchanged undo queue", flush=True)

    c, curve = setup()
    cmds.keyframe(curve, edit=True, relative=True, timeChange=5, option="over")
    assert labels(c) == {10: "Key", 15: "Extreme"}, labels(c)
    cmds.undo()
    assert labels(c) == {5: "Key", 10: "Extreme"}
    cmds.scaleKey(curve, timeScale=-1, timePivot=8)
    assert labels(c) == {11: "Key", 6: "Extreme"}, labels(c)
    cmds.undo()
    assert labels(c) == {5: "Key", 10: "Extreme"}
    cmds.keyframe(curve, edit=True, time=(5, 5), relative=True, valueChange=3)
    assert labels(c) == {5: "Key", 10: "Extreme"}
    cmds.keyframe(curve, edit=True, time=(5, 5), timeChange=5.5)
    assert labels(c) == {5.5: "Key", 10: "Extreme"}
    print("PASS: overlapping group moves, reverse scale, value edits and subframes", flush=True)

    c, curve = setup()
    cmds.cutKey(curve, time=(5, 5), clear=True)
    assert labels(c) == {10: "Extreme"}
    assert c.identity(curve, 5) not in c.store.read()
    cmds.undo()
    assert labels(c) == {5: "Key", 10: "Extreme"}, labels(c)
    cmds.redo()
    assert labels(c) == {10: "Extreme"}
    cmds.setKeyframe(curve, time=5, value=2)
    assert labels(c) == {10: "Extreme"}, "Replacement key inherited deleted label"
    cmds.cutKey(curve, time=(5, 5), clear=True)
    assert labels(c) == {10: "Extreme"}
    cmds.undo()
    assert labels(c) == {10: "Extreme"}, "Undo of unlabelled key restored stale label"
    print("PASS: delete, undo/redo, replacement keys and deleted-label cleanup", flush=True)

    c, curve = setup()
    cmds.delete(curve)
    tracker.flush()
    assert c.store.read() == {}, c.store.read()
    cmds.undo()
    assert labels(c) == {5: "Key", 10: "Extreme"}, labels(c)
    cmds.redo()
    tracker.flush()
    assert c.store.read() == {}
    c, curve = setup()
    cmds.cutKey(curve, clear=True)
    tracker.flush()
    assert c.store.read() == {}, c.store.read()
    cmds.undo()
    assert labels(c) == {5: "Key", 10: "Extreme"}, labels(c)
    print("PASS: whole curve deletion and deleting all keys, including Undo", flush=True)

    c, curve = setup()
    path = ROOT / "animation tool kit scripts/Add-Remove-Inbetweens_1_0_1/insert_remove_frames_tool.py"
    spec = importlib.util.spec_from_file_location("atk_frame_shift_test", path)
    frame_tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(frame_tool)
    cmds.currentTime(4)
    assert frame_tool.shift_keys([curve], 3, False)
    assert labels(c) == {8: "Key", 13: "Extreme"}, labels(c)
    assert frame_tool.shift_keys([curve], -2, False)
    assert labels(c) == {6: "Key", 11: "Extreme"}, labels(c)
    cmds.undo()
    assert labels(c) == {8: "Key", 13: "Extreme"}
    cmds.undo()
    assert labels(c) == {5: "Key", 10: "Extreme"}
    print("PASS: actual ATK Add/Remove Frames positive/negative shifts and chunk Undo", flush=True)

    c, curve = setup()
    frame_tool.get_time_range = lambda enabled: (5.0, 10.0)
    assert frame_tool.shift_keys([curve], 2, True)
    # The existing ranged tool applies its range shift and then its downstream
    # ripple as separate edits. Labels must follow the actual resulting keys.
    assert labels(c) == {7: "Key", 14: "Extreme"}, labels(c)
    cmds.undo()
    assert labels(c) == {5: "Key", 10: "Extreme"}
    cmds.redo()
    assert labels(c) == {7: "Key", 14: "Extreme"}, labels(c)
    # Annotation edits and key edits must undo together in the right order.
    cmds.currentTime(7)
    c.apply("Current frame", kind="Breakdown")
    assert labels(c) == {7: "Breakdown", 14: "Extreme"}, labels(c)
    cmds.undo()
    assert labels(c) == {7: "Key", 14: "Extreme"}, labels(c)
    # Scripted currentTime is itself undoable in Maya; undo that native step.
    cmds.undo()
    assert labels(c) == {7: "Key", 14: "Extreme"}, labels(c)
    cmds.undo()
    assert labels(c) == {5: "Key", 10: "Extreme"}, labels(c)
    print("PASS: ranged ripple shifts and interleaved annotation/key edit Undo", flush=True)

    c, curve = setup()
    cmds.keyframe(curve, edit=True, time=(5, 5), timeChange=6)
    cmds.keyframe(curve, edit=True, time=(6, 6), timeChange=7)
    assert labels(c) == {7: "Key", 10: "Extreme"}
    cmds.undo()
    cmds.undo()
    assert labels(c) == {5: "Key", 10: "Extreme"}
    print("PASS: chained edits before idle and immediate consecutive Undo", flush=True)

    c, curve = setup()
    cmds.keyframe(curve, edit=True, time=(5, 5), timeChange=7)
    # Save before manually flushing: the before-save callback must synchronize.
    with tempfile.TemporaryDirectory(prefix="atk_key_tracking_", dir=ROOT) as folder:
        scene = str(Path(folder) / "tracked.ma")
        cmds.file(rename=scene)
        cmds.file(save=True, type="mayaAscii")
        cmds.file(new=True, force=True)
        cmds.file(scene, open=True, force=True)
        assert labels(c) == {7: "Key", 10: "Extreme"}, labels(c)
        cmds.keyframe(curve, edit=True, time=(7, 7), timeChange=8)
        assert labels(c) == {8: "Key", 10: "Extreme"}
    print("PASS: immediate save, reopen and continued key tracking", flush=True)

    callbacks = len(tracker.callbacks)
    assert callbacks > 0
    ticks.shutdown()
    assert not tracker.callbacks
    print("PASS: service singleton and callback cleanup", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
        raise
    finally:
        ticks.shutdown()
        maya.standalone.uninitialize()
