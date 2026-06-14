# =============================================================================
# xform_copy_paste.py
#
# Copy Xform World Space - Maya Animation Utility
#
# Copies and pastes world-space transforms (translate, rotate, scale) between
# objects. Also known as "Sticky Tool" or "Animation Recorder".
#
# Usage: install via install_xform_copy_paste.mel, then click the shelf button.
#
# Public API (unchanged across the 2.0 UI rebuild):
#   show()                                - Open the tool window
#   launch()                              - Alias for show()
#   dispatch()                            - Shelf entry point with modifier routing
#   auto_xform_world_space()              - Copy first selected, paste to rest
#   copy_xform_world_space()              - Copy xform from first selected (single frame)
#   copy_xform_playback_range()           - Copy all frames in playback range
#   copy_xform_world_space_multi_range()  - Copy all selected across playback range
#   paste_xform_world_space()             - Paste stored xform at current frame
#   paste_xform_world_space_all_keys()    - Paste at all existing keyframe times
#   paste_xform_world_space_bake_frames() - Bake stored range xform to targets
#   paste_xform_world_space_next_frame()  - Paste then advance timeline by 1
#   paste_xform_world_space_keys_range()  - Paste multi-object range at existing keys
#
# Requirements: Maya 2020+ (PySide2 or PySide6).  Core transform functions work
#               under Maya 2017+ / Python 2.7 as well; only the Qt window needs
#               a modern Maya.
#
# Version: 2.0.0
# =============================================================================

from __future__ import division, print_function

import os
import shutil

import maya.cmds as cmds

VERSION = "2.0.0"
TITLE   = "Copy Xform World Space"

# ---------------------------------------------------------------------------
# UI ids.  The legacy maya.cmds window ids are kept so a 1.x window left open
# from a previous version is cleaned up automatically on launch.
# ---------------------------------------------------------------------------
_WIN_ID        = "xform_copy_paste_win"          # legacy cmds window
_STATUS_ID     = "xform_copy_paste_status"       # legacy cmds status control
_HELP_WIN_ID   = "xform_copy_paste_help_win"     # legacy cmds help window
_ABOUT_WIN_ID  = "xform_copy_paste_about_win"    # legacy cmds about window


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

    # Copy icon to Maya icons directory (optional - falls back to default icon)
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
                cmds.warning("xform_copy_paste: Could not copy icon - " + str(e))

    # Shelf button Python command - routes through dispatch() so modifier
    # clicks (Alt/Ctrl/Shift...) fire the matching action; a plain click
    # opens the window.
    py_cmd = (
        "import sys, importlib\n"
        "import maya.cmds as cmds\n"
        "scripts_dir = cmds.internalVar(userScriptDir=True)\n"
        "if scripts_dir not in sys.path:\n"
        "    sys.path.insert(0, scripts_dir)\n"
        "import xform_copy_paste\n"
        "importlib.reload(xform_copy_paste)\n"
        "xform_copy_paste.dispatch()\n"
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
        annotation="Copy Xform World Space - click to open. "
                   "Alt=Auto  Ctrl=Paste  Shift=Paste+Next  "
                   "Ctrl+Shift=Copy Range  Ctrl+Alt=Bake  Ctrl+Alt+Shift=Paste All Keys",
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
    "translate":  None,   # list[float, float, float] - single-frame copy
    "rotate":     None,   # list[float, float, float]
    "scale":      None,   # list[float, float, float]
    "frame_data": None,   # dict[int, {t,r,s}] - single-object range copy
    "multi_data": None,   # list[dict[int, {t,r,s}]] - multi-object range copy
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


def _set_xform(obj, t, r, s):
    """Apply world-space translate, rotate, scale to obj."""
    cmds.xform(obj, ws=True, t=t)
    cmds.xform(obj, ws=True, ro=r)
    cmds.xform(obj, ws=True, s=s)


def _set_keyframe(obj, frame):
    """Key all 9 transform channels on obj at the given frame.

    Intentionally does NOT pass explicit values - Maya keys whatever the
    attribute currently holds.  This is correct after a _set_xform() call
    because _set_xform places the object in world space, and Maya stores the
    resulting *local* channel values.  Passing world-space values directly
    as 'v=' would be wrong for any object inside a parent hierarchy.
    """
    for attr in (
        "translateX", "translateY", "translateZ",
        "rotateX",    "rotateY",    "rotateZ",
        "scaleX",     "scaleY",     "scaleZ",
    ):
        cmds.setKeyframe(obj, at=attr, t=frame)


def _store_single_frame(t, r, s):
    """Save single-frame xform, clear all range data."""
    _XFORM_STORE["translate"]  = t
    _XFORM_STORE["rotate"]     = r
    _XFORM_STORE["scale"]      = s
    _XFORM_STORE["frame_data"] = None
    _XFORM_STORE["multi_data"] = None
    _notify_status()


def _store_frame_data(frame_data):
    """Save single-object range data, clear all other stores."""
    _XFORM_STORE["translate"]  = None
    _XFORM_STORE["rotate"]     = None
    _XFORM_STORE["scale"]      = None
    _XFORM_STORE["frame_data"] = frame_data
    _XFORM_STORE["multi_data"] = None
    _notify_status()


def _store_multi_data(multi_data):
    """Save multi-object range data, clear all other stores."""
    _XFORM_STORE["translate"]  = None
    _XFORM_STORE["rotate"]     = None
    _XFORM_STORE["scale"]      = None
    _XFORM_STORE["frame_data"] = None
    _XFORM_STORE["multi_data"] = multi_data
    _notify_status()


def _status_info():
    """Return (state_key, headline, detail, accent_hex) for the current store.

    state_key is one of: 'none', 'single', 'range', 'multi'.  Used by the Qt
    status panel and by any external caller that wants to inspect what is held.
    """
    if _XFORM_STORE["translate"] is not None:
        return ("single",
                "Single Xform Stored",
                "Ready to paste at the current frame or existing keys.",
                "#3fae62")
    if _XFORM_STORE["frame_data"] is not None:
        n = len(_XFORM_STORE["frame_data"])
        return ("range",
                "Playback Range Stored",
                "{} frames captured - use Bake Frames to apply.".format(n),
                "#4f86d6")
    if _XFORM_STORE["multi_data"] is not None:
        n_obj = len(_XFORM_STORE["multi_data"])
        n_frm = len(_XFORM_STORE["multi_data"][0]) if _XFORM_STORE["multi_data"] else 0
        return ("multi",
                "Multi-Object Range Stored",
                "{} objects x {} frames - use Keys Playback Range to apply.".format(n_obj, n_frm),
                "#9a6bd8")
    return ("none",
            "No Xform Stored",
            "Store a transform to enable paste operations.",
            "#6f7177")


# Weak reference to the live Qt window so storage helpers can refresh the
# status panel without importing Qt at module scope.
_ACTIVE_WINDOW = None


def _notify_status():
    """Refresh the status panel on the live Qt window, if one is open."""
    win = _ACTIVE_WINDOW
    if win is None:
        return
    try:
        win.refresh_status()
    except Exception:
        # Window was destroyed out from under us - drop the reference.
        pass


# ---------------------------------------------------------------------------
# Help / About text (shared by the Qt dialogs)
# ---------------------------------------------------------------------------

_HELP_TEXT = """\
COPY XFORM WORLD SPACE - HELP
==============================

OVERVIEW
--------
This tool copies and pastes world-space transforms (translate, rotate,
scale) between objects or across the timeline.  It is also known as the
"Sticky Tool" or "Animation Recorder".

All paste operations call cmds.xform(..., ws=True) to position the target
in world space, then key the resulting local channel values.  This means
the tool works correctly for objects inside a parent hierarchy (rig
controllers, COG, IK handles, etc.).

COPY FUNCTIONS
--------------
Auto Xform World Space  [Alt+Click shelf button]
  Copies the world-space transform from the FIRST selected object and
  immediately pastes it to every other selected object at the current
  frame.  Keys all 9 channels for each target.  Needs 2+ objects.

Copy Xform World Space  [window button]
  Captures the world-space transform of the first selected object at the
  current frame and stores it.  Needs 1+ object.

Copy Xform World Space Playback Range  [Ctrl+Shift+Click shelf button]
  Samples the first selected object's world-space transform on every frame
  of the playback range.  Used with Paste Xform WS Bake Frames.

Copy Xform WS Multi Objects Playback Range  [window button]
  Samples ALL selected objects across the playback range, preserving
  selection order.  Used with Paste Xform WS Keys Playback Range.

PASTE FUNCTIONS
---------------
Paste Xform World Space  [Ctrl+Click shelf button]
  Pastes the stored single-frame xform to all selected objects at the
  current frame.

Paste Xform World Space All Keys  [Ctrl+Alt+Shift+Click shelf button]
  Pastes the stored single-frame xform at every existing keyframe time on
  each target.  Creates no new keys.

Paste Xform World Space Bake Frames  [Ctrl+Alt+Click shelf button]
  Bakes the stored playback-range data onto all selected objects, keying
  every frame of the range.

Paste Xform World Space Next Frame  [Shift+Click shelf button]
  Pastes the stored single-frame xform then advances the timeline by 1.

Paste Xform WS Keys Playback Range  [window button]
  Pairs with Copy Xform WS Multi Objects Playback Range.  For each target,
  overwrites only the keyframes it already has within the playback range,
  matched to its source by selection index.

STATUS PANEL
------------
The coloured status panel shows what is stored:
  Grey   - nothing stored
  Green  - single-frame xform
  Blue   - single-object playback-range data
  Purple - multi-object playback-range data

SHELF MODIFIER CLICKS
---------------------
  (no modifier)        Open this window
  Alt+Click            Auto Xform World Space
  Ctrl+Click           Paste Xform World Space
  Shift+Click          Paste Xform World Space Next Frame
  Ctrl+Shift+Click     Copy Xform World Space Playback Range
  Ctrl+Alt+Click       Paste Xform World Space Bake Frames
  Ctrl+Alt+Shift+Click Paste Xform World Space All Keys
"""

_ABOUT_TEXT = """\
Copy Xform World Space
Version {ver}
----------------------------------------------------------------

Also known as: Sticky Tool, Animation Recorder

A Maya Python animation utility that copies and pastes world-space
transforms between objects and across the timeline.  Keyframe values are
always written as local channel values so the tool works correctly with
rigged characters and parented controllers.

REQUIREMENTS
  Maya 2020 or later (PySide2 or PySide6)

INSTALLATION
  Drag install_xform_copy_paste.mel onto the Maya viewport.

SOURCE
  github.com/dshepstone/xform_copy_paste
----------------------------------------------------------------
""".format(ver=VERSION)


# ===========================================================================
#  Public API - core transform functions
#  These contain no UI code and run under any Maya (Python 2.7 or 3.x).
# ===========================================================================

def auto_xform_world_space():
    """
    Alt+Click

    Copy world-space xform from the FIRST selected object and paste it to
    all remaining selected objects at the current frame. Sets a keyframe on
    all 9 transform channels for each target.

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
    Ctrl+Shift+Click

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
    print("xform_copy_paste: Copied xform for {} frames ({}-{}) from '{}'.".format(
        len(frame_data), min_f, max_f, source))


def paste_xform_world_space():
    """
    Ctrl+Click

    Paste the stored single-frame world-space xform to all selected objects
    at the current frame. Sets a keyframe on all 9 transform channels.
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
    Ctrl+Alt+Shift+Click

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
                cmds.warning("xform_copy_paste: '{}' has no keyframes - skipping.".format(obj))
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
    Ctrl+Alt+Click

    Bake the stored range xform data to all selected objects across the
    current playback range. Requires copy_xform_playback_range() first.

    Sets a keyframe on every frame for all 9 transform channels.
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
                cmds.warning("xform_copy_paste: Frame {} not in copied range - skipping.".format(f))
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
        " ({} frame(s) skipped - not in copied range)".format(skipped) if skipped else ""))


def paste_xform_world_space_next_frame():
    """
    Shift+Click

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
      1. Select all source controllers -> Copy Xform WS Multi Objects Range
      2. Select corresponding target controllers (same order / count)
         -> Paste Xform WS Keys Playback Range

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
    print("xform_copy_paste: Copied {} object(s) across {} frames ({}-{}).".format(
        len(sel), max_f - min_f + 1, min_f, max_f))


def paste_xform_world_space_keys_range():
    """
    Paste the stored multi-object world-space xform onto each selected object,
    but ONLY at frames that already have keyframes on that object within the
    current playback range.  No new frames are created - only existing keys
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

    cmds.undoInfo(openChunk=True, chunkName="paste_xform_ws_keys_range")
    try:
        for i, obj in enumerate(sel):
            if i >= len(multi_data):
                cmds.warning(
                    "xform_copy_paste: No stored data for target {} ('{}') - skipping.".format(
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
                    "xform_copy_paste: '{}' has no keyframes in range {}-{} - skipping.".format(
                        obj, min_f, max_f)
                )
                continue

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
        total_keys, min(len(sel), len(multi_data))))


# ===========================================================================
#  Shelf entry point - modifier-click routing
# ===========================================================================

def dispatch():
    """Shelf-button entry point.

    Reads the keyboard modifiers held during the click and runs the matching
    action.  A plain click (no modifiers) opens the tool window.  This is what
    makes the SHORTCUTS table on the window actually work from the shelf.

    Modifier bit values from cmds.getModifiers(): Shift=1, Ctrl=4, Alt=8.
    """
    try:
        mods = cmds.getModifiers()
    except Exception:
        mods = 0

    shift = bool(mods & 1)
    ctrl  = bool(mods & 4)
    alt   = bool(mods & 8)

    # Order matters: test the most specific combos first.
    if ctrl and alt and shift:
        paste_xform_world_space_all_keys()
    elif ctrl and shift:
        copy_xform_playback_range()
    elif ctrl and alt:
        paste_xform_world_space_bake_frames()
    elif alt:
        auto_xform_world_space()
    elif ctrl:
        paste_xform_world_space()
    elif shift:
        paste_xform_world_space_next_frame()
    else:
        show()


# ===========================================================================
#  Qt compatibility layer (matches the Inbetweener / Noise Generator tools)
# ===========================================================================

def _import_qt_modules():
    """Resolve the Qt bindings bundled with the current Maya session."""
    binding_attempts = (
        ("PySide6", "shiboken6"),
        ("PySide6", "shiboken2"),
        ("PySide2", "shiboken2"),
        ("PySide2", "shiboken6"),
    )

    last_error = None
    for qt_mod_name, shiboken_name in binding_attempts:
        try:
            qt_mod = __import__(qt_mod_name, fromlist=["QtCore", "QtGui", "QtWidgets"])
            shiboken_mod = __import__(shiboken_name)
        except ImportError as exc:
            last_error = exc
            continue

        try:
            qt_core = getattr(qt_mod, "QtCore")
            qt_gui = getattr(qt_mod, "QtGui")
            qt_widgets = getattr(qt_mod, "QtWidgets")
        except AttributeError as exc:
            last_error = exc
            continue

        return qt_core, qt_gui, qt_widgets, shiboken_mod

    raise ImportError(
        "Copy Xform World Space requires PySide2/PySide6 with shiboken"
        " (last error: {})".format(last_error))


# ---------------------------------------------------------------------------
# Palette - single source of truth for the dark theme
# ---------------------------------------------------------------------------
_C = {
    "bg":          "#1e1f22",
    "panel":       "#26272b",
    "panel_hi":    "#2c2d32",
    "border":      "#3a3b40",
    "border_soft": "#45464c",
    "text":        "#e6e7ea",
    "text_dim":    "#9a9ca2",
    "text_faint":  "#6f7177",
    # category accents
    "amber":       "#d08a2e",
    "amber_text":  "#f0cf9a",
    "blue":        "#4f86d6",
    "blue_text":   "#bcd3f2",
    "purple":      "#9a6bd8",
    "purple_text": "#dcc6f4",
}


def _stylesheet():
    """Return the application-wide stylesheet for the tool window."""
    return """
    QDialog#xformRoot {{ background: {bg}; }}
    QWidget#contentPane {{ background: {bg}; }}

    QLabel {{ color: {text}; background: transparent; border: none; }}

    /* Card panels */
    QFrame#card {{
        background: {panel};
        border: 1px solid {border};
        border-radius: 8px;
    }}

    /* Section heading text */
    QLabel#sectionTitle {{
        color: {text_dim};
        font-size: 11px;
        font-weight: bold;
        letter-spacing: 1px;
    }}

    QLabel#headerTitle {{
        color: {text};
        font-size: 17px;
        font-weight: bold;
    }}
    QLabel#headerSub {{ color: {text_dim}; font-size: 11px; }}
    QLabel#statusHead {{ color: {text}; font-size: 13px; font-weight: bold; }}
    QLabel#statusDetail {{ color: {text_dim}; font-size: 10px; }}
    QLabel#footer {{ color: {text_faint}; font-size: 10px; }}

    /* --- Buttons: base --- */
    QPushButton {{
        text-align: left;
        padding: 7px 12px;
        border-radius: 6px;
        font-size: 12px;
        color: {text};
        background: {panel_hi};
        border: 1px solid {border};
    }}
    QPushButton:hover {{ border-color: {border_soft}; }}
    QPushButton:pressed {{ background: {bg}; }}

    /* Auto - primary orange, filled */
    QPushButton#autoBtn {{
        background: #9c6322;
        border: 1px solid #c5832f;
        color: #fdf3e2;
        font-weight: bold;
    }}
    QPushButton#autoBtn:hover {{ background: #b37428; }}
    QPushButton#autoBtn:pressed {{ background: #7e4f1a; }}

    /* Copy - warm/amber */
    QPushButton#copyBtn {{
        background: #2f2818;
        border: 1px solid #6a5325;
        color: {amber_text};
    }}
    QPushButton#copyBtn:hover {{ background: #3a311d; border-color: #8a6a30; }}
    QPushButton#copyBtn:pressed {{ background: #241d11; }}

    /* Paste - blue */
    QPushButton#pasteBtn {{
        background: #1d2733;
        border: 1px solid #3a567c;
        color: {blue_text};
    }}
    QPushButton#pasteBtn:hover {{ background: #243140; border-color: #4f6f9c; }}
    QPushButton#pasteBtn:pressed {{ background: #161e28; }}

    /* Paste keys playback range - purple */
    QPushButton#purpleBtn {{
        background: #281d36;
        border: 1px solid #5a3d80;
        color: {purple_text};
    }}
    QPushButton#purpleBtn:hover {{ background: #312542; border-color: #74519f; }}
    QPushButton#purpleBtn:pressed {{ background: #1e1629; }}

    /* Icon/ghost button (header gear, db icon) */
    QPushButton#ghostBtn {{
        background: transparent;
        border: 1px solid {border};
        border-radius: 14px;
        padding: 0;
        color: {text_dim};
        font-size: 14px;
    }}
    QPushButton#ghostBtn:hover {{ border-color: {border_soft}; color: {text}; }}

    /* Shortcut key caps */
    QLabel#keycap {{
        color: {text_dim};
        background: {panel_hi};
        border: 1px solid {border};
        border-radius: 4px;
        padding: 2px 8px;
        font-family: "Consolas", "Courier New", monospace;
        font-size: 10px;
    }}
    QLabel#shortcutName {{ color: {text_dim}; font-size: 11px; }}

    QScrollArea {{ background: transparent; border: none; }}
    QScrollBar:vertical {{
        background: {bg}; width: 10px; margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background: {border_soft}; border-radius: 5px; min-height: 28px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    """.format(**_C)


# Resolve Qt once at import.  Kept here (after the core API) so the transform
# functions remain importable even if a non-Maya context lacks PySide; the
# import only fires when the module is actually loaded inside Maya.
QtCore, QtGui, QtWidgets, shiboken = _import_qt_modules()


# ---------------------------------------------------------------------------
# Action descriptors - single source for buttons, tooltips and the shortcut
# table.  (name, object_id, tooltip, function, shortcut_label)
# ---------------------------------------------------------------------------
_COPY_ACTIONS = [
    ("Auto Xform World Space", "autoBtn",
     "Copy from the first selected object and paste to all the rest at the "
     "current frame  (shelf: Alt+Click). Needs 2+ objects.",
     auto_xform_world_space),
    ("Copy Xform World Space", "copyBtn",
     "Copy the world-space xform of the first selected object at the current frame.",
     copy_xform_world_space),
    ("Copy Xform World Space Playback Range", "copyBtn",
     "Sample the first selected object every frame of the playback range  "
     "(shelf: Ctrl+Shift+Click).",
     copy_xform_playback_range),
    ("Copy Xform WS Multi Objects Playback Range", "copyBtn",
     "Sample ALL selected objects across the playback range, preserving "
     "selection order.",
     copy_xform_world_space_multi_range),
]

_PASTE_ACTIONS = [
    ("Paste Xform World Space", "pasteBtn",
     "Paste the stored xform to selected objects at the current frame  "
     "(shelf: Ctrl+Click).",
     paste_xform_world_space),
    ("Paste Xform World Space All Keys", "pasteBtn",
     "Paste the stored xform at every existing keyframe time  "
     "(shelf: Ctrl+Alt+Shift+Click).",
     paste_xform_world_space_all_keys),
    ("Paste Xform World Space Bake Frames", "pasteBtn",
     "Bake the stored single-object range onto every frame  "
     "(shelf: Ctrl+Alt+Click).",
     paste_xform_world_space_bake_frames),
    ("Paste Xform World Space Next Frame", "pasteBtn",
     "Paste at the current frame then advance by 1  (shelf: Shift+Click).",
     paste_xform_world_space_next_frame),
    ("Paste Xform WS Keys Playback Range", "purpleBtn",
     "After 'Copy Xform WS Multi Objects Playback Range', overwrite each "
     "target's existing keys within the playback range (no baking).",
     paste_xform_world_space_keys_range),
]

_SHORTCUTS = [
    ("Auto Xform World Space",       "Alt+Click"),
    ("Copy Xform WS Playback Range", "Ctrl+Shift+Click"),
    ("Copy Xform WS Multi Range",    "window button"),
    ("Paste Xform World Space",      "Ctrl+Click"),
    ("Paste Xform WS All Keys",      "Ctrl+Alt+Shift+Click"),
    ("Paste Xform WS Bake Frames",   "Ctrl+Alt+Click"),
    ("Paste Xform WS Next Frame",    "Shift+Click"),
    ("Paste Xform WS Keys Range",    "window button"),
]


def _maya_main_window():
    """Return Maya's main window wrapped as a QWidget (or None)."""
    try:
        import maya.OpenMayaUI as omui
        ptr = omui.MQtUtil.mainWindow()
        if ptr is not None:
            return shiboken.wrapInstance(int(ptr), QtWidgets.QWidget)
    except Exception:
        pass
    return None


class XformCopyPasteUI(QtWidgets.QDialog):
    """Copy Xform World Space - modern PySide tool window."""

    instance = None

    # -- singleton display ------------------------------------------------
    @classmethod
    def display(cls):
        if cls.instance is not None:
            try:
                if not shiboken.isValid(cls.instance):
                    cls.instance = None
            except RuntimeError:
                cls.instance = None

        if cls.instance is None:
            cls.instance = cls()

        cls.instance.show()
        cls.instance.raise_()
        cls.instance.activateWindow()
        return cls.instance

    def __init__(self, parent=None):
        _delete_legacy_ui()
        if parent is None:
            parent = _maya_main_window()
        super(XformCopyPasteUI, self).__init__(parent)

        self.setObjectName("xformRoot")
        self.setWindowTitle("{}  v{}".format(TITLE, VERSION))
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.Tool)
        self.setStyleSheet(_stylesheet())
        self.setMinimumWidth(420)

        self._status_dot  = None
        self._status_head = None
        self._status_det  = None

        self._build_ui()
        self.refresh_status()

        # Size to content, capped to the available screen height.
        hint = self._content.sizeHint()
        avail_h = 1000
        try:
            screen = self.screen() or QtGui.QGuiApplication.primaryScreen()
            if screen:
                avail_h = screen.availableGeometry().height()
        except Exception:
            pass
        self.resize(460, min(hint.height() + 16, avail_h - 80))

    # =====================================================================
    #  Construction helpers
    # =====================================================================
    def _build_ui(self):
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        outer.addWidget(scroll)

        self._content = QtWidgets.QWidget()
        self._content.setObjectName("contentPane")
        scroll.setWidget(self._content)

        main = QtWidgets.QVBoxLayout(self._content)
        main.setContentsMargins(14, 14, 14, 12)
        main.setSpacing(12)

        main.addWidget(self._build_header())
        main.addWidget(self._build_status_card())
        main.addWidget(self._build_action_card("COPY", "⦿", _COPY_ACTIONS))
        main.addWidget(self._build_action_card("PASTE", "⤓", _PASTE_ACTIONS))
        main.addWidget(self._build_shortcuts_card())
        main.addWidget(self._build_footer())
        main.addStretch()

    def _card(self):
        frame = QtWidgets.QFrame()
        frame.setObjectName("card")
        lay = QtWidgets.QVBoxLayout(frame)
        lay.setContentsMargins(12, 10, 12, 12)
        lay.setSpacing(8)
        return frame, lay

    def _build_header(self):
        frame, lay = self._card()

        row = QtWidgets.QHBoxLayout()
        row.setSpacing(12)

        icon = QtWidgets.QLabel("◎")  # bullseye glyph
        icon.setStyleSheet("color: {}; font-size: 30px;".format(_C["amber"]))
        icon.setFixedWidth(40)
        icon.setAlignment(QtCore.Qt.AlignCenter)
        row.addWidget(icon)

        text_col = QtWidgets.QVBoxLayout()
        text_col.setSpacing(2)
        title = QtWidgets.QLabel(TITLE)
        title.setObjectName("headerTitle")
        sub = QtWidgets.QLabel("Copy and paste world-space transforms between objects.")
        sub.setObjectName("headerSub")
        sub.setWordWrap(True)
        text_col.addWidget(title)
        text_col.addWidget(sub)
        row.addLayout(text_col, 1)

        gear = QtWidgets.QPushButton("⚙")
        gear.setObjectName("ghostBtn")
        gear.setFixedSize(28, 28)
        gear.setToolTip("Help and About")
        gear.setCursor(QtCore.Qt.PointingHandCursor)
        gear.clicked.connect(self._show_help_menu)
        self._gear_btn = gear
        row.addWidget(gear, 0, QtCore.Qt.AlignTop)

        lay.addLayout(row)
        return frame

    def _build_status_card(self):
        frame, lay = self._card()
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(12)

        dot = QtWidgets.QLabel()
        dot.setFixedSize(12, 12)
        self._status_dot = dot
        row.addWidget(dot, 0, QtCore.Qt.AlignVCenter)

        col = QtWidgets.QVBoxLayout()
        col.setSpacing(2)
        head = QtWidgets.QLabel("No Xform Stored")
        head.setObjectName("statusHead")
        det = QtWidgets.QLabel("Store a transform to enable paste operations.")
        det.setObjectName("statusDetail")
        det.setWordWrap(True)
        self._status_head = head
        self._status_det = det
        col.addWidget(head)
        col.addWidget(det)
        row.addLayout(col, 1)

        clear = QtWidgets.QPushButton("✕")
        clear.setObjectName("ghostBtn")
        clear.setFixedSize(28, 28)
        clear.setToolTip("Clear the stored transform")
        clear.setCursor(QtCore.Qt.PointingHandCursor)
        clear.clicked.connect(self._clear_store)
        row.addWidget(clear, 0, QtCore.Qt.AlignVCenter)

        lay.addLayout(row)
        return frame

    def _build_action_card(self, title, glyph, actions):
        frame, lay = self._card()
        lay.addLayout(self._section_header(glyph, title))
        for name, obj_id, tip, func in actions:
            lay.addWidget(self._action_button(name, obj_id, tip, func))
        return frame

    def _section_header(self, glyph, title):
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(6)
        g = QtWidgets.QLabel(glyph)
        g.setStyleSheet("color: {}; font-size: 12px;".format(_C["text_dim"]))
        lbl = QtWidgets.QLabel(title)
        lbl.setObjectName("sectionTitle")
        row.addWidget(g)
        row.addWidget(lbl)
        row.addStretch()
        return row

    def _action_button(self, name, obj_id, tip, func):
        btn = QtWidgets.QPushButton(name)
        btn.setObjectName(obj_id)
        btn.setToolTip(tip)
        btn.setMinimumHeight(34)
        btn.setCursor(QtCore.Qt.PointingHandCursor)
        btn.clicked.connect(lambda _=False, f=func: self._run(f))
        return btn

    def _build_shortcuts_card(self):
        frame, lay = self._card()
        lay.addLayout(self._section_header("⌨", "SHORTCUTS"))

        grid = QtWidgets.QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)
        grid.setColumnStretch(0, 1)
        for r, (name, hotkey) in enumerate(_SHORTCUTS):
            nm = QtWidgets.QLabel(name)
            nm.setObjectName("shortcutName")
            cap = QtWidgets.QLabel(hotkey)
            cap.setObjectName("keycap")
            cap.setAlignment(QtCore.Qt.AlignCenter)
            grid.addWidget(nm, r, 0, QtCore.Qt.AlignVCenter)
            grid.addWidget(cap, r, 1, QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        lay.addLayout(grid)
        return frame

    def _build_footer(self):
        lbl = QtWidgets.QLabel(
            "ⓘ  World-space position, rotation and scale are copied and pasted.")
        lbl.setObjectName("footer")
        lbl.setAlignment(QtCore.Qt.AlignCenter)
        lbl.setWordWrap(True)
        return lbl

    # =====================================================================
    #  Behaviour
    # =====================================================================
    def _run(self, func):
        """Execute a core function then refresh the status panel."""
        try:
            func()
        except Exception as e:
            cmds.warning("xform_copy_paste: {}".format(e))
        self.refresh_status()

    def _clear_store(self):
        for k in _XFORM_STORE:
            _XFORM_STORE[k] = None
        self.refresh_status()
        print("xform_copy_paste: Stored transform cleared.")

    def refresh_status(self):
        """Update the status dot / text from the current store."""
        if self._status_dot is None:
            return
        try:
            _state, head, detail, accent = _status_info()
            self._status_dot.setStyleSheet(
                "background: {}; border-radius: 6px;".format(accent))
            self._status_head.setText(head)
            self._status_det.setText(detail)
        except RuntimeError:
            # Widgets were deleted (window closed) - ignore.
            pass

    def _show_help_menu(self):
        menu = QtWidgets.QMenu(self)
        menu.addAction("Help", show_help)
        menu.addAction("About", show_about)
        menu.exec_(self._gear_btn.mapToGlobal(
            QtCore.QPoint(0, self._gear_btn.height())))

    # =====================================================================
    #  Lifecycle
    # =====================================================================
    def showEvent(self, event):
        global _ACTIVE_WINDOW
        _ACTIVE_WINDOW = self
        super(XformCopyPasteUI, self).showEvent(event)

    def closeEvent(self, event):
        global _ACTIVE_WINDOW
        if _ACTIVE_WINDOW is self:
            _ACTIVE_WINDOW = None
        super(XformCopyPasteUI, self).closeEvent(event)


# ---------------------------------------------------------------------------
# Help / About windows (Qt)
# ---------------------------------------------------------------------------

def _text_window(title, body, size):
    win = QtWidgets.QDialog(_maya_main_window())
    win.setWindowTitle(title)
    win.setWindowFlags(win.windowFlags() | QtCore.Qt.Tool)
    win.setStyleSheet("QDialog {{ background: {bg}; }}".format(bg=_C["bg"]))
    win.resize(*size)

    lay = QtWidgets.QVBoxLayout(win)
    lay.setContentsMargins(0, 0, 0, 0)
    view = QtWidgets.QPlainTextEdit()
    view.setReadOnly(True)
    view.setPlainText(body)
    view.setStyleSheet(
        "QPlainTextEdit {{ background: {panel}; color: {text}; border: none;"
        " font-family: 'Consolas','Courier New',monospace; font-size: 11px;"
        " padding: 10px; }}".format(panel=_C["panel"], text=_C["text"]))
    lay.addWidget(view)
    win.show()
    return win


_HELP_WINDOW = None
_ABOUT_WINDOW = None


def show_help():
    """Open the Help reference window."""
    global _HELP_WINDOW
    _HELP_WINDOW = _text_window(
        "Copy Xform World Space - Help", _HELP_TEXT, (620, 700))


def show_about():
    """Open the About window."""
    global _ABOUT_WINDOW
    _ABOUT_WINDOW = _text_window(
        "About - Copy Xform World Space", _ABOUT_TEXT, (520, 380))


# ---------------------------------------------------------------------------
# Legacy cleanup + entry points
# ---------------------------------------------------------------------------

def _delete_legacy_ui():
    """Remove any leftover maya.cmds windows from the 1.x UI."""
    for win_id in (_WIN_ID, _HELP_WIN_ID, _ABOUT_WIN_ID):
        try:
            if cmds.window(win_id, exists=True):
                cmds.deleteUI(win_id, window=True)
        except Exception:
            pass


def show():
    """Open (or reopen) the Copy Xform World Space tool window."""
    return XformCopyPasteUI.display()


def launch():
    """Alias for show()."""
    return show()


if __name__ == "__main__":
    show()
