"""Build the real toolbar widget offscreen in every layout (PySide6, fake Maya).

Maya is replaced by small in-memory stand-ins for ``maya.cmds``,
``maya.mel`` and ``maya.OpenMayaUI``, so the toolbar package imports and
``ATKToolbarWidget`` renders the layout engine's plan with real Qt widgets.
"""
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]

try:
    from PySide6 import QtCore, QtWidgets
    import shiboken6 as shiboken
except ImportError:  # pragma: no cover
    QtWidgets = None


def _gone(widget):
    """True once a popup is closed (it deletes itself)."""
    return widget is None or not shiboken.isValid(widget) or not widget.isVisible()


class FakeCmds(types.ModuleType):
    """The few maya.cmds calls the toolbar makes, backed by a dict."""

    def __init__(self, temp_dir):
        super(FakeCmds, self).__init__("maya.cmds")
        self.vars = {}
        self.temp_dir = temp_dir
        self.warnings = []

    def optionVar(self, *args, **kw):
        if "exists" in kw:
            return kw["exists"] in self.vars
        if "q" in kw:
            return self.vars.get(kw["q"], 0)
        for flag in ("sv", "iv", "fv"):
            if flag in kw:
                key, value = kw[flag]
                self.vars[key] = value
                return None
        if "remove" in kw:
            self.vars.pop(kw["remove"], None)
        return None

    def internalVar(self, **kw):
        return self.temp_dir + os.sep

    def warning(self, msg):
        self.warnings.append(msg)

    def workspaceControl(self, *args, **kw):
        if kw.get("exists"):
            return False
        if kw.get("q"):
            return True if kw.get("floating") else 0
        return None

    def workspaceControlState(self, *args, **kw):
        return False

    def pluginInfo(self, *args, **kw):
        return False

    def loadPlugin(self, *args, **kw):
        return None

    def scriptJob(self, *args, **kw):
        return []

    def inViewMessage(self, *args, **kw):
        return None

    def __getattr__(self, name):
        return lambda *a, **k: None


def _install_fake_maya(temp_dir):
    cmds = FakeCmds(temp_dir)
    maya = types.ModuleType("maya")
    mel = types.ModuleType("maya.mel")
    mel.eval = lambda *a, **k: ""
    omui = types.ModuleType("maya.OpenMayaUI")
    omui.MQtUtil = types.SimpleNamespace(mainWindow=lambda: None,
                                         findControl=lambda name: None)
    maya.cmds, maya.mel, maya.OpenMayaUI = cmds, mel, omui
    modules = {"maya": maya, "maya.cmds": cmds, "maya.mel": mel, "maya.OpenMayaUI": omui}
    return cmds, modules


class _FakeMayaCase(unittest.TestCase):
    """Imports the toolbar package against the fake Maya modules."""

    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        cls.temp = tempfile.TemporaryDirectory()
        cls.cmds, fakes = _install_fake_maya(cls.temp.name)
        cls.saved = {n: sys.modules.get(n) for n in list(fakes) + ["atk_toolbar"]}
        for name in [n for n in sys.modules if n == "atk_toolbar" or n.startswith("atk_toolbar.")]:
            del sys.modules[name]
        sys.modules.update(fakes)
        sys.path.insert(0, str(ROOT))
        cls.tb = importlib.import_module("atk_toolbar.atk_toolbar")
        cls.loader = cls.tb.atk_loader
        cls.layout = cls.tb.atk_layout
        cls.registry = cls.loader.TOOL_REGISTRY
        cls.patches = [
            mock.patch.object(cls.loader, "start_tool_services", lambda: None),
            mock.patch.object(cls.loader, "is_tool_installed",
                              lambda tid: tid not in ("inbetweener", "add_remove")),
        ]
        for p in cls.patches:
            p.start()

    @classmethod
    def tearDownClass(cls):
        for p in cls.patches:
            p.stop()
        sys.path.remove(str(ROOT))
        for name in [n for n in sys.modules if n == "atk_toolbar" or n.startswith("atk_toolbar.")]:
            del sys.modules[name]
        for name, module in cls.saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module
        cls.temp.cleanup()

    def setUp(self):
        self.cmds.vars.clear()
        self.cmds.warnings[:] = []
        self.widgets = []

    def tearDown(self):
        for w in self.widgets:
            w.close()
            w.deleteLater()
        self.app.processEvents()

    # -- helpers ----------------------------------------------------------
    def configure(self, orientation="horizontal", icon_size=32, **layout):
        # The geometry checks below are written for Medium (32 px) icons.
        self.cmds.vars["atk_toolbar_orientation"] = orientation
        self.cmds.vars["atk_toolbar_icon_size"] = icon_size
        settings = self.layout.default_settings(self.registry, self.loader.GROUP_ORDER)
        settings.update(layout)
        self.loader.save_layout_settings(settings)

    def build(self, orientation="horizontal", **layout):
        self.configure(orientation, **layout)
        w = self.tb.ATKToolbarWidget()
        self.widgets.append(w)
        w.show()
        self.app.processEvents()
        return w

    def tool_buttons(self, w):
        return dict(w._button_map)

    def lines_block(self, w):
        return w.findChild(QtWidgets.QWidget, "atk_tool_lines")



@unittest.skipIf(QtWidgets is None, "PySide6 is required")
class ToolbarLayoutWidgetTests(_FakeMayaCase):
    def test_full_default_shows_every_tool_like_1_1_16(self):
        self.cmds.vars["atk_toolbar_orientation"] = "horizontal"
        w = self.tb.ATKToolbarWidget()   # no layout data stored at all
        self.widgets.append(w)
        self.assertEqual(list(w._button_map), [t["id"] for t in self.registry])
        self.assertEqual(w._fold_buttons, {})
        self.assertEqual(w._plan.preset, "full")
        # A fresh install starts with Small (24 px) icons.
        self.assertEqual(w._plan.icon_size, 24)
        self.assertEqual(w.findChild(QtWidgets.QToolButton, "atk_tool_anim_snap").width(), 32)

    def test_every_preset_builds_on_both_orientations_and_line_counts(self):
        for orientation in ("horizontal", "vertical"):
            for preset in self.layout.PRESETS:
                for lines in (1, 2, 3):
                    for expert in (False, True):
                        with self.subTest(o=orientation, p=preset, n=lines, e=expert):
                            w = self.build(orientation, preset=preset, lines=lines,
                                           expert=expert, most_used_count=5)
                            shown = set(w._button_map)
                            folded = set()
                            for item_id, btn in w._fold_buttons.items():
                                self.assertTrue(btn.isVisible())
                            for line in w._plan.lines:
                                for item in line:
                                    folded.update(item.tools)
                            all_ids = {t["id"] for t in self.registry}
                            self.assertEqual(shown | folded, all_ids)
                            block = self.lines_block(w)
                            self.assertEqual(block.layout().count(), len(w._plan.lines))
                            if expert:
                                self.assertEqual(w._plan.icon_size, 24)

    def test_rows_make_the_horizontal_bar_taller(self):
        heights = []
        for lines in (1, 2, 3):
            self.configure("horizontal", lines=lines)
            heights.append(self.tb._horizontal_bar_height())
        self.assertEqual(heights, [44, 86, 128])
        w = self.build("horizontal", lines=3)
        self.assertEqual(w.maximumHeight(), 128)

    def test_columns_make_the_vertical_bar_wider(self):
        widths = []
        for lines in (1, 2):
            self.configure("vertical", lines=lines)
            widths.append(self.tb._vertical_bar_width())
        self.assertEqual(widths[1] - widths[0], 42)
        w = self.build("vertical", lines=2)
        self.assertEqual(w.width(), widths[1])

    def test_fewer_tools_make_a_shorter_bar(self):
        self.configure("horizontal")
        full = self.tb._calc_content_width()
        self.configure("horizontal", preset="most_used", most_used_count=5)
        most = self.tb._calc_content_width()
        self.configure("horizontal", preset="grouped", expert=True)
        grouped = self.tb._calc_content_width()
        self.assertLess(most, full / 2)
        self.assertLess(grouped, most)

    def test_measured_width_matches_the_built_widget(self):
        for preset in self.layout.PRESETS:
            with self.subTest(preset=preset):
                w = self.build("horizontal", preset=preset, most_used_count=6)
                hint = self.lines_block(w).sizeHint().width()
                along, _ = self.layout.measure(w._plan, self.tb._EXTRA_SLOTS,
                                               self.tb._fold_label_px(w._plan, "horizontal"))
                self.assertEqual(hint, along)

    def test_grouped_popup_holds_the_group_tools_with_their_actions(self):
        w = self.build("horizontal", preset="grouped")
        btn = w._fold_buttons["group:viewport"]
        # The label space is measured with the real font, so built-in group
        # names fit whole on every platform.
        self.assertEqual(btn.accessibleName(), "Viewport")
        self.assertEqual(btn.text(), "Viewport")
        self.assertIn("Viewport", btn.toolTip())
        btn.click()
        self.app.processEvents()
        popup = w._popup
        self.assertIsNotNone(popup)
        self.assertTrue(popup.isVisible())
        names = [b.objectName() for b in popup.buttons]
        expected = ["atk_tool_" + t["id"] for t in self.registry if t["group"] == "viewport"]
        self.assertEqual(names, expected)
        snap = popup.buttons[names.index("atk_tool_anim_snap")]
        self.assertIn("AnimSnap", snap.toolTip())
        self.assertEqual(snap.contextMenuPolicy(), QtCore.Qt.CustomContextMenu)
        # Left-click runs the quick action, counts a use and closes the strip.
        with mock.patch.object(self.loader, "launch_tool_fn") as launch:
            snap.click()
        quick = next(t for t in self.registry if t["id"] == "anim_snap")["quick_fn"]
        launch.assert_called_once_with("anim_snap", quick)
        self.app.processEvents()
        self.assertTrue(_gone(popup))

    def test_more_button_holds_the_rest_in_registry_order(self):
        self.cmds.vars["atk_toolbar_usage"] = json.dumps(
            {"version": 1, "counts": {"saveplus": 5, "anim_snap": 3}})
        w = self.build("horizontal", preset="most_used", most_used_count=3)
        self.assertEqual(list(w._button_map), ["timeline_ticks", "anim_snap", "saveplus"])
        w._fold_buttons["more"].click()
        self.app.processEvents()
        names = [b.objectName() for b in w._popup.buttons]
        rest = [t["id"] for t in self.registry
                if t["id"] not in ("timeline_ticks", "anim_snap", "saveplus")]
        # Tangent Tools brings its three quick tangent buttons along.
        self.assertEqual([n for n in names if not n.startswith("atk_tangent_")],
                         ["atk_tool_" + r for r in rest])
        self.assertEqual(sum(n.startswith("atk_tangent_") for n in names), 3)

    def test_folded_timeline_ticks_palette_keeps_its_strips(self):
        w = self.build("horizontal", preset="grouped")
        w._fold_buttons["group:timing"].click()
        self.app.processEvents()
        palette = w._popup.findChild(QtWidgets.QWidget, "timeline_ticks_palette")
        self.assertIsNotNone(palette)
        yellow = palette.findChild(QtWidgets.QToolButton, "timeline_ticks_yellow")
        with mock.patch.object(self.loader, "launch_tool_fn") as launch:
            yellow.click()
        launch.assert_called_once_with("timeline_ticks", "apply_yellow")

    def test_clicking_the_open_group_again_does_not_reopen(self):
        w = self.build("horizontal", preset="grouped")
        btn = w._fold_buttons["group:rigging"]
        btn.click()
        self.app.processEvents()
        w._popup.close()          # the outside click that closes it...
        btn.click()               # ...also reaches the button
        self.app.processEvents()
        self.assertTrue(_gone(w._popup))

    def test_open_group_is_inline(self):
        w = self.build("horizontal", preset="grouped", group_open={"timing": True})
        self.assertIn("timeline_ticks", w._button_map)
        self.assertNotIn("group:timing", w._fold_buttons)
        self.assertIn("group:pipeline", w._fold_buttons)

    def test_custom_order_hidden_and_custom_group(self):
        order = ["saveplus", "anim_snap"] + [t["id"] for t in self.registry
                                             if t["id"] not in ("saveplus", "anim_snap")]
        w = self.build("horizontal", preset="custom", order=order, hidden=["noise"],
                       custom_groups=[{"name": "Keys", "tools": ["tween_machine", "overlap"],
                                       "open": False}])
        ids = list(w._button_map)
        self.assertEqual(ids[:2], ["saveplus", "anim_snap"])
        self.assertNotIn("noise", ids)
        self.assertNotIn("tween_machine", ids)
        self.assertIn("custom:0", w._fold_buttons)

    def test_expert_fold_buttons_are_icons_only(self):
        w = self.build("horizontal", preset="grouped", expert=True)
        btn = w._fold_buttons["group:timing"]
        self.assertEqual(btn.text(), "")
        self.assertEqual(btn.width(), 28)

    def test_vertical_fold_buttons_are_icons_only(self):
        w = self.build("vertical", preset="grouped")
        self.assertEqual(w._fold_buttons["group:timing"].text(), "")

    def test_usage_is_counted_for_clicks_menus_and_tangents(self):
        w = self.build("horizontal")
        w._button_map["overlap"].click()          # launches the window
        w._button_map["anim_snap"].click()        # quick_fn
        tool = next(t for t in self.registry if t["id"] == "anim_snap")
        menu = w._tool_menu(tool, True)
        next(a for a in menu.actions() if a.text() == tool["context_actions"][0][0]).trigger()
        w.findChild(QtWidgets.QToolButton, "atk_tangent_linear").click()
        counts = self.loader.get_usage()
        self.assertEqual(counts, {"overlap": 1, "anim_snap": 2, "tangent_tools": 1})

    def test_startup_services_are_not_counted(self):
        self.loader.launch_tool_fn("timeline_ticks", "start_tracking", track=False)
        self.assertEqual(self.loader.get_usage(), {})

    def test_old_hidden_prefs_still_hide_tools(self):
        self.cmds.vars["atk_toolbar_orientation"] = "horizontal"
        self.cmds.vars["atk_hidden_noise"] = 1
        self.cmds.vars["atk_hidden_reset"] = 0
        w = self.tb.ATKToolbarWidget()
        self.widgets.append(w)
        self.assertNotIn("noise", w._button_map)
        self.assertIn("reset", w._button_map)
        self.assertFalse(self.loader.is_tool_visible("noise"))

    def test_hiding_writes_the_old_prefs_too(self):
        self.loader.set_tool_visible("onion_skin", False)
        self.assertEqual(self.cmds.vars["atk_hidden_onion_skin"], 1)
        self.assertEqual(self.loader.get_layout_settings()["hidden"], ["onion_skin"])
        self.loader.set_tool_visible("onion_skin", True)
        self.assertEqual(self.cmds.vars["atk_hidden_onion_skin"], 0)

    def test_broken_stored_layout_falls_back_to_full(self):
        self.cmds.vars["atk_toolbar_orientation"] = "horizontal"
        self.cmds.vars["atk_toolbar_layout"] = "{not json"
        self.cmds.vars["atk_toolbar_usage"] = "[]"
        w = self.tb.ATKToolbarWidget()
        self.widgets.append(w)
        self.assertEqual(w._plan.preset, "full")
        self.assertEqual(len(w._button_map), len(self.registry))

    def test_rebuild_switches_layout_in_place(self):
        w = self.build("horizontal")
        self.configure("horizontal", preset="grouped")
        w._build()
        self.app.processEvents()
        self.assertEqual(w._button_map, {})
        self.assertEqual(len(w._fold_buttons), 4)

    def test_gear_menu_has_layout_presets(self):
        w = self.build("horizontal")
        menu = QtWidgets.QMenu()
        sub = w._add_layout_menu(menu)
        labels = [a.text() for a in sub.actions() if a.text()]
        self.assertEqual(labels[:4], ["Full", "Most used", "Custom", "Grouped"])
        self.assertIn("Expert Mode", labels)
        with mock.patch.object(self.tb.QtCore.QTimer, "singleShot"):
            next(a for a in sub.actions() if a.text() == "Grouped").trigger()
        self.assertEqual(self.loader.get_layout_settings()["preset"], "grouped")

    def test_alignment_stretches(self):
        for align, before, after in (("left", False, True), ("center", True, True),
                                     ("right", True, False)):
            self.cmds.vars["atk_toolbar_icon_alignment"] = align
            w = self.build("horizontal")
            lay = w.layout()
            first, last = lay.itemAt(4), lay.itemAt(lay.count() - 1)
            self.assertEqual(first.spacerItem() is not None, before, align)
            self.assertEqual(last.spacerItem() is not None, after, align)



@unittest.skipIf(QtWidgets is None, "PySide6 is required")
class LayoutTabTests(_FakeMayaCase):
    """Settings → Layout: every change is saved and rebuilds the toolbar."""

    def dialog(self):
        rebuilds = []
        d = self.tb.atk_settings.ATKSettingsDialog(rebuild_callback=lambda: rebuilds.append(1))
        self.widgets.append(d)
        return d, rebuilds

    def settle(self, d):
        """Fire the live-preview timer now."""
        if d._live_timer.isActive():
            d._live_timer.stop()
            d._request_rebuild()

    def test_layout_tab_is_first_and_selectable(self):
        d, _ = self.dialog()
        self.assertEqual(d._tabs.tabText(0), "Layout")
        d.select_tab("About")
        self.assertEqual(d._tabs.tabText(d._tabs.currentIndex()), "About")

    def test_preset_change_is_live(self):
        d, rebuilds = self.dialog()
        d._preset_combo.setCurrentIndex(d._preset_combo.findData("grouped"))
        self.assertEqual(self.loader.get_layout_settings()["preset"], "grouped")
        self.settle(d)
        self.assertEqual(rebuilds, [1])
        self.assertFalse(d._most_used_spin.isEnabled())
        self.assertTrue(d._groups_box.isEnabled())

    def test_quick_clicks_give_one_rebuild(self):
        d, rebuilds = self.dialog()
        d._expert_cb.setChecked(True)
        d._lines_spin.setValue(2)
        d._icon_size_combo.setCurrentIndex(d._icon_size_combo.findData(48))
        self.settle(d)
        self.assertEqual(rebuilds, [1])
        s = self.loader.get_layout_settings()
        self.assertTrue(s["expert"])
        self.assertEqual(s["lines"], 2)
        self.assertEqual(self.cmds.vars["atk_toolbar_icon_size"], 48)

    def test_untick_and_reorder_tools(self):
        d, _ = self.dialog()
        first = d._tool_list.item(0)
        first.setCheckState(QtCore.Qt.Unchecked)
        self.assertEqual(self.loader.get_layout_settings()["hidden"], ["timeline_ticks"])
        self.assertEqual(self.cmds.vars["atk_hidden_timeline_ticks"], 1)
        d._tool_list.setCurrentRow(2)
        d._move_tool(-1)
        order = self.loader.get_layout_settings()["order"]
        self.assertEqual(order[:3], ["timeline_ticks", "add_remove", "inbetweener"])
        d._show_all_tools()
        self.assertEqual(self.loader.get_layout_settings()["hidden"], [])

    def test_apply_keeps_layout_changes(self):
        d, _ = self.dialog()
        d._icon_size_combo.setCurrentIndex(d._icon_size_combo.findData(24))
        d._halign_combo.setCurrentIndex(d._halign_combo.findData("right"))
        d._apply()
        self.assertEqual(self.cmds.vars["atk_toolbar_icon_size"], 24)
        self.assertEqual(self.cmds.vars["atk_toolbar_icon_alignment"], "right")

    def test_custom_group_new_and_open(self):
        d, _ = self.dialog()
        with mock.patch.object(QtWidgets.QInputDialog, "getText", return_value=("Keys", True)), \
                mock.patch.object(d, "_pick_tools", return_value=["overlap", "noise"]):
            d._new_custom_group()
        groups = self.loader.get_layout_settings()["custom_groups"]
        self.assertEqual(groups, [{"name": "Keys", "tools": ["overlap", "noise"], "open": False}])
        d._custom_open_cb.setChecked(True)
        self.assertTrue(self.loader.get_layout_settings()["custom_groups"][0]["open"])
        d._delete_custom_group()
        self.assertEqual(self.loader.get_layout_settings()["custom_groups"], [])

    def test_export_then_import(self):
        d, rebuilds = self.dialog()
        d._preset_combo.setCurrentIndex(d._preset_combo.findData("most_used"))
        d._most_used_spin.setValue(7)
        path = os.path.join(self.temp.name, "layout.json")
        with mock.patch.object(QtWidgets.QFileDialog, "getSaveFileName", return_value=(path, "")):
            d._export_layout()
        with open(path, encoding="utf-8") as handle:
            self.assertEqual(json.load(handle)["layout"]["most_used_count"], 7)
        self.loader.reset_layout_settings()
        with mock.patch.object(QtWidgets.QFileDialog, "getOpenFileName", return_value=(path, "")):
            d._import_layout()
        s = self.loader.get_layout_settings()
        self.assertEqual((s["preset"], s["most_used_count"]), ("most_used", 7))
        self.assertEqual(d._most_used_spin.value(), 7)

    def test_import_rejects_other_files(self):
        d, _ = self.dialog()
        path = os.path.join(self.temp.name, "other.json")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write('{"hello": 1}')
        with mock.patch.object(QtWidgets.QFileDialog, "getOpenFileName", return_value=(path, "")), \
                mock.patch.object(QtWidgets.QMessageBox, "warning") as warn:
            d._import_layout()
        warn.assert_called_once()
        self.assertEqual(self.loader.get_layout_settings()["preset"], "full")

    def test_menu_changes_refresh_the_open_dialog(self):
        d, _ = self.dialog()
        d.show()
        self.tb.atk_settings._dialog_instance = d
        try:
            with mock.patch.object(self.tb.QtCore.QTimer, "singleShot"):
                self.tb._set_layout_field("preset", "grouped")
                self.tb._set_layout_field("expert", True)
                item = self.layout.Item("group", "group:timing", "Timing", "timing", ())
                self.tb._set_fold_open(item, True)
            self.assertEqual(d._preset_combo.currentData(), "grouped")
            self.assertTrue(d._expert_cb.isChecked())
            self.assertTrue(d._group_open_checks["timing"].isChecked())
            # Apply must not put the old values back.
            d._apply()
            s = self.loader.get_layout_settings()
            self.assertEqual((s["preset"], s["expert"], s["group_open"]["timing"]),
                             ("grouped", True, True))
        finally:
            self.tb.atk_settings._dialog_instance = None

    def test_reset_layout_and_usage(self):
        self.loader.record_usage("anim_snap")
        d, _ = self.dialog()
        d._preset_combo.setCurrentIndex(d._preset_combo.findData("custom"))
        with mock.patch.object(QtWidgets.QMessageBox, "question",
                               return_value=QtWidgets.QMessageBox.Yes):
            d._reset_layout()
            d._reset_usage()
        self.assertEqual(self.loader.get_layout_settings()["preset"], "full")
        self.assertEqual(d._preset_combo.currentData(), "full")
        self.assertEqual(self.loader.get_usage(), {})

if __name__ == "__main__":
    unittest.main()
