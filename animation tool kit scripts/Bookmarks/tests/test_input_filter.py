"""Qt tests for TimelineEventFilter — modifier + mouse button decoding."""

import pytest

from time_bookmarks.maya.input_filter import TimelineEventFilter
from time_bookmarks.qt_compat import QtCore, QtGui


# ---------------------------------------------------------------------------
# Helper — build a synthetic QMouseEvent
# ---------------------------------------------------------------------------

def _make_press(button, modifiers) -> QtGui.QMouseEvent:
    """Create a MouseButtonPress event with the given button and modifiers.

    Handles the PySide2 / PySide6 constructor difference transparently.
    """
    try:
        event_type = QtCore.QEvent.Type.MouseButtonPress
        pos = QtCore.QPointF(10.0, 10.0)
    except AttributeError:
        event_type = QtCore.QEvent.MouseButtonPress  # type: ignore[attr-defined]
        pos = QtCore.QPoint(10, 10)  # type: ignore[assignment]

    return QtGui.QMouseEvent(event_type, pos, button, button, modifiers)


def _btn():
    try:
        return QtCore.Qt.MouseButton.LeftButton
    except AttributeError:
        return QtCore.Qt.LeftButton  # type: ignore[attr-defined]


def _mod(**flags) -> object:
    """Build a modifier flags value from keyword args (ctrl, alt, shift)."""
    try:
        No   = QtCore.Qt.KeyboardModifier.NoModifier
        Ctrl  = QtCore.Qt.KeyboardModifier.ControlModifier
        Alt   = QtCore.Qt.KeyboardModifier.AltModifier
        Shift = QtCore.Qt.KeyboardModifier.ShiftModifier
    except AttributeError:
        No    = QtCore.Qt.NoModifier    # type: ignore[attr-defined]
        Ctrl  = QtCore.Qt.ControlModifier  # type: ignore[attr-defined]
        Alt   = QtCore.Qt.AltModifier      # type: ignore[attr-defined]
        Shift = QtCore.Qt.ShiftModifier    # type: ignore[attr-defined]

    result = No
    if flags.get("ctrl"):
        result = result | Ctrl
    if flags.get("alt"):
        result = result | Alt
    if flags.get("shift"):
        result = result | Shift
    return result


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def ef() -> TimelineEventFilter:
    # TimelineEventFilter is a QObject, not a QWidget — just return it directly.
    return TimelineEventFilter()


# ---------------------------------------------------------------------------
# Signal emission tests
# ---------------------------------------------------------------------------

class TestTimelineEventFilterSignals:
    def _collect(self, signal):
        received = []
        signal.connect(lambda: received.append(True))
        return received

    # ---- Ctrl + Alt + Shift + Click → remove ----------------------------

    def test_ctrl_alt_shift_emits_remove(self, ef):
        received = self._collect(ef.remove_requested)
        event = _make_press(_btn(), _mod(ctrl=True, alt=True, shift=True))
        ef.eventFilter(None, event)
        assert received == [True]

    def test_ctrl_alt_shift_does_not_emit_create(self, ef):
        received = self._collect(ef.create_requested)
        event = _make_press(_btn(), _mod(ctrl=True, alt=True, shift=True))
        ef.eventFilter(None, event)
        assert received == []

    # ---- Ctrl + Alt + Click → create ------------------------------------

    def test_ctrl_alt_emits_create(self, ef):
        received = self._collect(ef.create_requested)
        event = _make_press(_btn(), _mod(ctrl=True, alt=True))
        ef.eventFilter(None, event)
        assert received == [True]

    def test_ctrl_alt_does_not_emit_navigate(self, ef):
        received = self._collect(ef.navigate_next_requested)
        event = _make_press(_btn(), _mod(ctrl=True, alt=True))
        ef.eventFilter(None, event)
        assert received == []

    # ---- Ctrl + Shift + Click → jump ------------------------------------

    def test_ctrl_shift_emits_jump(self, ef):
        received = self._collect(ef.jump_requested)
        event = _make_press(_btn(), _mod(ctrl=True, shift=True))
        ef.eventFilter(None, event)
        assert received == [True]

    # ---- Alt + Shift + Click → panel ------------------------------------

    def test_alt_shift_emits_panel(self, ef):
        received = self._collect(ef.panel_requested)
        event = _make_press(_btn(), _mod(alt=True, shift=True))
        ef.eventFilter(None, event)
        assert received == [True]

    # ---- Ctrl + Click → next -------------------------------------------

    def test_ctrl_emits_next(self, ef):
        received = self._collect(ef.navigate_next_requested)
        event = _make_press(_btn(), _mod(ctrl=True))
        ef.eventFilter(None, event)
        assert received == [True]

    # ---- Shift + Click → prev ------------------------------------------

    def test_shift_emits_prev(self, ef):
        received = self._collect(ef.navigate_prev_requested)
        event = _make_press(_btn(), _mod(shift=True))
        ef.eventFilter(None, event)
        assert received == [True]

    # ---- Alt + Click → visibility --------------------------------------

    def test_alt_emits_visibility(self, ef):
        received = self._collect(ef.visibility_requested)
        event = _make_press(_btn(), _mod(alt=True))
        ef.eventFilter(None, event)
        assert received == [True]

    # ---- No modifier → nothing -----------------------------------------

    def test_bare_click_emits_nothing(self, ef):
        all_received = []
        for sig in [
            ef.create_requested, ef.navigate_next_requested,
            ef.navigate_prev_requested, ef.jump_requested,
            ef.remove_requested, ef.panel_requested, ef.visibility_requested,
        ]:
            sig.connect(lambda: all_received.append(True))

        event = _make_press(_btn(), _mod())
        ef.eventFilter(None, event)
        assert all_received == []


# ---------------------------------------------------------------------------
# Return value — never consume the event
# ---------------------------------------------------------------------------

class TestTimelineEventFilterReturnValue:
    def test_always_returns_false_for_handled_shortcut(self, ef):
        event = _make_press(_btn(), _mod(ctrl=True, alt=True))
        result = ef.eventFilter(None, event)
        assert result is False

    def test_always_returns_false_for_bare_click(self, ef):
        event = _make_press(_btn(), _mod())
        result = ef.eventFilter(None, event)
        assert result is False

    def test_returns_false_for_non_mouse_event(self, ef):
        try:
            non_mouse = QtCore.QEvent(QtCore.QEvent.Type.KeyPress)
        except AttributeError:
            non_mouse = QtCore.QEvent(QtCore.QEvent.KeyPress)  # type: ignore[attr-defined]
        result = ef.eventFilter(None, non_mouse)
        assert result is False


# ---------------------------------------------------------------------------
# Right-button click — no signals
# ---------------------------------------------------------------------------

class TestTimelineEventFilterRightButton:
    def test_right_button_emits_nothing(self, ef):
        try:
            right = QtCore.Qt.MouseButton.RightButton
        except AttributeError:
            right = QtCore.Qt.RightButton  # type: ignore[attr-defined]

        received = []
        ef.create_requested.connect(lambda: received.append(True))
        ef.navigate_next_requested.connect(lambda: received.append(True))

        event = _make_press(right, _mod(ctrl=True, alt=True))
        ef.eventFilter(None, event)
        assert received == []
