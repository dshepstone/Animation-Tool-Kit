"""ATK Settings — settings dialog for the Animation Tool Kit toolbar.

Opens a QDialog that lets the user:
  • Choose icon size (small / medium / large)
  • Choose where the toolbar docks (above the timeline, below the shelf,
    or vertically on the left/right edge of the viewport)
  • Toggle individual tools on/off
  • Toggle group separator visibility
  • View tool version info (About tab)
  • Reload the latest installed tool scripts without restarting Maya
    (Reload Scripts button)

All preferences are stored as Maya optionVars with an "atk_" prefix.
Clicking Apply rebuilds the toolbar immediately.
"""

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
        self.setMinimumWidth(380)
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
            "Re-import the latest installed tool scripts without restarting Maya.\n"
            "Use this after installing or updating a tool.\n"
            "Tool windows that are already open keep running on the old code\n"
            "until they are relaunched from the toolbar."
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

        # Icon size
        size_group = QtWidgets.QGroupBox("Icon Size")
        size_layout = QtWidgets.QVBoxLayout(size_group)
        self._size_radios = []
        for label, px in ICON_SIZES:
            rb = QtWidgets.QRadioButton(label)
            size_layout.addWidget(rb)
            self._size_radios.append((rb, px))
        layout.addWidget(size_group)

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

        note = QtWidgets.QLabel(
            "Controls where the toolbar docks and how tool icons are\n"
            "positioned inside the horizontal bar."
        )
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

        align_group = QtWidgets.QGroupBox("Icon Alignment  (horizontal bar)")
        align_layout = QtWidgets.QVBoxLayout(align_group)

        self._rb_align_left   = QtWidgets.QRadioButton("Left  — tools start immediately after the gear")
        self._rb_align_center = QtWidgets.QRadioButton("Centre  — tools centred in the bar")
        self._rb_align_right  = QtWidgets.QRadioButton("Right  — tools pushed to the far right")

        align_layout.addWidget(self._rb_align_left)
        align_layout.addWidget(self._rb_align_center)
        align_layout.addWidget(self._rb_align_right)
        layout.addWidget(align_group)

        layout.addStretch()
        self._tabs.addTab(tab, "Workspace")

    def _build_tools_tab(self):
        tab = QtWidgets.QWidget()
        outer = QtWidgets.QVBoxLayout(tab)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(6)

        note = QtWidgets.QLabel("Uncheck tools to hide them from the toolbar.")
        note.setObjectName("lbl_subtitle")
        note.setWordWrap(True)
        outer.addWidget(note)

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        inner_widget = QtWidgets.QWidget()
        inner_layout = QtWidgets.QVBoxLayout(inner_widget)
        inner_layout.setContentsMargins(0, 0, 0, 0)
        inner_layout.setSpacing(4)
        scroll.setWidget(inner_widget)

        self._tool_checks = {}
        self._tool_installed_labels = {}
        self._inline_widget_checks = {}
        current_group = None

        widget_label = QtWidgets.QLabel("TOOLBAR WIDGETS")
        widget_label.setObjectName("lbl_section")
        inner_layout.addWidget(widget_label)

        slider_cb = QtWidgets.QCheckBox("Inbetweener Slider")
        slider_cb.setToolTip("Show/hide the inline Inbetweener slider widget on the toolbar.")
        self._inline_widget_checks[OPT_SHOW_INLINE_SLIDER] = slider_cb
        inner_layout.addWidget(slider_cb)

        frame_cb = QtWidgets.QCheckBox("Insert/Remove Frame Stepper")
        frame_cb.setToolTip("Show/hide the inline frame insert/remove control next to the slider.")
        self._inline_widget_checks[OPT_SHOW_FRAME_STEPPER] = frame_cb
        inner_layout.addWidget(frame_cb)

        inner_layout.addSpacing(8)

        for tool in atk_loader.TOOL_REGISTRY:
            if tool["group"] != current_group:
                current_group = tool["group"]
                grp_label = QtWidgets.QLabel(current_group.upper())
                grp_label.setObjectName("lbl_section")
                inner_layout.addSpacing(6)
                inner_layout.addWidget(grp_label)

            row = QtWidgets.QHBoxLayout()
            row.setSpacing(8)

            # Icon thumbnail
            icon = atk_icons.load_or_generate_icon(
                tool["icon_file"], tool["icon_key"], tool["group"], size=20
            )
            icon_label = QtWidgets.QLabel()
            icon_label.setPixmap(icon.pixmap(20, 20))
            icon_label.setFixedSize(24, 24)
            row.addWidget(icon_label)

            cb = QtWidgets.QCheckBox(tool["label"])
            cb.setToolTip(tool["tooltip"])
            self._tool_checks[tool["id"]] = cb
            row.addWidget(cb)
            row.addStretch()

            installed_lbl = QtWidgets.QLabel()
            installed_lbl.setStyleSheet("color: #ff6666; font-size: 10px;")
            if not atk_loader.is_tool_installed(tool["id"]):
                installed_lbl.setText("not installed")
                cb.setEnabled(False)
            self._tool_installed_labels[tool["id"]] = installed_lbl
            row.addWidget(installed_lbl)

            inner_layout.addLayout(row)

        inner_layout.addStretch()
        outer.addWidget(scroll)
        self._tabs.addTab(tab, "Tools")

    def _build_about_tab(self):
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        header = QtWidgets.QLabel("Animation Tool Kit Toolbar")
        header.setObjectName("lbl_title")
        layout.addWidget(header)

        version_label = QtWidgets.QLabel("Toolbar version 1.0.0")
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

        # Icon alignment
        align = cmds.optionVar(q=OPT_ICON_ALIGNMENT) if cmds.optionVar(exists=OPT_ICON_ALIGNMENT) else "center"
        self._rb_align_left.setChecked(align == "left")
        self._rb_align_right.setChecked(align == "right")
        self._rb_align_center.setChecked(align not in ("left", "right"))

        # Docked position
        dock_pos = self._get_dock_pref()
        self._rb_dock_shelf.setChecked(dock_pos == "below_shelf")
        self._rb_dock_left.setChecked(dock_pos == "left")
        self._rb_dock_right.setChecked(dock_pos == "right")
        self._rb_dock_timeline.setChecked(dock_pos not in ("below_shelf", "left", "right"))

        # Icon size
        current_size = _get_pref_int(OPT_ICON_SIZE, 32)
        for rb, px in self._size_radios:
            rb.setChecked(px == current_size)
        if not any(rb.isChecked() for rb, _ in self._size_radios):
            self._size_radios[1][0].setChecked(True)  # default medium

        # Display
        self._cb_tooltips.setChecked(bool(_get_pref_int(OPT_SHOW_TOOLTIPS, 1)))
        self._cb_separators.setChecked(bool(_get_pref_int(OPT_SHOW_SEPARATORS, 1)))

        # Tool visibility
        for tool_id, cb in self._tool_checks.items():
            cb.setChecked(atk_loader.is_tool_visible(tool_id))
        for pref_key, cb in self._inline_widget_checks.items():
            cb.setChecked(bool(_get_pref_int(pref_key, 1)))

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

        # Icon alignment
        if self._rb_align_left.isChecked():
            align = "left"
        elif self._rb_align_right.isChecked():
            align = "right"
        else:
            align = "center"
        cmds.optionVar(sv=(OPT_ICON_ALIGNMENT, align))

        # Docked position
        old_dock = self._get_dock_pref()
        new_dock = self._selected_dock_position()
        cmds.optionVar(sv=(OPT_DOCK_POSITION, new_dock))

        # Icon size
        for rb, px in self._size_radios:
            if rb.isChecked():
                _set_pref_int(OPT_ICON_SIZE, px)
                break

        # Display
        _set_pref_int(OPT_SHOW_TOOLTIPS, int(self._cb_tooltips.isChecked()))
        _set_pref_int(OPT_SHOW_SEPARATORS, int(self._cb_separators.isChecked()))

        # Tool visibility
        for tool_id, cb in self._tool_checks.items():
            atk_loader.set_tool_visible(tool_id, cb.isChecked())
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
        _set_pref_int(OPT_ICON_SIZE, 32)
        _set_pref_int(OPT_SHOW_TOOLTIPS, 1)
        _set_pref_int(OPT_SHOW_SEPARATORS, 1)
        _set_pref_int(OPT_SHOW_INLINE_SLIDER, 1)
        _set_pref_int(OPT_SHOW_FRAME_STEPPER, 1)
        for tool in atk_loader.TOOL_REGISTRY:
            atk_loader.set_tool_visible(tool["id"], True)
        self._load_prefs()

    # ── Script reloading ─────────────────────────────────────────────────────

    def _reload_scripts(self):
        """Re-import the latest installed tool scripts without restarting Maya.

        Purges every registered tool module so the next launch picks up the
        freshly installed files, refreshes the Tools tab installed states,
        and rebuilds the toolbar so inline widgets use the new code too.
        """
        try:
            purged = atk_loader.reload_tool_modules()
        except Exception as exc:
            cmds.warning("ATK Toolbar: script reload failed: {}".format(exc))
            return

        self._refresh_installed_states()

        # Rebuild the toolbar so inline widgets (e.g. the Inbetweener
        # slider) are recreated from the reloaded modules.
        try:
            self._request_rebuild()
        except Exception as exc:
            cmds.warning("ATK Toolbar: rebuild after reload failed: {}".format(exc))

        if purged:
            summary = "Reloaded {} tool module{}. Relaunch open tools to use the new scripts.".format(
                len(purged), "" if len(purged) == 1 else "s")
        else:
            summary = "Scripts refreshed. Tools will import the latest installed files on next launch."
        cmds.inViewMessage(amg="<hl>ATK Toolbar</hl>: {}".format(summary),
                           pos="midCenter", fade=True)
        QtWidgets.QMessageBox.information(self, "Reload Scripts", summary)

    def _refresh_installed_states(self):
        """Update the Tools tab 'not installed' labels and checkbox states."""
        for tool_id, lbl in self._tool_installed_labels.items():
            installed = atk_loader.is_tool_installed(tool_id)
            lbl.setText("" if installed else "not installed")
            cb = self._tool_checks.get(tool_id)
            if cb is not None:
                cb.setEnabled(installed)


# ---------------------------------------------------------------------------
# Singleton show helper
# ---------------------------------------------------------------------------
_dialog_instance = None


def show(rebuild_callback=None):
    """Show (or raise) the ATK settings dialog."""
    global _dialog_instance
    try:
        if _dialog_instance is not None and not _dialog_instance.isHidden():
            # Refresh the callback — the toolbar widget may have been
            # recreated (e.g. by a re-dock) since the dialog was opened.
            _dialog_instance.rebuild_callback = rebuild_callback
            _dialog_instance.raise_()
            _dialog_instance.activateWindow()
            return _dialog_instance
    except RuntimeError:
        _dialog_instance = None

    _dialog_instance = ATKSettingsDialog(rebuild_callback=rebuild_callback)
    _dialog_instance.show()
    return _dialog_instance
