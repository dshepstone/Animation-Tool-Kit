"""Playblast Creator v2.0.4 installer.

Executed by install_playblast_creator_v2_0_4.mel when dragged into Maya.
"""

import os
import shutil
import sys

import maya.cmds as cmds
import maya.mel as mel


VERSION_FOLDER = "PBC_v2_0_4"
TOOL_FOLDER = "playblast_creator"
ICON_NAME = "playblast_creator_icon.png"

REQUIRED_FILES = [
    "playblast_creator.py",
    "playblast_creator_ui.py",
    "playblast_creator_presets.py",
]


def _resolve_source_dir(source_dir):
    if source_dir:
        return os.path.normpath(source_dir)
    return os.path.dirname(os.path.abspath(__file__))


def _copy_required_files(source_dir, install_root):
    missing = [
        filename for filename in REQUIRED_FILES
        if not os.path.exists(os.path.join(source_dir, filename))
    ]
    if missing:
        raise RuntimeError(
            "[Playblast Creator] Missing required files: {0}".format(", ".join(missing))
        )

    os.makedirs(install_root, exist_ok=True)

    for filename in REQUIRED_FILES:
        shutil.copy2(os.path.join(source_dir, filename), os.path.join(install_root, filename))


def _install_icon(source_dir, icons_dir):
    package_root = os.path.dirname(source_dir)
    source_icon = os.path.join(package_root, ICON_NAME)
    if not os.path.exists(source_icon):
        print("[Playblast Creator] Icon not found: {0}".format(source_icon))
        return ""

    os.makedirs(icons_dir, exist_ok=True)
    target_icon = os.path.join(icons_dir, ICON_NAME)
    shutil.copy2(source_icon, target_icon)
    return target_icon


def _write_launcher(scripts_dir):
    launcher_root = os.path.join(scripts_dir, TOOL_FOLDER)
    os.makedirs(launcher_root, exist_ok=True)
    launcher_path = os.path.join(launcher_root, "playblast_creator_latest.py")

    launcher_source = (
        "import os\n"
        "import sys\n"
        "import importlib\n"
        "import maya.cmds as cmds\n\n"
        "root = os.path.join(cmds.internalVar(userAppDir=True), 'scripts', 'playblast_creator', 'PBC_v2_0_4')\n"
        "if root not in sys.path:\n"
        "    sys.path.insert(0, root)\n\n"
        "def launch():\n"
        "    module = importlib.import_module('playblast_creator_ui')\n"
        "    importlib.reload(module)\n"
        "    if hasattr(module, 'show_ui'):\n"
        "        return module.show_ui()\n"
        "    if hasattr(module, 'show_playblast_dialog'):\n"
        "        return module.show_playblast_dialog()\n"
        "    raise RuntimeError('No UI entry point found in playblast_creator_ui.py')\n"
    )

    with open(launcher_path, "w") as launcher_file:
        launcher_file.write(launcher_source)


def _add_shelf_button(icon_path):
    try:
        shelf_top_level = mel.eval('$tmp = $gShelfTopLevel')
        if not shelf_top_level:
            print("[Playblast Creator] Shelf layout not available. Skipping shelf button creation.")
            return

        current_shelf = cmds.tabLayout(shelf_top_level, q=True, selectTab=True)
        if not current_shelf:
            print("[Playblast Creator] No active shelf tab. Skipping shelf button creation.")
            return

        existing_buttons = cmds.shelfLayout(current_shelf, q=True, childArray=True) or []
        for button in existing_buttons:
            if cmds.objectTypeUI(button) == "shelfButton":
                cmd = cmds.shelfButton(button, q=True, command=True) or ""
                if "playblast_creator_latest" in cmd:
                    cmds.deleteUI(button)

        shelf_command = (
            "import os, runpy, maya.cmds as cmds\n"
            "launcher = os.path.join(cmds.internalVar(userAppDir=True), 'scripts', 'playblast_creator', 'playblast_creator_latest.py')\n"
            "globals_dict = runpy.run_path(launcher)\n"
            "globals_dict['launch']()"
        )

        image_name = os.path.basename(icon_path) if icon_path else "commandButton.png"

        cmds.shelfButton(
            parent=current_shelf,
            label="Playblast",
            annotation="Launch Playblast Creator",
            image1=image_name,
            imageOverlayLabel="",
            command=shelf_command,
            sourceType="python",
        )

    except Exception as exc:
        print("[Playblast Creator] Failed to create shelf button: {0}".format(exc))


def install(source_dir=None):
    source_dir = _resolve_source_dir(source_dir)

    maya_app_dir = os.path.normpath(cmds.internalVar(userAppDir=True))
    scripts_dir = os.path.join(maya_app_dir, "scripts")
    icons_dir = os.path.join(maya_app_dir, "prefs", "icons")
    install_root = os.path.join(scripts_dir, TOOL_FOLDER, VERSION_FOLDER)

    _copy_required_files(source_dir, install_root)
    icon_path = _install_icon(source_dir, icons_dir)
    _write_launcher(scripts_dir)
    _add_shelf_button(icon_path)

    message = "Installation complete.\nInstalled to:\n{0}".format(install_root)
    cmds.confirmDialog(title="Playblast Creator", message=message, button=["OK"])
    print("[Playblast Creator] Installed v2.0.4 to: {0}".format(install_root))


if __name__ == "__main__":
    passed_source_dir = None
    if len(sys.argv) > 1:
        passed_source_dir = sys.argv[1]
    install(source_dir=passed_source_dir)
