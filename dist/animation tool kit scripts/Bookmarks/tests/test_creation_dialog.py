"""Qt widget tests for BookmarkCreationDialog."""

import pytest

from time_bookmarks.ui.bookmark_creation_dialog import (
    BookmarkCreationDialog,
    BookmarkCreationRequest,
)
from time_bookmarks.ui.color_picker import DEFAULT_PALETTE
from time_bookmarks.qt_compat import QtCore, QtWidgets


@pytest.fixture()
def dialog(qtbot):
    d = BookmarkCreationDialog(start_frame=10, end_frame=80)
    qtbot.addWidget(d)
    return d


class TestBookmarkCreationDialog:
    def test_dialog_creates_without_error(self, dialog):
        assert dialog is not None

    def test_default_start_frame(self, dialog):
        assert dialog._start_spin.value() == 10

    def test_default_end_frame(self, dialog):
        assert dialog._end_spin.value() == 80

    def test_initial_color_matches_first_palette(self, dialog):
        assert dialog._color_model.selected_color == DEFAULT_PALETTE[0]

    def test_initial_color_parameter_honoured(self, qtbot):
        target = DEFAULT_PALETTE[4]
        d = BookmarkCreationDialog(color_hex=target)
        qtbot.addWidget(d)
        assert d._color_model.selected_color == target

    def test_unknown_initial_color_falls_back_to_default(self, qtbot):
        d = BookmarkCreationDialog(color_hex="#BADBAD")
        qtbot.addWidget(d)
        assert d._color_model.selected_color == DEFAULT_PALETTE[0]

    def test_prefill_sets_name(self, dialog):
        dialog.prefill(name="Hero Walk")
        assert dialog._name_edit.text() == "Hero Walk"

    def test_prefill_sets_notes(self, dialog):
        dialog.prefill(notes="important scene")
        assert dialog._notes_edit.text() == "important scene"

    def test_get_request_returns_none_before_accept(self, dialog):
        assert dialog.get_request() is None

    def test_accept_builds_request(self, dialog, qtbot):
        dialog._name_edit.setText("Sprint")
        dialog._start_spin.setValue(20)
        dialog._end_spin.setValue(60)
        # Trigger accept via the internal helper directly (avoids modal exec).
        dialog._on_accept()
        req = dialog.get_request()
        assert isinstance(req, BookmarkCreationRequest)
        assert req.name == "Sprint"
        assert req.start_frame == 20
        assert req.end_frame == 60
        assert req.color_hex == dialog._color_model.selected_color

    def test_accept_strips_whitespace_from_name(self, dialog, qtbot):
        dialog._name_edit.setText("  Hero  ")
        dialog._on_accept()
        assert dialog.get_request().name == "Hero"

    def test_empty_name_is_allowed(self, dialog, qtbot):
        dialog._name_edit.setText("")
        dialog._on_accept()
        assert dialog.get_request().name == ""

    def test_invalid_range_shows_warning_not_request(self, dialog, qtbot, monkeypatch):
        dialog._start_spin.setValue(100)
        dialog._end_spin.setValue(50)
        # Patch QMessageBox.warning so it doesn't block.
        monkeypatch.setattr(QtWidgets.QMessageBox, "warning", lambda *a, **kw: None)
        dialog._on_accept()
        assert dialog.get_request() is None

    def test_color_change_updates_name_background(self, dialog, qtbot):
        target = DEFAULT_PALETTE[6]
        # set_selected_color emits color_selected, which triggers the dialog's
        # stylesheet update via _on_color_changed.
        dialog._color_widget.set_selected_color(target)
        style = dialog._name_edit.styleSheet()
        assert target in style

    def test_color_picker_embedded(self, dialog):
        # Import ColorPickerWidget after QApplication exists so the class
        # is the same object as the one embedded in the dialog.
        from time_bookmarks.ui.color_picker import ColorPickerWidget
        assert type(dialog._color_widget).__name__ == "ColorPickerWidget"
        assert isinstance(dialog._color_widget, ColorPickerWidget)


class TestSingleFrameOption:
    def test_checkbox_disabled_without_current_frame(self, qtbot):
        d = BookmarkCreationDialog(start_frame=1, end_frame=10, current_frame=None)
        qtbot.addWidget(d)
        assert d._single_frame_check.isEnabled() is False

    def test_checkbox_enables_with_current_frame(self, qtbot):
        d = BookmarkCreationDialog(start_frame=1, end_frame=10, current_frame=42)
        qtbot.addWidget(d)
        assert d._single_frame_check.isEnabled() is True
        assert d._single_frame_check.isChecked() is False

    def test_toggle_on_locks_frames_to_current(self, qtbot):
        d = BookmarkCreationDialog(start_frame=1, end_frame=10, current_frame=42)
        qtbot.addWidget(d)
        d._single_frame_check.setChecked(True)
        assert d._start_spin.value() == 42
        assert d._end_spin.value() == 42
        assert d._start_spin.isEnabled() is False
        assert d._end_spin.isEnabled() is False

    def test_toggle_off_re_enables_spinboxes(self, qtbot):
        d = BookmarkCreationDialog(start_frame=1, end_frame=10, current_frame=42)
        qtbot.addWidget(d)
        d._single_frame_check.setChecked(True)
        d._single_frame_check.setChecked(False)
        assert d._start_spin.isEnabled() is True
        assert d._end_spin.isEnabled() is True

    def test_auto_checked_when_range_matches_current_frame(self, qtbot):
        d = BookmarkCreationDialog(
            start_frame=42, end_frame=42, current_frame=42
        )
        qtbot.addWidget(d)
        assert d._single_frame_check.isChecked() is True

    def test_accept_produces_single_frame_request(self, qtbot):
        d = BookmarkCreationDialog(start_frame=1, end_frame=10, current_frame=42)
        qtbot.addWidget(d)
        d._single_frame_check.setChecked(True)
        d._on_accept()
        req = d.get_request()
        assert req.start_frame == req.end_frame == 42


class TestBookmarkCreationRequest:
    def test_dataclass_fields(self):
        req = BookmarkCreationRequest(
            name="Run", start_frame=1, end_frame=50, color_hex="#4CAF50"
        )
        assert req.name == "Run"
        assert req.notes == ""  # default

    def test_notes_field(self):
        req = BookmarkCreationRequest(
            name="X", start_frame=0, end_frame=0,
            color_hex="#000", notes="hero moment"
        )
        assert req.notes == "hero moment"
