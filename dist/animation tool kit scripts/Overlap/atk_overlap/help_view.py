"""Offline HTML documentation in a lightweight Maya-compatible Qt window."""
from pathlib import Path
from .qt_compat import QtCore, QtGui, QtWidgets
from .shelf import icon_path


class HelpWindow(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Overlap Help')
        self.setWindowIcon(QtGui.QIcon(str(icon_path())))
        self.resize(900, 720)
        self.setMinimumSize(620, 420)
        layout = QtWidgets.QVBoxLayout(self)
        search_row = QtWidgets.QHBoxLayout()
        layout.addLayout(search_row)
        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText('Find a setting or phrase…')
        find = QtWidgets.QPushButton('Find next')
        search_row.addWidget(self.search)
        search_row.addWidget(find)
        splitter = QtWidgets.QSplitter()
        layout.addWidget(splitter)
        self.navigation = QtWidgets.QListWidget()
        self.navigation.setMaximumWidth(185)
        for label, anchor in (('Getting started', 'start'), ('Controls and setup', 'setup'),
                              ('Spring settings', 'spring'), ('Endpoint', 'endpoint'),
                              ('Preview and baking', 'baking'), ('Suggested settings', 'examples'),
                              ('Troubleshooting', 'troubleshooting'), ('About / licence', 'about')):
            item = QtWidgets.QListWidgetItem(label)
            item.setData(QtCore.Qt.UserRole, anchor)
            self.navigation.addItem(item)
        self.browser = QtWidgets.QTextBrowser()
        self.browser.setOpenLinks(False)
        self.browser.setOpenExternalLinks(False)
        splitter.addWidget(self.navigation)
        splitter.addWidget(self.browser)
        splitter.setStretchFactor(1, 1)
        self.browser.setSource(QtCore.QUrl.fromLocalFile(str(
            Path(__file__).resolve().parent / 'resources' / 'help.html')))
        self.navigation.currentItemChanged.connect(lambda current, previous: self.go_to(
            current.data(QtCore.Qt.UserRole)) if current else None)
        self.browser.anchorClicked.connect(lambda url: self.go_to(url.fragment()))
        find.clicked.connect(self.find_next)
        self.search.returnPressed.connect(self.find_next)

    def go_to(self, anchor='start'):
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


def show_help(owner, anchor='start'):
    window = getattr(owner, '_overlap_help', None)
    if window is None:
        window = HelpWindow(owner)
        owner._overlap_help = window
    window.show()
    window.go_to(anchor)
    window.raise_()
    return window
