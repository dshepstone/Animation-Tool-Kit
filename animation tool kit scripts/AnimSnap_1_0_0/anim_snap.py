"""
AnimSnap - Maya Python tool for snapping one object to another using
world-space transforms.

Usage:
    1. Select two objects in Maya (source first, then target)
    2. Run: anim_snap.snap()

The first selected object will be moved to match the position and orientation
of the second selected object in world space.

From the ATK Toolbar:
    Left-click the AnimSnap button   - snap immediately (translate + rotate)
    Right-click the AnimSnap button  - open the AnimSnap window, snap
                                       variants, and hotkey setup

Every snap function can also be bound to a Maya hotkey via
show_hotkey_setup() ("Setup / Edit Hotkeys..." in the window).
"""

import maya.cmds as cmds
from maya import OpenMayaUI as omui

try:
    from PySide6 import QtCore, QtGui, QtWidgets
    from shiboken6 import wrapInstance
except ImportError:  # Maya 2022-2024
    from PySide2 import QtCore, QtGui, QtWidgets
    from shiboken2 import wrapInstance

WINDOW_OBJECT_NAME = "animSnapUI"
HOTKEY_WINDOW_OBJECT_NAME = "animSnapHotkeyUI"

# Legacy cmds-based window from v1.0 — deleted on show() so upgrading never
# leaves a stale duplicate window open.
_LEGACY_WIN_ID = "animSnapWindow"


# ---------------------------------------------------------------------------
# Core snap functions
# ---------------------------------------------------------------------------

def snap(translate=True, rotate=True):
    """Snap the first selected object to the second selected object in world space.

    Args:
        translate: Apply world-space translation from target. Default True.
        rotate: Apply world-space rotation from target. Default True.
    """
    sel = cmds.ls(selection=True)

    if len(sel) < 2:
        cmds.warning("AnimSnap: Select two objects: source then target")
        return

    # If more than 2 selected, use the last two
    source = sel[-2]
    target = sel[-1]

    if not translate and not rotate:
        cmds.warning("AnimSnap: Nothing to snap: both translate and rotate are disabled")
        return

    # Query target world-space transforms
    target_translation = cmds.xform(target, query=True, worldSpace=True, translation=True)
    target_rotation = cmds.xform(target, query=True, worldSpace=True, rotation=True)

    # Apply to source in world space (handles parent hierarchies correctly).
    # One undo chunk so a snap undoes in a single step.
    cmds.undoInfo(openChunk=True, chunkName="animSnap")
    try:
        if translate:
            try:
                cmds.xform(source, worldSpace=True, translation=target_translation)
            except RuntimeError:
                cmds.warning("AnimSnap: could not set translate on '{}' (locked/connected) - skipped.".format(source))
        if rotate:
            try:
                cmds.xform(source, worldSpace=True, rotation=target_rotation)
            except RuntimeError:
                cmds.warning("AnimSnap: could not set rotate on '{}' (locked/connected) - skipped.".format(source))
    finally:
        cmds.undoInfo(closeChunk=True)

    # Confirmation
    mode = "translate + rotate"
    if translate and not rotate:
        mode = "translate only"
    elif rotate and not translate:
        mode = "rotate only"

    print("AnimSnap: Snapped '{}' -> '{}' ({})".format(source, target, mode))


def snap_translate():
    """Snap translation only."""
    snap(translate=True, rotate=False)


def snap_rotate():
    """Snap rotation only."""
    snap(translate=False, rotate=True)


# ---------------------------------------------------------------------------
# Stylesheet — matches the ATK toolbar / Reset Tool design language
# ---------------------------------------------------------------------------

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
QPushButton#btn_snap_all {
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
QPushButton#btn_snap_all:hover {
    background-color: #3a7ec0;
    border-color: #5599d4;
}
QPushButton#btn_snap_all:pressed {
    background-color: #205080;
    border-color: #2e6da4;
}
"""


def _get_maya_main_window():
    """Return Maya's main window as a QtWidgets.QWidget."""
    ptr = omui.MQtUtil.mainWindow()
    if ptr is None:
        return None
    return wrapInstance(int(ptr), QtWidgets.QWidget)


# ---------------------------------------------------------------------------
# UI — main window
# ---------------------------------------------------------------------------

class AnimSnapDialog(QtWidgets.QDialog):
    """Modern AnimSnap dialog for Maya."""

    def __init__(self, parent=None):
        super(AnimSnapDialog, self).__init__(parent)
        self.setObjectName(WINDOW_OBJECT_NAME)
        self.setWindowTitle("AnimSnap")
        self.setWindowFlags(
            QtCore.Qt.Window
            | QtCore.Qt.WindowTitleHint
            | QtCore.Qt.WindowCloseButtonHint
        )
        self.setMinimumWidth(320)
        self.setStyleSheet(_STYLESHEET)
        self._build_ui()

    # ── Helpers ─────────────────────────────────────────────────────────────

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

    # ── Layout ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(0)

        # Header
        title = QtWidgets.QLabel("AnimSnap")
        title.setObjectName("lbl_title")
        subtitle = QtWidgets.QLabel(
            "Snaps one object to another using world-space transforms. "
            "Select the source object first, then the target, and click a "
            "snap button. Works with parented rig controls."
        )
        subtitle.setObjectName("lbl_subtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(title)
        layout.addSpacing(4)
        layout.addWidget(subtitle)
        layout.addSpacing(12)
        layout.addWidget(self._separator())
        layout.addSpacing(12)

        # Snap all — primary action
        layout.addWidget(self._section_label("Snap All Axes"))
        layout.addSpacing(8)

        btn_all = QtWidgets.QPushButton("Snap (Translate + Rotate)")
        btn_all.setObjectName("btn_snap_all")
        btn_all.setToolTip(
            "Moves and orients the source object to match the target's\n"
            "world-space position and rotation.\n"
            "Same as left-clicking the AnimSnap button on the toolbar."
        )
        btn_all.clicked.connect(lambda *_: snap())
        layout.addWidget(btn_all)
        layout.addSpacing(4)
        layout.addWidget(
            self._desc_label(
                "Matches the target's world-space position and rotation in one click."
            )
        )

        layout.addSpacing(14)
        layout.addWidget(self._separator())
        layout.addSpacing(12)

        # Individual channels
        layout.addWidget(self._section_label("Individual Channels"))
        layout.addSpacing(8)

        channels = [
            (
                "Snap Translate Only",
                "Moves the source to the target's world-space position.\n"
                "Rotation is left unchanged.",
                "Matches world-space position only - keeps the current rotation.",
                snap_translate,
            ),
            (
                "Snap Rotate Only",
                "Orients the source to the target's world-space rotation.\n"
                "Position is left unchanged.",
                "Matches world-space rotation only - keeps the current position.",
                snap_rotate,
            ),
        ]

        for i, (label, tooltip, desc, fn) in enumerate(channels):
            btn = self._action_button(label, tooltip, lambda checked=False, f=fn: f())
            layout.addWidget(btn)
            layout.addSpacing(3)
            layout.addWidget(self._desc_label(desc))
            if i < len(channels) - 1:
                layout.addSpacing(10)

        # Hotkeys section
        layout.addSpacing(14)
        layout.addWidget(self._separator())
        layout.addSpacing(12)

        layout.addWidget(self._section_label("Shortcuts"))
        layout.addSpacing(8)

        btn_hotkeys = self._action_button(
            "Setup / Edit Hotkeys...",
            "Assign or change keyboard shortcuts for each snap function.\n"
            "Bindings are saved to your Maya hotkey set and persist "
            "between sessions.",
            lambda *_: show_hotkey_setup(),
        )
        layout.addWidget(btn_hotkeys)
        layout.addSpacing(3)
        layout.addWidget(
            self._desc_label(
                "Assign Maya keyboard shortcuts to snap directly - no window needed."
            )
        )


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

_dialog = None  # keeps the window alive when launched without a Maya parent


def show():
    """Show the AnimSnap dialog, closing any existing instance first."""
    global _dialog

    # Remove the legacy cmds-based window if a previous version left one open
    try:
        if cmds.window(_LEGACY_WIN_ID, exists=True):
            cmds.deleteUI(_LEGACY_WIN_ID)
    except Exception:
        pass

    for widget in QtWidgets.QApplication.allWidgets():
        if widget.objectName() == WINDOW_OBJECT_NAME:
            widget.close()
            widget.deleteLater()

    _dialog = AnimSnapDialog(parent=_get_maya_main_window())
    _dialog.show()
    _dialog.raise_()
    _dialog.activateWindow()
    return _dialog


def create_ui():
    """Legacy entry point kept for backwards compatibility."""
    return show()


def launch():
    """Launch the AnimSnap UI — called by the ATK Toolbar."""
    return show()


def add_shelf_button():
    """Add an AnimSnap button to the current shelf."""
    current_shelf = cmds.tabLayout("ShelfLayout", query=True, selectTab=True)
    cmds.shelfButton(
        parent=current_shelf,
        label="AnimSnap",
        annotation="Snap source object to target (select two objects)",
        command="import anim_snap; anim_snap.snap()",
        image1="snapTogether.png",
    )
    print("AnimSnap: Shelf button added to '{}'".format(current_shelf))


# ---------------------------------------------------------------------------
# Hotkey Set Management
# Maya's default hotkey set is locked — bindings must live in a custom set.
# ---------------------------------------------------------------------------

_LOCKED_HOTKEY_SET = "Maya_Default"


class _HotkeySetSelectDialog(QtWidgets.QDialog):
    """Modal dialog for selecting a writable hotkey set via dropdown."""

    def __init__(self, custom_sets, parent=None):
        super(_HotkeySetSelectDialog, self).__init__(parent)
        self.setWindowTitle("Select Hotkey Set")
        self.setWindowFlags(
            QtCore.Qt.Window
            | QtCore.Qt.WindowTitleHint
            | QtCore.Qt.WindowCloseButtonHint
        )
        self.setFixedWidth(360)
        self.setStyleSheet(_HOTKEY_STYLESHEET)
        self._selected_set = None
        self._build_ui(custom_sets)

    def _build_ui(self, custom_sets):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(12)

        msg = QtWidgets.QLabel(
            "The default 'Maya_Default' hotkey set is locked.\n"
            "Choose a custom hotkey set for editing, or create a new one."
        )
        msg.setObjectName("lbl_subtitle")
        msg.setWordWrap(True)
        layout.addWidget(msg)

        self._combo = QtWidgets.QComboBox()
        for s in custom_sets:
            self._combo.addItem(s)
        self._combo.addItem("< Create New Set >")
        layout.addWidget(self._combo)

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch()

        btn_ok = QtWidgets.QPushButton("OK")
        btn_ok.setObjectName("btn_snap_all")
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

    all_sets = cmds.hotkeySet(query=True, hotkeySetArray=True) or []
    custom_sets = [s for s in all_sets if s != _LOCKED_HOTKEY_SET]

    if custom_sets:
        dlg = _HotkeySetSelectDialog(
            custom_sets, parent=_get_maya_main_window()
        )
        if dlg.exec() != QtWidgets.QDialog.Accepted:
            return None
        choice = dlg.selected_set()
        if choice == "< Create New Set >":
            return _prompt_create_hotkey_set()
        cmds.hotkeySet(choice, edit=True, current=True)
        print("AnimSnap: switched to hotkey set '{}'".format(choice))
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
        cmds.warning("AnimSnap: hotkey set name cannot be empty.")
        return None
    # Create from the current default so existing hotkeys carry over
    if cmds.hotkeySet(name, exists=True):
        cmds.hotkeySet(name, edit=True, current=True)
    else:
        cmds.hotkeySet(name, source=_LOCKED_HOTKEY_SET)
        cmds.hotkeySet(name, edit=True, current=True)
    print("AnimSnap: created and activated hotkey set '{}'".format(name))
    return name


# ---------------------------------------------------------------------------
# Runtime Commands — appear in Maya's Hotkey Editor under 'Custom Scripts'
# ---------------------------------------------------------------------------

_RUNTIME_CMD_PREFIX = "animSnap_"

_SNAP_ACTIONS = {
    "snapAll": (
        "import anim_snap; anim_snap.snap()",
        "Snap (Translate + Rotate)",
    ),
    "snapTranslate": (
        "import anim_snap; anim_snap.snap_translate()",
        "Snap Translate Only",
    ),
    "snapRotate": (
        "import anim_snap; anim_snap.snap_rotate()",
        "Snap Rotate Only",
    ),
}

_ACTION_ORDER = ["snapAll", "snapTranslate", "snapRotate"]


def _ensure_runtime_commands():
    """Register (or update) runtime commands for each snap function.

    Commands appear in Maya's Hotkey Editor under 'Custom Scripts.AnimSnap'.
    """
    for cmd_suffix, (py_code, annotation) in _SNAP_ACTIONS.items():
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
                category="Custom Scripts.AnimSnap",
                commandLanguage="python",
                command=py_code,
            )
        print("AnimSnap: runtime command '{}' ready".format(rt_name))


# ---------------------------------------------------------------------------
# Hotkey Assignment
# ---------------------------------------------------------------------------

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
    """Assign a keyboard shortcut to a snap action.

    Caller must ensure a writable hotkey set is active and runtime
    commands are registered before calling this function.

    Returns True if assigned, False if the user cancelled (conflict).
    """
    display = _display_string(key, ctrl, alt, shift)
    nc_name = _RUNTIME_CMD_PREFIX + action_key + "NameCommand"
    rt_name = _RUNTIME_CMD_PREFIX + action_key
    annotation = _SNAP_ACTIONS[action_key][1]

    # Check for an existing binding on this key combination
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
                "'{}' is already assigned to:\n"
                "{}\n\n"
                "Overwrite with {}?".format(display, existing, annotation)
            ),
            button=["Overwrite", "Cancel"],
            defaultButton="Cancel",
            cancelButton="Cancel",
        )
        if result == "Cancel":
            return False

    # Create the nameCommand that wraps our runtime command
    cmds.nameCommand(nc_name, ann=annotation, sourceType="mel", command=rt_name)

    # Bind the hotkey
    hotkey_kw = {"k": key, "n": nc_name}
    if ctrl:
        hotkey_kw["ctl"] = True
    if alt:
        hotkey_kw["alt"] = True
    if shift:
        hotkey_kw["sht"] = True
    cmds.hotkey(**hotkey_kw)

    # Persist the display string for the UI
    cmds.optionVar(sv=("animSnap_hotkey_" + action_key, display))

    print("AnimSnap: hotkey '{}' -> {}".format(display, rt_name))
    return True


def _get_current_hotkey(action_key):
    """Return a human-readable string of the current hotkey, or empty string."""
    var_name = "animSnap_hotkey_" + action_key
    if cmds.optionVar(exists=var_name):
        return cmds.optionVar(q=var_name)
    return ""


def _clear_hotkey(action_key):
    """Remove the hotkey binding for the given action."""
    var_name = "animSnap_hotkey_" + action_key
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


# ---------------------------------------------------------------------------
# Qt key-to-Maya mapping
# ---------------------------------------------------------------------------

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
        _QT_KEY_TO_MAYA[getattr(key, "Key_F{}".format(i)).value] = "F{}".format(i)
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
    key_combo = seq[0]
    if hasattr(key_combo, "key"):
        # PySide6 — QKeyCombination
        key_enum = key_combo.key()
        modifiers = key_combo.keyboardModifiers()
        key_val = key_enum.value if hasattr(key_enum, "value") else int(key_enum)
        ctrl  = bool(modifiers & QtCore.Qt.KeyboardModifier.ControlModifier)
        alt   = bool(modifiers & QtCore.Qt.KeyboardModifier.AltModifier)
        shift = bool(modifiers & QtCore.Qt.KeyboardModifier.ShiftModifier)
    else:
        # PySide2 — plain int with modifier bits OR'd in
        combined = int(key_combo)
        key_val = combined & ~int(
            QtCore.Qt.ControlModifier
            | QtCore.Qt.AltModifier
            | QtCore.Qt.ShiftModifier
            | QtCore.Qt.MetaModifier
            | QtCore.Qt.KeypadModifier
        )
        ctrl  = bool(combined & int(QtCore.Qt.ControlModifier))
        alt   = bool(combined & int(QtCore.Qt.AltModifier))
        shift = bool(combined & int(QtCore.Qt.ShiftModifier))
    maya_key = _QT_KEY_TO_MAYA.get(key_val)
    if maya_key is None:
        return None
    return maya_key, ctrl, alt, shift


# ---------------------------------------------------------------------------
# Hotkey Setup Dialog
# ---------------------------------------------------------------------------

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
    """Dialog for assigning keyboard shortcuts to snap functions."""

    def __init__(self, parent=None):
        super(HotkeySetupDialog, self).__init__(parent)
        self.setObjectName(HOTKEY_WINDOW_OBJECT_NAME)
        self.setWindowTitle("AnimSnap — Setup Hotkeys")
        self.setWindowFlags(
            QtCore.Qt.Window
            | QtCore.Qt.WindowTitleHint
            | QtCore.Qt.WindowCloseButtonHint
        )
        self.setMinimumWidth(380)
        self.setStyleSheet(_HOTKEY_STYLESHEET)
        self._key_edits = {}
        self._current_labels = {}
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
            "Assign keyboard shortcuts to each snap function. "
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
            label_text = _SNAP_ACTIONS[action_key][1]
            lbl = QtWidgets.QLabel(label_text)
            lbl.setObjectName("lbl_section")
            grid.addWidget(lbl, row * 2, 0, QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)

            key_edit = QtWidgets.QKeySequenceEdit()
            if hasattr(key_edit, "setMaximumSequenceLength"):
                key_edit.setMaximumSequenceLength(1)
            current = _get_current_hotkey(action_key)
            if current:
                key_edit.setKeySequence(QtGui.QKeySequence.fromString(current))
            grid.addWidget(key_edit, row * 2, 1)
            self._key_edits[action_key] = key_edit

            current_lbl = QtWidgets.QLabel(
                "Current: {}".format(current) if current else "No shortcut assigned"
            )
            current_lbl.setObjectName("lbl_current")
            grid.addWidget(current_lbl, row * 2 + 1, 1)
            self._current_labels[action_key] = current_lbl

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
        btn_clear.setToolTip("Remove all hotkey assignments for snap functions")
        btn_clear.clicked.connect(self._on_clear)
        btn_row.addWidget(btn_clear)

        btn_row.addStretch()

        btn_apply = QtWidgets.QPushButton("Apply")
        btn_apply.setObjectName("btn_snap_all")
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
            # Defer rebuild so the combo widget fully finishes processing the
            # activated signal before we tear down and repopulate its items.
            QtCore.QTimer.singleShot(0, self._rebuild_set_combo)
            if new_set is None:
                return
        else:
            cmds.hotkeySet(choice, edit=True, current=True)
            print("AnimSnap: switched to hotkey set '{}'".format(choice))
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
        self._set_combo.update()
        self._refresh_hotkeys()

    def _refresh_hotkeys(self):
        """Update the key-sequence fields to reflect the active hotkey set."""
        for action_key, key_edit in self._key_edits.items():
            current = _get_current_hotkey(action_key)
            key_edit.clear()
            if current:
                key_edit.setKeySequence(QtGui.QKeySequence.fromString(current))
            self._current_labels[action_key].setText(
                "Current: {}".format(current) if current else "No shortcut assigned"
            )

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
                        "AnimSnap: could not map key '{}' for {} - unsupported key.".format(
                            seq.toString(), _SNAP_ACTIONS[action_key][1])
                    )
                continue
            maya_key, ctrl, alt, shift = parsed
            try:
                if assign_hotkey(action_key, maya_key, ctrl=ctrl, alt=alt, shift=shift):
                    applied += 1
                else:
                    skipped += 1
            except Exception as exc:
                cmds.warning("AnimSnap: failed to assign hotkey - {}".format(exc))

        if applied:
            # Save hotkeys so they persist between sessions
            cmds.savePrefs(hotkeys=True)
            msg = "<hl>AnimSnap</hl>  {} hotkey(s) assigned and saved.".format(applied)
            if skipped:
                msg += "  {} skipped.".format(skipped)
            cmds.inViewMessage(amg=msg, pos="midCenter", fade=True)
        elif skipped:
            cmds.inViewMessage(
                amg="<hl>AnimSnap</hl>  {} hotkey(s) skipped (conflicts).".format(skipped),
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
            amg="<hl>AnimSnap</hl>  All hotkeys cleared.",
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
