"""ATK Loader — path management and tool registry for the Animation Tool Kit toolbar.

Handles sys.path setup for all tool modules and provides the central TOOL_REGISTRY
that drives toolbar button creation and tool launching.
"""

import os
import sys
import importlib
import importlib.util
import maya.cmds as cmds

try:
    from .atk_window import watch_launch as _watch_launch
except Exception:                       # never let the window fix block a launch
    import contextlib as _contextlib
    _watch_launch = _contextlib.nullcontext

try:
    from . import atk_layout
except ImportError:                     # loaded by file path (tests)
    _layout_spec = importlib.util.spec_from_file_location(
        "atk_layout", os.path.join(os.path.dirname(os.path.abspath(__file__)), "atk_layout.py"))
    atk_layout = importlib.util.module_from_spec(_layout_spec)
    _layout_spec.loader.exec_module(atk_layout)

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
#   extra_modules – (optional) helper modules the tool imports that live
#                   outside its main module/package; purged by Reload Scripts
#   maya_plugin – (optional) Maya plug-in file the tool loads; unloaded and
#                   reloaded by Reload Scripts so plug-in changes take effect
#   startup_fn  – (optional) idempotent service started on toolbar builds
#   palette_colors – (optional) three (label, hex, function) colour strips

TOOL_REGISTRY = [
    {
        "id":        "timeline_ticks",
        "label":     "Timeline Ticks",
        "tooltip":   "Colour timeline ticks and label keys, extremes, breakdowns and inbetweens",
        "module":    "timeline_ticks",
        "launch_fn": "show",
        "icon_file": "timeline_ticks.png",
        "icon_key":  "bookmark",
        "group":     "timing",
        "version":   "1.0.0",
        "startup_fn": "start_tracking",
        "extra_modules": ["timeline_ticks_tracking"],
        "palette_colors": [
            ("Yellow", "#f5cf58", "apply_yellow"),
            ("Red", "#ef6464", "apply_red"),
            ("Blue", "#60a5fa", "apply_blue"),
        ],
        "context_actions": [
            ("Colour Yellow", "apply_yellow"),
            ("Colour Red", "apply_red"),
            ("Colour Blue", "apply_blue"),
            None,
            ("Mark as Key", "mark_key"),
            ("Mark as Extreme", "mark_extreme"),
            ("Mark as Breakdown", "mark_breakdown"),
            ("Mark as Inbetween", "mark_inbetween"),
            None,
            ("Clear Tick Annotations", "clear_ticks"),
            ("Clear All Marks", "clear_all_marks"),
            None,
            ("Hide Coloured Marks", "hide_marks"),
            ("Show Coloured Marks", "show_marks"),
        ],
    },
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
        "version":   "1.0.3",
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
        "version":   "1.0.1",
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
        "tooltip":   "Bake inbetweens, add pinned noise, ease, and one-click shake/skid presets",
        "module":    "noise_generator_1_0_0",
        "launch_fn": "launch",
        "icon_file": "noise_generator_icon.png",
        "icon_key":  "noise",
        "group":     "timing",
        "version":   "1.2.0",
    },
    {
        "id":        "overlap",
        "label":     "Overlap",
        "tooltip":   "Add spring overlap to control animation with axis masks and optimized baking",
        "module":    "atk_overlap",
        "launch_fn": "show",
        "icon_file": "overlap_32.png",
        "icon_key":  "overlap",
        "group":     "timing",
        "version":   "0.5.1",
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
        "version":   "2.0.1",
    },
    {
        "id":        "walk_off_node",
        "label":     "Walk Off Node",
        "tooltip":   "Turn a treadmill walk cycle into a walk that travels off the base node",
        "module":    "walk_off_node",
        "launch_fn": "show",
        "icon_file": "walk_off_node.png",
        "icon_key":  "xform",
        "group":     "timing",
        "version":   "1.0.0",
    },
    {
        "id":        "stagger_keys",
        "label":     "Stagger Keys",
        "tooltip":   "Offset keys across a selection, in selection order, to block in overlap",
        "module":    "stagger_keys",
        "launch_fn": "show",
        "context_actions": [
            ("Stagger +1 Frame",    "stagger_plus_1"),
            ("Stagger +2 Frames",   "stagger_plus_2"),
            ("Stagger -1 Frame",    "stagger_minus_1"),
            None,
            ("Offset All +1 Frame", "offset_plus_1"),
            ("Offset All -1 Frame", "offset_minus_1"),
        ],
        "icon_file": "stagger_keys.png",
        "icon_key":  "stagger",
        "group":     "timing",
        "version":   "1.0.0",
    },
    {
        "id":        "key_cleanup",
        "label":     "Key Cleanup",
        "tooltip":   "Remove redundant keys, static channels, sub-frame keys and Euler flips",
        "module":    "key_cleanup",
        "launch_fn": "show",
        "context_actions": [
            ("Remove Redundant Keys",     "remove_redundant_keys"),
            ("Delete Static Channels",    "delete_static_channels"),
            ("Snap Keys to Whole Frames", "snap_keys_to_frames"),
            ("Euler Filter",              "euler_filter"),
            None,
            ("Run All Passes",            "clean_all"),
        ],
        "icon_file": "key_cleanup.png",
        "icon_key":  "cleanup",
        "group":     "timing",
        "version":   "1.0.0",
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
        "version":   "0.1.1",
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
        "version":   "1.0.1",
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
        "module":    "onion_skin_2_2_0",
        "launch_fn": "launch",
        "icon_file": "onionSkinIcon.png",
        "icon_key":  "onion",
        "group":     "viewport",
        "version":   "2.2.0",
    },
    {
        "id":        "blue_pencil_flipbook",
        "label":     "Blue Pencil Flipbook Manager",
        "tooltip":   "Manage Blue Pencil frames and flipbook playback for drawn animation",
        "module":    "blue_pencil_flipbook.launch",
        "launch_fn": "show",
        "icon_file": "Blue_Pencil.png",
        "icon_key":  "onion",
        "group":     "viewport",
        "version":   "0.2.0",
    },
    {
        "id":        "anim_snap",
        "label":     "AnimSnap",
        "tooltip":   "Snap one object to another using world-space transforms",
        "module":    "anim_snap",
        "launch_fn": "launch",
        # Left-click on the toolbar button snaps immediately (all axes);
        # the full window lives in the right-click menu.
        "quick_fn":  "snap",
        "quick_tip": "Left-click: snap first selected to second (all axes)<br>"
                     "Right-click: open AnimSnap window and more options",
        "context_actions": [
            ("Snap (Translate + Rotate)", "snap"),
            ("Snap Translate Only",       "snap_translate"),
            ("Snap Rotate Only",          "snap_rotate"),
            None,
            ("Setup / Edit Hotkeys...",   "show_hotkey_setup"),
        ],
        "icon_file": "animSnap.png",
        "icon_key":  "snap",
        "group":     "viewport",
        "version":   "1.1.1",
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
        "version":   "2.1.0",
    },
    {
        "id":        "reset",
        "label":     "Reset Tool",
        "tooltip":   "Reset translate, rotate and scale on selected objects",
        "module":    "transform_reset_tool",
        "launch_fn": "show",
        # Left-click on the toolbar button resets all transforms immediately;
        # the full window lives in the right-click menu.
        "quick_fn":  "reset_all",
        "quick_tip": "Left-click: reset all transforms on selection<br>"
                     "Right-click: open Reset Tool window and more options",
        "context_actions": [
            ("Reset All Transforms", "reset_all"),
            ("Reset Translate",      "reset_translate"),
            ("Reset Rotate",         "reset_rotate"),
            ("Reset Scale",          "reset_scale"),
            None,
            ("Setup / Edit Hotkeys...", "show_hotkey_setup"),
        ],
        "icon_file": "reset_icon.png",
        "icon_key":  "reset",
        "group":     "rigging",
        "version":   "2.0.2",
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
        "version":   "2.5.1",
    },
    {
        "id":        "character_snapshot",
        "label":     "Character Snapshot",
        "tooltip":   "Capture rig snapshots used by Mirror Controls and other ATK tools",
        "module":    "character_snapshot_v1_0_0",
        "launch_fn": "show_dialog",
        "icon_file": "snapshot.png",
        "icon_key":  "snap",
        "group":     "rigging",
        "version":   "1.4.0",
    },
    {
        "id":        "mirror_controls",
        "label":     "Mirror Controls",
        "tooltip":   "Mirror, swap or flip rig controls across left and right",
        "module":    "mirror_controls_v2_3_0",
        "launch_fn": "MirrorControls.show_dialog",
        "icon_file": "mirror.png",
        "icon_key":  "mirror",
        "group":     "rigging",
        "version":   "2.3.3",
    },
    {
        "id":        "animation_tweaker",
        "label":     "Animation Tweaker",
        "tooltip":   "Sculpt corrections and polish onto animated meshes after the skin",
        "module":    "atk_tweaker",
        "launch_fn": "show",
        "icon_file": "animation_tweaker_32.png",
        "icon_key":  "tweaker",
        "group":     "rigging",
        "version":   "1.2.1",
        "context_actions": [
            ("Commit Sculpt", "commit_sculpt"),
            ("Cancel Sculpt", "cancel_sculpt"),
            None,
            ("Toggle Smooth Preview", "toggle_smooth_preview"),
            ("Next Camera", "cycle_camera"),
        ],
    },
    {
        "id":        "saveplus",
        "label":     "SavePlus",
        "tooltip":   "Intelligent file versioning and backup for Maya scenes",
        "module":    "savePlus_launcher",
        "launch_fn": "launch_save_plus",
        "extra_modules": ["savePlus_core", "savePlus_main", "savePlus_maya",
                          "savePlus_ui_components"],
        "icon_file": "saveplus.png",
        "icon_key":  "save",
        "group":     "pipeline",
        "version":   "2.0.7",
    },
    {
        "id":        "studio_library",
        "label":     "Studio Library",
        "tooltip":   "Manage poses and animation clips in a visual library",
        "module":    "studiolibrary",
        "launch_fn": "main",
        "extra_modules": ["studiolibrarymaya", "studioqt", "studiovendor", "mutils"],
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
        "extra_modules": ["playblast_creator_presets"],
        "maya_plugin": "playblast_creator.py",
        "icon_file": "playblast_creator_icon.png",
        "icon_key":  "snap",
        "group":     "pipeline",
        "version":   "2.0.6",
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


def _plugin_file(plugin):
    """Full path of a tool's Maya plug-in file shipped by ATK, or None."""
    scripts_dir = cmds.internalVar(userScriptDir=True)
    for folder in (os.path.join(scripts_dir, "playblast_creator", "PBC_v2_0_4"), scripts_dir):
        path = os.path.join(folder, plugin)
        if os.path.isfile(path):
            return path.replace("\\", "/")
    return None


def load_tool_plugins():
    """Load the tools' Maya plug-ins by full path, with Maya auto-load off.

    Maya's own auto-load stores the bare file name and runs before the
    toolbar adds the plug-in folder to MAYA_PLUG_IN_PATH, so it fails at
    every start ("... was not found on MAYA_PLUG_IN_PATH"). Loading here
    keeps scenes that contain the tools' nodes working once the toolbar is
    up, and clears any stale auto-load preference left by older versions.
    """
    for tool in TOOL_REGISTRY:
        plugin = tool.get("maya_plugin")
        if not plugin:
            continue
        try:
            if not _is_plugin_loaded(plugin):
                path = _plugin_file(plugin)
                if path is None:
                    continue
                cmds.loadPlugin(path, quiet=True)
            if cmds.pluginInfo(plugin, query=True, autoload=True):
                cmds.pluginInfo(plugin, edit=True, autoload=False)
        except Exception as exc:
            try:
                cmds.warning("ATK Toolbar: could not load plug-in {}: {}".format(plugin, exc))
            except Exception:
                pass


def start_tool_services():
    """Start idempotent runtime services required by installed toolbar tools."""
    load_tool_plugins()
    for tool in TOOL_REGISTRY:
        if tool.get("startup_fn") and is_tool_installed(tool["id"]):
            launch_tool_fn(tool["id"], tool["startup_fn"], track=False)


# ---------------------------------------------------------------------------
# Tool visibility
# ---------------------------------------------------------------------------

def is_tool_visible(tool_id):
    """Return True if the tool should appear on the toolbar."""
    return tool_id not in get_layout_settings()["hidden"]


def set_tool_visible(tool_id, visible):
    """Show or hide a tool (saved in the layout data)."""
    settings = get_layout_settings()
    hidden = [t for t in settings["hidden"] if t != tool_id]
    if not visible:
        hidden.append(tool_id)
    settings["hidden"] = hidden
    save_layout_settings(settings)


def get_visible_tools():
    """Return the subset of TOOL_REGISTRY entries that should be shown."""
    hidden = set(get_layout_settings()["hidden"])
    return [t for t in TOOL_REGISTRY if t["id"] not in hidden]


# ---------------------------------------------------------------------------
# Layout data and usage counts (versioned JSON optionVars, see atk_layout)
# ---------------------------------------------------------------------------
OPT_LAYOUT = "atk_toolbar_layout"
OPT_USAGE  = "atk_toolbar_usage"


def _legacy_hidden_ids():
    """Tools hidden by the per-tool optionVars ATK used before 1.1.17."""
    hidden = []
    for tool in TOOL_REGISTRY:
        opt = _OPT_HIDDEN_PREFIX + tool["id"]
        try:
            if cmds.optionVar(exists=opt) and bool(cmds.optionVar(q=opt)):
                hidden.append(tool["id"])
        except Exception:
            pass
    return hidden


def _read_string_var(key):
    """The optionVar's string value, None when it does not exist."""
    try:
        if not cmds.optionVar(exists=key):
            return None
        value = cmds.optionVar(q=key)
    except Exception:
        return None
    return value if isinstance(value, str) else ""


def get_layout_settings():
    """The toolbar layout settings (defaults when missing or unreadable).

    On first use the old ``atk_hidden_<id>`` preferences are migrated.
    """
    raw = _read_string_var(OPT_LAYOUT)
    legacy = _legacy_hidden_ids() if raw is None else ()
    return atk_layout.load_settings(raw, TOOL_REGISTRY, legacy, GROUP_ORDER)


def save_layout_settings(settings):
    """Store the layout settings.

    The hidden tools are also written to the old per-tool optionVars, so
    going back to an older ATK still hides the same tools.
    """
    settings = atk_layout.normalize_settings(settings, TOOL_REGISTRY, GROUP_ORDER)
    cmds.optionVar(sv=(OPT_LAYOUT, atk_layout.encode_settings(settings)))
    hidden = set(settings["hidden"])
    for tool in TOOL_REGISTRY:
        cmds.optionVar(iv=(_OPT_HIDDEN_PREFIX + tool["id"], 1 if tool["id"] in hidden else 0))
    return settings


def reset_layout_settings():
    """Back to the default Full layout with every tool shown."""
    return save_layout_settings(atk_layout.default_settings(TOOL_REGISTRY, GROUP_ORDER))


def get_usage():
    """Launch counts per tool id."""
    return atk_layout.decode_usage(_read_string_var(OPT_USAGE))


def record_usage(tool_id):
    """Count one launch of a tool.  Never raises."""
    try:
        if _tool_by_id(tool_id) is None:
            return
        counts = atk_layout.bump_usage(get_usage(), tool_id)
        cmds.optionVar(sv=(OPT_USAGE, atk_layout.encode_usage(counts)))
    except Exception:
        pass


def reset_usage():
    """Forget every launch count."""
    cmds.optionVar(sv=(OPT_USAGE, atk_layout.encode_usage({})))


# ---------------------------------------------------------------------------
# Tool launching
# ---------------------------------------------------------------------------

def launch_tool(tool_id, track=True):
    """Import the tool module and call its launch function.

    Errors are caught and reported via cmds.warning so the toolbar stays alive
    even if an individual tool fails to load.
    """
    launch_tool_fn(tool_id, track=track)


def launch_tool_fn(tool_id, fn_name=None, track=True):
    """Import a tool module and call a named function on it.

    ``fn_name`` defaults to the tool's registered ``launch_fn``.  Used by the
    toolbar for quick-action buttons and context-menu actions (e.g. AnimSnap's
    left-click snap) that call functions other than the window launcher.

    Every call counts as one use of the tool for the Most used layout,
    unless ``track`` is False (startup services, reopening after a reload).

    Errors are caught and reported via cmds.warning so the toolbar stays alive
    even if an individual tool fails to load.
    """
    tool = _tool_by_id(tool_id)
    if tool is None:
        cmds.warning("ATK Toolbar: unknown tool id '{}'".format(tool_id))
        return
    if track:
        record_usage(tool_id)

    module_name = tool["module"]
    if fn_name is None:
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

        # Watch the windows the launcher opens so their minimized title bars
        # line up at the bottom of the screen instead of floating over Maya
        # (see atk_window.py).
        with _watch_launch():
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


# ---------------------------------------------------------------------------
# Script reloading
# ---------------------------------------------------------------------------

def tool_module_roots():
    """Map each top-level module a tool owns to that tool's id.

    Helper modules (e.g. playblast_creator_presets, savePlus_core, Studio
    Library's mutils/studioqt) are included: Reload Scripts must purge them
    too, otherwise the fresh tool module re-imports the stale cached helpers.
    """
    roots = {}
    for tool in TOOL_REGISTRY:
        for name in [tool["module"]] + list(tool.get("extra_modules", ())):
            roots.setdefault(name.split(".")[0], tool["id"])
    return roots


def shutdown_tool_modules():
    """Call ``shutdown()`` on every loaded tool module that defines one.

    Used before Reload Scripts purges the modules and when Maya quits, so
    tools release Maya callbacks, event filters on Maya widgets and Python
    owned Qt objects while Python and Qt are still running. Returns the
    names of the modules that were shut down.
    """
    names = []
    for tool in TOOL_REGISTRY:
        for name in [tool["module"]] + list(tool.get("extra_modules", ())):
            for candidate in (name, name.split(".")[0]):
                if candidate not in names:
                    names.append(candidate)
    done = []
    for name in names:
        module = sys.modules.get(name)
        shutdown = getattr(module, "shutdown", None)
        if not callable(shutdown):
            continue
        try:
            shutdown()
            done.append(name)
        except Exception as exc:
            try:
                cmds.warning("ATK Toolbar: {} shutdown failed: {}".format(name, exc))
            except Exception:
                pass
    return done


def purge_toolbar_modules():
    """Drop the atk_toolbar package itself from ``sys.modules``.

    The caller must then import ``atk_toolbar.atk_toolbar`` afresh and call
    its ``show()`` so the toolbar, registry, icons and settings dialog run
    the newly installed code (this is what the installer does as well).
    """
    root = __name__.split(".")[0]
    for name in list(sys.modules):
        if name == root or name.startswith(root + "."):
            del sys.modules[name]
    importlib.invalidate_caches()


def reload_tool_modules():
    """Purge every tool module from ``sys.modules`` so the next launch
    re-imports the latest installed scripts, and reload tool Maya plug-ins —
    no Maya restart needed after updating or reinstalling tools.

    Already-open tool windows keep running on the old code; relaunch a tool
    from the toolbar to get the reloaded version.

    Returns ``(purged, plugin_notes)``: the sorted top-level module names that
    were purged, and one message per plug-in that could not be reloaded.
    """
    # Pick up any directories created by a fresh install and make sure
    # cached import metadata doesn't shadow newly copied files.
    setup_paths()
    importlib.invalidate_caches()

    shutdown_tool_modules()

    purged = set()
    for root in tool_module_roots():
        prefix = root + "."
        for name in list(sys.modules):
            if name == root or name.startswith(prefix):
                del sys.modules[name]
                purged.add(root)

    plugin_notes = []
    for tool in TOOL_REGISTRY:
        plugin = tool.get("maya_plugin")
        if plugin:
            note = _reload_maya_plugin(plugin)
            if note:
                plugin_notes.append("{}: {}".format(tool["label"], note))

    return sorted(purged), plugin_notes


def _is_plugin_loaded(plugin):
    for name in (plugin, os.path.splitext(plugin)[0]):
        try:
            if cmds.pluginInfo(name, q=True, loaded=True):
                return True
        except Exception:
            pass
    return False


def _reload_maya_plugin(plugin):
    """Unload and reload a Python Maya plug-in so edits to it take effect.

    Maya keeps a loaded plug-in's code in memory, so purging ``sys.modules``
    alone never picks up plug-in changes. A plug-in whose node types exist
    in the open scene cannot be unloaded without losing those nodes, so it
    is left alone. Returns a message when the plug-in was not reloaded,
    otherwise None.
    """
    if not _is_plugin_loaded(plugin):
        return None  # Loads fresh from disk the next time the tool starts.

    try:
        path = cmds.pluginInfo(plugin, q=True, path=True)
    except Exception:
        path = plugin

    try:
        node_types = cmds.pluginInfo(plugin, q=True, dependNode=True) or []
    except Exception:
        node_types = []
    in_scene = [t for t in node_types if cmds.ls(type=t)]
    if in_scene:
        return ("plug-in not reloaded because the scene contains {} node(s). "
                "Delete them or restart Maya to load the new plug-in.".format(
                    ", ".join(in_scene)))

    try:
        cmds.unloadPlugin(os.path.basename(path))
    except Exception as exc:
        return "could not unload plug-in ({}). Restart Maya to reload it.".format(exc)

    try:
        cmds.loadPlugin(path, quiet=True)
    except Exception as exc:
        return "unloaded but failed to reload plug-in ({}). It will reload when the tool is next launched.".format(exc)
    return None
