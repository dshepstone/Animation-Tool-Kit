"""ATK Toolbar — main dockable toolbar for the Animation Tool Kit.

Creates a Maya workspaceControl that renders as a compact strip of icon buttons,
one per tool, with a Settings button on the left side.

Docking behaviour
-----------------
The workspaceControl opens docked at the position chosen in the Workspace
settings tab: above the Time Slider (default), below the Shelf, or vertically
on the left/right edge of the viewport.  Dropping the bar in a dock area
auto-corrects its orientation to match (vertical in side areas, horizontal
in top/bottom areas).  The dotted grip handle acts as a tear-off tab — drag
it to pull the bar off its dock and float it, or click it to float in
place.  Tearing the bar off fades it in smoothly instead of popping (see
``_on_floating_change``).

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
import importlib
import shutil

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
VERSION        = "1.1.1"

# optionVar keys mirrored from atk_settings
_OPT_ICON_SIZE       = atk_settings.OPT_ICON_SIZE
_OPT_SHOW_TOOLTIPS   = atk_settings.OPT_SHOW_TOOLTIPS
_OPT_SHOW_SEPARATORS = atk_settings.OPT_SHOW_SEPARATORS
_OPT_ORIENTATION     = atk_settings.OPT_ORIENTATION
_OPT_ICON_ALIGNMENT  = atk_settings.OPT_ICON_ALIGNMENT
_OPT_SHOW_INLINE_SLIDER = atk_settings.OPT_SHOW_INLINE_SLIDER
_OPT_SHOW_FRAME_STEPPER = atk_settings.OPT_SHOW_FRAME_STEPPER
_OPT_DOCK_POSITION      = atk_settings.OPT_DOCK_POSITION

DOCK_POSITIONS = ("above_timeline", "below_shelf", "left", "right")

_DOCK_MENU_LABELS = {
    "above_timeline": "Dock Above Timeline",
    "below_shelf":    "Dock Below Shelf",
    "left":           "Dock Left of Viewport",
    "right":          "Dock Right of Viewport",
}

_INB_TOOLBAR_SLIDER_WIDTH = 290
_INB_TOOLBAR_SLIDER_HEIGHT = 52
_FRAME_STEPPER_WIDTH = 118

# Vertical-bar variant of the inline Inbetweener slider: the horizontal-only
# VertexTickedSlider is embedded in a QGraphicsView rotated -90 degrees.
_INB_VSLIDER_LEN   = 220   # rotated slider length along the bar
_INB_VSLIDER_THICK = 44    # rotated slider thickness across the bar
_INB_VSLIDER_BLOCK_HEIGHT = 258   # margins + mode combo + spacing + rotated slider view

_VERTICAL_SCROLLBAR_W = 14   # width reserved for the vertical bar's scrollbar

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

# Logo button: no padding so the 'A•T' mark can fill the whole button and
# read clearly at small icon sizes.
_BTN_STYLE_LOGO = (
    "QToolButton {"
    "  background: transparent;"
    "  border: none;"
    "  border-radius: 4px;"
    "  padding: 0px;"
    "}"
    "QToolButton:hover {"
    "  background: rgba(255,255,255,30);"
    "}"
    "QToolButton:pressed {"
    "  background: rgba(0,0,0,60);"
    "}"
)

# Slim, dark scrollbar for the vertical bar's scroll area.
_SCROLL_STYLE = (
    "QScrollArea { background: transparent; border: none; }"
    "QScrollArea > QWidget > QWidget { background: transparent; }"
    "QScrollBar:vertical {"
    "  background: transparent; width: 10px; margin: 0;"
    "}"
    "QScrollBar::handle:vertical {"
    "  background: #5a5a5a; border-radius: 4px; min-height: 24px;"
    "}"
    "QScrollBar::handle:vertical:hover { background: #787878; }"
    "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
    "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }"
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

def _show_inline_slider():
    return bool(atk_settings._get_pref_int(_OPT_SHOW_INLINE_SLIDER, 1))


def _show_frame_stepper():
    return bool(atk_settings._get_pref_int(_OPT_SHOW_FRAME_STEPPER, 1))


def _get_alignment():
    if cmds.optionVar(exists=_OPT_ICON_ALIGNMENT):
        val = cmds.optionVar(q=_OPT_ICON_ALIGNMENT)
        if val in ("left", "center", "right"):
            return val
    return "center"


def _get_dock_position():
    if cmds.optionVar(exists=_OPT_DOCK_POSITION):
        val = cmds.optionVar(q=_OPT_DOCK_POSITION)
        if val in DOCK_POSITIONS:
            return val
    return "above_timeline"


def _maya_main_window():
    ptr = omui.MQtUtil.mainWindow()
    if ptr is None:
        return None
    return wrapInstance(int(ptr), QtWidgets.QWidget)


def _count_layout_items():
    """Return (n_buttons, n_seps) for the current visible tools and settings."""
    show_sep = bool(atk_settings._get_pref_int(_OPT_SHOW_SEPARATORS, 1))
    visible  = atk_loader.get_visible_tools()
    n_buttons = len(visible) + 2   # +2 for the settings gear and the logo button

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
    total = (n_buttons * btn_sz) + (n_seps * 1) + max(0, n_items - 1) * spacing + margins
    total += 12   # grip handle strip
    if atk_loader.is_tool_installed("inbetweener") and _show_inline_slider():
        total += (_INB_VSLIDER_BLOCK_HEIGHT + spacing)
    return total


def _horizontal_bar_height():
    """Pixel height of the horizontal bar's content (no window chrome)."""
    icon_sz = atk_settings._get_pref_int(_OPT_ICON_SIZE, 32)
    h = icon_sz + 8 + 4   # button size + layout margins
    if atk_loader.is_tool_installed("inbetweener") and _show_inline_slider():
        h = max(h, _INB_TOOLBAR_SLIDER_HEIGHT + 4)
    return h


def _vertical_bar_width():
    """Pixel width of the vertical bar, including its scrollbar allowance."""
    icon_sz = atk_settings._get_pref_int(_OPT_ICON_SIZE, 32)
    w = icon_sz + 8 + 4   # button size + layout margins
    if atk_loader.is_tool_installed("inbetweener") and _show_inline_slider():
        w = max(w, _INB_VSLIDER_THICK + 8, 60)
    return w + _VERTICAL_SCROLLBAR_W


def _calc_content_width():
    """Return the pixel width needed to display all visible buttons horizontally."""
    icon_sz  = atk_settings._get_pref_int(_OPT_ICON_SIZE, 32)
    btn_sz   = icon_sz + 8
    spacing  = 2
    margins  = 4             # 2px left + 2px right

    n_buttons, n_seps = _count_layout_items()
    n_items  = n_buttons + n_seps
    total = (n_buttons * btn_sz) + (n_seps * 1) + max(0, n_items - 1) * spacing + margins
    total += 12   # grip handle strip
    if atk_loader.is_tool_installed("inbetweener") and _show_inline_slider():
        total += (_INB_TOOLBAR_SLIDER_WIDTH + spacing)
    if atk_loader.is_tool_installed("add_remove") and _show_frame_stepper():
        total += (_FRAME_STEPPER_WIDTH + spacing)
    return total


def _get_chrome_height():
    """Return an estimate of the OS title-bar height in pixels."""
    try:
        app = QtWidgets.QApplication.instance()
        return app.style().pixelMetric(QtWidgets.QStyle.PM_TitleBarHeight) + 6
    except Exception:
        return 32


_QWIDGETSIZE_MAX = 16777215


def _resize_to_fit():
    """Fit the workspaceControl to its content.

    Floating: resize the wrapper window to hug the button strip.
    Docked:   clamp the strip's thin axis (height for a horizontal bar,
              width for a vertical one) so the dock area hugs the bar
              instead of surrounding it with dead space.
    """
    if not cmds.workspaceControl(WORKSPACE_NAME, exists=True):
        return
    try:
        floating = cmds.workspaceControl(WORKSPACE_NAME, q=True, floating=True)
    except Exception:
        return

    orient = (cmds.optionVar(q=_OPT_ORIENTATION)
              if cmds.optionVar(exists=_OPT_ORIENTATION) else "horizontal")

    content = None
    try:
        ptr = omui.MQtUtil.findControl(WORKSPACE_NAME)
        if ptr is not None:
            content = wrapInstance(int(ptr), QtWidgets.QWidget)
    except Exception:
        content = None

    if not floating:
        # Docked: cap the wrapper widget's thin axis (Maya's dock layout
        # respects child maximum sizes) and free the long axis, then nudge
        # the workspaceControl to the exact size.
        try:
            if orient == "vertical":
                bar_w = _vertical_bar_width()
                if content is not None:
                    content.setMaximumWidth(bar_w)
                    content.setMaximumHeight(_QWIDGETSIZE_MAX)
                cmds.workspaceControl(WORKSPACE_NAME, edit=True, width=bar_w)
            else:
                bar_h = _horizontal_bar_height()
                if content is not None:
                    content.setMaximumHeight(bar_h)
                    content.setMaximumWidth(_QWIDGETSIZE_MAX)
                cmds.workspaceControl(WORKSPACE_NAME, edit=True, height=bar_h)
        except Exception:
            pass
        try:
            if orient == "vertical":
                cmds.workspaceControl(WORKSPACE_NAME, edit=True,
                                      widthProperty="fixed", heightProperty="free")
            else:
                cmds.workspaceControl(WORKSPACE_NAME, edit=True,
                                      heightProperty="fixed", widthProperty="free")
        except Exception:
            pass
        return

    chrome = _get_chrome_height()
    if orient == "vertical":
        new_w = _vertical_bar_width()
        new_h = _calc_content_height() + chrome
        # Cap to the screen — the scroll area shows whatever doesn't fit.
        try:
            avail = QtWidgets.QApplication.primaryScreen().availableGeometry()
            new_h = min(new_h, avail.height() - 120)
        except Exception:
            pass
    else:
        new_w = _calc_content_width() + 8
        new_h = _horizontal_bar_height() + chrome

    # Release any docked-state clamps so the floating window can be sized.
    if content is not None:
        try:
            content.setMaximumWidth(_QWIDGETSIZE_MAX)
            content.setMaximumHeight(_QWIDGETSIZE_MAX)
        except Exception:
            pass

    try:
        cmds.workspaceControl(WORKSPACE_NAME, edit=True,
                              width=new_w, height=new_h)
    except Exception:
        pass

    # The workspaceControl edit often only sets minimums and won't shrink
    # the window in the non-primary axis.  Force the Qt window directly.
    try:
        if content is not None:
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


def _toolbar_is_floating():
    try:
        return bool(cmds.workspaceControl(WORKSPACE_NAME, q=True, floating=True))
    except Exception:
        return True


def _undock_toolbar():
    """Float the workspaceControl if it is currently docked."""
    if not cmds.workspaceControl(WORKSPACE_NAME, exists=True):
        return
    if not _toolbar_is_floating():
        cmds.workspaceControl(WORKSPACE_NAME, edit=True, floating=True)


def _dock_to_preferred():
    """Recreate the toolbar docked at the position chosen in the Workspace settings.

    Scheduled via QTimer so the gear context menu finishes closing before the
    workspaceControl is torn down and rebuilt (avoids deleting the widget while
    its menu's event handler is still on the call stack).
    """
    QtCore.QTimer.singleShot(0, show)


def _dock_to_position(dock_pos):
    """Re-dock the toolbar at one of DOCK_POSITIONS and remember it as the
    preferred position (keeps the gear menu and next launch in sync with
    where the user actually dropped the bar)."""
    if dock_pos in DOCK_POSITIONS:
        cmds.optionVar(sv=(_OPT_DOCK_POSITION, dock_pos))
    QtCore.QTimer.singleShot(0, show)


# ---------------------------------------------------------------------------
# Grip-drag drop zones
# ---------------------------------------------------------------------------
# Maya only shows its own dock drop zones for a native tab drag; a window
# moved programmatically (the grip drag) never triggers them.  So the grip
# release checks the cursor against the main window's edges and re-docks the
# bar itself, mirroring the four Workspace dock positions.
_EDGE_SNAP_X   = 90    # px from the main window's left/right edge
_EDGE_SNAP_TOP = 170   # px from the top edge (status line + shelf region)
_EDGE_SNAP_BOT = 140   # px from the bottom edge (timeline region)


def _screen_available_at(gp):
    """availableGeometry of the screen containing global point gp, or None."""
    try:
        screen = QtGui.QGuiApplication.screenAt(gp)
        if screen is None:
            screen = QtGui.QGuiApplication.primaryScreen()
        if screen is not None:
            return screen.availableGeometry()
    except Exception:
        pass
    return None


def _dock_zone_at(gp):
    """Dock position for a drag released at global point gp, or None to stay floating."""
    maya_win = _maya_main_window()
    if maya_win is None:
        return None
    try:
        rect = QtCore.QRect(maya_win.mapToGlobal(QtCore.QPoint(0, 0)), maya_win.size())
    except Exception:
        return None
    if not rect.contains(gp):
        return None
    if gp.x() - rect.left() <= _EDGE_SNAP_X:
        return "left"
    if rect.right() - gp.x() <= _EDGE_SNAP_X:
        return "right"
    if rect.bottom() - gp.y() <= _EDGE_SNAP_BOT:
        return "above_timeline"
    if gp.y() - rect.top() <= _EDGE_SNAP_TOP:
        return "below_shelf"
    return None


# ---------------------------------------------------------------------------
# Smooth undock (tear-off) transition
# ---------------------------------------------------------------------------
# When Maya tears a workspaceControl off a dock it instantly re-parents the
# content into a brand-new top-level window, then our floatingChangeCommand
# handler strips the min/max buttons (setWindowFlags recreates the native
# window) and snap-resizes it.  All of that used to happen in full view,
# which read as a hard "pop".  Instead we hide the new window the moment the
# tear-off happens, do the chrome work while it is invisible, and then ease
# it in with a short fade (plus a subtle grow when the mouse is not still
# dragging it).
_release_anim = None   # keep a reference so the animation is not GC'd mid-flight
_grip_drag_active = False   # True while the grip handle is dragging the bar


def _get_floating_window():
    """Return the floating top-level window wrapping the toolbar, or None if docked."""
    try:
        ptr = omui.MQtUtil.findControl(WORKSPACE_NAME)
        if ptr is None:
            return None
        content  = wrapInstance(int(ptr), QtWidgets.QWidget)
        win      = content.window()
        maya_win = _maya_main_window()
        if win is None or win is maya_win:
            return None
        return win
    except Exception:
        return None


def _begin_float_release():
    """Make the freshly torn-off window invisible so the flag-stripping and
    resize that follow an undock happen off-screen instead of visibly popping."""
    if _grip_drag_active:
        return
    win = _get_floating_window()
    if win is not None:
        try:
            win.setWindowOpacity(0.0)
        except Exception:
            pass


def _finish_float_release():
    """Ease the floating toolbar window in after the chrome work is done."""
    global _release_anim
    if _grip_drag_active:
        return
    win = _get_floating_window()
    if win is None:
        return
    try:
        if _release_anim is not None:
            try:
                _release_anim.stop()
            except Exception:
                pass

        group = QtCore.QParallelAnimationGroup(win)

        fade = QtCore.QPropertyAnimation(win, b"windowOpacity", win)
        fade.setDuration(240)
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)
        fade.setEasingCurve(QtCore.QEasingCurve.OutCubic)
        group.addAnimation(fade)

        # Only ease the geometry when the user is no longer dragging the
        # window — animating it under an active tear-off drag would fight
        # the mouse.
        if not (QtWidgets.QApplication.mouseButtons() & QtCore.Qt.LeftButton):
            end_geo = QtCore.QRect(win.geometry())
            dx = max(4, end_geo.width() // 20)
            dy = max(3, end_geo.height() // 10)
            start_geo = end_geo.adjusted(dx, dy, -dx, -dy)
            grow = QtCore.QPropertyAnimation(win, b"geometry", win)
            grow.setDuration(240)
            grow.setStartValue(start_geo)
            grow.setEndValue(end_geo)
            grow.setEasingCurve(QtCore.QEasingCurve.OutCubic)
            group.addAnimation(grow)

        def _ensure_opaque():
            try:
                win.setWindowOpacity(1.0)
            except Exception:
                pass

        group.finished.connect(_ensure_opaque)
        _release_anim = group
        group.start()
    except Exception:
        # Never leave the window stuck transparent.
        try:
            win.setWindowOpacity(1.0)
        except Exception:
            pass


def _auto_orient_docked():
    """Match the bar's layout to the dock area it was dropped into.

    Runs after a user drag docks the control (floatingChangeCommand fires on
    the transition, never on programmatic creation).  The control's CENTRE
    inside the main window identifies the dock area: side areas centre the
    bar in the left/right portion of the window, top/bottom areas centre it
    near the top/bottom edge.  This holds even right after the drop, when a
    wide horizontal bar makes a side area temporarily wider than it is tall
    (the case that fooled earlier aspect/cursor-based heuristics and left
    overlapping icons in a side dock).  Left/right areas turn the bar
    vertical, top/bottom horizontal, and the saved dock position is synced
    to the matching zone.  Rebuilds in place — never undocks the control the
    user just docked.
    """
    global _toolbar_widget
    try:
        if not cmds.workspaceControl(WORKSPACE_NAME, exists=True):
            return
        if cmds.workspaceControl(WORKSPACE_NAME, q=True, floating=True):
            return
        ptr = omui.MQtUtil.findControl(WORKSPACE_NAME)
        if ptr is None:
            return
        content = wrapInstance(int(ptr), QtWidgets.QWidget)
        w, h = content.width(), content.height()
        if w <= 0 or h <= 0:
            return

        maya_win = _maya_main_window()
        new_orient = None
        drop_zone  = None

        if maya_win is not None and maya_win.width() > 0 and maya_win.height() > 0:
            try:
                top_left = content.mapToGlobal(QtCore.QPoint(0, 0))
                origin   = maya_win.mapToGlobal(QtCore.QPoint(0, 0))
                cx = (top_left.x() - origin.x() + w / 2.0) / float(maya_win.width())
                cy = (top_left.y() - origin.y() + h / 2.0) / float(maya_win.height())
                # Whichever axis the centre is further off-centre on wins:
                # far left/right of centre → side area; near the top/bottom
                # edge → top/bottom area.
                if abs(cx - 0.5) > abs(cy - 0.5):
                    drop_zone  = "left" if cx < 0.5 else "right"
                    new_orient = "vertical"
                else:
                    drop_zone  = "below_shelf" if cy < 0.5 else "above_timeline"
                    new_orient = "horizontal"
            except Exception:
                new_orient = None
                drop_zone  = None

        if new_orient is None:
            new_orient = "vertical" if h > w else "horizontal"

        # Keep the saved dock position in sync with where the bar landed.
        if drop_zone is not None:
            cmds.optionVar(sv=(_OPT_DOCK_POSITION, drop_zone))

        cur = (cmds.optionVar(q=_OPT_ORIENTATION)
               if cmds.optionVar(exists=_OPT_ORIENTATION) else "horizontal")
        if new_orient != cur:
            cmds.optionVar(sv=(_OPT_ORIENTATION, new_orient))
            if _toolbar_widget is not None:
                try:
                    _toolbar_widget._build()
                except RuntimeError:
                    _toolbar_widget = None
                    _rebuild_ui()
            else:
                _rebuild_ui()
        _resize_to_fit()
    except Exception:
        pass


class _DockWatcher(QtCore.QObject):
    """Watches the workspaceControl wrapper for geometry changes.

    Dragging a docked bar by its tab straight into another dock area is a
    dock-to-dock move: the floating state never toggles, so Maya's
    floatingChangeCommand never fires and the orientation fix would never
    run.  This filter catches the wrapper's Move/Resize events instead and,
    once they settle (debounced), re-runs the docked orientation/size
    correction.  Repeated runs converge: once the orientation matches the
    dock area and the size is clamped, no further geometry events fire.
    """

    def __init__(self, parent=None):
        super(_DockWatcher, self).__init__(parent)
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self._on_settled)

    def eventFilter(self, obj, event):
        try:
            if event.type() in (QtCore.QEvent.Move, QtCore.QEvent.Resize):
                if not _grip_drag_active:
                    self._timer.start()
        except Exception:
            pass
        return False

    @staticmethod
    def _on_settled():
        try:
            if not cmds.workspaceControl(WORKSPACE_NAME, exists=True):
                return
            if _toolbar_is_floating():
                return
            _auto_orient_docked()
        except Exception:
            pass


def _on_floating_change():
    """Called by Maya's floatingChangeCommand whenever the panel is docked or undocked.

    Uses short timers so the new window hierarchy is fully constructed before
    we try to read it.  On an undock the chrome work runs while the window is
    hidden, then the window eases in (see _begin/_finish_float_release).
    On a dock the layout re-orients to match the dock area's axis and the
    strip is clamped to hug its content.
    """
    try:
        floating = bool(cmds.workspaceControl(WORKSPACE_NAME, q=True, floating=True))
    except Exception:
        floating = False

    if floating:
        if _grip_drag_active:
            # A grip drag tore the bar off: leave the window completely
            # alone — stripping flags or resizing would recreate/move the
            # native window under the mouse grab and send the bar flying.
            # The grip's release handler runs the deferred chrome work.
            return
        QtCore.QTimer.singleShot(0, _begin_float_release)
        QtCore.QTimer.singleShot(150, _remove_min_max_buttons)
        QtCore.QTimer.singleShot(160, _resize_to_fit)
        QtCore.QTimer.singleShot(180, _finish_float_release)
    else:
        QtCore.QTimer.singleShot(150, _remove_min_max_buttons)
        QtCore.QTimer.singleShot(150, _resize_to_fit)
        QtCore.QTimer.singleShot(280, _auto_orient_docked)
        # Second pass once the dock layout has fully settled — corrects the
        # orientation if the first measurement caught mid-transition geometry.
        QtCore.QTimer.singleShot(650, _auto_orient_docked)


# ---------------------------------------------------------------------------
# Grip handle widget
# ---------------------------------------------------------------------------

def _event_global_pos(event):
    """QPoint of a mouse event in global coordinates (PySide2/6 compatible)."""
    try:
        return event.globalPosition().toPoint()   # PySide6
    except AttributeError:
        return event.globalPos()                  # PySide2


def _event_local_pos(event):
    """QPoint of a mouse event in widget coordinates (PySide2/6 compatible)."""
    try:
        return event.position().toPoint()         # PySide6
    except AttributeError:
        return event.pos()                        # PySide2


class _GripHandle(QtWidgets.QWidget):
    """Dotted grip tab shown at the leading edge of the toolbar.

    Dragging it tears the toolbar off its dock — the bar floats and follows
    the mouse until release, like dragging a workspaceControl tab.  A simple
    click (no drag) floats the bar in place.  The cursor changes to an open
    hand on hover to communicate the affordance.

    In horizontal mode the grip is a narrow vertical strip of dots on the
    left side of the bar.  In vertical mode it is a short horizontal strip
    of dots at the top.
    """

    _DOT_NORMAL = QtGui.QColor("#707070")
    _DOT_HOVER  = QtGui.QColor("#b8b8b8")
    _DOT_SIZE   = 2
    _DOT_GAP    = 4   # centre-to-centre distance between dots

    def __init__(self, orientation="horizontal", parent=None):
        super(_GripHandle, self).__init__(parent)
        self._orientation = orientation
        self._hovered = False
        self._press_global = None   # global pos of the press starting a drag
        self._dragging = False
        self._win_offset = None     # grab point inside the floating window frame

        if orientation == "horizontal":
            self.setFixedWidth(10)
            self.setSizePolicy(
                QtWidgets.QSizePolicy.Fixed,
                QtWidgets.QSizePolicy.Expanding,
            )
        else:
            self.setFixedHeight(10)
            self.setSizePolicy(
                QtWidgets.QSizePolicy.Expanding,
                QtWidgets.QSizePolicy.Fixed,
            )

        self.setCursor(QtCore.Qt.OpenHandCursor)
        self.setToolTip("Drag to tear off the toolbar — click to float it in place")
        self.setAttribute(QtCore.Qt.WA_Hover, True)

    def event(self, ev):
        if ev.type() == QtCore.QEvent.HoverEnter:
            self._hovered = True
            self.update()
        elif ev.type() == QtCore.QEvent.HoverLeave:
            self._hovered = False
            self.update()
        return super(_GripHandle, self).event(ev)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        color = self._DOT_HOVER if self._hovered else self._DOT_NORMAL
        ds  = self._DOT_SIZE
        gap = self._DOT_GAP
        w, h = self.width(), self.height()

        if self._orientation == "horizontal":
            # Two columns of dots running vertically down the strip
            cx = w // 2
            y = gap
            while y + ds <= h - gap:
                painter.fillRect(cx - 2, y, ds, ds, color)
                painter.fillRect(cx + 2, y, ds, ds, color)
                y += gap
        else:
            # Two rows of dots running horizontally across the strip
            cy = h // 2
            x = gap
            while x + ds <= w - gap:
                painter.fillRect(x, cy - 2, ds, ds, color)
                painter.fillRect(x, cy + 2, ds, ds, color)
                x += gap

    # ── Drag-to-tear-off ─────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self._press_global = _event_global_pos(event)
            self._dragging = False
            self._win_offset = None
            self.setCursor(QtCore.Qt.ClosedHandCursor)
            event.accept()
            return
        super(_GripHandle, self).mousePressEvent(event)

    def mouseMoveEvent(self, event):
        global _grip_drag_active
        if self._press_global is None:
            super(_GripHandle, self).mouseMoveEvent(event)
            return
        gp = _event_global_pos(event)

        if not self._dragging:
            drag_dist = QtWidgets.QApplication.startDragDistance()
            if (gp - self._press_global).manhattanLength() < drag_dist:
                return
            # Threshold crossed: tear the bar off its dock and let the
            # floating window follow the mouse until release.  The flag
            # makes _on_floating_change leave the window alone — its
            # chrome work (setWindowFlags/resize) would recreate the
            # native window under the grab and send the bar flying.
            self._dragging = True
            _grip_drag_active = True
            if not _toolbar_is_floating():
                _undock_toolbar()
                # Maya re-parents the content into a new top-level window;
                # re-grab so this grip keeps receiving the drag.
                try:
                    self.grabMouse()
                except Exception:
                    pass

        win = self.window()
        maya_win = _maya_main_window()
        if win is None or win is maya_win:
            event.accept()
            return

        if self._win_offset is None:
            # First move after the tear-off: grab the window by the grip.
            # Include the frame offset (title bar) so win.move() — which
            # positions the frame, not the client area — keeps the grip
            # under the cursor instead of sagging the bar downwards.
            try:
                local = self.mapTo(win, _event_local_pos(event))
                frame_delta = win.geometry().topLeft() - win.frameGeometry().topLeft()
                self._win_offset = local + frame_delta
            except Exception:
                self._win_offset = QtCore.QPoint(24, 16)

        target = gp - self._win_offset
        avail = _screen_available_at(gp)
        if avail is not None:
            # Never let the bar leave the screen.
            min_x = avail.left() - win.width() + 60
            max_x = avail.right() - 60
            min_y = avail.top()
            max_y = avail.bottom() - 40
            target.setX(min(max(target.x(), min_x), max_x))
            target.setY(min(max(target.y(), min_y), max_y))
        win.move(target)
        event.accept()

    def mouseReleaseEvent(self, event):
        global _grip_drag_active
        if event.button() == QtCore.Qt.LeftButton:
            try:
                self.releaseMouse()
            except Exception:
                pass
            was_dragging = self._dragging
            had_press    = self._press_global is not None
            self._press_global = None
            self._dragging = False
            self._win_offset = None
            _grip_drag_active = False
            self.setCursor(QtCore.Qt.OpenHandCursor)

            if was_dragging:
                # Dropped near a main-window edge: snap-dock there (the
                # orientation auto-corrects via the dock transition).
                zone = _dock_zone_at(_event_global_pos(event))
                if zone:
                    _dock_to_position(zone)
                else:
                    # Stays floating — run the chrome work deferred during
                    # the drag (strip min/max buttons, fit to content).
                    QtCore.QTimer.singleShot(0, _remove_min_max_buttons)
                    QtCore.QTimer.singleShot(60, _resize_to_fit)
            elif had_press:
                _undock_toolbar()   # plain click: float in place
            event.accept()
            return
        super(_GripHandle, self).mouseReleaseEvent(event)


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
            # The button column lives inside a scroll area so every icon
            # stays reachable when the bar is taller than the dock area.
            outer = QtWidgets.QVBoxLayout(self)
            outer.setContentsMargins(0, 0, 0, 0)
            outer.setSpacing(0)

            scroll = QtWidgets.QScrollArea(self)
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
            scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
            scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
            scroll.setStyleSheet(_SCROLL_STYLE)
            outer.addWidget(scroll)

            body = QtWidgets.QWidget()
            scroll.setWidget(body)
            layout = QtWidgets.QVBoxLayout(body)
            layout.setContentsMargins(2, 2, 2, 2)
            layout.setSpacing(2)

            # Grip handle at the very top for tear-off undocking
            layout.addWidget(_GripHandle("vertical", parent=body))

            # Settings gear always at the top, ATK logo button just below it
            self._add_settings_btn(layout, icon_sz, show_tips, orientation)
            self._add_logo_btn(layout, icon_sz, show_tips, orientation)
            self._add_inbetweener_slider(layout, orientation)
            if show_sep:
                self._add_sep(layout, orientation)

            self._button_map = {}
            prev_group = None
            for tool in atk_loader.TOOL_REGISTRY:
                if not atk_loader.is_tool_visible(tool["id"]):
                    continue
                if show_sep and prev_group and tool["group"] != prev_group:
                    self._add_sep(layout, orientation)
                btn = self._make_tool_btn(tool, icon_sz, show_tips)
                self._button_map[tool["id"]] = btn
                layout.addWidget(btn, 0, QtCore.Qt.AlignHCenter)
                if tool["id"] == "tangent_tools":
                    for tangent_btn in self._make_tangent_quick_buttons(icon_sz, show_tips):
                        layout.addWidget(tangent_btn, 0, QtCore.Qt.AlignHCenter)
                prev_group = tool["group"]

            layout.addStretch()

            # Hug the bar: fixed width across, free along the column.
            self.setMinimumSize(0, 0)
            self.setMaximumHeight(_QWIDGETSIZE_MAX)
            self.setFixedWidth(_vertical_bar_width())

        else:  # horizontal
            layout = QtWidgets.QHBoxLayout(self)
            layout.setContentsMargins(2, 2, 2, 2)
            layout.setSpacing(2)

            # Grip handle at the far left for tear-off undocking
            layout.addWidget(_GripHandle("horizontal", parent=self))

            # Settings gear always anchored to the far left, ATK logo to its right
            self._add_settings_btn(layout, icon_sz, show_tips, orientation)
            self._add_logo_btn(layout, icon_sz, show_tips, orientation)
            if show_sep:
                self._add_sep(layout, orientation)

            # Build the ordered list of tool widgets (buttons + group separators)
            self._button_map = {}
            tool_widgets = []
            if atk_loader.is_tool_installed("add_remove") and _show_frame_stepper():
                tool_widgets.append(_FrameStepperToolbarWidget(parent=self))
                if atk_loader.is_tool_installed("inbetweener") and _show_inline_slider():
                    tool_widgets.append(self._make_sep_widget(orientation))
            if atk_loader.is_tool_installed("inbetweener") and _show_inline_slider():
                # Keep the inline slider directly beside the TW button cluster.
                tool_widgets.append(_InbetweenerToolbarSlider(parent=self, orientation=orientation))
                # Visual divider between the inline slider and the TW tool button.
                tool_widgets.append(self._make_sep_widget(orientation))
            prev_group = None
            for tool in atk_loader.TOOL_REGISTRY:
                if not atk_loader.is_tool_visible(tool["id"]):
                    continue
                if show_sep and prev_group and tool["group"] != prev_group:
                    tool_widgets.append(self._make_sep_widget(orientation))
                btn = self._make_tool_btn(tool, icon_sz, show_tips)
                self._button_map[tool["id"]] = btn
                tool_widgets.append(btn)
                if tool["id"] == "tangent_tools":
                    tool_widgets.extend(self._make_tangent_quick_buttons(icon_sz, show_tips))
                prev_group = tool["group"]

            # Respect workspace alignment preference while keeping the slider
            # adjacent to the TW tool cluster.
            alignment = _get_alignment()
            if alignment == "center":
                layout.addStretch()
                for w in tool_widgets:
                    layout.addWidget(w)
                layout.addStretch()
            elif alignment == "right":
                layout.addStretch()
                for w in tool_widgets:
                    layout.addWidget(w)
            else:  # left
                for w in tool_widgets:
                    layout.addWidget(w)
                layout.addStretch()

            # Hug the bar: fixed-ish height across, free along the row.
            self.setMinimumSize(0, 0)
            self.setMaximumWidth(_QWIDGETSIZE_MAX)
            self.setMaximumHeight(_horizontal_bar_height())

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
        if orientation == "vertical":
            layout.addWidget(btn, 0, QtCore.Qt.AlignHCenter)
        else:
            layout.addWidget(btn)

    def _add_logo_btn(self, layout, icon_sz, show_tips, orientation):
        """ATK 'A•T' logo button — opens the Shepstone website."""
        btn = QtWidgets.QToolButton()
        btn.setFixedSize(icon_sz + 8, icon_sz + 8)
        # Render the logo larger than the tool glyphs: fill the whole button
        # footprint (no padding) so the mark is clearly visible.
        logo_px = icon_sz + 8
        btn.setIcon(atk_icons.make_logo_icon(logo_px))
        btn.setIconSize(QtCore.QSize(logo_px, logo_px))
        btn.setStyleSheet(_BTN_STYLE_LOGO)
        btn.setCursor(QtCore.Qt.PointingHandCursor)
        if show_tips:
            btn.setToolTip(
                "<b>Animation Tool Kit</b><br>Visit shepstone.ca"
            )
        btn.clicked.connect(self._open_website)
        if orientation == "vertical":
            layout.addWidget(btn, 0, QtCore.Qt.AlignHCenter)
        else:
            layout.addWidget(btn)

    @staticmethod
    def _open_website():
        url = "https://shepstone.ca/"
        try:
            QtGui.QDesktopServices.openUrl(QtCore.QUrl(url))
        except Exception as exc:
            cmds.warning("ATK Toolbar: could not open {}: {}".format(url, exc))

    def _add_inbetweener_slider(self, layout, orientation):
        if not atk_loader.is_tool_installed("inbetweener") or not _show_inline_slider():
            return
        slider = _InbetweenerToolbarSlider(parent=self, orientation=orientation)
        if orientation == "vertical":
            layout.addWidget(slider, 0, QtCore.Qt.AlignHCenter)
        else:
            layout.addWidget(slider)

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
            if installed and tool.get("quick_tip"):
                tip += "<br><i style='color:#999;'>{}</i>".format(tool["quick_tip"])
            if not installed:
                tip += "<br><i style='color:#ff6666;'>Not installed</i>"
            btn.setToolTip(tip)

        if installed:
            # Tools with a quick_fn run it on left-click (e.g. AnimSnap snaps
            # immediately); the window launcher stays in the right-click menu.
            quick_fn = tool.get("quick_fn")
            if quick_fn:
                btn.clicked.connect(
                    lambda checked=False, tid=tool["id"], fn=quick_fn:
                        atk_loader.launch_tool_fn(tid, fn)
                )
            else:
                btn.clicked.connect(lambda checked=False, tid=tool["id"]: atk_loader.launch_tool(tid))

        # Right-click context menu
        btn.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        btn.customContextMenuRequested.connect(
            lambda pos, t=tool, b=btn, inst=installed: self._tool_context_menu(t, b, pos, inst)
        )
        return btn

    def _make_tangent_quick_buttons(self, icon_sz, show_tips):
        tangents = (
            ("auto_legacy", "AutoSpline.png", "Auto Spline (Legacy)"),
            ("linear", "Linear.png", "Linear"),
            ("stepped", "stepped.png", "Stepped"),
        )
        installed = atk_loader.is_tool_installed("tangent_tools")
        buttons = []
        for kind, icon_file, label in tangents:
            btn = QtWidgets.QToolButton()
            btn.setFixedSize(icon_sz + 8, icon_sz + 8)
            if installed:
                icon = atk_icons.load_or_generate_icon(
                    icon_file, "tween", "timing", icon_sz
                )
                btn.setStyleSheet(_BTN_STYLE_NORMAL)
                btn.clicked.connect(
                    lambda checked=False, tangent_kind=kind: self._set_tangent_quick(tangent_kind)
                )
            else:
                icon = atk_icons.make_warning_icon(icon_sz)
                btn.setStyleSheet(_BTN_STYLE_NORMAL + "QToolButton { opacity: 0.5; }")
                btn.setEnabled(False)
            btn.setIcon(icon)
            btn.setIconSize(QtCore.QSize(icon_sz, icon_sz))
            if show_tips:
                tip = "<b>{}</b><br>Set selected keys to {} tangents.".format(label, label)
                if not installed:
                    tip += "<br><i style='color:#ff6666;'>Tangent Tools not installed</i>"
                btn.setToolTip(tip)
            buttons.append(btn)
        return buttons

    @staticmethod
    def _set_tangent_quick(kind):
        try:
            core = importlib.import_module("tangent_tools.core")
            core.set_tangent_type(kind)
        except Exception as exc:
            cmds.warning("ATK Toolbar: failed to apply tangent '{}': {}".format(kind, exc))


    @staticmethod
    def _make_sep_widget(orientation):
        sep = QtWidgets.QFrame()
        if orientation == "vertical":
            sep.setFrameShape(QtWidgets.QFrame.HLine)
            sep.setFixedHeight(1)
        else:
            sep.setFrameShape(QtWidgets.QFrame.VLine)
            sep.setFixedWidth(1)
        sep.setStyleSheet("background-color: #555555; border: none;")
        return sep

    @staticmethod
    def _add_sep(layout, orientation):
        layout.addWidget(ATKToolbarWidget._make_sep_widget(orientation))

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

        # Dock / float toggle — grey out the option that already matches current state
        try:
            is_floating = bool(cmds.workspaceControl(WORKSPACE_NAME, q=True, floating=True))
        except Exception:
            is_floating = True

        float_act = menu.addAction("Float / Undock Toolbar")
        float_act.triggered.connect(_undock_toolbar)
        float_act.setEnabled(not is_floating)

        dock_label = _DOCK_MENU_LABELS.get(_get_dock_position(), "Dock Toolbar")
        dock_act = menu.addAction(dock_label)
        dock_act.triggered.connect(_dock_to_preferred)
        dock_act.setEnabled(is_floating)

        menu.addSeparator()
        menu.addAction("About Animation Tool Kit", self._show_about)
        menu.exec(btn.mapToGlobal(pos))

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

        # Tool-specific quick actions (e.g. AnimSnap's snap variants)
        if installed and tool.get("context_actions"):
            menu.addSeparator()
            for entry in tool["context_actions"]:
                if entry is None:
                    menu.addSeparator()
                    continue
                label, fn_name = entry
                act = menu.addAction(label)
                act.triggered.connect(
                    lambda checked=False, tid=tool["id"], fn=fn_name:
                        atk_loader.launch_tool_fn(tid, fn)
                )

        menu.addSeparator()
        about_act = menu.addAction("About This Tool")
        about_act.triggered.connect(lambda: self._show_tool_about(tool))
        menu.exec(btn.mapToGlobal(pos))

    @staticmethod
    def _show_about():
        msg = QtWidgets.QMessageBox()
        msg.setWindowTitle("About Animation Tool Kit")
        lines = ["<b>Animation Tool Kit Toolbar</b> v{}<br>".format(VERSION)]
        for t in atk_loader.TOOL_REGISTRY:
            lines.append("• {} v{}".format(t["label"], t["version"]))
        msg.setText("<br>".join(lines))
        msg.setIcon(QtWidgets.QMessageBox.Information)
        msg.exec()

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
        msg.exec()

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


class _InbetweenerToolbarSlider(QtWidgets.QFrame):
    """Inline Inbetweener slider embedded in the toolbar.

    A thin wrapper around ``vertex_tweener.SliderSession`` so the toolbar
    shares the exact press/drag/release behavior of the full Inbetweener
    window (cache on press, tween on drag, re-apply + key + close the undo
    chunk on release) instead of duplicating that logic here.
    """

    SLIDER_TYPES = ("LT", "WT", "BN", "BD", "BE")

    def __init__(self, parent=None, orientation="horizontal"):
        super(_InbetweenerToolbarSlider, self).__init__(parent)
        self._orientation = orientation
        self._vt = None
        self._config = {}
        self._neutral = 50
        self._session = None
        self._build_failed = False
        self._load_inbetweener()
        self._build_ui()

    def _load_inbetweener(self):
        try:
            self._vt = importlib.import_module("vertex_tweener")
            self._config = dict(self._vt.SliderPopOut.CONFIGS)
            # SliderSession carries all of the corrected press/drag/release
            # behavior; older tool versions lack it and must be updated.
            if not hasattr(self._vt, "SliderSession"):
                raise RuntimeError("vertex_tweener 2.2.1+ required")
        except Exception:
            self._build_failed = True

    def _build_ui(self):
        self.setObjectName("ATKInbetweenerSlider")
        self.setStyleSheet("#ATKInbetweenerSlider { background: transparent; border: none; }")
        vertical = (self._orientation == "vertical")

        if vertical:
            main = QtWidgets.QVBoxLayout(self)
            main.setContentsMargins(0, 4, 0, 4)
        else:
            main = QtWidgets.QHBoxLayout(self)
            main.setContentsMargins(4, 0, 4, 0)
        main.setSpacing(4)

        if self._build_failed:
            unavailable = QtWidgets.QLabel("Inbetweener slider unavailable — update the Inbetweener tool")
            unavailable.setStyleSheet("color:#999; font-size:10px;")
            unavailable.setWordWrap(vertical)
            main.addWidget(unavailable)
            return

        mode_names = {
            "LT": "Local Tweener",
            "WT": "World Tweener (ONE controller at a time)",
            "BN": "Blend to Neighbor",
            "BD": "Blend to Default",
            "BE": "Blend to Ease",
        }
        self.slider_type_combo = QtWidgets.QComboBox()
        for idx, key in enumerate(self.SLIDER_TYPES):
            self.slider_type_combo.addItem(key)
            self.slider_type_combo.setItemData(
                idx, mode_names.get(key, key), QtCore.Qt.ToolTipRole)
        self.slider_type_combo.setToolTip(
            "Choose Inbetweener slider mode\n"
            "LT: Local Tweener\n"
            "WT: World Tweener (ONE controller at a time)\n"
            "BN: Blend to Neighbor\n"
            "BD: Blend to Default\n"
            "BE: Blend to Ease"
        )
        self.slider_type_combo.setFixedWidth(52 if vertical else 56)
        self.slider_type_combo.setFixedHeight(24)
        self.slider_type_combo.setStyleSheet(self._combo_style(
            self._config.get("LT", {}).get("color", "#6BB5FF")))
        if vertical:
            main.addWidget(self.slider_type_combo, 0, QtCore.Qt.AlignHCenter)
        else:
            main.addWidget(self.slider_type_combo)

        self.slider = self._vt.VertexTickedSlider(QtCore.Qt.Horizontal, label_text="LT")
        self.slider.setTracking(True)
        self.slider.setRange(0, 100)
        self.slider.setValue(50)
        if vertical:
            # VertexTickedSlider paints and maps the mouse horizontally only,
            # so a vertical bar shows it through a QGraphicsView rotated -90°
            # (min at the bottom, max at the top).  The proxy widget maps
            # mouse events back into the slider's own coordinates, keeping
            # the press/drag/release tween session intact.
            self.slider.setFixedSize(_INB_VSLIDER_LEN, _INB_VSLIDER_THICK)
            main.addWidget(self._make_rotated_slider_view(), 0, QtCore.Qt.AlignHCenter)
            self.setFixedWidth(max(_INB_VSLIDER_THICK + 4, 56))
            self.setFixedHeight(_INB_VSLIDER_BLOCK_HEIGHT)
        else:
            self.slider.setMinimumHeight(40)
            self.setFixedWidth(_INB_TOOLBAR_SLIDER_WIDTH)
            self.setFixedHeight(_INB_TOOLBAR_SLIDER_HEIGHT)
            main.addWidget(self.slider, 1)

        self.slider_type_combo.currentTextChanged.connect(self._on_type_changed)
        self.slider.sliderPressed.connect(self._on_pressed)
        self.slider.valueChanged.connect(self._on_changed)
        self.slider.sliderReleased.connect(self._on_released)
        try:
            self._on_type_changed("LT")
        except Exception as exc:
            cmds.warning("ATK Toolbar: failed to initialize Inbetweener slider defaults: {}".format(exc))

    def _make_rotated_slider_view(self):
        """Embed the horizontal slider in a QGraphicsView rotated -90°."""
        scene = QtWidgets.QGraphicsScene(self)
        proxy = scene.addWidget(self.slider)
        proxy.setRotation(-90)
        view = QtWidgets.QGraphicsView(scene, self)
        view.setFrameShape(QtWidgets.QFrame.NoFrame)
        view.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        view.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        view.setStyleSheet("background: transparent; border: none;")
        view.viewport().setAutoFillBackground(False)
        try:
            view.setRenderHints(QtGui.QPainter.Antialiasing
                                | QtGui.QPainter.SmoothPixmapTransform)
        except Exception:
            pass
        rect = proxy.sceneBoundingRect()
        scene.setSceneRect(rect)
        view.setFixedSize(int(rect.width()) + 2, int(rect.height()) + 2)
        return view

    @staticmethod
    def _combo_style(accent):
        """Dark, rounded combo styling; the selected mode reads in its
        accent color and the popup list matches the toolbar's dark theme."""
        return (
            "QComboBox {"
            "  background: #3a3a3a; color: ACCENT; border: 1px solid #555;"
            "  border-radius: 4px; padding: 2px 2px 2px 8px;"
            "  font-weight: bold; font-size: 11px;"
            "}"
            "QComboBox:hover { background: #444444; border-color: #777; }"
            "QComboBox:on { background: #333333; border-color: ACCENT; }"
            "QComboBox::drop-down { border: none; width: 16px; }"
            "QComboBox QAbstractItemView {"
            "  background: #2f2f2f; color: #dddddd; border: 1px solid #555;"
            "  selection-background-color: ACCENT; selection-color: #000000;"
            "  outline: none; padding: 2px;"
            "}"
        ).replace("ACCENT", accent)

    def _on_type_changed(self, key):
        try:
            if key not in self._config:
                return
            cfg = self._config[key]
            self._neutral = cfg["neutral"]
            self.slider.is_tw = cfg["is_tw"]
            self.slider.is_world = cfg["is_world"]
            self.slider.label_text = cfg["label"]
            self.slider_type_combo.setStyleSheet(
                self._combo_style(cfg.get("color", "#6BB5FF")))
            overshoot_key = getattr(self._vt, "PREF_OVERSHOOT_MODE", "vertexTweener_overshootMode")
            overshoot = self._pref_bool(overshoot_key, False)
            # Block signals so the reset never fires _on_changed and applies
            # values to the scene while merely switching modes.
            self.slider.blockSignals(True)
            if key == "LT" and overshoot:
                self.slider.setRange(-50, 150)
            else:
                self.slider.setRange(0, 100)
            self.slider.setValue(self._neutral)
            self.slider.blockSignals(False)
            self.slider.keyed_value = None
            self.slider.update()
        except Exception as exc:
            cmds.warning("ATK Toolbar: Inbetweener slider mode switch failed ({}): {}".format(key, exc))

    def _on_pressed(self):
        try:
            key = self.slider_type_combo.currentText()
            self.slider.keyed_value = None
            self.slider.update()
            self._session = self._vt.SliderSession(
                key, chunk_name="ATK_Inbetweener_{}".format(key))
            count = self._session.begin()
            if not count:
                # When the session blocked the selection (e.g. World Tweener
                # with multiple controllers) it already showed its own popup.
                if not getattr(self._session, "block_message", None):
                    self._show_message(self._vt._no_target_message(key))
        except Exception as exc:
            if self._session is not None:
                self._session.cancel()
                self._session = None
            cmds.warning("ATK Toolbar: Inbetweener slider press failed: {}".format(exc))

    def _on_changed(self, value):
        if self._session is None or not getattr(self._session, "active", False):
            return
        try:
            self._session.update(value)
        except Exception as exc:
            cmds.warning("ATK Toolbar: Inbetweener slider drag failed: {}".format(exc))

    def _on_released(self):
        final_val = self.slider.value()
        applied = 0
        if self._session is not None:
            try:
                applied = self._session.end(final_val)
            except Exception as exc:
                cmds.warning("ATK Toolbar: Inbetweener slider release failed: {}".format(exc))
            self._session = None

        # Show the keyed-position tick, then snap back to neutral.
        # blockSignals stops the reset from re-applying the neutral value
        # on top of the freshly keyed pose (the old snap-back bug).
        self.slider.keyed_value = final_val if applied else None
        self.slider.blockSignals(True)
        self.slider.setValue(self._neutral)
        self.slider.blockSignals(False)
        self.slider.update()

    @staticmethod
    def _show_message(text):
        try:
            cmds.inViewMessage(
                amg="Inbetweener: {}".format(text),
                pos="botCenter", fade=True, fadeStayTime=1500)
        except Exception:
            cmds.warning("Inbetweener: {}".format(text))

    def _pref_bool(self, pref_name, default):
        try:
            if cmds.optionVar(exists=pref_name):
                return bool(cmds.optionVar(q=pref_name))
        except Exception:
            pass
        return bool(default)


class _FrameStepperToolbarWidget(QtWidgets.QFrame):
    """Compact insert/remove frame control based on Add-Remove-Inbetweens logic."""

    def __init__(self, parent=None):
        super(_FrameStepperToolbarWidget, self).__init__(parent)
        self._mod = None
        try:
            self._mod = importlib.import_module("insert_remove_frames_tool")
        except Exception:
            self._mod = None
        self._build_ui()

    def _build_ui(self):
        self.setStyleSheet("QFrame { background: transparent; border: none; }")
        self.setFixedWidth(_FRAME_STEPPER_WIDTH)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(4)

        self._ensure_retime_icons_installed()

        self.left_btn = QtWidgets.QToolButton()
        self.left_btn.setToolTip("Remove frames on selected curves")
        self.left_btn.setFixedSize(26, 22)
        self.left_btn.setIcon(self._retime_icon("ReTimeArrowLeft.png"))
        self.left_btn.setIconSize(QtCore.QSize(18, 18))
        self.left_btn.setText("" if not self.left_btn.icon().isNull() else "◀")
        layout.addWidget(self.left_btn)

        self.right_btn = QtWidgets.QToolButton()
        self.right_btn.setToolTip("Insert frames on selected curves")
        self.right_btn.setFixedSize(26, 22)
        self.right_btn.setIcon(self._retime_icon("ReTimeArrowRight.png"))
        self.right_btn.setIconSize(QtCore.QSize(18, 18))
        self.right_btn.setText("" if not self.right_btn.icon().isNull() else "▶")
        layout.addWidget(self.right_btn)

        self.frames_spin = QtWidgets.QSpinBox()
        self.frames_spin.setRange(1, 1000)
        self.frames_spin.setValue(1)
        self.frames_spin.setFixedWidth(48)
        self.frames_spin.setToolTip("Number of frames to insert/remove")
        layout.addWidget(self.frames_spin)

        self.left_btn.clicked.connect(lambda: self._apply(-1))
        self.right_btn.clicked.connect(lambda: self._apply(1))

    def _retime_icon(self, icon_name):
        """Return a QIcon for the retime arrow buttons from Maya prefs icon folders."""
        candidate_paths = [
            os.path.join(cmds.internalVar(userBitmapsDir=True), icon_name),
            os.path.join(cmds.internalVar(userPrefDir=True), "icons", icon_name),
        ]

        for icon_path in candidate_paths:
            if not os.path.exists(icon_path):
                continue
            pixmap = QtGui.QPixmap(icon_path)
            if pixmap.isNull():
                continue
            icon = QtGui.QIcon(pixmap)
            if not icon.isNull():
                return icon

        for icon_ref in (icon_name, ":/{}".format(icon_name), "icons/{}".format(icon_name)):
            icon = QtGui.QIcon(icon_ref)
            if not icon.isNull():
                return icon

        return QtGui.QIcon()

    def _ensure_retime_icons_installed(self):
        """Copy re-time arrow PNGs into Maya user prefs icon folders when available."""
        module_dir = os.path.dirname(__file__)
        add_remove_dir = None
        if self._mod is not None:
            add_remove_dir = os.path.dirname(getattr(self._mod, "__file__", "") or "")

        source_roots = [
            add_remove_dir,
            os.path.join(module_dir, "icons"),
            os.path.normpath(os.path.join(module_dir, "..", "icon")),
            os.path.normpath(os.path.join(module_dir, "..", "..", "icon")),
            os.path.normpath(os.path.join(module_dir, "..", "animation tool kit scripts", "Add-Remove-Inbetweens_1_0_1")),
            os.path.join(os.getcwd(), "animation tool kit scripts", "Add-Remove-Inbetweens_1_0_1"),
            os.path.join(os.getcwd(), "icon"),
        ]
        for entry in sys.path:
            if not entry:
                continue
            source_roots.append(
                os.path.join(entry, "animation tool kit scripts", "Add-Remove-Inbetweens_1_0_1")
            )
            source_roots.append(os.path.join(entry, "icon"))

        target_dirs = [
            cmds.internalVar(userBitmapsDir=True),
            os.path.join(cmds.internalVar(userPrefDir=True), "icons"),
        ]

        for icon_name in ("ReTimeArrowLeft.png", "ReTimeArrowRight.png"):
            src_path = None
            for root in source_roots:
                candidate = os.path.join(root, icon_name)
                if os.path.exists(candidate):
                    src_path = candidate
                    break
            if not src_path:
                continue

            for target_dir in target_dirs:
                try:
                    if not target_dir:
                        continue
                    os.makedirs(target_dir, exist_ok=True)
                    dst_path = os.path.join(target_dir, icon_name)
                    shutil.copy2(src_path, dst_path)
                except Exception:
                    pass

    def _apply(self, direction):
        if self._mod is None:
            cmds.warning("ATK Toolbar: Add/Remove Frames tool module is not installed.")
            return
        frames = self.frames_spin.value()
        curves = self._mod.gather_anim_curves("selected")
        if not curves:
            self._mod._show_headsup("<span style='color:#ffaf00'>No keyed objects selected.</span>")
            return
        changed = self._mod.shift_keys(curves, frames * direction, False)
        if not changed:
            self._mod._show_headsup("<span style='color:#ffaf00'>No keys in the chosen scope.</span>")
            return
        action = "Inserted" if direction > 0 else "Removed"
        self._mod._show_headsup(
            "<span style='color:#a0ff7a'>{} {} frame(s).</span>".format(action, frames)
        )


# ---------------------------------------------------------------------------
# workspaceControl management
# ---------------------------------------------------------------------------
_toolbar_widget = None
_dock_watcher   = None


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

    # Watch the wrapper for dock-to-dock moves (no floating transition, so
    # floatingChangeCommand stays silent) and re-run the orientation fix.
    global _dock_watcher
    if _dock_watcher is None:
        _dock_watcher = _DockWatcher()
    try:
        parent_widget.removeEventFilter(_dock_watcher)
    except Exception:
        pass
    parent_widget.installEventFilter(_dock_watcher)

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

    Always deletes and recreates the control so the UI is fully rebuilt,
    docked at the position chosen in the Workspace settings (above the
    timeline by default).
    """
    atk_loader.setup_paths()

    if cmds.workspaceControl(WORKSPACE_NAME, exists=True):
        cmds.deleteUI(WORKSPACE_NAME)

    # Clear retained workspace state so launch position is deterministic:
    # always docked at the position chosen in the Workspace settings.
    try:
        if cmds.workspaceControlState(WORKSPACE_NAME, exists=True):
            cmds.workspaceControlState(WORKSPACE_NAME, remove=True)
    except Exception:
        pass

    # The dock position dictates the launch orientation: the left/right
    # viewport edges need a vertical strip, the timeline/shelf positions a
    # horizontal one.
    dock_pos = _get_dock_position()
    orient = "vertical" if dock_pos in ("left", "right") else "horizontal"
    cmds.optionVar(sv=(_OPT_ORIENTATION, orient))

    if orient == "vertical":
        init_w = _vertical_bar_width()
        init_h = min(_calc_content_height(), 700)
    else:
        init_w = _calc_content_width() + 8
        init_h = _horizontal_bar_height()

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

    # Dock at the preferred position on open.  The user can undock or move
    # the bar freely afterwards.
    dock_kw = dict(
        label=TOOLBAR_LABEL,
        retain=False,
        initialWidth=init_w,
        initialHeight=init_h,
        minimumWidth=52,
        minimumHeight=52,
        uiScript=ui_script,
    )

    # The horizontal positions behave like native Maya UI elements — slim
    # strips docked against the Time Slider / Shelf toolbars; their tear-off
    # tab is the toolbar's grip handle.  The vertical positions are regular
    # workspace controls docked into the left/right dock areas of the main
    # window (those areas do not host UI-element toolbars, so
    # actLikeMayaUIElement must stay off there); they also get Maya's
    # native drag tab.
    if dock_pos in ("above_timeline", "below_shelf"):
        dock_kw["actLikeMayaUIElement"] = True

    # Fix the strip's thin axis so Maya docks it as a slim bar hugging its
    # content instead of handing it a huge slab of the dock area.
    if orient == "vertical":
        dock_kw["widthProperty"] = "fixed"
    else:
        dock_kw["heightProperty"] = "fixed"

    # Candidate dock targets, tried in order until one succeeds.
    candidates = []
    try:
        if dock_pos == "above_timeline":
            anchor = mel.eval('getUIComponentToolBar("Time Slider", false)')
            if anchor and cmds.control(anchor, exists=True):
                candidates.append({"dockToControl": (anchor, "top")})
        elif dock_pos == "below_shelf":
            anchor = mel.eval('getUIComponentToolBar("Shelf", false)')
            if anchor and cmds.control(anchor, exists=True):
                candidates.append({"dockToControl": (anchor, "bottom")})
    except Exception:
        pass

    # dockToMainWindow only accepts the "left", "right" and "bottom" areas.
    if dock_pos == "left":
        candidates.append({"dockToMainWindow": ("left", True)})
    elif dock_pos == "right":
        candidates.append({"dockToMainWindow": ("right", True)})
    else:
        # Bottom-edge fallback.  For "below_shelf" this only applies when the
        # Shelf toolbar could not be resolved — there is no "top" dock area.
        candidates.append({"dockToMainWindow": ("bottom", False)})

    candidates.append({})   # last resort: create the control floating

    # floatingChangeCommand is only available in Maya 2024+.  If the flag is
    # not recognised we fall back without it — the toolbar still works, it just
    # won't auto-strip min/max buttons or resize after a dock/undock transition.
    created = False
    for dock_args in candidates:
        kw = dict(dock_kw)
        kw.update(dock_args)
        try:
            try:
                cmds.workspaceControl(WORKSPACE_NAME, floatingChangeCommand=float_cmd, **kw)
            except TypeError:
                # Older Maya missing floatingChangeCommand and/or the
                # width/height property flags — retry with the basics only.
                kw.pop("widthProperty", None)
                kw.pop("heightProperty", None)
                cmds.workspaceControl(WORKSPACE_NAME, **kw)
            created = True
            break
        except RuntimeError:
            # Dock target rejected — drop any partially created control and
            # retry with the next candidate.
            try:
                if cmds.workspaceControl(WORKSPACE_NAME, exists=True):
                    cmds.deleteUI(WORKSPACE_NAME)
            except Exception:
                pass

    if not created:
        cmds.warning("ATK Toolbar: could not create the toolbar workspaceControl.")
        return

    cmds.workspaceControl(WORKSPACE_NAME, edit=True, visible=True)
    _rebuild_ui()

    # Force exact size after a short delay — overrides any retained state from
    # a previous session, and runs after the dock layout has settled.
    QtCore.QTimer.singleShot(100, _resize_to_fit)
    QtCore.QTimer.singleShot(200, _remove_min_max_buttons)


def rebuild_current():
    """Rebuild the toolbar widget in place.

    Safe to call even after the workspaceControl has been recreated (e.g. a
    re-dock from the settings dialog destroyed the widget a stored callback
    still points at) — it falls back to repopulating the current control.
    """
    global _toolbar_widget
    if _toolbar_widget is not None:
        try:
            _toolbar_widget.rebuild()
            return
        except RuntimeError:
            # Underlying C++ widget was deleted — repopulate from scratch.
            _toolbar_widget = None
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


def toggle():
    """Toggle the toolbar visibility on or off.

    Bound to the ATK shelf button so a single click hides the toolbar when it
    is showing and restores it when it is hidden.  The underlying
    workspaceControl and all installed tool scripts remain in place — only the
    UI is shown or hidden.
    """
    if cmds.workspaceControl(WORKSPACE_NAME, exists=True):
        if bool(cmds.workspaceControl(WORKSPACE_NAME, q=True, visible=True)):
            cmds.workspaceControl(WORKSPACE_NAME, edit=True, visible=False)
        else:
            cmds.workspaceControl(WORKSPACE_NAME, edit=True, restore=True)
            cmds.workspaceControl(WORKSPACE_NAME, edit=True, visible=True)
    else:
        show()
