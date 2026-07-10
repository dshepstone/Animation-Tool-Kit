"""Filtered Blue Pencil playback using a Qt timer rather than Maya playback."""

from __future__ import annotations

from .qt_compat import QtCore

from . import maya_blue_pencil_api as bp
from . import metadata_store

FILTERS = {
    "Keys Only": {"KEY"},
    "Keys + Breakdowns": {"KEY", "BREAKDOWN"},
    "All Drawings": {"KEY", "BREAKDOWN", "INBETWEEN"},
}


class FlipbookPlayer(QtCore.QObject if QtCore else object):
    def __init__(self, parent=None):
        if QtCore:
            super().__init__(parent)
            self.timer = QtCore.QTimer(self)
            self.timer.timeout.connect(self._tick)
        else:
            self.timer = None
        self.frames = []
        self.index = 0
        self.fps = 12
        self.loop = True
        self.mode = "All Drawings"

    def filtered_frames(self, camera=None, layer=None, mode=None):
        allowed = FILTERS.get(mode or self.mode, FILTERS["All Drawings"])
        frames = []
        for entry in metadata_store.load_metadata().get("frames", []):
            if camera and entry.get("camera") != camera:
                continue
            if layer and entry.get("layer") != layer:
                continue
            if entry.get("type") in allowed:
                frames.append(entry)
        return sorted(frames, key=lambda item: int(item.get("frame", 0)))

    def play(self, camera=None, layer=None, mode=None, fps=None, loop=None):
        self.mode = mode or self.mode
        self.fps = int(fps or self.fps or 12)
        if loop is not None:
            self.loop = bool(loop)
        self.frames = self.filtered_frames(camera, layer, self.mode)
        self.index = 0
        if not self.frames or not self.timer:
            return
        self.timer.start(max(1, int(1000.0 / self.fps)))
        self._show_current()

    def pause(self):
        if self.timer:
            self.timer.stop()

    def stop(self):
        self.pause()
        self.index = 0

    def previous(self, camera=None, layer=None, mode=None):
        frames = self.filtered_frames(camera, layer, mode)
        if not frames:
            return None
        current = bp.current_time()
        previous = frames[-1]
        for entry in frames:
            if int(entry.get("frame", 0)) < current:
                previous = entry
            else:
                break
        bp.set_current_time(previous.get("frame"))
        return previous

    def next(self, camera=None, layer=None, mode=None):
        frames = self.filtered_frames(camera, layer, mode)
        if not frames:
            return None
        current = bp.current_time()
        target = frames[0]
        for entry in frames:
            if int(entry.get("frame", 0)) > current:
                target = entry
                break
        bp.set_current_time(target.get("frame"))
        return target

    def _show_current(self):
        if self.frames:
            bp.set_current_time(self.frames[self.index].get("frame"))

    def _tick(self):
        if not self.frames:
            self.stop()
            return
        self.index += 1
        if self.index >= len(self.frames):
            if self.loop:
                self.index = 0
            else:
                self.stop()
                return
        self._show_current()
