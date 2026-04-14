"""Dialog for creating or editing a single bookmark.

Usage::

    dialog = BookmarkCreationDialog(start_frame=1, end_frame=100, parent=parent)
    if exec_dialog(dialog) == QDialog.Accepted:
        req = dialog.get_request()  # BookmarkCreationRequest | None
"""

from __future__ import annotations

from dataclasses import dataclass, field

from time_bookmarks.qt_compat import QtCore, QtGui, QtWidgets, Signal, exec_dialog
from time_bookmarks.ui.color_picker import DEFAULT_PALETTE, ColorPickerModel


# ---------------------------------------------------------------------------
# Value object
# ---------------------------------------------------------------------------

@dataclass
class BookmarkCreationRequest:
    """Plain data object capturing everything the user entered."""

    name: str
    start_frame: int
    end_frame: int
    color_hex: str
    notes: str = field(default="")


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------

_DARK   = "#1e1e1e"
_PANEL  = "#252525"
_INPUT  = "#2d2d2d"
_BORDER = "#3a3a3a"
_TEXT   = "#e8e8e8"
_DIM    = "#888888"
_ACCENT = "#3d8fef"
_BTN    = "#333333"
_BTN_HV = "#404040"
_OK_BG  = "#0e639c"
_OK_HV  = "#1177bb"


class BookmarkCreationDialog(QtWidgets.QDialog):
    """Modal dialog for bookmark creation and editing.

    Parameters
    ----------
    start_frame / end_frame:
        Pre-filled frame range.
    color_hex:
        Initially selected colour.
    from_selection:
        When ``True`` a badge is shown indicating the range came from
        the user's timeline drag-selection rather than the playback range.
    parent:
        Optional Qt parent widget.
    """

    def __init__(
        self,
        start_frame: int = 1,
        end_frame: int = 100,
        color_hex: str = DEFAULT_PALETTE[0],
        from_selection: bool = False,
        current_frame: int | None = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Bookmark")
        self.setModal(True)
        self.setMinimumWidth(340)
        self.setMaximumWidth(420)

        self._color_model = ColorPickerModel()
        if color_hex in self._color_model.palette:
            self._color_model.selected_color = color_hex

        self._from_selection = from_selection
        self._current_frame = current_frame
        self._request: BookmarkCreationRequest | None = None
        self._build_ui(start_frame, end_frame)
        self._apply_style()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_request(self) -> BookmarkCreationRequest | None:
        return self._request

    def prefill(self, name: str = "", notes: str = "") -> None:
        self._name_edit.setText(name)
        self._notes_edit.setText(notes)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self, start_frame: int, end_frame: int) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setSpacing(0)
        root.setContentsMargins(0, 0, 0, 0)

        # ── Inner content area ────────────────────────────────────────
        content = QtWidgets.QWidget()
        inner = QtWidgets.QVBoxLayout(content)
        inner.setSpacing(14)
        inner.setContentsMargins(18, 18, 18, 14)
        root.addWidget(content)

        # ── Name ──────────────────────────────────────────────────────
        inner.addLayout(self._make_section("Name"))
        self._name_edit = QtWidgets.QLineEdit()
        self._name_edit.setPlaceholderText("e.g.  Hero Walk")
        self._name_edit.setFixedHeight(32)
        self._apply_name_bg(self._color_model.selected_color)
        inner.addWidget(self._name_edit)

        # ── Frame range ───────────────────────────────────────────────
        range_hdr = self._make_section("Frame Range")
        if self._from_selection:
            badge = QtWidgets.QLabel("● from timeline selection")
            badge.setStyleSheet(
                f"color:#4CAF50; font-size:10px; font-style:italic;"
            )
            range_hdr.addStretch()
            range_hdr.addWidget(badge)
        inner.addLayout(range_hdr)

        frame_row = QtWidgets.QHBoxLayout()
        frame_row.setSpacing(8)

        self._start_spin = QtWidgets.QSpinBox()
        self._start_spin.setRange(-99999, 99999)
        self._start_spin.setValue(start_frame)
        self._start_spin.setFixedHeight(30)
        self._start_spin.setAlignment(QtCore.Qt.AlignCenter)  # type: ignore[attr-defined]

        arrow = QtWidgets.QLabel("→")
        arrow.setStyleSheet(f"color:{_DIM}; font-size:14px;")
        arrow.setAlignment(QtCore.Qt.AlignCenter)  # type: ignore[attr-defined]

        self._end_spin = QtWidgets.QSpinBox()
        self._end_spin.setRange(-99999, 99999)
        self._end_spin.setValue(end_frame)
        self._end_spin.setFixedHeight(30)
        self._end_spin.setAlignment(QtCore.Qt.AlignCenter)  # type: ignore[attr-defined]

        frame_row.addWidget(self._start_spin)
        frame_row.addWidget(arrow)
        frame_row.addWidget(self._end_spin)
        frame_row.addStretch()
        inner.addLayout(frame_row)

        # ── Single-frame option ───────────────────────────────────────
        self._single_frame_check = QtWidgets.QCheckBox(
            "Single frame at current time"
        )
        if self._current_frame is None:
            self._single_frame_check.setEnabled(False)
            self._single_frame_check.setToolTip(
                "The current frame is not available in this context."
            )
        else:
            self._single_frame_check.setToolTip(
                f"Pin this bookmark to frame {self._current_frame}\n"
                "Only top and bottom strips are drawn on the timeline."
            )
            # Auto-enable when the incoming range is already a single frame
            # pinned to the current frame.
            if start_frame == end_frame == self._current_frame:
                self._single_frame_check.setChecked(True)
        self._single_frame_check.toggled.connect(self._on_single_frame_toggled)
        inner.addWidget(self._single_frame_check)
        # Sync spinbox state with initial checkbox state.
        self._on_single_frame_toggled(self._single_frame_check.isChecked())

        # ── Colour ────────────────────────────────────────────────────
        inner.addLayout(self._make_section("Colour"))
        from time_bookmarks.ui.color_picker import ColorPickerWidget
        self._color_widget = ColorPickerWidget(model=self._color_model, parent=self)
        self._color_widget.color_selected.connect(self._on_color_changed)
        inner.addWidget(self._color_widget)

        # ── Notes ─────────────────────────────────────────────────────
        inner.addLayout(self._make_section("Notes  (optional)"))
        self._notes_edit = QtWidgets.QLineEdit()
        self._notes_edit.setPlaceholderText("Reminder, shot context …")
        self._notes_edit.setFixedHeight(30)
        inner.addWidget(self._notes_edit)

        # ── Divider ───────────────────────────────────────────────────
        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.HLine)  # type: ignore[attr-defined]
        line.setStyleSheet(f"color:{_BORDER};")
        root.addWidget(line)

        # ── Button row ────────────────────────────────────────────────
        btn_bar = QtWidgets.QWidget()
        btn_layout = QtWidgets.QHBoxLayout(btn_bar)
        btn_layout.setContentsMargins(18, 10, 18, 14)
        btn_layout.setSpacing(10)

        cancel_btn = QtWidgets.QPushButton("Cancel")
        cancel_btn.setFixedHeight(32)
        cancel_btn.clicked.connect(self.reject)

        ok_btn = QtWidgets.QPushButton("Create")
        ok_btn.setFixedHeight(32)
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self._on_accept)
        ok_btn.setObjectName("ok_btn")

        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(ok_btn)
        root.addWidget(btn_bar)

    @staticmethod
    def _make_section(label: str) -> QtWidgets.QHBoxLayout:
        """Return an HBoxLayout containing a styled section label."""
        row = QtWidgets.QHBoxLayout()
        lbl = QtWidgets.QLabel(label)
        lbl.setStyleSheet(
            f"color:{_DIM}; font-size:11px; font-weight:600; text-transform:uppercase;"
        )
        row.addWidget(lbl)
        return row

    # ------------------------------------------------------------------
    # Styling
    # ------------------------------------------------------------------

    def _apply_style(self) -> None:
        self.setStyleSheet(f"""
            BookmarkCreationDialog {{
                background: {_DARK};
            }}
            QWidget {{
                background: {_DARK};
                color: {_TEXT};
                font-size: 12px;
            }}
            QLineEdit, QSpinBox {{
                background: {_INPUT};
                color: {_TEXT};
                border: 1px solid {_BORDER};
                border-radius: 4px;
                padding: 0 6px;
                selection-background-color: {_ACCENT};
            }}
            QLineEdit:focus, QSpinBox:focus {{
                border: 1px solid {_ACCENT};
            }}
            QSpinBox::up-button, QSpinBox::down-button {{
                width: 18px;
                border: none;
                background: {_BTN};
            }}
            QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
                background: {_BTN_HV};
            }}
            QPushButton {{
                background: {_BTN};
                color: {_TEXT};
                border: 1px solid {_BORDER};
                border-radius: 4px;
                padding: 0 16px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background: {_BTN_HV};
            }}
            QPushButton:pressed {{
                background: #2a2a2a;
            }}
            QPushButton#ok_btn {{
                background: {_OK_BG};
                border-color: {_OK_BG};
                font-weight: 600;
            }}
            QPushButton#ok_btn:hover {{
                background: {_OK_HV};
                border-color: {_OK_HV};
            }}
            QFrame[frameShape="4"] {{
                color: {_BORDER};
            }}
        """)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _on_color_changed(self, color_hex: str) -> None:
        self._apply_name_bg(color_hex)

    def _on_single_frame_toggled(self, checked: bool) -> None:
        """Lock the frame range to the current frame when enabled."""
        if checked and self._current_frame is not None:
            self._start_spin.setValue(self._current_frame)
            self._end_spin.setValue(self._current_frame)
            self._start_spin.setEnabled(False)
            self._end_spin.setEnabled(False)
        else:
            self._start_spin.setEnabled(True)
            self._end_spin.setEnabled(True)

    def _apply_name_bg(self, color_hex: str) -> None:
        """Tint the name field with the chosen colour as a live preview."""
        r = int(color_hex[1:3], 16)
        g = int(color_hex[3:5], 16)
        b = int(color_hex[5:7], 16)
        luminance = 0.299 * r + 0.587 * g + 0.114 * b
        text_color = "#000000" if luminance > 140 else "#FFFFFF"
        self._name_edit.setStyleSheet(
            f"QLineEdit {{"
            f"  background-color: {color_hex};"
            f"  color: {text_color};"
            f"  border: 1px solid rgba(0,0,0,0.4);"
            f"  border-radius: 4px;"
            f"  padding: 0 6px;"
            f"  font-size: 13px;"
            f"  font-weight: 500;"
            f"}}"
        )

    def _on_accept(self) -> None:
        if self._end_spin.value() < self._start_spin.value():
            QtWidgets.QMessageBox.warning(
                self,
                "Invalid Range",
                "End frame must be greater than or equal to start frame.",
            )
            return
        self._request = BookmarkCreationRequest(
            name=self._name_edit.text().strip(),
            start_frame=self._start_spin.value(),
            end_frame=self._end_spin.value(),
            color_hex=self._color_model.selected_color,
            notes=self._notes_edit.text().strip(),
        )
        self.accept()

    # ------------------------------------------------------------------
    # Keyboard
    # ------------------------------------------------------------------

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        Qt = QtCore.Qt
        try:
            enter_keys = (Qt.Key.Key_Return, Qt.Key.Key_Enter)
        except AttributeError:
            enter_keys = (Qt.Key_Return, Qt.Key_Enter)  # type: ignore[attr-defined]
        if event.key() in enter_keys:
            self._on_accept()
        else:
            super().keyPressEvent(event)
