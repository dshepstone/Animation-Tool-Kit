"""Standalone Maya window. ATK can embed Panel or call the Session API."""
from dataclasses import asdict
from maya import cmds
from maya.app.general.mayaMixin import MayaQWidgetDockableMixin
from .qt_compat import QtCore, QtWidgets, QtGui
from .settings import Settings
from .maya_engine import Session, Cancelled
from . import __version__
from .bakes import list_bakes, delete_bake
from .shelf import add_to_shelf, icon_path
from .help_view import show_help


def build_menu_bar(owner, panel):
    """Shared by the dockable window and UI validation harness."""
    menu = QtWidgets.QMenuBar(owner)
    menu.setNativeMenuBar(False)
    file_menu = menu.addMenu('File')
    file_menu.addAction('Add to current shelf', lambda: panel.run(panel.add_to_shelf))
    file_menu.addSeparator()
    file_menu.addAction('Load preset…', lambda: panel.run(panel.load_preset))
    file_menu.addAction('Save preset…', lambda: panel.run(panel.save_preset))
    file_menu.addSeparator()
    file_menu.addAction('Close', owner.close)
    help_menu = menu.addMenu('Help')
    help_menu.addAction('User guide', lambda: show_help(owner, 'start'))
    help_menu.addAction('Suggested settings & examples', lambda: show_help(owner, 'examples'))
    help_menu.addSeparator()
    help_menu.addAction('About Overlap', lambda: show_help(owner, 'about'))
    return menu


class BakeLayerCombo(QtWidgets.QComboBox):
    def __init__(self, refresh):
        super().__init__()
        self.refresh = refresh

    def showPopup(self):
        self.refresh()
        super().showPopup()


class Panel(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.session = None
        self.setMinimumWidth(370)
        layout = QtWidgets.QVBoxLayout(self)
        title = QtWidgets.QLabel("OVERLAP")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #79d6be; padding: 8px 0;")
        layout.addWidget(title)
        layout.addWidget(QtWidgets.QLabel("Spring overlap for animated controls"))
        self.controls = QtWidgets.QListWidget()
        self.controls.setMinimumHeight(80)
        self.controls.setMaximumHeight(120)
        layout.addWidget(self.controls)
        row = QtWidgets.QHBoxLayout()
        layout.addLayout(row)
        for label, action, key in (("Load selected", self.load_selection, "load"),
                                   ("Up", lambda: self.move_control(-1), "up"),
                                   ("Down", lambda: self.move_control(1), "down")):
            button = QtWidgets.QPushButton(label)
            button.clicked.connect(action)
            row.addWidget(button)
        layout.addWidget(QtWidgets.QLabel("List order: root to tip. Independent controls are also supported."))
        form = QtWidgets.QFormLayout()
        layout.addLayout(form)
        self.mode = QtWidgets.QComboBox()
        self.mode.addItems(["rotation", "translation"])
        form.addRow("Mode", self.mode)
        channel_row = QtWidgets.QHBoxLayout()
        self.channel_checks = {}
        for axis in "XYZ":
            check = QtWidgets.QCheckBox("Rotate " + axis)
            check.setChecked(True)
            self.channel_checks[axis] = check
            channel_row.addWidget(check)
        form.addRow("Apply overlap to", channel_row)
        self.mode.currentTextChanged.connect(self.update_channel_labels)
        self.start = QtWidgets.QSpinBox()
        self.end = QtWidgets.QSpinBox()
        for widget in (self.start, self.end):
            widget.setRange(-1000000, 1000000)
        self.start.setValue(int(cmds.playbackOptions(query=True, minTime=True)))
        self.end.setValue(int(cmds.playbackOptions(query=True, maxTime=True)))
        range_row = QtWidgets.QHBoxLayout()
        range_row.addWidget(self.start)
        range_row.addWidget(self.end)
        form.addRow("Start / end", range_row)
        self.fields = {}
        defaults = Settings()
        for name, label, low, high, decimals in (
                ("frequency", "Stiffness (Hz)", .05, 30, 2),
                ("damping", "Damping ratio", 0, 3, 2),
                ("strength", "Effect strength", 0, 1, 2),
                ("substeps", "Minimum substeps", 1, 128, 0),
                ("preroll", "Preroll frames", 0, 1000, 0),
                ("length", "Fallback tip length (scene units)", .001, 100000, 3)):
            field = QtWidgets.QDoubleSpinBox() if decimals else QtWidgets.QSpinBox()
            field.setRange(low, high)
            if decimals:
                field.setDecimals(decimals)
                field.setSingleStep(.1)
            field.setValue(getattr(defaults, name))
            self.fields[name] = field
            form.addRow(label, field)
        self.axis = QtWidgets.QComboBox()
        self.axis.addItems(["+X", "-X", "+Y", "-Y", "+Z", "-Z"])
        self.tip_mode = QtWidgets.QComboBox()
        self.tip_mode.addItems(["Auto: continue chain", "Manual: axis + length"])
        form.addRow("Endpoint direction", self.tip_mode)
        form.addRow("Fallback tip axis", self.axis)
        tip = QtWidgets.QPushButton("Create / replace endpoint locator")
        tip.clicked.connect(lambda: self.run(self.create_tip))
        layout.addWidget(tip)
        self.refresh = QtWidgets.QPushButton("1. Refresh source + preview")
        self.refresh.clicked.connect(lambda: self.run(lambda: self.make_preview(True)))
        layout.addWidget(self.refresh)
        self.preview_button = QtWidgets.QPushButton("2. Update preview from cached source")
        self.preview_button.clicked.connect(lambda: self.run(lambda: self.make_preview(False)))
        layout.addWidget(self.preview_button)
        self.optimize_bake = QtWidgets.QCheckBox("Optimize bake (reduce unnecessary keys)")
        layout.addWidget(self.optimize_bake)
        bake_form = QtWidgets.QFormLayout()
        layout.addLayout(bake_form)
        self.key_tolerance = QtWidgets.QDoubleSpinBox()
        self.key_tolerance.setRange(0, 100000)
        self.key_tolerance.setDecimals(4)
        self.key_tolerance.setSingleStep(.05)
        self.key_tolerance.setValue(defaults.key_tolerance)
        self.key_tolerance.setEnabled(False)
        self.key_tolerance_label = QtWidgets.QLabel("Bake tolerance (degrees)")
        bake_form.addRow(self.key_tolerance_label, self.key_tolerance)
        self.optimize_bake.toggled.connect(self.key_tolerance.setEnabled)
        self.key_tolerance.setToolTip("Maximum error per output channel. Lower = more keys. "
                                     "Endpoints and swing peaks are retained. Linear tangents preserve the error bound.")
        self.bake_button = QtWidgets.QPushButton("3. Bake to new animation layer")
        self.bake_button.setStyleSheet("background: #285c51; padding: 8px; font-weight: bold;")
        self.bake_button.clicked.connect(lambda: self.run(self.bake))
        layout.addWidget(self.bake_button)
        bake_row = QtWidgets.QHBoxLayout()
        layout.addLayout(bake_row)
        bake_row.addWidget(QtWidgets.QLabel('Bake layer'))
        self.bake_layers = BakeLayerCombo(self.refresh_bake_layers)
        self.bake_layers.setMinimumContentsLength(12)
        self.bake_layers.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.delete_bake_button = QtWidgets.QPushButton('Delete bake')
        self.delete_bake_button.clicked.connect(lambda: self.run(self.delete_selected_bake))
        bake_row.addWidget(self.bake_layers, 1)
        bake_row.addWidget(self.delete_bake_button)
        self.refresh_bake_layers()
        clear = QtWidgets.QPushButton("Clear session helpers")
        clear.clicked.connect(lambda: self.run(self.clear))
        layout.addWidget(clear)
        self.status = QtWidgets.QLabel("Load transform controls to begin.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        note = QtWidgets.QLabel("After editing source keys, refresh source. Preview locators do not drive the rig.\n"
                               "v{} supports offset pivots; unit scale and zero rotate axis required.".format(__version__))
        note.setWordWrap(True)
        note.setStyleSheet("color: #aaaaaa; font-size: 11px;")
        layout.addWidget(note)
        layout.addStretch()

    def settings(self):
        return Settings(mode=self.mode.currentText(), axis=self.axis.currentText(),
                        channels="".join(a for a, check in self.channel_checks.items() if check.isChecked()),
                        tip_mode="chain" if self.tip_mode.currentIndex() == 0 else "axis",
                        optimize_bake=self.optimize_bake.isChecked(), key_tolerance=self.key_tolerance.value(),
                        **{key: widget.value() for key, widget in self.fields.items()})

    def update_channel_labels(self):
        prefix = "Rotate " if self.mode.currentText() == "rotation" else "Translate "
        for axis, check in self.channel_checks.items():
            check.setText(prefix + axis)
        self.key_tolerance_label.setText("Bake tolerance (degrees)" if self.mode.currentText() == "rotation"
                                         else "Bake tolerance (scene units)")

    def names(self):
        return [self.controls.item(i).data(QtCore.Qt.UserRole) or self.controls.item(i).text()
                for i in range(self.controls.count())]

    def load_selection(self):
        self.run(self._load_selection)

    def _load_selection(self):
        names = cmds.ls(selection=True, long=True, type="transform") or []
        if not names:
            raise ValueError("Select transform controls in the viewport or Outliner")
        self.load_controls(names)

    def load_controls(self, names):
        """Load named transforms from ATK or a rig setup script."""
        resolved = []
        for name in names:
            found = cmds.ls(name, long=True, type='transform') or []
            if len(found) != 1:
                raise ValueError('Control must resolve uniquely: ' + name)
            if found[0] not in resolved:
                resolved.append(found[0])
        self.clear()
        self.controls.clear()
        # DAG depth keeps ancestors ahead of selected descendants. Short labels
        # remain readable on production rigs; tooltips retain full DAG paths.
        for node in sorted(resolved, key=lambda n: n.count("|")):
            item = QtWidgets.QListWidgetItem(node.split("|")[-1])
            item.setData(QtCore.Qt.UserRole, node)
            item.setToolTip(node)
            self.controls.addItem(item)
        self.status.setText("Loaded {} controls. Check root-to-tip order.".format(len(resolved)))

    def move_control(self, delta):
        row = self.controls.currentRow()
        target = row + delta
        if row >= 0 and 0 <= target < self.controls.count():
            self.controls.insertItem(target, self.controls.takeItem(row))
            self.controls.setCurrentRow(target)

    def get_session(self):
        if self.session and self.session.controls != self.names():
            self.clear()
        if self.session is None:
            self.session = Session(self.names(), self.settings())
        self.session.settings = self.settings()
        return self.session

    def create_tip(self):
        session = self.get_session()
        node = session.create_tip()
        session.samples, session.results = [], []
        cmds.select(node, replace=True)
        self.status.setText("Endpoint placed. Check it follows the final segment, then refresh source.")

    def make_preview(self, refresh):
        session = self.get_session()
        with self.progress() as report:
            if refresh:
                session.sample(self.start.value(), self.end.value(), report)
            elif (not session.samples or session.start != self.start.value() or
                  session.end != self.end.value()):
                raise ValueError("Frame range changed or source missing: refresh source first")
            session.solve(report)
            session.preview(report)
        self.status.setText("Locator preview ready. Scrub freely; the rig moves after Bake.")

    def bake(self):
        session = self.get_session()
        if not session.samples or (session.start, session.end) != (self.start.value(), self.end.value()):
            raise ValueError("Refresh source and preview for this range first")
        with self.progress() as report:
            layer = session.bake(report)
        stats = session.last_bake_stats
        self.refresh_bake_layers(layer)
        self.status.setText("Baked to {}. Keys: {} → {}. Mute the layer to compare.".format(
            layer, stats["before"], stats["after"]))
        # Reusing a baked source cache can unintentionally overwrite later edits.
        session.samples, session.results = [], []

    def refresh_bake_layers(self, preferred=None):
        selected = preferred or self.bake_layers.currentData()
        self.bake_layers.clear()
        for layer in list_bakes():
            self.bake_layers.addItem(layer, layer)
        if self.bake_layers.count() == 0:
            self.bake_layers.addItem('No bake layers', None)
        else:
            index = self.bake_layers.findData(selected)
            if index >= 0:
                self.bake_layers.setCurrentIndex(index)
        self.delete_bake_button.setEnabled(self.bake_layers.currentData() is not None)

    def delete_selected_bake(self):
        layer = self.bake_layers.currentData()
        delete_bake(layer)
        if self.session:
            self.session.samples, self.session.results = [], []
            self.session.last_bake_stats = None
        self.refresh_bake_layers()
        self.status.setText('Deleted {}. Refresh source, then bake a replacement. Undo restores it.'.format(layer))

    def add_to_shelf(self):
        add_to_shelf()
        self.status.setText('Overlap added to the current shelf with its 32 × 32 icon.')

    def clear(self):
        if self.session:
            self.session.cleanup()
            self.session = None
        self.status.setText("Session helpers cleared. Baked layers retained.")

    def save_preset(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save Overlap preset", "", "JSON (*.json)")
        if path:
            if not path.lower().endswith(".json"):
                path += ".json"
            self.settings().save(path)
            self.status.setText("Preset saved.")

    def load_preset(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Load Overlap preset", "", "JSON (*.json)")
        if path:
            self.apply_settings(Settings.load(path))
            self.status.setText("Preset loaded. Refresh source to apply endpoint changes.")

    def apply_settings(self, settings):
        """Apply validated settings from a preset or an earlier tool window."""
        data = asdict(settings)
        self.mode.setCurrentText(data["mode"])
        self.axis.setCurrentText(data["axis"])
        self.tip_mode.setCurrentIndex(0 if data["tip_mode"] == "chain" else 1)
        self.optimize_bake.setChecked(data["optimize_bake"])
        self.key_tolerance.setValue(data["key_tolerance"])
        for axis, check in self.channel_checks.items():
            check.setChecked(axis in data["channels"])
        for name, widget in self.fields.items():
            widget.setValue(data[name])

    def run(self, operation):
        try:
            operation()
        except Cancelled:
            self.status.setText("Cancelled. Incomplete output was removed.")
        except Exception as error:
            self.status.setText(str(error))
            cmds.warning("Overlap: " + str(error))

    from contextlib import contextmanager

    @contextmanager
    def progress(self):
        dialog = QtWidgets.QProgressDialog("Overlap", "Cancel", 0, 100, self)
        dialog.setWindowModality(QtCore.Qt.WindowModal)
        dialog.setMinimumDuration(0)
        dialog.setAutoClose(False)
        dialog.show()

        def report(fraction, label):
            dialog.setLabelText(label)
            dialog.setValue(int(fraction * 100))
            # Process only this progress dialog's events; parent is modal-disabled.
            QtWidgets.QApplication.processEvents()
            if dialog.wasCanceled():
                raise Cancelled("Cancelled by animator")
        try:
            yield report
        finally:
            dialog.close()
            dialog.deleteLater()


class Window(MayaQWidgetDockableMixin, QtWidgets.QDialog):
    def __init__(self):
        super().__init__()
        self.setObjectName("ATKOverlapWindow")
        self.setWindowTitle("Overlap {}".format(__version__))
        self.setWindowIcon(QtGui.QIcon(str(icon_path())))
        self.resize(440, 840)
        layout = QtWidgets.QVBoxLayout(self)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        self.panel = Panel()
        self.menu_bar = build_menu_bar(self, self.panel)
        layout.setMenuBar(self.menu_bar)
        scroll.setWidget(self.panel)
        layout.addWidget(scroll)

    def closeEvent(self, event):
        self.panel.run(self.panel.clear)
        super().closeEvent(event)

    def dockCloseEventTriggered(self):
        self.panel.run(self.panel.clear)


_window = None


def show():
    global _window
    if _window is None:
        # ATK Reload Scripts purges modules, while existing Qt windows may still
        # be alive. Replace only this bundle's previous window on the next launch.
        for widget in QtWidgets.QApplication.allWidgets():
            if widget.objectName() == "ATKOverlapWindow":
                widget.close()
                widget.deleteLater()
        workspace = "ATKOverlapWindowWorkspaceControl"
        if cmds.workspaceControl(workspace, query=True, exists=True):
            cmds.deleteUI(workspace)
        _window = Window()
    _window.show(dockable=True)
    _window.raise_()
    return _window
