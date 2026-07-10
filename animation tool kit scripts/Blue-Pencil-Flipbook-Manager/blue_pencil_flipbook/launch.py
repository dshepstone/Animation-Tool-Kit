"""Launch entry points for Maya.

Run in Maya's Script Editor:

import blue_pencil_flipbook.launch as bp
bp.show()
"""

from __future__ import annotations

_window = None


def show():
    global _window
    from . import ui_main
    _window = ui_main.show()
    return _window


def mark_current(frame_type):
    if _window:
        _window.mark_current(frame_type)


def previous_drawing():
    if _window:
        _window.previous_drawing()


def next_drawing():
    if _window:
        _window.next_drawing()


def play_mode(mode):
    if _window:
        _window.filter_combo.setCurrentText(mode)
        _window.play_pause()
    else:
        show().filter_combo.setCurrentText(mode)


# Simple launch command:
# import blue_pencil_flipbook.launch as bp
# bp.show()
