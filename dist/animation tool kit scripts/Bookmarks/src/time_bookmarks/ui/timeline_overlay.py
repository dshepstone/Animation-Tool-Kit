"""Transparent overlay widget painted over the Maya timeline.

Draws each bookmark as a frame — a solid top rail, solid bottom label
strip, and 2-pixel side edges — with the middle left completely
transparent so that Maya's red tick marks remain fully readable.

Mouse events pass straight through (``WA_TransparentForMouseEvents``).
The overlay self-registers an event filter on its parent to stay in sync
when the timeline is resized.

Frame → pixel mapping
---------------------
    x = (frame - range_start) / (range_end - range_start) * widget_width
"""

from __future__ import annotations

from typing import List, Tuple

from time_bookmarks.data.models import Bookmark
from time_bookmarks.qt_compat import QtCore, QtGui, QtWidgets


class TimelineOverlay(QtWidgets.QWidget):
    """Bookmark frame-outline overlay for the Maya timeline."""

    _LABEL_HEIGHT: int = 14  # px  solid label strip at the bottom
    _RAIL_H:       int = 3   # px  solid colour rail at the top
    _EDGE_W:       int = 2   # px  left/right edge lines
    _MIN_BAND_WIDTH: int = 3 # px  minimum visible width for a single-frame bookmark

    def __init__(self, parent_widget: QtWidgets.QWidget) -> None:
        super().__init__(parent_widget)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)  # type: ignore[attr-defined]
        self.setAttribute(QtCore.Qt.WA_NoSystemBackground, True)          # type: ignore[attr-defined]

        self._parent_widget = parent_widget
        self._bookmarks: List[Bookmark] = []
        self._frame_range: Tuple[int, int] = (0, 100)

        parent_widget.installEventFilter(self)
        self.setGeometry(parent_widget.rect())
        self.raise_()
        self.show()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_bookmarks(
        self,
        bookmarks: List[Bookmark],
        frame_range: Tuple[int, int],
    ) -> None:
        self._bookmarks = list(bookmarks)
        self._frame_range = frame_range
        self.update()

    def set_visible(self, visible: bool) -> None:
        self.setVisible(visible)

    # ------------------------------------------------------------------
    # Qt overrides
    # ------------------------------------------------------------------

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if obj is self._parent_widget:
            try:
                resize_t = QtCore.QEvent.Type.Resize
            except AttributeError:
                resize_t = QtCore.QEvent.Resize  # type: ignore[attr-defined]
            if event.type() == resize_t:
                self.setGeometry(self._parent_widget.rect())
        return False

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # type: ignore[override]
        if not self._bookmarks:
            return
        painter = QtGui.QPainter(self)
        try:
            self._draw(painter)
        finally:
            painter.end()

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _draw(self, painter: QtGui.QPainter) -> None:
        start_frame, end_frame = self._frame_range
        frame_span = max(end_frame - start_frame, 1)
        w = self.width()
        h = self.height()

        try:
            align = QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter
            elide = QtCore.Qt.TextElideMode.ElideRight
        except AttributeError:
            align = QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter  # type: ignore[attr-defined]
            elide = QtCore.Qt.ElideRight                           # type: ignore[attr-defined]

        label_y  = h - self._LABEL_HEIGHT
        middle_h = label_y - self._RAIL_H   # transparent gap height

        for bookmark in self._bookmarks:
            # Per-bookmark visibility — skip when the user has toggled it off.
            if not getattr(bookmark, "visible", True):
                continue

            x1 = int((bookmark.start_frame - start_frame) / frame_span * w)
            x2 = int((bookmark.end_frame   - start_frame) / frame_span * w)
            x2 = max(x2, x1 + self._MIN_BAND_WIDTH)
            band_w = x2 - x1

            color = QtGui.QColor(bookmark.color_hex)

            # ── Top rail ──────────────────────────────────────────────
            painter.fillRect(x1, 0, band_w, self._RAIL_H, color)

            # ── Bottom label strip ────────────────────────────────────
            painter.fillRect(x1, label_y, band_w, self._LABEL_HEIGHT, color)

            # Single-frame bookmarks only get the top rail and the bottom
            # label strip — no side edges — so the timeline stays clean.
            is_single_frame = bookmark.start_frame == bookmark.end_frame
            if not is_single_frame:
                # ── Left edge ─────────────────────────────────────────
                painter.fillRect(x1, self._RAIL_H, self._EDGE_W, middle_h, color)

                # ── Right edge ────────────────────────────────────────
                painter.fillRect(
                    x2 - self._EDGE_W, self._RAIL_H, self._EDGE_W, middle_h, color
                )

            # ── Name text in the label strip ──────────────────────────
            if bookmark.name and band_w > 6:
                r, g, b = color.red(), color.green(), color.blue()
                luminance = 0.299 * r + 0.587 * g + 0.114 * b
                text_color = (
                    QtGui.QColor("#000000") if luminance > 140
                    else QtGui.QColor("#FFFFFF")
                )
                painter.setPen(text_color)
                fm = painter.fontMetrics()
                label_text = fm.elidedText(
                    bookmark.name, elide, max(band_w - 4, 1)
                )
                painter.drawText(
                    x1 + 2, label_y, band_w - 4, self._LABEL_HEIGHT,
                    align, label_text,
                )
