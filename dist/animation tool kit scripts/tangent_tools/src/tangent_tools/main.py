"""Tangent Tools — launch entrypoint.

Run from Maya's script editor::

    import tangent_tools.main
    tangent_tools.main.launch()

``launch`` is idempotent: if the panel is already open it brings the
existing window back to the front rather than spawning a second one.
"""
from __future__ import absolute_import, division, print_function

try:
    from PySide6 import QtWidgets
except ImportError:
    from PySide2 import QtWidgets

from . import ui


_window = None  # Keep a module-level reference so Qt doesn't GC the panel.


def launch():
    """Show the Tangent Tools panel, reusing an existing one if present."""
    global _window

    # If a previous panel is still alive, just raise it.
    app = QtWidgets.QApplication.instance()
    if app is not None:
        for w in app.topLevelWidgets():
            if w.objectName() == ui.WINDOW_OBJECT_NAME:
                try:
                    w.show()
                    w.raise_()
                    w.activateWindow()
                    _window = w
                    return w
                except Exception:
                    try:
                        w.deleteLater()
                    except Exception:
                        pass

    _window = ui.TangentToolsWindow()
    _window.show()
    _window.raise_()
    _window.activateWindow()
    return _window
