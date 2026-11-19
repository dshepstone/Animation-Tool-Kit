"""Toolbar layouts inside Maya (run locally with mayapy; CI has no Maya).

    "C:\\Program Files\\Autodesk\\Maya2027\\bin\\mayapy.exe" tests/check_toolbar_layouts_maya.py

Works with Maya 2025, 2026 and 2027. The toolbar package is copied into a
throwaway scripts folder and built with Maya's real optionVars, icons and Qt:
every preset, both orientations, 1-3 rows/columns, expert mode, fold-out
popups, usage counting, migration of the old per-tool hide preferences, the
Layout tab, export/import and Reload Scripts. The ATK optionVars it touches
are saved first and put back at the end. Prints PASS or stops at the first
failed check with an AssertionError.

mayapy has no main window, so docking itself (workspaceControl) is not run
here; check docking on each side by hand (see the PR's checklist).
"""
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
import json
import shutil
import sys
import tempfile
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
try:
    from PySide6 import QtCore, QtWidgets
    import shiboken6 as shiboken
except ImportError:
    from PySide2 import QtCore, QtWidgets
    import shiboken2 as shiboken
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
import maya.standalone
maya.standalone.initialize(name="python")
from maya import cmds

STEPS = []
SAVED = {}


def step(text):
    STEPS.append(text)
    print("  ok: " + text)


def _atk_vars():
    return [v for v in (cmds.optionVar(list=True) or []) if v.startswith("atk_")]


def backup_vars():
    for name in _atk_vars():
        SAVED[name] = cmds.optionVar(q=name)


def restore_vars():
    for name in _atk_vars():
        cmds.optionVar(remove=name)
    for name, value in SAVED.items():
        if isinstance(value, str):
            cmds.optionVar(sv=(name, value))
        elif isinstance(value, float):
            cmds.optionVar(fv=(name, value))
        elif isinstance(value, int):
            cmds.optionVar(iv=(name, value))


def clear_vars():
    for name in _atk_vars():
        cmds.optionVar(remove=name)


def main():
    backup_vars()
    clear_vars()
    scratch = ROOT / "work"
    scratch.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=str(scratch)) as temp:
        scripts = Path(temp) / "scripts"
        icons = Path(temp) / "icons"
        scripts.mkdir()
        icons.mkdir()
        shutil.copytree(ROOT / "atk_toolbar", scripts / "atk_toolbar",
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        sys.path.insert(0, str(scripts))
        original_internal = cmds.internalVar

        def internal(**kwargs):
            if kwargs.get("userScriptDir"):
                return str(scripts) + os.sep
            if kwargs.get("userBitmapsDir"):
                return str(icons) + os.sep
            if kwargs.get("userPrefDir"):
                return str(temp) + os.sep
            return original_internal(**kwargs)

        with patch.object(cmds, "internalVar", side_effect=internal):
            run_checks(temp)
    print("PASS: toolbar layouts in Maya %s (%d checks)" % (cmds.about(version=True), len(STEPS)))


def run_checks(temp):
    from atk_toolbar import atk_loader, atk_layout, atk_toolbar, atk_settings
    registry = atk_loader.TOOL_REGISTRY
    all_ids = [t["id"] for t in registry]

    # 1. Upgrading from 1.1.16: the old per-tool hide prefs still apply.
    cmds.optionVar(iv=("atk_hidden_noise", 1))
    cmds.optionVar(iv=("atk_hidden_reset", 0))
    assert not cmds.optionVar(exists=atk_loader.OPT_LAYOUT)
    settings = atk_loader.get_layout_settings()
    assert settings["preset"] == "full" and settings["hidden"] == ["noise"], settings
    assert not atk_loader.is_tool_visible("noise") and atk_loader.is_tool_visible("reset")
    step("old atk_hidden_* prefs migrate into the layout")

    # 2. Real optionVar round trip; bad data falls back to Full.
    settings["preset"] = "grouped"
    atk_loader.save_layout_settings(settings)
    raw = cmds.optionVar(q=atk_loader.OPT_LAYOUT)
    assert json.loads(raw)["version"] == 1
    assert atk_loader.get_layout_settings()["preset"] == "grouped"
    assert cmds.optionVar(q="atk_hidden_noise") == 1
    cmds.optionVar(sv=(atk_loader.OPT_LAYOUT, "{broken"))
    assert atk_loader.get_layout_settings()["preset"] == "full"
    cmds.optionVar(sv=(atk_loader.OPT_USAGE, "[1, 2]"))
    assert atk_loader.get_usage() == {}
    atk_loader.reset_layout_settings()
    atk_loader.reset_usage()
    step("layout and usage optionVars: versioned JSON, bad data falls back")

    # 3. Build the real widget in every layout.
    def build(orientation, **layout):
        cmds.optionVar(sv=("atk_toolbar_orientation", orientation))
        s = atk_layout.default_settings(registry, atk_loader.GROUP_ORDER)
        s.update(layout)
        atk_loader.save_layout_settings(s)
        with patch.object(atk_toolbar.ATKToolbarWidget, "_add_inbetweener_slider"), \
                patch.object(atk_toolbar, "_show_frame_stepper", return_value=False):
            w = atk_toolbar.ATKToolbarWidget()
        w.show()
        app.processEvents()
        return w

    count = 0
    for orientation in ("horizontal", "vertical"):
        for preset in atk_layout.PRESETS:
            for lines in (1, 2, 3):
                for expert in (False, True):
                    w = build(orientation, preset=preset, lines=lines, expert=expert,
                              most_used_count=6)
                    shown = set(w._button_map)
                    for line in w._plan.lines:
                        for item in line:
                            shown.update(item.tools)
                    assert shown == set(all_ids), (orientation, preset, lines, expert)
                    if orientation == "horizontal":
                        assert w.maximumHeight() == atk_toolbar._horizontal_bar_height()
                    else:
                        assert w.width() == atk_toolbar._vertical_bar_width()
                    w.close()
                    w.deleteLater()
                    count += 1
    app.processEvents()
    step("toolbar builds in %d layouts (4 presets x 2 sides x 1-3 lines x expert)" % count)

    # 4. Rows / columns grow the bar the right way.
    sizes = []
    for lines in (1, 2, 3):
        build("horizontal", lines=lines).close()
        sizes.append(atk_toolbar._horizontal_bar_height())
    assert sizes[0] < sizes[1] < sizes[2], sizes
    build("vertical", lines=2).close()
    two = atk_toolbar._vertical_bar_width()
    build("vertical", lines=1).close()
    assert two > atk_toolbar._vertical_bar_width()
    step("rows make a top/bottom bar taller, columns make a side bar wider")

    # 5. Fold-outs keep icons, tooltips, quick actions and right-click menus.
    # The tool scripts are not installed in the throwaway folder; treat them
    # as installed so the buttons get their click actions.
    with patch.object(atk_loader, "is_tool_installed", return_value=True):
        w = build("horizontal", preset="grouped")
        btn = w._fold_buttons["group:viewport"]
        btn.click()
        app.processEvents()
        popup = w._popup
        assert popup is not None and popup.isVisible()
        snap = next(b for b in popup.buttons if b.objectName() == "atk_tool_anim_snap")
        assert not snap.icon().isNull() and "AnimSnap" in snap.toolTip()
        assert snap.contextMenuPolicy() == QtCore.Qt.CustomContextMenu
        with patch.object(atk_loader, "launch_tool_fn") as launch:
            snap.click()
        tool = next(t for t in registry if t["id"] == "anim_snap")
        launch.assert_called_once_with("anim_snap", tool["quick_fn"])
        app.processEvents()
        assert not shiboken.isValid(popup) or not popup.isVisible()
        w._fold_buttons["group:timing"].click()
        app.processEvents()
        assert w._popup.findChild(QtWidgets.QWidget, "timeline_ticks_palette") is not None
        w._popup.close()
        w.close()
    step("group fold-out popup: icons, tooltips, quick action, right-click, Timeline Ticks palette")

    # 6. Usage counting through the real launcher, ranking Most used.
    atk_loader.reset_usage()
    with patch.object(atk_loader, "_watch_launch", nullcontext):
        for _ in range(3):
            atk_loader.launch_tool_fn("user_directory_check", "no_such_function")
        atk_loader.launch_tool_fn("saveplus", "no_such_function")
        atk_loader.launch_tool_fn("timeline_ticks", "start_tracking", track=False)
    counts = atk_loader.get_usage()
    assert counts == {"user_directory_check": 3, "saveplus": 1}, counts
    w = build("horizontal", preset="most_used", most_used_count=3)
    inline = list(w._button_map)
    assert "user_directory_check" in inline and "saveplus" in inline, inline
    assert "more" in w._fold_buttons
    w.close()
    step("usage counted per launch (not for startup), Most used ranks it")

    # 7. Layout tab: live save, Apply keeps it, export / import.
    rebuilds = []
    dialog = atk_settings.ATKSettingsDialog(rebuild_callback=lambda: rebuilds.append(1))
    dialog._preset_combo.setCurrentIndex(dialog._preset_combo.findData("custom"))
    dialog._lines_spin.setValue(2)
    dialog._icon_size_combo.setCurrentIndex(dialog._icon_size_combo.findData(24))
    dialog._live_timer.stop()
    dialog._request_rebuild()
    assert rebuilds and atk_loader.get_layout_settings()["preset"] == "custom"
    dialog._apply()
    assert cmds.optionVar(q="atk_toolbar_icon_size") == 24
    path = os.path.join(temp, "layout.json")
    with patch.object(QtWidgets.QFileDialog, "getSaveFileName", return_value=(path, "")):
        dialog._export_layout()
    atk_loader.reset_layout_settings()
    with patch.object(QtWidgets.QFileDialog, "getOpenFileName", return_value=(path, "")):
        dialog._import_layout()
    s = atk_loader.get_layout_settings()
    assert s["preset"] == "custom" and s["lines"] == 2, s
    step("Layout tab saves live, Apply keeps it, export/import round trip")

    # 8. Reload Scripts rebuilds with the stored layout on fresh code.
    queued = []
    with patch.object(QtWidgets.QMessageBox, "information"), patch.object(
            QtCore.QTimer, "singleShot", side_effect=lambda ms, fn: queued.append(fn)):
        dialog._reload_scripts()
    assert "atk_toolbar" not in sys.modules and len(queued) == 1
    import atk_toolbar.atk_toolbar as fresh
    assert fresh is not atk_toolbar
    with patch.object(fresh, "show"):
        queued[0]()
    cmds.optionVar(sv=("atk_toolbar_orientation", "horizontal"))
    with patch.object(fresh.ATKToolbarWidget, "_add_inbetweener_slider"), \
            patch.object(fresh, "_show_frame_stepper", return_value=False):
        w = fresh.ATKToolbarWidget()
    assert w._plan.preset == "custom" and len(w._plan.lines) == 2
    w.close()
    step("Reload Scripts: fresh toolbar code rebuilds with the stored layout")


try:
    main()
finally:
    try:
        restore_vars()
    finally:
        maya.standalone.uninitialize()
