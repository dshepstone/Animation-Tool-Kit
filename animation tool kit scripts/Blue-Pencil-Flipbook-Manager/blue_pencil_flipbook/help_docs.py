"""Local HTML help viewer."""

from __future__ import annotations

import os

from .qt_compat import QtCore, QtWidgets
from . import theme

HELP_FILE = os.path.join(os.path.dirname(__file__), "resources", "help", "blue_pencil_flipbook_help.html")


def show_help(parent=None, anchor=None):
    if QtWidgets is None:
        return None
    dialog = QtWidgets.QDialog(parent)
    dialog.setWindowTitle("Blue Pencil Flipbook Manager Help")
    dialog.resize(720, 540)
    theme.apply(dialog)
    layout = QtWidgets.QVBoxLayout(dialog)
    browser = QtWidgets.QTextBrowser()
    browser.setOpenExternalLinks(True)
    browser.setSearchPaths([os.path.dirname(HELP_FILE)])
    browser.setSource(QtCore.QUrl.fromLocalFile(HELP_FILE) if hasattr(QtCore, "QUrl") else HELP_FILE)
    if anchor:
        browser.scrollToAnchor(anchor)
    layout.addWidget(browser)
    close = QtWidgets.QPushButton("Close")
    close.setProperty("role", "accent")
    close.clicked.connect(dialog.accept)
    layout.addWidget(close, alignment=QtCore.Qt.AlignRight)
    dialog.show()
    return dialog
