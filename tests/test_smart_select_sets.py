"""Smart Select Sets: button order, category names and pop-out lifecycle.

Runs the real tool module offscreen with PySide6 and a small in-memory
stand-in for ``maya.cmds`` (no Maya needed).
"""
import importlib.util
import os
from pathlib import Path
import sys
import types
import unittest
import unittest.mock

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "animation tool kit scripts" / "selection_set_2_0_4" / "SmartSelectSets_v2.py"

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6 import QtCore, QtGui, QtWidgets
    import shiboken6
except ImportError:  # pragma: no cover
    QtWidgets = None


class FakeCmds(types.ModuleType):
    """Scene objects are plain names; one string attribute store."""

    def __init__(self):
        super().__init__("maya.cmds")
        self.objects = set()
        self.attrs = {}
        self.selection = []
        self.jobs = set()
        self._next_job = 1

    def objExists(self, name):
        return name in self.objects or name.split(".")[0] in self.objects

    def ls(self, *args, **kw):
        if kw.get("selection"):
            return list(self.selection)
        names = args[0] if args and isinstance(args[0], (list, tuple)) else args
        return [n for n in names if n in self.objects]

    def select(self, objs, **kw):
        self.selection = list(objs)

    def createNode(self, node_type, name):
        self.objects.add(name)
        return name

    def attributeQuery(self, attr, node, exists):
        return "%s.%s" % (node, attr) in self.attrs

    def addAttr(self, node, longName, dataType):
        self.attrs.setdefault("%s.%s" % (node, longName), "")

    def setAttr(self, plug, value, type=None):
        self.attrs[plug] = value

    def getAttr(self, plug):
        return self.attrs.get(plug)

    def scriptJob(self, **kw):
        if "kill" in kw:
            self.jobs.discard(kw["kill"])
            return None
        job = self._next_job
        self._next_job += 1
        self.jobs.add(job)
        return job

    def warning(self, msg):
        pass


_LOADED = None


def _load_tool():
    global _LOADED
    if _LOADED is None:
        _LOADED = _import_tool()
    return _LOADED


def _import_tool():
    cmds = FakeCmds()
    maya = types.ModuleType("maya")
    mel = types.ModuleType("maya.mel")
    mel.eval = lambda *a, **k: ""
    omui = types.ModuleType("maya.OpenMayaUI")
    omui.MQtUtil = types.SimpleNamespace(mainWindow=lambda: None)
    maya.cmds, maya.mel, maya.OpenMayaUI = cmds, mel, omui
    fakes = {"maya": maya, "maya.cmds": cmds, "maya.mel": mel, "maya.OpenMayaUI": omui}
    saved = {name: sys.modules.get(name) for name in fakes}
    sys.modules.update(fakes)
    try:
        spec = importlib.util.spec_from_file_location("SmartSelectSets_v2_under_test", TOOL)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module      # dataclasses look the module up
        spec.loader.exec_module(module)
    finally:
        for name, mod in saved.items():
            if mod is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = mod
    return module, cmds


def _pump(times=3):
    for _ in range(times):
        QtWidgets.QApplication.processEvents()
        QtCore.QCoreApplication.sendPostedEvents(None, 0)


@unittest.skipIf(QtWidgets is None, "PySide6 is not installed")
class SmartSelectSetsTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        cls.sss, cls.cmds = _load_tool()

    def setUp(self):
        self.cmds.objects = {"a", "b", "c", "d"}
        self.cmds.attrs = {}

    def names(self, manager, category):
        return [g.name for g in manager.groups_in_category(category)]


class ManagerOrderTests(SmartSelectSetsTestCase):
    def make(self):
        m = self.sss.SmartSelectSetsManager()
        ids = {n: m.create_group(n, "Body", ["a"]) for n in ("one", "two", "three")}
        return m, ids

    def test_new_sets_are_appended_in_creation_order(self):
        m, _ = self.make()
        self.assertEqual(self.names(m, "Body"), ["one", "two", "three"])

    def test_drop_after_moves_button_to_the_right_of_target(self):
        m, ids = self.make()
        m.reorder_group(ids["one"], ids["two"], after=True)
        self.assertEqual(self.names(m, "Body"), ["two", "one", "three"])
        m.reorder_group(ids["three"], ids["two"], after=False)
        self.assertEqual(self.names(m, "Body"), ["three", "two", "one"])

    def test_drop_on_button_in_other_category_moves_and_positions(self):
        m, ids = self.make()
        x = m.create_group("x", "Face", ["b"])
        y = m.create_group("y", "Face", ["b"])
        m.reorder_group(ids["two"], y, after=False)
        self.assertEqual(self.names(m, "Face"), ["x", "two", "y"])
        self.assertEqual(self.names(m, "Body"), ["one", "three"])
        self.assertEqual([g.order for g in m.groups_in_category("Body")], [0, 1])
        m.move_group(x, "Body")
        self.assertEqual(self.names(m, "Body"), ["one", "three", "x"])

    def test_order_survives_save_and_old_data_stays_alphabetical(self):
        m, ids = self.make()
        m.reorder_group(ids["three"], ids["one"], after=False)
        payload = m.to_payload()
        again = self.sss.SmartSelectSetsManager()
        again.load_payload(payload)
        self.assertEqual(self.names(again, "Body"), ["three", "one", "two"])

        for data in payload["groups"].values():
            del data["order"]          # data saved by 2.5.x
        legacy = self.sss.SmartSelectSetsManager()
        legacy.load_payload(payload)
        self.assertEqual(self.names(legacy, "Body"), ["one", "three", "two"])

    def test_duplicate_lands_next_to_original(self):
        m, ids = self.make()
        m.duplicate_group(ids["one"])
        self.assertEqual(self.names(m, "Body"), ["one", "one_copy", "two", "three"])


class WindowTests(SmartSelectSetsTestCase):
    def setUp(self):
        super().setUp()
        self.win = self.sss.SmartSelectSetsWindow()
        self.win.show()
        # Message boxes would block offscreen
        self.win._show_info = lambda *a: None
        self.win._show_error = lambda msg: self.fail("unexpected error: %s" % msg)

    def tearDown(self):
        if shiboken6.isValid(self.win):
            self.win.shutdown_window()
        _pump()

    def box_titles(self):
        return [w["group_box"].title() for w in self.win.category_widgets.values()]

    def test_category_name_can_be_reused_after_it_returns_hidden(self):
        win = self.win
        with unittest.mock.patch.object(QtWidgets.QInputDialog, "getText", return_value=("Arms", True)):
            win.create_category_dialog()
        self.assertIn("Arms", self.box_titles())
        win.manager.save_to_scene_node()
        with unittest.mock.patch.object(QtWidgets.QMessageBox, "question",
                                        return_value=QtWidgets.QMessageBox.Yes):
            win.delete_specific_category_dialog("Arms")
        self.assertNotIn("Arms", self.box_titles())
        # Load (or a scene reopen) brings the empty category back without a box
        win.load_from_scene(show_feedback=False)
        self.assertIn("Arms", win.manager.categories)
        self.assertNotIn("Arms", self.box_titles())
        with unittest.mock.patch.object(QtWidgets.QInputDialog, "getText", return_value=("Arms", True)):
            win.create_category_dialog()
        self.assertIn("Arms", self.box_titles())

    def test_rename_category_button_works(self):
        win = self.win
        win.manager.create_group("hand", "Arms", ["a"])
        win.refresh_ui()
        with unittest.mock.patch.object(QtWidgets.QInputDialog, "getText", return_value=("Hands", True)):
            win.rename_category_dialog("Arms")
        self.assertEqual(win.manager.groups_in_category("Hands")[0].name, "hand")
        self.assertIn("Hands", self.box_titles())

    def test_drop_handler_reorders_buttons_in_window_and_popout(self):
        win = self.win
        first = win.manager.create_group("button1", "Body", ["a"])
        second = win.manager.create_group("button2", "Body", ["b"])
        win.refresh_ui()
        win.open_category_popout("Body")
        win.group_buttons[second].groupDroppedOnGroup.emit(first, second, True)
        _pump()
        self.assertEqual(self.names(win.manager, "Body"), ["button2", "button1"])
        popup = win.popout_windows["Body"]
        self.assertEqual([b.text() for b in popup.group_buttons.values()], ["button2", "button1"])

    def _drop_on(self, widget, group_id, x):
        mime = QtCore.QMimeData()
        mime.setData(self.sss.GROUP_MIME, str(group_id).encode("utf-8"))
        pos = QtCore.QPointF(x, widget.height() / 2.0)
        args = (QtCore.Qt.MoveAction, mime, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier)
        enter = QtGui.QDragEnterEvent(pos.toPoint(), *args)
        QtWidgets.QApplication.sendEvent(widget, enter)
        drop = QtGui.QDropEvent(pos, *args)
        QtWidgets.QApplication.sendEvent(widget, drop)
        _pump()
        return enter.isAccepted()

    def test_dropping_on_right_half_of_a_button_places_after_it(self):
        win = self.win
        ids = [win.manager.create_group(n, "Body", ["a"]) for n in ("b1", "b2", "b3")]
        win.refresh_ui()
        target = win.group_buttons[ids[1]]
        target.resize(100, 40)
        self.assertTrue(self._drop_on(target, ids[0], 90))
        self.assertEqual(self.names(win.manager, "Body"), ["b2", "b1", "b3"])
        target = win.group_buttons[ids[1]]
        target.resize(100, 40)
        self.assertTrue(self._drop_on(target, ids[2], 10))
        self.assertEqual(self.names(win.manager, "Body"), ["b3", "b2", "b1"])
        # Letting go over the dragged button itself changes nothing
        self._drop_on(win.group_buttons[ids[1]], ids[1], 10)
        self.assertEqual(self.names(win.manager, "Body"), ["b3", "b2", "b1"])

    def test_dropping_on_another_category_box_still_moves_the_set(self):
        win = self.win
        moved = win.manager.create_group("hand", "Arms", ["a"])
        win.manager.create_group("head", "Face", ["b"])
        win.refresh_ui()
        box = win.category_widgets["Face"]["group_box"]
        self._drop_on(box, moved, 5)
        self.assertEqual(self.names(win.manager, "Face"), ["head", "hand"])

    def test_popout_is_not_a_global_stay_on_top_window(self):
        self.win.manager.create_group("x", "Body", ["a"])
        self.win.refresh_ui()
        self.win.open_category_popout("Body")
        flags = self.win.popout_windows["Body"].windowFlags()
        self.assertFalse(flags & QtCore.Qt.WindowStaysOnTopHint)
        self.assertTrue(flags & QtCore.Qt.Tool)

    def test_closing_main_window_keeps_popouts_working(self):
        win = self.win
        group = win.manager.create_group("x", "Body", ["a"])
        win.refresh_ui()
        win.open_category_popout("Body")
        popup = win.popout_windows["Body"]
        jobs = set(self.cmds.jobs)

        win.close()
        _pump()
        self.assertTrue(shiboken6.isValid(win))
        self.assertTrue(win.isHidden())
        self.assertTrue(popup.isVisible())
        self.assertTrue(jobs <= self.cmds.jobs)       # scene callbacks still live
        popup.group_buttons[group].clickedWithId.emit(group)
        self.assertEqual(self.cmds.selection, ["a"])

        # Opening the tool again brings back the same window
        self.sss._window = None
        shown = self.sss.show_smart_select_sets()
        self.assertIs(shown, win)
        self.assertTrue(win.isVisible())

        # Closing the main window, then the last pop-out, closes everything
        win.close()
        _pump()
        popup.close()
        _pump(6)
        self.assertFalse(shiboken6.isValid(popup) and popup.isVisible())
        self.assertFalse(shiboken6.isValid(win))
        self.assertFalse(jobs & self.cmds.jobs)

    def test_close_really_closes_window_and_popout(self):
        win = self.win
        win.manager.create_group("x", "Body", ["a"])
        win.refresh_ui()
        win.open_category_popout("Body")
        popup = win.popout_windows["Body"]
        popup.close()
        _pump(6)
        self.assertFalse(shiboken6.isValid(popup) and popup.isVisible())
        self.assertNotIn("Body", win.popout_windows)
        jobs = set(self.cmds.jobs)
        win.close()
        _pump(6)
        self.assertFalse(shiboken6.isValid(win) and win.isVisible())
        self.assertFalse(jobs & self.cmds.jobs)

    def test_escape_closes_window(self):
        win = self.win
        win.reject()
        _pump(6)
        self.assertFalse(shiboken6.isValid(win) and win.isVisible())

    def test_shutdown_closes_hidden_window_and_popouts(self):
        win = self.win
        win.manager.create_group("x", "Body", ["a"])
        win.refresh_ui()
        win.open_category_popout("Body")
        win.close()
        _pump()
        self.sss.shutdown()
        _pump(6)
        self.assertFalse(shiboken6.isValid(win))


if __name__ == "__main__":
    unittest.main()
