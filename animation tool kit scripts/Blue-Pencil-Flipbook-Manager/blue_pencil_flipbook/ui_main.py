"""Main dockable PySide2/PySide6 UI for the Blue Pencil Flipbook Manager."""

from __future__ import annotations

try:
    from maya import cmds
    from maya.app.general.mayaMixin import MayaQWidgetDockableMixin
except Exception:
    cmds = None
    MayaQWidgetDockableMixin = object

from .qt_compat import QtCore, QtGui, QtWidgets

from .controller import FlipbookController
from . import help_docs, hotkeys, theme, maya_blue_pencil_api as bp
from .ui_thumbnail import ThumbnailCard

WORKSPACE_CONTROL = "BluePencilFlipbookManagerWorkspaceControl"


if QtWidgets:
    class BluePencilFlipbookWindow(MayaQWidgetDockableMixin, QtWidgets.QMainWindow):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.setObjectName("BluePencilFlipbookManager")
            self.setWindowTitle("Blue Pencil Flipbook Manager")
            self.controller = FlipbookController()
            self._draw_color = QtGui.QColor(theme.DRAW_DEFAULT)
            self._active_tool = "pencil"
            self._loading = False
            # Load the Blue Pencil plugin up front so its commands and layers are
            # available as soon as the tool opens.
            bp.ensure_blue_pencil_plugin()
            self._build_ui()
            self.refresh_all()
            # Apply the default light-blue stroke color so drawing starts with it.
            bp.set_draw_color(self._draw_color.red(), self._draw_color.green(), self._draw_color.blue())

        # -- construction ----------------------------------------------------
        def _build_ui(self):
            theme.apply(self)
            self._build_menus()
            central = QtWidgets.QWidget()
            self.setCentralWidget(central)
            outer = QtWidgets.QVBoxLayout(central)
            outer.setContentsMargins(0, 0, 0, 0)
            outer.setSpacing(0)

            scroll = QtWidgets.QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
            content = QtWidgets.QWidget()
            self.content_layout = QtWidgets.QVBoxLayout(content)
            self.content_layout.setContentsMargins(10, 10, 10, 10)
            self.content_layout.setSpacing(10)
            scroll.setWidget(content)
            outer.addWidget(scroll)

            self._build_header()
            self._build_tools()
            self._build_frames()
            self._build_actions()
            self._build_thumbnails()
            self.content_layout.addStretch()

            # A plain label in our own layout is used as the status line. A
            # QMainWindow.statusBar() inside a Maya workspace control can have
            # its C++ object deleted out from under us during docking, which
            # raised "Internal C++ object (QStatusBar) already deleted".
            self.status_label = QtWidgets.QLabel()
            self.status_label.setProperty("role", "status")
            self.status_label.setContentsMargins(10, 4, 10, 6)
            outer.addWidget(self.status_label)

        def _build_menus(self):
            bar = self.menuBar()
            file_menu = bar.addMenu("File")
            self._menu_action(file_menu, "Refresh", self.refresh_all)
            file_menu.addSeparator()
            self._menu_action(file_menu, "Export Session…", self.export_session)
            self._menu_action(file_menu, "Import Session…", self.import_session)
            view = bar.addMenu("View")
            self._menu_action(view, "Regenerate All Thumbnails", self.regenerate_all_thumbnails)
            frames = bar.addMenu("Frames")
            for label, kind in [("Mark as Key", "KEY"), ("Mark as Breakdown", "BREAKDOWN"), ("Mark as Inbetween", "INBETWEEN")]:
                self._menu_action(frames, label, lambda k=kind: self.mark_current(k))
            tools = bar.addMenu("Tools")
            self._menu_action(tools, "Reset Tool", bp.reset_tool)
            self._menu_action(tools, "Refresh Timeline", bp.refresh_timeline_display)
            hk = bar.addMenu("Hotkeys")
            self._menu_action(hk, "Edit Hotkeys…", self.edit_hotkeys)
            hk.addSeparator()
            self._menu_action(hk, "Create Default Hotkeys", hotkeys.create_default_hotkeys)
            self._menu_action(hk, "Reset Default Hotkeys", hotkeys.reset_default_hotkeys)
            self._menu_action(hk, "Remove Hotkeys", hotkeys.remove_hotkeys)
            help_menu = bar.addMenu("Help")
            for text, anchor in [("How to Use the Flipbook Manager", "use"), ("Drawing Tools", "tools"), ("Frame Types", "types"), ("Export & Import Sessions", "sessions"), ("Playback Filters", "playback"), ("Hotkeys", "hotkeys"), ("About", "about")]:
                self._menu_action(help_menu, text, lambda a=anchor: help_docs.show_help(self, a))

        def _menu_action(self, menu, text, callback):
            # QAction.triggered passes a `checked` bool; swallow it so zero-arg
            # callbacks (bp.reset_tool, etc.) actually run instead of raising.
            return menu.addAction(text, lambda *args, cb=callback: cb())

        def edit_hotkeys(self):
            from . import ui_hotkeys
            return ui_hotkeys.show_editor(self)

        def _build_header(self):
            header = QtWidgets.QWidget()
            header.setProperty("role", "header")
            row = QtWidgets.QHBoxLayout(header)
            row.setContentsMargins(12, 10, 12, 10)
            row.setSpacing(10)

            titles = QtWidgets.QVBoxLayout()
            titles.setSpacing(0)
            title = QtWidgets.QLabel("Blue Pencil Flipbook")
            title.setProperty("role", "title")
            subtitle = QtWidgets.QLabel("Draw · Mark · Flip through your review drawings")
            subtitle.setProperty("role", "subtitle")
            titles.addWidget(title)
            titles.addWidget(subtitle)
            row.addLayout(titles)
            row.addStretch()

            row.addWidget(self._caption("Camera"))
            self.camera_combo = QtWidgets.QComboBox()
            self.camera_combo.setMinimumWidth(120)
            self.camera_combo.currentIndexChanged.connect(self._on_camera_changed)
            row.addWidget(self.camera_combo)

            row.addWidget(self._caption("Layer"))
            self.layer_combo = QtWidgets.QComboBox()
            self.layer_combo.setMinimumWidth(120)
            self.layer_combo.currentIndexChanged.connect(self._on_layer_changed)
            row.addWidget(self.layer_combo)

            refresh = self._button("↻  Refresh", self.refresh_all)
            refresh.setProperty("role", "accent")
            refresh.setToolTip("Reload cameras, layers and thumbnails")
            row.addWidget(refresh)

            self.content_layout.addWidget(header)

        def _build_tools(self):
            group = QtWidgets.QGroupBox("Drawing Tools")
            vbox = QtWidgets.QVBoxLayout(group)
            vbox.setSpacing(8)
            self.content_layout.addWidget(group)

            grid = QtWidgets.QGridLayout()
            grid.setSpacing(6)
            vbox.addLayout(grid)

            self.tool_group = QtWidgets.QButtonGroup(self)
            self.tool_group.setExclusive(True)
            tools = [
                ("✎  Draw", bp.draw_context, "Enter Blue Pencil draw mode", "draw"),
                ("⇆  Transform", bp.transform_tool, "Transform / move strokes", "transform"),
                ("Pencil", bp.pencil_tool, "Pencil tool", "pencil"),
                ("Brush", bp.brush_tool, "Brush tool", "brush"),
                ("Eraser", bp.eraser_tool, "Eraser tool", "eraser"),
                ("Text", bp.text_tool, "Text tool", "text"),
                ("Line", bp.line_tool, "Line tool", "line"),
                ("Arrow", bp.arrow_tool, "Arrow tool", "arrow"),
                ("Ellipse", bp.ellipse_tool, "Ellipse tool", "ellipse"),
                ("Rectangle", bp.rectangle_tool, "Rectangle tool", "rectangle"),
            ]
            for i, (label, callback, tip, key) in enumerate(tools):
                btn = QtWidgets.QPushButton(label)
                btn.setCheckable(True)
                btn.setToolTip(tip)
                btn.clicked.connect(lambda checked=False, cb=callback, k=key: self._activate_tool(k, cb))
                self.tool_group.addButton(btn)
                grid.addWidget(btn, i // 5, i % 5)

            # Color + brush settings row.
            settings = QtWidgets.QHBoxLayout()
            settings.setSpacing(10)
            vbox.addLayout(settings)

            settings.addWidget(self._caption("Color"))
            self.color_btn = QtWidgets.QPushButton()
            self.color_btn.setFixedSize(34, 24)
            self.color_btn.setToolTip("Choose stroke color")
            self.color_btn.clicked.connect(self.choose_color)
            self._update_color_swatch()
            settings.addWidget(self.color_btn)

            settings.addSpacing(6)
            settings.addWidget(self._caption("Size"))
            self.size_slider, self.size_spin = self._slider_spin(1, 100, 5, self._on_size_changed)
            settings.addWidget(self.size_slider, 2)
            settings.addWidget(self.size_spin)

            settings.addSpacing(6)
            settings.addWidget(self._caption("Opacity"))
            self.opacity_slider, self.opacity_spin = self._slider_spin(0, 100, 100, self._on_opacity_changed, suffix="%")
            settings.addWidget(self.opacity_slider, 2)
            settings.addWidget(self.opacity_spin)

            reset = self._button("Reset Tool", bp.reset_tool)
            reset.setToolTip("Reset the active Blue Pencil tool to defaults")
            settings.addWidget(reset)

        def _build_frames(self):
            group = QtWidgets.QGroupBox("Frame Types · Playback")
            vbox = QtWidgets.QVBoxLayout(group)
            vbox.setSpacing(8)
            self.content_layout.addWidget(group)

            marks = QtWidgets.QHBoxLayout()
            marks.setSpacing(6)
            vbox.addLayout(marks)
            for text, kind, color in [("● Mark Key", "KEY", theme.KEY_COLOR), ("● Mark Breakdown", "BREAKDOWN", theme.BREAKDOWN_COLOR), ("● Mark Inbetween", "INBETWEEN", theme.INBETWEEN_COLOR)]:
                btn = self._button(text, lambda k=kind: self.mark_current(k))
                btn.setToolTip("Mark the current frame as {0}".format(kind.title()))
                # Tint only the glyph/label color (avoids the Qt box-model quirk
                # where a partial border spec drops border-radius on the button).
                btn.setStyleSheet("QPushButton {{ color: {0}; }}".format(color))
                marks.addWidget(btn)
            marks.addStretch()
            self.isolate_check = QtWidgets.QCheckBox("Isolate on white")
            self.isolate_check.setChecked(True)
            self.isolate_check.setToolTip(
                "Capture the thumbnail with a white background and scene geometry\n"
                "hidden, so the drawing is clearly visible. Uncheck to capture the\n"
                "drawing over the scene as shown in the viewport."
            )
            marks.addWidget(self.isolate_check)

            transport = QtWidgets.QHBoxLayout()
            transport.setSpacing(6)
            vbox.addLayout(transport)

            transport.addWidget(self._caption("Filter"))
            self.filter_combo = QtWidgets.QComboBox()
            self.filter_combo.addItems(["Keys Only", "Keys + Breakdowns", "All Drawings"])
            self.filter_combo.setCurrentText("All Drawings")
            self.filter_combo.setToolTip("Which frame types to include during playback")
            transport.addWidget(self.filter_combo)

            transport.addWidget(self._caption("FPS"))
            self.fps_combo = QtWidgets.QComboBox()
            self.fps_combo.setEditable(True)
            self.fps_combo.setInsertPolicy(QtWidgets.QComboBox.NoInsert)
            self.fps_combo.addItems(["12", "24"])
            self.fps_combo.setValidator(QtGui.QIntValidator(1, 120, self.fps_combo))
            self.fps_combo.setMinimumWidth(56)
            self.fps_combo.lineEdit().setAlignment(QtCore.Qt.AlignCenter)
            self.fps_combo.setCurrentText("24")
            self.fps_combo.setToolTip("Flipbook playback rate — pick 12/24 or type any value (1-120)")
            transport.addWidget(self.fps_combo)

            self.loop_check = QtWidgets.QCheckBox("Loop")
            self.loop_check.setChecked(True)
            transport.addWidget(self.loop_check)

            transport.addStretch()

            prev_btn = self._button("⏮", self.previous_drawing)
            prev_btn.setProperty("role", "transport")
            prev_btn.setToolTip("Previous tracked drawing")
            self.play_btn = self._button("▶", self.play_pause)
            self.play_btn.setProperty("role", "transport")
            self.play_btn.setToolTip("Play / pause filtered flipbook")
            stop_btn = self._button("■", self._stop)
            stop_btn.setProperty("role", "transport")
            stop_btn.setToolTip("Stop playback")
            next_btn = self._button("⏭", self.next_drawing)
            next_btn.setProperty("role", "transport")
            next_btn.setToolTip("Next tracked drawing")
            for b in (prev_btn, self.play_btn, stop_btn, next_btn):
                transport.addWidget(b)

        def _build_actions(self):
            group = QtWidgets.QGroupBox("Frame Actions")
            grid = QtWidgets.QGridLayout(group)
            grid.setSpacing(6)
            self.content_layout.addWidget(group)
            actions = [
                ("Insert Frame", bp.insert_frame, "Insert a new blank Blue Pencil frame at the current time"),
                ("Duplicate", bp.duplicate_frame, "Duplicate the previous drawing onto the current frame"),
                ("Delete Frame", self.delete_current_frame, "Delete the Blue Pencil frame at the current time (also removes its tracked thumbnail)"),
                ("Clear Frame", bp.clear_frame, "Erase all strokes on the current frame"),
                ("Cut", bp.cut_frame, "Cut the current frame's drawing to the clipboard"),
                ("Copy", bp.copy_frame, "Copy the current frame's drawing to the clipboard"),
                ("Paste", bp.paste_frame, "Paste the clipboard drawing onto the current frame"),
                ("Step Back", bp.step_back, "Move to the previous Blue Pencil drawing"),
                ("Step Forward", bp.step_forward, "Move to the next Blue Pencil drawing"),
                ("Retime…", self.retime_frame, "Shift the current drawing by a number of frames"),
                ("Import Frames", self.import_session,
                 "Import a saved session — restores the Blue Pencil drawings, frame types and thumbnails from an exported session folder"),
                ("Export Frames", self.export_session,
                 "Export the current session — saves the Blue Pencil drawings, frame types and thumbnails to a session folder you can re-import later"),
            ]
            for i, (label, callback, tip) in enumerate(actions):
                button = self._button(label, callback)
                button.setToolTip(tip)
                grid.addWidget(button, i // 4, i % 4)

        def _build_thumbnails(self):
            group = QtWidgets.QGroupBox("Tracked Drawings")
            vbox = QtWidgets.QVBoxLayout(group)
            self.content_layout.addWidget(group)
            self.thumb_scroll = QtWidgets.QScrollArea()
            self.thumb_scroll.setWidgetResizable(True)
            self.thumb_scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
            self.thumb_scroll.setMinimumHeight(170)
            self.thumb_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
            self.thumb_scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
            self.thumb_container = QtWidgets.QWidget()
            self.thumb_layout = QtWidgets.QHBoxLayout(self.thumb_container)
            self.thumb_layout.setSpacing(8)
            self.thumb_layout.setContentsMargins(2, 2, 2, 2)
            self.empty_label = QtWidgets.QLabel("No tracked drawings yet — mark the current frame as Key, Breakdown or Inbetween.")
            self.empty_label.setProperty("role", "sectionCaption")
            self.empty_label.setAlignment(QtCore.Qt.AlignCenter)
            self.thumb_layout.addWidget(self.empty_label)
            self.thumb_layout.addStretch()
            self.thumb_scroll.setWidget(self.thumb_container)
            vbox.addWidget(self.thumb_scroll)

        # -- small widget helpers -------------------------------------------
        def _caption(self, text):
            label = QtWidgets.QLabel(text)
            label.setProperty("role", "sectionCaption")
            return label

        def _button(self, text, callback):
            button = QtWidgets.QPushButton(text)
            button.clicked.connect(lambda checked=False, cb=callback: cb())
            return button

        def _slider_spin(self, minimum, maximum, value, on_change, suffix=""):
            slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
            slider.setRange(minimum, maximum)
            slider.setValue(value)
            slider.setMinimumWidth(70)
            spin = QtWidgets.QSpinBox()
            spin.setRange(minimum, maximum)
            spin.setValue(value)
            if suffix:
                spin.setSuffix(suffix)
            slider.valueChanged.connect(spin.setValue)
            spin.valueChanged.connect(slider.setValue)
            spin.valueChanged.connect(on_change)
            return slider, spin

        # -- state / refresh -------------------------------------------------
        def current_camera(self):
            return self.camera_combo.currentText()

        def current_layer(self):
            return self.layer_combo.currentText()

        def refresh_all(self):
            self._loading = True
            try:
                # Prefer the camera of the viewport in focus, falling back to the
                # current selection, so tracking follows where the user is working.
                current_cam = bp.active_viewport_camera() or self.current_camera()
                self.camera_combo.clear()
                self.camera_combo.addItems(self.controller.cameras())
                self._select_camera(current_cam)
                self._reload_layers()
            finally:
                self._loading = False
            self.refresh_thumbnails()

        def _select_camera(self, camera):
            """Select ``camera`` in the dropdown, adding it if it isn't listed."""
            if not camera:
                return
            idx = self.camera_combo.findText(camera)
            if idx < 0:
                self.camera_combo.addItem(camera)
                idx = self.camera_combo.findText(camera)
            if idx >= 0:
                self.camera_combo.setCurrentIndex(idx)

        def sync_camera_to_viewport(self):
            """Point the camera dropdown at the currently focused viewport."""
            camera = bp.active_viewport_camera()
            if not camera or camera == self.current_camera():
                return
            self._loading = True
            try:
                self._select_camera(camera)
                self._reload_layers()
            finally:
                self._loading = False

        def _reload_layers(self):
            current_layer = self.layer_combo.currentText()
            self.layer_combo.blockSignals(True)
            self.layer_combo.clear()
            self.layer_combo.addItems(self.controller.layers(self.current_camera()))
            if current_layer:
                idx = self.layer_combo.findText(current_layer)
                if idx >= 0:
                    self.layer_combo.setCurrentIndex(idx)
            self.layer_combo.blockSignals(False)

        def _on_camera_changed(self, *_):
            if self._loading:
                return
            self._reload_layers()
            self.refresh_thumbnails()

        def _on_layer_changed(self, *_):
            if self._loading:
                return
            self.refresh_thumbnails()

        def refresh_thumbnails(self):
            while self.thumb_layout.count() > 2:  # keep empty label + stretch
                item = self.thumb_layout.takeAt(0)
                widget = item.widget()
                if widget and widget is not self.empty_label:
                    widget.deleteLater()
            entries = self.controller.frames(self.current_camera(), self.current_layer())
            self.empty_label.setVisible(not entries)
            for entry in entries:
                card = ThumbnailCard(entry)
                card.clicked.connect(self.show_preview)
                card.action_requested.connect(self.thumbnail_action)
                self.thumb_layout.insertWidget(self.thumb_layout.count() - 2, card)
            self._update_status(entries)

        def _update_status(self, entries=None):
            if entries is None:
                entries = self.controller.frames(self.current_camera(), self.current_layer())
            counts = {"KEY": 0, "BREAKDOWN": 0, "INBETWEEN": 0}
            for entry in entries:
                counts[entry.get("type", "INBETWEEN")] = counts.get(entry.get("type", "INBETWEEN"), 0) + 1
            self.status_label.setText(
                "{total} drawings   •   {k} keys   •   {b} breakdowns   •   {i} inbetweens".format(
                    total=len(entries), k=counts["KEY"], b=counts["BREAKDOWN"], i=counts["INBETWEEN"]
                )
            )

        # -- actions ---------------------------------------------------------
        def _update_color_swatch(self):
            c = self._draw_color
            self.color_btn.setStyleSheet(
                "QPushButton {{ background: {0}; border: 1px solid {1}; border-radius: 5px; }}".format(
                    c.name(), theme.BORDER
                )
            )

        def choose_color(self):
            color = QtWidgets.QColorDialog.getColor(self._draw_color, self, "Blue Pencil Color")
            if color.isValid():
                self._draw_color = color
                self._update_color_swatch()
                bp.set_draw_color(color.red(), color.green(), color.blue())

        def _activate_tool(self, key, callback):
            self._active_tool = key
            callback()
            # Push the current size/opacity onto the newly activated tool so the
            # sliders and the tool stay in sync (pencil/brush only).
            self._apply_size_opacity()

        def _apply_size_opacity(self):
            bp.set_tool_size_opacity(self._active_tool, self.size_spin.value(), self.opacity_spin.value())

        def _on_size_changed(self, value):
            if not self._loading:
                self._apply_size_opacity()

        def _on_opacity_changed(self, value):
            if not self._loading:
                self._apply_size_opacity()

        def mark_current(self, kind):
            # Follow the focused viewport so the mark + thumbnail use that camera.
            self.sync_camera_to_viewport()
            self.controller.mark_current(kind, self.current_camera(), self.current_layer(), isolate=self._isolate())
            self.refresh_thumbnails()

        def _isolate(self):
            return self.isolate_check.isChecked()

        def previous_drawing(self):
            self.controller.player.previous(self.current_camera(), self.current_layer(), self.filter_combo.currentText())

        def next_drawing(self):
            self.controller.player.next(self.current_camera(), self.current_layer(), self.filter_combo.currentText())

        def _fps(self):
            try:
                return int(self.fps_combo.currentText())
            except (TypeError, ValueError):
                return 24

        def play_pause(self):
            player = self.controller.player
            if player.timer and player.timer.isActive():
                player.pause()
                self.play_btn.setText("▶")
            else:
                player.play(self.current_camera(), self.current_layer(), self.filter_combo.currentText(), self._fps(), self.loop_check.isChecked())
                self.play_btn.setText("‖")

        def _stop(self):
            self.controller.player.stop()
            self.play_btn.setText("▶")

        def show_preview(self, entry):
            from . import ui_preview
            dialog = ui_preview.ThumbnailPreview(entry, self)
            dialog.go_to_frame_requested.connect(self.controller.go_to_frame)
            dialog.show()
            return dialog

        def delete_current_frame(self):
            # Delete the Blue Pencil frame at the current time and, if that frame
            # is tracked, drop its metadata + cached thumbnail and refresh cards.
            bp.delete_frame()
            entry = self.controller.entry_at(self.current_camera(), self.current_layer())
            if entry:
                self.controller.delete_metadata(entry)
            self.refresh_thumbnails()

        def retime_frame(self):
            value, ok = QtWidgets.QInputDialog.getInt(self, "Retime Frame", "Offset in frames (negative moves earlier):", 1, -1000, 1000, 1)
            if ok:
                bp.retime_frame(value)

        def regenerate_all_thumbnails(self):
            self.controller.regenerate_all_thumbnails(self.current_camera(), self.current_layer(), isolate=self._isolate())
            self.refresh_thumbnails()

        def export_session(self):
            dest = QtWidgets.QFileDialog.getExistingDirectory(self, "Export Session To Folder")
            if not dest:
                return
            try:
                path = self.controller.export_session(dest)
            except Exception as exc:
                QtWidgets.QMessageBox.warning(self, "Export Failed", "Could not export session:\n{0}".format(exc))
                return
            note = ""
            if not bp.has_blue_pencil_nodes():
                note = ("\n\nNote: no Blue Pencil drawings were found in the scene, so only the "
                        "frame metadata and thumbnails were exported.")
            QtWidgets.QMessageBox.information(self, "Session Exported", "Session exported to:\n{0}{1}".format(path, note))

        def import_session(self):
            folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Import Session Folder")
            if not folder:
                return
            import os
            if not os.path.exists(os.path.join(folder, "session.json")):
                QtWidgets.QMessageBox.warning(self, "Import Failed", "No session.json found in:\n{0}".format(folder))
                return
            box = QtWidgets.QMessageBox(self)
            box.setWindowTitle("Import Session")
            box.setText("Import tracked drawings into this scene?")
            box.setInformativeText("Replace clears the current tracked drawings; Merge keeps them and adds the imported ones.")
            replace_btn = box.addButton("Replace", QtWidgets.QMessageBox.AcceptRole)
            merge_btn = box.addButton("Merge", QtWidgets.QMessageBox.ActionRole)
            box.addButton("Cancel", QtWidgets.QMessageBox.RejectRole)
            box.exec_() if hasattr(box, "exec_") else box.exec()
            clicked = box.clickedButton()
            if clicked not in (replace_btn, merge_btn):
                return
            try:
                count = self.controller.import_session(folder, replace=(clicked is replace_btn))
            except Exception as exc:
                QtWidgets.QMessageBox.warning(self, "Import Failed", "Could not import session:\n{0}".format(exc))
                return
            self.refresh_all()
            QtWidgets.QMessageBox.information(self, "Session Imported", "Imported {0} tracked drawing(s).".format(count))

        def thumbnail_action(self, action, entry):
            if action == "goto":
                self.controller.go_to_frame(entry)
            elif action.startswith("mark_"):
                self.controller.set_frame_type(entry, {"mark_key": "KEY", "mark_breakdown": "BREAKDOWN", "mark_inbetween": "INBETWEEN"}[action])
            elif action == "duplicate":
                bp.duplicate_frame()
            elif action == "delete":
                bp.delete_frame()
                self.controller.delete_metadata(entry)
            elif action == "regenerate":
                self.controller.regenerate_thumbnail(entry, isolate=self._isolate())
            self.refresh_thumbnails()


def show():
    if QtWidgets is None:
        raise RuntimeError("PySide2 or PySide6 is required inside Maya to show the Blue Pencil Flipbook Manager.")
    if cmds and cmds.workspaceControl(WORKSPACE_CONTROL, exists=True):
        cmds.deleteUI(WORKSPACE_CONTROL)
    window = BluePencilFlipbookWindow()
    window.show(dockable=True, floating=False, area="right", allowedArea=["right", "left"], retain=False)
    return window
