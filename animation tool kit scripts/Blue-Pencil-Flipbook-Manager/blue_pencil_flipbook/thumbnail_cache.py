"""Viewport thumbnail capture helpers."""

from __future__ import annotations

import os
import time

from . import maya_blue_pencil_api as bp
from . import metadata_store

try:
    from maya import cmds
except Exception:
    cmds = None


def cache_dir():
    if cmds:
        try:
            base = cmds.internalVar(userPrefDir=True)
        except Exception:
            base = os.path.expanduser("~")
    else:
        base = os.path.expanduser("~")
    path = os.path.join(base, "blue_pencil_flipbook", "thumbnail_cache")
    os.makedirs(path, exist_ok=True)
    return path


def thumbnail_path(entry):
    safe_uid = entry.get("uid", "frame")
    return os.path.join(cache_dir(), safe_uid + ".png")


def has_thumbnail(entry):
    """True when the entry already points at a thumbnail file on disk."""
    path = entry.get("thumbnail") or ""
    return bool(path) and os.path.exists(path)


def delete_thumbnail(entry):
    """Remove the cached thumbnail image for an entry, if any. Returns True when
    a file was deleted."""
    removed = False
    for path in {entry.get("thumbnail") or "", thumbnail_path(entry)}:
        try:
            if path and os.path.exists(path):
                os.remove(path)
                removed = True
        except Exception:
            pass
    return removed


def _camera_transform(name):
    if not name or cmds is None:
        return name
    try:
        if cmds.objExists(name) and cmds.objectType(name) == "camera":
            parents = cmds.listRelatives(name, parent=True) or []
            return parents[0] if parents else name
    except Exception:
        pass
    return name


def _active_model_editor(camera=None):
    """Return a usable 3d viewport panel, preferring one showing ``camera``.

    playblast needs a model panel. When the tool window holds focus (which it
    does right after a button click) the "active" panel may not be a model
    panel, so we resolve one explicitly and, when possible, pick the panel that
    is actually looking through the marked camera.
    """
    if cmds is None:
        return None
    panels = []
    try:
        focused = cmds.getPanel(withFocus=True)
        if focused and cmds.getPanel(typeOf=focused) == "modelPanel":
            panels.append(focused)
    except Exception:
        pass
    try:
        for panel in cmds.getPanel(visiblePanels=True) or []:
            if panel not in panels and cmds.getPanel(typeOf=panel) == "modelPanel":
                panels.append(panel)
    except Exception:
        pass
    try:
        for panel in cmds.getPanel(type="modelPanel") or []:
            if panel not in panels:
                panels.append(panel)
    except Exception:
        pass
    if not panels:
        return None
    if camera:
        target = _camera_transform(camera)
        for panel in panels:
            try:
                cam = cmds.modelPanel(panel, query=True, camera=True)
            except Exception:
                cam = None
            if cam and _camera_transform(cam) == target:
                return panel
    return panels[0]


def _ensure_blue_pencil_visible(panel):
    """Turn on the Blue Pencil plugin display filter for this panel.

    Blue Pencil draws as a plugin overlay (Show > Plugins > Blue Pencil). If
    that filter is off on the panel the playblast renders through, the stroke is
    not captured at all and the thumbnail comes out empty. Enabling it before
    the blast is harmless if it was already on, and we leave it on afterwards
    (that is the state the user is already working in).
    """
    if cmds is None or not panel:
        return
    # Discover the actual filter name where possible, then fall back to guesses.
    names = set()
    try:
        listed = cmds.modelEditor(panel, query=True, pluginObjects=True)
        if listed:
            names.update(listed)
    except Exception:
        pass
    names.update({"bluePencil", "BluePencil", "bluePencilDisplayFilter"})
    for name in names:
        low = str(name).lower()
        if "blue" in low and "pencil" in low:
            try:
                cmds.modelEditor(panel, edit=True, pluginObjects=[name, True])
            except Exception:
                pass
    try:
        cmds.modelEditor(panel, edit=True, pluginShapes=True)
    except Exception:
        pass


# Scene-content display flags. For a non-isolated capture these are forced ON so
# the thumbnail shows the geometry and rig behind the drawing; for an isolated
# capture they are forced OFF so only the Blue Pencil drawing remains on white.
# NOTE: pluginShapes is intentionally excluded so the Blue Pencil overlay (a
# plugin draw) is never hidden by the isolate pass.
_SCENE_FLAGS = (
    "grid", "polymeshes", "nurbsSurfaces", "nurbsCurves", "subdivSurfaces",
    "planes", "joints", "ikHandles", "deformers", "locators", "dynamics",
    "fluids", "follicles", "hairSystems", "nCloths", "nParticles", "nRigids",
    "imagePlane", "manipulators", "cameras", "lights", "dimensions", "handles",
    "pivots", "textures", "motionTrails", "strokes", "controllers",
)


def _query_flags(panel, flags):
    state = {}
    for flag in flags:
        try:
            state[flag] = cmds.modelEditor(panel, query=True, **{flag: True})
        except Exception:
            pass
    return state


def _set_flags(panel, state):
    """Set each flag from a {flag: value} mapping."""
    for flag, value in state.items():
        try:
            cmds.modelEditor(panel, edit=True, **{flag: value})
        except Exception:
            pass


def _apply_scene_visibility(panel, visible):
    """Force geometry/rig display on (visible=True) or off, returning the prior
    state so it can be restored after the capture."""
    previous = _query_flags(panel, _SCENE_FLAGS)
    _set_flags(panel, {flag: bool(visible) for flag in previous})
    return previous




def _row_background(image, y, width):
    """Median color of a row's left/right edge pixels (per-row handles the
    viewport's vertical background gradient)."""
    samples = []
    for x in (0, 1, 2, 3, width - 4, width - 3, width - 2, width - 1):
        rgb = image.pixel(x, y)
        samples.append(((rgb >> 16) & 255, (rgb >> 8) & 255, rgb & 255))
    samples.sort()
    return samples[len(samples) // 2]


def _composite_on_white(path):
    """Replace the captured background with pure white, keeping the strokes.

    Offscreen playblast on some Maya builds (2026 included) ignores background
    display-pref changes, so instead of relying on the viewport we key the
    background out of the image itself: each row's background color is sampled
    from its edge pixels and pixels near that color are blended to white, while
    stroke pixels (far from the background color) keep their own color. If the
    background already is white this is a no-op.
    """
    try:
        from .qt_compat import QtGui
    except Exception:
        return False
    if QtGui is None or not path or not os.path.exists(path):
        return False
    image = QtGui.QImage(path)
    if image.isNull():
        return False
    image = image.convertToFormat(QtGui.QImage.Format_RGB32)
    width, height = image.width(), image.height()
    if width < 8 or height < 2:
        return False
    # Narrow band so only near-background pixels turn white; this preserves even
    # dark strokes (a near-black line on a dark viewport is still well outside
    # the band) while cleanly whitening the background.
    lo, hi = 10.0, 34.0  # color-distance band for the soft key
    for y in range(height):
        br, bg_, bb = _row_background(image, y, width)
        for x in range(width):
            rgb = image.pixel(x, y)
            r = (rgb >> 16) & 255
            g = (rgb >> 8) & 255
            b = rgb & 255
            dist = ((r - br) ** 2 + (g - bg_) ** 2 + (b - bb) ** 2) ** 0.5
            if dist <= lo:
                value = 0xFFFFFFFF
            elif dist >= hi:
                value = 0xFF000000 | rgb
            else:
                a = (dist - lo) / (hi - lo)
                nr = int(r * a + 255.0 * (1.0 - a) + 0.5)
                ng = int(g * a + 255.0 * (1.0 - a) + 0.5)
                nb = int(b * a + 255.0 * (1.0 - a) + 0.5)
                value = 0xFF000000 | (nr << 16) | (ng << 8) | nb
            image.setPixel(x, y, value)
    return bool(image.save(path, "PNG"))


def _warn_capture(message):
    if cmds:
        cmds.warning("Blue Pencil Flipbook Manager: " + message)


def _scale_to_fit(path, max_width, max_height):
    """Downscale the image to fit max bounds, preserving aspect."""
    try:
        from .qt_compat import QtCore, QtGui
    except Exception:
        return
    if QtGui is None:
        return
    image = QtGui.QImage(path)
    if image.isNull():
        return
    if image.width() > max_width or image.height() > max_height:
        image = image.scaled(max_width, max_height, QtCore.Qt.KeepAspectRatio,
                             QtCore.Qt.SmoothTransformation)
        image.save(path, "PNG")


def _image_mostly_black(path, threshold=8, fraction=0.85):
    """True when the image is essentially pure black — the signature of a failed
    VP2 capture (only the overlay pass rendered). A healthy capture always has
    Maya's gray background gradient, which is far above the threshold."""
    try:
        from .qt_compat import QtGui
    except Exception:
        return False
    if QtGui is None:
        return False
    image = QtGui.QImage(path)
    if image.isNull():
        return True
    image = image.convertToFormat(QtGui.QImage.Format_RGB32)
    width, height = image.width(), image.height()
    step_x, step_y = max(1, width // 64), max(1, height // 64)
    total = black = 0
    for y in range(0, height, step_y):
        for x in range(0, width, step_x):
            rgb = image.pixel(x, y)
            if ((rgb >> 16) & 255) < threshold and ((rgb >> 8) & 255) < threshold and (rgb & 255) < threshold:
                black += 1
            total += 1
    return total > 0 and (float(black) / total) >= fraction


def _capture_refresh_dump(panel, path, frame, width, height):
    """Dump the current on-screen view render to a file (refresh -cv -fn).

    This uses the interactive render already on screen rather than a separate
    offscreen pass, so it is the first choice."""
    try:
        cmds.refresh(currentView=True, fileExtension="png", filename=path)
        return os.path.exists(path)
    except Exception:
        return False


def _capture_view_buffer(panel, path, frame, width, height):
    """Read the 3d view's color buffer via M3dView (may miss the beauty pass on
    some VP2/driver combinations — validated by the caller)."""
    try:
        import maya.OpenMayaUI as omui
        import maya.OpenMaya as om
    except Exception:
        return False
    view = None
    if panel:
        try:
            view = omui.M3dView()
            omui.M3dView.getM3dViewFromModelPanel(panel, view)
        except Exception:
            view = None
    if view is None:
        try:
            view = omui.M3dView.active3dView()
        except Exception:
            return False
    try:
        view.refresh(False, True)
        image = om.MImage()
        view.readColorBuffer(image, True)
        image.writeToFile(path, "png")
        return os.path.exists(path)
    except Exception:
        return False


def _capture_playblast(panel, path, frame, width, height):
    """Single-frame offscreen playblast (also validated by the caller)."""
    try:
        result = cmds.playblast(
            completeFilename=path,
            forceOverwrite=True,
            format="image",
            compression="png",
            widthHeight=(width, height),
            showOrnaments=False,
            viewer=False,
            offScreen=True,
            clearCache=True,
            startTime=frame,
            endTime=frame,
            frame=[frame],
            percent=100,
        )
        result = str(result or path)
        if result != path and os.path.exists(result):
            try:
                import shutil
                shutil.move(result, path)
            except Exception:
                return os.path.exists(result)
        return os.path.exists(path)
    except Exception:
        return False


def _capture_screen_grab(panel, path, frame, width, height):
    """Grab the viewport widget's actual desktop pixels — guaranteed WYSIWYG.

    Floating Qt windows are hidden for the instant of the grab so dialogs, the
    flipbook manager, or preview windows cannot cover the viewport, then they
    are restored."""
    try:
        from .qt_compat import QtCore, QtGui, QtWidgets
        import maya.OpenMayaUI as omui
    except Exception:
        return False
    if QtWidgets is None or not panel:
        return False
    try:
        try:
            from shiboken6 import wrapInstance
        except ImportError:
            from shiboken2 import wrapInstance
        pointer = omui.MQtUtil.findControl(panel)
        if not pointer:
            return False
        widget = wrapInstance(int(pointer), QtWidgets.QWidget)
    except Exception:
        return False
    hidden = []
    try:
        viewport_window = widget.window()
        for top in QtWidgets.QApplication.topLevelWidgets():
            try:
                if not top or top is viewport_window or not top.isVisible():
                    continue
                # Do not hide the Maya main window that owns the model panel;
                # hide every other floating top-level window so the desktop grab
                # sees the unobstructed viewport.
                if viewport_window and top.isAncestorOf(viewport_window):
                    continue
                # Transient popups (tooltips, open combo dropdowns) are hidden
                # but not restored — re-showing them detached looks broken.
                transient = top.windowType() in (QtCore.Qt.ToolTip, QtCore.Qt.Popup)
                top.hide()
                if not transient:
                    hidden.append(top)
            except Exception:
                pass
        QtWidgets.QApplication.processEvents()
        try:
            cmds.refresh(force=True)
        except Exception:
            pass
        # QWidget.hide() returns before the OS compositor repaints the desktop
        # region the window uncovered, so grabbing immediately can still read
        # the stale pixels with the "hidden" window in them. Pump the event
        # loop across several composition frames before reading the screen.
        deadline = time.time() + 0.25
        while time.time() < deadline:
            QtCore.QThread.msleep(16)
            QtWidgets.QApplication.processEvents()
        try:
            cmds.refresh(force=True)
        except Exception:
            pass
        origin = widget.mapToGlobal(QtCore.QPoint(0, 0))
        grab_rect = QtCore.QRect(origin, QtCore.QSize(widget.width(), widget.height()))
        for top in QtWidgets.QApplication.topLevelWidgets():
            try:
                if not top or top is viewport_window or not top.isVisible():
                    continue
                if viewport_window and top.isAncestorOf(viewport_window):
                    continue
                if top.frameGeometry().intersects(grab_rect):
                    # Something is still covering the viewport; hand this
                    # frame to an offscreen fallback instead of baking the
                    # window into the thumbnail.
                    return False
            except Exception:
                pass
        window_handle = widget.window().windowHandle()
        screen = window_handle.screen() if window_handle else QtGui.QGuiApplication.primaryScreen()
        if screen is None:
            return False
        pixmap = screen.grabWindow(0, origin.x(), origin.y(), widget.width(), widget.height())
        return bool(pixmap.save(path, "PNG")) and os.path.exists(path)
    except Exception:
        return False
    finally:
        for top in reversed(hidden):
            try:
                top.show()
            except Exception:
                pass
        try:
            QtWidgets.QApplication.processEvents()
        except Exception:
            pass


# Capture methods in order of preference; each writes to `path` and returns
# True on success. The result is then validated (a mostly-black image means the
# VP2 beauty pass was missed) and the next method is tried on failure.
_CAPTURE_METHODS = (
    ("view dump", _capture_refresh_dump),
    ("view buffer", _capture_view_buffer),
    ("playblast", _capture_playblast),
    ("screen grab", _capture_screen_grab),
)

# Non-isolated thumbnails must be WYSIWYG with the animator's viewport. On some
# Maya/VP2 combinations the offscreen/current-view APIs can return only the Blue
# Pencil overlay composited over a plain viewport background, even though the
# visible model panel is drawing geometry and rig controls correctly. Try the
# desktop grab first in normal mode because it captures the real model-panel
# pixels after hiding this tool's windows. Keep the offscreen paths as fallbacks
# for minimized/remote sessions where a screen grab may not be available.
_WYSIWYG_CAPTURE_METHODS = (
    ("screen grab", _capture_screen_grab),
    ("view dump", _capture_refresh_dump),
    ("view buffer", _capture_view_buffer),
    ("playblast", _capture_playblast),
)


# Captured at preview resolution; the cards scale it down to 160x90 and the
# click-to-review dialog shows it large (up to 960x540) without a second file.
def capture_thumbnail(entry, width=960, height=540, isolate=False):
    if cmds is None:
        return ""
    frame = int(entry.get("frame", 1))
    path = thumbnail_path(entry)
    bp.set_current_time(frame)
    editor = _active_model_editor(entry.get("camera"))

    # Isolate mode temporarily hides the scene content on the capture panel so
    # only the drawing remains (then the background is keyed to white). Normal
    # mode should look like a regular playblast/WYSIWYG capture, so force the
    # known scene-content flags on for the capture and restore the animator's
    # model-editor state afterwards. This also undoes any stale hidden-state left
    # by a previous failed isolate capture.
    scene_state = None
    if editor:
        scene_state = _apply_scene_visibility(editor, visible=not isolate)
        _ensure_blue_pencil_visible(editor)
        try:
            cmds.refresh(force=True)
        except Exception:
            pass

    try:
        captured = ""
        methods = _CAPTURE_METHODS if isolate else _WYSIWYG_CAPTURE_METHODS
        for name, method in methods:
            try:
                ok = method(editor, path, frame, width, height)
            except Exception:
                ok = False
            if not ok or not os.path.exists(path):
                continue
            if _image_mostly_black(path):
                # Overlay-only capture (no beauty pass) — try the next method,
                # but keep this file as a last resort.
                captured = captured or ""
                continue
            captured = path
            break
        if not captured:
            # Every method came back black/empty; keep whatever the last method
            # wrote rather than nothing, or bail if no file exists at all.
            if not os.path.exists(path):
                _warn_capture("no viewport available for thumbnail capture.")
                return ""
            captured = path
        _scale_to_fit(captured, width, height)
        if isolate:
            _composite_on_white(captured)
        metadata_store.set_thumbnail(entry.get("uid"), captured)
        return captured
    finally:
        if scene_state is not None:
            _set_flags(editor, scene_state)
            try:
                cmds.refresh(force=True)
            except Exception:
                pass


def regenerate_all(camera=None, layer=None, isolate=False):
    data = metadata_store.load_metadata()
    paths = []
    for entry in data.get("frames", []):
        if camera and entry.get("camera") != camera:
            continue
        if layer and entry.get("layer") != layer:
            continue
        path = capture_thumbnail(entry, isolate=isolate)
        if path:
            paths.append(path)
    return paths
