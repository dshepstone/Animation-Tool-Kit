"""Safe wrappers for Maya Blue Pencil commands.

All direct Blue Pencil command calls live here so the UI can fail gracefully when
Maya, a camera, or a Blue Pencil node is not available.
"""

from __future__ import annotations

import os

try:
    from maya import cmds
except Exception:  # Allows importing modules outside Maya for linting/tests.
    cmds = None

# The Blue Pencil commands (bluePencilUtil / bluePencilNode / bluePencilFrame /
# bluePencilLayer) are registered by a Maya plugin. If that plugin is not loaded
# the commands do not exist on ``cmds`` at all, which is why every call raised
# "module 'maya.cmds' has no attribute 'bluePencilUtil'". We load it on demand.
_PROBE_COMMAND = "bluePencilUtil"
_CANDIDATE_PLUGINS = ("bluePencil", "BluePencil", "bluepencil", "BluePencil2", "bluePencil2")
_PLUGIN_LOAD_ATTEMPTED = False
_PLUGIN_WARNED = False


def _warn(message: str) -> None:
    if cmds:
        cmds.warning("Blue Pencil Flipbook Manager: {0}".format(message))
    else:
        print("Blue Pencil Flipbook Manager: {0}".format(message))


def _plugin_search_dirs():
    dirs = []
    for value in (os.environ.get("MAYA_PLUG_IN_PATH", ""),):
        dirs.extend(p for p in value.split(os.pathsep) if p)
    location = os.environ.get("MAYA_LOCATION")
    if location:
        dirs.append(os.path.join(location, "plug-ins"))
    return dirs


def ensure_blue_pencil_plugin():
    """Make sure the Blue Pencil plugin (and its commands) is loaded.

    Returns True when ``cmds.bluePencilUtil`` and friends are callable. The
    plugin file name differs across platforms/versions, so we try the common
    registry names first and then scan the plug-in path for a matching file.
    """
    global _PLUGIN_LOAD_ATTEMPTED
    if cmds is None:
        return False
    # Cheap check first - also picks it up if the user enables it by hand later.
    if hasattr(cmds, _PROBE_COMMAND):
        return True
    if _PLUGIN_LOAD_ATTEMPTED:
        return False
    _PLUGIN_LOAD_ATTEMPTED = True

    for name in _CANDIDATE_PLUGINS:
        try:
            if not cmds.pluginInfo(name, query=True, loaded=True):
                cmds.loadPlugin(name, quiet=True)
        except Exception:
            pass
        if hasattr(cmds, _PROBE_COMMAND):
            return True

    exts = (".mll", ".so", ".bundle", ".py", ".nll.dll")
    for directory in _plugin_search_dirs():
        try:
            names = os.listdir(directory)
        except Exception:
            continue
        for fname in names:
            low = fname.lower()
            if "blue" in low and "pencil" in low and low.endswith(exts):
                try:
                    cmds.loadPlugin(os.path.join(directory, fname), quiet=True)
                except Exception:
                    continue
                if hasattr(cmds, _PROBE_COMMAND):
                    return True
    return hasattr(cmds, _PROBE_COMMAND)


def _warn_plugin_missing():
    global _PLUGIN_WARNED
    if _PLUGIN_WARNED:
        return
    _PLUGIN_WARNED = True
    _warn(
        "Blue Pencil plugin is not loaded. Enable it in Windows > Settings/"
        "Preferences > Plug-in Manager (search 'blue pencil'), or open the "
        "Blue Pencil toolbar once, then try again."
    )


_CALL_FAILED = object()


def _safe_call(command_name: str, **kwargs):
    if cmds is None:
        _warn("Maya commands are unavailable outside Maya.")
        return None
    if not ensure_blue_pencil_plugin():
        _warn_plugin_missing()
        return None
    try:
        command = getattr(cmds, command_name)
        return command(**kwargs)
    except Exception as exc:
        _warn("{0} failed: {1}".format(command_name, exc))
        return None


def _call_quiet(command_name: str, **kwargs):
    """Attempt a command, returning _CALL_FAILED on any error without warning.

    Used when several valid call forms exist and only one is right for the host
    Maya build, so callers can try them in order and warn only if all fail.
    """
    if cmds is None or not ensure_blue_pencil_plugin():
        return _CALL_FAILED
    try:
        return getattr(cmds, command_name)(**kwargs)
    except Exception:
        return _CALL_FAILED


def draw_context(): return _safe_call("bluePencilUtil", draw=True)
def transform_tool(): return _safe_call("bluePencilUtil", transform=True)
def pencil_tool(): return _safe_call("bluePencilUtil", pencilTool=True)
def brush_tool(): return _safe_call("bluePencilUtil", brushTool=True)
def eraser_tool(): return _safe_call("bluePencilUtil", eraserTool=True)
def text_tool(): return _safe_call("bluePencilUtil", textTool=True)
def line_tool(): return _safe_call("bluePencilUtil", lineTool=True)
def arrow_tool(): return _safe_call("bluePencilUtil", arrowTool=True)
def ellipse_tool(): return _safe_call("bluePencilUtil", ellipseTool=True)
def rectangle_tool(): return _safe_call("bluePencilUtil", rectangleTool=True)
def set_draw_color(r, g, b):
    # bluePencilUtil -drawColor takes 0-255 integer channels (e.g. [255, 0, 0]
    # is red) and only commits in edit mode: a plain/create call is rejected
    # ("Invalid command parameters"), while 0.0-1.0 values apply but render as
    # near-black because they are far below the 0-255 range. So: edit mode, with
    # 0-255 values, and a plain-call fallback only for builds that accept it.
    color = [int(round(r)), int(round(g)), int(round(b))]
    for kwargs in ({"edit": True, "drawColor": color}, {"drawColor": color}):
        result = _call_quiet("bluePencilUtil", **kwargs)
        if result is not _CALL_FAILED:
            return result
    _warn("Could not set Blue Pencil draw color.")
    return None


# Blue Pencil sets size/opacity through per-tool option vectors, not standalone
# flags (adjustBrushSize / adjustOpacity are interactive drag toggles, which is
# why passing them a value returned "Invalid command parameters"). Parameter
# order, per the Maya docs:
#   pencilOptions: size opacity pressureSize pressureOpacity
#   brushOptions:  size opacity hardness pressureSize pressureOpacity
_TOOL_OPTIONS = ("pencil", "brush")


def set_tool_size_opacity(tool, size, opacity):
    """Set size and opacity for a Blue Pencil tool.

    ``opacity`` is on Maya's 0-100 scale. Only the pencil and brush tools have a
    documented option layout, so other tools are skipped (no invalid command).
    """
    key = (tool or "").lower()
    if key not in _TOOL_OPTIONS:
        return None
    size = float(size)
    opacity = float(opacity)
    if key == "pencil":
        flag, values = "pencilOptions", [size, opacity, 35.0, 45.0]
    else:
        flag, values = "brushOptions", [size, opacity, 30.0, 35.0, 45.0]
    # Like drawColor, tool options are committed in edit mode; fall back to the
    # plain form for builds that accept it directly.
    for kwargs in ({"edit": True, flag: values}, {flag: values}):
        result = _call_quiet("bluePencilUtil", **kwargs)
        if result is not _CALL_FAILED:
            return result
    _warn("Could not set Blue Pencil {0}.".format(flag))
    return None


def reset_tool(): return _safe_call("bluePencilUtil", resetTool=True)
def refresh_timeline_display(): return _safe_call("bluePencilUtil", refreshTimelineDisplay=True)
def refresh_node(): return _safe_call("bluePencilNode", refresh=True)
def refresh_ghosting(): return _safe_call("bluePencilNode", refreshGhosting=True)
def insert_frame(): return _safe_call("bluePencilFrame", insert=True)
def duplicate_frame(): return _safe_call("bluePencilFrame", duplicate=True)
def delete_frame(): return _safe_call("bluePencilFrame", delete=True)
def clear_frame(): return _safe_call("bluePencilFrame", clear=True)
def cut_frame(): return _safe_call("bluePencilFrame", cutFrame=True)
def copy_frame(): return _safe_call("bluePencilFrame", copy=True)
def paste_frame(): return _safe_call("bluePencilFrame", paste=True)
def step_back(): return _safe_call("bluePencilFrame", stepBack=True)
def step_forward(): return _safe_call("bluePencilFrame", stepForward=True)
def import_frames(): return _safe_call("bluePencilFrame", importFrames=True)
def export_frames(): return _safe_call("bluePencilFrame", exportFrames=True)


def blue_pencil_nodes():
    """Return all Blue Pencil nodes in the scene (shapes and their transforms)."""
    if cmds is None:
        return []
    found = set()
    try:
        types = [t for t in (cmds.allNodeTypes() or []) if "bluepencil" in t.lower()]
        for node_type in types:
            for node in cmds.ls(type=node_type, long=True) or []:
                found.add(node)
    except Exception:
        pass
    nodes = set(found)
    for node in found:
        try:
            for parent in cmds.listRelatives(node, parent=True, fullPath=True) or []:
                nodes.add(parent)
        except Exception:
            pass
    return list(nodes)


def has_blue_pencil_nodes():
    """True if the scene contains any Blue Pencil node(s)."""
    return bool(blue_pencil_nodes())


def export_archive(path):
    # bluePencilFrame -exportArchive <path.zip> writes the actual drawing data
    # (strokes per frame/camera) to a zip archive. The drawings live in this
    # archive, not in the node's plain attributes, so a scene-node export would
    # bring back an empty node. Forward slashes for cross-platform safety.
    return _safe_call("bluePencilFrame", exportArchive=str(path).replace("\\", "/"))


def import_archive(path):
    return _safe_call("bluePencilFrame", importArchive=str(path).replace("\\", "/"))


def retime_frame(frames):
    # bluePencilFrame -retime <int> shifts the current drawing by N frames.
    try:
        return _safe_call("bluePencilFrame", retime=int(frames))
    except (TypeError, ValueError):
        _warn("Retime requires a whole number of frames.")
        return None


def current_time():
    if cmds is None:
        return 1
    try:
        return int(round(cmds.currentTime(query=True)))
    except Exception as exc:
        _warn("currentTime query failed: {0}".format(exc))
        return 1


def set_current_time(frame):
    if cmds is None:
        return None
    try:
        return cmds.currentTime(frame, edit=True)
    except Exception as exc:
        _warn("currentTime set failed: {0}".format(exc))
        return None


def cameras():
    """Return renderable camera *transform* names (not shape nodes)."""
    if cmds is None:
        return ["persp"]
    try:
        shapes = cmds.ls(type="camera", long=False) or []
        result = []
        seen = set()
        for shape in shapes:
            parents = cmds.listRelatives(shape, parent=True) or []
            name = parents[0] if parents else shape
            if name not in seen:
                seen.add(name)
                result.append(name)
        return result or ["persp"]
    except Exception as exc:
        _warn("camera query failed: {0}".format(exc))
        return ["persp"]


def active_viewport_camera():
    """Return the camera *transform* of the focused/active 3d viewport, or None.

    This is the viewport the user is currently working in, so tracked marks and
    their thumbnails are tagged with (and captured from) the right camera.
    """
    if cmds is None:
        return None
    panel = None
    try:
        focused = cmds.getPanel(withFocus=True)
        if focused and cmds.getPanel(typeOf=focused) == "modelPanel":
            panel = focused
    except Exception:
        pass
    if panel is None:
        try:
            for candidate in cmds.getPanel(visiblePanels=True) or []:
                if cmds.getPanel(typeOf=candidate) == "modelPanel":
                    panel = candidate
                    break
        except Exception:
            pass
    if panel is None:
        return None
    try:
        cam = cmds.modelPanel(panel, query=True, camera=True)
    except Exception:
        return None
    if not cam:
        return None
    try:
        if cmds.objExists(cam) and cmds.objectType(cam) == "camera":
            parents = cmds.listRelatives(cam, parent=True) or []
            return parents[0] if parents else cam
    except Exception:
        pass
    return cam


def active_camera():
    """Best-effort active Blue Pencil camera, or None."""
    if cmds is None or not ensure_blue_pencil_plugin():
        return None
    try:
        cam = cmds.bluePencilNode(query=True, camera=True)
        if isinstance(cam, (list, tuple)):
            cam = cam[0] if cam else None
        return cam or None
    except Exception:
        return None


def _layers_for_camera(camera):
    """Return Blue Pencil layer names for a camera via the bluePencilLayer command.

    Blue Pencil layers are not scene nodes you can list with ``cmds.ls`` - they
    are owned per-camera and queried through the ``bluePencilLayer`` command, so
    the previous ``cmds.ls(type="bluePencilLayer")`` call never returned data.
    """
    if not ensure_blue_pencil_plugin():
        return []
    try:
        count = cmds.bluePencilLayer(camera, query=True, count=True)
    except Exception:
        return []
    if not count:
        return []
    names = []
    for index in range(int(count)):
        name = None
        for kwargs in (
            {"query": True, "name": index, "queryName": True},
            {"query": True, "queryName": index},
        ):
            try:
                result = cmds.bluePencilLayer(camera, **kwargs)
            except Exception:
                continue
            if result:
                name = result[0] if isinstance(result, (list, tuple)) else result
                break
        names.append(name or "Layer {0}".format(index + 1))
    return names


def blue_pencil_layers(camera=None):
    if cmds is None:
        return ["Default"]
    names = []
    try:
        cam = camera or active_camera()
        if cam:
            names = _layers_for_camera(cam)
    except Exception as exc:
        _warn("layer query failed: {0}".format(exc))
    return names or ["Default"]
