"""ATK Toolbar — main dockable toolbar for the Animation Tool Kit.

Creates a Maya workspaceControl that renders as a compact strip of icon buttons,
one per tool, with a Settings button on the left side.

Docking behaviour
-----------------
The workspaceControl is created with ``floating=True`` and ``retain=True``.
Maya saves the dock position on exit and restores it on the next session via
the ``uiScript`` callback.

Orientation detection
---------------------
When the toolbar is narrower than it is tall, buttons are stacked vertically;
otherwise they run horizontally.  The layout is rebuilt whenever the user
calls ``_rebuild_ui()`` (e.g. after docking to a different edge).

Right-click context menu per button
------------------------------------
  • Open Tool
  • Close / Hide Tool Window   (disabled if not applicable)
  • ─────────────────────────
  • Help / About This Tool
"""

import os
import sys

import maya.cmds as cmds
import maya.mel as mel
from maya import OpenMayaUI as omui

try:
    from PySide6 import QtCore, QtGui, QtWidgets
    from shiboken6 import wrapInstance
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets
    from shiboken2 import wrapInstance

from . import atk_loader
from . import atk_icons
from . import atk_settings

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
WORKSPACE_NAME = "ATKToolbar"
TOOLBAR_LABEL  = "Animation Tool Kit"
VERSION        = "1.0.0"

# optionVar keys mirrored from atk_settings
_OPT_ICON_SIZE       = atk_settings.OPT_ICON_SIZE
_OPT_SHOW_TOOLTIPS   = atk_settings.OPT_SHOW_TOOLTIPS
_OPT_SHOW_SEPARATORS = atk_settings.OPT_SHOW_SEPARATORS
_OPT_ORIENTATION     = atk_settings.OPT_ORIENTATION

_BTN_STYLE_NORMAL = (
    "QToolButton {"
    "  background: transparent;"
    "  border: none;"
    "  border-radius: 4px;"
    "  padding: 2px;"
    "}"
    "QToolButton:hover {"
    "  background: rgba(255,255,255,30);"
    "}"
    "QToolButton:pressed {"
    "  background: rgba(0,0,0,60);"
    "}"
)

_BTN_STYLE_SETTINGS = (
    "QToolButton {"
    "  background: transparent;"
    "  border: none;"
    "  border-radius: 4px;"
    "  padding: 2px;"
    "}"
    "QToolButton:hover {"
    "  background: rgba(144,164,174,40);"
    "}"
    "QToolButton:pressed {"
    "  background: rgba(144,164,174,80);"
    "}"
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_icon_size():
    return atk_settings._get_pref_int(_OPT_ICON_SIZE, 32)


def _show_tooltips():
    return bool(atk_settings._get_pref_int(_OPT_SHOW_TOOLTIPS, 1))


def _show_separators():
    return bool(atk_settings._get_pref_int(_OPT_SHOW_SEPARATORS, 1))


def _maya_main_window():
    ptr = omui.MQtUtil.mainWindow()
    if ptr is None:
        return None
    return wrapInstance(int(ptr), QtWidgets.QWidget)


def _count_layout_items():
    """Return (n_buttons, n_seps) for the current visible tools and settings."""
    show_sep = bool(atk_settings._get_pref_int(_OPT_SHOW_SEPARATORS, 1))
    visible  = atk_loader.get_visible_tools()
    n_buttons = len(visible) + 1   # +1 for the settings button

    n_seps = 0
    if show_sep:
        n_seps = 1
        prev_group = None
        for tool in visible:
            if prev_group and tool["group"] != prev_group:
                n_seps += 1
            prev_group = tool["group"]

    return n_buttons, n_seps


def _calc_content_height():
    """Return the pixel height needed to display all visible buttons with no dead space.

    Mirrors the layout logic in ATKToolbarWidget._build() so the window can be
    pre-sized before the widget is constructed.
    """
    icon_sz  = atk_settings._get_pref_int(_OPT_ICON_SIZE, 32)
    btn_sz   = icon_sz + 8   # QToolButton fixed size
    spacing  = 2             # QVBoxLayout/QHBoxLayout spacing
    margins  = 4             # 2px top + 2px bottom

    n_buttons, n_seps = _count_layout_items()
    n_items  = n_buttons + n_seps
    # sum of item heights + spacing between consecutive items + outer margins
    return (n_buttons * btn_sz) + (n_seps * 1) + max(0, n_items - 1) * spacing + margins


def _calc_content_width():
    """Return the pixel width needed to display all visible buttons horizontally."""
    icon_sz  = atk_settings._get_pref_int(_OPT_ICON_SIZE, 32)
    btn_sz   = icon_sz + 8
    spacing  = 2
    margins  = 4             # 2px left + 2px right

    n_buttons, n_seps = _count_layout_items()
    n_items  = n_buttons + n_seps
    return (n_buttons * btn_sz) + (n_seps * 1) + max(0, n_items - 1) * spacing + margins


def _get_chrome_height():
    """Return an estimate of the OS title-bar height in pixels."""
    try:
        app = QtWidgets.QApplication.instance()
        return app.style().pixelMetric(QtWidgets.QStyle.PM_TitleBarHeight) + 6
    except Exception:
        return 32


def _resize_to_fit():
    """Resize the floating workspaceControl to exactly fit its content.

    Ignored when the control is docked (the dock handles sizing).
    Uses both the Maya workspaceControl API and direct Qt window resize
    to ensure the window shrinks in both dimensions on orientation change.
    """
    if not cmds.workspaceControl(WORKSPACE_NAME, exists=True):
        return
    try:
        floating = cmds.workspaceControl(WORKSPACE_NAME, q=True, floating=True)
    except Exception:
        return
    if not floating:
        return

    icon_sz = atk_settings._get_pref_int(_OPT_ICON_SIZE, 32)
    btn_sz  = icon_sz + 8
    orient  = (cmds.optionVar(q=_OPT_ORIENTATION)
               if cmds.optionVar(exists=_OPT_ORIENTATION) else "horizontal")
    chrome  = _get_chrome_height()

    if orient == "vertical":
        new_w = btn_sz + 8
        new_h = _calc_content_height() + chrome
    else:
        new_w = _calc_content_width() + 8
        new_h = btn_sz + chrome

    try:
        cmds.workspaceControl(WORKSPACE_NAME, edit=True,
                              width=new_w, height=new_h)
    except Exception:
        pass

    # The workspaceControl edit often only sets minimums and won't shrink
    # the window in the non-primary axis.  Force the Qt window directly.
    try:
        ptr = omui.MQtUtil.findControl(WORKSPACE_NAME)
        if ptr is not None:
            content  = wrapInstance(int(ptr), QtWidgets.QWidget)
            win      = content.window()
            maya_win = _maya_main_window()
            if win is not None and win is not maya_win:
                win.resize(new_w, new_h)
    except Exception:
        pass


def _remove_min_max_buttons():
    """Strip the minimize and maximize buttons from the floating toolbar window.

    Called via QTimer.singleShot so Maya has finished constructing the panel
    before we walk the widget hierarchy.

    Key points:
    - Explicitly keep WindowCloseButtonHint so the X stays active and not greyed.
    - Call raise_() + activateWindow() so the OS draws the chrome as "active"
      (without this Windows draws the title bar in its inactive/greyed state).
    - Skip silently when the panel is docked (content.window() == Maya main window).
    """
    try:
        ptr = omui.MQtUtil.findControl(WORKSPACE_NAME)
        if ptr is None:
            return
        content  = wrapInstance(int(ptr), QtWidgets.QWidget)
        win      = content.window()
        maya_win = _maya_main_window()
        if win is None or win is maya_win:
            return   # docked — title bar belongs to Maya, don't touch it
        flags = win.windowFlags()
        flags &= ~QtCore.Qt.WindowMinimizeButtonHint
        flags &= ~QtCore.Qt.WindowMaximizeButtonHint
        flags |=  QtCore.Qt.WindowCloseButtonHint   # keep X active
        win.setWindowFlags(flags)
        win.show()
        # Schedule activation at 0 / 100 / 250 ms — at least one fires AFTER
        # the OS finishes its show-event processing so the title bar chrome is
        # drawn in "active" (not greyed) state.
        for _ms in (0, 100, 250):
            QtCore.QTimer.singleShot(_ms, win.raise_)
            QtCore.QTimer.singleShot(_ms, win.activateWindow)
    except Exception:
        pass


def _undock_toolbar():
    """Float the workspaceControl if it is currently docked."""
    if not cmds.workspaceControl(WORKSPACE_NAME, exists=True):
        return
    try:
        floating = cmds.workspaceControl(WORKSPACE_NAME, q=True, floating=True)
    except Exception:
        return
    if not floating:
        cmds.workspaceControl(WORKSPACE_NAME, edit=True, floating=True)


def _on_floating_change():
    """Called by Maya's floatingChangeCommand whenever the panel is docked or undocked.

    Uses a short timer so the new window hierarchy is fully constructed before
    we try to read it.
    """
    QtCore.QTimer.singleShot(150, _remove_min_max_buttons)
    QtCore.QTimer.singleShot(150, _resize_to_fit)


# ---------------------------------------------------------------------------
# Toolbar Qt widget
# ---------------------------------------------------------------------------

class ATKToolbarWidget(QtWidgets.QWidget):
    """The actual button-strip widget embedded inside the workspaceControl."""

    def __init__(self, parent=None):
        super(ATKToolbarWidget, self).__init__(parent)
        self._button_map = {}   # tool_id -> QToolButton
        self._current_orientation = None
        self._build()

    # ── Construction ────────────────────────────────────────────────────────

    def _build(self):
        # Clear any previous children
        old_layout = self.layout()
        if old_layout is not None:
            while old_layout.count():
                item = old_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            QtWidgets.QWidget().setLayout(old_layout)

        orientation = self._detect_orientation()
        self._current_orientation = orientation
        icon_sz = _get_icon_size()
        show_tips = _show_tooltips()
        show_sep = _show_separators()

        if orientation == "vertical":
            layout = QtWidgets.QVBoxLayout(self)
        else:
            layout = QtWidgets.QHBoxLayout(self)

        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)

        # Settings button (always first)
        self._add_settings_btn(layout, icon_sz, show_tips, orientation)
        if show_sep:
            self._add_sep(layout, orientation)

        # Tool buttons
        self._button_map = {}
        prev_group = None

        for tool in atk_loader.TOOL_REGISTRY:
            if not atk_loader.is_tool_visible(tool["id"]):
                continue

            if show_sep and prev_group and tool["group"] != prev_group:
                self._add_sep(layout, orientation)

            btn = self._make_tool_btn(tool, icon_sz, show_tips)
            self._button_map[tool["id"]] = btn
            layout.addWidget(btn)
            prev_group = tool["group"]

        layout.addStretch()

    def _add_settings_btn(self, layout, icon_sz, show_tips, orientation):
        btn = QtWidgets.QToolButton()
        btn.setFixedSize(icon_sz + 8, icon_sz + 8)
        btn.setIcon(atk_icons.make_settings_icon(icon_sz))
        btn.setIconSize(QtCore.QSize(icon_sz, icon_sz))
        btn.setStyleSheet(_BTN_STYLE_SETTINGS)
        btn.setToolTip("Settings" if show_tips else "")
        btn.clicked.connect(lambda: atk_settings.show(rebuild_callback=self.rebuild))

        # Right-click menu
        btn.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        btn.customContextMenuRequested.connect(
            lambda pos, b=btn: self._settings_context_menu(b, pos)
        )
        layout.addWidget(btn)

    def _make_tool_btn(self, tool, icon_sz, show_tips):
        btn = QtWidgets.QToolButton()
        btn.setFixedSize(icon_sz + 8, icon_sz + 8)

        installed = atk_loader.is_tool_installed(tool["id"])
        if installed:
            icon = atk_icons.load_or_generate_icon(
                tool["icon_file"], tool["icon_key"], tool["group"], icon_sz
            )
            btn.setStyleSheet(_BTN_STYLE_NORMAL)
        else:
            icon = atk_icons.make_warning_icon(icon_sz)
            btn.setStyleSheet(_BTN_STYLE_NORMAL + "QToolButton { opacity: 0.5; }")

        btn.setIcon(icon)
        btn.setIconSize(QtCore.QSize(icon_sz, icon_sz))

        if show_tips:
            tip = "<b>{}</b><br>{}".format(tool["label"], tool["tooltip"])
            if not installed:
                tip += "<br><i style='color:#ff6666;'>Not installed</i>"
            btn.setToolTip(tip)

        if installed:
            btn.clicked.connect(lambda checked=False, tid=tool["id"]: atk_loader.launch_tool(tid))

        # Right-click context menu
        btn.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        btn.customContextMenuRequested.connect(
            lambda pos, t=tool, b=btn, inst=installed: self._tool_context_menu(t, b, pos, inst)
        )
        return btn

    @staticmethod
    def _add_sep(layout, orientation):
        sep = QtWidgets.QFrame()
        if orientation == "vertical":
            sep.setFrameShape(QtWidgets.QFrame.HLine)
            sep.setFixedHeight(1)
        else:
            sep.setFrameShape(QtWidgets.QFrame.VLine)
            sep.setFixedWidth(1)
        sep.setStyleSheet("background-color: #555555; border: none;")
        layout.addWidget(sep)

    # ── Orientation detection ────────────────────────────────────────────────

    def _detect_orientation(self):
        """Return orientation from the saved preference."""
        if cmds.optionVar(exists=_OPT_ORIENTATION):
            val = cmds.optionVar(q=_OPT_ORIENTATION)
            if val in ("horizontal", "vertical"):
                return val
        return "horizontal"

    # ── Context menus ────────────────────────────────────────────────────────

    def _settings_context_menu(self, btn, pos):
        menu = QtWidgets.QMenu(self)
        menu.setStyleSheet(
            "QMenu { background:#3c3c3c; color:#cccccc; border:1px solid #555; }"
            "QMenu::item:selected { background:#4FC3F7; color:#000; }"
        )
        menu.addAction("Open Settings", lambda: atk_settings.show(rebuild_callback=self.rebuild))
        menu.addSeparator()
        menu.addAction("About Animation Tool Kit", self._show_about)
        menu.exec_(btn.mapToGlobal(pos))

    def _tool_context_menu(self, tool, btn, pos, installed):
        menu = QtWidgets.QMenu(self)
        menu.setStyleSheet(
            "QMenu { background:#3c3c3c; color:#cccccc; border:1px solid #555; }"
            "QMenu::item:selected { background:#4FC3F7; color:#000; }"
        )
        open_act = menu.addAction("Open {}".format(tool["label"]))
        if installed:
            open_act.triggered.connect(lambda: atk_loader.launch_tool(tool["id"]))
        else:
            open_act.setEnabled(False)

        menu.addSeparator()
        about_act = menu.addAction("About This Tool")
        about_act.triggered.connect(lambda: self._show_tool_about(tool))
        menu.exec_(btn.mapToGlobal(pos))

    @staticmethod
    def _show_about():
        msg = QtWidgets.QMessageBox()
        msg.setWindowTitle("About Animation Tool Kit")
        lines = ["<b>Animation Tool Kit Toolbar</b> v{}<br>".format(VERSION)]
        for t in atk_loader.TOOL_REGISTRY:
            lines.append("• {} v{}".format(t["label"], t["version"]))
        msg.setText("<br>".join(lines))
        msg.setIcon(QtWidgets.QMessageBox.Information)
        msg.exec_()

    @staticmethod
    def _show_tool_about(tool):
        msg = QtWidgets.QMessageBox()
        msg.setWindowTitle("About — {}".format(tool["label"]))
        text = (
            "<b>{}</b> v{}<br><br>"
            "{}<br><br>"
            "<i>Module: {}</i>"
        ).format(tool["label"], tool["version"], tool["tooltip"], tool["module"])
        msg.setText(text)
        msg.setIcon(QtWidgets.QMessageBox.Information)
        msg.exec_()

    # ── Rebuild ──────────────────────────────────────────────────────────────

    def rebuild(self):
        """Re-build the button strip (called after settings change)."""
        old_orient = self._current_orientation
        self._build()

        new_orient = self._current_orientation
        if old_orient != new_orient:
            _undock_toolbar()
            # Give Maya time to process the undock before resizing
            QtCore.QTimer.singleShot(150, _resize_to_fit)
            QtCore.QTimer.singleShot(200, _remove_min_max_buttons)
        else:
            _resize_to_fit()
            QtCore.QTimer.singleShot(50, _remove_min_max_buttons)


# ---------------------------------------------------------------------------
# workspaceControl management
# ---------------------------------------------------------------------------
_toolbar_widget = None


def _rebuild_ui():
    """Called by Maya's workspaceControl uiScript to populate the panel.

    Also invoked directly after show() to populate on first launch.
    """
    global _toolbar_widget

    atk_loader.setup_paths()

    if not cmds.workspaceControl(WORKSPACE_NAME, exists=True):
        return

    # Find the Qt widget that wraps the workspaceControl
    ptr = omui.MQtUtil.findControl(WORKSPACE_NAME)
    if ptr is None:
        return

    parent_widget = wrapInstance(int(ptr), QtWidgets.QWidget)

    # Remove any existing ATKToolbarWidget immediately (setParent(None) detaches
    # from the layout right now; deleteLater() cleans up memory later).
    # This makes _rebuild_ui() safe to call multiple times without double icons,
    # which matters because uiScript fires synchronously on workspaceControl
    # creation AND show() calls _rebuild_ui() explicitly.
    for child in parent_widget.findChildren(ATKToolbarWidget):
        child.setParent(None)
        child.deleteLater()

    _toolbar_widget = ATKToolbarWidget(parent=parent_widget)

    # Insert into the workspaceControl's layout
    layout = parent_widget.layout()
    if layout is None:
        layout = QtWidgets.QVBoxLayout(parent_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

    layout.addWidget(_toolbar_widget)
    _toolbar_widget.show()

    _resize_to_fit()
    QtCore.QTimer.singleShot(50, _remove_min_max_buttons)


def show():
    """Create or restore the ATK toolbar workspaceControl.

    Always deletes and recreates the control so the UI is fully rebuilt.
    Maya will restore the last dock position because ``retain=True``.
    """
    atk_loader.setup_paths()

    if cmds.workspaceControl(WORKSPACE_NAME, exists=True):
        cmds.deleteUI(WORKSPACE_NAME)

    # Size the initial window to match orientation + exact button count
    orient = "horizontal"
    if cmds.optionVar(exists=_OPT_ORIENTATION):
        val = cmds.optionVar(q=_OPT_ORIENTATION)
        if val in ("horizontal", "vertical"):
            orient = val

    icon_sz = atk_settings._get_pref_int(_OPT_ICON_SIZE, 32)
    btn_sz  = icon_sz + 8
    chrome  = _get_chrome_height()

    if orient == "vertical":
        init_w = btn_sz + 8
        init_h = _calc_content_height() + chrome
    else:
        init_w = _calc_content_width() + 8
        init_h = btn_sz + chrome

    # floatingChangeCommand fires every time the panel is docked or undocked,
    # letting us re-strip min/max buttons and re-fit the size after each transition.
    float_cmd = (
        "import sys, maya.cmds as cmds; "
        "scripts_dir = cmds.internalVar(userScriptDir=True); "
        "sys.path.insert(0, scripts_dir) if scripts_dir not in sys.path else None; "
        "import atk_toolbar.atk_toolbar as _atk; _atk._on_floating_change()"
    )

    ui_script = (
        "import sys, maya.cmds as cmds; "
        "scripts_dir = cmds.internalVar(userScriptDir=True); "
        "sys.path.insert(0, scripts_dir) if scripts_dir not in sys.path else None; "
        "import atk_toolbar.atk_toolbar as _atk; _atk._rebuild_ui()"
    )

    # Dock below the Channel Box on first open; user can undock/move freely.
    # dockToControl places ATK as a separate panel directly below ChannelBoxLayerEditor.
    # Fall back to the right edge of the main window if that panel is absent.
    #
    # floatingChangeCommand is only available in Maya 2024+.  If the flag is
    # not recognised we fall back without it — the toolbar still works, it just
    # won't auto-strip min/max buttons or resize after a dock/undock transition.
    dock_kw = dict(
        label=TOOLBAR_LABEL,
        retain=True,
        initialWidth=init_w,
        initialHeight=init_h,
        minimumWidth=52,
        minimumHeight=52,
        uiScript=ui_script,
    )

    if cmds.workspaceControl("ChannelBoxLayerEditor", exists=True):
        dock_kw["dockToControl"] = ["ChannelBoxLayerEditor", "bottom"]
    else:
        dock_kw["dockToMainWindow"] = ["right", False]

    try:
        cmds.workspaceControl(WORKSPACE_NAME, floatingChangeCommand=float_cmd, **dock_kw)
    except TypeError:
        # Maya version does not support floatingChangeCommand — create without it
        cmds.workspaceControl(WORKSPACE_NAME, **dock_kw)

    cmds.workspaceControl(WORKSPACE_NAME, edit=True, visible=True)
    _rebuild_ui()

    # Force exact size after a short delay — overrides any retained state from
    # a previous session, and runs after the dock layout has settled.
    QtCore.QTimer.singleShot(100, _resize_to_fit)
    QtCore.QTimer.singleShot(200, _remove_min_max_buttons)


def close():
    """Hide the toolbar workspaceControl (does not destroy retain state)."""
    if cmds.workspaceControl(WORKSPACE_NAME, exists=True):
        cmds.workspaceControl(WORKSPACE_NAME, edit=True, visible=False)


def is_visible():
    """Return True if the toolbar is currently shown."""
    if cmds.workspaceControl(WORKSPACE_NAME, exists=True):
        return bool(cmds.workspaceControl(WORKSPACE_NAME, q=True, visible=True))
    return False
