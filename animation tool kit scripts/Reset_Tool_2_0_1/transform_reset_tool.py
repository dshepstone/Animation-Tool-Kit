"""Maya Transform Reset Tool.

Provides a modern UI to reset translate, rotate, scale, or all transforms
on selected nodes, while skipping locked or non-settable channels.
"""

from PySide6 import QtCore, QtGui, QtWidgets
from maya import cmds
from maya import OpenMayaUI as omui
from shiboken6 import wrapInstance

WINDOW_OBJECT_NAME = "scaleRotateTranslateResetUI"

# ── Stylesheet ────────────────────────────────────────────────────────────────
_STYLESHEET = """
QDialog {
    background-color: #3c3c3c;
    color: #cccccc;
}
QLabel {
    color: #cccccc;
    background: transparent;
}
QLabel#lbl_title {
    font-size: 14px;
    font-weight: bold;
    color: #ffffff;
}
QLabel#lbl_subtitle {
    font-size: 11px;
    color: #999999;
}
QLabel#lbl_section {
    font-size: 9px;
    font-weight: bold;
    color: #777777;
    letter-spacing: 1px;
}
QLabel#lbl_desc {
    font-size: 10px;
    color: #848484;
    padding-left: 2px;
}
QFrame#separator {
    background-color: #525252;
    border: none;
    max-height: 1px;
    min-height: 1px;
}
QPushButton {
    background-color: #555555;
    color: #dddddd;
    border: 1px solid #666666;
    border-radius: 4px;
    padding: 7px 14px;
    font-size: 12px;
    min-height: 30px;
    text-align: left;
}
QPushButton:hover {
    background-color: #636363;
    border-color: #888888;
    color: #ffffff;
}
QPushButton:pressed {
    background-color: #444444;
    border-color: #555555;
}
QPushButton#btn_all {
    background-color: #2e6da4;
    color: #ffffff;
    border: 1px solid #4088c0;
    border-radius: 4px;
    font-weight: bold;
    font-size: 13px;
    min-height: 38px;
    text-align: center;
    padding: 8px 14px;
}
QPushButton#btn_all:hover {
    background-color: #3a7ec0;
    border-color: #5599d4;
}
QPushButton#btn_all:pressed {
    background-color: #205080;
    border-color: #2e6da4;
}
"""


# ── Core reset logic ──────────────────────────────────────────────────────────

def _get_maya_main_window():
    """Return Maya's main window as a QtWidgets.QWidget."""
    ptr = omui.MQtUtil.mainWindow()
    if ptr is None:
        return None
    return wrapInstance(int(ptr), QtWidgets.QWidget)


def _iter_reset_targets(attr_value_pairs):
    """Yield (full_attr, value) for unlocked, settable channels on selected nodes."""
    selection = cmds.ls(selection=True) or []
    if not selection:
        cmds.warning("No objects selected. Select one or more transforms to reset.")
        return
    for node in selection:
        for attr_name, value in attr_value_pairs:
            if not cmds.attributeQuery(attr_name, node=node, exists=True):
                continue
            full_attr = f"{node}.{attr_name}"
            if cmds.getAttr(full_attr, lock=True):
                continue
            if not cmds.getAttr(full_attr, settable=True):
                continue
            yield full_attr, value


def _reset_attributes(attr_value_pairs):
    for full_attr, value in _iter_reset_targets(attr_value_pairs):
        cmds.setAttr(full_attr, value)


def reset_translate():
    """Set tx, ty, tz to 0 on selected objects."""
    _reset_attributes((("tx", 0.0), ("ty", 0.0), ("tz", 0.0)))


def reset_rotate():
    """Set rx, ry, rz to 0 on selected objects."""
    _reset_attributes((("rx", 0.0), ("ry", 0.0), ("rz", 0.0)))


def reset_scale():
    """Set sx, sy, sz to 1 on selected objects."""
    _reset_attributes((("sx", 1.0), ("sy", 1.0), ("sz", 1.0)))


def reset_all():
    """Reset translate, rotate and scale to defaults on selected objects."""
    _reset_attributes(
        (
            ("tx", 0.0), ("ty", 0.0), ("tz", 0.0),
            ("rx", 0.0), ("ry", 0.0), ("rz", 0.0),
            ("sx", 1.0), ("sy", 1.0), ("sz", 1.0),
        )
    )


# ── UI ────────────────────────────────────────────────────────────────────────

class ResetTransformsDialog(QtWidgets.QDialog):
    """Modern Transform Reset dialog for Maya."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName(WINDOW_OBJECT_NAME)
        self.setWindowTitle("Transform Reset Tool")
        self.setWindowFlags(
            QtCore.Qt.Window
            | QtCore.Qt.WindowTitleHint
            | QtCore.Qt.WindowCloseButtonHint
        )
        self.setMinimumWidth(320)
        self.setStyleSheet(_STYLESHEET)
        self._build_ui()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _separator(self):
        line = QtWidgets.QFrame()
        line.setObjectName("separator")
        line.setFrameShape(QtWidgets.QFrame.HLine)
        return line

    def _section_label(self, text):
        lbl = QtWidgets.QLabel(text.upper())
        lbl.setObjectName("lbl_section")
        return lbl

    def _desc_label(self, text):
        lbl = QtWidgets.QLabel(text)
        lbl.setObjectName("lbl_desc")
        lbl.setWordWrap(True)
        return lbl

    def _action_button(self, text, tooltip, callback):
        btn = QtWidgets.QPushButton(text)
        btn.setToolTip(tooltip)
        btn.clicked.connect(callback)
        return btn

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(0)

        # Header
        title = QtWidgets.QLabel("Transform Reset Tool")
        title.setObjectName("lbl_title")
        subtitle = QtWidgets.QLabel(
            "Resets transform channels on selected objects to their default values. "
            "Locked or driven channels are automatically skipped."
        )
        subtitle.setObjectName("lbl_subtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(title)
        layout.addSpacing(4)
        layout.addWidget(subtitle)
        layout.addSpacing(12)
        layout.addWidget(self._separator())
        layout.addSpacing(12)

        # Individual channel resets
        layout.addWidget(self._section_label("Individual Channels"))
        layout.addSpacing(8)

        channels = [
            (
                "Reset Translate",
                "Moves the object back to origin — sets tx, ty, tz to 0",
                "Sets X, Y, Z translation (tx · ty · tz) to 0.\n"
                "Moves the object back to the world origin position.",
                reset_translate,
            ),
            (
                "Reset Rotate",
                "Returns to default orientation — sets rx, ry, rz to 0°",
                "Sets X, Y, Z rotation (rx · ry · rz) to 0°.\n"
                "Returns the object to its default, unrotated orientation.",
                reset_rotate,
            ),
            (
                "Reset Scale",
                "Restores 100% size — sets sx, sy, sz to 1",
                "Sets X, Y, Z scale (sx · sy · sz) to 1.\n"
                "Restores the object to its default uniform size (100%).",
                reset_scale,
            ),
        ]

        for i, (label, desc, tooltip, fn) in enumerate(channels):
            btn = self._action_button(label, tooltip, fn)
            layout.addWidget(btn)
            layout.addSpacing(3)
            layout.addWidget(self._desc_label(desc))
            if i < len(channels) - 1:
                layout.addSpacing(10)

        layout.addSpacing(14)
        layout.addWidget(self._separator())
        layout.addSpacing(12)

        # Reset All
        layout.addWidget(self._section_label("Reset Everything"))
        layout.addSpacing(8)

        btn_all = QtWidgets.QPushButton("Reset All Transforms")
        btn_all.setObjectName("btn_all")
        btn_all.setToolTip(
            "Resets translate, rotate and scale in one action.\n"
            "Equivalent to clicking all three buttons above at once."
        )
        btn_all.clicked.connect(reset_all)
        layout.addWidget(btn_all)
        layout.addSpacing(4)
        layout.addWidget(
            self._desc_label(
                "Resets translate, rotate, and scale to defaults in a single click."
            )
        )

        # Hotkeys section
        layout.addSpacing(14)
        layout.addWidget(self._separator())
        layout.addSpacing(12)

        layout.addWidget(self._section_label("Shortcuts"))
        layout.addSpacing(8)

        btn_hotkeys = self._action_button(
            "Setup / Edit Hotkeys...",
            "Assign or change keyboard shortcuts for each reset function.\n"
            "Opens a dialog to configure hotkey bindings.",
            lambda: show_hotkey_setup(),
        )
        layout.addWidget(btn_hotkeys)
        layout.addSpacing(3)
        layout.addWidget(
            self._desc_label(
                "Assign keyboard shortcuts to trigger reset functions directly."
            )
        )


# ── Public API ────────────────────────────────────────────────────────────────

def show():
    """Show the Transform Reset dialog, closing any existing instance first."""
    for widget in QtWidgets.QApplication.allWidgets():
        if widget.objectName() == WINDOW_OBJECT_NAME:
            widget.close()
            widget.deleteLater()

    dialog = ResetTransformsDialog(parent=_get_maya_main_window())
    dialog.show()
    dialog.raise_()
    dialog.activateWindow()
    return dialog


def run():
    """Legacy entry point kept for backwards compatibility."""
    return show()


# ── Hotkey Set Management ────────────────────────────────────────────────────

_LOCKED_HOTKEY_SET = "Maya_Default"


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
        self.setStyleSheet(_STYLESHEET)
        self._selected_set = None
        self._build_ui(custom_sets)

    def _build_ui(self, custom_sets):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(12)

        # Message
        msg = QtWidgets.QLabel(
            "The default \u2018Maya_Default\u2019 hotkey set is locked.\n"
            "Choose a custom hotkey set for editing, or create a new one."
        )
        msg.setObjectName("lbl_subtitle")
        msg.setWordWrap(True)
        layout.addWidget(msg)

        # Dropdown
        self._combo = QtWidgets.QComboBox()
        for s in custom_sets:
            self._combo.addItem(s)
        self._combo.addItem("< Create New Set >")
        layout.addWidget(self._combo)

        # Buttons
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch()

        btn_ok = QtWidgets.QPushButton("OK")
        btn_ok.setObjectName("btn_all")
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


def _ensure_writable_hotkey_set():
    """Make sure the current hotkey set is writable (not Maya_Default).

    If Maya_Default is active, prompt the user to choose an existing custom
    set or create a new one via a dropdown dialog.  Returns the name of the
    active writable set, or None if the user cancels.
    """
    current = cmds.hotkeySet(query=True, current=True)
    if current != _LOCKED_HOTKEY_SET:
        return current  # already on a writable set

    # Gather custom sets
    all_sets = cmds.hotkeySet(query=True, hotkeySetArray=True) or []
    custom_sets = [s for s in all_sets if s != _LOCKED_HOTKEY_SET]

    if custom_sets:
        dlg = _HotkeySetSelectDialog(
            custom_sets, parent=_get_maya_main_window()
        )
        if dlg.exec_() != QtWidgets.QDialog.Accepted:
            return None
        choice = dlg.selected_set()
        if choice == "< Create New Set >":
            return _prompt_create_hotkey_set()
        cmds.hotkeySet(choice, edit=True, current=True)
        print(f"Reset Tool: switched to hotkey set '{choice}'")
        return choice
    else:
        # No custom sets exist — must create one
        return _prompt_create_hotkey_set()


def _prompt_create_hotkey_set():
    """Prompt the user to name and create a new hotkey set.

    Returns the new set name, or None if cancelled.
    """
    result = cmds.promptDialog(
        title="Create Hotkey Set",
        message=(
            "The default 'Maya_Default' hotkey set is locked and cannot\n"
            "be modified.  Enter a name for a new custom hotkey set:"
        ),
        button=["Create", "Cancel"],
        defaultButton="Create",
        cancelButton="Cancel",
        text="Custom",
    )
    if result != "Create":
        return None
    name = cmds.promptDialog(query=True, text=True).strip()
    if not name:
        cmds.warning("Reset Tool: hotkey set name cannot be empty.")
        return None
    # Create from the current default so existing hotkeys carry over
    if cmds.hotkeySet(name, exists=True):
        cmds.hotkeySet(name, edit=True, current=True)
    else:
        cmds.hotkeySet(name, source=_LOCKED_HOTKEY_SET)
        cmds.hotkeySet(name, edit=True, current=True)
    print(f"Reset Tool: created and activated hotkey set '{name}'")
    return name


# ── Runtime Commands ─────────────────────────────────────────────────────────

_RUNTIME_CMD_PREFIX = "resetTool_"

_RESET_ACTIONS = {
    "resetAll": (
        "import transform_reset_tool; transform_reset_tool.reset_all()",
        "Reset All Transforms",
    ),
    "resetTranslate": (
        "import transform_reset_tool; transform_reset_tool.reset_translate()",
        "Reset Translate",
    ),
    "resetRotate": (
        "import transform_reset_tool; transform_reset_tool.reset_rotate()",
        "Reset Rotate",
    ),
    "resetScale": (
        "import transform_reset_tool; transform_reset_tool.reset_scale()",
        "Reset Scale",
    ),
}

_ACTION_ORDER = ["resetAll", "resetTranslate", "resetRotate", "resetScale"]


def _ensure_runtime_commands():
    """Register (or update) runtime commands for each reset function.

    Commands appear in Maya's Hotkey Editor under 'Custom Scripts'.
    """
    for cmd_suffix, (py_code, annotation) in _RESET_ACTIONS.items():
        rt_name = _RUNTIME_CMD_PREFIX + cmd_suffix
        if cmds.runTimeCommand(rt_name, exists=True):
            cmds.runTimeCommand(
                rt_name, edit=True,
                command=py_code,
                commandLanguage="python",
            )
        else:
            cmds.runTimeCommand(
                rt_name,
                annotation=annotation,
                category="Custom Scripts.Reset Tool",
                commandLanguage="python",
                command=py_code,
            )
        print(f"Reset Tool: runtime command '{rt_name}' ready")


# ── Hotkey Assignment ────────────────────────────────────────────────────────

def _display_string(key, ctrl=False, alt=False, shift=False):
    """Return a human-readable string like 'Ctrl+Shift+R'."""
    display = ""
    if ctrl:
        display += "Ctrl+"
    if alt:
        display += "Alt+"
    if shift:
        display += "Shift+"
    display += key.upper() if len(key) == 1 else key
    return display


def assign_hotkey(action_key, key, ctrl=False, alt=False, shift=False):
    """Assign a keyboard shortcut to a reset action.

    Caller must ensure a writable hotkey set is active and runtime
    commands are registered before calling this function.

    Returns True if assigned, False if the user cancelled (conflict).
    """
    display = _display_string(key, ctrl, alt, shift)
    nc_name = _RUNTIME_CMD_PREFIX + action_key + "NameCommand"
    rt_name = _RUNTIME_CMD_PREFIX + action_key
    annotation = _RESET_ACTIONS[action_key][1]

    # --- Check for existing binding ---
    # Docs: cmds.hotkey( 'z', query=True, name=True )
    query_kw = {}
    if ctrl:
        query_kw["ctl"] = True
    if alt:
        query_kw["alt"] = True
    if shift:
        query_kw["sht"] = True
    try:
        existing = cmds.hotkey(key, query=True, n=True, **query_kw)
    except Exception:
        existing = ""

    if existing and existing != nc_name:
        result = cmds.confirmDialog(
            title="Hotkey Conflict",
            message=(
                f"'{display}' is already assigned to:\n"
                f"{existing}\n\n"
                f"Overwrite with {annotation}?"
            ),
            button=["Overwrite", "Cancel"],
            defaultButton="Cancel",
            cancelButton="Cancel",
        )
        if result == "Cancel":
            return False

    # --- Create the nameCommand that wraps our runtime command ---
    # Docs: cmds.nameCommand('myNC', ann='...', command='myRuntimeCmd')
    cmds.nameCommand(nc_name, ann=annotation, sourceType="mel", command=rt_name)

    # --- Bind the hotkey ---
    # Docs: cmds.hotkey( k='F5', alt=True, name='myNC' )
    hotkey_kw = {"k": key, "n": nc_name}
    if ctrl:
        hotkey_kw["ctl"] = True
    if alt:
        hotkey_kw["alt"] = True
    if shift:
        hotkey_kw["sht"] = True
    cmds.hotkey(**hotkey_kw)

    # --- Persist the display string for the UI ---
    cmds.optionVar(sv=("resetTool_hotkey_" + action_key, display))

    print(f"Reset Tool: hotkey '{display}' -> {rt_name}")
    return True


def _get_current_hotkey(action_key):
    """Return a human-readable string of the current hotkey, or empty string."""
    var_name = "resetTool_hotkey_" + action_key
    if cmds.optionVar(exists=var_name):
        return cmds.optionVar(q=var_name)
    return ""


def _clear_hotkey(action_key):
    """Remove the hotkey binding for the given action."""
    var_name = "resetTool_hotkey_" + action_key
    if cmds.optionVar(exists=var_name):
        stored = cmds.optionVar(q=var_name)
        cmds.optionVar(remove=var_name)
        parts = stored.split("+")
        key = parts[-1].lower() if len(parts[-1]) == 1 else parts[-1]
        clear_kw = {"k": key, "n": ""}
        if "Ctrl" in parts:
            clear_kw["ctl"] = True
        if "Alt" in parts:
            clear_kw["alt"] = True
        if "Shift" in parts:
            clear_kw["sht"] = True
        try:
            cmds.hotkey(**clear_kw)
        except Exception:
            pass


# ── Qt key-to-Maya mapping ───────────────────────────────────────────────────

_QT_KEY_TO_MAYA = {}


def _build_key_map():
    """Populate the Qt-key-to-Maya-string mapping (lazy init)."""
    if _QT_KEY_TO_MAYA:
        return
    key = QtCore.Qt.Key
    for i in range(26):
        _QT_KEY_TO_MAYA[key.Key_A.value + i] = chr(ord("a") + i)
    for i in range(10):
        _QT_KEY_TO_MAYA[key.Key_0.value + i] = str(i)
    for i in range(1, 13):
        _QT_KEY_TO_MAYA[getattr(key, f"Key_F{i}").value] = f"F{i}"
    extras = {
        key.Key_Space: "Space", key.Key_Return: "Return", key.Key_Enter: "Return",
        key.Key_Tab: "Tab", key.Key_Backspace: "Backspace", key.Key_Delete: "Delete",
        key.Key_Home: "Home", key.Key_End: "End",
        key.Key_Left: "Left", key.Key_Right: "Right",
        key.Key_Up: "Up", key.Key_Down: "Down",
        key.Key_PageUp: "Page_Up", key.Key_PageDown: "Page_Down",
        key.Key_Insert: "Insert",
    }
    for qt_key, maya_str in extras.items():
        _QT_KEY_TO_MAYA[qt_key.value if hasattr(qt_key, "value") else qt_key] = maya_str


def _parse_key_sequence(seq):
    """Parse a QKeySequence into (maya_key, ctrl, alt, shift) or None."""
    _build_key_map()
    if seq.count() == 0:
        return None
    key_combo = seq[0]  # QKeyCombination
    key_enum = key_combo.key()
    modifiers = key_combo.keyboardModifiers()
    key_val = key_enum.value if hasattr(key_enum, "value") else int(key_enum)
    maya_key = _QT_KEY_TO_MAYA.get(key_val)
    if maya_key is None:
        return None
    ctrl = bool(modifiers & QtCore.Qt.KeyboardModifier.ControlModifier)
    alt = bool(modifiers & QtCore.Qt.KeyboardModifier.AltModifier)
    shift = bool(modifiers & QtCore.Qt.KeyboardModifier.ShiftModifier)
    return maya_key, ctrl, alt, shift


# ── Hotkey Setup Dialog ──────────────────────────────────────────────────────

HOTKEY_WINDOW_OBJECT_NAME = "resetToolHotkeySetupUI"

_HOTKEY_STYLESHEET = _STYLESHEET + """
QKeySequenceEdit {
    background-color: #4a4a4a;
    color: #dddddd;
    border: 1px solid #666666;
    border-radius: 3px;
    padding: 4px 8px;
    font-size: 12px;
    min-height: 24px;
}
QKeySequenceEdit:focus {
    border-color: #2e6da4;
}
QLabel#lbl_current {
    font-size: 10px;
    color: #999999;
    padding-left: 2px;
}
QComboBox {
    background-color: #4a4a4a;
    color: #dddddd;
    border: 1px solid #666666;
    border-radius: 3px;
    padding: 4px 8px;
    font-size: 12px;
    min-height: 22px;
}
QComboBox:hover {
    border-color: #888888;
}
QComboBox::drop-down {
    border: none;
    width: 20px;
}
QComboBox QAbstractItemView {
    background-color: #3c3c3c;
    color: #dddddd;
    border: 1px solid #555555;
    selection-background-color: #2e6da4;
}
"""


class HotkeySetupDialog(QtWidgets.QDialog):
    """Dialog for assigning keyboard shortcuts to reset functions."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName(HOTKEY_WINDOW_OBJECT_NAME)
        self.setWindowTitle("Reset Tool — Setup Hotkeys")
        self.setWindowFlags(
            QtCore.Qt.Window
            | QtCore.Qt.WindowTitleHint
            | QtCore.Qt.WindowCloseButtonHint
        )
        self.setMinimumWidth(380)
        self.setStyleSheet(_HOTKEY_STYLESHEET)
        self._key_edits = {}
        self._build_ui()

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(0)

        # Header
        title = QtWidgets.QLabel("Setup Hotkeys")
        title.setObjectName("lbl_title")
        layout.addWidget(title)
        layout.addSpacing(4)

        # Hotkey set selector
        set_row = QtWidgets.QHBoxLayout()
        set_row.setSpacing(8)
        set_label = QtWidgets.QLabel("Hotkey Set:")
        set_label.setObjectName("lbl_section")
        set_row.addWidget(set_label)

        self._set_combo = QtWidgets.QComboBox()
        all_sets = cmds.hotkeySet(query=True, hotkeySetArray=True) or []
        current_set = cmds.hotkeySet(query=True, current=True)
        custom_sets = [s for s in all_sets if s != _LOCKED_HOTKEY_SET]
        for s in custom_sets:
            self._set_combo.addItem(s)
        self._set_combo.addItem("< Create New Set >")
        # Select the current set in the dropdown
        idx = self._set_combo.findText(current_set)
        if idx >= 0:
            self._set_combo.setCurrentIndex(idx)
        self._set_combo.activated.connect(self._on_set_changed)
        set_row.addWidget(self._set_combo, 1)

        btn_refresh = QtWidgets.QPushButton()
        btn_refresh.setToolTip("Refresh hotkey set list")
        refresh_icon = self.style().standardIcon(
            QtWidgets.QStyle.SP_BrowserReload
        )
        btn_refresh.setIcon(refresh_icon)
        btn_refresh.setFixedSize(26, 26)
        btn_refresh.setIconSize(QtCore.QSize(16, 16))
        btn_refresh.setStyleSheet(
            "QPushButton {"
            "  padding: 0px;"
            "  border: 1px solid #555;"
            "  border-radius: 3px;"
            "  background-color: #3a3a3a;"
            "}"
            "QPushButton:hover {"
            "  background-color: #4a4a4a;"
            "  border-color: #777;"
            "}"
        )
        btn_refresh.clicked.connect(self._rebuild_set_combo)
        set_row.addWidget(btn_refresh)

        layout.addLayout(set_row)
        layout.addSpacing(4)

        subtitle = QtWidgets.QLabel(
            "Assign keyboard shortcuts to each reset function. "
            "Click a field and press the desired key combination."
        )
        subtitle.setObjectName("lbl_subtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)
        layout.addSpacing(12)

        line = QtWidgets.QFrame()
        line.setObjectName("separator")
        line.setFrameShape(QtWidgets.QFrame.HLine)
        layout.addWidget(line)
        layout.addSpacing(12)

        # Grid of actions
        grid = QtWidgets.QGridLayout()
        grid.setColumnStretch(1, 1)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)

        for row, action_key in enumerate(_ACTION_ORDER):
            label_text = _RESET_ACTIONS[action_key][1]
            lbl = QtWidgets.QLabel(label_text)
            lbl.setObjectName("lbl_section")
            grid.addWidget(lbl, row * 2, 0, QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)

            key_edit = QtWidgets.QKeySequenceEdit()
            key_edit.setMaximumSequenceLength(1)
            current = _get_current_hotkey(action_key)
            if current:
                key_edit.setKeySequence(QtGui.QKeySequence.fromString(current))
            grid.addWidget(key_edit, row * 2, 1)
            self._key_edits[action_key] = key_edit

            current_lbl = QtWidgets.QLabel(
                f"Current: {current}" if current else "No shortcut assigned"
            )
            current_lbl.setObjectName("lbl_current")
            grid.addWidget(current_lbl, row * 2 + 1, 1)

        layout.addLayout(grid)
        layout.addSpacing(16)

        line2 = QtWidgets.QFrame()
        line2.setObjectName("separator")
        line2.setFrameShape(QtWidgets.QFrame.HLine)
        layout.addWidget(line2)
        layout.addSpacing(12)

        # Buttons
        btn_row = QtWidgets.QHBoxLayout()

        btn_clear = QtWidgets.QPushButton("Clear All")
        btn_clear.setToolTip("Remove all hotkey assignments for reset functions")
        btn_clear.clicked.connect(self._on_clear)
        btn_row.addWidget(btn_clear)

        btn_row.addStretch()

        btn_apply = QtWidgets.QPushButton("Apply")
        btn_apply.setObjectName("btn_all")
        btn_apply.setToolTip("Save and apply the hotkey assignments")
        btn_apply.clicked.connect(self._on_apply)
        btn_row.addWidget(btn_apply)

        layout.addLayout(btn_row)

    # ── Hotkey set switching ────────────────────────────────────────────────

    def _on_set_changed(self, index):
        """Handle hotkey set dropdown selection."""
        choice = self._set_combo.currentText()
        if choice == "< Create New Set >":
            new_set = _prompt_create_hotkey_set()
            if new_set is None:
                # Cancelled — revert dropdown to the current active set
                QtCore.QTimer.singleShot(0, self._rebuild_set_combo)
                return
            # New set was created and activated — defer rebuild so the
            # combo widget fully finishes processing the activated signal
            # before we tear down and repopulate its item list.
            QtCore.QTimer.singleShot(0, self._rebuild_set_combo)
        else:
            cmds.hotkeySet(choice, edit=True, current=True)
            print(f"Reset Tool: switched to hotkey set '{choice}'")
        self._refresh_hotkeys()

    def _rebuild_set_combo(self):
        """Rebuild the hotkey-set dropdown from Maya's current state."""
        self._set_combo.blockSignals(True)
        self._set_combo.clear()
        all_sets = cmds.hotkeySet(query=True, hotkeySetArray=True) or []
        custom_sets = [s for s in all_sets if s != _LOCKED_HOTKEY_SET]
        for s in custom_sets:
            self._set_combo.addItem(s)
        self._set_combo.addItem("< Create New Set >")
        current = cmds.hotkeySet(query=True, current=True)
        idx = self._set_combo.findText(current)
        if idx >= 0:
            self._set_combo.setCurrentIndex(idx)
        self._set_combo.blockSignals(False)
        # Force the widget to repaint immediately
        self._set_combo.update()
        self._refresh_hotkeys()

    def _refresh_hotkeys(self):
        """Update the key-sequence fields to reflect the active hotkey set."""
        for action_key, key_edit in self._key_edits.items():
            current = _get_current_hotkey(action_key)
            key_edit.clear()
            if current:
                key_edit.setKeySequence(QtGui.QKeySequence.fromString(current))

    def _on_apply(self):
        # Ensure runtime commands are registered before assigning hotkeys
        _ensure_runtime_commands()

        applied = 0
        skipped = 0
        for action_key in _ACTION_ORDER:
            seq = self._key_edits[action_key].keySequence()
            parsed = _parse_key_sequence(seq)
            if parsed is None:
                if seq.count() > 0:
                    cmds.warning(
                        f"Reset Tool: could not map key '{seq.toString()}' "
                        f"for {_RESET_ACTIONS[action_key][1]} — unsupported key."
                    )
                continue
            maya_key, ctrl, alt, shift = parsed
            try:
                if assign_hotkey(action_key, maya_key, ctrl=ctrl, alt=alt, shift=shift):
                    applied += 1
                else:
                    skipped += 1
            except Exception as exc:
                cmds.warning(f"Reset Tool: failed to assign hotkey — {exc}")

        if applied:
            # Save hotkeys so they persist
            cmds.savePrefs(hotkeys=True)
            msg = f"<hl>Reset Tool</hl>  {applied} hotkey(s) assigned and saved."
            if skipped:
                msg += f"  {skipped} skipped."
            cmds.inViewMessage(amg=msg, pos="midCenter", fade=True)
        elif skipped:
            cmds.inViewMessage(
                amg=f"<hl>Reset Tool</hl>  {skipped} hotkey(s) skipped (conflicts).",
                pos="midCenter",
                fade=True,
            )
        self.close()

    def _on_clear(self):
        for action_key in _ACTION_ORDER:
            _clear_hotkey(action_key)
            self._key_edits[action_key].clear()
        cmds.savePrefs(hotkeys=True)
        cmds.inViewMessage(
            amg="<hl>Reset Tool</hl>  All hotkeys cleared.",
            pos="midCenter",
            fade=True,
        )
        self.close()


def show_hotkey_setup():
    """Show the Hotkey Setup dialog.

    First ensures a writable hotkey set is active and runtime commands
    are registered.  Always allows re-opening for editing.
    """
    # Close any existing instance
    for widget in QtWidgets.QApplication.allWidgets():
        if widget.objectName() == HOTKEY_WINDOW_OBJECT_NAME:
            widget.close()
            widget.deleteLater()

    # 1) Ensure a writable hotkey set is active
    hotkey_set = _ensure_writable_hotkey_set()
    if hotkey_set is None:
        return None  # user cancelled

    # 2) Register / update the runtime commands
    _ensure_runtime_commands()

    # 3) Show the dialog
    dialog = HotkeySetupDialog(parent=_get_maya_main_window())
    dialog.show()
    dialog.raise_()
    dialog.activateWindow()
    return dialog
