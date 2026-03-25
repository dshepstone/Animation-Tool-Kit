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
        "version":   "2.1.0",
    },
    {
        "id":        "add_remove",
        "label":     "Add / Remove Frames",
        "tooltip":   "Insert or remove frames while rippling keys downstream",
        "module":    "insert_remove_frames_tool",
        "launch_fn": "show",
        "icon_file": "add-remove.png",
        "icon_key":  "frames",
        "group":     "timing",
        "version":   "1.0.1",
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

        fn = getattr(mod, fn_name, None)
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
