"""TimelineEventFilter — decodes modifier + mouse-button combos on the timeline.

This ``QObject`` is installed as an event filter on the Maya ``timeControl``
widget.  It never calls the controller directly; it only emits typed Qt
signals.  The controller (or the panel for UI actions) connects to those
signals in ``main.launch()``.

Shortcut map (matches the screenshots)
--------------------------------------
Ctrl + Alt + Shift + Click  →  remove_requested
Ctrl + Alt + Click          →  create_requested
Ctrl + Shift + Click        →  jump_requested
Alt  + Shift + Click        →  panel_requested
Ctrl + Click                →  navigate_next_requested
Shift + Click               →  navigate_prev_requested
Alt  + Click                →  visibility_requested

Return value
------------
``eventFilter`` always returns ``False`` so Maya's own click handling
(timeline scrubbing, etc.) continues to run normally.  If future testing
reveals conflicts a specific shortcut can be changed to return ``True``
to consume the event.
"""

from __future__ import annotations

from time_bookmarks.qt_compat import QtCore, Signal


def _flag(name: str, alt_name: str | None = None):
    """Return a Qt enum value by trying new-style PySide6 path then old-style."""
    Qt = QtCore.Qt
    for attr in ([name] if alt_name is None else [name, alt_name]):
        parts = attr.split(".")
        obj = Qt
        try:
            for part in parts:
                obj = getattr(obj, part)
            return obj
        except AttributeError:
            continue
    raise AttributeError(f"Cannot resolve Qt flag: {name!r}")


class TimelineEventFilter(QtCore.QObject):
    """Translates raw QMouseEvent combos into semantic bookmark signals.

    Install on the timeline widget::

        timeline = MayaQtBridge.get_timeline_widget()
        _filter = TimelineEventFilter(parent=timeline)
        timeline.installEventFilter(_filter)
    """

    # One signal per shortcut gesture — connect these in main.launch().
    create_requested = Signal()        # Ctrl + Alt + Click
    navigate_next_requested = Signal() # Ctrl + Click  (no Alt)
    navigate_prev_requested = Signal() # Shift + Click (no Ctrl, no Alt)
    jump_requested = Signal()          # Ctrl + Shift + Click (no Alt)
    remove_requested = Signal()        # Ctrl + Alt + Shift + Click
    panel_requested = Signal()         # Alt + Shift + Click (no Ctrl)
    visibility_requested = Signal()    # Alt + Click  (no Ctrl, no Shift)

    # ------------------------------------------------------------------
    # Resolve modifier / button constants once at class definition time
    # to avoid repeated attribute lookups in the hot path.
    # ------------------------------------------------------------------
    try:
        _LEFT   = QtCore.Qt.MouseButton.LeftButton            # type: ignore[attr-defined]
        _CTRL   = QtCore.Qt.KeyboardModifier.ControlModifier  # type: ignore[attr-defined]
        _ALT    = QtCore.Qt.KeyboardModifier.AltModifier      # type: ignore[attr-defined]
        _SHIFT  = QtCore.Qt.KeyboardModifier.ShiftModifier    # type: ignore[attr-defined]
        _PRESS  = QtCore.QEvent.Type.MouseButtonPress         # type: ignore[attr-defined]
    except AttributeError:
        # PySide2 fallback
        _LEFT   = QtCore.Qt.LeftButton        # type: ignore[attr-defined]
        _CTRL   = QtCore.Qt.ControlModifier   # type: ignore[attr-defined]
        _ALT    = QtCore.Qt.AltModifier       # type: ignore[attr-defined]
        _SHIFT  = QtCore.Qt.ShiftModifier     # type: ignore[attr-defined]
        _PRESS  = QtCore.QEvent.MouseButtonPress  # type: ignore[attr-defined]

    # ------------------------------------------------------------------

    def eventFilter(
        self,
        obj: QtCore.QObject,
        event: QtCore.QEvent,
    ) -> bool:
        if event.type() != self._PRESS:
            return False

        # Only act on left-button presses.
        if event.button() != self._LEFT:  # type: ignore[attr-defined]
            return False

        mods = event.modifiers()  # type: ignore[attr-defined]
        ctrl  = bool(mods & self._CTRL)
        alt   = bool(mods & self._ALT)
        shift = bool(mods & self._SHIFT)

        # Evaluate most-specific combos first.
        if ctrl and alt and shift:
            self.remove_requested.emit()
        elif ctrl and alt:
            self.create_requested.emit()
        elif ctrl and shift:
            self.jump_requested.emit()
        elif alt and shift:
            self.panel_requested.emit()
        elif ctrl:
            self.navigate_next_requested.emit()
        elif shift:
            self.navigate_prev_requested.emit()
        elif alt:
            self.visibility_requested.emit()
        # Bare click: no signal — Maya handles it normally.

        return False  # Never consume; let Maya scrub the timeline.
