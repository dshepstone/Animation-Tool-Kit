"""Qt widget tests for ColorPickerWidget."""

import pytest

from time_bookmarks.ui.color_picker import (
    DEFAULT_PALETTE,
    ColorPickerModel,
)


@pytest.fixture()
def model() -> ColorPickerModel:
    return ColorPickerModel()


@pytest.fixture()
def widget(qtbot):
    from time_bookmarks.ui.color_picker import ColorPickerWidget
    m = ColorPickerModel()
    w = ColorPickerWidget(model=m)
    qtbot.addWidget(w)
    return w


class TestColorPickerModel:
    def test_default_selected_is_first_palette_color(self, model):
        assert model.selected_color == DEFAULT_PALETTE[0]

    def test_set_valid_color_updates_selection(self, model):
        target = DEFAULT_PALETTE[3]
        model.set_selected_color(target)
        assert model.selected_color == target

    def test_set_invalid_color_raises(self, model):
        with pytest.raises(ValueError):
            model.set_selected_color("#BADBAD")

    def test_palette_has_expected_length(self, model):
        assert len(model.palette) == len(DEFAULT_PALETTE)


class TestColorPickerWidget:
    def test_widget_creates_one_button_per_palette_color(self, widget):
        assert len(widget._buttons) == len(DEFAULT_PALETTE)

    def test_initial_selected_color_matches_model(self, widget):
        assert widget.selected_color == DEFAULT_PALETTE[0]

    def test_clicking_swatch_updates_selected_color(self, qtbot, widget):
        target = DEFAULT_PALETTE[5]
        btn = widget._buttons[target]
        received = []
        widget.color_selected.connect(received.append)
        qtbot.mouseClick(btn, __import__("time_bookmarks.qt_compat", fromlist=["QtCore"]).QtCore.Qt.LeftButton)
        assert widget.selected_color == target
        assert received == [target]

    def test_set_selected_color_programmatically(self, widget):
        target = DEFAULT_PALETTE[7]
        widget.set_selected_color(target)
        assert widget.selected_color == target

    def test_set_unknown_color_does_not_raise_or_change(self, widget):
        original = widget.selected_color
        widget.set_selected_color("#BADBAD")
        assert widget.selected_color == original

    def test_selected_button_has_white_border(self, widget):
        target = DEFAULT_PALETTE[2]
        widget.set_selected_color(target)
        style = widget._buttons[target].styleSheet()
        assert "#FFFFFF" in style or "white" in style.lower()

    def test_non_selected_buttons_have_no_white_border(self, widget):
        widget.set_selected_color(DEFAULT_PALETTE[0])
        for color, btn in widget._buttons.items():
            if color != DEFAULT_PALETTE[0]:
                assert "#FFFFFF" not in btn.styleSheet()
