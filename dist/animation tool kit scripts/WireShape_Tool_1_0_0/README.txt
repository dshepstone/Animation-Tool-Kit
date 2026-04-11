================================================================
  WIRE SHAPE TOOL FOR MAYA — README
  Rig Control Curve Creator | Maya 2022–2026
================================================================

WHAT IS THIS TOOL?
------------------
Wire Shape Tool is a Maya UI panel for quickly creating curve-based
rig control shapes. It includes MEL-sourced classic Comet shapes
(arrow, circle, cube, orient, locator, etc.) and additional Python
shapes (Circle 4-Arrow, Double Arrow, Star, Diamond, Pyramid,
Capsule, and more).

Shapes snap to any selected object and are named with a _CTRL suffix
ready to use as rig controls.


================================================================
  FILES INCLUDED IN THIS PACKAGE
================================================================

  install_wire_shape_tool.mel   ← Drag-and-drop installer (this runs the install)
  wire_shape_tool.py            ← The main tool script
  Shape_Icon.png                ← Shelf button icon
  README.txt                    ← This file

ALL FOUR FILES must be kept in the same folder before installing.


================================================================
  OPTION A — DRAG AND DROP INSTALL (Recommended)
================================================================

1. Extract / place all four files into the same folder on your
   computer (e.g. Desktop, Downloads — anywhere is fine).

2. Open Maya.

3. Open a viewport panel (Perspective, Top, etc.).

4. Drag  install_wire_shape_tool.mel  from Windows Explorer
   or macOS Finder directly onto the Maya viewport.

5. Maya will:
     • Copy  wire_shape_tool.py  →  your Maya scripts folder
     • Copy  Shape_Icon.png      →  your Maya icons folder
     • Add a shelf button to the "Custom" shelf

6. A confirmation dialog will appear when install is complete.

7. Click the shelf button (compass icon) to launch the tool.

That's it — you're done!


================================================================
  OPTION B — MANUAL INSTALL
================================================================

If you prefer to install by hand, copy the files yourself:

  1. Copy  wire_shape_tool.py  to your Maya scripts folder:

       Windows:  C:\Users\<YourName>\Documents\maya\<version>\scripts\
       macOS:    ~/Library/Preferences/Autodesk/maya/<version>/scripts/
       Linux:    ~/maya/<version>/scripts/

  2. Copy  Shape_Icon.png  to your Maya icons folder:

       Windows:  C:\Users\<YourName>\Documents\maya\<version>\prefs\icons\
       macOS:    ~/Library/Preferences/Autodesk/maya/<version>/prefs/icons/
       Linux:    ~/maya/<version>/prefs/icons/

  3. In Maya's Script Editor (Python tab), paste and run:

       import sys, importlib
       import maya.cmds as cmds

       scripts_dir = cmds.internalVar(userScriptDir=True)
       if scripts_dir not in sys.path:
           sys.path.insert(0, scripts_dir)

       import wire_shape_tool
       importlib.reload(wire_shape_tool)
       wire_shape_tool.show()

  4. To make a shelf button manually:
       • Run the command above in the Script Editor
       • Middle-mouse drag the tab from the Script Editor
         input area onto any shelf


================================================================
  LAUNCHING THE TOOL AFTER INSTALL
================================================================

  • Click the shelf button (compass icon) on the "Custom" shelf, OR

  • Run in the Script Editor (Python tab):

      import sys, importlib
      import maya.cmds as cmds

      scripts_dir = cmds.internalVar(userScriptDir=True)
      if scripts_dir not in sys.path:
          sys.path.insert(0, scripts_dir)

      import wire_shape_tool
      importlib.reload(wire_shape_tool)
      wire_shape_tool.show()


================================================================
  USING THE TOOL
================================================================

  • MEL Shapes tab   — Classic wireShape.mel controls (arrow,
                       circle, cube, orient, locator, etc.)

  • Extra Shapes tab — Python curve shapes (Circle 4-Arrow,
                       Double Arrow, Star, Diamond, Pyramid,
                       Capsule, 4-Way Arrow)

  Snap to Selection  — When checked, the created control moves
                       to the pivot of your current selection
                       automatically.

  Search box         — Filter shapes by name in real time.

  All shapes are created at the world origin (or snapped to
  selection) and named with a _CTRL suffix.


================================================================
  COMPATIBILITY
================================================================

  Maya 2022    PySide2 / Qt5
  Maya 2023    PySide2 / Qt5
  Maya 2024    PySide2 / Qt5
  Maya 2025    PySide2 / Qt5
  Maya 2026    PySide6 / Qt6   ← Primary target

  The script auto-detects Qt version at load time.


================================================================
  TROUBLESHOOTING
================================================================

  "No module named 'wire_shape_tool'"
    → The .py file is not in your scripts folder.
      Re-run the installer or copy it manually (see Option B).

  Shelf button shows no icon
    → Shape_Icon.png was not found during install.
      Copy it manually to your Maya prefs/icons/ folder.

  Install dialog does not appear
    → Make sure all four files are in the same folder before
      dragging the .mel file onto the viewport.

  Tool opens but shapes don't snap
    → Ensure "Snap to Selection" is checked in the tool header.


================================================================
  UNINSTALL
================================================================

  1. Delete  wire_shape_tool.py  from your scripts folder.
  2. Delete  Shape_Icon.png  from your icons folder.
  3. Right-click the shelf button → Delete Button.


================================================================
