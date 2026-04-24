"""ATK Loader — path management and tool registry for the Animation Tool Kit toolbar.

Handles sys.path setup for all tool modules and provides the central TOOL_REGISTRY
that drives toolbar button creation and tool launching.
"""

import os
import sys
import importlib
import importlib.util
import maya.cmds as cmds

# ---------------------------------------------------------------------------
# Tool Registry
# ---------------------------------------------------------------------------
# Each entry describes one toolbar button. Keys:
#   id          – unique string identifier
#   label       – human-readable name (used in tooltips and settings)
#   tooltip     – one-line description shown on hover
#   module      – importable Python module name (must be on sys.path)
#   launch_fn   – attribute name on the module to call (e.g. "show", "launch")
#   icon_file   – PNG basename searched in userBitmapsDir (fallback to generated)
#   icon_key    – key passed to atk_icons for the generated fallback icon
#   group       – logical category; separators are inserted between groups
#   version     – version string shown in the About tab of settings

TOOL_REGISTRY = [
    {
        "id":        "inbetweener",
        "label":     "Inbetweener",
        "tooltip":   "Blend poses between keyframes with multiple easing modes",
        "module":    "vertex_tweener",
        "launch_fn": "show",
        "icon_file": "inbetweener.png",
        "icon_key":  "tween",
        "group":     "timing",
        "version":   "2.0.2",
    },
    {
        "id":        "add_remove",
        "label":     "Add / Remove Frames",
        "tooltip":   "Insert or remove frames while rippling keys downstream",
        "module":    "insert_remove_frames_tool",
        "launch_fn": "show",
        "icon_file": "add_Remove.png",
        "icon_key":  "frames",
        "group":     "timing",
        "version":   "1.0.1",
    },
    {
        "id":        "tangent_tools",
        "label":     "Tangent Tools",
        "tooltip":   "Graph Editor curve tools for tangents and interpolation",
        "module":    "tangent_tools.main",
        "launch_fn": "launch",
        "icon_file": "curveTool.png",
        "icon_key":  "tween",
        "group":     "timing",
        "version":   "1.0.0",
    },
    {
        "id":        "tween_machine",
        "label":     "TweenMachine",
        "tooltip":   "Create in-between poses on selected keys and controls",
        "module":    "tweenMachine",
        "launch_fn": "start",
        "icon_file": "tm3-ShelfIcon.png",
        "icon_key":  "tween",
        "group":     "timing",
        "version":   "3.x",
    },
    {
        "id":        "noise",
        "label":     "Noise Generator",
        "tooltip":   "Add noise, easing and scaling effects to animation curves",
        "module":    "noise_generator_1_0_0",
        "launch_fn": "launch",
        "icon_file": "noise_generator_icon.png",
        "icon_key":  "noise",
        "group":     "timing",
        "version":   "1.0.0",
    },
    {
        "id":        "xform_copy_paste",
        "label":     "Xform Copy Paste",
        "tooltip":   "Copy and paste world-space transforms between objects",
        "module":    "xform_copy_paste",
        "launch_fn": "show",
        "icon_file": "xform_copy_paste.png",
        "icon_key":  "xform",
        "group":     "timing",
        "version":   "2.0.0",
    },
    {
        "id":        "bookmarks",
        "label":     "Bookmarks",
        "tooltip":   "Create and navigate time bookmarks on the Maya timeline",
        "module":    "time_bookmarks.main",
        "launch_fn": "launch",
        "icon_file": "Bookmark.png",
        "icon_key":  "bookmark",
        "group":     "timing",
        "version":   "0.1.0",
    },
    {
        "id":        "micro_manipulator",
        "label":     "Micro Manipulator",
        "tooltip":   "Precision transform controls with micro speed scrubbing",
        "module":    "Micro_Manipulator_v1_0_0",
        "launch_fn": "show",
        "icon_file": "Micro_Manipulator_Icon.png",
        "icon_key":  "xform",
        "group":     "viewport",
        "version":   "1.0.0",
    },
    {
        "id":        "temp_pivot",
        "label":     "Temp Pivot",
        "tooltip":   "Create temporary non-destructive rotation pivots for animation",
        "module":    "temp_pivot_tool",
        "launch_fn": "show",
        "icon_file": "temp-pivot.png",
        "icon_key":  "pivot",
        "group":     "viewport",
        "version":   "1.0.5",
    },
    {
        "id":        "onion_skin",
        "label":     "Onion Skin",
        "tooltip":   "Multi-frame ghosting for reference visualisation",
        "module":    "onion_skin_2_1_0",
        "launch_fn": "launch",
        "icon_file": "onionSkinIcon.png",
        "icon_key":  "onion",
        "group":     "viewport",
        "version":   "2.1.0",
    },
    {
        "id":        "anim_snap",
        "label":     "AnimSnap",
        "tooltip":   "Snap one object to another using world-space transforms",
        "module":    "anim_snap",
        "launch_fn": "launch",
        "icon_file": "animSnap.png",
        "icon_key":  "snap",
        "group":     "viewport",
        "version":   "1.0.0",
    },
    {
        "id":        "wire_shape",
        "label":     "Wire Shape Tool",
        "tooltip":   "Create curve-based rig control shapes",
        "module":    "wire_shape_tool",
        "launch_fn": "show",
        "icon_file": "Shape_Icon.png",
        "icon_key":  "wire",
        "group":     "rigging",
        "version":   "1.0.0",
    },
    {
        "id":        "reset",
        "label":     "Reset Tool",
        "tooltip":   "Reset translate, rotate and scale on selected objects",
        "module":    "transform_reset_tool",
        "launch_fn": "show",
        "icon_file": "reset_icon.png",
        "icon_key":  "reset",
        "group":     "rigging",
        "version":   "2.0.1",
    },
    {
        "id":        "selection_set",
        "label":     "Selection Set",
        "tooltip":   "Manage and recall named selection sets",
        "module":    "SmartSelectSets_v2",
        "launch_fn": "show_smart_select_sets",
        "icon_file": "selectionSet.png",
        "icon_key":  "select",
        "group":     "rigging",
        "version":   "2.0.4",
    },
    {
        "id":        "diget_mirror",
        "label":     "Diget Mirror",
        "tooltip":   "Mirror, swap or flip rig controls across left and right",
        "module":    "digetMirrorControl_v2_2_5",
        "launch_fn": "DigetMirrorControl.show_dialog",
        "icon_file": "mirror.png",
        "icon_key":  "mirror",
        "group":     "rigging",
        "version":   "2.2.5",
    },
    {
        "id":        "saveplus",
        "label":     "SavePlus",
        "tooltip":   "Intelligent file versioning and backup for Maya scenes",
        "module":    "savePlus_launcher",
        "launch_fn": "launch_save_plus",
        "icon_file": "saveplus.png",
        "icon_key":  "save",
        "group":     "pipeline",
        "version":   "2.0.4",
    },
    {
        "id":        "studio_library",
        "label":     "Studio Library",
        "tooltip":   "Manage poses and animation clips in a visual library",
        "module":    "studiolibrary",
        "launch_fn": "main",
        "icon_file": "studioLibrary.png",
        "icon_key":  "library",
        "group":     "pipeline",
        "version":   "2.21.1",
    },
    {
        "id":        "playblast_creator",
        "label":     "Playblast Creator",
        "tooltip":   "Render preview playblasts with shot masks and presets",
        "module":    "playblast_creator_ui",
        "launch_fn": "show_ui",
        "icon_file": "playblast_creator_icon.png",
        "icon_key":  "snap",
        "group":     "pipeline",
        "version":   "2.0.4",
    },
    {
        "id":        "user_directory_check",
        "label":     "User Directory Check",
        "tooltip":   "Review Maya user directories and verify that key paths exist",
        "module":    "user_directory_check",
        "launch_fn": "show",
        "icon_file": "user_directory_check_icon.png",
        "icon_key":  "user_dir",
        "group":     "pipeline",
        "version":   "1.0.0",
    },
]

# Ordered list of groups as they appear left-to-right on the toolbar
GROUP_ORDER = ["timing", "viewport", "rigging", "pipeline"]

# ---------------------------------------------------------------------------
# Preference keys for tool visibility (stored as Maya optionVar)
# ---------------------------------------------------------------------------
_OPT_HIDDEN_PREFIX = "atk_hidden_"


def _tool_by_id(tool_id):
    for t in TOOL_REGISTRY:
        if t["id"] == tool_id:
            return t
    return None


# ---------------------------------------------------------------------------
# sys.path setup
# ---------------------------------------------------------------------------

def setup_paths():
    """Add all known tool subdirectories to sys.path.

    Called once when the toolbar first loads.  Safe to call multiple times.
    """
    scripts_dir = cmds.internalVar(userScriptDir=True)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)

    # The atk_toolbar package directory itself
    pkg_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(pkg_dir)
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)

    # Playblast Creator ships into a versioned sub-folder that mirrors the
    # standalone installer layout (scripts/playblast_creator/PBC_v2_0_4/).
    # Put it on sys.path so "import playblast_creator_ui" resolves and add
    # it to MAYA_PLUG_IN_PATH so cmds.loadPlugin("playblast_creator.py")
    # finds the bundled plug-in by short name.
    pbc_dir = os.path.join(scripts_dir, "playblast_creator", "PBC_v2_0_4")
    if os.path.isdir(pbc_dir):
        if pbc_dir not in sys.path:
            sys.path.insert(0, pbc_dir)
        plug_in_path = os.environ.get("MAYA_PLUG_IN_PATH", "")
        if pbc_dir not in plug_in_path.split(os.pathsep):
            os.environ["MAYA_PLUG_IN_PATH"] = (
                pbc_dir if not plug_in_path else plug_in_path + os.pathsep + pbc_dir
            )


# ---------------------------------------------------------------------------
# Tool visibility
# ---------------------------------------------------------------------------

def is_tool_visible(tool_id):
    """Return True if the tool should appear on the toolbar."""
    opt = _OPT_HIDDEN_PREFIX + tool_id
    if cmds.optionVar(exists=opt):
        return not bool(cmds.optionVar(q=opt))
    return True  # visible by default


def set_tool_visible(tool_id, visible):
    """Persist tool visibility in a Maya optionVar."""
    opt = _OPT_HIDDEN_PREFIX + tool_id
    cmds.optionVar(iv=(opt, 0 if visible else 1))


def get_visible_tools():
    """Return the subset of TOOL_REGISTRY entries that should be shown."""
    return [t for t in TOOL_REGISTRY if is_tool_visible(t["id"])]


# ---------------------------------------------------------------------------
# Tool launching
# ---------------------------------------------------------------------------

def launch_tool(tool_id):
    """Import the tool module and call its launch function.

    Errors are caught and reported via cmds.warning so the toolbar stays alive
    even if an individual tool fails to load.
    """
    tool = _tool_by_id(tool_id)
    if tool is None:
        cmds.warning("ATK Toolbar: unknown tool id '{}'".format(tool_id))
        return

    module_name = tool["module"]
    fn_name = tool["launch_fn"]

    try:
        if module_name not in sys.modules:
            mod = importlib.import_module(module_name)
        else:
            mod = sys.modules[module_name]

        fn = mod
        for attr in fn_name.split("."):
            fn = getattr(fn, attr, None)
            if fn is None:
                break
        if fn is None:
            cmds.warning(
                "ATK Toolbar: module '{}' has no attribute '{}'.".format(
                    module_name, fn_name
                )
            )
            return

        fn()

    except ImportError as exc:
        exc_str = str(exc)
        if "PySide6" in exc_str or "shiboken6" in exc_str:
            # Reset Tool has a hard PySide6 import — only works on Maya 2025+
            cmds.confirmDialog(
                title="{} — Not Available".format(tool["label"]),
                message=(
                    "{} requires Maya 2025+ (PySide6).\n\n"
                    "Your Maya version ships PySide2 and is not supported "
                    "by this tool."
                ).format(tool["label"]),
                button=["OK"],
            )
        else:
            cmds.warning(
                "ATK Toolbar: could not import '{}'. "
                "Make sure the tool is installed.\n{}".format(module_name, exc)
            )
    except Exception as exc:
        cmds.warning("ATK Toolbar: error launching '{}': {}".format(tool_id, exc))


def is_tool_installed(tool_id):
    """Return True if the tool module can be found on sys.path."""
    tool = _tool_by_id(tool_id)
    if tool is None:
        return False
    try:
        spec = importlib.util.find_spec(tool["module"])
        return spec is not None
    except (ImportError, ValueError, ModuleNotFoundError):
        return False
