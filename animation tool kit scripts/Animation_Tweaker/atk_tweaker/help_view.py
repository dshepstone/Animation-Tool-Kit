"""Offline HTML help in a small Qt window (no network, no browser)."""
from pathlib import Path

from .qt_compat import QtCore, QtGui, QtWidgets

HERE = Path(__file__).resolve().parent
SECTIONS = (("Getting started", "start"), ("How tweaks are stored", "storage"),
            ("Sculpt and commit", "sculpt"), ("Keying modes", "keying"),
            ("Tweak list", "list"), ("Shape: inflate and relax", "shape"),
            ("Effects", "effects"), ("Surface Handle", "handle"),
            ("Utilities", "utilities"), ("Cache versions", "cache"),
            ("Troubleshooting", "troubleshooting"), ("About", "about"))


def icon_path():
    return HERE / "assets" / "animation_tweaker_32.png"


class HelpWindow(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Animation Tweaker Help")
        self.setWindowIcon(QtGui.QIcon(str(icon_path())))
        self.resize(900, 720)
        layout = QtWidgets.QVBoxLayout(self)
        row = QtWidgets.QHBoxLayout()
        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText("Find a word or phrase…")
        find = QtWidgets.QPushButton("Find next")
        row.addWidget(self.search)
        row.addWidget(find)
        layout.addLayout(row)
        splitter = QtWidgets.QSplitter()
        layout.addWidget(splitter, 1)
        self.navigation = QtWidgets.QListWidget()
        self.navigation.setMaximumWidth(200)
        for label, anchor in SECTIONS:
            item = QtWidgets.QListWidgetItem(label)
            item.setData(QtCore.Qt.UserRole, anchor)
            self.navigation.addItem(item)
        self.browser = QtWidgets.QTextBrowser()
        self.browser.setOpenLinks(False)
        self.browser.setOpenExternalLinks(False)
        splitter.addWidget(self.navigation)
        splitter.addWidget(self.browser)
        splitter.setStretchFactor(1, 1)
        self.browser.setSource(QtCore.QUrl.fromLocalFile(str(HERE / "resources" / "help.html")))
        self.navigation.currentItemChanged.connect(
            lambda current, _previous: self.go_to(current.data(QtCore.Qt.UserRole)) if current else None)
        self.browser.anchorClicked.connect(lambda url: self.go_to(url.fragment()))
        find.clicked.connect(self.find_next)
        self.search.returnPressed.connect(self.find_next)

    def go_to(self, anchor="start"):
        self.navigation.blockSignals(True)
        try:
            for index in range(self.navigation.count()):
                if self.navigation.item(index).data(QtCore.Qt.UserRole) == anchor:
                    self.navigation.setCurrentRow(index)
                    break
        finally:
            self.navigation.blockSignals(False)
        self.browser.scrollToAnchor(anchor)

    def find_next(self):
        text = self.search.text().strip()
        if text and not self.browser.find(text):
            self.browser.moveCursor(QtGui.QTextCursor.Start)
            self.browser.find(text)


def show_help(owner, anchor="start"):
    window = getattr(owner, "_tweaker_help", None)
    if window is None:
        window = HelpWindow(owner)
        owner._tweaker_help = window
    window.show()
    window.go_to(anchor)
    window.raise_()
    return window
