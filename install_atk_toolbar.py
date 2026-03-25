"""ATK Toolbar Installer — called by install_atk_toolbar.mel.

Steps:
  1. Determine the source directory (where this file lives).
  2. Copy the entire atk_toolbar/ package to Maya's userScriptDir.
  3. Copy all tool icons to Maya's userBitmapsDir (if not already present).
  4. Add userScriptDir to sys.path.
  5. Create (or update) a single ATK shelf button on the current shelf.
  6. Launch the toolbar immediately.

This script is intentionally self-contained so it can also be run directly
from Maya's Script Editor for development purposes:
    exec(open(r"/path/to/install_atk_toolbar.py").read())
"""

import os
import sys
import shutil
import maya.cmds as cmds
import maya.mel as mel

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ensure_dir(path):
    if not os.path.isdir(path):
        os.makedirs(path)


def _copy_file(src, dst):
    """Copy src → dst, creating parent dirs as needed. Returns True on success."""
    if not os.path.isfile(src):
        cmds.warning("ATK Installer: source file not found: {}".format(src))
        return False
    _ensure_dir(os.path.dirname(dst))
    try:
        shutil.copy2(src, dst)
        print("  Copied: {}".format(os.path.basename(src)))
        return True
    except Exception as exc:
        cmds.warning("ATK Installer: failed to copy {} → {}: {}".format(src, dst, exc))
        return False


def _copy_dir(src_dir, dst_dir):
    """Recursively copy all .py files from src_dir to dst_dir."""
    _ensure_dir(dst_dir)
    ok = True
    for name in os.listdir(src_dir):
        if name.endswith(".py"):
            ok = _copy_file(os.path.join(src_dir, name),
                            os.path.join(dst_dir, name)) and ok
    return ok


def _remove_existing_atk_buttons(shelf):
    """Delete any previous ATK toolbar shelf buttons."""
    buttons = cmds.shelfLayout(shelf, query=True, childArray=True) or []
    for btn in buttons:
        if not cmds.shelfButton(btn, exists=True):
            continue
        try:
            annotation = cmds.shelfButton(btn, query=True, annotation=True) or ""
            if "ATK_TOOLBAR_SHELF_BUTTON" in annotation:
                cmds.deleteUI(btn)
                print("  Removed existing ATK shelf button.")
        except Exception:
            pass


def _create_shelf_button(shelf, icon_path):
    """Create the ATK toolbar shelf button on *shelf*."""
    # Use just the basename so Maya searches XBMLANGPATH (includes userBitmapsDir)
    icon_name = os.path.basename(icon_path) if os.path.isfile(icon_path) else "commandButton.png"

    button_cmd = (
        "import sys, maya.cmds as cmds\n"
        "scripts_dir = cmds.internalVar(userScriptDir=True)\n"
        "if scripts_dir not in sys.path:\n"
        "    sys.path.insert(0, scripts_dir)\n"
        "import atk_toolbar\n"
        "atk_toolbar.show()\n"
    )

    cmds.shelfButton(
        parent=shelf,
        label="ATK",
        annotation="ATK_TOOLBAR_SHELF_BUTTON — Animation Tool Kit Toolbar",
        image=icon_name,
        image1=icon_name,
        sourceType="python",
        command=button_cmd,
        doubleClickCommand=(
            "import importlib, sys, maya.cmds as cmds\n"
            "scripts_dir = cmds.internalVar(userScriptDir=True)\n"
            "if scripts_dir not in sys.path:\n"
            "    sys.path.insert(0, scripts_dir)\n"
            "import atk_toolbar, atk_toolbar.atk_toolbar, "
            "atk_toolbar.atk_loader, atk_toolbar.atk_icons, atk_toolbar.atk_settings\n"
            "for m in ['atk_toolbar.atk_loader', 'atk_toolbar.atk_icons',\n"
            "          'atk_toolbar.atk_settings', 'atk_toolbar.atk_toolbar',\n"
            "          'atk_toolbar']:\n"
            "    if m in sys.modules:\n"
            "        importlib.reload(sys.modules[m])\n"
            "atk_toolbar.show()\n"
        ),
    )
    print("  Created ATK shelf button on shelf: {}".format(shelf))


# ---------------------------------------------------------------------------
# Icon constants — all existing tool icons to copy
# ---------------------------------------------------------------------------
_TOOL_ICONS = [
    # (relative path from source_dir, target basename in userBitmapsDir)
    ("Temp_Pivot_Tool_1_0_5/temp-pivot.png",              "temp-pivot.png"),
    ("inbetweener_2_0_1/inbetweener.png",                 "inbetweener.png"),
    ("inbetweener_2_0_1/defaultPose.png",                 "defaultPose.png"),
    ("Add-Remove-Inbetweens_1_0_1/add-remove.png",        "add-remove.png"),
    ("noise_generator_1_0_0/noise_generator_icon.png",    "noise_generator_icon.png"),
    ("onion-skin-tool_2_1_0/onionSkinIcon.png",           "onionSkinIcon.png"),
    ("WireShape_Tool_1_0_0/Shape_Icon.png",               "Shape_Icon.png"),
    ("Reset_Tool_2_0_1/reset_icon.png",                   "reset_icon.png"),
    ("SavePlus_2_0_4/icons/saveplus.png",                 "saveplus.png"),
]

# The icon to use for the ATK shelf button itself
_ATK_SHELF_ICON_SRC = None   # we'll use the inbetweener icon as placeholder


# ---------------------------------------------------------------------------
# Main install
# ---------------------------------------------------------------------------

def install(source_dir=None):
    """Run the full installation.

    Parameters
    ----------
    source_dir : str, optional
        Directory containing the ``atk_toolbar/`` package and this file.
        Defaults to the directory of this script.
    """
    if source_dir is None:
        source_dir = os.path.dirname(os.path.abspath(__file__))

    print("\n" + "=" * 60)
    print("  Animation Tool Kit Toolbar Installer v1.0.0")
    print("=" * 60)
    print("Source: {}\n".format(source_dir))

    scripts_dir  = cmds.internalVar(userScriptDir=True).rstrip("/\\")
    bitmaps_dir  = cmds.internalVar(userBitmapsDir=True).rstrip("/\\")

    # -- 1. Copy atk_toolbar package --------------------------------------
    print("Copying toolbar package files:")
    src_pkg = os.path.join(source_dir, "atk_toolbar")
    dst_pkg = os.path.join(scripts_dir, "atk_toolbar")

    if not os.path.isdir(src_pkg):
        cmds.confirmDialog(
            title="ATK Install Failed",
            message="Cannot find 'atk_toolbar/' folder next to the installer.\n"
                    "Make sure all files were extracted together.",
            button=["OK"],
        )
        return False

    if not _copy_dir(src_pkg, dst_pkg):
        cmds.confirmDialog(
            title="ATK Install Failed",
            message="Failed to copy toolbar package. See Script Editor for details.",
            button=["OK"],
        )
        return False

    # -- 2. Copy tool icons -----------------------------------------------
    print("\nCopying tool icons:")
    _ensure_dir(bitmaps_dir)
    for rel_src, basename in _TOOL_ICONS:
        src_icon = os.path.join(source_dir, rel_src)
        dst_icon = os.path.join(bitmaps_dir, basename)
        if not os.path.isfile(dst_icon):   # don't overwrite if already installed
            _copy_file(src_icon, dst_icon)
        else:
            print("  Skipped (already present): {}".format(basename))

    # -- 3. sys.path ------------------------------------------------------
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)

    # -- 4. Shelf button --------------------------------------------------
    print("\nCreating shelf button:")
    try:
        shelf_top = mel.eval("$__tmp = $gShelfTopLevel")
        current_shelf = cmds.tabLayout(shelf_top, query=True, selectTab=True)
        _remove_existing_atk_buttons(current_shelf)

        # Try to use the inbetweener icon for the shelf button
        atk_icon_path = os.path.join(bitmaps_dir, "inbetweener.png")
        _create_shelf_button(current_shelf, atk_icon_path)
    except Exception as exc:
        cmds.warning("ATK Installer: could not create shelf button: {}".format(exc))

    # -- 5. Launch --------------------------------------------------------
    print("\nLaunching toolbar...")
    try:
        import atk_toolbar
        atk_toolbar.show()
    except Exception as exc:
        cmds.warning("ATK Installer: toolbar launched with warnings: {}".format(exc))

    print("\n" + "=" * 60)
    print("  Installation Complete!")
    print("=" * 60)
    print("\nFiles installed to:")
    print("  Package:  {}".format(dst_pkg))
    print("  Icons:    {}".format(bitmaps_dir))
    print("\nTo launch: click the ATK button on your shelf")
    print("        or: import atk_toolbar; atk_toolbar.show()\n")
    return True


# Run immediately when executed via Maya's python() command or exec()
if __name__ == "__main__":
    install()
