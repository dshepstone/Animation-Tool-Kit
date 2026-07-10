"""Hotkey editor for the Blue Pencil Flipbook Manager.

Mirrors the working Transform Reset Tool setup: a writable hotkey set is
selected (or created) first, each action gets a QKeySequenceEdit capture
field, and Apply pushes the bindings through Maya's runtime-command /
nameCommand / hotkey chain and saves the prefs.
"""

from __future__ import annotations

from .qt_compat import QtCore, QtGui, QtWidgets

from . import hotkeys, theme

try:
    from maya import cmds
except Exception:
    cmds = None


def _maya_main_window():
    try:
        import maya.OpenMayaUI as omui
        try:
            from shiboken6 import wrapInstance
        except ImportError:
            from shiboken2 import wrapInstance
        pointer = omui.MQtUtil.mainWindow()
        if pointer:
            return wrapInstance(int(pointer), QtWidgets.QWidget)
    except Exception:
        pass
    return None


# ── Qt key-to-Maya mapping ───────────────────────────────────────────────────

_QT_KEY_TO_MAYA = {}


def _enum_value(enum):
    return enum.value if hasattr(enum, "value") else int(enum)


def _build_key_map():
    """Populate the Qt-key-to-Maya-string mapping (lazy init)."""
    if _QT_KEY_TO_MAYA:
        return
    qt = QtCore.Qt
    for i in range(1, 13):
        _QT_KEY_TO_MAYA[_enum_value(getattr(qt, "Key_F{0}".format(i)))] = "F{0}".format(i)
    extras = {
        qt.Key_Space: "Space", qt.Key_Return: "Return", qt.Key_Enter: "Return",
        qt.Key_Tab: "Tab", qt.Key_Backspace: "Backspace", qt.Key_Delete: "Delete",
        qt.Key_Home: "Home", qt.Key_End: "End",
        qt.Key_Left: "Left", qt.Key_Right: "Right",
        qt.Key_Up: "Up", qt.Key_Down: "Down",
        qt.Key_PageUp: "Page_Up", qt.Key_PageDown: "Page_Down",
        qt.Key_Insert: "Insert",
    }
    for qt_key, maya_str in extras.items():
        _QT_KEY_TO_MAYA[_enum_value(qt_key)] = maya_str


def _parse_key_sequence(seq):
    """Parse a QKeySequence into (maya_key, ctrl, alt, shift) or None."""
    _build_key_map()
    if seq.count() == 0:
        return None
    combo = seq[0]
    if hasattr(combo, "key"):
        # Qt6: QKeyCombination
        key_val = _enum_value(combo.key())
        mods_val = _enum_value(combo.keyboardModifiers())
    else:
        # Qt5: int of key | modifiers
        combo = int(combo)
        mask = _enum_value(QtCore.Qt.KeyboardModifierMask)
        mods_val = combo & mask
        key_val = combo & ~mask
    maya_key = _QT_KEY_TO_MAYA.get(key_val)
    if maya_key is None and 0x21 <= key_val <= 0x7E:
        # Qt key codes for printable ASCII match the uppercase character.
        maya_key = chr(key_val).lower()
    if maya_key is None:
        return None
    ctrl = bool(mods_val & _enum_value(QtCore.Qt.ControlModifier))
    alt = bool(mods_val & _enum_value(QtCore.Qt.AltModifier))
    shift = bool(mods_val & _enum_value(QtCore.Qt.ShiftModifier))
    return maya_key, ctrl, alt, shift


def _sequence_from_binding(binding):
    if not (binding.get("key") or "").strip():
        return QtGui.QKeySequence()
    try:
        return QtGui.QKeySequence.fromString(hotkeys.display_string(binding))
    except Exception:
        return QtGui.QKeySequence()


if QtWidgets is not None:

    class _HotkeySetSelectDialog(QtWidgets.QDialog):
        """Modal dialog for selecting a writable hotkey set via dropdown."""

        def __init__(self, custom_sets, parent=None):
            super().__init__(parent)
            self.setWindowTitle("Select Hotkey Set")
            self.setWindowFlags(
                QtCore.Qt.Window
                | QtCore.Qt.WindowTitleHint
                | QtCore.Qt.WindowCloseButtonHint
            )
            self.setFixedWidth(360)
            theme.apply(self)
            self._selected_set = None

            layout = QtWidgets.QVBoxLayout(self)
            layout.setContentsMargins(16, 14, 16, 16)
            layout.setSpacing(12)

            msg = QtWidgets.QLabel(
                "The default ‘Maya_Default’ hotkey set is locked.\n"
                "Choose a custom hotkey set for editing, or create a new one."
            )
            msg.setWordWrap(True)
            layout.addWidget(msg)

            self._combo = QtWidgets.QComboBox()
            for name in custom_sets:
                self._combo.addItem(name)
            self._combo.addItem(hotkeys.CREATE_NEW_SET_LABEL)
            layout.addWidget(self._combo)

            btn_row = QtWidgets.QHBoxLayout()
            btn_row.addStretch()
            btn_ok = QtWidgets.QPushButton("OK")
            btn_ok.setProperty("role", "accent")
            btn_ok.clicked.connect(self._on_ok)
            btn_row.addWidget(btn_ok)
            btn_cancel = QtWidgets.QPushButton("Cancel")
            btn_cancel.clicked.connect(self.reject)
            btn_row.addWidget(btn_cancel)
            layout.addLayout(btn_row)

        def _on_ok(self):
            self._selected_set = self._combo.currentText()
            self.accept()

        def selected_set(self):
            return self._selected_set


    def select_hotkey_set(custom_sets, parent=None):
        """Modal picker used by hotkeys.ensure_writable_hotkey_set().

        Returns a set name, hotkeys.CREATE_NEW_SET_LABEL, or None (cancelled).
        """
        dialog = _HotkeySetSelectDialog(custom_sets, parent or _maya_main_window())
        accepted = QtWidgets.QDialog.Accepted
        result = dialog.exec_() if hasattr(dialog, "exec_") else dialog.exec()
        if result != accepted:
            return None
        return dialog.selected_set()


    class HotkeyEditor(QtWidgets.QDialog):
        """Per-action hotkey editor: click a field, press the combination.

        Apply binds through Maya's runtime-command / nameCommand / hotkey
        chain on the active writable hotkey set and saves the prefs.
        """

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setWindowTitle("Blue Pencil Flipbook — Hotkeys")
            self.setModal(True)
            self.resize(560, 520)
            theme.apply(self)
            self._key_edits = {}
            self._build_ui()
            self._load(hotkeys.load_bindings())

        def _build_ui(self):
            layout = QtWidgets.QVBoxLayout(self)
            layout.setContentsMargins(12, 12, 12, 12)
            layout.setSpacing(10)

            # Hotkey set selector — bindings land in this set.
            set_row = QtWidgets.QHBoxLayout()
            set_row.setSpacing(8)
            set_label = QtWidgets.QLabel("Hotkey Set:")
            set_label.setProperty("role", "sectionCaption")
            set_row.addWidget(set_label)
            self._set_combo = QtWidgets.QComboBox()
            self._set_combo.activated.connect(self._on_set_changed)
            set_row.addWidget(self._set_combo, 1)
            btn_refresh = QtWidgets.QPushButton("Refresh")
            btn_refresh.setToolTip("Refresh the hotkey set list")
            btn_refresh.clicked.connect(self._rebuild_set_combo)
            set_row.addWidget(btn_refresh)
            layout.addLayout(set_row)
            self._rebuild_set_combo()

            intro = QtWidgets.QLabel(
                "Click a field and press the key combination you want, then "
                "click Apply. Shortcuts are bound in the hotkey set above and "
                "saved with your Maya preferences."
            )
            intro.setWordWrap(True)
            intro.setProperty("role", "sectionCaption")
            layout.addWidget(intro)

            scroll = QtWidgets.QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
            body = QtWidgets.QWidget()
            grid = QtWidgets.QGridLayout(body)
            grid.setHorizontalSpacing(10)
            grid.setVerticalSpacing(6)
            grid.setColumnStretch(1, 1)

            for row, name in enumerate(hotkeys.ORDER):
                binding = hotkeys.DEFAULTS[name]
                label = QtWidgets.QLabel(binding["label"])
                grid.addWidget(label, row, 0)

                key_edit = QtWidgets.QKeySequenceEdit()
                if hasattr(key_edit, "setMaximumSequenceLength"):
                    key_edit.setMaximumSequenceLength(1)
                grid.addWidget(key_edit, row, 1)
                self._key_edits[name] = key_edit

                clear = QtWidgets.QPushButton("Clear")
                clear.setToolTip("Remove this shortcut")
                clear.clicked.connect(lambda *args, e=key_edit: e.clear())
                grid.addWidget(clear, row, 2)

            scroll.setWidget(body)
            layout.addWidget(scroll)

            buttons = QtWidgets.QHBoxLayout()
            restore = QtWidgets.QPushButton("Restore Defaults")
            restore.clicked.connect(self._restore_defaults)
            remove = QtWidgets.QPushButton("Remove All")
            remove.clicked.connect(self._remove_all)
            buttons.addWidget(restore)
            buttons.addWidget(remove)
            buttons.addStretch()
            close = QtWidgets.QPushButton("Close")
            close.clicked.connect(self.reject)
            apply_btn = QtWidgets.QPushButton("Apply")
            apply_btn.setProperty("role", "accent")
            apply_btn.clicked.connect(self._apply)
            buttons.addWidget(close)
            buttons.addWidget(apply_btn)
            layout.addLayout(buttons)

        # ── Hotkey set switching ────────────────────────────────────────────

        def _rebuild_set_combo(self):
            if cmds is None:
                return
            self._set_combo.blockSignals(True)
            self._set_combo.clear()
            for name in hotkeys.custom_hotkey_sets():
                self._set_combo.addItem(name)
            self._set_combo.addItem(hotkeys.CREATE_NEW_SET_LABEL)
            idx = self._set_combo.findText(hotkeys.current_hotkey_set())
            if idx >= 0:
                self._set_combo.setCurrentIndex(idx)
            self._set_combo.blockSignals(False)

        def _on_set_changed(self, index):
            choice = self._set_combo.currentText()
            if choice == hotkeys.CREATE_NEW_SET_LABEL:
                hotkeys.prompt_create_hotkey_set()
                # Defer the rebuild so the combo finishes handling the
                # activated signal before its item list is replaced.
                QtCore.QTimer.singleShot(0, self._rebuild_set_combo)
            else:
                hotkeys.activate_hotkey_set(choice)

        # ── Bindings <-> fields ─────────────────────────────────────────────

        def _load(self, bindings):
            for name, key_edit in self._key_edits.items():
                binding = bindings.get(name, hotkeys.DEFAULTS[name])
                key_edit.setKeySequence(_sequence_from_binding(binding))

        def _collect(self):
            """Build a bindings dict from the capture fields.

            Unmapped keys raise a warning and keep the field's action unbound.
            """
            bindings = hotkeys.default_bindings()
            for name, key_edit in self._key_edits.items():
                seq = key_edit.keySequence()
                parsed = _parse_key_sequence(seq)
                if parsed is None:
                    if seq.count() > 0 and cmds:
                        cmds.warning(
                            "Blue Pencil Flipbook: could not map key '{0}' for {1} — "
                            "unsupported key.".format(seq.toString(), hotkeys.DEFAULTS[name]["label"])
                        )
                    bindings[name]["key"] = ""
                    bindings[name]["ctrl"] = bindings[name]["alt"] = bindings[name]["shift"] = False
                    continue
                key, ctrl, alt, shift = parsed
                bindings[name]["key"] = key
                bindings[name]["ctrl"] = ctrl
                bindings[name]["alt"] = alt
                bindings[name]["shift"] = shift
            return bindings

        # ── Buttons ─────────────────────────────────────────────────────────

        def _apply(self):
            result = hotkeys.apply_bindings(self._collect())
            if result is None:
                # User cancelled the writable-hotkey-set step (or no Maya).
                return
            applied, skipped = result
            self._rebuild_set_combo()
            msg = "{0} hotkey(s) assigned and saved to hotkey set '{1}'.".format(
                applied, hotkeys.current_hotkey_set()
            )
            if skipped:
                msg += "  {0} skipped.".format(skipped)
            if cmds:
                cmds.inViewMessage(
                    amg="<hl>Blue Pencil Flipbook</hl>  " + msg,
                    pos="midCenter", fade=True,
                )
            QtWidgets.QMessageBox.information(self, "Hotkeys", msg)

        def _restore_defaults(self):
            self._load(hotkeys.default_bindings())

        def _remove_all(self):
            if hotkeys.remove_hotkeys() is False:
                return
            for key_edit in self._key_edits.values():
                key_edit.clear()
            QtWidgets.QMessageBox.information(
                self, "Hotkeys", "Removed the tool's hotkeys from the active set."
            )


    def show_editor(parent=None):
        """Open the hotkey editor, ensuring a writable hotkey set first."""
        if hotkeys.ensure_writable_hotkey_set() is None:
            return None
        dialog = HotkeyEditor(parent or _maya_main_window())
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        return dialog

else:
    class HotkeyEditor(object):
        def __init__(self, *args, **kwargs):
            raise RuntimeError("HotkeyEditor requires PySide2 or PySide6 inside Maya.")

    def select_hotkey_set(custom_sets, parent=None):
        return custom_sets[0] if custom_sets else None

    def show_editor(parent=None):
        raise RuntimeError("HotkeyEditor requires PySide2 or PySide6 inside Maya.")
