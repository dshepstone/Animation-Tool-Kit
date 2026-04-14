"""Bookmark list view — model, delegate, and container widget."""

from __future__ import annotations

from typing import Any, List, Optional

from time_bookmarks.data.models import Bookmark
from time_bookmarks.qt_compat import QtCore, QtGui, QtWidgets


# ---------------------------------------------------------------------------
# Colours (shared with panel stylesheet)
# ---------------------------------------------------------------------------

_BG_ROW       = "#252525"
_BG_ALT       = "#272727"
_BG_SELECTED  = "#2c4f7c"   # muted blue selection
_BG_HOVER     = "#2e2e2e"
_TEXT_NAME    = "#e8e8e8"
_TEXT_RANGE   = "#707070"
_TEXT_DIM     = "#555555"
_SEPARATOR    = "#333333"
_STRIP_W      = 5           # px — left colour strip width


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

class BookmarkListModel(QtCore.QAbstractListModel):
    """Data model for a flat list of bookmarks."""

    ColorHexRole:    int = QtCore.Qt.UserRole + 1   # type: ignore[attr-defined]
    StartFrameRole:  int = QtCore.Qt.UserRole + 2   # type: ignore[attr-defined]
    EndFrameRole:    int = QtCore.Qt.UserRole + 3   # type: ignore[attr-defined]
    BookmarkIdRole:  int = QtCore.Qt.UserRole + 4   # type: ignore[attr-defined]
    NotesRole:       int = QtCore.Qt.UserRole + 5   # type: ignore[attr-defined]
    VisibleRole:     int = QtCore.Qt.UserRole + 6   # type: ignore[attr-defined]

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._bookmarks: List[Bookmark] = []

    def rowCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._bookmarks)

    def data(self, index: QtCore.QModelIndex, role: int = QtCore.Qt.DisplayRole) -> Any:  # type: ignore[attr-defined]
        if not index.isValid() or not (0 <= index.row() < len(self._bookmarks)):
            return None
        b = self._bookmarks[index.row()]
        if role == QtCore.Qt.DisplayRole:  # type: ignore[attr-defined]
            return b.name or f"({b.start_frame} – {b.end_frame})"
        if role == self.ColorHexRole:   return b.color_hex
        if role == self.StartFrameRole: return b.start_frame
        if role == self.EndFrameRole:   return b.end_frame
        if role == self.BookmarkIdRole: return b.id
        if role == self.NotesRole:      return b.notes or ""
        if role == self.VisibleRole:    return getattr(b, "visible", True)
        if role == QtCore.Qt.ToolTipRole:  # type: ignore[attr-defined]
            note = f"\n{b.notes}" if b.notes else ""
            return f"{b.name}  [{b.start_frame} → {b.end_frame}]{note}"
        return None

    def refresh(self, bookmarks: List[Bookmark]) -> None:
        self.beginResetModel()
        self._bookmarks = list(bookmarks)
        self.endResetModel()


# ---------------------------------------------------------------------------
# Delegate
# ---------------------------------------------------------------------------

class BookmarkDelegate(QtWidgets.QStyledItemDelegate):
    """Paints each row:  [strip] [eye] [name] [notes dot] [frame range]."""

    _ROW_H       = 40
    _ROW_HEIGHT  = _ROW_H   # backward-compatible alias used by tests
    _RANGE_W     = 100
    _NOTES_DOT_W = 14
    _EYE_W       = 22
    _EYE_PAD     = 6
    _PAD_LEFT    = _STRIP_W + _EYE_W + _EYE_PAD + 8  # strip + eye + gap

    def sizeHint(self, option, index) -> QtCore.QSize:
        return QtCore.QSize(option.rect.width(), self._ROW_H)

    @classmethod
    def eye_rect(cls, row_rect: QtCore.QRect) -> QtCore.QRect:
        """Return the clickable visibility-toggle rect for a given row."""
        return QtCore.QRect(
            row_rect.left() + _STRIP_W + cls._EYE_PAD,
            row_rect.top(),
            cls._EYE_W,
            row_rect.height(),
        )

    def paint(self, painter: QtGui.QPainter, option, index) -> None:
        painter.save()
        r = option.rect
        selected = bool(
            option.state & QtWidgets.QStyle.State_Selected  # type: ignore[attr-defined]
        )

        # ── Row background ────────────────────────────────────────────
        if selected:
            bg = QtGui.QColor(_BG_SELECTED)
        elif option.state & QtWidgets.QStyle.State_MouseOver:  # type: ignore[attr-defined]
            bg = QtGui.QColor(_BG_HOVER)
        else:
            bg = QtGui.QColor(_BG_ROW)
        painter.fillRect(r, bg)

        # ── Coloured left strip ───────────────────────────────────────
        color_hex = index.data(BookmarkListModel.ColorHexRole) or "#555555"
        strip = QtCore.QRect(r.left(), r.top(), _STRIP_W, r.height())
        painter.fillRect(strip, QtGui.QColor(color_hex))

        # ── Visibility-toggle "eye" ──────────────────────────────────
        visible = index.data(BookmarkListModel.VisibleRole)
        if visible is None:
            visible = True
        self._paint_eye(painter, self.eye_rect(r), bool(visible), color_hex)

        # ── Name ─────────────────────────────────────────────────────
        name = index.data(QtCore.Qt.DisplayRole) or ""  # type: ignore[attr-defined]
        if not visible:
            text_color = QtGui.QColor(_TEXT_DIM)
        else:
            text_color = QtGui.QColor(_TEXT_NAME) if not selected else QtGui.QColor("#FFFFFF")
        painter.setPen(text_color)
        font = painter.font()
        font.setPointSizeF(font.pointSizeF())   # keep current size
        painter.setFont(font)

        name_x = r.left() + self._PAD_LEFT
        range_x = r.right() - self._RANGE_W
        name_rect = QtCore.QRect(name_x, r.top(), range_x - name_x - self._NOTES_DOT_W, r.height())
        try:
            align = QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter
        except AttributeError:
            align = QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter  # type: ignore[attr-defined]
        painter.drawText(name_rect, align, name)

        # ── Notes indicator dot ───────────────────────────────────────
        notes = index.data(BookmarkListModel.NotesRole) or ""
        if notes:
            dot_x = range_x - self._NOTES_DOT_W
            dot_rect = QtCore.QRect(dot_x, r.top(), self._NOTES_DOT_W, r.height())
            painter.setPen(QtGui.QColor(color_hex))
            painter.drawText(dot_rect, align, "●")

        # ── Frame range tag ───────────────────────────────────────────
        start = index.data(BookmarkListModel.StartFrameRole)
        end   = index.data(BookmarkListModel.EndFrameRole)
        if start is not None and end is not None:
            range_text = f"{start} – {end}"
            rr = QtCore.QRect(range_x, r.top(), self._RANGE_W - 8, r.height())
            painter.setPen(QtGui.QColor(_TEXT_RANGE if not selected else "#aaaaaa"))
            try:
                ra = QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter
            except AttributeError:
                ra = QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter  # type: ignore[attr-defined]
            painter.drawText(rr, ra, range_text)

        # ── Bottom separator ──────────────────────────────────────────
        painter.setPen(QtGui.QColor(_SEPARATOR))
        painter.drawLine(r.left() + _STRIP_W, r.bottom(), r.right(), r.bottom())

        painter.restore()

    @staticmethod
    def _paint_eye(
        painter: QtGui.QPainter,
        rect: QtCore.QRect,
        visible: bool,
        color_hex: str,
    ) -> None:
        """Draw a small eye icon that indicates per-bookmark visibility."""
        painter.save()
        try:
            try:
                painter.setRenderHint(QtGui.QPainter.Antialiasing, True)  # type: ignore[attr-defined]
            except AttributeError:
                pass

            # Centre a 16x16 square inside the clickable rect.
            side = 16
            cx = rect.center().x()
            cy = rect.center().y()
            box = QtCore.QRect(cx - side // 2, cy - side // 2, side, side)

            fg = QtGui.QColor(color_hex) if visible else QtGui.QColor(_TEXT_DIM)
            pen = QtGui.QPen(fg)
            pen.setWidth(2)
            painter.setPen(pen)
            painter.setBrush(QtCore.Qt.NoBrush)  # type: ignore[attr-defined]

            # Eye almond (ellipse) + pupil.
            painter.drawEllipse(box.adjusted(0, 3, 0, -3))
            if visible:
                pupil_side = 4
                pupil = QtCore.QRect(
                    cx - pupil_side // 2,
                    cy - pupil_side // 2,
                    pupil_side,
                    pupil_side,
                )
                painter.setBrush(fg)
                painter.drawEllipse(pupil)
            else:
                # Diagonal "hidden" slash across the eye.
                painter.drawLine(box.topLeft(), box.bottomRight())
        finally:
            painter.restore()


# ---------------------------------------------------------------------------
# Container widget
# ---------------------------------------------------------------------------

class BookmarkListWidget(QtWidgets.QWidget):
    """Wraps ``QListView`` + model + delegate into a convenient component."""

    bookmark_double_clicked = QtCore.Signal(str)    # type: ignore[attr-defined]
    bookmark_visibility_toggled = QtCore.Signal(str)  # type: ignore[attr-defined]

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._model = BookmarkListModel(self)
        self._delegate = BookmarkDelegate(self)
        self._build_ui()

    # -- Public API ---------------------------------------------------------

    def set_bookmarks(self, bookmarks: List[Bookmark]) -> None:
        self._model.refresh(bookmarks)
        # Show/hide the empty-state label.
        empty = len(bookmarks) == 0
        self._empty_label.setVisible(empty)
        self._list_view.setVisible(not empty)

    def selected_bookmark_id(self) -> Optional[str]:
        idxs = self._list_view.selectedIndexes()
        if not idxs:
            return None
        return self._model.data(idxs[0], BookmarkListModel.BookmarkIdRole)

    # -- Private ------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QtWidgets.QStackedLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setStackingMode(QtWidgets.QStackedLayout.StackAll)  # type: ignore[attr-defined]

        # Empty-state label (shown when no bookmarks exist)
        self._empty_label = QtWidgets.QLabel(
            "No bookmarks yet.\n\n"
            "Drag-select frames on the timeline,\n"
            "then click  + Add  to create one.\n\n"
            "Ctrl+Alt+Click on the timeline\n"
            "also opens the create dialog."
        )
        self._empty_label.setAlignment(QtCore.Qt.AlignCenter)  # type: ignore[attr-defined]
        self._empty_label.setStyleSheet(
            "color: #555555; font-size: 12px; background: #252525;"
        )
        self._empty_label.setWordWrap(True)
        layout.addWidget(self._empty_label)

        # List view
        self._list_view = QtWidgets.QListView(self)
        self._list_view.setModel(self._model)
        self._list_view.setItemDelegate(self._delegate)
        self._list_view.setSelectionMode(
            QtWidgets.QAbstractItemView.SingleSelection  # type: ignore[attr-defined]
        )
        self._list_view.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarAlwaysOff  # type: ignore[attr-defined]
        )
        self._list_view.setMouseTracking(True)
        self._list_view.setStyleSheet(
            "QListView {"
            f"  background: #252525; border: none; outline: none;"
            "}"
            "QListView::item { border: none; }"
            "QListView::item:selected { background: transparent; }"
            "QScrollBar:vertical {"
            "  background: #1e1e1e; width: 8px; margin: 0;"
            "}"
            "QScrollBar::handle:vertical {"
            f"  background: #444; border-radius: 4px; min-height: 24px;"
            "}"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )
        self._list_view.doubleClicked.connect(self._on_double_click)
        self._list_view.viewport().installEventFilter(self)
        layout.addWidget(self._list_view)

        # Initial state: no bookmarks
        self._empty_label.setVisible(True)
        self._list_view.setVisible(False)

    def _on_double_click(self, index: QtCore.QModelIndex) -> None:
        bookmark_id = self._model.data(index, BookmarkListModel.BookmarkIdRole)
        if bookmark_id:
            self.bookmark_double_clicked.emit(bookmark_id)

    # ------------------------------------------------------------------
    # Click routing — detects clicks on the per-row eye toggle
    # ------------------------------------------------------------------

    def eventFilter(self, obj, event) -> bool:
        try:
            press_type = QtCore.QEvent.Type.MouseButtonPress
        except AttributeError:
            press_type = QtCore.QEvent.MouseButtonPress  # type: ignore[attr-defined]
        if obj is self._list_view.viewport() and event.type() == press_type:
            try:
                left_btn = QtCore.Qt.MouseButton.LeftButton
            except AttributeError:
                left_btn = QtCore.Qt.LeftButton  # type: ignore[attr-defined]
            if event.button() == left_btn:
                pos = event.pos()
                index = self._list_view.indexAt(pos)
                if index.isValid():
                    row_rect = self._list_view.visualRect(index)
                    if BookmarkDelegate.eye_rect(row_rect).contains(pos):
                        bid = self._model.data(
                            index, BookmarkListModel.BookmarkIdRole
                        )
                        if bid:
                            self.bookmark_visibility_toggled.emit(bid)
                        return True  # consume — don't change selection
        return super().eventFilter(obj, event)
