"""Dockable Animation Tweaker window. All scene work is delegated to the engine modules."""
import traceback
from functools import partial

from maya import cmds
from maya.app.general.mayaMixin import MayaQWidgetDockableMixin

from . import __version__, cache_versions, core, effects, engine, surface_handle, utilities
from .engine import TweakError
from .help_view import icon_path, show_help
from .qt_compat import QtCore, QtGui, QtWidgets

WINDOW_NAME = "ATKAnimationTweakerWindow"
WORKSPACE_NAME = WINDOW_NAME + "WorkspaceControl"

MODE_LABELS = (("Static (always on)", core.MODE_STATIC),
               ("Pulse (0-1-0 around frame)", core.MODE_PULSE),
               ("Sequence (pose to pose)", core.MODE_SEQUENCE))
MUTE_LABELS = (("Off: sculpt on top of every tweak", core.MUTE_NONE),
               ("Mute all tweaks", core.MUTE_ALL),
               ("Mute static and pulse tweaks", core.MUTE_STATIC),
               ("Mute sequence tweaks", core.MUTE_SEQUENCE),
               ("Mute this level only", core.MUTE_LEVEL))
EFFECTS = (("Smooth Motion", core.KIND_SMOOTH), ("Stick to Surface", core.KIND_STICK),
           ("Push Out", core.KIND_PUSH), ("Pin to World", core.KIND_PIN))


def _button(text, slot, tip=""):
    button = QtWidgets.QPushButton(text)
    # clicked() sends a 'checked' flag; the slots here take their own arguments.
    button.clicked.connect(lambda *_args: slot())
    if tip:
        button.setToolTip(tip)
    return button


def _row(*widgets):
    layout = QtWidgets.QHBoxLayout()
    layout.setContentsMargins(0, 0, 0, 0)
    for widget in widgets:
        if isinstance(widget, str):
            layout.addWidget(QtWidgets.QLabel(widget))
        elif widget is None:
            layout.addStretch(1)
        else:
            layout.addWidget(widget)
    holder = QtWidgets.QWidget()
    holder.setLayout(layout)
    return holder


def _spin(value, low, high, step=1.0, decimals=2):
    spin = QtWidgets.QDoubleSpinBox()
    spin.setRange(low, high)
    spin.setDecimals(decimals)
    spin.setSingleStep(step)
    spin.setValue(value)
    return spin


def _group(title):
    box = QtWidgets.QGroupBox(title)
    layout = QtWidgets.QVBoxLayout(box)
    layout.setSpacing(4)
    return box, layout


class WeightCell(QtWidgets.QWidget):
    """Slider + key button for one tweak row."""

    def __init__(self, panel, index, weight, keyed):
        super().__init__()
        self.panel, self.index = panel, index
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(2, 0, 2, 0)
        self.slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.slider.setRange(0, 100)
        self.slider.setValue(int(round(max(0.0, min(1.0, weight)) * 100)))
        self.slider.setToolTip("Weight on this frame: %.2f" % weight)
        self.slider.sliderReleased.connect(self.apply)
        key = QtWidgets.QToolButton()
        key.setText("Key" if not keyed else "Key*")
        key.setToolTip("Key this weight on the current frame" + (" (already animated)" if keyed else ""))
        key.clicked.connect(self.key)
        layout.addWidget(self.slider, 1)
        layout.addWidget(key)

    def value(self):
        return self.slider.value() / 100.0

    def apply(self):
        self.panel.run(engine.set_weight, self.panel.mesh(), self.index, self.value(), refresh=False)

    def key(self):
        self.panel.run(engine.key_weight, self.panel.mesh(), self.index, self.value())


class Panel(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        self.mesh_field = QtWidgets.QLineEdit()
        self.mesh_field.setReadOnly(True)
        self.mesh_field.setPlaceholderText("Pick a mesh")
        layout.addWidget(_row("Mesh", self.mesh_field,
                              _button("Use selected", self.use_selected, "Work on the selected mesh")))
        tabs = QtWidgets.QTabWidget()
        tabs.addTab(self._sculpt_tab(), "Sculpt")
        tabs.addTab(self._shape_tab(), "Shape")
        tabs.addTab(self._effects_tab(), "Effects")
        tabs.addTab(self._handle_tab(), "Handle")
        tabs.addTab(self._utilities_tab(), "Utilities")
        tabs.addTab(self._cache_tab(), "Cache")
        layout.addWidget(tabs, 1)
        self.status = QtWidgets.QLabel("Select a mesh and click Use selected.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        try:
            self.mesh_field.setText(engine.selected_mesh())
            self.refresh()
        except Exception:
            pass

    # -- plumbing -----------------------------------------------------------

    def mesh(self):
        text = self.mesh_field.text()
        if not text or not cmds.objExists(text):
            raise TweakError("Pick a mesh first (select it and click Use selected)")
        return text

    def run(self, fn, *args, **kwargs):
        refresh = kwargs.pop("refresh", True)
        message = kwargs.pop("message", None)
        try:
            result = fn(*args, **kwargs)
        except (TweakError, ValueError) as error:
            self.status.setText("<span style='color:#f0a35e'>%s</span>" % error)
            cmds.warning("Animation Tweaker: %s" % error)
            return None
        except Exception as error:   # keep the window usable, report the details
            traceback.print_exc()
            self.status.setText("<span style='color:#ef6464'>Error: %s (details in the Script "
                                "Editor)</span>" % error)
            return None
        if message:
            self.status.setText(message(result) if callable(message) else message)
        else:
            self.status.setText("Done: %s" % fn.__name__.replace("_", " "))
        if refresh:
            self.refresh()
        return result

    def use_selected(self):
        try:
            self.mesh_field.setText(engine.selected_mesh())
        except TweakError as error:
            self.status.setText(str(error))
            return
        self.refresh()

    def keying(self):
        return dict(mode=self.mode.currentData(), layer=self.level.text().strip() or "L1",
                    ramp_in=self.ramp_in.value(), ramp_out=self.ramp_out.value())

    # -- Sculpt tab ---------------------------------------------------------

    def _sculpt_tab(self):
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        box, inner = _group("Keying")
        self.mode = QtWidgets.QComboBox()
        for label, mode in MODE_LABELS:
            self.mode.addItem(label, mode)
        self.level = QtWidgets.QLineEdit("L1")
        self.level.setToolTip("Sequence level. Levels are independent pose-to-pose tracks.")
        self.level.setMaximumWidth(70)
        self.ramp_in = _spin(3, 0, 1000, 1, 1)
        self.ramp_out = _spin(3, 0, 1000, 1, 1)
        inner.addWidget(_row("Mode", self.mode))
        inner.addWidget(_row("Level", self.level, "Ramp in", self.ramp_in, "out", self.ramp_out))
        layout.addWidget(box)

        box, inner = _group("Sculpt")
        self.mute = QtWidgets.QComboBox()
        for label, mode in MUTE_LABELS:
            self.mute.addItem(label, mode)
        self.highlight = QtWidgets.QCheckBox("Highlight shader")
        self.highlight.setChecked(True)
        self.hide_original = QtWidgets.QCheckBox("Hide original")
        self.hide_original.setChecked(True)
        inner.addWidget(_row("Sculpt from zero", self.mute))
        inner.addWidget(_row(self.highlight, self.hide_original, None))
        inner.addWidget(_row(_button("Sculpt", self.start_sculpt, "Copy the mesh as it is on this frame"),
                             _button("Commit", self.commit, "Store the sculpt as a tweak"),
                             _button("Cancel", self.cancel, "Discard the sculpt and restore the mesh")))
        inner.addWidget(_row(_button("Blank pose", self.blank, "Empty pose on this frame (sequence level)"),
                             _button("Hold pose", self.hold, "Copy the previous pose on this level here")))
        layout.addWidget(box)

        box, inner = _group("Tweaks on this mesh")
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderLabels(["Tweak", "Kind", "Mode", "Frame", "Level", "Weight"])
        self.tree.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.tree.setRootIsDecorated(False)
        self.tree.setMinimumHeight(220)
        self.tree.header().setStretchLastSection(True)
        inner.addWidget(self.tree, 1)
        self.factor = _spin(1.25, -10, 10, 0.05)
        self.proxies = QtWidgets.QCheckBox("Proxy channels on mesh")
        self.proxies.setToolTip("Keyable copies of every tweak weight under a TWEAKS divider")
        self.proxies.toggled.connect(self.toggle_proxies)
        inner.addWidget(_row(_button("Refresh", self.refresh), _button("Refine", self.refine,
                             "Sculpt a correction and add it to the selected tweak"),
                             _button("Rename", self.rename), _button("Paint mask", self.paint)))
        inner.addWidget(_row(_button("Amplify ×", self.amplify, "Scale the selected tweaks' offsets"),
                             self.factor, _button("Delete", self.delete), None))
        inner.addWidget(self.proxies)
        layout.addWidget(box, 1)
        return page

    def selected_indices(self):
        return [item.data(0, QtCore.Qt.UserRole) for item in self.tree.selectedItems()]

    def refresh(self):
        self.tree.clear()
        text = self.mesh_field.text()
        if not text or not cmds.objExists(text):
            return
        try:
            rows = engine.list_tweaks(text)
            node = engine.find_tweak_node(text)
        except Exception:
            traceback.print_exc()
            return
        self.proxies.blockSignals(True)
        self.proxies.setChecked(bool(node) and engine.proxies_enabled(node))
        self.proxies.blockSignals(False)
        for row in rows:
            frame = "" if row["frame"] is None else "%g" % row["frame"]
            item = QtWidgets.QTreeWidgetItem([row["label"], row["kind"], row["mode"], frame,
                                              row["layer"], ""])
            item.setData(0, QtCore.Qt.UserRole, row["index"])
            item.setToolTip(0, "%s (weight[%d])" % (row["alias"], row["index"]))
            self.tree.addTopLevelItem(item)
            self.tree.setItemWidget(item, 5, WeightCell(self, row["index"], row["weight"], row["keyed"]))
        for column in range(5):
            self.tree.resizeColumnToContents(column)

    def start_sculpt(self):
        k = self.keying()
        self.run(engine.start_sculpt, self.mesh(), k["mode"], k["layer"], k["ramp_in"], k["ramp_out"],
                 self.mute.currentData(), self.highlight.isChecked(), self.hide_original.isChecked(),
                 message="Sculpt the blue copy with any tool, then click Commit.")

    def commit(self):
        self.run(engine.commit_sculpt, self.mesh_field.text() or None, message="Sculpt stored as a tweak.")

    def cancel(self):
        self.run(engine.cancel_sculpt, self.mesh_field.text() or None, message="Sculpt cancelled.")

    def blank(self):
        self.run(engine.blank_pose, self.mesh(), self.keying()["layer"])

    def hold(self):
        self.run(engine.hold_pose, self.mesh(), self.keying()["layer"])

    def refine(self):
        indices = self.selected_indices()
        if len(indices) != 1:
            self.status.setText("Select one tweak to refine")
            return
        self.run(engine.start_sculpt, self.mesh(), highlight=self.highlight.isChecked(),
                 hide_original=self.hide_original.isChecked(), refine=indices[0],
                 message="Sculpt the correction, then click Commit to add it to the tweak.")

    def amplify(self):
        for index in self.selected_indices():
            self.run(engine.scale_tweak, self.mesh(), index, self.factor.value(), refresh=False)
        self.refresh()

    def rename(self):
        indices = self.selected_indices()
        if len(indices) != 1:
            self.status.setText("Select one tweak to rename")
            return
        current = self.tree.selectedItems()[0].text(0)
        text, ok = QtWidgets.QInputDialog.getText(self, "Rename tweak", "Name", text=current)
        if ok and text.strip():
            self.run(engine.rename_tweak, self.mesh(), indices[0], text.strip())

    def paint(self):
        indices = self.selected_indices()
        if len(indices) != 1:
            self.status.setText("Select one tweak to paint")
            return
        self.run(engine.paint_mask, self.mesh(), indices[0], refresh=False)

    def delete(self):
        indices = self.selected_indices()
        if indices:
            self.run(engine.delete_tweaks, self.mesh(), indices)

    def toggle_proxies(self, enabled):
        self.run(engine.set_proxies, self.mesh(), enabled)

    # -- Shape tab ----------------------------------------------------------

    def _shape_tab(self):
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        note = QtWidgets.QLabel("Works on the current frame. Select vertices (soft selection "
                                "sets the falloff) to mask the effect. The result is stored as "
                                "a tweak with the Sculpt tab's keying mode.")
        note.setWordWrap(True)
        layout.addWidget(note)
        box, inner = _group("Inflate / Deflate")
        self.amount = _spin(0.1, 0.0, 1000, 0.01, 3)
        inner.addWidget(_row("Distance", self.amount,
                             _button("Inflate", partial(self.inflate, 1.0)),
                             _button("Deflate", partial(self.inflate, -1.0))))
        layout.addWidget(box)
        box, inner = _group("Relax")
        self.iterations = QtWidgets.QSpinBox()
        self.iterations.setRange(1, 200)
        self.iterations.setValue(5)
        self.strength = _spin(0.5, 0.0, 1.0, 0.05)
        inner.addWidget(_row("Iterations", self.iterations, "Strength", self.strength,
                             _button("Relax", self.relax)))
        layout.addWidget(box)
        layout.addStretch(1)
        return page

    def inflate(self, sign):
        k = self.keying()
        self.run(engine.inflate, self.mesh(), sign * self.amount.value(), k["mode"], k["layer"],
                 k["ramp_in"], k["ramp_out"])

    def relax(self):
        k = self.keying()
        self.run(engine.relax, self.mesh(), self.iterations.value(), self.strength.value(), k["mode"],
                 k["layer"], k["ramp_in"], k["ramp_out"])

    # -- Effects tab --------------------------------------------------------

    def _effects_tab(self):
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        note = QtWidgets.QLabel("Each effect bakes one sequence pose per frame on its own level. "
                                "Running it again replaces the previous result. The selected "
                                "vertices (with soft selection) are the mask.")
        note.setWordWrap(True)
        layout.addWidget(note)
        box, inner = _group("Frames")
        self.start = _spin(1, -100000, 100000, 1, 0)
        self.end = _spin(24, -100000, 100000, 1, 0)
        self.bind = _spin(1, -100000, 100000, 1, 0)
        inner.addWidget(_row("Start", self.start, "End", self.end,
                             _button("Playback range", self.use_playback)))
        inner.addWidget(_row("Bind frame", self.bind, _button("Current", self.use_current), None))
        layout.addWidget(box)
        box, inner = _group("Smooth Motion")
        self.sigma = _spin(2.0, 0.1, 50, 0.25)
        self.world = QtWidgets.QCheckBox("World space")
        self.world.setChecked(True)
        inner.addWidget(_row("Smoothing (frames)", self.sigma, self.world, _button("Smooth", self.smooth)))
        layout.addWidget(box)
        box, inner = _group("Driver surface")
        self.driver = QtWidgets.QLineEdit()
        self.driver.setReadOnly(True)
        self.offset = _spin(0.1, 0.0, 1000, 0.01, 3)
        inner.addWidget(_row("Driver", self.driver, _button("Use selected", self.use_driver)))
        inner.addWidget(_row(_button("Stick to surface", self.stick),
                             "Skin offset", self.offset, _button("Push out", self.push)))
        layout.addWidget(box)
        box, inner = _group("Pin")
        inner.addWidget(_row(_button("Pin to world", self.pin,
                                     "Hold the masked area where it was on the bind frame"), None))
        layout.addWidget(box)
        box, inner = _group("Remove")
        self.effect_kind = QtWidgets.QComboBox()
        for label, kind in EFFECTS:
            self.effect_kind.addItem(label, kind)
        inner.addWidget(_row(self.effect_kind, _button("Remove effect", self.remove_effect)))
        layout.addWidget(box)
        layout.addStretch(1)
        self.use_playback()
        return page

    def use_playback(self):
        try:
            self.start.setValue(cmds.playbackOptions(query=True, minTime=True))
            self.end.setValue(cmds.playbackOptions(query=True, maxTime=True))
            self.bind.setValue(cmds.playbackOptions(query=True, minTime=True))
        except Exception:
            pass

    def use_current(self):
        self.bind.setValue(cmds.currentTime(query=True))

    def use_driver(self):
        try:
            selection = cmds.ls(selection=True, long=True, objectsOnly=True) or []
            meshes = [engine.resolve_mesh(n)[0] for n in selection]
            others = [m for m in meshes if m != self.mesh_field.text()]
            self.driver.setText((others or meshes)[0])
        except (TweakError, IndexError):
            self.status.setText("Select the driver (collider) mesh")

    def _driver(self):
        if not self.driver.text():
            raise TweakError("Pick a driver mesh first")
        return self.driver.text()

    def smooth(self):
        self.run(effects.smooth_motion, self.mesh(), self.start.value(), self.end.value(),
                 self.sigma.value(), self.world.isChecked(),
                 message=lambda n: "Smooth Motion baked on %s frames." % n)

    def stick(self):
        self.run(lambda: effects.stick_to_surface(self.mesh(), self._driver(), self.start.value(),
                                                  self.end.value(), self.bind.value()),
                 message=lambda n: "Stick to Surface baked on %s frames." % n)

    def push(self):
        self.run(lambda: effects.push_out(self.mesh(), self._driver(), self.start.value(),
                                          self.end.value(), self.offset.value()),
                 message=lambda n: "Push Out baked on %s frames." % n)

    def pin(self):
        self.run(effects.pin_to_world, self.mesh(), self.start.value(), self.end.value(),
                 self.bind.value(), message=lambda n: "Pin to World baked on %s frames." % n)

    def remove_effect(self):
        self.run(effects.remove_effect, self.mesh(), self.effect_kind.currentData(),
                 message=lambda n: "Removed %s frame poses." % n)

    # -- Handle tab ---------------------------------------------------------

    def _handle_tab(self):
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        box, inner = _group("Create")
        self.handle_radius = _spin(0.0, 0.0, 100000, 0.1, 3)
        self.handle_radius.setToolTip("0 = 15% of the mesh size")
        inner.addWidget(_row("Radius", self.handle_radius,
                             _button("Create on selected vertex", self.create_handle)))
        layout.addWidget(box)
        box, inner = _group("Selected handle")
        self.falloff_mode = QtWidgets.QComboBox()
        self.falloff_mode.addItems(["Volume", "Surface"])
        self.falloff_shape = QtWidgets.QComboBox()
        self.falloff_shape.addItems(list(core.FALLOFF_NAMES))
        inner.addWidget(_row("Radius", _button("Set", self.set_radius), "Mode", self.falloff_mode,
                             _button("Set", self.set_mode)))
        inner.addWidget(_row("Falloff shape", self.falloff_shape, _button("Apply", self.apply_shape)))
        self.show_sphere = QtWidgets.QCheckBox("Show falloff sphere")
        self.show_sphere.setChecked(True)
        self.show_sphere.toggled.connect(self.toggle_sphere)
        inner.addWidget(_row(self.show_sphere, _button("Colour…", self.sphere_colour), None))
        self.world_orient = QtWidgets.QCheckBox("Orient to world")
        self.world_orient.toggled.connect(self.toggle_orient)
        inner.addWidget(_row(self.world_orient, _button("Aim at selected", self.aim),
                             _button("Clear aim", self.clear_aim)))
        inner.addWidget(_row(_button("Add geometry", self.add_geo), _button("Remove geometry", self.remove_geo),
                             _button("Delete handle", self.delete_handle)))
        layout.addWidget(box)
        note = QtWidgets.QLabel("Select the handle first, then (for Aim and geometry) the other objects.")
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch(1)
        return page

    def _handle(self):
        return surface_handle.selected_handle()

    def create_handle(self):
        radius = self.handle_radius.value() or None
        self.run(surface_handle.create_handle, None, radius, refresh=False)

    def set_radius(self):
        self.run(lambda: surface_handle.set_radius(self._handle(), self.handle_radius.value()), refresh=False)

    def set_mode(self):
        self.run(lambda: surface_handle.set_mode(self._handle(), self.falloff_mode.currentIndex() == 1),
                 refresh=False)

    def apply_shape(self):
        self.run(lambda: surface_handle.apply_falloff_curve(self._handle(), self.falloff_shape.currentText()),
                 refresh=False)

    def toggle_sphere(self, visible):
        self.run(lambda: surface_handle.show_falloff(self._handle(), visible), refresh=False)

    def sphere_colour(self):
        colour = QtWidgets.QColorDialog.getColor(QtGui.QColor("#f2bf40"), self, "Falloff colour")
        if colour.isValid():
            self.run(lambda: surface_handle.set_falloff_colour(self._handle(), colour.name()), refresh=False)

    def toggle_orient(self, enabled):
        self.run(lambda: surface_handle.orient_to_world(self._handle(), enabled), refresh=False)

    def aim(self):
        self.run(lambda: surface_handle.aim_at(self._handle()), refresh=False)

    def clear_aim(self):
        self.run(lambda: surface_handle.clear_aim(self._handle()), refresh=False)

    def add_geo(self):
        self.run(lambda: surface_handle.add_geometry(self._handle()), refresh=False)

    def remove_geo(self):
        self.run(lambda: surface_handle.remove_geometry(self._handle()), refresh=False)

    def delete_handle(self):
        self.run(lambda: surface_handle.delete_handle(self._handle()), refresh=False)

    # -- Utilities tab ------------------------------------------------------

    def _utilities_tab(self):
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        box, inner = _group("Bake over the playback range")
        self.card_size = _spin(1.0, 0.001, 1000, 0.1, 3)
        inner.addWidget(_row("Size", self.card_size,
                             _button("Locator on vertex", partial(self.follow, "locator")),
                             _button("Card on vertex", partial(self.follow, "card"))))
        inner.addWidget(_row(_button("Bake mesh transforms", partial(
            self.run, utilities.bake_transforms, refresh=False)), None))
        layout.addWidget(box)
        box, inner = _group("View")
        self.skip_ortho = QtWidgets.QCheckBox("Skip ortho cameras")
        self.skip_ortho.setChecked(True)
        inner.addWidget(_row(_button("Smooth preview", partial(
            self.run, utilities.toggle_smooth_preview, refresh=False),
            "Toggle smooth-mesh preview on the selected hierarchy"),
            _button("Next camera", self.next_camera), self.skip_ortho))
        layout.addWidget(box)
        box, inner = _group("Colour materials")
        swatches = QtWidgets.QHBoxLayout()
        for colour in core.PALETTE:
            swatch = QtWidgets.QToolButton()
            swatch.setFixedSize(22, 22)
            swatch.setStyleSheet("background:%s; border:1px solid #222;" % colour)
            swatch.setToolTip(colour)
            swatch.clicked.connect(partial(self.colour, colour))
            swatches.addWidget(swatch)
        random_button = QtWidgets.QToolButton()
        random_button.setText("?")
        random_button.setToolTip("Random colour")
        random_button.clicked.connect(partial(self.colour, None))
        swatches.addWidget(random_button)
        swatches.addStretch(1)
        inner.addLayout(swatches)
        layout.addWidget(box)
        box, inner = _group("Channels")
        inner.addWidget(_row(_button("Copy values", partial(
            self.run, utilities.copy_channels, refresh=False,
            message=lambda n: "Copied %s channel values." % n)),
            _button("Paste values", partial(self.run, utilities.paste_channels, refresh=False,
                                            message=lambda n: "Pasted %s channel values." % n)), None))
        layout.addWidget(box)
        box, inner = _group("Geometry")
        inner.addWidget(_row(_button("Extract faces (live copy)", partial(
            self.run, utilities.extract_faces, refresh=False)), None))
        layout.addWidget(box)
        layout.addStretch(1)
        return page

    def follow(self, kind):
        self.run(utilities.bake_followers, kind, self.card_size.value(), refresh=False)

    def next_camera(self):
        self.run(utilities.cycle_camera, self.skip_ortho.isChecked(), refresh=False,
                 message=lambda cam: "Looking through %s" % engine.short_name(cam))

    def colour(self, colour):
        self.run(utilities.apply_colour, colour, refresh=False,
                 message=lambda c: "Applied %s" % c)

    # -- Cache tab ----------------------------------------------------------

    def _cache_tab(self):
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        note = QtWidgets.QLabel("Export the polished meshes to Alembic, bring caches back as "
                                "versions, and attach the active version onto the originals.")
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addWidget(_row(_button("Export selected…", self.export_cache),
                              _button("Import version…", self.import_cache), None))
        self.versions = QtWidgets.QListWidget()
        layout.addWidget(self.versions, 1)
        layout.addWidget(_row(_button("Attach", self.attach), _button("Swap to selected", self.swap),
                              _button("Detach", partial(self.run, cache_versions.detach,
                                                        refresh=False)),
                              _button("Delete version", self.delete_version)))
        layout.addWidget(_row(_button("Refresh", self.refresh_versions), None))
        self.refresh_versions()
        return page

    def refresh_versions(self):
        self.versions.clear()
        try:
            for version in cache_versions.list_versions():
                item = QtWidgets.QListWidgetItem(("● " if version["active"] else "   ") + version["label"])
                item.setData(QtCore.Qt.UserRole, version["label"])
                item.setToolTip(version["path"])
                self.versions.addItem(item)
        except Exception:
            traceback.print_exc()

    def _version(self):
        item = self.versions.currentItem()
        if item is None:
            raise TweakError("Pick a version in the list")
        return item.data(QtCore.Qt.UserRole)

    def export_cache(self):
        path, _filter = QtWidgets.QFileDialog.getSaveFileName(self, "Export Alembic", "", "Alembic (*.abc)")
        if path:
            self.run(cache_versions.export_selected, path, refresh=False,
                     message="Exported %s" % path)

    def import_cache(self):
        path, _filter = QtWidgets.QFileDialog.getOpenFileName(self, "Import Alembic", "", "Alembic (*.abc)")
        if path:
            self.run(cache_versions.import_version, path, refresh=False)
            self.refresh_versions()

    def attach(self):
        self.run(lambda: cache_versions.attach(self._version_or_none()), refresh=False,
                 message=lambda n: "Attached the cache to %s meshes." % n)
        self.refresh_versions()

    def _version_or_none(self):
        item = self.versions.currentItem()
        return item.data(QtCore.Qt.UserRole) if item else None

    def swap(self):
        self.run(lambda: cache_versions.swap(self._version()), refresh=False)
        self.refresh_versions()

    def delete_version(self):
        self.run(lambda: cache_versions.delete_version(self._version()), refresh=False)
        self.refresh_versions()


def build_menu_bar(owner, panel):
    menu = QtWidgets.QMenuBar(owner)
    menu.setNativeMenuBar(False)
    file_menu = menu.addMenu("File")
    file_menu.addAction("Refresh", panel.refresh)
    file_menu.addAction("Cancel every open sculpt", lambda: panel.run(_cancel_all))
    file_menu.addSeparator()
    file_menu.addAction("Close", owner.close)
    help_menu = menu.addMenu("Help")
    help_menu.addAction("User guide", lambda: show_help(owner, "start"))
    help_menu.addAction("Keying modes", lambda: show_help(owner, "keying"))
    help_menu.addSeparator()
    help_menu.addAction("About Animation Tweaker", lambda: show_help(owner, "about"))
    return menu


def _cancel_all():
    for sculpt in list(engine.active_sessions()):
        engine.cancel_sculpt(sculpt)


class Window(MayaQWidgetDockableMixin, QtWidgets.QDialog):
    def __init__(self):
        super().__init__()
        self.setObjectName(WINDOW_NAME)
        self.setWindowTitle("Animation Tweaker %s" % __version__)
        self.setWindowIcon(QtGui.QIcon(str(icon_path())))
        self.resize(460, 780)
        layout = QtWidgets.QVBoxLayout(self)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        self.panel = Panel()
        layout.setMenuBar(build_menu_bar(self, self.panel))
        scroll.setWidget(self.panel)
        layout.addWidget(scroll)


_window = None


def _remove_stale():
    """Close windows left by an earlier import (ATK Reload Scripts purges modules)."""
    app = QtWidgets.QApplication.instance()
    for widget in (app.allWidgets() if app else []):
        try:
            if widget.objectName() == WINDOW_NAME:
                widget.close()
                widget.deleteLater()
        except RuntimeError:
            pass
    if cmds.workspaceControl(WORKSPACE_NAME, query=True, exists=True):
        cmds.deleteUI(WORKSPACE_NAME)


def show():
    global _window
    alive = _window is not None
    if alive:
        try:
            _window.objectName()
        except RuntimeError:      # the C++ widget was deleted (workspace closed)
            alive = False
    if not alive:
        _remove_stale()
        _window = Window()
    _window.show(dockable=True)
    _window.raise_()
    return _window


def close():
    global _window
    if _window is not None:
        try:
            _window.close()
            _window.deleteLater()
        except RuntimeError:
            pass
    _window = None
    if cmds.workspaceControl(WORKSPACE_NAME, query=True, exists=True):
        cmds.deleteUI(WORKSPACE_NAME)
