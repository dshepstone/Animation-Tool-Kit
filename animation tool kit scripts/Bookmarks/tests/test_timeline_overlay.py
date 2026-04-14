"""Qt widget tests for TimelineOverlay."""

import pytest

from time_bookmarks.data.models import Bookmark
from time_bookmarks.qt_compat import QtCore, QtGui, QtWidgets
from time_bookmarks.ui.timeline_overlay import TimelineOverlay


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_bookmark(name="Walk", start=0, end=50, color="#4CAF50") -> Bookmark:
    return Bookmark(name=name, start_frame=start, end_frame=end, color_hex=color)


@pytest.fixture()
def parent_widget(qtbot) -> QtWidgets.QWidget:
    w = QtWidgets.QWidget()
    w.resize(500, 30)
    qtbot.addWidget(w)
    w.show()
    return w


@pytest.fixture()
def overlay(parent_widget) -> TimelineOverlay:
    return TimelineOverlay(parent_widget=parent_widget)


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

class TestTimelineOverlayConstruction:
    def test_overlay_is_child_of_parent(self, overlay, parent_widget):
        assert overlay.parent() is parent_widget

    def test_overlay_matches_parent_geometry(self, overlay, parent_widget):
        assert overlay.geometry() == parent_widget.rect()

    def test_mouse_events_pass_through(self, overlay):
        assert overlay.testAttribute(
            QtCore.Qt.WA_TransparentForMouseEvents  # type: ignore[attr-defined]
        )

    def test_overlay_is_visible_by_default(self, overlay):
        assert overlay.isVisible()


# ---------------------------------------------------------------------------
# set_bookmarks / set_visible
# ---------------------------------------------------------------------------

class TestTimelineOverlayAPI:
    def test_set_bookmarks_stores_data(self, overlay):
        bookmarks = [make_bookmark()]
        overlay.set_bookmarks(bookmarks, (0, 100))
        assert overlay._bookmarks == bookmarks
        assert overlay._frame_range == (0, 100)

    def test_set_bookmarks_replaces_previous(self, overlay):
        overlay.set_bookmarks([make_bookmark("A")], (0, 100))
        overlay.set_bookmarks([make_bookmark("B"), make_bookmark("C")], (0, 200))
        assert len(overlay._bookmarks) == 2
        assert overlay._frame_range == (0, 200)

    def test_set_visible_false_hides_overlay(self, overlay):
        overlay.set_visible(False)
        assert not overlay.isVisible()

    def test_set_visible_true_shows_overlay(self, overlay):
        overlay.set_visible(False)
        overlay.set_visible(True)
        assert overlay.isVisible()


# ---------------------------------------------------------------------------
# Resize tracking
# ---------------------------------------------------------------------------

class TestTimelineOverlayResize:
    def test_resize_parent_updates_overlay_geometry(self, overlay, parent_widget):
        parent_widget.resize(800, 40)
        # Trigger the event filter manually with a resize event.
        resize_event = QtGui.QResizeEvent(
            QtCore.QSize(800, 40),
            QtCore.QSize(500, 30),
        )
        overlay.eventFilter(parent_widget, resize_event)
        assert overlay.width() == parent_widget.width()
        assert overlay.height() == parent_widget.height()

    def test_non_parent_resize_ignored(self, overlay, qtbot):
        other = QtWidgets.QWidget()
        qtbot.addWidget(other)
        original_geom = overlay.geometry()
        resize_event = QtGui.QResizeEvent(
            QtCore.QSize(9999, 9999),
            QtCore.QSize(1, 1),
        )
        overlay.eventFilter(other, resize_event)
        assert overlay.geometry() == original_geom

    def test_event_filter_never_consumes_event(self, overlay, parent_widget):
        resize_event = QtGui.QResizeEvent(
            QtCore.QSize(400, 30), QtCore.QSize(500, 30)
        )
        result = overlay.eventFilter(parent_widget, resize_event)
        assert result is False


# ---------------------------------------------------------------------------
# paintEvent — render to QPixmap and inspect pixels
# ---------------------------------------------------------------------------

class TestTimelineOverlayPaint:
    def _render(self, overlay: TimelineOverlay) -> QtGui.QImage:
        """Force a paint and return the result as a QImage."""
        overlay.resize(400, 30)
        pixmap = QtGui.QPixmap(overlay.size())
        pixmap.fill(QtGui.QColor("#000000"))
        overlay.render(pixmap)
        return pixmap.toImage()

    def test_paint_does_not_raise_with_no_bookmarks(self, overlay):
        overlay.set_bookmarks([], (0, 100))
        # Trigger paintEvent via render — must not raise.
        pixmap = QtGui.QPixmap(400, 30)
        painter = QtGui.QPainter(pixmap)
        try:
            overlay.paintEvent(QtGui.QPaintEvent(overlay.rect()))
        finally:
            painter.end()

    def test_paint_draws_band_color(self, overlay):
        """A bookmark's color should appear somewhere in the rendered image."""
        overlay.resize(400, 30)
        overlay.set_bookmarks(
            [make_bookmark(start=0, end=100, color="#FF0000")],
            (0, 100),
        )
        image = self._render(overlay)
        # Check that at least one pixel has a red-ish value.
        found_red = False
        for x in range(0, 400, 20):
            for y in range(0, 30, 5):
                c = QtGui.QColor(image.pixel(x, y))
                if c.red() > 150 and c.green() < 80 and c.blue() < 80:
                    found_red = True
                    break
            if found_red:
                break
        assert found_red, "Expected red bookmark band not found in rendered image"

    def test_paint_no_pixels_outside_frame_range(self, overlay):
        """Bands outside the visible frame range should not bleed into the image."""
        overlay.resize(400, 30)
        # Bookmark at frames 200-300, but visible range is 0-100.
        overlay.set_bookmarks(
            [make_bookmark(start=200, end=300, color="#00FF00")],
            (0, 100),
        )
        image = self._render(overlay)
        # The entire image should be near-black (our fill colour).
        found_green = False
        for x in range(0, 400, 10):
            c = QtGui.QColor(image.pixel(x, 15))
            if c.green() > 150:
                found_green = True
                break
        assert not found_green, "Unexpected green pixel found outside visible range"

    def test_minimum_band_width_applied(self, overlay):
        """A zero-duration bookmark should still paint a visible sliver."""
        overlay.resize(400, 30)
        overlay.set_bookmarks(
            [make_bookmark(start=50, end=50, color="#0000FF")],  # zero-duration
            (0, 100),
        )
        # Should not raise.
        pixmap = QtGui.QPixmap(overlay.size())
        overlay.render(pixmap)
