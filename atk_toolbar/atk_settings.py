"""ATK Settings — settings dialog for the Animation Tool Kit toolbar.

Opens a QDialog that lets the user:
  • Pick the toolbar layout (Layout tab): Full, Most used, Custom or
    Grouped, expert mode, rows, alignment, icon size, which tools show and
    in what order, custom groups, export / import.  Layout changes show on
    the toolbar straight away.
  • Choose where the toolbar docks (above the timeline, below the shelf,
    or vertically on the left/right edge of the viewport)
  • Toggle the inline Inbetweener slider and frame stepper
  • Toggle group separator visibility
  • View tool version info (About tab)
  • Reload the latest installed tool scripts without restarting Maya
    (Reload Scripts button)

All preferences are stored as Maya optionVars with an "atk_" prefix.
Clicking Apply rebuilds the toolbar immediately.
"""

import os

import maya.cmds as cmds
from maya import OpenMayaUI as omui

try:
    from PySide6 import QtCore, QtGui, QtWidgets
    from shiboken6 import wrapInstance
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets
    from shiboken2 import wrapInstance

from . import atk_loader
from . import atk_icons
from . import atk_layout

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
WINDOW_OBJECT_NAME = "ATKSettingsDialog"
WINDOW_TITLE       = "Animation Tool Kit — Settings"

# optionVar keys
OPT_ICON_SIZE        = "atk_toolbar_icon_size"        # int: 24, 32, 48
OPT_SHOW_TOOLTIPS    = "atk_toolbar_show_tooltips"    # int 0/1
OPT_SHOW_SEPARATORS  = "atk_toolbar_show_separators"  # int 0/1
OPT_ORIENTATION      = "atk_toolbar_orientation"      # str: "horizontal" | "vertical"
OPT_ICON_ALIGNMENT   = "atk_toolbar_icon_alignment"   # str: "left" | "center" | "right"
OPT_SHOW_INLINE_SLIDER = "atk_toolbar_show_inline_slider"  # int 0/1
OPT_SHOW_FRAME_STEPPER = "atk_toolbar_show_frame_stepper"  # int 0/1
OPT_DOCK_POSITION    = "atk_toolbar_dock_position"     # str: "above_timeline" | "below_shelf" | "left" | "right"

DOCK_POSITIONS = ("above_timeline", "below_shelf", "left", "right")

ICON_SIZES = [("Small  (24 px)", 24), ("Medium  (32 px)", 32), ("Large  (48 px)", 48)]

_LIST_STYLE = (
    "QListWidget { background:#333333; color:#cccccc; border:1px solid #555; }"
    "QListWidget::item:selected { background:#2e6da4; color:#ffffff; }"
)

_LIVE_DELAY_MS = 150   # batch quick Layout-tab clicks into one toolbar rebuild

# ---------------------------------------------------------------------------
# Stylesheet — shared dark theme, consistent with Reset Tool
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
    text-transform: uppercase;
}
QFrame#separator {
    background-color: #525252;
    border: none;
    max-height: 1px;
    min-height: 1px;
}
QTabWidget::pane {
    border: 1px solid #555555;
    background-color: #3c3c3c;
}
QTabBar::tab {
    background-color: #484848;
    color: #aaaaaa;
    padding: 6px 16px;
    border: 1px solid #555555;
    border-bottom: none;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}
QTabBar::tab:selected {
    background-color: #3c3c3c;
    color: #ffffff;
}
QGroupBox {
    border: 1px solid #555555;
    border-radius: 4px;
    margin-top: 8px;
    color: #aaaaaa;
    font-size: 10px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    padding: 0 4px;
}
QCheckBox {
    color: #cccccc;
    spacing: 6px;
}
QCheckBox::indicator {
    width: 14px;
    height: 14px;
    border: 1px solid #666666;
    border-radius: 3px;
    background-color: #4a4a4a;
}
QCheckBox::indicator:checked {
    background-color: #4FC3F7;
    border-color: #4FC3F7;
}
QRadioButton {
    color: #cccccc;
    spacing: 6px;
}
QRadioButton::indicator {
    width: 14px;
    height: 14px;
    border: 1px solid #666666;
    border-radius: 7px;
    background-color: #4a4a4a;
}
QRadioButton::indicator:checked {
    background-color: #4FC3F7;
    border-color: #4FC3F7;
}
QPushButton {
    background-color: #555555;
    color: #dddddd;
    border: 1px solid #666666;
    border-radius: 4px;
    padding: 6px 14px;
    font-size: 12px;
    min-height: 28px;
}
QPushButton:hover {
    background-color: #636363;
    border-color: #888888;
    color: #ffffff;
}
QPushButton:pressed {
    background-color: #444444;
}
QPushButton#btn_apply {
    background-color: #2e6da4;
    color: #ffffff;
    border: 1px solid #4088c0;
    font-weight: bold;
    font-size: 13px;
    min-height: 34px;
}
QPushButton#btn_apply:hover {
    background-color: #3a7ec0;
    border-color: #5599d4;
}
QPushButton#btn_apply:pressed {
    background-color: #205080;
}
QScrollArea {
    border: none;
    background-color: transparent;
}
QScrollArea > QWidget > QWidget {
    background-color: transparent;
}
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_pref_int(key, default):
    if cmds.optionVar(exists=key):
        return int(cmds.optionVar(q=key))
    return default


def _set_pref_int(key, value):
    cmds.optionVar(iv=(key, int(value)))


def _maya_main_window():
    ptr = omui.MQtUtil.mainWindow()
    if ptr is None:
        return None
    return wrapInstance(int(ptr), QtWidgets.QWidget)


def _hsep():
    """Return a 1px horizontal separator frame."""
    line = QtWidgets.QFrame()
    line.setObjectName("separator")
    line.setFrameShape(QtWidgets.QFrame.HLine)
    return line


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------

class ATKSettingsDialog(QtWidgets.QDialog):
    """Settings dialog for the ATK toolbar."""

    def __init__(self, rebuild_callback=None, parent=None):
        if parent is None:
            parent = _maya_main_window()
        super(ATKSettingsDialog, self).__init__(parent)

        self.rebuild_callback = rebuild_callback
        self.setObjectName(WINDOW_OBJECT_NAME)
        self.setWindowTitle(WINDOW_TITLE)
        self.setMinimumWidth(620)
        self.setStyleSheet(_STYLESHEET)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, False)

        self._build_ui()
        self._load_prefs()

    # ── UI construction ──────────────────────────────────────────────────────

    def _build_ui(self):
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # Title
        title = QtWidgets.QLabel("Animation Tool Kit")
        title.setObjectName("lbl_title")
        sub = QtWidgets.QLabel("Toolbar Settings")
        sub.setObjectName("lbl_subtitle")
        root.addWidget(title)
        root.addWidget(sub)
        root.addWidget(_hsep())

        # Tab widget
        self._tabs = QtWidgets.QTabWidget()
        root.addWidget(self._tabs)

        self._loading = True
        self._live_timer = QtCore.QTimer(self)
        self._live_timer.setSingleShot(True)
        self._live_timer.setInterval(_LIVE_DELAY_MS)
        self._live_timer.timeout.connect(self._request_rebuild)

        self._build_layout_tab()
        self._build_appearance_tab()
        self._build_workspace_tab()
        self._build_tools_tab()
        self._build_about_tab()

        root.addWidget(_hsep())

        # Buttons
        btn_row = QtWidgets.QHBoxLayout()
        btn_reset = QtWidgets.QPushButton("Reset Defaults")
        btn_reset.clicked.connect(self._reset_defaults)

        btn_reload = QtWidgets.QPushButton("Reload Scripts")
        btn_reload.setToolTip(
            "Re-import the latest installed toolbar and tool scripts without\n"
            "restarting Maya. Use this after installing or updating ATK.\n"
            "Open tool windows are closed and reopened on the new code."
        )
        btn_reload.clicked.connect(self._reload_scripts)

        self._btn_apply = QtWidgets.QPushButton("Apply")
        self._btn_apply.setObjectName("btn_apply")
        self._btn_apply.clicked.connect(self._apply)

        btn_close = QtWidgets.QPushButton("Close")
        btn_close.clicked.connect(self.hide)

        btn_row.addWidget(btn_reset)
        btn_row.addWidget(btn_reload)
        btn_row.addStretch()
        btn_row.addWidget(self._btn_apply)
        btn_row.addWidget(btn_close)
        root.addLayout(btn_row)

    # ── Layout tab ───────────────────────────────────────────────────────────

    def _build_layout_tab(self):
        tab = QtWidgets.QWidget()
        root = QtWidgets.QHBoxLayout(tab)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(10)

        # Left: options (scrolls when the dialog is short).
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        left_widget = QtWidgets.QWidget()
        left = QtWidgets.QVBoxLayout(left_widget)
        left.setContentsMargins(0, 0, 4, 0)
        left.setSpacing(8)
        scroll.setWidget(left_widget)
        root.addWidget(scroll, 3)

        note = QtWidgets.QLabel("Changes show on the toolbar straight away.")
        note.setObjectName("lbl_subtitle")
        left.addWidget(note)

        # Preset + expert
        preset_group = QtWidgets.QGroupBox("Layout")
        form = QtWidgets.QFormLayout(preset_group)
        self._preset_combo = QtWidgets.QComboBox()
        tips = {
            "full": "Every tool, as in earlier versions.",
            "most_used": "Your most used tools, the rest under More.",
            "custom": "The tools you tick, in your order.",
            "grouped": "One button per group. Unfold the groups you want.",
        }
        for preset in atk_layout.PRESETS:
            self._preset_combo.addItem(atk_layout.PRESET_LABELS[preset], preset)
            self._preset_combo.setItemData(self._preset_combo.count() - 1,
                                           tips[preset], QtCore.Qt.ToolTipRole)
        form.addRow("Preset", self._preset_combo)
        self._expert_cb = QtWidgets.QCheckBox("Expert mode")
        self._expert_cb.setToolTip("Smaller icons, tighter spacing, no separators. "
                                   "Works with any preset.")
        form.addRow("", self._expert_cb)
        self._most_used_spin = QtWidgets.QSpinBox()
        self._most_used_spin.setRange(atk_layout.MOST_USED_MIN, atk_layout.MOST_USED_MAX)
        self._most_used_spin.setToolTip("How many tools Most used shows on the bar.")
        form.addRow("Most used", self._most_used_spin)
        left.addWidget(preset_group)

        # Size and placement
        size_group = QtWidgets.QGroupBox("Size and placement")
        form = QtWidgets.QFormLayout(size_group)
        self._icon_size_combo = QtWidgets.QComboBox()
        for label, px in (("Small", 24), ("Medium", 32), ("Large", 48)):
            self._icon_size_combo.addItem(label, px)
        form.addRow("Icon size", self._icon_size_combo)
        self._lines_spin = QtWidgets.QSpinBox()
        self._lines_spin.setRange(atk_layout.LINES_MIN, atk_layout.LINES_MAX)
        self._lines_spin.setToolTip("Rows on a top or bottom bar, columns on a side bar.")
        form.addRow("Rows / columns", self._lines_spin)
        self._halign_combo = QtWidgets.QComboBox()
        for label, value in (("Left", "left"), ("Centre", "center"), ("Right", "right")):
            self._halign_combo.addItem(label, value)
        form.addRow("Align (top/bottom bar)", self._halign_combo)
        self._valign_combo = QtWidgets.QComboBox()
        for label, value in (("Top", "top"), ("Centre", "center"), ("Bottom", "bottom")):
            self._valign_combo.addItem(label, value)
        form.addRow("Align (side bar)", self._valign_combo)
        left.addWidget(size_group)

        # Built-in groups
        self._groups_box = QtWidgets.QGroupBox("Grouped: open on the bar")
        grid = QtWidgets.QGridLayout(self._groups_box)
        self._group_open_checks = {}
        groups = atk_layout.registry_groups(atk_loader.TOOL_REGISTRY, atk_loader.GROUP_ORDER)
        for n, group in enumerate(groups):
            cb = QtWidgets.QCheckBox(atk_layout.group_label(group))
            cb.setToolTip("Ticked: tools show on the bar. Unticked: one folded button.")
            self._group_open_checks[group] = cb
            grid.addWidget(cb, n // 2, n % 2)
        left.addWidget(self._groups_box)

        # Custom groups
        self._custom_box = QtWidgets.QGroupBox("My groups  (Custom and Grouped)")
        cg = QtWidgets.QVBoxLayout(self._custom_box)
        self._custom_list = QtWidgets.QListWidget()
        self._custom_list.setMaximumHeight(90)
        self._custom_list.setStyleSheet(_LIST_STYLE)
        cg.addWidget(self._custom_list)
        self._custom_open_cb = QtWidgets.QCheckBox("Open on the bar")
        cg.addWidget(self._custom_open_cb)
        row = QtWidgets.QHBoxLayout()
        for text, slot in (("New", self._new_custom_group), ("Tools...", self._edit_custom_tools),
                           ("Rename", self._rename_custom_group),
                           ("Delete", self._delete_custom_group)):
            b = QtWidgets.QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        cg.addLayout(row)
        left.addWidget(self._custom_box)

        # Usage, reset, export / import
        more_group = QtWidgets.QGroupBox("Layout file and usage")
        grid = QtWidgets.QGridLayout(more_group)
        for n, (text, slot, tip) in enumerate((
                ("Export...", self._export_layout, "Save this layout to a file."),
                ("Import...", self._import_layout, "Load a layout file."),
                ("Reset layout", self._reset_layout, "Back to Full with every tool."),
                ("Reset usage", self._reset_usage, "Forget the launch counts Most used uses."))):
            b = QtWidgets.QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            grid.addWidget(b, n // 2, n % 2)
        left.addWidget(more_group)
        left.addStretch()

        # Right: the tool list.
        right = QtWidgets.QVBoxLayout()
        right.setSpacing(6)
        title = QtWidgets.QLabel("TOOLS")
        title.setObjectName("lbl_section")
        right.addWidget(title)
        hint = QtWidgets.QLabel("Tick to show. Drag to reorder (Custom, Grouped).")
        hint.setObjectName("lbl_subtitle")
        hint.setWordWrap(True)
        right.addWidget(hint)
        self._tool_list = QtWidgets.QListWidget()
        self._tool_list.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)
        self._tool_list.setDefaultDropAction(QtCore.Qt.MoveAction)
        self._tool_list.setIconSize(QtCore.QSize(20, 20))
        self._tool_list.setStyleSheet(_LIST_STYLE)
        right.addWidget(self._tool_list, 1)
        row = QtWidgets.QHBoxLayout()
        for text, step in (("Up", -1), ("Down", 1)):
            b = QtWidgets.QPushButton(text)
            b.clicked.connect(lambda checked=False, d=step: self._move_tool(d))
            row.addWidget(b)
        show_all = QtWidgets.QPushButton("Show all")
        show_all.clicked.connect(self._show_all_tools)
        row.addWidget(show_all)
        right.addLayout(row)
        root.addLayout(right, 2)

        # Live preview: every change is saved and the toolbar rebuilt.
        self._preset_combo.currentIndexChanged.connect(self._layout_changed)
        self._expert_cb.toggled.connect(self._layout_changed)
        self._most_used_spin.valueChanged.connect(self._layout_changed)
        self._icon_size_combo.currentIndexChanged.connect(self._layout_changed)
        self._lines_spin.valueChanged.connect(self._layout_changed)
        self._halign_combo.currentIndexChanged.connect(self._layout_changed)
        self._valign_combo.currentIndexChanged.connect(self._layout_changed)
        for cb in self._group_open_checks.values():
            cb.toggled.connect(self._layout_changed)
        self._custom_list.currentRowChanged.connect(self._custom_selected)
        self._custom_open_cb.toggled.connect(self._custom_open_toggled)
        self._tool_list.itemChanged.connect(self._layout_changed)
        self._tool_list.model().rowsMoved.connect(self._layout_changed)

        self._custom_groups = []
        self._tabs.addTab(tab, "Layout")

    def select_tab(self, name):
        if not name:
            return
        for i in range(self._tabs.count()):
            if self._tabs.tabText(i) == name:
                self._tabs.setCurrentIndex(i)
                return

    @staticmethod
    def _tool_item_text(tool_id):
        tool = atk_loader._tool_by_id(tool_id)
        text = tool["label"] if tool else tool_id
        if not atk_loader.is_tool_installed(tool_id):
            text += "  (not installed)"
        return text

    def _load_layout(self):
        """Fill the Layout tab from the stored settings."""
        self._loading = True
        try:
            settings = atk_loader.get_layout_settings()
            self._set_combo(self._preset_combo, settings["preset"])
            self._expert_cb.setChecked(settings["expert"])
            self._most_used_spin.setValue(settings["most_used_count"])
            self._lines_spin.setValue(settings["lines"])
            self._set_combo(self._valign_combo, settings["valign"])
            self._set_combo(self._icon_size_combo,
                           _get_pref_int(OPT_ICON_SIZE, atk_layout.ICON_SIZE_DEFAULT), 0)
            align = (cmds.optionVar(q=OPT_ICON_ALIGNMENT)
                     if cmds.optionVar(exists=OPT_ICON_ALIGNMENT) else "center")
            self._set_combo(self._halign_combo, align, 1)
            for group, cb in self._group_open_checks.items():
                cb.setChecked(bool(settings["group_open"].get(group)))

            self._tool_list.clear()
            hidden = set(settings["hidden"])
            for tool_id in settings["order"]:
                tool = atk_loader._tool_by_id(tool_id)
                if tool is None:
                    continue
                item = QtWidgets.QListWidgetItem(self._tool_item_text(tool_id))
                item.setData(QtCore.Qt.UserRole, tool_id)
                item.setToolTip(tool["tooltip"])
                item.setIcon(atk_icons.load_or_generate_icon(
                    tool["icon_file"], tool["icon_key"], tool["group"], size=20))
                item.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable
                              | QtCore.Qt.ItemIsUserCheckable | QtCore.Qt.ItemIsDragEnabled)
                item.setCheckState(QtCore.Qt.Unchecked if tool_id in hidden
                                   else QtCore.Qt.Checked)
                self._tool_list.addItem(item)

            self._custom_groups = [dict(g, tools=list(g["tools"]))
                                   for g in settings["custom_groups"]]
            self._refresh_custom_list()
            self._update_layout_enabled()
        finally:
            self._loading = False

    @staticmethod
    def _set_combo(combo, value, fallback=0):
        index = combo.findData(value)
        combo.setCurrentIndex(index if index >= 0 else fallback)

    def _collect_layout(self):
        settings = atk_loader.get_layout_settings()
        settings["preset"] = self._preset_combo.currentData()
        settings["expert"] = self._expert_cb.isChecked()
        settings["most_used_count"] = self._most_used_spin.value()
        settings["lines"] = self._lines_spin.value()
        settings["valign"] = self._valign_combo.currentData()
        order, hidden = [], []
        for row in range(self._tool_list.count()):
            item = self._tool_list.item(row)
            tool_id = item.data(QtCore.Qt.UserRole)
            order.append(tool_id)
            if item.checkState() != QtCore.Qt.Checked:
                hidden.append(tool_id)
        settings["order"] = order
        settings["hidden"] = hidden
        settings["group_open"] = {g: cb.isChecked() for g, cb in self._group_open_checks.items()}
        settings["custom_groups"] = [dict(g, tools=list(g["tools"])) for g in self._custom_groups]
        return settings

    def _save_layout(self):
        atk_loader.save_layout_settings(self._collect_layout())
        _set_pref_int(OPT_ICON_SIZE, self._icon_size_combo.currentData())
        cmds.optionVar(sv=(OPT_ICON_ALIGNMENT, self._halign_combo.currentData()))

    def _layout_changed(self, *args):
        if self._loading:
            return
        self._update_layout_enabled()
        self._save_layout()
        self._live_timer.start()

    def _update_layout_enabled(self):
        preset = self._preset_combo.currentData()
        self._most_used_spin.setEnabled(preset == "most_used")
        self._groups_box.setEnabled(preset == "grouped")
        self._custom_box.setEnabled(preset in ("custom", "grouped"))
        has_group = self._custom_list.currentRow() >= 0
        self._custom_open_cb.setEnabled(has_group)

    def _move_tool(self, step):
        row = self._tool_list.currentRow()
        new = row + step
        if row < 0 or not 0 <= new < self._tool_list.count():
            return
        self._loading = True
        item = self._tool_list.takeItem(row)
        self._tool_list.insertItem(new, item)
        self._tool_list.setCurrentRow(new)
        self._loading = False
        self._layout_changed()

    def _show_all_tools(self):
        self._loading = True
        for row in range(self._tool_list.count()):
            self._tool_list.item(row).setCheckState(QtCore.Qt.Checked)
        self._loading = False
        self._layout_changed()

    # Custom groups

    def _refresh_custom_list(self, select=None):
        was = self._loading
        self._loading = True
        self._custom_list.clear()
        for g in self._custom_groups:
            self._custom_list.addItem("{}  ({} tools)".format(g["name"], len(g["tools"])))
        if select is not None and 0 <= select < len(self._custom_groups):
            self._custom_list.setCurrentRow(select)
        self._custom_selected(self._custom_list.currentRow())
        self._loading = was

    def _custom_selected(self, row):
        was = self._loading
        self._loading = True
        if 0 <= row < len(self._custom_groups):
            self._custom_open_cb.setChecked(self._custom_groups[row]["open"])
        else:
            self._custom_open_cb.setChecked(False)
        self._custom_open_cb.setEnabled(row >= 0)
        self._loading = was

    def _custom_open_toggled(self, checked):
        row = self._custom_list.currentRow()
        if self._loading or not 0 <= row < len(self._custom_groups):
            return
        self._custom_groups[row]["open"] = bool(checked)
        self._layout_changed()

    def _ask_group_name(self, title, current=""):
        name, ok = QtWidgets.QInputDialog.getText(self, title, "Group name:", text=current)
        name = " ".join((name or "").split())[:atk_layout.MAX_GROUP_NAME]
        if not ok or not name:
            return None
        taken = {g["name"].lower() for g in self._custom_groups if g["name"] != current}
        if name.lower() in taken:
            QtWidgets.QMessageBox.warning(self, title, "That name is already used.")
            return None
        return name

    def _new_custom_group(self):
        if len(self._custom_groups) >= atk_layout.MAX_CUSTOM_GROUPS:
            QtWidgets.QMessageBox.information(
                self, "New Group", "You can have up to {} groups.".format(
                    atk_layout.MAX_CUSTOM_GROUPS))
            return
        name = self._ask_group_name("New Group")
        if not name:
            return
        tools = self._pick_tools(name, [])
        if tools is None:
            return
        self._custom_groups.append({"name": name, "tools": tools, "open": False})
        self._refresh_custom_list(select=len(self._custom_groups) - 1)
        self._layout_changed()

    def _rename_custom_group(self):
        row = self._custom_list.currentRow()
        if not 0 <= row < len(self._custom_groups):
            return
        name = self._ask_group_name("Rename Group", self._custom_groups[row]["name"])
        if name:
            self._custom_groups[row]["name"] = name
            self._refresh_custom_list(select=row)
            self._layout_changed()

    def _edit_custom_tools(self):
        row = self._custom_list.currentRow()
        if not 0 <= row < len(self._custom_groups):
            return
        group = self._custom_groups[row]
        tools = self._pick_tools(group["name"], group["tools"])
        if tools is not None:
            group["tools"] = tools
            self._refresh_custom_list(select=row)
            self._layout_changed()

    def _delete_custom_group(self):
        row = self._custom_list.currentRow()
        if not 0 <= row < len(self._custom_groups):
            return
        del self._custom_groups[row]
        self._refresh_custom_list(select=min(row, len(self._custom_groups) - 1))
        self._layout_changed()

    def _pick_tools(self, name, current):
        """Small checklist dialog. Returns the ticked tool ids, or None."""
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Tools in {}".format(name))
        dialog.setStyleSheet(_STYLESHEET)
        lay = QtWidgets.QVBoxLayout(dialog)
        lst = QtWidgets.QListWidget()
        lst.setStyleSheet(_LIST_STYLE)
        order = [self._tool_list.item(r).data(QtCore.Qt.UserRole)
                 for r in range(self._tool_list.count())]
        # Tools already in the group first, in the group's order.
        for tool_id in list(current) + [t for t in order if t not in current]:
            tool = atk_loader._tool_by_id(tool_id)
            if tool is None:
                continue
            item = QtWidgets.QListWidgetItem(tool["label"])
            item.setData(QtCore.Qt.UserRole, tool_id)
            item.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsUserCheckable)
            item.setCheckState(QtCore.Qt.Checked if tool_id in current else QtCore.Qt.Unchecked)
            lst.addItem(item)
        lay.addWidget(lst)
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        lay.addWidget(buttons)
        dialog.resize(280, 420)
        if dialog.exec() != QtWidgets.QDialog.Accepted:
            return None
        return [lst.item(r).data(QtCore.Qt.UserRole) for r in range(lst.count())
                if lst.item(r).checkState() == QtCore.Qt.Checked]

    # Export / import / reset

    def _export_layout(self):
        path, _filter = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export Layout", "atk_layout.json", "ATK layout (*.json)")
        if not path:
            return
        text = atk_layout.export_layout(
            self._collect_layout(), self._icon_size_combo.currentData(),
            self._halign_combo.currentData())
        try:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(text)
        except (IOError, OSError) as exc:
            QtWidgets.QMessageBox.warning(self, "Export Layout",
                                          "Could not save the file:\n{}".format(exc))

    def _import_layout(self):
        path, _filter = QtWidgets.QFileDialog.getOpenFileName(
            self, "Import Layout", "", "ATK layout (*.json);;All files (*)")
        if not path:
            return
        try:
            if os.path.getsize(path) > 1024 * 1024:
                raise ValueError("The file is too big to be an ATK layout.")
            with open(path, "r", encoding="utf-8") as handle:
                settings, icon_size, align = atk_layout.import_layout(
                    handle.read(), atk_loader.TOOL_REGISTRY, atk_loader.GROUP_ORDER)
        except (IOError, OSError, UnicodeDecodeError) as exc:
            QtWidgets.QMessageBox.warning(self, "Import Layout",
                                          "Could not read the file:\n{}".format(exc))
            return
        except ValueError as exc:
            QtWidgets.QMessageBox.warning(self, "Import Layout", str(exc))
            return
        atk_loader.save_layout_settings(settings)
        _set_pref_int(OPT_ICON_SIZE, icon_size)
        cmds.optionVar(sv=(OPT_ICON_ALIGNMENT, align))
        self._load_layout()
        self._request_rebuild()

    def _reset_layout(self):
        answer = QtWidgets.QMessageBox.question(
            self, "Reset Layout", "Go back to the Full layout with every tool shown?")
        if answer != QtWidgets.QMessageBox.Yes:
            return
        atk_loader.reset_layout_settings()
        _set_pref_int(OPT_ICON_SIZE, atk_layout.ICON_SIZE_DEFAULT)
        cmds.optionVar(sv=(OPT_ICON_ALIGNMENT, "center"))
        self._load_layout()
        self._request_rebuild()

    def _reset_usage(self):
        answer = QtWidgets.QMessageBox.question(
            self, "Reset Usage", "Forget how often each tool was used?")
        if answer != QtWidgets.QMessageBox.Yes:
            return
        atk_loader.reset_usage()
        if self._preset_combo.currentData() == "most_used":
            self._request_rebuild()

    def _build_appearance_tab(self):
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)

        # Orientation
        orient_group = QtWidgets.QGroupBox("Orientation")
        orient_layout = QtWidgets.QHBoxLayout(orient_group)
        self._rb_horizontal = QtWidgets.QRadioButton("Horizontal")
        self._rb_vertical   = QtWidgets.QRadioButton("Vertical")
        orient_layout.addWidget(self._rb_horizontal)
        orient_layout.addWidget(self._rb_vertical)
        orient_layout.addStretch()
        layout.addWidget(orient_group)

        size_note = QtWidgets.QLabel("Icon size, rows and alignment are on the Layout tab.")
        size_note.setObjectName("lbl_subtitle")
        layout.addWidget(size_note)

        # Display options
        disp_group = QtWidgets.QGroupBox("Display")
        disp_layout = QtWidgets.QVBoxLayout(disp_group)
        self._cb_tooltips = QtWidgets.QCheckBox("Show tooltips on hover")
        self._cb_separators = QtWidgets.QCheckBox("Show separators between tool groups")
        disp_layout.addWidget(self._cb_tooltips)
        disp_layout.addWidget(self._cb_separators)
        layout.addWidget(disp_group)

        layout.addStretch()
        self._tabs.addTab(tab, "Appearance")

    def _build_workspace_tab(self):
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)

        note = QtWidgets.QLabel("Controls where the toolbar docks.")
        note.setObjectName("lbl_subtitle")
        note.setWordWrap(True)
        layout.addWidget(note)

        dock_group = QtWidgets.QGroupBox("Docked Position")
        dock_layout = QtWidgets.QVBoxLayout(dock_group)

        self._rb_dock_timeline = QtWidgets.QRadioButton("Above the timeline  — horizontal bar")
        self._rb_dock_shelf    = QtWidgets.QRadioButton("Below the shelf  — horizontal bar")
        self._rb_dock_left     = QtWidgets.QRadioButton("Left of the viewport  — vertical bar")
        self._rb_dock_right    = QtWidgets.QRadioButton("Right of the viewport  — vertical bar")

        dock_layout.addWidget(self._rb_dock_timeline)
        dock_layout.addWidget(self._rb_dock_shelf)
        dock_layout.addWidget(self._rb_dock_left)
        dock_layout.addWidget(self._rb_dock_right)

        dock_note = QtWidgets.QLabel(
            "Applying a new position re-docks the toolbar immediately.\n"
            "You can still drag the bar off its dock and float it anywhere."
        )
        dock_note.setObjectName("lbl_subtitle")
        dock_note.setWordWrap(True)
        dock_layout.addWidget(dock_note)
        layout.addWidget(dock_group)

        layout.addStretch()
        self._tabs.addTab(tab, "Workspace")

    def _build_tools_tab(self):
        tab = QtWidgets.QWidget()
        outer = QtWidgets.QVBoxLayout(tab)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(6)

        self._inline_widget_checks = {}

        widget_label = QtWidgets.QLabel("TOOLBAR WIDGETS")
        widget_label.setObjectName("lbl_section")
        outer.addWidget(widget_label)

        slider_cb = QtWidgets.QCheckBox("Inbetweener Slider")
        slider_cb.setToolTip("Show/hide the inline Inbetweener slider widget on the toolbar.")
        self._inline_widget_checks[OPT_SHOW_INLINE_SLIDER] = slider_cb
        outer.addWidget(slider_cb)

        frame_cb = QtWidgets.QCheckBox("Insert/Remove Frame Stepper")
        frame_cb.setToolTip("Show/hide the inline frame insert/remove control next to the slider.")
        self._inline_widget_checks[OPT_SHOW_FRAME_STEPPER] = frame_cb
        outer.addWidget(frame_cb)

        outer.addSpacing(8)
        note = QtWidgets.QLabel("Pick which tools show, and their order, on the Layout tab.")
        note.setObjectName("lbl_subtitle")
        note.setWordWrap(True)
        outer.addWidget(note)
        outer.addStretch()
        self._tabs.addTab(tab, "Widgets")

    def _build_about_tab(self):
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        header = QtWidgets.QLabel("Animation Tool Kit Toolbar")
        header.setObjectName("lbl_title")
        layout.addWidget(header)

        # Read the version from the package so this label cannot drift from
        # the installed release again.
        import sys as _sys
        _package = _sys.modules.get(__name__.rpartition(".")[0])
        version_label = QtWidgets.QLabel(
            "Toolbar version {}".format(getattr(_package, "__version__", "unknown")))
        version_label.setObjectName("lbl_subtitle")
        layout.addWidget(version_label)
        layout.addWidget(_hsep())

        tools_label = QtWidgets.QLabel("INCLUDED TOOLS")
        tools_label.setObjectName("lbl_section")
        layout.addWidget(tools_label)

        for tool in atk_loader.TOOL_REGISTRY:
            row = QtWidgets.QHBoxLayout()
            name = QtWidgets.QLabel("  {}".format(tool["label"]))
            ver  = QtWidgets.QLabel("v{}".format(tool["version"]))
            ver.setObjectName("lbl_subtitle")
            row.addWidget(name)
            row.addStretch()
            row.addWidget(ver)
            layout.addLayout(row)

        layout.addStretch()
        self._tabs.addTab(tab, "About")

    # ── Preference read/write ────────────────────────────────────────────────

    def _load_prefs(self):
        # Orientation
        orient = cmds.optionVar(q=OPT_ORIENTATION) if cmds.optionVar(exists=OPT_ORIENTATION) else "horizontal"
        self._rb_vertical.setChecked(orient == "vertical")
        self._rb_horizontal.setChecked(orient != "vertical")

        # Docked position
        dock_pos = self._get_dock_pref()
        self._rb_dock_shelf.setChecked(dock_pos == "below_shelf")
        self._rb_dock_left.setChecked(dock_pos == "left")
        self._rb_dock_right.setChecked(dock_pos == "right")
        self._rb_dock_timeline.setChecked(dock_pos not in ("below_shelf", "left", "right"))

        # Display
        self._cb_tooltips.setChecked(bool(_get_pref_int(OPT_SHOW_TOOLTIPS, 1)))
        self._cb_separators.setChecked(bool(_get_pref_int(OPT_SHOW_SEPARATORS, 1)))

        for pref_key, cb in self._inline_widget_checks.items():
            cb.setChecked(bool(_get_pref_int(pref_key, 1)))

        self._load_layout()

    @staticmethod
    def _get_dock_pref():
        if cmds.optionVar(exists=OPT_DOCK_POSITION):
            val = cmds.optionVar(q=OPT_DOCK_POSITION)
            if val in DOCK_POSITIONS:
                return val
        return "above_timeline"

    def _selected_dock_position(self):
        if self._rb_dock_shelf.isChecked():
            return "below_shelf"
        if self._rb_dock_left.isChecked():
            return "left"
        if self._rb_dock_right.isChecked():
            return "right"
        return "above_timeline"

    def _apply(self):
        # Orientation
        orient = "vertical" if self._rb_vertical.isChecked() else "horizontal"
        cmds.optionVar(sv=(OPT_ORIENTATION, orient))

        # Docked position
        old_dock = self._get_dock_pref()
        new_dock = self._selected_dock_position()
        cmds.optionVar(sv=(OPT_DOCK_POSITION, new_dock))

        # Display
        _set_pref_int(OPT_SHOW_TOOLTIPS, int(self._cb_tooltips.isChecked()))
        _set_pref_int(OPT_SHOW_SEPARATORS, int(self._cb_separators.isChecked()))

        # Layout (already live, saved again so Apply is never behind)
        self._save_layout()

        for pref_key, cb in self._inline_widget_checks.items():
            _set_pref_int(pref_key, int(cb.isChecked()))

        if new_dock != old_dock:
            # Re-dock: recreate the toolbar at the new position (this also
            # rebuilds it, so the plain rebuild below would be redundant).
            self._redock_toolbar()
        else:
            self._request_rebuild()

    @staticmethod
    def _redock_toolbar():
        """Recreate the toolbar docked at the currently saved dock position.

        Deferred with a timer so the workspaceControl (which may host the
        widget whose gear button opened this dialog) is not torn down while
        its event handler is still on the call stack.
        """
        try:
            from . import atk_toolbar
        except Exception as exc:
            cmds.warning("ATK Toolbar: could not re-dock toolbar: {}".format(exc))
            return
        QtCore.QTimer.singleShot(0, atk_toolbar.show)

    def _request_rebuild(self):
        """Rebuild the toolbar, surviving a stale callback.

        The stored callback points at the toolbar widget that existed when
        this dialog was opened; a re-dock recreates that widget, so fall back
        to the module-level rebuild when the old one is gone.
        """
        if callable(self.rebuild_callback):
            try:
                self.rebuild_callback()
                return
            except RuntimeError:
                self.rebuild_callback = None   # widget was deleted
        try:
            from . import atk_toolbar
            atk_toolbar.rebuild_current()
        except Exception as exc:
            cmds.warning("ATK Toolbar: rebuild failed: {}".format(exc))

    def _reset_defaults(self):
        cmds.optionVar(sv=(OPT_ORIENTATION, "horizontal"))
        cmds.optionVar(sv=(OPT_ICON_ALIGNMENT, "center"))
        cmds.optionVar(sv=(OPT_DOCK_POSITION, "above_timeline"))
        _set_pref_int(OPT_ICON_SIZE, atk_layout.ICON_SIZE_DEFAULT)
        _set_pref_int(OPT_SHOW_TOOLTIPS, 1)
        _set_pref_int(OPT_SHOW_SEPARATORS, 1)
        _set_pref_int(OPT_SHOW_INLINE_SLIDER, 1)
        _set_pref_int(OPT_SHOW_FRAME_STEPPER, 1)
        atk_loader.reset_layout_settings()
        self._load_prefs()
        self._request_rebuild()

    # ── Script reloading ─────────────────────────────────────────────────────

    def _reload_scripts(self):
        """Re-import the latest installed scripts without restarting Maya.

        Closes open tool windows, purges every registered tool module and the
        atk_toolbar package itself, then rebuilds the toolbar from the fresh
        code and reopens the tools that were open, so everything on the strip
        runs the newly installed scripts.
        """
        try:
            reopen = close_tool_windows()
            purged, plugin_notes = atk_loader.reload_tool_modules()
        except Exception as exc:
            cmds.warning("ATK Toolbar: script reload failed: {}".format(exc))
            return

        summary = "Reloaded the toolbar and {} tool module{}.".format(
            len(purged), "" if len(purged) == 1 else "s")
        if reopen:
            summary += " Reopened: {}.".format(", ".join(
                t["label"] for t in atk_loader.TOOL_REGISTRY if t["id"] in reopen))
        if plugin_notes:
            for note in plugin_notes:
                cmds.warning("ATK Toolbar: {}".format(note))
            summary += "\n\n" + "\n".join(plugin_notes)
        QtWidgets.QMessageBox.information(self, "Reload Scripts", summary)

        # This dialog belongs to the old package; the next gear click opens
        # a fresh one. Rebuild after this handler returns, as on re-dock.
        global _dialog_instance
        _dialog_instance = None
        self.close()
        self.deleteLater()
        atk_loader.purge_toolbar_modules()
        QtCore.QTimer.singleShot(0, lambda: _show_fresh_toolbar(reopen, summary))

    def _refresh_installed_states(self):
        """Update the Layout tab's 'not installed' notes."""
        for row in range(self._tool_list.count()):
            item = self._tool_list.item(row)
            item.setText(self._tool_item_text(item.data(QtCore.Qt.UserRole)))


# ---------------------------------------------------------------------------
# Singleton show helper
# ---------------------------------------------------------------------------
_dialog_instance = None


def close_tool_windows():
    """Close every open window built from a registered tool's modules.

    Returns the ids of the tools that had a window open, so Reload Scripts
    can reopen them on the reloaded code. Windows embedded in the toolbar
    (inline sliders) are skipped; the toolbar rebuild recreates those.
    Dockable windows are closed by deleting their Maya workspaceControl.
    """
    app = QtWidgets.QApplication.instance()
    if app is None:
        return []
    roots = atk_loader.tool_module_roots()

    def owner(widget):
        return roots.get(type(widget).__module__.split(".")[0])

    outermost = []
    for widget in app.allWidgets():
        try:
            if owner(widget) is None or not widget.isVisible():
                continue
            parent, inside = widget.parentWidget(), False
            while parent is not None:
                if owner(parent) or type(parent).__module__.split(".")[0] == __name__.split(".")[0]:
                    inside = True        # nested in a tool window, or in the toolbar
                    break
                parent = parent.parentWidget()
            if not inside:
                outermost.append(widget)
        except RuntimeError:             # C++ object already deleted
            continue

    reopen = []
    for widget in outermost:
        try:
            tool_id = owner(widget)
            control, embedded = _tool_workspace_control(widget)
            if embedded:
                # An overlay or helper the tool placed inside Maya's own UI
                # (Timeline Ticks / Bookmarks draw on the Time Slider). It is
                # not a window: the tool's shutdown() removes it. Deleting
                # its enclosing control here deleted Maya's Time Slider.
                continue
            if control:
                cmds.deleteUI(control)
            else:
                # Plain Qt close: Maya's dockable mixin overrides close() to
                # act on a workspaceControl, which a floating window lacks.
                QtWidgets.QWidget.close(widget.window())
            if tool_id not in reopen:
                reopen.append(tool_id)
        except Exception as exc:
            cmds.warning("ATK Toolbar: could not close a tool window: {}".format(exc))
    return reopen


# Maya's own UI elements (Windows > UI Elements and the main panes). Reload
# Scripts must never delete these, whatever a tool has parented inside them.
_MAYA_UI_CONTROLS = frozenset((
    "TimeSlider", "RangeSlider", "Shelf", "StatusLine", "ToolBox",
    "CommandLine", "HelpLine", "ChannelBoxLayerEditor", "AttributeEditor",
    "Outliner", "ToolSettings", "MainPane", "ToolBar", "PlaybackControls",
))


def _is_maya_ui_object(name):
    """True when ``name`` is a Maya UI object (control, layout, panel...)."""
    try:
        return bool(cmds.objectTypeUI(name))
    except Exception:
        return False


def _tool_workspace_control(widget):
    """Find the workspaceControl hosting a tool widget.

    Returns ``(control, embedded)``. ``control`` is the name of the tool's
    own workspaceControl, or None for a plain floating window. ``embedded``
    is True when the widget sits inside Maya's own UI instead - a Maya
    control or panel lies between it and the workspaceControl (an overlay
    on ``timeControl1``), or the control is one of Maya's UI elements - and
    nothing may be deleted for it.

    ``workspaceControl -exists`` answers True for any UI object of that
    name, so each candidate is checked to really be a workspaceControl.
    """
    parent = widget.parentWidget()
    while parent is not None:
        name = parent.objectName()
        if name and _is_maya_ui_object(name):
            try:
                kind = cmds.objectTypeUI(name)
            except Exception:
                kind = ""
            if kind == "workspaceControl":
                if name in _MAYA_UI_CONTROLS:
                    return None, True
                return name, False
            if not kind.lower().endswith("layout"):
                # A Maya control or panel (timeControl1, a modelPanel, ...)
                # owns this widget: it is drawn on Maya's UI.
                return None, True
        parent = parent.parentWidget()
    return None, False


def _show_fresh_toolbar(reopen, summary):
    """Import the purged atk_toolbar package anew, rebuild, reopen tools."""
    import importlib
    try:
        toolbar = importlib.import_module("atk_toolbar.atk_toolbar")
        toolbar.show()
        for tool_id in reopen:
            toolbar.atk_loader.launch_tool(tool_id, track=False)
    except Exception as exc:
        cmds.warning("ATK Toolbar: rebuild after reload failed: {}".format(exc))
        return
    cmds.inViewMessage(amg="<hl>ATK Toolbar</hl>: {}".format(summary.split("\n")[0]),
                       pos="midCenter", fade=True)


def refresh_open_dialog():
    """Reload the Layout tab of an open Settings dialog from the stored data.

    Called when the layout changes outside the dialog (the gear menu's Layout
    submenu, a group button's Unfold), so the dialog's controls never hold
    stale values that Apply or the next Layout change would save back.
    """
    global _dialog_instance
    try:
        if _dialog_instance is not None and not _dialog_instance.isHidden():
            _dialog_instance._load_layout()
    except RuntimeError:
        _dialog_instance = None


def show(rebuild_callback=None, tab=None):
    """Show (or raise) the ATK settings dialog, optionally on a named tab."""
    global _dialog_instance
    try:
        if _dialog_instance is not None and not _dialog_instance.isHidden():
            # Refresh the callback — the toolbar widget may have been
            # recreated (e.g. by a re-dock) since the dialog was opened.
            _dialog_instance.rebuild_callback = rebuild_callback
            _dialog_instance.select_tab(tab)
            _dialog_instance.raise_()
            _dialog_instance.activateWindow()
            return _dialog_instance
    except RuntimeError:
        _dialog_instance = None

    _dialog_instance = ATKSettingsDialog(rebuild_callback=rebuild_callback)
    _dialog_instance.select_tab(tab)
    _dialog_instance.show()
    return _dialog_instance
