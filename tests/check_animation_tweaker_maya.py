"""Animation Tweaker inside Maya (run locally with mayapy; CI has no Maya).

    "C:\\Program Files\\Autodesk\\Maya2027\\bin\\mayapy.exe" tests/check_animation_tweaker_maya.py

Works with Maya 2025, 2026 and 2027. It installs the package with the real
MEL installer block into a throwaway scripts folder, builds a small skinned
scene, and drives the engine and the window the way an artist would. No
preferences or user scripts are touched. Prints PASS or stops at the first
failed check with an AssertionError.
"""
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
import shutil
import sys
import tempfile
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
try:
    from PySide6 import QtCore, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtWidgets
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
import maya.standalone
maya.standalone.initialize(name="python")
from maya import cmds, mel
from maya.app.general.mayaMixin import MayaQWidgetDockableMixin

STEPS = []


def step(text):
    STEPS.append(text)
    print("  ok: " + text)


def near(a, b, tol=1e-4):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def skinned_tube():
    """A cylinder on two joints; the top joint bends 60 degrees over frames 1-20."""
    cmds.file(new=True, force=True)
    cmds.playbackOptions(minTime=1, maxTime=20)
    mesh = cmds.polyCylinder(name="tube", height=4, subdivisionsY=8, subdivisionsX=12, radius=0.5)[0]
    cmds.move(0, 2, 0, mesh)
    cmds.makeIdentity(mesh, apply=True, translate=True)
    cmds.select(clear=True)
    root = cmds.joint(name="root_jnt", position=(0, 0, 0))
    tip = cmds.joint(name="mid_jnt", position=(0, 2, 0))
    cmds.joint(name="end_jnt", position=(0, 4, 0))
    cmds.skinCluster(root, tip, mesh, toSelectedBones=True, name="tube_skin")
    cmds.setKeyframe(tip, attribute="rotateZ", time=1, value=0)
    cmds.setKeyframe(tip, attribute="rotateZ", time=20, value=60)
    cmds.currentTime(1)
    return mesh


def install(temp):
    scripts = Path(temp) / "scripts"
    icons = Path(temp) / "icons"
    scripts.mkdir()
    icons.mkdir()
    shutil.copytree(ROOT / "atk_toolbar", scripts / "atk_toolbar",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    installer = (ROOT / "install_atk_toolbar.mel").read_text(encoding="utf-8")
    mel.eval(installer.rsplit("atk__install();", 1)[0])
    begin = installer.index("    // Animation Tweaker ships as an isolated ATK package")
    end = installer.index("    // Playblast Creator", begin)
    tools = (ROOT / "animation tool kit scripts").as_posix() + "/"
    mel.eval('string $toolsBase = "' + tools + '"; string $scriptsDir = "' + scripts.as_posix()
             + '/";\n' + installer[begin:end])
    installed = scripts / "atk_tweaker"
    assert (installed / "resources" / "help.html").is_file()
    assert (installed / "assets" / "animation_tweaker_32.png").is_file()
    assert not list(installed.rglob("__pycache__"))
    shutil.copyfile(installed / "assets" / "animation_tweaker_32.png", icons / "animation_tweaker_32.png")
    sys.path.insert(0, str(scripts))
    step("MEL installer copies the package, help and icon")
    return scripts, icons


def check_engine():
    from atk_tweaker import core, engine
    mesh = skinned_tube()
    xf, shape = engine.resolve_mesh(mesh)
    node = engine.ensure_tweak_node(mesh)
    deformers = cmds.listHistory(shape, pruneDagObjects=True, interestLevel=1) or []
    order = [d for d in deformers if cmds.nodeType(d) in ("blendShape", "skinCluster")]
    assert order[:2] == [node, "tube_skin"], order       # nearest the shape = evaluated last
    step("tweak blendShape sits after the skinCluster")

    # Sculpt on frame 10, move one vertex 0.3 along X, commit as a static tweak.
    cmds.currentTime(10)
    before = engine.read_points(shape)
    sculpt = engine.start_sculpt(mesh, mode=core.MODE_STATIC, highlight=True, hide_original=True)
    assert not cmds.getAttr(xf + ".visibility")
    assert cmds.objExists(engine.SCULPT_SHADER)
    cmds.move(0.3, 0, 0, sculpt + ".vtx[30]", relative=True, objectSpace=True)
    index = engine.commit_sculpt(mesh)
    assert index is not None and not cmds.objExists(sculpt)
    assert cmds.getAttr(xf + ".visibility") and not cmds.objExists(engine.SCULPT_SHADER)
    after = engine.read_points(shape)
    assert near(after[30], (before[30][0] + 0.3, before[30][1], before[30][2])), (before[30], after[30])
    assert near(after[0], before[0])
    assert engine.read_target(node, index) and engine.alias_map(node)[index].startswith("tw_")
    assert engine.read_meta(node)["targets"][index]["mode"] == core.MODE_STATIC
    step("sculpt, commit and object-space delta write")

    cmds.undo()
    assert near(engine.read_points(shape)[30], before[30])
    # Undoing a commit returns to the sculpt state, so the sculpt mesh is back.
    assert cmds.objExists(sculpt) and not engine.read_target(node, index)
    cmds.redo()
    assert not cmds.objExists(sculpt)
    assert near(engine.read_points(shape)[30], after[30])
    step("commit is one Undo")

    # Cancel restores everything, including muted tweaks.
    sculpt = engine.start_sculpt(mesh, mute=core.MUTE_ALL)
    assert cmds.getAttr(engine.weight_plug(node, index)) == 0.0
    engine.cancel_sculpt(mesh)
    assert cmds.getAttr(engine.weight_plug(node, index)) == 1.0 and not cmds.objExists(sculpt)
    step("cancel and sculpt-from-zero restore")

    # Sequence poses crossfade.
    with engine.undo_chunk("poses"):
        a = engine.commit_delta(mesh, {5: (0, 0.2, 0)}, core.MODE_SEQUENCE, 4, "L1")
        b = engine.commit_delta(mesh, {5: (0, 0.6, 0)}, core.MODE_SEQUENCE, 12, "L1")
    cmds.currentTime(8)
    wa, wb = cmds.getAttr(engine.weight_plug(node, a)), cmds.getAttr(engine.weight_plug(node, b))
    assert abs(wa - 0.5) < 1e-4 and abs(wb - 0.5) < 1e-4, (wa, wb)
    engine.hold_pose(mesh, "L1", 16)
    engine.blank_pose(mesh, "L1", 20)
    engine.delete_tweaks(mesh, [b])
    assert b not in engine.read_meta(node)["targets"]
    step("sequence keys, hold, blank, delete with rekey")

    cmds.currentTime(10)
    engine.set_proxies(mesh, True)
    assert cmds.attributeQuery("TWEAKS", node=xf, exists=True)
    engine.set_proxies(mesh, False)
    assert not cmds.attributeQuery("TWEAKS", node=xf, exists=True)
    step("proxy channels on and off")

    check_keying(mesh, node)

    cmds.select(xf + ".vtx[40:60]")
    engine.relax(mesh, 3, 0.5)
    engine.inflate(mesh, 0.05)
    engine.scale_tweak(mesh, index, 2.0)
    step("relax, inflate, amplify")
    return mesh


def check_keying(mesh, node):
    """Hand keys, key navigation and re-keying a tweak's mode."""
    from atk_tweaker import core, engine
    with engine.undo_chunk("key test tweak"):
        t = engine.commit_delta(mesh, {7: (0.1, 0, 0)}, core.MODE_STATIC, 1, label="hand")
    plug = engine.driver_plug(node, t)
    assert engine.key_times(plug) == []
    engine.key_tweaks(mesh, [t], 0.0, frame=2)
    engine.key_tweaks(mesh, [t], 1.0, frame=8)
    assert engine.read_meta(node)["targets"][t]["mode"] == core.MODE_MANUAL
    assert engine.key_times(plug) == [2.0, 8.0]
    cmds.currentTime(5)
    assert abs(cmds.getAttr(plug) - 0.5) < 1e-4
    row = [r for r in engine.list_tweaks(mesh) if r["index"] == t][0]
    assert row["key_state"] == "animated" and row["keys"] == 2
    assert engine.jump_to_key(mesh, [t], 1) == 8.0
    assert [r for r in engine.list_tweaks(mesh) if r["index"] == t][0]["key_state"] == "key"
    assert engine.jump_to_key(mesh, [t], -1) == 2.0
    assert engine.remove_tweak_keys(mesh, [t]) == 1 and engine.key_times(plug) == [8.0]
    cmds.undo()
    assert engine.key_times(plug) == [2.0, 8.0]
    # Re-key as a pulse around frame 10, then as static; manual keys are replaced.
    engine.set_tweak_mode(mesh, [t], core.MODE_PULSE, frame=10, ramp_in=2, ramp_out=2)
    assert engine.key_times(plug) == [8.0, 10.0, 12.0]
    assert engine.read_meta(node)["targets"][t]["mode"] == core.MODE_PULSE
    engine.set_tweak_mode(mesh, [t], core.MODE_STATIC)
    assert engine.key_times(plug) == [] and cmds.getAttr(plug) == 1.0
    # A sequence pose keyed by hand leaves its level; the level rekeys without it.
    with engine.undo_chunk("two poses"):
        p1 = engine.commit_delta(mesh, {9: (0, 0.1, 0)}, core.MODE_SEQUENCE, 3, "K")
        p2 = engine.commit_delta(mesh, {9: (0, 0.3, 0)}, core.MODE_SEQUENCE, 9, "K")
    engine.key_tweaks(mesh, [p2], 0.25, frame=9)
    meta = engine.read_meta(node)
    assert meta["targets"][p2]["mode"] == core.MODE_MANUAL
    assert core.level_entries(meta, "K") == [(p1, 3.0)]
    # Clearing keys holds the weight the tweak shows now.
    cmds.currentTime(9)
    engine.clear_tweak_keys(mesh, [p2])
    assert engine.key_times(engine.driver_plug(node, p2)) == []
    assert abs(cmds.getAttr(engine.driver_plug(node, p2)) - 0.25) < 1e-4
    engine.delete_tweaks(mesh, [t, p1, p2])
    step("hand keys, key navigation, re-key as pulse/static, leave a level")


def check_effects(mesh):
    from atk_tweaker import core, effects, engine
    xf, shape = engine.resolve_mesh(mesh)
    cmds.select(xf + ".vtx[80:95]")
    count = effects.pin_to_world(mesh, 1, 20, bind_frame=1)
    assert count == 20
    world_1 = effects._world_points(engine.sample_points(shape, 1), engine.world_matrix(xf, 1))
    world_20 = effects._world_points(engine.sample_points(shape, 20), engine.world_matrix(xf, 20))
    assert near(world_1[85], world_20[85], 1e-3), (world_1[85], world_20[85])
    step("Pin to World holds vertices (MDGContext sampling)")
    cmds.select(xf + ".vtx[80:95]")
    effects.smooth_motion(mesh, 1, 20, sigma=1.5)
    assert engine.read_meta(engine.find_tweak_node(mesh))["targets"]
    ground = cmds.polyPlane(name="ground", width=10, height=10)[0]
    cmds.move(0, 1.0, 0, ground)
    cmds.select(xf + ".vtx[0:23]")
    effects.push_out(mesh, ground, 1, 3, skin_offset=0.05)
    cmds.select(xf + ".vtx[0:23]")
    effects.stick_to_surface(mesh, ground, 1, 3, bind_frame=1)
    assert effects.remove_effect(mesh, core.KIND_STICK) == 3
    step("Smooth Motion, Push Out, Stick to Surface, remove effect")


def check_handle(mesh):
    from atk_tweaker import core, surface_handle, engine
    xf, shape = engine.resolve_mesh(mesh)
    cmds.currentTime(1)
    cmds.select(xf + ".vtx[70]")
    handle = surface_handle.create_handle(radius=0.8)
    record = surface_handle.handle_record(handle)
    assert record["uvPin"] and cmds.objExists(record["softMod"])
    rest = engine.read_points(shape)
    cmds.currentTime(20)
    moved = engine.read_points(shape)
    cmds.currentTime(1)
    assert near(engine.read_points(shape)[70], rest[70])     # handle at rest: no change on frame 1
    cmds.setAttr(handle + ".translateX", 0.5)
    pushed = engine.read_points(shape)
    assert core.v_length(core.v_sub(pushed[70], rest[70])) > 0.2, (rest[70], pushed[70])
    cmds.setAttr(handle + ".translateX", 0)
    cmds.currentTime(20)
    assert near(engine.read_points(shape)[70], moved[70], 1e-3)  # riding the bend adds nothing
    step("Surface Handle rides the skin and is neutral at rest")
    surface_handle.apply_falloff_curve(handle, "Dome")
    surface_handle.show_falloff(handle, False)
    surface_handle.set_falloff_colour(handle, "#ff0000")
    surface_handle.orient_to_world(handle, True)
    loc = cmds.spaceLocator(name="aim_loc")[0]
    surface_handle.aim_at(handle, loc)
    surface_handle.clear_aim(handle)
    surface_handle.delete_handle(handle)
    assert not cmds.objExists(record["softMod"])
    step("handle falloff shape, display, orient, aim, delete")


def check_utilities(mesh):
    from atk_tweaker import utilities, engine
    xf, _shape = engine.resolve_mesh(mesh)
    cmds.select(xf + ".vtx[10]")
    created = utilities.bake_followers("card", 0.2, 1, 5)
    assert len(created) == 1 and cmds.keyframe(created[0], query=True, keyframeCount=True)
    cmds.select(xf)
    assert utilities.toggle_smooth_preview() in (True, False)
    utilities.apply_colour("#5cb85c", [xf])
    assert cmds.objExists("atkColour_5cb85c")
    a = cmds.spaceLocator(name="copy_src")[0]
    b = cmds.spaceLocator(name="copy_dst")[0]
    cmds.setAttr(a + ".tx", 3.5)
    utilities.copy_channels([a])
    assert utilities.paste_channels([b]) > 0 and cmds.getAttr(b + ".tx") == 3.5
    cmds.optionVar(remove=utilities.CLIPBOARD_VAR)
    copy = utilities.extract_faces(["%s.f[0:5]" % xf])
    assert cmds.polyEvaluate(copy, face=True) == 6
    step("followers, smooth preview, colour, channel clipboard, live extract")


def check_cache(mesh, temp):
    from atk_tweaker import cache_versions
    try:
        cmds.loadPlugin("AbcExport", quiet=True)
        cmds.loadPlugin("AbcImport", quiet=True)
    except RuntimeError:
        print("  skipped: Alembic plug-ins not available")
        return
    path = str(Path(temp) / "tube_v001.abc")
    cache_versions.export_selected(path, 1, 3, [mesh])
    label = cache_versions.import_version(path)
    second = cache_versions.import_version(path)
    assert cache_versions.attach(label) == 1
    cache_versions.swap(second)
    cmds.setAttr(cache_versions.CONTROL + ".envelope", 0.5)
    cache_versions.delete_version(label)
    cache_versions.delete_all()
    assert not cmds.objExists(cache_versions.CONTROL)
    step("Alembic export, import versions, attach, swap, delete")


def engine_start(panel):
    from atk_tweaker import engine
    return engine.start_sculpt(panel.mesh())


def check_ui_and_toolbar(scripts, icons):
    original_internal = cmds.internalVar

    def internal(**kwargs):
        if kwargs.get("userScriptDir"):
            return str(scripts) + os.sep
        if kwargs.get("userBitmapsDir"):
            return str(icons) + os.sep
        return original_internal(**kwargs)

    with patch.object(cmds, "internalVar", side_effect=internal), patch.object(
            MayaQWidgetDockableMixin, "setVisible", QtWidgets.QDialog.setVisible):
        from atk_toolbar import atk_loader, atk_icons
        atk_loader.setup_paths()
        assert atk_loader.is_tool_installed("animation_tweaker")
        import atk_tweaker.ui as ui

        def show_without_workspace(self, *args, **kwargs):
            return QtWidgets.QDialog.show(self)
        with patch.object(ui.Window, "show", show_without_workspace), patch.object(
                atk_loader, "_watch_launch", nullcontext):
            atk_loader.launch_tool("animation_tweaker")
            first = ui._window
            assert first.objectName() == ui.WINDOW_NAME and first.isVisible()
            mesh = skinned_tube()
            cmds.select(mesh)
            first.panel.use_selected()
            cmds.currentTime(5)
            first.panel.start_sculpt()
            first.panel.commit()                      # nothing sculpted: warns, stores nothing
            first.panel.inflate(1.0)
            assert first.panel.tree.topLevelItemCount() == 1
            panel = first.panel
            # Brush shelf: every brush has a button; picking one with a sculpt
            # open selects the copy first.
            from atk_tweaker import sculpt_brushes
            assert set(panel.brush_buttons) == {b[0] for b in sculpt_brushes.ALL_BRUSHES}
            sculpt = engine_start(panel)
            panel.pick_brush("smooth")
            assert cmds.ls(selection=True, long=True) == [sculpt]
            assert sculpt_brushes.last_brush() == "smooth"
            panel.cancel()
            # Animate box: key the selected tweak by hand, colours follow the frame.
            item = panel.tree.topLevelItem(0)
            item.setSelected(True)
            cmds.currentTime(3)
            panel.key_selected(0.0)
            cmds.currentTime(9)
            panel.tree.topLevelItem(0).setSelected(True)
            panel.key_selected(1.0)
            index = panel.tree.topLevelItem(0).data(0, QtCore.Qt.UserRole)
            assert panel.tree.topLevelItem(0).text(2) == "keyed"
            cmds.currentTime(6)
            panel.sync_keys()
            assert abs(panel.cells[index].value() - 0.5) < 0.011
            # scriptJob needs the interactive Maya UI; mayapy batch mode has none.
            assert cmds.about(batch=True) or cmds.scriptJob(exists=panel._time_job)
            ui.close()
            atk_loader.launch_tool("animation_tweaker")
            assert ui._window is not first
            stale = [w for w in QtWidgets.QApplication.allWidgets()
                     if w.objectName() == ui.WINDOW_NAME and w.isVisible()]
            assert len(stale) == 1
        assert not atk_icons._generate_icon("tweaker", "rigging", 32).isNull()
        import atk_tweaker
        atk_tweaker.shutdown()
    step("toolbar launch, window, stale-window cleanup, fallback icon")


def main():
    scratch = ROOT / "work"
    scratch.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=str(scratch)) as temp:
        scripts, icons = install(temp)
        mesh = check_engine()
        check_effects(mesh)
        check_handle(mesh)
        check_utilities(mesh)
        check_cache(mesh, temp)
        check_ui_and_toolbar(scripts, icons)
    print("PASS: Animation Tweaker in Maya %s (%d checks)" % (cmds.about(version=True), len(STEPS)))


try:
    main()
finally:
    maya.standalone.uninitialize()
