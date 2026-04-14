"""Qt widget tests for BookmarkListModel, BookmarkDelegate, BookmarkListWidget."""

import pytest

from time_bookmarks.data.models import Bookmark
from time_bookmarks.ui.bookmark_list_widget import (
    BookmarkDelegate,
    BookmarkListModel,
    BookmarkListWidget,
)
from time_bookmarks.qt_compat import QtCore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_bookmark(**kwargs) -> Bookmark:
    defaults = dict(
        name="Walk Cycle",
        start_frame=1,
        end_frame=50,
        color_hex="#4CAF50",
    )
    defaults.update(kwargs)
    return Bookmark(**defaults)


# ---------------------------------------------------------------------------
# BookmarkListModel
# ---------------------------------------------------------------------------

class TestBookmarkListModel:
    @pytest.fixture()
    def model(self):
        return BookmarkListModel()

    def test_empty_initially(self, model):
        assert model.rowCount() == 0

    def test_row_count_after_refresh(self, model):
        bookmarks = [make_bookmark(name=f"B{i}", start_frame=i * 10,
                                   end_frame=i * 10 + 5) for i in range(3)]
        model.refresh(bookmarks)
        assert model.rowCount() == 3

    def test_display_role_returns_name(self, model):
        b = make_bookmark(name="Hero Walk")
        model.refresh([b])
        index = model.index(0)
        assert model.data(index, QtCore.Qt.DisplayRole) == "Hero Walk"

    def test_color_hex_role(self, model):
        b = make_bookmark(color_hex="#E57373")
        model.refresh([b])
        index = model.index(0)
        assert model.data(index, BookmarkListModel.ColorHexRole) == "#E57373"

    def test_start_frame_role(self, model):
        b = make_bookmark(start_frame=42)
        model.refresh([b])
        index = model.index(0)
        assert model.data(index, BookmarkListModel.StartFrameRole) == 42

    def test_end_frame_role(self, model):
        b = make_bookmark(end_frame=99)
        model.refresh([b])
        index = model.index(0)
        assert model.data(index, BookmarkListModel.EndFrameRole) == 99

    def test_bookmark_id_role(self, model):
        b = make_bookmark()
        model.refresh([b])
        index = model.index(0)
        assert model.data(index, BookmarkListModel.BookmarkIdRole) == b.id

    def test_invalid_index_returns_none(self, model):
        assert model.data(model.index(99)) is None

    def test_refresh_resets_model(self, model):
        model.refresh([make_bookmark(name="Old")])
        model.refresh([make_bookmark(name="A"), make_bookmark(name="B",
                        start_frame=10, end_frame=20)])
        assert model.rowCount() == 2

    def test_unnamed_bookmark_shows_frame_range(self, model):
        b = Bookmark(name="", start_frame=10, end_frame=20, color_hex="#000")
        model.refresh([b])
        label = model.data(model.index(0), QtCore.Qt.DisplayRole)
        assert "10" in label and "20" in label


# ---------------------------------------------------------------------------
# BookmarkDelegate
# ---------------------------------------------------------------------------

class TestBookmarkDelegate:
    @pytest.fixture()
    def delegate(self):
        return BookmarkDelegate()

    def test_size_hint_height(self, qtbot, delegate):
        from time_bookmarks.qt_compat import QtWidgets, QtCore
        widget = QtWidgets.QWidget()
        qtbot.addWidget(widget)
        opt = QtWidgets.QStyleOptionViewItem()
        opt.rect = QtCore.QRect(0, 0, 400, 100)
        hint = delegate.sizeHint(opt, QtCore.QModelIndex())
        assert hint.height() == BookmarkDelegate._ROW_HEIGHT

    def test_paint_does_not_raise(self, qtbot, delegate):
        from time_bookmarks.qt_compat import QtWidgets, QtGui, QtCore
        widget = QtWidgets.QWidget()
        widget.resize(400, 40)
        qtbot.addWidget(widget)

        model = BookmarkListModel()
        model.refresh([make_bookmark(name="Test", color_hex="#4CAF50")])

        pixmap = QtGui.QPixmap(400, 40)
        painter = QtGui.QPainter(pixmap)
        opt = QtWidgets.QStyleOptionViewItem()
        opt.rect = QtCore.QRect(0, 0, 400, 40)
        opt.state = QtWidgets.QStyle.State_Enabled  # type: ignore[attr-defined]
        opt.palette = widget.palette()

        # Always end the painter to avoid a destroyed-while-painting warning.
        try:
            delegate.paint(painter, opt, model.index(0))
        finally:
            painter.end()


# ---------------------------------------------------------------------------
# BookmarkListWidget
# ---------------------------------------------------------------------------

class TestBookmarkListWidget:
    @pytest.fixture()
    def list_widget(self, qtbot):
        w = BookmarkListWidget()
        qtbot.addWidget(w)
        return w

    def test_set_bookmarks_populates_view(self, list_widget):
        bookmarks = [make_bookmark(name="A"), make_bookmark(name="B",
                      start_frame=10, end_frame=20)]
        list_widget.set_bookmarks(bookmarks)
        assert list_widget._model.rowCount() == 2

    def test_selected_bookmark_id_none_when_empty(self, list_widget):
        list_widget.set_bookmarks([])
        assert list_widget.selected_bookmark_id() is None

    def test_selected_bookmark_id_after_programmatic_selection(self, list_widget, qtbot):
        b = make_bookmark(name="Target")
        list_widget.set_bookmarks([b])
        # Select the first row programmatically.
        index = list_widget._model.index(0)
        list_widget._list_view.setCurrentIndex(index)
        assert list_widget.selected_bookmark_id() == b.id

    def test_double_click_emits_id(self, list_widget, qtbot):
        b = make_bookmark(name="Click Me")
        list_widget.set_bookmarks([b])
        received = []
        list_widget.bookmark_double_clicked.connect(received.append)

        # Drive the internal handler directly rather than synthesising mouse
        # events, which can be unreliable against an offscreen viewport.
        index = list_widget._model.index(0)
        list_widget._on_double_click(index)
        assert received == [b.id]
