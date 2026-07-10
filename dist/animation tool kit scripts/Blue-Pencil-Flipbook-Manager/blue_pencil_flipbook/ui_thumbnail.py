"""Thumbnail card widgets for the flipbook strip."""

from __future__ import annotations

from .qt_compat import QtCore, QtGui, QtWidgets, Signal, exec_menu
from . import theme

_BADGE = {
    "KEY": ("KEY", theme.KEY_COLOR),
    "BREAKDOWN": ("BDN", theme.BREAKDOWN_COLOR),
    "INBETWEEN": ("INB", theme.INBETWEEN_COLOR),
}


if QtWidgets is not None:
    class ThumbnailCard(QtWidgets.QFrame):
        clicked = Signal(dict)
        action_requested = Signal(str, dict)

        def __init__(self, entry, parent=None):
            super().__init__(parent)
            self.entry = entry
            self.setObjectName("ThumbnailCard")
            self.setCursor(QtCore.Qt.PointingHandCursor)
            self.setToolTip("Click to review the drawing large • Right-click for frame actions")
            self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
            self.customContextMenuRequested.connect(self._show_menu)
            layout = QtWidgets.QVBoxLayout(self)
            layout.setContentsMargins(6, 6, 6, 6)
            layout.setSpacing(4)
            self.image = QtWidgets.QLabel()
            self.image.setFixedSize(160, 90)
            self.image.setAlignment(QtCore.Qt.AlignCenter)
            self.image.setStyleSheet(
                "background:#1e2126; color:{0}; border-radius:5px;".format(theme.TEXT_DIM)
            )

            caption = QtWidgets.QHBoxLayout()
            caption.setContentsMargins(0, 0, 0, 0)
            caption.setSpacing(4)
            self.frame_label = QtWidgets.QLabel()
            self.frame_label.setStyleSheet("font-weight:600;")
            self.update_btn = QtWidgets.QPushButton("↻")
            self.update_btn.setFixedSize(22, 22)
            self.update_btn.setCursor(QtCore.Qt.PointingHandCursor)
            self.update_btn.setToolTip("Update this thumbnail from the current viewport")
            self.update_btn.setStyleSheet(
                "QPushButton {{ border:1px solid {b}; border-radius:11px; background:{p};"
                " color:{t}; font-size:13px; padding:0; }}"
                " QPushButton:hover {{ border-color:{a}; color:{a}; }}".format(
                    b=theme.BORDER, p=theme.PANEL_ALT, t=theme.TEXT, a=theme.ACCENT
                )
            )
            self.update_btn.clicked.connect(
                lambda checked=False: self.action_requested.emit("regenerate", self.entry)
            )
            self.badge = QtWidgets.QLabel()
            self.badge.setAlignment(QtCore.Qt.AlignCenter)
            self.badge.setFixedWidth(38)
            caption.addWidget(self.frame_label)
            caption.addStretch()
            caption.addWidget(self.update_btn)
            caption.addWidget(self.badge)

            self.goto_btn = QtWidgets.QPushButton("⏱  Go To Frame")
            self.goto_btn.setCursor(QtCore.Qt.PointingHandCursor)
            self.goto_btn.setToolTip("Jump Maya's current time to this drawing's frame")
            self.goto_btn.setStyleSheet(
                "QPushButton {{ border:1px solid {b}; border-radius:5px; background:{p};"
                " color:{t}; padding:4px; }}"
                " QPushButton:hover {{ border-color:{a}; color:{a}; }}".format(
                    b=theme.BORDER, p=theme.PANEL_ALT, t=theme.TEXT, a=theme.ACCENT
                )
            )
            self.goto_btn.clicked.connect(
                lambda checked=False: self.action_requested.emit("goto", self.entry)
            )

            layout.addWidget(self.image)
            layout.addLayout(caption)
            layout.addWidget(self.goto_btn)
            self.refresh(entry)

        def refresh(self, entry):
            self.entry = entry
            path = entry.get("thumbnail") or ""
            pixmap = QtGui.QPixmap(path) if path else QtGui.QPixmap()
            if not pixmap.isNull():
                self.image.setPixmap(pixmap.scaled(self.image.size(), QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation))
            else:
                self.image.setPixmap(QtGui.QPixmap())
                self.image.setText("No Thumbnail")
            self.frame_label.setText("Frame {0}".format(entry.get("frame", "?")))
            text, color = _BADGE.get(entry.get("type"), _BADGE["INBETWEEN"])
            self.badge.setText(text)
            self.badge.setStyleSheet(
                "font-weight:bold; font-size:10px; border-radius:8px; padding:2px 4px;"
                " background:{0}; color:white;".format(color)
            )

        def mousePressEvent(self, event):
            if event.button() == QtCore.Qt.LeftButton:
                self.clicked.emit(self.entry)
            super().mousePressEvent(event)

        def _show_menu(self, pos):
            menu = QtWidgets.QMenu(self)
            actions = [
                ("Go To Frame", "goto"), ("Mark as Key", "mark_key"),
                ("Mark as Breakdown", "mark_breakdown"), ("Mark as Inbetween", "mark_inbetween"),
                ("Duplicate Frame", "duplicate"), ("Delete Frame", "delete"),
                ("Regenerate Thumbnail", "regenerate"),
            ]
            for text, action in actions:
                item = menu.addAction(text)
                item.triggered.connect(lambda checked=False, a=action: self.action_requested.emit(a, self.entry))
            exec_menu(menu, self.mapToGlobal(pos))

else:
    class ThumbnailCard(object):
        """Placeholder used only when Qt is unavailable outside Maya."""

        def __init__(self, *args, **kwargs):
            raise RuntimeError("ThumbnailCard requires PySide2 or PySide6 inside Maya.")
