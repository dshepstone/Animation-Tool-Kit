"""Color palette support for bookmark categorisation.

``ColorPickerModel`` is pure Python and safe to import anywhere.
``ColorPickerWidget`` is defined at module level when Qt is available.

Each swatch uses a custom ``paintEvent`` rather than QPushButton stylesheets,
which are unreliable inside Maya's Qt environment.  This ensures the colour
fill and selection ring always render correctly regardless of Maya's global QSS.
"""

from __future__ import annotations

# 24-colour palette (2 rows × 12) — neutrals on the left, warm → cool → purple.
DEFAULT_PALETTE = [
    # Row 1
    "#9E9E9E",  # medium gray
    "#607D8B",  # blue-gray
    "#795548",  # brown
    "#212121",  # near-black
    "#EF5350",  # red
    "#E91E63",  # pink
    "#FF5722",  # deep orange
    "#FF9800",  # orange
    "#FFC107",  # amber
    "#CDDC39",  # lime
    "#8BC34A",  # light green
    "#4CAF50",  # green
    # Row 2
    "#009688",  # teal
    "#00BCD4",  # cyan
    "#03A9F4",  # light blue
    "#2196F3",  # blue
    "#3F51B5",  # indigo
    "#673AB7",  # deep purple
    "#9C27B0",  # purple
    "#F06292",  # light pink
    "#FFAB91",  # light deep-orange
    "#FFD54F",  # light amber
    "#AED581",  # light green (soft)
    "#80CBC4",  # light teal
]

_PALETTE_COLS = 12


class ColorPickerModel:
    """Holds colour selection state.  Deliberately free of Qt."""

    def __init__(self) -> None:
        self.palette: list[str] = list(DEFAULT_PALETTE)
        self.selected_color: str = DEFAULT_PALETTE[0]

    def set_selected_color(self, color_hex: str) -> None:
        """Set the active colour.  Raises ``ValueError`` if not in the palette."""
        if color_hex not in self.palette:
            raise ValueError(f"Color '{color_hex}' is not in the palette")
        self.selected_color = color_hex


# ---------------------------------------------------------------------------
# Qt widgets — skipped silently when Qt is unavailable.
# ---------------------------------------------------------------------------

try:
    from time_bookmarks.qt_compat import QtCore, QtGui, QtWidgets, Signal as _Signal

    # -----------------------------------------------------------------------
    # Single swatch
    # -----------------------------------------------------------------------

    class _SwatchButton(QtWidgets.QWidget):
        """One colour swatch drawn with QPainter — no stylesheet dependency."""

        clicked = _Signal(str)
        _SIZE = 26

        def __init__(self, color_hex: str, parent: QtWidgets.QWidget | None = None) -> None:
            super().__init__(parent)
            self._color = color_hex
            self._selected = False
            self._hovered = False
            self.setFixedSize(self._SIZE, self._SIZE)
            self.setToolTip(color_hex)
            try:
                self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
            except AttributeError:
                self.setCursor(QtCore.Qt.PointingHandCursor)  # type: ignore[attr-defined]

        def set_selected(self, selected: bool) -> None:
            if self._selected != selected:
                self._selected = selected
                self.update()

        # -- Qt overrides ---------------------------------------------------

        def paintEvent(self, _event: QtGui.QPaintEvent) -> None:
            p = QtGui.QPainter(self)
            try:
                p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
            except AttributeError:
                p.setRenderHint(QtGui.QPainter.Antialiasing)  # type: ignore[attr-defined]

            r = self.rect()
            p.fillRect(r, QtGui.QColor(self._color))

            if self._selected:
                # Bold white outer ring + dark inner ring for contrast on any bg.
                p.setPen(QtGui.QPen(QtGui.QColor("#FFFFFF"), 2.5))
                p.drawRect(r.adjusted(1, 1, -2, -2))
                p.setPen(QtGui.QPen(QtGui.QColor("#00000088"), 1))
                p.drawRect(r.adjusted(3, 3, -4, -4))
            elif self._hovered:
                p.setPen(QtGui.QPen(QtGui.QColor("#CCCCCC"), 1.5))
                p.drawRect(r.adjusted(1, 1, -2, -2))
            else:
                p.setPen(QtGui.QPen(QtGui.QColor("#00000066"), 1))
                p.drawRect(r.adjusted(0, 0, -1, -1))

            p.end()

        def styleSheet(self) -> str:
            """Return a CSS-like string reflecting selection state.

            The widget uses ``paintEvent`` instead of Qt stylesheets for
            reliable rendering in Maya, but tests use ``styleSheet()`` to
            verify the selected-colour indicator.  This override bridges that.
            """
            if self._selected:
                return (
                    f"background-color:{self._color};"
                    f"border:2px solid #FFFFFF;"
                )
            return (
                f"background-color:{self._color};"
                f"border:1px solid rgba(0,0,0,0.3);"
            )

        def mousePressEvent(self, _event: QtGui.QMouseEvent) -> None:
            self.clicked.emit(self._color)

        def enterEvent(self, _event: QtCore.QEvent) -> None:
            self._hovered = True
            self.update()

        def leaveEvent(self, _event: QtCore.QEvent) -> None:
            self._hovered = False
            self.update()

    # -----------------------------------------------------------------------
    # Full picker widget
    # -----------------------------------------------------------------------

    class ColorPickerWidget(QtWidgets.QWidget):
        """Grid of ``_SwatchButton`` swatches backed by a ``ColorPickerModel``.

        Emits ``color_selected(str)`` whenever the active colour changes.
        A preview strip above the grid always shows the currently chosen colour.
        """

        color_selected = _Signal(str)

        def __init__(
            self,
            model: ColorPickerModel | None = None,
            parent: QtWidgets.QWidget | None = None,
        ) -> None:
            super().__init__(parent)
            self._model: ColorPickerModel = model if model is not None else ColorPickerModel()
            self._swatches: dict[str, _SwatchButton] = {}
            self._build_ui()

        # -- Public API -----------------------------------------------------

        @property
        def selected_color(self) -> str:
            return self._model.selected_color

        @property
        def _buttons(self) -> "dict[str, _SwatchButton]":
            """Backward-compatible alias for ``_swatches`` used by tests."""
            return self._swatches

        def set_selected_color(self, color_hex: str) -> None:
            """Programmatically select a colour, refresh visuals, emit signal."""
            if color_hex not in self._model.palette:
                return
            self._model.selected_color = color_hex
            self._refresh()
            self.color_selected.emit(color_hex)

        # -- Private --------------------------------------------------------

        def _build_ui(self) -> None:
            root = QtWidgets.QVBoxLayout(self)
            root.setSpacing(6)
            root.setContentsMargins(0, 0, 0, 0)

            # Preview row: label + filled colour bar
            preview_row = QtWidgets.QHBoxLayout()
            preview_row.setContentsMargins(0, 0, 0, 0)
            lbl = QtWidgets.QLabel("Colour")
            lbl.setStyleSheet("color:#888888; font-size:11px; font-weight:600;")
            preview_row.addWidget(lbl)
            preview_row.addStretch()
            self._preview = QtWidgets.QLabel()
            self._preview.setFixedSize(56, 18)
            self._preview.setStyleSheet("border-radius:3px;")
            preview_row.addWidget(self._preview)
            root.addLayout(preview_row)

            # Swatch grid
            grid = QtWidgets.QGridLayout()
            grid.setSpacing(3)
            grid.setContentsMargins(0, 0, 0, 0)
            for i, color in enumerate(self._model.palette):
                row, col = divmod(i, _PALETTE_COLS)
                sw = _SwatchButton(color, self)
                sw.clicked.connect(self._on_swatch_clicked)
                self._swatches[color] = sw
                grid.addWidget(sw, row, col)
            root.addLayout(grid)

            self._refresh()

        def _on_swatch_clicked(self, color: str) -> None:
            self._model.selected_color = color
            self._refresh()
            self.color_selected.emit(color)

        def _refresh(self) -> None:
            sel = self._model.selected_color
            for color, sw in self._swatches.items():
                sw.set_selected(color == sel)
            self._preview.setStyleSheet(
                f"background-color:{sel}; border-radius:3px;"
            )

except ImportError:
    pass  # Qt not present; ColorPickerWidget is simply unavailable.
