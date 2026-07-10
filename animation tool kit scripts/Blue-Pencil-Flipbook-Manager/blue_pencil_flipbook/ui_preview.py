"""Large thumbnail review dialog, opened by clicking a card."""

from __future__ import annotations

from .qt_compat import QtCore, QtGui, QtWidgets

from . import theme

_TYPE_LABEL = {"KEY": "Key", "BREAKDOWN": "Breakdown", "INBETWEEN": "Inbetween"}
_TYPE_COLOR = {
    "KEY": theme.KEY_COLOR,
    "BREAKDOWN": theme.BREAKDOWN_COLOR,
    "INBETWEEN": theme.INBETWEEN_COLOR,
}


if QtWidgets is not None:
    class ThumbnailPreview(QtWidgets.QDialog):
        """Shows a tracked drawing's capture at review size.

        The capture is stored at preview resolution, so this simply displays it
        large (upscaling smoothly if the image predates the higher-res capture).
        """

        go_to_frame_requested = QtCore.Signal(dict)

        def __init__(self, entry, parent=None):
            super().__init__(parent)
            self.entry = entry
            self.setObjectName("BluePencilFlipbookPreview")
            frame = entry.get("frame", "?")
            kind = entry.get("type", "INBETWEEN")
            self.setWindowTitle("Frame {0} — {1}".format(frame, _TYPE_LABEL.get(kind, kind)))
            self.setModal(True)
            theme.apply(self)

            layout = QtWidgets.QVBoxLayout(self)
            layout.setContentsMargins(12, 12, 12, 12)
            layout.setSpacing(10)

            self.image = QtWidgets.QLabel()
            self.image.setAlignment(QtCore.Qt.AlignCenter)
            self.image.setMinimumSize(320, 180)
            self.image.setStyleSheet(
                "background:#1e2126; color:{0}; border-radius:6px;".format(theme.TEXT_DIM)
            )
            layout.addWidget(self.image, 1)

            caption = QtWidgets.QHBoxLayout()
            info = QtWidgets.QLabel("Frame {0}   •   Camera: {1}   •   Layer: {2}".format(
                frame, entry.get("camera", "?"), entry.get("layer", "?")))
            info.setProperty("role", "sectionCaption")
            badge = QtWidgets.QLabel(_TYPE_LABEL.get(kind, kind))
            badge.setStyleSheet(
                "font-weight:bold; font-size:11px; border-radius:8px; padding:2px 10px;"
                " background:{0}; color:white;".format(_TYPE_COLOR.get(kind, theme.INBETWEEN_COLOR))
            )
            caption.addWidget(info)
            caption.addStretch()
            caption.addWidget(badge)
            layout.addLayout(caption)

            buttons = QtWidgets.QHBoxLayout()
            buttons.addStretch()
            goto = QtWidgets.QPushButton("Go To Frame")
            goto.setProperty("role", "accent")
            goto.setToolTip("Set Maya's current time to this drawing's frame")
            goto.clicked.connect(self._go_to_frame)
            close = QtWidgets.QPushButton("Close")
            close.clicked.connect(self.reject)
            buttons.addWidget(goto)
            buttons.addWidget(close)
            layout.addLayout(buttons)

            self._pixmap = QtGui.QPixmap(entry.get("thumbnail") or "")
            if self._pixmap.isNull():
                self.image.setText("No Thumbnail")
                self.resize(560, 380)
            else:
                # Open at the stored capture size, capped to 960 wide for small
                # screens (the 960x540 captures show at full size here).
                width = min(self._pixmap.width(), 960)
                height = int(width * 9 / 16)
                self.resize(width + 24, height + 110)

        def _go_to_frame(self):
            self.go_to_frame_requested.emit(self.entry)
            self.accept()

        def resizeEvent(self, event):
            super().resizeEvent(event)
            self._update_image()

        def showEvent(self, event):
            super().showEvent(event)
            self._update_image()

        def _update_image(self):
            if not self._pixmap.isNull():
                self.image.setPixmap(self._pixmap.scaled(
                    self.image.size(), QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation))

else:
    class ThumbnailPreview(object):
        def __init__(self, *args, **kwargs):
            raise RuntimeError("ThumbnailPreview requires PySide2 or PySide6 inside Maya.")
