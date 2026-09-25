"""
atk_window.py — make ATK tool windows minimize to the Windows taskbar.

Why this exists
---------------
ATK tools parent their windows to Maya's main window so they stay on top of
Maya. On Windows that makes each tool window an *owned* window, and the Shell
never gives owned windows a taskbar button. When one is minimized, Windows
turns it into a small "iconic" title-bar stub and parks it inside Maya: over
the viewport or picker, or stacked at the bottom-left of the screen. That is
the stray title bar you see when a tool is minimized.

The fix is to give the tool window the WS_EX_APPWINDOW extended style
("force a top-level window onto the taskbar when it is visible"). The
window stays owned by Maya, so it still floats above Maya and hides with it,
but minimize now goes to its own taskbar button, like any normal window.
The style has to be in place before the native window is shown, so it is
applied from the window's Show event.

How it is used
--------------
    atk_loader.launch_tool_fn() runs every tool launcher inside
    ``watch_launch()``. Every top-level window shown during (and shortly
    after) the launch is watched: the style is applied on each Show, and
    dialogs the tool opens later as children (editors, pickers, reports)
    are watched too.

Tools can also opt in directly (for shelf launches outside the toolbar):
    try:
        from atk_toolbar.atk_window import watch_window
        watch_window(self)
    except ImportError:
        pass

Everything is a no-op on macOS / Linux, where minimized windows already go
to the Dock / taskbar.
"""

import sys

try:
    from PySide6 import QtCore, QtWidgets
except ImportError:                                     # Maya < 2025
    from PySide2 import QtCore, QtWidgets

IS_WINDOWS = sys.platform.startswith("win")

_GWL_EXSTYLE      = -20
_WS_EX_TOOLWINDOW = 0x00000080
_WS_EX_APPWINDOW  = 0x00040000

_PROP_WATCHED = "_atkTaskbarMinimize"

# How long the application-wide launch watcher stays active after a launcher
# returns — covers tools that show their window via evalDeferred / timers.
_LAUNCH_GRACE_MS = 1500

_launch_watchers = []    # keep references alive until their timer removes them


# ---------------------------------------------------------------------------
# Win32
# ---------------------------------------------------------------------------

def _user32():
    import ctypes
    user32 = ctypes.windll.user32
    get = getattr(user32, "GetWindowLongPtrW", None) or user32.GetWindowLongW
    set_ = getattr(user32, "SetWindowLongPtrW", None) or user32.SetWindowLongW
    get.restype, get.argtypes = ctypes.c_ssize_t, [ctypes.c_void_p, ctypes.c_int]
    set_.restype = ctypes.c_ssize_t
    set_.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
    return get, set_


def _set_app_window_style(widget):
    """Give *widget*'s native window its own taskbar button. True if changed."""
    try:
        hwnd = int(widget.winId())
        get, set_ = _user32()
        style = get(hwnd, _GWL_EXSTYLE)
        new = (style | _WS_EX_APPWINDOW) & ~_WS_EX_TOOLWINDOW
        if new != style:
            set_(hwnd, _GWL_EXSTYLE, new)
            return True
    except Exception:
        pass
    return False


# ---------------------------------------------------------------------------
# Which windows qualify
# ---------------------------------------------------------------------------

def _is_minimizable_tool_window(widget):
    """True for a top-level window that has a minimize button and is not
    Maya's own main window."""
    if not isinstance(widget, QtWidgets.QWidget) or not widget.isWindow():
        return False
    if widget.objectName() == "MayaWindow":
        return False
    flags = widget.windowFlags()
    wtype = flags & QtCore.Qt.WindowType_Mask
    if wtype in (QtCore.Qt.Tool, QtCore.Qt.Popup, QtCore.Qt.ToolTip,
                 QtCore.Qt.SplashScreen, QtCore.Qt.Desktop, QtCore.Qt.SubWindow,
                 QtCore.Qt.Drawer, QtCore.Qt.Sheet, QtCore.Qt.ForeignWindow):
        return False
    if flags & QtCore.Qt.WindowMinimizeButtonHint:
        return True
    customised = flags & (QtCore.Qt.CustomizeWindowHint | QtCore.Qt.WindowTitleHint
                          | QtCore.Qt.WindowSystemMenuHint
                          | QtCore.Qt.WindowMaximizeButtonHint
                          | QtCore.Qt.WindowCloseButtonHint)
    # A plain Qt.Window (QMainWindow, setWindowFlags(Qt.Window)) gets
    # minimize / maximize buttons by default; dialogs don't.
    return not customised and wtype == QtCore.Qt.Window


# ---------------------------------------------------------------------------
# Per-window watcher
# ---------------------------------------------------------------------------

class _TaskbarMinimizeFilter(QtCore.QObject):
    """Applies the taskbar style on every Show of the watched window (Qt
    recreates the native window when window flags change) and starts
    watching dialogs the window opens as children."""

    def eventFilter(self, obj, event):
        etype = event.type()
        if etype == QtCore.QEvent.Show:
            if _is_minimizable_tool_window(obj):
                _set_app_window_style(obj)
        elif etype == QtCore.QEvent.ChildAdded:
            child = event.child()
            if isinstance(child, (QtWidgets.QDialog, QtWidgets.QMainWindow)):
                watch_window(child)
        return False


def watch_window(widget):
    """Make *widget* (a tool window) minimize to the taskbar. Safe to call
    repeatedly and on any platform."""
    if not IS_WINDOWS or not isinstance(widget, QtWidgets.QWidget):
        return
    try:
        if widget.property(_PROP_WATCHED):
            return
        widget.setProperty(_PROP_WATCHED, True)
        # Parented to the widget, so it is deleted with it.
        widget.installEventFilter(_TaskbarMinimizeFilter(widget))
        if widget.isVisible() and _is_minimizable_tool_window(widget):
            # Already on screen: the style takes effect for the taskbar the
            # next time the window is shown.
            _set_app_window_style(widget)
    except RuntimeError:
        pass     # the C++ widget is already gone


# ---------------------------------------------------------------------------
# Launch watcher
# ---------------------------------------------------------------------------

class _LaunchWatcher(QtCore.QObject):
    """Short-lived application-wide filter: watches every top-level window
    that is shown while a tool is launching."""

    def eventFilter(self, obj, event):
        if event.type() == QtCore.QEvent.Show:
            try:
                if isinstance(obj, QtWidgets.QWidget) and obj.isWindow():
                    watch_window(obj)
                    if _is_minimizable_tool_window(obj):
                        _set_app_window_style(obj)
            except RuntimeError:
                pass
        return False


class watch_launch(object):
    """Context manager wrapped around a tool launcher:

        with watch_launch():
            tool.show()
    """

    def __enter__(self):
        self._app = QtWidgets.QApplication.instance() if IS_WINDOWS else None
        self._watcher = None
        if self._app is not None:
            self._watcher = _LaunchWatcher()
            self._app.installEventFilter(self._watcher)
            _launch_watchers.append(self._watcher)
        return self

    def __exit__(self, *exc):
        watcher, app = self._watcher, self._app
        if watcher is not None:
            def _remove():
                try:
                    app.removeEventFilter(watcher)
                except RuntimeError:
                    pass
                if watcher in _launch_watchers:
                    _launch_watchers.remove(watcher)
            QtCore.QTimer.singleShot(_LAUNCH_GRACE_MS, _remove)
        return False
