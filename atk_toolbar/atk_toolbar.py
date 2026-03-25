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


# ---------------------------------------------------------------------------
# Toolbar Qt widget
# ---------------------------------------------------------------------------

class ATKToolbarWidget(QtWidgets.QWidget):
    """The actual button-strip widget embedded inside the workspaceControl."""

    def __init__(self, parent=None):
        super(ATKToolbarWidget, self).__init__(parent)
        self._button_map = {}   # tool_id -> QToolButton
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
        self._build()


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

    # Clear any existing ATKToolbarWidget children
    for child in parent_widget.findChildren(ATKToolbarWidget):
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


def show():
    """Create or restore the ATK toolbar workspaceControl.

    Always deletes and recreates the control so the UI is fully rebuilt.
    Maya will restore the last dock position because ``retain=True``.
    """
    atk_loader.setup_paths()

    if cmds.workspaceControl(WORKSPACE_NAME, exists=True):
        cmds.deleteUI(WORKSPACE_NAME)

    # Size the initial window to match the stored orientation preference
    orient = "horizontal"
    if cmds.optionVar(exists=_OPT_ORIENTATION):
        val = cmds.optionVar(q=_OPT_ORIENTATION)
        if val in ("horizontal", "vertical"):
            orient = val

    if orient == "vertical":
        init_w, init_h = 52, 460
    else:
        init_w, init_h = 460, 52

    cmds.workspaceControl(
        WORKSPACE_NAME,
        label=TOOLBAR_LABEL,
        floating=True,
        retain=True,
        initialWidth=init_w,
        initialHeight=init_h,
        minimumWidth=52,
        minimumHeight=52,
        uiScript="import sys, maya.cmds as cmds; "
                 "scripts_dir = cmds.internalVar(userScriptDir=True); "
                 "sys.path.insert(0, scripts_dir) if scripts_dir not in sys.path else None; "
                 "import atk_toolbar.atk_toolbar as _atk; _atk._rebuild_ui()",
    )

    cmds.workspaceControl(WORKSPACE_NAME, edit=True, visible=True)
    _rebuild_ui()


def close():
    """Hide the toolbar workspaceControl (does not destroy retain state)."""
    if cmds.workspaceControl(WORKSPACE_NAME, exists=True):
        cmds.workspaceControl(WORKSPACE_NAME, edit=True, visible=False)


def is_visible():
    """Return True if the toolbar is currently shown."""
    if cmds.workspaceControl(WORKSPACE_NAME, exists=True):
        return bool(cmds.workspaceControl(WORKSPACE_NAME, q=True, visible=True))
    return False
