"""PySide2 / PySide6 compatibility shim.

This is the ONLY file in the project that imports Qt conditionally.
All other modules obtain Qt via::

    from time_bookmarks.qt_compat import QtWidgets, QtCore, QtGui, Signal, Slot

The shim also exposes small helpers that paper over the most common API
differences between the two bindings.
"""

from __future__ import annotations

try:
    from PySide6 import QtCore, QtGui, QtWidgets
    from PySide6.QtCore import Signal, Slot

    QT_BINDING = "PySide6"

    def exec_dialog(dialog: QtWidgets.QDialog) -> int:
        """Execute a QDialog modally. Returns the result code."""
        return dialog.exec()

    def exec_app(app: QtWidgets.QApplication) -> int:
        """Start the QApplication event loop."""
        return app.exec()

except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets  # type: ignore[no-redef]
    from PySide2.QtCore import Signal, Slot  # type: ignore[no-redef]

    QT_BINDING = "PySide2"

    def exec_dialog(dialog: QtWidgets.QDialog) -> int:  # type: ignore[misc]
        return dialog.exec_()

    def exec_app(app: QtWidgets.QApplication) -> int:  # type: ignore[misc]
        return app.exec_()


__all__ = [
    "QT_BINDING",
    "QtCore",
    "QtGui",
    "QtWidgets",
    "Signal",
    "Slot",
    "exec_dialog",
    "exec_app",
]
