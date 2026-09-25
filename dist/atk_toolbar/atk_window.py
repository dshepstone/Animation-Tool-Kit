"""
atk_window.py — keep minimized ATK tool windows lined up at the bottom of
the screen.

Why this exists
---------------
ATK tools parent their windows to Maya's main window so they stay on top of
Maya. On Windows that makes each tool window an *owned* window. When one is
minimized, Windows turns it into a small title-bar "stub". Where that stub
lands depends on the window's remembered minimized position, which is
often left over from earlier moves. So stubs end up floating in the middle
of the screen (over the viewport or picker) instead of along the bottom.

The fix: when a watched tool window is minimized, its stub is placed
in the next free slot along the bottom edge of the screen Maya is on
(left to right, starting a new row above if the bottom row is full). The
stub stays a normal Windows minimized bar: click it (or its restore button)
to bring the tool back.

How it is used
--------------
    atk_loader.launch_tool_fn() runs every tool launcher inside
    ``watch_launch()``. Every top-level window shown during (and shortly
    after) the launch is watched, and dialogs the tool opens later as
    children (editors, reports) are watched too.

Tools can also opt in directly (for shelf launches outside the toolbar):
    try:
        from atk_toolbar.atk_window import watch_window
        watch_window(self)
    except ImportError:
        pass

Everything is a no-op on macOS / Linux.
"""

import sys

try:
    from PySide6 import QtCore, QtWidgets
except ImportError:                                     # Maya < 2025
    from PySide2 import QtCore, QtWidgets

IS_WINDOWS = sys.platform.startswith("win")

_PROP_WATCHED = "_atkBottomMinimize"

# How long the application-wide launch watcher stays active after a launcher
# returns — covers tools that show their window via evalDeferred / timers.
_LAUNCH_GRACE_MS = 1500

# Gap between neighbouring stubs, in physical pixels.
_STUB_GAP = 2

_launch_watchers = []    # keep references alive until their timer removes them


# ---------------------------------------------------------------------------
# Stub layout (pure Python — no Win32, easy to test)
# ---------------------------------------------------------------------------

def choose_stub_slot(work, size, occupied, gap=_STUB_GAP):
    """Top-left (x, y) for a minimized stub of *size* (w, h).

    *work* is the monitor work area (left, top, right, bottom); *occupied*
    holds the (left, top, right, bottom) rects of stubs already on screen.
    Slots run left to right along the bottom edge; a full row continues on
    the row above.
    """
    left, top, right, bottom = work
    w, h = size
    if w <= 0 or h <= 0:
        return left, bottom - max(h, 1)

    def free(x, y):
        for ol, ot, orr, ob in occupied:
            if x < orr and x + w > ol and y < ob and y + h > ot:
                return False
        return True

    y = bottom - h
    while y >= top:
        x = left
        while x + w <= right:
            if free(x, y):
                return x, y
            x += w + gap
        y -= h + gap
    return left, bottom - h          # screen is full of stubs — stack at the corner


# ---------------------------------------------------------------------------
# Win32
# ---------------------------------------------------------------------------

def _win32():
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32

    class WINDOWPLACEMENT(ctypes.Structure):
        _fields_ = [("length", wintypes.UINT), ("flags", wintypes.UINT),
                    ("showCmd", wintypes.UINT), ("ptMinPosition", wintypes.POINT),
                    ("ptMaxPosition", wintypes.POINT),
                    ("rcNormalPosition", wintypes.RECT)]

    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                    ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]

    return ctypes, wintypes, user32, WINDOWPLACEMENT, MONITORINFO


def _rect_tuple(rc):
    return rc.left, rc.top, rc.right, rc.bottom


def _place_minimized_stub(widget):
    """Move *widget*'s minimized stub to the next free bottom slot."""
    try:
        ctypes, wintypes, user32, WINDOWPLACEMENT, MONITORINFO = _win32()
        hwnd = wintypes.HWND(int(widget.winId()))
        if not user32.IsIconic(hwnd):
            return False

        GW_OWNER = 4
        owner = user32.GetWindow(hwnd, GW_OWNER)

        # Work area of the monitor Maya (the owner) is on.
        MONITOR_DEFAULTTONEAREST = 2
        monitor = user32.MonitorFromWindow(owner or hwnd, MONITOR_DEFAULTTONEAREST)
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            return False
        work = _rect_tuple(info.rcWork)

        rc = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rc))
        size = (rc.right - rc.left, rc.bottom - rc.top)

        # Every other visible minimized stub on screen (ATK or not).
        occupied = []
        WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def _collect(other, _lparam):
            if other and other != hwnd.value and user32.IsWindowVisible(other) \
                    and user32.IsIconic(other):
                orc = wintypes.RECT()
                if user32.GetWindowRect(other, ctypes.byref(orc)):
                    occupied.append(_rect_tuple(orc))
            return True

        user32.EnumWindows(WNDENUMPROC(_collect), 0)
        x, y = choose_stub_slot(work, size, occupied)

        # WINDOWPLACEMENT positions are in *workspace* coordinates (relative
        # to the primary monitor's work area) for normal top-level windows.
        SPI_GETWORKAREA = 0x0030
        primary = wintypes.RECT()
        user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(primary), 0)

        wp = WINDOWPLACEMENT()
        wp.length = ctypes.sizeof(WINDOWPLACEMENT)
        if user32.GetWindowPlacement(hwnd, ctypes.byref(wp)):
            WPF_SETMINPOSITION = 0x0001
            SW_SHOWMINNOACTIVE = 7
            wp.flags |= WPF_SETMINPOSITION
            wp.showCmd = SW_SHOWMINNOACTIVE      # stay minimized, don't steal focus
            wp.ptMinPosition = wintypes.POINT(x - primary.left, y - primary.top)
            if user32.SetWindowPlacement(hwnd, ctypes.byref(wp)):
                return True

        # Fallback: move the iconic window directly (screen coordinates).
        SWP_NOSIZE, SWP_NOZORDER, SWP_NOACTIVATE = 0x0001, 0x0004, 0x0010
        return bool(user32.SetWindowPos(hwnd, None, x, y, 0, 0,
                                        SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE))
    except Exception:
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

class _BottomMinimizeFilter(QtCore.QObject):
    """Places the window's stub at the bottom of the screen whenever it is
    minimized, and starts watching dialogs it opens as children."""

    def eventFilter(self, obj, event):
        etype = event.type()
        if etype == QtCore.QEvent.WindowStateChange:
            if obj.isWindow() and obj.windowState() & QtCore.Qt.WindowMinimized \
                    and _is_minimizable_tool_window(obj):
                # Let Windows finish minimizing first, then move the stub.
                QtCore.QTimer.singleShot(0, lambda w=obj: _place_if_alive(w))
        elif etype == QtCore.QEvent.ChildAdded:
            child = event.child()
            if isinstance(child, (QtWidgets.QDialog, QtWidgets.QMainWindow)):
                watch_window(child)
        return False


def _place_if_alive(widget):
    try:
        if widget.isMinimized():
            _place_minimized_stub(widget)
    except RuntimeError:
        pass     # the C++ widget is already gone


def watch_window(widget):
    """Keep *widget*'s minimized stub at the bottom of the screen. Safe to
    call repeatedly and on any platform."""
    if not IS_WINDOWS or not isinstance(widget, QtWidgets.QWidget):
        return
    try:
        if widget.property(_PROP_WATCHED):
            return
        widget.setProperty(_PROP_WATCHED, True)
        # Parented to the widget, so it is deleted with it.
        widget.installEventFilter(_BottomMinimizeFilter(widget))
    except RuntimeError:
        pass


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
