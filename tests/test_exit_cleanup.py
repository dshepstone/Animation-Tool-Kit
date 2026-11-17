"""Maya-exit clean-up: nothing Python-owned may outlive Qt (no Maya needed).

Maya 2027 crashed on close in shiboken6.abi3.dll's exit clean-up. Timeline
Ticks (started with every toolbar) left an overlay and an event filter on
Maya's Time Slider, torn down with deleteLater(), which never runs once Maya
is quitting. These tests check that the teardown is immediate and that the
toolbar's quit job shuts every loaded tool down.
"""
import ast
import importlib.util
from pathlib import Path
import sys
import types
import unittest

ROOT = Path(__file__).resolve().parents[1]
TICKS = ROOT / "animation tool kit scripts" / "Timeline_Ticks_1_0_0" / "timeline_ticks.py"
TOOLBAR = ROOT / "atk_toolbar" / "atk_toolbar.py"
LOADER = ROOT / "atk_toolbar" / "atk_loader.py"

try:
    from PySide6 import QtCore, QtWidgets
    import shiboken6 as shiboken
except ImportError:  # pragma: no cover
    QtWidgets = None


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@unittest.skipIf(QtWidgets is None, "PySide6 is required")
class TimelineTicksTeardownTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def _fake_window(self, ticks):
        timeline = QtWidgets.QWidget()
        overlay = QtWidgets.QWidget(timeline)
        timeline.installEventFilter(overlay)
        window = QtWidgets.QWidget()
        window.overlay = overlay
        window.timer = QtCore.QTimer(window)
        window.timer.start(400)
        ticks._window = window
        return timeline, overlay, window

    def test_shutdown_destroys_overlay_and_window_immediately(self):
        ticks = _load(TICKS, "atk_test_ticks_shutdown")
        timeline, overlay, window = self._fake_window(ticks)
        ticks.shutdown()
        # No event loop runs here, just like a quitting Maya: the objects
        # must already be gone, not merely scheduled with deleteLater().
        self.assertFalse(shiboken.isValid(overlay))
        self.assertFalse(shiboken.isValid(window))
        self.assertIsNone(ticks._window)
        self.assertTrue(shiboken.isValid(timeline))  # Maya's widget survives
        timeline.deleteLater()

    def test_shutdown_stops_the_key_tracker(self):
        ticks = _load(TICKS, "atk_test_ticks_tracker")
        stopped = []
        ticks._tracker = types.SimpleNamespace(stop=lambda: stopped.append(True))
        ticks.shutdown()
        self.assertEqual(stopped, [True])
        self.assertIsNone(ticks._tracker)

    def test_closing_the_bar_normally_still_uses_deletelater(self):
        ticks = _load(TICKS, "atk_test_ticks_close")
        timeline, overlay, window = self._fake_window(ticks)
        ticks._close_window()
        self.assertTrue(shiboken.isValid(window))  # deferred, not destroyed
        self.assertFalse(window.timer.isActive())
        timeline.deleteLater()


class LoaderShutdownTests(unittest.TestCase):
    def test_shutdown_tool_modules_calls_every_loaded_tool(self):
        cmds = types.SimpleNamespace(warning=lambda *a, **k: None)
        maya = types.ModuleType("maya")
        maya.cmds = cmds
        saved = {n: sys.modules.get(n) for n in ("maya", "maya.cmds")}
        sys.modules.update({"maya": maya, "maya.cmds": cmds})
        called = []
        fakes = {}
        for name in ("timeline_ticks", "time_bookmarks.main", "anim_snap"):
            module = types.ModuleType(name)
            if name != "anim_snap":
                module.shutdown = lambda n=name: called.append(n)
            fakes[name] = module
        try:
            spec = importlib.util.spec_from_file_location("atk_test_loader", LOADER)
            loader = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(loader)
            for name, module in fakes.items():
                sys.modules[name] = module
            done = loader.shutdown_tool_modules()
        finally:
            for name in fakes:
                sys.modules.pop(name, None)
            for name, module in saved.items():
                if module is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = module
        self.assertEqual(sorted(called), ["time_bookmarks.main", "timeline_ticks"])
        self.assertEqual(sorted(done), ["time_bookmarks.main", "timeline_ticks"])


class QuitJobWiringTests(unittest.TestCase):
    """Static: the quitApplication clean-up must shut the tools down."""

    def _function(self, path, name):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == name:
                return node
        self.fail("%s() not found in %s" % (name, path.name))

    def _calls(self, function):
        names = set()
        for node in ast.walk(function):
            if isinstance(node, ast.Call):
                func = node.func
                names.add(func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", ""))
        return names

    def test_quit_cleanup_shuts_tools_down_and_deletes_windows(self):
        calls = self._calls(self._function(TOOLBAR, "_shutdown_cleanup"))
        self.assertIn("shutdown_tool_modules", calls)
        self.assertIn("_delete_tool_windows", calls)

    def test_reload_uses_the_same_shutdown(self):
        calls = self._calls(self._function(LOADER, "reload_tool_modules"))
        self.assertIn("shutdown_tool_modules", calls)


if __name__ == "__main__":
    unittest.main()
