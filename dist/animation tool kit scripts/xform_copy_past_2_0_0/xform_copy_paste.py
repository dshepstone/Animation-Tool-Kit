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
#   paste_xform_world_space()             - Paste stored xform at current frame
#   paste_xform_world_space_all_keys()    - Paste at all existing keyframe times
#   paste_xform_world_space_bake_frames() - Bake stored range xform to targets
#   paste_xform_world_space_next_frame()  - Paste then advance timeline by 1
#
# Requirements: Maya 2017+ (Python 2.7 or 3.x)
# =============================================================================

import os
import shutil

import maya.cmds as cmds

# ---------------------------------------------------------------------------
# Window ID — used to detect and delete an existing window before reopening
# ---------------------------------------------------------------------------
_WIN_ID    = "xform_copy_paste_win"
_STATUS_ID = "xform_copy_paste_status"


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


def _set_xform(obj, t, r, s):
    """Apply world-space translate, rotate, scale to obj."""
    cmds.xform(obj, ws=True, t=t)
    cmds.xform(obj, ws=True, ro=r)
    cmds.xform(obj, ws=True, s=s)


def _set_keyframe(obj, frame):
    """Key all 9 transform channels on obj at the given frame.

    Intentionally does NOT pass explicit values — Maya keys whatever the
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


def _update_status():
    """Refresh the status pill in the tool window (if open)."""
    if not cmds.control(_STATUS_ID, exists=True):
        return
    if _XFORM_STORE["translate"] is not None:
        label = "  \u25cf  Xform Stored"
        bg    = (0.11, 0.40, 0.18)
    elif _XFORM_STORE["frame_data"] is not None:
        n     = len(_XFORM_STORE["frame_data"])
        label = "  \u25cf  Range Stored  ({} frames)".format(n)
        bg    = (0.12, 0.28, 0.52)
    elif _XFORM_STORE["multi_data"] is not None:
        n_obj = len(_XFORM_STORE["multi_data"])
        n_frm = len(_XFORM_STORE["multi_data"][0]) if _XFORM_STORE["multi_data"] else 0
        label = "  \u25cf  Multi-Object Range  ({} objs, {} frames)".format(n_obj, n_frm)
        bg    = (0.30, 0.16, 0.50)
    else:
        label = "  \u25cb  No Xform Stored"
        bg    = (0.25, 0.25, 0.25)
    cmds.text(_STATUS_ID, e=True, label=label, backgroundColor=bg)


# ---------------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------------

def _section_header(label):
    """Dark full-width section label strip."""
    cmds.columnLayout(adjustableColumn=True, bgc=(0.17, 0.17, 0.17))
    cmds.text(
        label=label,
        align="left",
        font="smallBoldLabelFont",
        height=22,
        backgroundColor=(0.17, 0.17, 0.17),
    )
    cmds.setParent("..")


def _action_button(label, annotation, color, func):
    """Colored action button."""
    cmds.button(
        label=label,
        height=30,
        annotation=annotation,
        backgroundColor=color,
        command=lambda *_: _run(func),
    )


# ---------------------------------------------------------------------------
# UI — Help and About windows
# ---------------------------------------------------------------------------

_HELP_WIN_ID  = "xform_copy_paste_help_win"
_ABOUT_WIN_ID = "xform_copy_paste_about_win"

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
controllers, COG, IK handles, etc.).

─────────────────────────────────────────────────────────────────────────

COPY FUNCTIONS
--------------

Auto Xform World Space  [Alt+Click shelf button]
  Copies the world-space transform from the FIRST selected object and
  immediately pastes it to every other selected object at the current
  frame.  Sets a keyframe on all 9 channels (tx ty tz rx ry rz sx sy sz)
  for each target.  Requires at least 2 objects selected.

Copy Xform World Space  [shelf button]
  Captures the world-space transform of the first selected object at the
  current frame and stores it in memory.  Use any Paste function to apply
  the stored values.  Requires at least 1 object selected.

Copy Xform World Space Playback Range  [Ctrl+Shift+Click shelf button]
  Samples the first selected object's world-space transform on every
  frame of the current playback range and stores the result as a
  frame-keyed dictionary.  Used with Paste Xform WS Bake Frames.
  Requires at least 1 object selected.

Copy Xform WS Multi Objects Playback Range  [window button]
  Samples ALL selected objects across the entire playback range and
  stores per-object, per-frame world-space data.  Selection order is
  preserved so each source maps to the corresponding target during paste.
  Used with Paste Xform WS Keys Playback Range.
  Requires at least 1 object selected.

─────────────────────────────────────────────────────────────────────────

PASTE FUNCTIONS
---------------

Paste Xform World Space  [Ctrl+Click shelf button]
  Pastes the stored single-frame world-space transform to all selected
  objects at the current frame.  Sets a keyframe on all 9 channels.
  Requires a prior Copy Xform World Space (or Auto Xform).

Paste Xform World Space All Keys  [Ctrl+Alt+Shift+Click shelf button]
  Pastes the stored single-frame xform to all selected objects at EVERY
  frame that already has a keyframe on the target.  Does not create new
  keyframe times — only overwrites existing ones.
  Requires a prior Copy Xform World Space.

Paste Xform World Space Bake Frames  [Ctrl+Alt+Click shelf button]
  Bakes the stored playback-range data onto all selected objects, setting
  a keyframe on every frame of the range.  Targets that are missing
  frames from the stored range receive a warning and those frames are
  skipped.
  Requires a prior Copy Xform WS Playback Range.

Paste Xform World Space Next Frame  [Shift+Click shelf button]
  Pastes the stored single-frame xform at the current frame then advances
  the timeline by 1.  Useful for step-by-step pose-to-pose work.
  Requires a prior Copy Xform World Space.

Paste Xform WS Keys Playback Range  [window button]
  Pairs with Copy Xform WS Multi Objects Playback Range.
  For each selected target, looks up the corresponding stored source data
  (matched by selection index) and overwrites keyframe values only at
  frames that already have keyframes on the target within the playback
  range.  No new keyframe times are created — existing animation curves
  are retimed to the captured world position.
  Requires a prior Copy Xform WS Multi Objects Playback Range.

─────────────────────────────────────────────────────────────────────────

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
Version 1.0
─────────────────────────────────────────────────────────────────────────

Also known as: Sticky Tool, Animation Recorder

A Maya Python animation utility that copies and pastes world-space
transforms between objects and across the timeline.  Keyframe values are
always written as local channel values so the tool works correctly with
rigged characters and parented controllers.

REQUIREMENTS
  Maya 2017 or later (Python 2.7 or Python 3.x)

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
─────────────────────────────────────────────────────────────────────────
"""


def show_help():
    """Open the Help reference window."""
    if cmds.window(_HELP_WIN_ID, exists=True):
        cmds.deleteUI(_HELP_WIN_ID)

    win = cmds.window(
        _HELP_WIN_ID,
        title="Copy Xform World Space — Help",
        widthHeight=(560, 680),
        sizeable=True,
        menuBar=False,
    )
    cmds.scrollLayout(childResizable=True)
    cmds.columnLayout(adjustableColumn=True, bgc=(0.18, 0.18, 0.18))
    cmds.separator(height=10, style="none")
    cmds.text(
        label=_HELP_TEXT,
        align="left",
        font="fixedWidthFont",
        backgroundColor=(0.18, 0.18, 0.18),
    )
    cmds.separator(height=10, style="none")
    cmds.setParent("..")
    cmds.setParent("..")
    cmds.showWindow(win)


def show_about():
    """Open the About window."""
    if cmds.window(_ABOUT_WIN_ID, exists=True):
        cmds.deleteUI(_ABOUT_WIN_ID)

    win = cmds.window(
        _ABOUT_WIN_ID,
        title="About — Copy Xform World Space",
        widthHeight=(480, 340),
        sizeable=True,
        menuBar=False,
    )
    cmds.scrollLayout(childResizable=True)
    cmds.columnLayout(adjustableColumn=True, bgc=(0.18, 0.18, 0.18))
    cmds.separator(height=10, style="none")
    cmds.text(
        label=_ABOUT_TEXT,
        align="left",
        font="fixedWidthFont",
        backgroundColor=(0.18, 0.18, 0.18),
    )
    cmds.separator(height=10, style="none")
    cmds.setParent("..")
    cmds.setParent("..")
    cmds.showWindow(win)


# ---------------------------------------------------------------------------
# UI — main window
# ---------------------------------------------------------------------------

def show():
    """Open (or reopen) the Copy Xform World Space tool window."""
    if cmds.window(_WIN_ID, exists=True):
        cmds.deleteUI(_WIN_ID)

    win = cmds.window(
        _WIN_ID,
        title="Copy Xform World Space",
        widthHeight=(380, 760),
        sizeable=True,
        menuBar=True,
    )

    # ── Menu bar ─────────────────────────────────────────────────────────
    cmds.menu(label="Help")
    cmds.menuItem(label="Help",  command=lambda *_: show_help())
    cmds.menuItem(label="About", command=lambda *_: show_about())
    cmds.setParent("..")

    # Scroll layout so all content is reachable even at small window sizes
    cmds.scrollLayout(childResizable=True)
    cmds.columnLayout(adjustableColumn=True, bgc=(0.20, 0.20, 0.20))

    # ── Title ──────────────────────────────────────────────────────────────
    cmds.separator(height=14, style="none")
    cmds.text(
        label="Copy Xform World Space",
        font="boldLabelFont",
        height=22,
        align="center",
        backgroundColor=(0.20, 0.20, 0.20),
    )
    cmds.separator(height=8, style="none")
    cmds.text(
        label=(
            "Copies and pastes world-space transforms between objects.\n"
            'Also known as "Sticky Tool" or "Animation Recorder".'
        ),
        align="center",
        height=32,
        backgroundColor=(0.20, 0.20, 0.20),
    )
    cmds.separator(height=12, style="none")

    # ── Status pill (full width — no side margin) ───────────────────────────
    cmds.text(
        _STATUS_ID,
        label="  \u25cb  No Xform Stored",
        height=30,
        align="left",
        font="boldLabelFont",
        backgroundColor=(0.25, 0.25, 0.25),
    )

    cmds.separator(height=12, style="none")

    # ── COPY section ───────────────────────────────────────────────────────
    _section_header("  COPY")
    # frameLayout provides the marginWidth/marginHeight that columnLayout lacks
    cmds.frameLayout(labelVisible=False, marginWidth=8, marginHeight=4,
                     bgc=(0.20, 0.20, 0.20))
    cmds.columnLayout(adjustableColumn=True, bgc=(0.20, 0.20, 0.20))

    _action_button(
        "Auto Xform World Space",
        "Copy first selected, paste to all remaining at current frame  (Alt+Click)",
        (0.52, 0.30, 0.08),
        auto_xform_world_space,
    )
    cmds.separator(height=4, style="none")
    _action_button(
        "Copy Xform World Space",
        "Copy world-space xform from first selected object at current frame",
        (0.12, 0.40, 0.46),
        copy_xform_world_space,
    )
    cmds.separator(height=4, style="none")
    _action_button(
        "Copy Xform World Space Playback Range",
        "Copy xform for every frame in the playback range  (Ctrl+Shift+Click)",
        (0.12, 0.40, 0.46),
        copy_xform_playback_range,
    )
    cmds.separator(height=4, style="none")
    _action_button(
        "Copy Xform WS Multi Objects Playback Range",
        "Copy world-space xform from ALL selected objects across the playback range",
        (0.10, 0.33, 0.38),
        copy_xform_world_space_multi_range,
    )
    cmds.setParent("..")  # end columnLayout
    cmds.setParent("..")  # end frameLayout (copy)

    cmds.separator(height=12, style="none")

    # ── PASTE section ──────────────────────────────────────────────────────
    _section_header("  PASTE")
    cmds.frameLayout(labelVisible=False, marginWidth=8, marginHeight=4,
                     bgc=(0.20, 0.20, 0.20))
    cmds.columnLayout(adjustableColumn=True, bgc=(0.20, 0.20, 0.20))

    _action_button(
        "Paste Xform World Space",
        "Paste stored xform to selected objects at current frame  (Ctrl+Click)",
        (0.17, 0.28, 0.52),
        paste_xform_world_space,
    )
    cmds.separator(height=4, style="none")
    _action_button(
        "Paste Xform World Space All Keys",
        "Paste stored xform at all existing keyframe times  (Ctrl+Alt+Shift+Click)",
        (0.17, 0.28, 0.52),
        paste_xform_world_space_all_keys,
    )
    cmds.separator(height=4, style="none")
    _action_button(
        "Paste Xform World Space Bake Frames",
        "Bake stored single-object range xform to every frame  (Ctrl+Alt+Click)",
        (0.17, 0.28, 0.52),
        paste_xform_world_space_bake_frames,
    )
    cmds.separator(height=4, style="none")
    _action_button(
        "Paste Xform World Space Next Frame",
        "Paste stored xform at current frame, then advance by 1  (Shift+Click)",
        (0.17, 0.28, 0.52),
        paste_xform_world_space_next_frame,
    )
    cmds.separator(height=4, style="none")
    _action_button(
        "Paste Xform WS Keys Playback Range",
        "Use after 'Copy Xform WS Multi Objects Playback Range' — "
        "pastes each target's stored world-space xform only at its existing "
        "keyframe times within the playback range (no baking)",
        (0.28, 0.14, 0.46),
        paste_xform_world_space_keys_range,
    )
    cmds.setParent("..")  # end columnLayout
    cmds.setParent("..")  # end frameLayout (paste)

    cmds.separator(height=12, style="none")

    # ── SHORTCUTS section ──────────────────────────────────────────────────
    _section_header("  SHORTCUTS")
    cmds.frameLayout(labelVisible=False, marginWidth=8, marginHeight=4,
                     bgc=(0.20, 0.20, 0.20))
    cmds.columnLayout(adjustableColumn=True, bgc=(0.20, 0.20, 0.20))

    _shortcuts = [
        ("Auto Xform World Space",        "Alt+Click"),
        ("Copy Xform WS Playback Range",  "Ctrl+Shift+Click"),
        ("Copy Xform WS Multi Range",     "window button"),
        ("Paste Xform World Space",       "Ctrl+Click"),
        ("Paste Xform WS All Keys",       "Ctrl+Alt+Shift+Click"),
        ("Paste Xform WS Bake Frames",    "Ctrl+Alt+Click"),
        ("Paste Xform WS Next Frame",     "Shift+Click"),
        ("Paste Xform WS Keys Range",     "window button"),
    ]

    cmds.rowColumnLayout(
        numberOfColumns=2,
        columnWidth=[(1, 210), (2, 148)],
        columnAlign=[(1, "left"), (2, "right")],
    )
    for i, (name, hotkey) in enumerate(_shortcuts):
        row_bg = (0.22, 0.22, 0.22) if i % 2 == 0 else (0.19, 0.19, 0.19)
        cmds.text(label="  " + name,    align="left",  font="smallFixedWidthFont",
                  height=20, backgroundColor=row_bg)
        cmds.text(label=hotkey + "  ",  align="right", font="smallFixedWidthFont",
                  height=20, backgroundColor=row_bg)
    cmds.setParent("..")  # end rowColumnLayout

    cmds.setParent("..")  # end columnLayout
    cmds.setParent("..")  # end frameLayout (shortcuts)
    cmds.separator(height=12, style="none")
    cmds.setParent("..")  # end outer columnLayout
    cmds.setParent("..")  # end scrollLayout

    cmds.showWindow(win)
    _update_status()


def _run(func):
    """Execute a core function then refresh the status indicator."""
    func()
    _update_status()


# ---------------------------------------------------------------------------
# Public API — 7 core functions
# ---------------------------------------------------------------------------

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
    print("xform_copy_paste: Copied xform for {} frames ({}–{}) from '{}'.".format(
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
