# =============================================================================
# xform_copy_paste.py
#
# Copy Xform World Space — Maya Animation Utility
#
# Copies and pastes world-space transforms (translate, rotate, scale) between
# objects. Also known as "Sticky Tool" or "Animation Recorder".
#
# Usage: install via install_xform_copy_paste.mel, then click the shelf button.
#
# Functions:
#   show()                                - Open the tool window
#   auto_xform_world_space()              - Copy first selected, paste to rest
#   copy_xform_world_space()              - Copy xform from first selected (single frame)
#   copy_xform_playback_range()           - Copy all frames in playback range
#   copy_xform_world_space_multi_range()  - Copy all selected across playback range
#   paste_xform_world_space()             - Paste stored xform at current frame
#   paste_xform_world_space_all_keys()    - Paste at all existing keyframe times
#   paste_xform_world_space_bake_frames() - Bake stored range xform to targets
#   paste_xform_world_space_next_frame()  - Paste then advance timeline by 1
#   paste_xform_world_space_keys_range()  - Paste multi-object data at existing keys
#   show_hotkey_setup()                   - Assign Maya hotkeys to any function
#
# Requirements: Maya 2022+ (PySide6 or PySide2)
# =============================================================================

import os
import shutil

import maya.cmds as cmds

try:
    from PySide6 import QtCore, QtGui, QtWidgets
    from shiboken6 import wrapInstance
except ImportError:  # Maya 2022–2024
    from PySide2 import QtCore, QtGui, QtWidgets
    from shiboken2 import wrapInstance

from maya import OpenMayaUI as omui

WINDOW_OBJECT_NAME = "xformCopyPasteUI"
HOTKEY_WINDOW_OBJECT_NAME = "xformCopyPasteHotkeyUI"

# Legacy cmds-based window id from v1 of this tool — deleted on show() so a
# reload never leaves a stale duplicate window open.
_LEGACY_WIN_ID = "xform_copy_paste_win"


# ---------------------------------------------------------------------------
# Maya drag-and-drop hook
# Called by Maya when this .py file is dragged onto the viewport.
# Copies the script to userScriptDir and installs a shelf button.
# ---------------------------------------------------------------------------
def onMayaDroppedPythonFile(*args):
    import sys
    import maya.mel as mel

    # Locate this file
    src = None
    try:
        src = os.path.abspath(__file__)
    except NameError:
        if args and isinstance(args[0], str) and os.path.isfile(args[0]):
            src = args[0]

    # Copy script to userScriptDir
    scripts_dir = cmds.internalVar(userScriptDir=True)
    src_dir = None
    if src and os.path.isfile(src):
        src_dir = os.path.dirname(src)
        dst = os.path.join(scripts_dir, "xform_copy_paste.py")
        shutil.copy2(src, dst)
        print("xform_copy_paste: Script copied to " + dst)
    else:
        cmds.warning("xform_copy_paste: Could not locate source file to copy.")

    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)

    # Copy icon to Maya icons directory (optional — falls back to default icon)
    icon_name = "commandButton.png"
    if src_dir:
        src_icon = os.path.join(src_dir, "xform_copy_paste.png")
        if os.path.isfile(src_icon):
            pref_dir  = cmds.internalVar(userPrefDir=True)
            icons_dir = os.path.join(pref_dir, "icons")
            try:
                os.makedirs(icons_dir, exist_ok=True)
                shutil.copy2(src_icon, os.path.join(icons_dir, "xform_copy_paste.png"))
                icon_name = "xform_copy_paste.png"
                print("xform_copy_paste: Icon copied to " + icons_dir)
            except Exception as e:
                cmds.warning("xform_copy_paste: Could not copy icon — " + str(e))

    # Shelf button Python command
    py_cmd = (
        "import sys, importlib\n"
        "import maya.cmds as cmds\n"
        "scripts_dir = cmds.internalVar(userScriptDir=True)\n"
        "if scripts_dir not in sys.path:\n"
        "    sys.path.insert(0, scripts_dir)\n"
        "import xform_copy_paste\n"
        "importlib.reload(xform_copy_paste)\n"
        "xform_copy_paste.show()\n"
    )

    # Get the currently active shelf
    try:
        shelf_top     = mel.eval("$tmp = $gShelfTopLevel")
        current_shelf = cmds.shelfTabLayout(shelf_top, q=True, st=True)
    except Exception:
        current_shelf = "Custom"
        if not cmds.shelfLayout("Custom", exists=True):
            mel.eval("addNewShelf Custom")

    # Remove any existing XformCP button (prevent duplicates)
    kids = cmds.shelfLayout(current_shelf, q=True, ca=True) or []
    for kid in kids:
        try:
            if cmds.shelfButton(kid, q=True, l=True) == "XformCP":
                cmds.deleteUI(kid)
        except Exception:
            pass

    # Add shelf button
    cmds.shelfButton(
        parent=current_shelf,
        label="XformCP",
        annotation="Copy Xform World Space — open tool window",
        image=icon_name,
        sourceType="python",
        command=py_cmd,
    )
    cmds.refresh(force=True)

    print("xform_copy_paste: Shelf button 'XformCP' installed on '" + current_shelf + "'.")
    try:
        cmds.inViewMessage(
            amg="<b>Copy Xform World Space</b> installed - click <b>XformCP</b> on the shelf.",
            pos="midCenter",
            fade=True,
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Module-level xform store
# All Copy operations clear the other modes to prevent mixing stale data.
# ---------------------------------------------------------------------------
_XFORM_STORE = {
    "translate":  None,   # list[float, float, float] — single-frame copy
    "rotate":     None,   # list[float, float, float]
    "scale":      None,   # list[float, float, float]
    "frame_data": None,   # dict[int, {t,r,s}] — single-object range copy
    "multi_data": None,   # list[dict[int, {t,r,s}]] — multi-object range copy
                          #   index matches selection order at copy time
}


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _get_xform(obj):
    """Return (translate, rotate, scale) world-space lists for obj at current time."""
    t = cmds.xform(obj, q=True, ws=True, t=True)
    r = cmds.xform(obj, q=True, ws=True, ro=True)
    s = cmds.xform(obj, q=True, ws=True, s=True)
    return t, r, s


def _world_to_local_scale(obj, s):
    """Convert a world-space scale into the local scale to set on obj.

    Maya's xform command only honours -worldSpace for translate and rotate
    when SETTING values — scale is always applied in local space.  To land on
    the requested world-space scale, divide out the parent's accumulated
    world scale first.
    """
    parent = cmds.listRelatives(obj, parent=True, fullPath=True)
    if not parent:
        return list(s)
    ps = cmds.xform(parent[0], q=True, ws=True, s=True)
    return [sv / pv if abs(pv) > 1e-9 else sv for sv, pv in zip(s, ps)]


def _set_xform(obj, t, r, s):
    """Apply world-space translate, rotate, scale to obj.

    Each component is applied independently so a locked or connected channel
    (common on rig controls, e.g. locked scale) skips with a warning instead
    of aborting the whole paste.
    """
    try:
        cmds.xform(obj, ws=True, t=t)
    except RuntimeError:
        cmds.warning("xform_copy_paste: could not set translate on '{}' (locked/connected) — skipped.".format(obj))
    try:
        cmds.xform(obj, ws=True, ro=r)
    except RuntimeError:
        cmds.warning("xform_copy_paste: could not set rotate on '{}' (locked/connected) — skipped.".format(obj))
    try:
        cmds.xform(obj, s=_world_to_local_scale(obj, s))
    except RuntimeError:
        cmds.warning("xform_copy_paste: could not set scale on '{}' (locked/connected) — skipped.".format(obj))


def _set_keyframe(obj, frame):
    """Key all settable transform channels on obj at the given frame.

    Intentionally does NOT pass explicit values — Maya keys whatever the
    attribute currently holds.  This is correct after a _set_xform() call
    because _set_xform places the object in world space, and Maya stores the
    resulting *local* channel values.  Passing world-space values directly
    as 'v=' would be wrong for any object inside a parent hierarchy.

    Locked or unsettable channels are skipped silently — attempting to key
    them raises and would abort the paste loop mid-way.
    """
    for attr in (
        "translateX", "translateY", "translateZ",
        "rotateX",    "rotateY",    "rotateZ",
        "scaleX",     "scaleY",     "scaleZ",
    ):
        full_attr = obj + "." + attr
        try:
            if cmds.getAttr(full_attr, lock=True):
                continue
            if not cmds.getAttr(full_attr, settable=True):
                continue
            cmds.setKeyframe(obj, at=attr, t=frame)
        except Exception:
            pass


def _store_single_frame(t, r, s):
    """Save single-frame xform, clear all range data."""
    _XFORM_STORE["translate"]  = t
    _XFORM_STORE["rotate"]     = r
    _XFORM_STORE["scale"]      = s
    _XFORM_STORE["frame_data"] = None
    _XFORM_STORE["multi_data"] = None


def _store_frame_data(frame_data):
    """Save single-object range data, clear all other stores."""
    _XFORM_STORE["translate"]  = None
    _XFORM_STORE["rotate"]     = None
    _XFORM_STORE["scale"]      = None
    _XFORM_STORE["frame_data"] = frame_data
    _XFORM_STORE["multi_data"] = None


def _store_multi_data(multi_data):
    """Save multi-object range data, clear all other stores."""
    _XFORM_STORE["translate"]  = None
    _XFORM_STORE["rotate"]     = None
    _XFORM_STORE["scale"]      = None
    _XFORM_STORE["frame_data"] = None
    _XFORM_STORE["multi_data"] = multi_data


# ---------------------------------------------------------------------------
# Status pill — module-level handle so core functions can refresh the UI
# ---------------------------------------------------------------------------

_status_label = None

_STATUS_STYLES = {
    "empty":  ("#404040", "#9a9a9a", "#4a4a4a"),
    "single": ("#1d6633", "#d5f5de", "#2a8a48"),
    "range":  ("#1f4878", "#d6e6fa", "#2e6da4"),
    "multi":  ("#4d2980", "#e8dcfa", "#6b3fae"),
}


def _status_state():
    """Return (state_key, label) describing what is currently stored."""
    if _XFORM_STORE["translate"] is not None:
        return "single", "●  Xform Stored"
    if _XFORM_STORE["frame_data"] is not None:
        n = len(_XFORM_STORE["frame_data"])
        return "range", "●  Range Stored  ({} frames)".format(n)
    if _XFORM_STORE["multi_data"] is not None:
        n_obj = len(_XFORM_STORE["multi_data"])
        n_frm = len(_XFORM_STORE["multi_data"][0]) if _XFORM_STORE["multi_data"] else 0
        return "multi", "●  Multi-Object Range  ({} objs, {} frames)".format(n_obj, n_frm)
    return "empty", "○  No Xform Stored"


def _update_status():
    """Refresh the status pill in the tool window (if open)."""
    global _status_label
    if _status_label is None:
        return
    state, label = _status_state()
    bg, fg, border = _STATUS_STYLES[state]
    try:
        _status_label.setText(label)
        _status_label.setStyleSheet(
            "QLabel {"
            "  background-color: %s;"
            "  color: %s;"
            "  border: 1px solid %s;"
            "  border-radius: 4px;"
            "  padding: 7px 10px;"
            "  font-size: 12px;"
            "  font-weight: bold;"
            "}" % (bg, fg, border)
        )
    except RuntimeError:
        # Underlying C++ widget was deleted (window closed)
        _status_label = None


def _run(func):
    """Execute a core function then refresh the status indicator."""
    try:
        func()
    finally:
        _update_status()


# ---------------------------------------------------------------------------
# Public API — core functions
# ---------------------------------------------------------------------------

def auto_xform_world_space():
    """
    Copy world-space xform from the FIRST selected object and paste it to
    all remaining selected objects at the current frame. Sets a keyframe on
    all settable transform channels for each target.

    Requires at least 2 objects selected.
    """
    sel = cmds.ls(sl=True, long=True)
    if len(sel) < 2:
        cmds.warning("xform_copy_paste: Select the source object first, then one or more target objects.")
        return

    source  = sel[0]
    targets = sel[1:]
    frame   = cmds.currentTime(q=True)

    cmds.undoInfo(openChunk=True, chunkName="auto_xform_world_space")
    try:
        t, r, s = _get_xform(source)
        _store_single_frame(t, r, s)
        for tgt in targets:
            _set_xform(tgt, t, r, s)
            _set_keyframe(tgt, frame)
    finally:
        cmds.undoInfo(closeChunk=True)

    print("xform_copy_paste: Auto xform applied to {} object(s) at frame {}.".format(
        len(targets), int(frame)))


def copy_xform_world_space():
    """
    Copy world-space xform from the first selected object at the current frame.
    Stores the result for use with any Paste operation.

    Requires at least 1 object selected.
    """
    sel = cmds.ls(sl=True, long=True)
    if not sel:
        cmds.warning("xform_copy_paste: Select the source object.")
        return

    source = sel[0]
    t, r, s = _get_xform(source)
    _store_single_frame(t, r, s)

    print("xform_copy_paste: Xform copied from '{}' at frame {}.".format(
        source, int(cmds.currentTime(q=True))))


def copy_xform_playback_range():
    """
    Copy world-space xform from the first selected object for every frame
    in the current playback range. Stored data is used by
    paste_xform_world_space_bake_frames().

    Requires at least 1 object selected.
    """
    sel = cmds.ls(sl=True, long=True)
    if not sel:
        cmds.warning("xform_copy_paste: Select the source object.")
        return

    source         = sel[0]
    min_f          = int(cmds.playbackOptions(q=True, min=True))
    max_f          = int(cmds.playbackOptions(q=True, max=True))
    original_frame = cmds.currentTime(q=True)

    frame_data = {}
    cmds.undoInfo(stateWithoutFlush=False)
    try:
        for f in range(min_f, max_f + 1):
            cmds.currentTime(f)
            t, r, s = _get_xform(source)
            frame_data[f] = {"translate": t, "rotate": r, "scale": s}
    finally:
        cmds.undoInfo(stateWithoutFlush=True)
        cmds.currentTime(original_frame)

    _store_frame_data(frame_data)
    print("xform_copy_paste: Copied xform for {} frames ({}–{}) from '{}'.".format(
        len(frame_data), min_f, max_f, source))


def paste_xform_world_space():
    """
    Paste the stored single-frame world-space xform to all selected objects
    at the current frame. Sets a keyframe on all settable transform channels.
    """
    if _XFORM_STORE["translate"] is None:
        cmds.warning("xform_copy_paste: Nothing copied. Use Copy or Auto Xform first.")
        return

    sel = cmds.ls(sl=True, long=True)
    if not sel:
        cmds.warning("xform_copy_paste: Select one or more target objects.")
        return

    frame = cmds.currentTime(q=True)
    t = _XFORM_STORE["translate"]
    r = _XFORM_STORE["rotate"]
    s = _XFORM_STORE["scale"]

    cmds.undoInfo(openChunk=True, chunkName="paste_xform_world_space")
    try:
        for obj in sel:
            _set_xform(obj, t, r, s)
            _set_keyframe(obj, frame)
    finally:
        cmds.undoInfo(closeChunk=True)

    print("xform_copy_paste: Xform pasted to {} object(s) at frame {}.".format(
        len(sel), int(frame)))


def paste_xform_world_space_all_keys():
    """
    Paste the stored single-frame world-space xform to all selected objects
    at every frame that already has a keyframe on the target.

    Skips objects that have no keyframes.
    """
    if _XFORM_STORE["translate"] is None:
        cmds.warning("xform_copy_paste: Nothing copied. Use Copy or Auto Xform first.")
        return

    sel = cmds.ls(sl=True, long=True)
    if not sel:
        cmds.warning("xform_copy_paste: Select one or more target objects.")
        return

    t = _XFORM_STORE["translate"]
    r = _XFORM_STORE["rotate"]
    s = _XFORM_STORE["scale"]
    original_frame = cmds.currentTime(q=True)

    cmds.undoInfo(openChunk=True, chunkName="paste_xform_world_space_all_keys")
    try:
        for obj in sel:
            key_times = cmds.keyframe(obj, q=True, tc=True) or []
            if not key_times:
                cmds.warning("xform_copy_paste: '{}' has no keyframes — skipping.".format(obj))
                continue
            key_times = sorted(set(key_times))
            for kf in key_times:
                cmds.currentTime(kf)
                _set_xform(obj, t, r, s)
                _set_keyframe(obj, kf)
    finally:
        cmds.currentTime(original_frame)
        cmds.undoInfo(closeChunk=True)

    print("xform_copy_paste: Xform pasted to all keyframe times on {} object(s).".format(len(sel)))


def paste_xform_world_space_bake_frames():
    """
    Bake the stored range xform data to all selected objects across the
    current playback range. Requires copy_xform_playback_range() first.

    Sets a keyframe on every frame for all settable transform channels.
    """
    if _XFORM_STORE["frame_data"] is None:
        cmds.warning("xform_copy_paste: No range data. Use 'Copy Xform WS Playback Range' first.")
        return

    sel = cmds.ls(sl=True, long=True)
    if not sel:
        cmds.warning("xform_copy_paste: Select one or more target objects.")
        return

    min_f          = int(cmds.playbackOptions(q=True, min=True))
    max_f          = int(cmds.playbackOptions(q=True, max=True))
    frame_data     = _XFORM_STORE["frame_data"]
    original_frame = cmds.currentTime(q=True)
    baked          = 0
    skipped        = 0

    cmds.undoInfo(openChunk=True, chunkName="paste_xform_world_space_bake_frames")
    try:
        for f in range(min_f, max_f + 1):
            if f not in frame_data:
                cmds.warning("xform_copy_paste: Frame {} not in copied range — skipping.".format(f))
                skipped += 1
                continue
            entry = frame_data[f]
            cmds.currentTime(f)
            for obj in sel:
                _set_xform(obj, entry["translate"], entry["rotate"], entry["scale"])
                _set_keyframe(obj, f)
            baked += 1
    finally:
        cmds.currentTime(original_frame)
        cmds.undoInfo(closeChunk=True)

    print("xform_copy_paste: Baked {} frame(s) to {} object(s){}.".format(
        baked, len(sel),
        " ({} frame(s) skipped — not in copied range)".format(skipped) if skipped else ""))


def paste_xform_world_space_next_frame():
    """
    Paste the stored single-frame world-space xform to all selected objects
    at the current frame, then advance the timeline by 1 frame.
    """
    if _XFORM_STORE["translate"] is None:
        cmds.warning("xform_copy_paste: Nothing copied. Use Copy or Auto Xform first.")
        return

    sel = cmds.ls(sl=True, long=True)
    if not sel:
        cmds.warning("xform_copy_paste: Select one or more target objects.")
        return

    frame = cmds.currentTime(q=True)
    t = _XFORM_STORE["translate"]
    r = _XFORM_STORE["rotate"]
    s = _XFORM_STORE["scale"]

    cmds.undoInfo(openChunk=True, chunkName="paste_xform_world_space_next_frame")
    try:
        for obj in sel:
            _set_xform(obj, t, r, s)
            _set_keyframe(obj, frame)
        cmds.currentTime(frame + 1)
    finally:
        cmds.undoInfo(closeChunk=True)

    print("xform_copy_paste: Xform pasted at frame {}, advanced to frame {}.".format(
        int(frame), int(frame + 1)))


def copy_xform_world_space_multi_range():
    """
    Copy world-space xform from EVERY selected object for every frame in the
    playback range. Each object's data is stored by selection index so it can
    be matched back to a corresponding target during paste.

    Workflow:
      1. Select all source controllers → Copy Xform WS Multi Objects Range
      2. Select corresponding target controllers (same order / count)
         → Paste Xform WS Keys Playback Range

    Requires at least 1 object selected.
    """
    sel = cmds.ls(sl=True, long=True)
    if not sel:
        cmds.warning("xform_copy_paste: Select one or more source objects.")
        return

    min_f          = int(cmds.playbackOptions(q=True, min=True))
    max_f          = int(cmds.playbackOptions(q=True, max=True))
    original_frame = cmds.currentTime(q=True)

    # One dict per selected object:  {frame: {translate, rotate, scale}}
    multi_data = [{} for _ in sel]

    cmds.undoInfo(stateWithoutFlush=False)
    try:
        for f in range(min_f, max_f + 1):
            cmds.currentTime(f)
            for i, obj in enumerate(sel):
                t, r, s = _get_xform(obj)
                multi_data[i][f] = {"translate": t, "rotate": r, "scale": s}
    finally:
        cmds.undoInfo(stateWithoutFlush=True)
        cmds.currentTime(original_frame)

    _store_multi_data(multi_data)
    print("xform_copy_paste: Copied {} object(s) across {} frames ({}–{}).".format(
        len(sel), max_f - min_f + 1, min_f, max_f))


def paste_xform_world_space_keys_range():
    """
    Paste the stored multi-object world-space xform onto each selected object,
    but ONLY at frames that already have keyframes on that object within the
    current playback range.  No new frames are created — only existing keys
    are overwritten with the world-space position from the copied data.

    Targets are matched to copied sources by selection order (1st target gets
    1st copied object's data, 2nd target gets 2nd, etc.).

    Requires a previous Copy Xform WS Multi Objects Range.
    """
    if _XFORM_STORE["multi_data"] is None:
        cmds.warning(
            "xform_copy_paste: No multi-object range data. "
            "Use 'Copy Xform WS Multi Objects Range' first."
        )
        return

    sel = cmds.ls(sl=True, long=True)
    if not sel:
        cmds.warning("xform_copy_paste: Select one or more target objects.")
        return

    multi_data     = _XFORM_STORE["multi_data"]
    min_f          = int(cmds.playbackOptions(q=True, min=True))
    max_f          = int(cmds.playbackOptions(q=True, max=True))
    original_frame = cmds.currentTime(q=True)
    total_keys     = 0
    pasted_objs    = 0

    cmds.undoInfo(openChunk=True, chunkName="paste_xform_ws_keys_range")
    try:
        for i, obj in enumerate(sel):
            if i >= len(multi_data):
                cmds.warning(
                    "xform_copy_paste: No stored data for target {} ('{}') — skipping.".format(
                        i + 1, obj)
                )
                continue

            src = multi_data[i]

            # Find this object's existing keyframe times within the playback range
            all_keys = cmds.keyframe(obj, q=True, tc=True) or []
            key_times = sorted(set(
                k for k in all_keys if min_f <= k <= max_f
            ))

            if not key_times:
                cmds.warning(
                    "xform_copy_paste: '{}' has no keyframes in range {}–{} — skipping.".format(
                        obj, min_f, max_f)
                )
                continue

            pasted_objs += 1
            for kf in key_times:
                # Snap to nearest integer frame in the stored data
                nearest = int(round(kf))
                if nearest not in src:
                    continue
                entry = src[nearest]
                cmds.currentTime(kf)
                _set_xform(obj, entry["translate"], entry["rotate"], entry["scale"])
                _set_keyframe(obj, kf)
                total_keys += 1
    finally:
        cmds.currentTime(original_frame)
        cmds.undoInfo(closeChunk=True)

    print("xform_copy_paste: Pasted at {} keyframe(s) across {} object(s).".format(
        total_keys, pasted_objs))


def run_action(action_key):
    """Run a core function by hotkey action id and refresh the status pill.

    Used by the runtime commands registered for Maya hotkeys so the window
    (if open) always reflects the latest copy state.
    """
    func = _ACTION_FUNCS.get(action_key)
    if func is None:
        cmds.warning("xform_copy_paste: Unknown action '{}'.".format(action_key))
        return
    _run(func)


# ---------------------------------------------------------------------------
# Stylesheet — matches the ATK toolbar / Reset Tool design language
# ---------------------------------------------------------------------------

_STYLESHEET = """
QDialog {
    background-color: #3c3c3c;
    color: #cccccc;
}
QScrollArea {
    background: transparent;
    border: none;
}
QScrollArea > QWidget > QWidget {
    background: transparent;
}
QScrollBar:vertical {
    background: #333333;
    width: 10px;
    margin: 0;
    border-radius: 5px;
}
QScrollBar::handle:vertical {
    background: #5a5a5a;
    min-height: 24px;
    border-radius: 5px;
}
QScrollBar::handle:vertical:hover {
    background: #6d6d6d;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: none;
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
QPushButton#btn_auto {
    background-color: #8a5416;
    color: #ffffff;
    border: 1px solid #a86c24;
    font-weight: bold;
}
QPushButton#btn_auto:hover {
    background-color: #a2661f;
    border-color: #c08236;
}
QPushButton#btn_auto:pressed {
    background-color: #6e430f;
    border-color: #8a5416;
}
QPushButton[atkRole="copy"] {
    background-color: #1c5c66;
    color: #ffffff;
    border: 1px solid #2a7a86;
}
QPushButton[atkRole="copy"]:hover {
    background-color: #24707c;
    border-color: #3a94a2;
}
QPushButton[atkRole="copy"]:pressed {
    background-color: #154850;
    border-color: #1c5c66;
}
QPushButton[atkRole="paste"] {
    background-color: #2e6da4;
    color: #ffffff;
    border: 1px solid #4088c0;
}
QPushButton[atkRole="paste"]:hover {
    background-color: #3a7ec0;
    border-color: #5599d4;
}
QPushButton[atkRole="paste"]:pressed {
    background-color: #205080;
    border-color: #2e6da4;
}
QPushButton[atkRole="multi"] {
    background-color: #5b3591;
    color: #ffffff;
    border: 1px solid #7449b3;
}
QPushButton[atkRole="multi"]:hover {
    background-color: #6c40aa;
    border-color: #8a5fd0;
}
QPushButton[atkRole="multi"]:pressed {
    background-color: #482a73;
    border-color: #5b3591;
}
"""


# ---------------------------------------------------------------------------
# UI — Help and About dialogs
# ---------------------------------------------------------------------------

_HELP_TEXT = """\
COPY XFORM WORLD SPACE — HELP
==============================

INSTALLATION
------------
Drag install_xform_copy_paste.mel onto the Maya viewport.
The script copies xform_copy_paste.py to your scripts directory and
adds a single "XformCP" shelf button to the active shelf.

Place xform_copy_paste.png in the same folder as the .mel file to
install the custom shelf icon automatically.

OVERVIEW
--------
This tool copies and pastes world-space transforms (translate, rotate,
scale) between objects or across the timeline.  It is also known as the
"Sticky Tool" or "Animation Recorder".

All paste operations call cmds.xform(..., ws=True) to position the target
in world space, then key the resulting local channel values.  This means
the tool works correctly for objects inside a parent hierarchy (rig
controllers, COG, IK handles, etc.).  Locked or connected channels are
skipped automatically instead of aborting the paste.

-------------------------------------------------------------------------

COPY FUNCTIONS
--------------

Auto Xform World Space
  Copies the world-space transform from the FIRST selected object and
  immediately pastes it to every other selected object at the current
  frame.  Sets a keyframe on all settable transform channels for each
  target.  Requires at least 2 objects selected.

Copy Xform World Space
  Captures the world-space transform of the first selected object at the
  current frame and stores it in memory.  Use any Paste function to apply
  the stored values.  Requires at least 1 object selected.

Copy Xform World Space Playback Range
  Samples the first selected object's world-space transform on every
  frame of the current playback range and stores the result as a
  frame-keyed dictionary.  Used with Paste Xform WS Bake Frames.
  Requires at least 1 object selected.

Copy Xform WS Multi Objects Playback Range
  Samples ALL selected objects across the entire playback range and
  stores per-object, per-frame world-space data.  Selection order is
  preserved so each source maps to the corresponding target during paste.
  Used with Paste Xform WS Keys Playback Range.
  Requires at least 1 object selected.

-------------------------------------------------------------------------

PASTE FUNCTIONS
---------------

Paste Xform World Space
  Pastes the stored single-frame world-space transform to all selected
  objects at the current frame.  Sets a keyframe on all settable
  transform channels.
  Requires a prior Copy Xform World Space (or Auto Xform).

Paste Xform World Space All Keys
  Pastes the stored single-frame xform to all selected objects at EVERY
  frame that already has a keyframe on the target.  Does not create new
  keyframe times — only overwrites existing ones.
  Requires a prior Copy Xform World Space.

Paste Xform World Space Bake Frames
  Bakes the stored playback-range data onto all selected objects, setting
  a keyframe on every frame of the range.  Targets that are missing
  frames from the stored range receive a warning and those frames are
  skipped.
  Requires a prior Copy Xform WS Playback Range.

Paste Xform World Space Next Frame
  Pastes the stored single-frame xform at the current frame then advances
  the timeline by 1.  Useful for step-by-step pose-to-pose work.
  Requires a prior Copy Xform World Space.

Paste Xform WS Keys Playback Range
  Pairs with Copy Xform WS Multi Objects Playback Range.
  For each selected target, looks up the corresponding stored source data
  (matched by selection index) and overwrites keyframe values only at
  frames that already have keyframes on the target within the playback
  range.  No new keyframe times are created — existing animation curves
  are retimed to the captured world position.
  Requires a prior Copy Xform WS Multi Objects Playback Range.

-------------------------------------------------------------------------

KEYBOARD SHORTCUTS
------------------
Every copy and paste function can be bound to a Maya hotkey.

Click "Setup / Edit Hotkeys..." in the tool window, click the field next
to a function and press the desired key combination, then Apply.  The
bindings are written to your active Maya hotkey set and saved with your
preferences, so they persist between sessions.

Maya's default hotkey set (Maya_Default) is locked — if it is active you
will be prompted to choose or create a custom hotkey set first.  The
commands also appear in Maya's Hotkey Editor under
Custom Scripts > Xform Copy Paste.

-------------------------------------------------------------------------

STATUS INDICATOR
----------------
The coloured pill at the top of the window shows what is stored:

  Grey   — nothing stored
  Green  — single-frame xform stored
  Blue   — single-object playback-range data stored
  Purple — multi-object playback-range data stored
"""

_ABOUT_TEXT = """\
Copy Xform World Space
Version 2.0
-------------------------------------------------------------------------

Also known as: Sticky Tool, Animation Recorder

A Maya Python animation utility that copies and pastes world-space
transforms between objects and across the timeline.  Keyframe values are
always written as local channel values so the tool works correctly with
rigged characters and parented controllers.

REQUIREMENTS
  Maya 2022 or later (PySide6 or PySide2)

INSTALLATION
  Drag install_xform_copy_paste.mel onto the Maya viewport.
  The installer copies xform_copy_paste.py to your Maya scripts
  directory and adds a single "XformCP" shelf button.

FILES
  xform_copy_paste.py           — main script (copy to scripts dir)
  install_xform_copy_paste.mel  — drag-and-drop installer
  xform_copy_paste.png          — shelf icon (place beside .mel)

SOURCE
  github.com/dshepstone/xform_copy_paste
-------------------------------------------------------------------------
"""


class _TextDialog(QtWidgets.QDialog):
    """Scrollable monospace text dialog used for Help and About."""

    def __init__(self, title, text, size, parent=None):
        super(_TextDialog, self).__init__(parent)
        self.setWindowTitle(title)
        self.setWindowFlags(
            QtCore.Qt.Window
            | QtCore.Qt.WindowTitleHint
            | QtCore.Qt.WindowCloseButtonHint
        )
        self.resize(*size)
        self.setStyleSheet(_STYLESHEET + """
            QPlainTextEdit {
                background-color: #333333;
                color: #cccccc;
                border: 1px solid #555555;
                border-radius: 4px;
                font-family: Consolas, Monaco, monospace;
                font-size: 11px;
            }
        """)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        viewer = QtWidgets.QPlainTextEdit()
        viewer.setPlainText(text)
        viewer.setReadOnly(True)
        layout.addWidget(viewer)

        btn_close = QtWidgets.QPushButton("Close")
        btn_close.clicked.connect(self.close)
        row = QtWidgets.QHBoxLayout()
        row.addStretch()
        row.addWidget(btn_close)
        layout.addLayout(row)


def show_help():
    """Open the Help reference window."""
    dlg = _TextDialog(
        "Copy Xform World Space — Help", _HELP_TEXT, (560, 680),
        parent=_get_maya_main_window(),
    )
    dlg.show()
    return dlg


def show_about():
    """Open the About window."""
    dlg = _TextDialog(
        "About — Copy Xform World Space", _ABOUT_TEXT, (480, 420),
        parent=_get_maya_main_window(),
    )
    dlg.show()
    return dlg


# ---------------------------------------------------------------------------
# UI — main window
# ---------------------------------------------------------------------------

def _get_maya_main_window():
    """Return Maya's main window as a QtWidgets.QWidget."""
    ptr = omui.MQtUtil.mainWindow()
    if ptr is None:
        return None
    return wrapInstance(int(ptr), QtWidgets.QWidget)


class XformCopyPasteDialog(QtWidgets.QDialog):
    """Modern Copy Xform World Space dialog for Maya."""

    def __init__(self, parent=None):
        super(XformCopyPasteDialog, self).__init__(parent)
        self.setObjectName(WINDOW_OBJECT_NAME)
        self.setWindowTitle("Xform Copy Paste")
        self.setWindowFlags(
            QtCore.Qt.Window
            | QtCore.Qt.WindowTitleHint
            | QtCore.Qt.WindowCloseButtonHint
        )
        self.setMinimumWidth(380)
        self.resize(400, 640)
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

    def _action_button(self, text, tooltip, func, role=None, object_name=None):
        btn = QtWidgets.QPushButton(text)
        btn.setToolTip(tooltip)
        if object_name:
            btn.setObjectName(object_name)
        if role:
            btn.setProperty("atkRole", role)
        btn.clicked.connect(lambda *_: _run(func))
        return btn

    # ── Layout ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        global _status_label

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Everything lives inside a vertical scroll area so the whole window
        # stays usable at small heights.
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        outer.addWidget(scroll)

        content = QtWidgets.QWidget()
        scroll.setWidget(content)

        layout = QtWidgets.QVBoxLayout(content)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(0)

        # Header
        title = QtWidgets.QLabel("Xform Copy Paste")
        title.setObjectName("lbl_title")
        subtitle = QtWidgets.QLabel(
            "Copies and pastes world-space transforms between objects. "
            'Also known as "Sticky Tool" or "Animation Recorder".'
        )
        subtitle.setObjectName("lbl_subtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(title)
        layout.addSpacing(4)
        layout.addWidget(subtitle)
        layout.addSpacing(12)

        # Status pill
        _status_label = QtWidgets.QLabel()
        _status_label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(_status_label)
        layout.addSpacing(12)
        layout.addWidget(self._separator())
        layout.addSpacing(12)

        # ── COPY section ────────────────────────────────────────────────────
        layout.addWidget(self._section_label("Copy"))
        layout.addSpacing(8)

        copy_buttons = [
            (
                "Auto Xform World Space",
                "Copies the world-space transform from the first selected object\n"
                "and pastes it to every other selected object at the current frame.",
                "Copy from first selected, paste to all remaining in one step.",
                auto_xform_world_space, None, "btn_auto",
            ),
            (
                "Copy Xform World Space",
                "Captures the world-space transform of the first selected object\n"
                "at the current frame and stores it for any Paste function.",
                "Store the first selected object's xform at the current frame.",
                copy_xform_world_space, "copy", None,
            ),
            (
                "Copy Xform WS Playback Range",
                "Samples the first selected object's world-space transform on\n"
                "every frame of the playback range.  Use with Bake Frames.",
                "Store every frame of the playback range from one object.",
                copy_xform_playback_range, "copy", None,
            ),
            (
                "Copy Xform WS Multi Objects Range",
                "Samples ALL selected objects across the playback range.\n"
                "Selection order is preserved for matching during paste.\n"
                "Use with Paste Xform WS Keys Playback Range.",
                "Store all selected objects across the playback range.",
                copy_xform_world_space_multi_range, "multi", None,
            ),
        ]
        for i, (label, tooltip, desc, fn, role, obj_name) in enumerate(copy_buttons):
            layout.addWidget(self._action_button(label, tooltip, fn, role, obj_name))
            layout.addSpacing(3)
            layout.addWidget(self._desc_label(desc))
            if i < len(copy_buttons) - 1:
                layout.addSpacing(10)

        layout.addSpacing(14)
        layout.addWidget(self._separator())
        layout.addSpacing(12)

        # ── PASTE section ───────────────────────────────────────────────────
        layout.addWidget(self._section_label("Paste"))
        layout.addSpacing(8)

        paste_buttons = [
            (
                "Paste Xform World Space",
                "Pastes the stored single-frame xform to all selected objects\n"
                "at the current frame and keys all settable channels.",
                "Paste the stored xform at the current frame.",
                paste_xform_world_space, "paste", None,
            ),
            (
                "Paste Xform WS All Keys",
                "Pastes the stored single-frame xform at every frame that\n"
                "already has a keyframe on each target.  No new keys created.",
                "Paste at every existing keyframe time on the targets.",
                paste_xform_world_space_all_keys, "paste", None,
            ),
            (
                "Paste Xform WS Bake Frames",
                "Bakes the stored playback-range data onto all selected objects,\n"
                "keying every frame of the range.  Needs Copy WS Playback Range.",
                "Bake the stored range to every frame on the targets.",
                paste_xform_world_space_bake_frames, "paste", None,
            ),
            (
                "Paste Xform WS Next Frame",
                "Pastes the stored xform at the current frame, then advances\n"
                "the timeline by one frame.  Handy for pose-to-pose stepping.",
                "Paste at the current frame, then step forward one frame.",
                paste_xform_world_space_next_frame, "paste", None,
            ),
            (
                "Paste Xform WS Keys Playback Range",
                "Pairs with Copy Xform WS Multi Objects Range.  Overwrites each\n"
                "target's existing keys (within the playback range) with the\n"
                "stored world-space data, matched by selection order.",
                "Paste multi-object data onto existing keys only.",
                paste_xform_world_space_keys_range, "multi", None,
            ),
        ]
        for i, (label, tooltip, desc, fn, role, obj_name) in enumerate(paste_buttons):
            layout.addWidget(self._action_button(label, tooltip, fn, role, obj_name))
            layout.addSpacing(3)
            layout.addWidget(self._desc_label(desc))
            if i < len(paste_buttons) - 1:
                layout.addSpacing(10)

        layout.addSpacing(14)
        layout.addWidget(self._separator())
        layout.addSpacing(12)

        # ── SHORTCUTS section ───────────────────────────────────────────────
        layout.addWidget(self._section_label("Shortcuts"))
        layout.addSpacing(8)

        btn_hotkeys = QtWidgets.QPushButton("Setup / Edit Hotkeys...")
        btn_hotkeys.setToolTip(
            "Assign or change keyboard shortcuts for each copy / paste function.\n"
            "Bindings are saved to your Maya hotkey set and persist between sessions."
        )
        btn_hotkeys.clicked.connect(lambda *_: show_hotkey_setup())
        layout.addWidget(btn_hotkeys)
        layout.addSpacing(3)
        layout.addWidget(
            self._desc_label(
                "Assign Maya keyboard shortcuts to trigger copy and paste "
                "functions directly — no window needed."
            )
        )

        layout.addSpacing(14)
        layout.addWidget(self._separator())
        layout.addSpacing(10)

        # ── Footer: Help / About ────────────────────────────────────────────
        footer = QtWidgets.QHBoxLayout()
        btn_help = QtWidgets.QPushButton("Help")
        btn_help.setToolTip("Open the full help reference.")
        btn_help.clicked.connect(lambda *_: show_help())
        btn_about = QtWidgets.QPushButton("About")
        btn_about.setToolTip("Version and installation information.")
        btn_about.clicked.connect(lambda *_: show_about())
        footer.addWidget(btn_help)
        footer.addWidget(btn_about)
        footer.addStretch()
        layout.addLayout(footer)

        layout.addStretch()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

_dialog = None  # keeps the window alive when launched without a Maya parent


def show():
    """Show the Xform Copy Paste dialog, closing any existing instance first."""
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

    _dialog = XformCopyPasteDialog(parent=_get_maya_main_window())
    _dialog.show()
    _dialog.raise_()
    _dialog.activateWindow()
    _update_status()
    return _dialog


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
            "The default ‘Maya_Default’ hotkey set is locked.\n"
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
        btn_ok.setProperty("atkRole", "paste")
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
        print("xform_copy_paste: switched to hotkey set '{}'".format(choice))
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
        cmds.warning("xform_copy_paste: hotkey set name cannot be empty.")
        return None
    # Create from the current default so existing hotkeys carry over
    if cmds.hotkeySet(name, exists=True):
        cmds.hotkeySet(name, edit=True, current=True)
    else:
        cmds.hotkeySet(name, source=_LOCKED_HOTKEY_SET)
        cmds.hotkeySet(name, edit=True, current=True)
    print("xform_copy_paste: created and activated hotkey set '{}'".format(name))
    return name


# ---------------------------------------------------------------------------
# Runtime Commands — appear in Maya's Hotkey Editor under 'Custom Scripts'
# ---------------------------------------------------------------------------

_RUNTIME_CMD_PREFIX = "xformCP_"

# action id -> (function, label shown in the hotkey dialog / hotkey editor)
_XFORM_ACTIONS = {
    "autoXform":       ("auto_xform_world_space",              "Auto Xform World Space"),
    "copyXform":       ("copy_xform_world_space",              "Copy Xform World Space"),
    "copyRange":       ("copy_xform_playback_range",           "Copy Xform WS Playback Range"),
    "copyMultiRange":  ("copy_xform_world_space_multi_range",  "Copy Xform WS Multi Objects Range"),
    "pasteXform":      ("paste_xform_world_space",             "Paste Xform World Space"),
    "pasteAllKeys":    ("paste_xform_world_space_all_keys",    "Paste Xform WS All Keys"),
    "pasteBakeFrames": ("paste_xform_world_space_bake_frames", "Paste Xform WS Bake Frames"),
    "pasteNextFrame":  ("paste_xform_world_space_next_frame",  "Paste Xform WS Next Frame"),
    "pasteKeysRange":  ("paste_xform_world_space_keys_range",  "Paste Xform WS Keys Playback Range"),
}

_ACTION_ORDER = [
    "autoXform",
    "copyXform",
    "copyRange",
    "copyMultiRange",
    "pasteXform",
    "pasteAllKeys",
    "pasteBakeFrames",
    "pasteNextFrame",
    "pasteKeysRange",
]


def _action_funcs():
    return {key: globals()[fn_name] for key, (fn_name, _) in _XFORM_ACTIONS.items()}


_ACTION_FUNCS = None  # populated lazily below (after functions are defined)


def _ensure_runtime_commands():
    """Register (or update) runtime commands for each copy/paste function.

    Commands appear in Maya's Hotkey Editor under
    'Custom Scripts.Xform Copy Paste'.
    """
    for action_key, (_, annotation) in _XFORM_ACTIONS.items():
        rt_name = _RUNTIME_CMD_PREFIX + action_key
        py_code = (
            "import xform_copy_paste; "
            "xform_copy_paste.run_action('{}')".format(action_key)
        )
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
                category="Custom Scripts.Xform Copy Paste",
                commandLanguage="python",
                command=py_code,
            )
        print("xform_copy_paste: runtime command '{}' ready".format(rt_name))


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
    """Assign a keyboard shortcut to a copy/paste action.

    Caller must ensure a writable hotkey set is active and runtime
    commands are registered before calling this function.

    Returns True if assigned, False if the user cancelled (conflict).
    """
    display = _display_string(key, ctrl, alt, shift)
    nc_name = _RUNTIME_CMD_PREFIX + action_key + "NameCommand"
    rt_name = _RUNTIME_CMD_PREFIX + action_key
    annotation = _XFORM_ACTIONS[action_key][1]

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
    cmds.optionVar(sv=("xformCP_hotkey_" + action_key, display))

    print("xform_copy_paste: hotkey '{}' -> {}".format(display, rt_name))
    return True


def _get_current_hotkey(action_key):
    """Return a human-readable string of the current hotkey, or empty string."""
    var_name = "xformCP_hotkey_" + action_key
    if cmds.optionVar(exists=var_name):
        return cmds.optionVar(q=var_name)
    return ""


def _clear_hotkey(action_key):
    """Remove the hotkey binding for the given action."""
    var_name = "xformCP_hotkey_" + action_key
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
    """Dialog for assigning keyboard shortcuts to copy/paste functions."""

    def __init__(self, parent=None):
        super(HotkeySetupDialog, self).__init__(parent)
        self.setObjectName(HOTKEY_WINDOW_OBJECT_NAME)
        self.setWindowTitle("Xform Copy Paste — Setup Hotkeys")
        self.setWindowFlags(
            QtCore.Qt.Window
            | QtCore.Qt.WindowTitleHint
            | QtCore.Qt.WindowCloseButtonHint
        )
        self.setMinimumWidth(420)
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
            "Assign keyboard shortcuts to each copy / paste function. "
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

        # Scrollable grid of actions (9 rows)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        grid_host = QtWidgets.QWidget()
        scroll.setWidget(grid_host)

        grid = QtWidgets.QGridLayout(grid_host)
        grid.setContentsMargins(0, 0, 6, 0)
        grid.setColumnStretch(1, 1)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)

        for row, action_key in enumerate(_ACTION_ORDER):
            label_text = _XFORM_ACTIONS[action_key][1]
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

        grid_host.adjustSize()
        scroll.setMinimumHeight(min(grid_host.sizeHint().height() + 4, 420))
        layout.addWidget(scroll)
        layout.addSpacing(16)

        line2 = QtWidgets.QFrame()
        line2.setObjectName("separator")
        line2.setFrameShape(QtWidgets.QFrame.HLine)
        layout.addWidget(line2)
        layout.addSpacing(12)

        # Buttons
        btn_row = QtWidgets.QHBoxLayout()

        btn_clear = QtWidgets.QPushButton("Clear All")
        btn_clear.setToolTip("Remove all hotkey assignments for copy/paste functions")
        btn_clear.clicked.connect(self._on_clear)
        btn_row.addWidget(btn_clear)

        btn_row.addStretch()

        btn_apply = QtWidgets.QPushButton("Apply")
        btn_apply.setProperty("atkRole", "paste")
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
            print("xform_copy_paste: switched to hotkey set '{}'".format(choice))
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
                        "xform_copy_paste: could not map key '{}' for {} — unsupported key.".format(
                            seq.toString(), _XFORM_ACTIONS[action_key][1])
                    )
                continue
            maya_key, ctrl, alt, shift = parsed
            try:
                if assign_hotkey(action_key, maya_key, ctrl=ctrl, alt=alt, shift=shift):
                    applied += 1
                else:
                    skipped += 1
            except Exception as exc:
                cmds.warning("xform_copy_paste: failed to assign hotkey — {}".format(exc))

        if applied:
            # Save hotkeys so they persist between sessions
            cmds.savePrefs(hotkeys=True)
            msg = "<hl>Xform Copy Paste</hl>  {} hotkey(s) assigned and saved.".format(applied)
            if skipped:
                msg += "  {} skipped.".format(skipped)
            cmds.inViewMessage(amg=msg, pos="midCenter", fade=True)
        elif skipped:
            cmds.inViewMessage(
                amg="<hl>Xform Copy Paste</hl>  {} hotkey(s) skipped (conflicts).".format(skipped),
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
            amg="<hl>Xform Copy Paste</hl>  All hotkeys cleared.",
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


# Resolve action ids to functions now that everything is defined
_ACTION_FUNCS = _action_funcs()
