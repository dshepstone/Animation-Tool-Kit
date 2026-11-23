"""Dockable Animation Tweaker window. All scene work is delegated to the engine modules."""
import traceback
from functools import partial

from maya import cmds
from maya.app.general.mayaMixin import MayaQWidgetDockableMixin

from . import (__version__, cache_versions, core, effects, engine, sculpt_brushes,
               surface_handle, utilities)
from .engine import TweakError
from .help_view import icon_path, show_help
from .qt_compat import QtCore, QtGui, QtWidgets

WINDOW_NAME = "ATKAnimationTweakerWindow"
WORKSPACE_NAME = WINDOW_NAME + "WorkspaceControl"

MODE_LABELS = (("Static (always on)", core.MODE_STATIC),
               ("Pulse (0-1-0 around frame)", core.MODE_PULSE),
               ("Sequence (pose to pose)", core.MODE_SEQUENCE),
               ("Keyed by hand (one key at 1)", core.MODE_MANUAL))
MODE_SHORT = {core.MODE_STATIC: "static", core.MODE_PULSE: "pulse",
              core.MODE_SEQUENCE: "sequence", core.MODE_MANUAL: "keyed"}
# Channel Box colours: grey = not animated, salmon = animated, red = key on this frame.
KEY_COLOURS = {"none": "#6b6b6b", "animated": "#d9897a", "key": "#e04848"}
KEY_TIPS = {"none": "Not animated", "animated": "Animated (no key on this frame)",
            "key": "Key on this frame"}
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
    """Weight slider, value and a Channel Box style key button for one tweak."""

    def __init__(self, panel, row):
        super().__init__()
        self.panel, self.index = panel, row["index"]
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(4)
        self.slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.slider.setRange(0, 100)
        self.slider.setMinimumWidth(70)
        self.slider.valueChanged.connect(self._changed)
        self.label = QtWidgets.QLabel()
        self.label.setFixedWidth(36)
        self.label.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        self.key = QtWidgets.QToolButton()
        self.key.setText(u"\u25c6")
        self.key.setAutoRaise(True)
        self.key.setFixedWidth(24)
        self.key.clicked.connect(lambda *_a: self.panel.key_one(self.index, self.value()))
        layout.addWidget(self.slider, 1)
        layout.addWidget(self.label)
        layout.addWidget(self.key)
        self.update_from(row)

    def value(self):
        return self.slider.value() / 100.0

    def update_from(self, row):
        weight = max(0.0, min(1.0, row["weight"]))
        self.slider.blockSignals(True)
        self.slider.setValue(int(round(weight * 100)))
        self.slider.blockSignals(False)
        self.label.setText("%.2f" % weight)
        state = row.get("key_state", "animated" if row.get("keyed") else "none")
        self.key.setStyleSheet("QToolButton { color: %s; font-size: 14px; }" % KEY_COLOURS[state])
        keys = row.get("keys", 0)
        self.key.setToolTip("%s%s. Click to key this weight on the current frame." % (
            KEY_TIPS[state], " (%d keys)" % keys if keys else ""))

    def _changed(self, value):
        # Live preview while dragging; a keyed weight holds it until the frame changes.
        self.label.setText("%.2f" % (value / 100.0))
        try:
            engine.set_weight(self.panel.mesh(), self.index, value / 100.0)
        except Exception as error:   # keep dragging responsive; report once
            self.panel.status.setText(str(error))


class BrushValue(QtWidgets.QWidget):
    """Slider plus field for one sculpt brush setting (size or strength)."""

    STEPS = 10      # slider ticks per unit: 0-100 in steps of 0.1

    def __init__(self, label, setter, tip):
        super().__init__()
        self.setter = setter
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        caption = QtWidgets.QLabel(label)
        caption.setFixedWidth(52)
        self.slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.slider.setRange(0, int(sculpt_brushes.SLIDER_MAX * self.STEPS))
        self.field = _spin(0, 0, sculpt_brushes.FIELD_MAX, 0.1, 2)
        self.field.setFixedWidth(80)
        self.field.setKeyboardTracking(False)
        for widget in (caption, self.slider, self.field):
            widget.setToolTip(tip)
        self.slider.valueChanged.connect(self._slid)
        self.field.valueChanged.connect(self._typed)
        layout.addWidget(caption)
        layout.addWidget(self.slider, 1)
        layout.addWidget(self.field)

    def busy(self):
        return self.slider.isSliderDown() or self.field.hasFocus()

    def show_value(self, value):
        for widget, v in ((self.slider, int(round(min(value, sculpt_brushes.SLIDER_MAX) * self.STEPS))),
                          (self.field, value)):
            widget.blockSignals(True)
            widget.setValue(v)
            widget.blockSignals(False)

    def _apply(self, value):
        try:
            self.setter(value)
        except Exception as error:
            cmds.warning("Animation Tweaker: %s" % error)

    def _slid(self, ticks):
        value = ticks / float(self.STEPS)
        self.field.blockSignals(True)
        self.field.setValue(value)
        self.field.blockSignals(False)
        self._apply(value)

    def _typed(self, value):
        self.slider.blockSignals(True)
        self.slider.setValue(int(round(min(value, sculpt_brushes.SLIDER_MAX) * self.STEPS)))
        self.slider.blockSignals(False)
        self._apply(value)


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
        self.cells = {}
        self._time_job = None
        self.listen()
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
        inner.addWidget(_row("Mute while sculpting", self.mute))
        inner.addWidget(_row(self.highlight, self.hide_original, None))
        inner.addWidget(_row(_button("Sculpt", self.start_sculpt, "Copy the mesh as it is on this frame"),
                             _button("Commit", self.commit, "Store the sculpt as a tweak"),
                             _button("Cancel", self.cancel, "Discard the sculpt and restore the mesh")))
        inner.addWidget(_row(_button("Blank pose", self.blank, "Empty pose on this frame (sequence level)"),
                             _button("Hold pose", self.hold, "Copy the previous pose on this level here")))
        layout.addWidget(box)

        layout.addWidget(self._brush_shelf())

        box, inner = _group("Tweaks on this mesh")
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderLabels(["Tweak", "Kind", "Mode", "Frame", "Level", "Weight"])
        self.tree.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.tree.setRootIsDecorated(False)
        self.tree.setMinimumHeight(200)
        self.tree.header().setStretchLastSection(True)
        self.tree.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._tree_menu)
        inner.addWidget(self.tree, 1)
        self.factor = _spin(1.25, -10, 10, 0.05)
        self.proxies = QtWidgets.QCheckBox("Proxy channels on mesh")
        self.proxies.setToolTip("Keyable copies of every tweak weight under a TWEAKS divider")
        self.proxies.toggled.connect(self.toggle_proxies)
        inner.addWidget(_row(_button("Refresh", self.refresh), _button("Refine", self.refine,
                             "Sculpt a correction and add it to the selected tweak"),
                             _button("Rename", self.rename), _button("Paint mask", self.paint)))
        inner.addWidget(_row(_button("Amplify \u00d7", self.amplify, "Scale the selected tweaks' offsets"),
                             self.factor, _button("Delete", self.delete), None))
        inner.addWidget(self.proxies)
        layout.addWidget(box, 1)

        layout.addWidget(self._animate_box())
        return page

    # -- brush shelf ----------------------------------------------------------

    def _brush_shelf(self):
        """Maya's sculpt brushes as a compact icon shelf, grouped Shape / Detail / Mask."""
        box, inner = _group("Sculpt brushes")
        inner.setSpacing(2)
        self.brush_group = QtWidgets.QButtonGroup(box)
        self.brush_group.setExclusive(True)
        self.brush_buttons = {}
        for title, brushes in sculpt_brushes.GROUPS:
            row = QtWidgets.QHBoxLayout()
            row.setSpacing(2)
            caption = QtWidgets.QLabel(title)
            caption.setFixedWidth(42)
            caption.setStyleSheet("color: #9a9a9a; font-size: 10px;")
            row.addWidget(caption)
            for brush_id, label, _command, icon, tip in brushes:
                button = self._tool_button(label, icon, "<b>%s</b><br>%s" % (label, tip), checkable=True)
                button.clicked.connect(partial(self.pick_brush, brush_id))
                self.brush_group.addButton(button)
                self.brush_buttons[brush_id] = button
                row.addWidget(button)
            if title == "Mask":
                for action_id, label, _command, _icon, tip in sculpt_brushes.MASK_ACTIONS:
                    button = self._tool_button(label, "", tip)
                    button.clicked.connect(partial(self.brush_action, action_id))
                    row.addWidget(button)
                row.addSpacing(10)
                self.symmetry = self._tool_button("Sym X", "", "Mirror brush strokes across the "
                                                  "mesh's X axis (object space)", checkable=True)
                self.symmetry.toggled.connect(self.toggle_symmetry)
                row.addWidget(self.symmetry)
                row.addWidget(self._tool_button("Settings", "", "Brush size, strength and falloff "
                                                "(Tool Settings)", slot=self.brush_settings))
                row.addWidget(self._tool_button("Select", "", "Leave the brush (Select tool)",
                                                slot=self.leave_brush))
            row.addStretch(1)
            inner.addLayout(row)
        self.brush_size = BrushValue("Size", sculpt_brushes.set_brush_size,
                                     "Brush radius for the current brush (Maya keeps one per brush). "
                                     "Type past 100 for large meshes. Same as holding B and dragging. "
                                     "Enabled once a sculpt brush has been picked.")
        self.brush_strength = BrushValue("Strength", sculpt_brushes.set_brush_strength,
                                         "How strongly the current brush moves the surface. "
                                         "Same as holding M and dragging. "
                                         "Enabled once a sculpt brush has been picked.")
        inner.addWidget(self.brush_size)
        inner.addWidget(self.brush_strength)
        # Follow brush changes and B/M-drag in the viewport while the window is open.
        self._brush_timer = QtCore.QTimer(box)
        self._brush_timer.setInterval(400)
        self._brush_timer.timeout.connect(self.sync_brush_values)
        self._brush_timer.start()
        self.sync_brush_values()
        self.auto_brush = QtWidgets.QCheckBox("Pick up the last brush when a sculpt starts")
        self.auto_brush.setChecked(True)
        inner.addWidget(self.auto_brush)
        try:
            self.symmetry.blockSignals(True)
            self.symmetry.setChecked(sculpt_brushes.symmetry_enabled())
            self.symmetry.blockSignals(False)
        except Exception:
            pass
        return box

    def _tool_button(self, label, icon, tip, checkable=False, slot=None):
        button = QtWidgets.QToolButton()
        button.setToolTip(tip)
        button.setCheckable(checkable)
        button.setAutoRaise(True)
        qicon = QtGui.QIcon(":/" + icon) if icon else QtGui.QIcon()
        if not qicon.isNull() and qicon.availableSizes():
            button.setIcon(qicon)
            button.setIconSize(QtCore.QSize(26, 26))
            button.setFixedSize(32, 32)
        else:
            # Maya's icons are missing (batch mode): fall back to short text.
            button.setText(label if not icon else label[:4])
            button.setMinimumHeight(26)
        if slot:
            button.clicked.connect(lambda *_a: slot())
        return button

    def pick_brush(self, brush_id, *_args):
        mesh = self.mesh_field.text() or None
        sculpt = self.run(sculpt_brushes.activate, brush_id, mesh, refresh=False,
                          message=lambda target: "%s brush on %s" % (
                              sculpt_brushes.brush(brush_id)[1],
                              engine.short_name(target) if target else
                              "the selection (click Sculpt first to work on a copy)"))
        self.sync_brush_values()
        return sculpt

    def sync_brush_values(self):
        """Show the current brush's size and strength; disabled until a brush exists."""
        if not self.isVisible() and getattr(self, "_brush_synced", False):
            return
        try:
            values = sculpt_brushes.brush_values()
        except Exception:
            values = None
        self._brush_synced = True
        for widget, value in zip((self.brush_size, self.brush_strength), values or (None, None)):
            widget.setEnabled(values is not None)
            if values is not None and not widget.busy():
                widget.show_value(value)

    def brush_action(self, action_id, *_args):
        self.run(sculpt_brushes.run_action, action_id, refresh=False)

    def toggle_symmetry(self, enabled):
        self.run(sculpt_brushes.set_symmetry, enabled, refresh=False,
                 message="Symmetry %s" % ("on (object X)" if enabled else "off"))

    def brush_settings(self):
        self.run(sculpt_brushes.show_settings, refresh=False, message="Brush settings open")

    def leave_brush(self):
        checked = self.brush_group.checkedButton()
        if checked:
            self.brush_group.setExclusive(False)
            checked.setChecked(False)
            self.brush_group.setExclusive(True)
        self.run(sculpt_brushes.exit_brush, refresh=False, message="Select tool")

    # -- animate tweaks -------------------------------------------------------

    def _animate_box(self):
        box, inner = _group("Animate selected tweaks")
        inner.addWidget(_row(
            _button(u"\u25c0 Key", partial(self.jump, -1), "Previous key of the selected tweaks "
                    "(all tweaks when none are selected)"),
            _button("Key", self.key_selected, "Key the weight each selected tweak shows now"),
            _button("Key 0", partial(self.key_selected, 0.0), "Key the selected tweaks off"),
            _button("Key 1", partial(self.key_selected, 1.0), "Key the selected tweaks fully on"),
            _button("Remove", self.remove_keys, "Remove the selected tweaks' keys on this frame"),
            _button(u"Key \u25b6", partial(self.jump, 1), "Next key of the selected tweaks "
                    "(all tweaks when none are selected)")))
        inner.addWidget(_row(
            _button("Clear keys", self.clear_keys, "Delete all keys, holding the current weight"),
            _button("Graph Editor", self.graph_editor, "Show the selected tweaks' curves"),
            None))
        inner.addWidget(_row(
            "Re-key as",
            _button("Static", partial(self.set_mode, core.MODE_STATIC), "Always on, no keys"),
            _button("Pulse here", partial(self.set_mode, core.MODE_PULSE),
                    "0-1-0 around this frame, with the Ramp in/out above"),
            _button("Pose here", partial(self.set_mode, core.MODE_SEQUENCE),
                    "A sequence pose on this frame, on the Level above (one tweak)"),
            None))
        note = QtWidgets.QLabel(u"\u25c6 grey: not animated \u00b7 salmon: animated \u00b7 red: key "
                                u"on this frame. Keying by hand switches a tweak to <i>keyed</i>, so "
                                u"automatic pulse/sequence keys never overwrite yours.")
        note.setWordWrap(True)
        note.setStyleSheet("color: #9a9a9a; font-size: 10px;")
        inner.addWidget(note)
        return box

    def _need_selection(self, what):
        indices = self.selected_indices()
        if not indices:
            self.status.setText("Select tweaks in the list to %s" % what)
        return indices

    def key_one(self, index, value):
        self.run(engine.key_tweaks, self.mesh(), [index], value,
                 message="Keyed %.2f on frame %g" % (value, cmds.currentTime(query=True)))

    def key_selected(self, value=None, *_args):
        indices = self._need_selection("key them")
        if indices:
            self.run(engine.key_tweaks, self.mesh(), indices, value,
                     message=lambda n: "Keyed %d tweak%s on frame %g" % (
                         n, "" if n == 1 else "s", cmds.currentTime(query=True)))

    def remove_keys(self):
        indices = self._need_selection("remove their keys")
        if indices:
            self.run(engine.remove_tweak_keys, self.mesh(), indices,
                     message=lambda n: "Removed %d key%s on this frame" % (n, "" if n == 1 else "s"))

    def clear_keys(self):
        indices = self._need_selection("clear their keys")
        if indices:
            self.run(engine.clear_tweak_keys, self.mesh(), indices,
                     message="Keys cleared; weights held where they were")

    def set_mode(self, mode, *_args):
        indices = self._need_selection("re-key them")
        if indices:
            k = self.keying()
            self.run(engine.set_tweak_mode, self.mesh(), indices, mode, None, k["layer"],
                     k["ramp_in"], k["ramp_out"],
                     message="Re-keyed as %s" % MODE_SHORT.get(mode, mode))

    def jump(self, direction, *_args):
        self.run(engine.jump_to_key, self.mesh(), self.selected_indices(), direction,
                 refresh=False, message=lambda frame: "Frame %g" % frame)

    def graph_editor(self):
        indices = self.selected_indices()
        def show():
            node = engine.find_tweak_node(self.mesh())
            plugs = [engine.driver_plug(node, i) for i in indices] if node else []
            nodes = sorted({plug.split(".")[0] for plug in plugs}) or [self.mesh()]
            cmds.select(nodes, replace=True)
            cmds.GraphEditor()
        self.run(show, refresh=False, message="Graph Editor: pick the tweak channels on the left")

    def _tree_menu(self, point):
        if not self.tree.itemAt(point):
            return
        menu = QtWidgets.QMenu(self)
        # triggered() sends a 'checked' flag; call each slot without it.
        for item in (("Key", self.key_selected),
                            ("Key 0", partial(self.key_selected, 0.0)),
                            ("Key 1", partial(self.key_selected, 1.0)),
                            ("Remove key on this frame", self.remove_keys),
                            ("Clear keys", self.clear_keys),
                            None,
                            ("Re-key as static", partial(self.set_mode, core.MODE_STATIC)),
                            ("Re-key as pulse here", partial(self.set_mode, core.MODE_PULSE)),
                            ("Re-key as pose here", partial(self.set_mode, core.MODE_SEQUENCE)),
                            None,
                            ("Refine", self.refine), ("Rename", self.rename),
                            ("Paint mask", self.paint), ("Delete", self.delete)):
            if item is None:
                menu.addSeparator()
                continue
            label, slot = item
            action = menu.addAction(label)
            action.triggered.connect(lambda *_a, fn=slot: fn())
        menu.exec_(self.tree.viewport().mapToGlobal(point))

    def sync_keys(self):
        """On frame change: update weights and key colours without rebuilding the list."""
        try:
            text = self.mesh_field.text()
        except RuntimeError:          # the window is gone; stop listening
            self.shutdown()
            return
        if not self.cells or not text or not cmds.objExists(text):
            return
        try:
            rows = engine.list_tweaks(text, from_curves=True)
        except Exception:
            return
        if sorted(r["index"] for r in rows) != sorted(self.cells):
            self.refresh()
            return
        for row in rows:
            try:
                self.cells[row["index"]].update_from(row)
            except RuntimeError:
                self.refresh()
                return

    def listen(self):
        """Follow frame changes. Closing the window stops listening, but Maya's
        dockable control only hides it, so reopening calls this again."""
        if cmds.about(batch=True):         # scriptJobs need the interactive UI
            return
        try:
            if self._time_job is not None and cmds.scriptJob(exists=self._time_job):
                return
            self._time_job = cmds.scriptJob(event=["timeChanged", self.sync_keys])
        except Exception:
            traceback.print_exc()

    def showEvent(self, event):
        super().showEvent(event)
        self.listen()
        self.sync_keys()       # catch up with frame changes made while closed

    def shutdown(self):
        job, self._time_job = self._time_job, None
        if job is not None:
            try:
                if cmds.scriptJob(exists=job):
                    cmds.scriptJob(kill=job, force=True)
            except Exception:
                pass

    def selected_indices(self):
        return [item.data(0, QtCore.Qt.UserRole) for item in self.tree.selectedItems()]

    def refresh(self):
        self.cells = {}
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
        self.cells = {}
        for row in rows:
            frame = "" if row["frame"] is None else "%g" % row["frame"]
            layer = row["layer"] if row["mode"] == core.MODE_SEQUENCE else ""
            item = QtWidgets.QTreeWidgetItem([row["label"], row["kind"],
                                              MODE_SHORT.get(row["mode"], row["mode"]), frame, layer, ""])
            item.setData(0, QtCore.Qt.UserRole, row["index"])
            item.setToolTip(0, "%s (weight[%d])" % (row["alias"], row["index"]))
            self.tree.addTopLevelItem(item)
            cell = WeightCell(self, row)
            self.cells[row["index"]] = cell
            self.tree.setItemWidget(item, 5, cell)
        for column in range(5):
            self.tree.resizeColumnToContents(column)

    def start_sculpt(self):
        k = self.keying()
        sculpt = self.run(engine.start_sculpt, self.mesh(), k["mode"], k["layer"], k["ramp_in"],
                          k["ramp_out"], self.mute.currentData(), self.highlight.isChecked(),
                          self.hide_original.isChecked(),
                          message="Sculpt the copy with any brush, then click Commit.")
        if sculpt and self.auto_brush.isChecked():
            self._resume_brush()

    def _resume_brush(self):
        brush_id = sculpt_brushes.last_brush()
        if self.run(sculpt_brushes.activate, brush_id, self.mesh_field.text() or None,
                    refresh=False, message="%s brush on the sculpt copy. Commit when done." %
                    sculpt_brushes.brush(brush_id)[1]) is not None:
            button = self.brush_buttons.get(brush_id)
            if button:
                button.setChecked(True)

    def commit(self):
        if self.run(engine.commit_sculpt, self.mesh_field.text() or None,
                    message="Sculpt stored as a tweak.") is not None:
            self._drop_brush()

    def cancel(self):
        self.run(engine.cancel_sculpt, self.mesh_field.text() or None, message="Sculpt cancelled.")
        self._drop_brush()

    def _drop_brush(self):
        """After commit/cancel the copy is gone: return to the Select tool."""
        checked = self.brush_group.checkedButton()
        if checked:
            self.brush_group.setExclusive(False)
            checked.setChecked(False)
            self.brush_group.setExclusive(True)
            try:
                sculpt_brushes.exit_brush()
            except Exception:
                pass

    def blank(self):
        self.run(engine.blank_pose, self.mesh(), self.keying()["layer"])

    def hold(self):
        self.run(engine.hold_pose, self.mesh(), self.keying()["layer"])

    def refine(self):
        indices = self.selected_indices()
        if len(indices) != 1:
            self.status.setText("Select one tweak to refine")
            return
        sculpt = self.run(engine.start_sculpt, self.mesh(), highlight=self.highlight.isChecked(),
                          hide_original=self.hide_original.isChecked(), refine=indices[0],
                          message="Sculpt the correction, then click Commit to add it to the tweak.")
        if sculpt and self.auto_brush.isChecked():
            self._resume_brush()

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

    def closeEvent(self, event):
        self.panel.shutdown()
        super().closeEvent(event)

    def dockCloseEventTriggered(self):
        self.panel.shutdown()


_window = None


def _dispose(widget):
    """Hide, close and delete a window. The dockable mixin's close() may only
    close the workspace control, and it overrides hide(), so hide the
    dialog itself through QWidget."""
    panel = getattr(widget, "panel", None)
    if panel is not None:
        panel.shutdown()
    QtWidgets.QWidget.hide(widget)
    widget.close()
    widget.deleteLater()


def _remove_stale():
    """Close windows left by an earlier import (ATK Reload Scripts purges modules)."""
    app = QtWidgets.QApplication.instance()
    for widget in (app.allWidgets() if app else []):
        try:
            if widget.objectName() == WINDOW_NAME:
                _dispose(widget)
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
    _window.panel.listen()
    _window.panel.sync_keys()
    return _window


def close():
    global _window
    if _window is not None:
        try:
            _dispose(_window)
        except RuntimeError:
            pass
    _window = None
    if cmds.workspaceControl(WORKSPACE_NAME, query=True, exists=True):
        cmds.deleteUI(WORKSPACE_NAME)
