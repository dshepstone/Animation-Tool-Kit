"""Main Time Bookmarks management panel.

``BookmarkPanel`` is a non-modal ``QDialog`` that is the primary UI surface
for the tool.  It receives a ``BookmarkController`` via constructor injection.

Layout::

    ┌─────────────────────────────────────────┐
    │ ◈  Time Bookmarks              [+ Add]  │  ← header
    ├─────────────────────────────────────────┤
    │ ▌ Hero Walk              1  –  73       │  ← list rows
    │ ▌ Jump Spin             75  – 126       │    (coloured left strip)
    │ ▌ Last Dance           198  – 271       │
    ├─────────────────────────────────────────┤
    │  n bookmarks    [Edit]  [Delete]  [Jump]│  ← footer
    └─────────────────────────────────────────┘
"""

from __future__ import annotations

from time_bookmarks.qt_compat import QtCore, QtGui, QtWidgets, exec_dialog
from time_bookmarks.ui.bookmark_creation_dialog import BookmarkCreationDialog
from time_bookmarks.ui.bookmark_list_widget import BookmarkListWidget

# ---------------------------------------------------------------------------
# Design tokens (must match bookmark_list_widget.py)
# ---------------------------------------------------------------------------

_BG_DARK    = "#1e1e1e"
_BG_PANEL   = "#252525"
_BG_HEADER  = "#1a1a1a"
_BG_FOOTER  = "#1f1f1f"
_BORDER     = "#333333"
_TEXT       = "#e8e8e8"
_DIM        = "#888888"
_ACCENT     = "#3d8fef"
_BTN        = "#2e2e2e"
_BTN_HV     = "#3a3a3a"
_BTN_PR     = "#252525"
_ADD_BG     = "#0e639c"
_ADD_HV     = "#1177bb"


class BookmarkPanel(QtWidgets.QDialog):
    """Primary bookmark management panel.

    Parameters
    ----------
    controller:
        A ``BookmarkController`` instance (injected).
    parent:
        Optional Qt parent widget.
    """

    def __init__(
        self,
        controller,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("MayaTimeBookmarksPanel")
        self.setWindowTitle("Time Bookmarks")
        self.setMinimumSize(400, 320)
        self.resize(460, 400)
        self.setWindowFlags(
            QtCore.Qt.Window |                 # type: ignore[attr-defined]
            QtCore.Qt.WindowCloseButtonHint    # type: ignore[attr-defined]
        )

        self._controller = controller
        self._build_ui()
        self._apply_style()
        self._controller.on_bookmarks_changed(self._refresh)
        self._sync_visibility_button()
        self._refresh()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def show(self) -> None:
        super().show()
        self.raise_()
        self.activateWindow()

    def open_create_dialog(self) -> None:
        """Open the creation dialog — called by timeline shortcut wiring."""
        self._on_add()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setSpacing(0)
        root.setContentsMargins(0, 0, 0, 0)

        # ── Header ────────────────────────────────────────────────────
        root.addWidget(self._make_header())
        root.addWidget(self._hline())

        # ── Bookmark list ─────────────────────────────────────────────
        self._list_widget = BookmarkListWidget(self)
        self._list_widget.bookmark_double_clicked.connect(self._on_edit_by_id)
        self._list_widget.bookmark_visibility_toggled.connect(
            self._on_toggle_bookmark_visibility
        )
        root.addWidget(self._list_widget, stretch=1)

        # ── Footer ────────────────────────────────────────────────────
        root.addWidget(self._hline())
        root.addWidget(self._make_footer())

    def _make_header(self) -> QtWidgets.QWidget:
        bar = QtWidgets.QWidget()
        bar.setObjectName("header")
        bar.setFixedHeight(44)
        h = QtWidgets.QHBoxLayout(bar)
        h.setContentsMargins(14, 0, 10, 0)
        h.setSpacing(10)

        # Accent diamond + title
        icon_lbl = QtWidgets.QLabel("◈")
        icon_lbl.setStyleSheet(f"color:{_ACCENT}; font-size:18px;")
        h.addWidget(icon_lbl)

        title = QtWidgets.QLabel("Time Bookmarks")
        title.setStyleSheet(f"color:{_TEXT}; font-size:13px; font-weight:600;")
        h.addWidget(title)

        h.addStretch()

        # Count badge
        self._count_label = QtWidgets.QLabel("")
        self._count_label.setObjectName("countBadge")
        self._count_label.setAlignment(QtCore.Qt.AlignCenter)  # type: ignore[attr-defined]
        self._count_label.setFixedHeight(20)
        self._count_label.setMinimumWidth(24)
        self._count_label.setVisible(False)
        h.addWidget(self._count_label)

        # Global visibility toggle button
        self._visibility_btn = QtWidgets.QPushButton("Hide All")
        self._visibility_btn.setObjectName("visibilityBtn")
        self._visibility_btn.setCheckable(True)
        self._visibility_btn.setFixedHeight(28)
        self._visibility_btn.setToolTip(
            "Toggle visibility of every bookmark on the timeline"
        )
        self._visibility_btn.clicked.connect(self._on_toggle_all_visibility)
        h.addWidget(self._visibility_btn)

        # Add button
        self._add_btn = QtWidgets.QPushButton("+ Add")
        self._add_btn.setObjectName("addBtn")
        self._add_btn.setFixedHeight(28)
        self._add_btn.setToolTip(
            "Create a new bookmark\n"
            "\n"
            "Tip: drag-select a frame range on the\n"
            "timeline first — it will auto-fill here.\n"
            "\n"
            "Shortcut: Ctrl+Alt+Click on the timeline"
        )
        self._add_btn.clicked.connect(self._on_add)
        h.addWidget(self._add_btn)

        return bar

    def _make_footer(self) -> QtWidgets.QWidget:
        bar = QtWidgets.QWidget()
        bar.setObjectName("footer")
        bar.setFixedHeight(42)
        h = QtWidgets.QHBoxLayout(bar)
        h.setContentsMargins(12, 0, 10, 0)
        h.setSpacing(6)

        self._status_label = QtWidgets.QLabel("")
        self._status_label.setStyleSheet(f"color:{_DIM}; font-size:11px;")
        h.addWidget(self._status_label)

        h.addStretch()

        self._edit_btn = self._make_btn(
            "Edit", "Edit selected bookmark\n(or double-click a row)"
        )
        self._edit_btn.clicked.connect(self._on_edit)
        h.addWidget(self._edit_btn)

        self._delete_btn = self._make_btn("Delete", "Delete selected bookmark")
        self._delete_btn.setObjectName("deleteBtn")
        self._delete_btn.clicked.connect(self._on_delete)
        h.addWidget(self._delete_btn)

        self._delete_all_btn = self._make_btn(
            "Delete All",
            "Delete every bookmark (shows a confirmation dialog first)",
        )
        self._delete_all_btn.setObjectName("deleteAllBtn")
        self._delete_all_btn.clicked.connect(self._on_delete_all)
        h.addWidget(self._delete_all_btn)

        self._jump_btn = self._make_btn(
            "Jump To", "Move the timeline cursor to this bookmark's start frame"
        )
        self._jump_btn.clicked.connect(self._on_jump)
        h.addWidget(self._jump_btn)

        return bar

    @staticmethod
    def _make_btn(label: str, tooltip: str) -> QtWidgets.QPushButton:
        btn = QtWidgets.QPushButton(label)
        btn.setFixedHeight(26)
        btn.setToolTip(tooltip)
        return btn

    @staticmethod
    def _hline() -> QtWidgets.QFrame:
        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.HLine)  # type: ignore[attr-defined]
        line.setStyleSheet(f"color:{_BORDER};")
        line.setFixedHeight(1)
        return line

    # ------------------------------------------------------------------
    # Stylesheet
    # ------------------------------------------------------------------

    def _apply_style(self) -> None:
        self.setStyleSheet(f"""
            BookmarkPanel {{
                background: {_BG_PANEL};
            }}
            QWidget {{
                background: {_BG_PANEL};
                color: {_TEXT};
                font-size: 12px;
            }}

            /* ── Header ── */
            QWidget#header {{
                background: {_BG_HEADER};
                border-top: 2px solid {_ACCENT};
            }}

            /* ── Footer ── */
            QWidget#footer {{
                background: {_BG_FOOTER};
            }}

            /* ── Count badge ── */
            QLabel#countBadge {{
                background: #2a3a4a;
                color: {_ACCENT};
                border: 1px solid #1e3050;
                border-radius: 9px;
                font-size: 11px;
                font-weight: 600;
                padding: 0 7px;
            }}

            /* ── Standard buttons — top-highlight gloss ── */
            QPushButton {{
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 #3a3a3a, stop:1 {_BTN}
                );
                color: {_TEXT};
                border-top:    1px solid rgba(255,255,255,0.10);
                border-left:   1px solid {_BORDER};
                border-right:  1px solid {_BORDER};
                border-bottom: 1px solid #1e1e1e;
                border-radius: 4px;
                padding: 0 12px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 #484848, stop:1 {_BTN_HV}
                );
                border-top: 1px solid rgba(255,255,255,0.18);
            }}
            QPushButton:pressed {{
                background: {_BTN_PR};
                border-top: 1px solid rgba(0,0,0,0.3);
            }}

            /* ── Add button (accent) ── */
            QPushButton#addBtn {{
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1a84c8, stop:1 {_ADD_BG}
                );
                border-top:    1px solid rgba(255,255,255,0.22);
                border-left:   1px solid {_ADD_BG};
                border-right:  1px solid {_ADD_BG};
                border-bottom: 1px solid #083050;
                border-radius: 4px;
                font-weight: 600;
                color: #ffffff;
                padding: 0 14px;
            }}
            QPushButton#addBtn:hover {{
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 #2292d8, stop:1 {_ADD_HV}
                );
            }}
            QPushButton#addBtn:pressed {{
                background: {_ADD_BG};
                border-top: 1px solid rgba(0,0,0,0.2);
            }}

            /* ── Delete button ── */
            QPushButton#deleteBtn:hover,
            QPushButton#deleteAllBtn:hover {{
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 #7a3030, stop:1 #5a2020
                );
                border-top: 1px solid rgba(255,255,255,0.12);
                border-color: #7a3030;
            }}
        """)

    # ------------------------------------------------------------------
    # Data helpers
    # ------------------------------------------------------------------

    def _refresh(self) -> None:
        bookmarks = self._controller.list_bookmarks()
        self._list_widget.set_bookmarks(bookmarks)
        n = len(bookmarks)
        if n:
            self._count_label.setText(str(n))
            self._count_label.setVisible(True)
            self._status_label.setText(
                f"{n} bookmark{'s' if n != 1 else ''}"
            )
            self._status_label.setStyleSheet(f"color:{_DIM}; font-size:11px;")
        else:
            self._count_label.setVisible(False)
            self._status_label.setText("Drag-select frames, then + Add")
            self._status_label.setStyleSheet(
                "color:#4a4a4a; font-size:11px; font-style:italic;"
            )

    def _selected_id(self) -> str | None:
        return self._list_widget.selected_bookmark_id()

    def _bookmark_by_id(self, bookmark_id: str):
        return next(
            (b for b in self._controller.list_bookmarks() if b.id == bookmark_id),
            None,
        )

    # ------------------------------------------------------------------
    # Action handlers
    # ------------------------------------------------------------------

    def _on_add(self) -> None:
        try:
            current_frame = self._controller.get_current_frame()
        except Exception:
            current_frame = None

        # Prefer a real multi-frame timeline drag-selection.
        # Without one, default to a single-frame bookmark pinned to the
        # timeline cursor so a quick "+ Add" just marks the current frame.
        sel = self._controller.get_timeline_selection()
        if sel is not None:
            start, end = sel
            from_sel = True
        elif current_frame is not None:
            start = end = current_frame
            from_sel = False
        else:
            start, end = self._controller.get_playback_range()
            from_sel = False

        dialog = BookmarkCreationDialog(
            start_frame=start,
            end_frame=end,
            from_selection=from_sel,
            current_frame=current_frame,
            parent=self,
        )
        if exec_dialog(dialog) == QtWidgets.QDialog.Accepted:
            req = dialog.get_request()
            if req is not None:
                self._controller.create_bookmark(
                    name=req.name,
                    start_frame=req.start_frame,
                    end_frame=req.end_frame,
                    color_hex=req.color_hex,
                    notes=req.notes,
                )

    def _on_edit(self) -> None:
        bid = self._selected_id()
        if bid:
            self._on_edit_by_id(bid)

    def _on_edit_by_id(self, bookmark_id: str) -> None:
        b = self._bookmark_by_id(bookmark_id)
        if b is None:
            return
        try:
            current_frame = self._controller.get_current_frame()
        except Exception:
            current_frame = None
        dialog = BookmarkCreationDialog(
            start_frame=b.start_frame,
            end_frame=b.end_frame,
            color_hex=b.color_hex,
            current_frame=current_frame,
            parent=self,
        )
        dialog.prefill(name=b.name, notes=b.notes or "")
        # Change the confirm button text for edit mode.
        for btn in dialog.findChildren(QtWidgets.QPushButton):
            if btn.objectName() == "ok_btn":
                btn.setText("Save Changes")
                break
        if exec_dialog(dialog) == QtWidgets.QDialog.Accepted:
            req = dialog.get_request()
            if req is not None:
                self._controller.update_bookmark(
                    bookmark_id,
                    name=req.name,
                    start_frame=req.start_frame,
                    end_frame=req.end_frame,
                    color_hex=req.color_hex,
                    notes=req.notes or None,
                )

    def _on_delete(self) -> None:
        bid = self._selected_id()
        if bid:
            self._controller.delete_bookmark(bid)

    def _on_delete_all(self) -> None:
        """Confirm and then delete every bookmark in the store."""
        count = len(self._controller.list_bookmarks())
        if count == 0:
            return
        try:
            yes = QtWidgets.QMessageBox.StandardButton.Yes
            no = QtWidgets.QMessageBox.StandardButton.No
        except AttributeError:
            yes = QtWidgets.QMessageBox.Yes  # type: ignore[attr-defined]
            no = QtWidgets.QMessageBox.No  # type: ignore[attr-defined]
        reply = QtWidgets.QMessageBox.question(
            self,
            "Delete all bookmarks?",
            f"This will permanently delete all {count} bookmark"
            f"{'s' if count != 1 else ''}. Continue?",
            yes | no,
            no,
        )
        if reply == yes:
            self._controller.delete_all_bookmarks()

    def _on_jump(self) -> None:
        bid = self._selected_id()
        if bid:
            self._controller.jump_to_bookmark(bid)

    # ------------------------------------------------------------------
    # Visibility handlers
    # ------------------------------------------------------------------

    def _on_toggle_all_visibility(self) -> None:
        """Flip the global overlay visibility state."""
        new_state = self._controller.toggle_visibility()
        self._sync_visibility_button(new_state)

    def _on_toggle_bookmark_visibility(self, bookmark_id: str) -> None:
        """Flip a single bookmark's visibility flag."""
        self._controller.toggle_bookmark_visible(bookmark_id)

    def _sync_visibility_button(self, state: bool | None = None) -> None:
        """Update the global visibility button's text/checked state."""
        if state is None:
            state = self._controller.overlay_visible
        self._visibility_btn.blockSignals(True)
        self._visibility_btn.setChecked(not state)
        self._visibility_btn.setText("Show All" if not state else "Hide All")
        self._visibility_btn.blockSignals(False)
