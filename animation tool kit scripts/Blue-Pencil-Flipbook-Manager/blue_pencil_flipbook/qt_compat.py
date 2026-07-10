"""Qt binding compatibility helpers for Maya.

Maya 2026 installations may expose either PySide2 or PySide6 depending on the
host build and environment. This module selects the first available binding and
keeps the rest of the package from conditionally defining missing UI classes.
"""

from __future__ import annotations

import importlib
import importlib.util

BINDING = None
QtCore = None
QtGui = None
QtWidgets = None
Signal = None


def _load_binding(name):
    return (
        importlib.import_module(name + ".QtCore"),
        importlib.import_module(name + ".QtGui"),
        importlib.import_module(name + ".QtWidgets"),
    )


# Maya 2025+ ships PySide6, so prefer it and fall back to PySide2 for older hosts.
if importlib.util.find_spec("PySide6") is not None:
    QtCore, QtGui, QtWidgets = _load_binding("PySide6")
    BINDING = "PySide6"
elif importlib.util.find_spec("PySide2") is not None:
    QtCore, QtGui, QtWidgets = _load_binding("PySide2")
    BINDING = "PySide2"

if QtCore is not None:
    Signal = QtCore.Signal


def require_qt():
    """Return Qt modules or raise a clear error for non-Maya/non-Qt sessions."""
    if QtWidgets is None:
        raise RuntimeError("Blue Pencil Flipbook Manager requires PySide2 or PySide6 inside Maya.")
    return QtCore, QtGui, QtWidgets


def exec_menu(menu, global_pos):
    """Execute a menu with the correct API name for PySide2 or PySide6."""
    if hasattr(menu, "exec_"):
        return menu.exec_(global_pos)
    return menu.exec(global_pos)
