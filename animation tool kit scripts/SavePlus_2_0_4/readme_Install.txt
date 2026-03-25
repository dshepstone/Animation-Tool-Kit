SavePlus Installation Guide (v2.0.4)
=====================================

Overview
--------
SavePlus is a Maya file versioning and project management tool. It provides
automatic version incrementing, backup creation, version notes, project scene
browsing, and project-aware save paths.


System Requirements
-------------------
- Autodesk Maya 2025 (primary support; Maya 2023/2024 may work with limited features)
- PySide6 (included with Maya 2025)
- Windows 10/11 / macOS 12+ / Linux (CentOS/Rocky 8.6+)
- Python support enabled in Maya (default)


=======================================================================
METHOD 1 — Quick Install (Drag & Drop .mel file)
=======================================================================

1) Download and extract SavePlus_v2.0.4.zip.
2) Open Maya 2025.
3) Drag install_saveplus.mel into the Maya viewport.
4) Accept the install prompt.
5) A SavePlus shelf button is created on your current shelf (duplicates are
   detected and updated in place rather than added again).
6) (Optional) Launch immediately when prompted.

If the drag-and-drop does not trigger the installer, see Method 2 or 3 below.


=======================================================================
METHOD 2 — Run the .mel File from the Script Editor
=======================================================================
Use this if dragging the .mel file into the viewport does nothing.

1) Open the Maya Script Editor  (Window > General Editors > Script Editor).
2) Set the tab language to MEL.
3) Paste the following command, replacing the path with the actual location
   of install_saveplus.mel on your system:

   source "C:/path/to/install_saveplus.mel";

   macOS / Linux example:
   source "/Users/yourname/Downloads/savePlus/src/install_saveplus.mel";

4) Press Ctrl+Enter (or the Execute All button) to run.
5) Accept the install prompt. A shelf button will be created.


=======================================================================
METHOD 3 — Full Manual Install (no .mel file needed)
=======================================================================
Use this if both Methods 1 and 2 fail, or if you prefer to install manually.

STEP 1 — Find your Maya scripts directory
------------------------------------------
In Maya's Script Editor (Python tab), run the following to print your exact
scripts directory path:

   import maya.cmds as cmds
   print(cmds.internalVar(userScriptDir=True))
   print(cmds.internalVar(userPrefsDir=True))

Common default locations (your system may differ):
  Windows:  C:/Users/<username>/Documents/maya/scripts/
  macOS:    /Users/<username>/Library/Preferences/Autodesk/maya/scripts/
  Linux:    /home/<username>/maya/scripts/

Common default prefs/icons locations:
  Windows:  C:/Users/<username>/Documents/maya/prefs/icons/
  macOS:    /Users/<username>/Library/Preferences/Autodesk/maya/prefs/icons/
  Linux:    /home/<username>/maya/prefs/icons/

NOTE: Run the cmds.internalVar() commands above to get the real paths on
your machine — especially if Maya is installed on a non-standard drive or
in a custom directory.

STEP 2 — Copy the script files
--------------------------------
Copy ALL of the following files from the SavePlus src/ folder into your
Maya scripts directory found in Step 1:

   __init__.py
   savePlus_core.py
   savePlus_maya.py
   savePlus_ui_components.py
   savePlus_main.py
   savePlus_launcher.py

STEP 3 — Copy the icon (optional)
-----------------------------------
Copy  icons/saveplus.png  from the SavePlus folder into your Maya
prefs/icons directory found in Step 1. If this folder does not exist,
create it. If you skip this step, Maya's default icon will be used instead.

STEP 4 — Launch SavePlus from the Script Editor
-------------------------------------------------
Once the files are copied, open the Maya Script Editor, set the tab to
Python, paste the Dynamic Launch Command below, and press Ctrl+Enter.


=======================================================================
DYNAMIC LAUNCH COMMAND (Script Editor — Python tab)
=======================================================================
This command can be pasted into Maya's Script Editor at any time to launch
SavePlus. It dynamically locates your scripts directory, reloads all
SavePlus modules so the latest saved version is always used, and then
opens the tool — no Maya restart required.

----------------------------------------------------------------------
import importlib
import sys
import maya.cmds as cmds

# Dynamically resolve the scripts directory for this machine
scriptsDir = cmds.internalVar(userScriptDir=True)
if scriptsDir not in sys.path:
    sys.path.insert(0, scriptsDir)

# Reload all SavePlus modules so any file updates take effect
# without needing to restart Maya.
for _mod in ['savePlus_maya', 'savePlus_core', 'savePlus_ui_components',
             'savePlus_main', 'savePlus_launcher']:
    if _mod in sys.modules:
        try:
            importlib.reload(sys.modules[_mod])
        except Exception as _e:
            print('SavePlus: warning reloading {}: {}'.format(_mod, _e))

try:
    import savePlus_launcher
    savePlus_launcher.launch_save_plus()
except Exception as e:
    cmds.warning('Error launching SavePlus: {}'.format(str(e)))
    raise
----------------------------------------------------------------------

TIP: Save this command as a custom shelf button for quick access:
  1) Select the command text above.
  2) In the Script Editor, go to File > Save Script to Shelf.
  3) Name it "SavePlus" and assign the saveplus.png icon if desired.


=======================================================================
CREATING THE SHELF BUTTON MANUALLY
=======================================================================
If you installed manually (Method 3) and want a shelf button, run the
following once in the Script Editor (Python tab) after Step 4 above:

   import savePlus_launcher
   savePlus_launcher.install_shelf_button()

This creates the shelf button on your active shelf.


=======================================================================
UPDATING SAVEPLUS
=======================================================================
- Drag-and-drop: Re-run the .mel installer. It detects the existing shelf
  button and updates it in place rather than creating a duplicate.
- Manual update: Overwrite the .py files in your Maya scripts directory
  with the new versions. The Dynamic Launch Command above will pick up
  the new code automatically on the next run.


=======================================================================
KEY FEATURES
=======================================================================
- Versioned Save:   Increments filenames automatically (e.g., _v01 -> _v02).
- Backups:          Optional timed backups with configurable retention.
- Version Notes:    Attach notes per save and review them later.
- Project Support:  Set Maya projects, browse project scenes, open directly.
- History:          Browse recent files and version history with notes.
- Compact Name Mode: Name Generator shortens filenames for cloud storage
                    and Windows path-length limits (target: under 64 chars).
- Hot Reload:       Shelf button reloads all modules on every click so file
                    changes take effect without restarting Maya.
- Docked Panel Scroll: Project and History tabs are fully scrollable when
                    docked at reduced height.


=======================================================================
TROUBLESHOOTING
=======================================================================
- .mel drag-and-drop does nothing:
    Use Method 2 (source the .mel via Script Editor) or Method 3 (manual).

- "No module named savePlus_launcher" error:
    The .py files are not in your Maya scripts directory. Re-check Step 1
    and Step 2 of Method 3 using the cmds.internalVar() output.

- UI does not open / Python error:
    Open the Script Editor and check the output tab for the full traceback.

- Wrong icons directory / icon not showing:
    Run  cmds.internalVar(userPrefsDir=True)  to find the correct path and
    place saveplus.png in the icons/ subfolder of that directory.

- Non-standard Maya installation path:
    Always use cmds.internalVar() to find paths rather than relying on the
    defaults listed above. SavePlus resolves all paths dynamically at runtime.


=======================================================================
DOWNLOAD
=======================================================================
ZIP: https://github.com/dshepstone/savePlus/releases/download/latest_release/SavePlus_v2.0.4.zip


=======================================================================
SUPPORT
=======================================================================
Check the Maya Script Editor output for error details.
Issues: https://github.com/dshepstone/savePlus/issues
