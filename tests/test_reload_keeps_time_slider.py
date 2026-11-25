"""Reload Scripts must close tool windows without touching Maya's own UI.

Timeline Ticks and Bookmarks draw overlays on Maya's Time Slider widget
(``timeControl1``). Reload Scripts closed every visible tool widget by
deleting the first ancestor that ``workspaceControl -exists`` accepted, and
that flag answers True for any UI object - so the overlay's parent,
``timeControl1``, was deleted and Maya was left with an empty Time Slider.
"""
import unittest

try:
    from PySide6 import QtWidgets
    import shiboken6 as shiboken
except ImportError:  # pragma: no cover
    QtWidgets = None

if QtWidgets is not None:
    from test_toolbar_layout_qt import _FakeMayaCase
else:  # pragma: no cover
    _FakeMayaCase = unittest.TestCase


def _tool_class(module, name="ToolWidget"):
    """A QWidget subclass that looks as if it was defined in ``module``."""
    return type(name, (QtWidgets.QWidget,), {"__module__": module})


@unittest.skipIf(QtWidgets is None, "PySide6 not installed")
class ReloadKeepsMayaUiTests(_FakeMayaCase):
    def setUp(self):
        super(ReloadKeepsMayaUiTests, self).setUp()
        self.settings = self.tb.atk_settings
        self.ui_types = {}
        self.deleted = []
        cmds = self.cmds
        self._orig = {n: cmds.__dict__.get(n) for n in ("objectTypeUI", "deleteUI", "workspaceControl")}

        def objectTypeUI(name):
            if name not in self.ui_types:
                raise RuntimeError("Object '%s' not found." % name)
            return self.ui_types[name]

        def workspaceControl(*args, **kw):
            if kw.get("exists"):
                # Like Maya: True for ANY UI object of that name.
                return args[0] in self.ui_types
            return None

        cmds.objectTypeUI = objectTypeUI
        cmds.deleteUI = lambda name: self.deleted.append(name)
        cmds.workspaceControl = workspaceControl

    def tearDown(self):
        for name, fn in self._orig.items():
            if fn is None:
                self.cmds.__dict__.pop(name, None)
            else:
                setattr(self.cmds, name, fn)
        super(ReloadKeepsMayaUiTests, self).tearDown()

    def named(self, parent, name, ui_type, cls=QtWidgets.QWidget if QtWidgets else None):
        w = cls(parent)
        if name:
            w.setObjectName(name)
            self.ui_types[name] = ui_type
        return w

    def build_time_slider(self):
        """TimeSlider > MainTimeSliderLayout > formLayout2 > timeControl1."""
        dock = self.named(None, "TimeSlider", "workspaceControl")
        self.widgets.append(dock)
        layout = self.named(dock, "MainTimeSliderLayout", "formLayout")
        form = self.named(layout, "formLayout2", "formLayout")
        slider = self.named(form, "timeControl1", "timeControl")
        dock.show()
        return slider

    def test_time_slider_overlays_are_left_alone(self):
        slider = self.build_time_slider()
        ticks = _tool_class("timeline_ticks", "Overlay")(slider)
        marks = _tool_class("time_bookmarks", "TimelineOverlay")(slider)
        for w in (ticks, marks):
            w.show()
        self.assertTrue(ticks.isVisible())

        reopen = self.settings.close_tool_windows()

        self.assertEqual(self.deleted, [])
        self.assertNotIn("timeline_ticks", reopen)
        self.assertTrue(shiboken.isValid(slider))

    def test_overlay_on_a_maya_layout_inside_a_ui_element(self):
        slider = self.build_time_slider()
        layout = slider.parentWidget()
        _tool_class("timeline_ticks", "Overlay")(layout).show()
        self.settings.close_tool_windows()
        self.assertEqual(self.deleted, [])

    def test_docked_tool_window_is_still_closed_and_reopened(self):
        self.build_time_slider()
        dock = self.named(None, "wireShapeWorkspaceControl", "workspaceControl")
        self.widgets.append(dock)
        inner = self.named(dock, "wireShapeLayout", "columnLayout")
        _tool_class("wire_shape_tool")(inner)
        dock.show()

        reopen = self.settings.close_tool_windows()

        self.assertEqual(self.deleted, ["wireShapeWorkspaceControl"])
        self.assertIn("wire_shape", reopen)


if __name__ == "__main__":
    unittest.main()
