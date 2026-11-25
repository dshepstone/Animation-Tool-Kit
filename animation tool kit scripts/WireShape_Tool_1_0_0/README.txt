================================================================
  WIRE SHAPE TOOL FOR MAYA - README
  Rig Control Curve Creator | Maya 2022-2026
================================================================

WHAT IS THIS TOOL?
------------------
Wire Shape Tool is a Maya UI panel for quickly creating curve-based
rig control shapes, organised into categories:

  Primitives          - circles, square, cube, sphere, diamonds,
                        triangle, hexagon, star, pyramid, capsule,
                        half circle, plus, cross
  Arrows & Direction  - arrow, double arrow, 4-way arrow,
                        circle 4-arrow, curved arrow, spin arrows,
                        orient
  Rig Controls        - root, gear, pole vector, lollipop, paddle,
                        foot, eye target, flag
  Utility             - null/group, locator, joint, bulb

It also builds an Offset Dummy: a locator-style gizmo control wrapped
in any number of offset groups (name_ZERO > name_OFS1... > name_CTRL)
for use as a clean null, constraint target or layered offset, plus a
helper that wraps existing objects in matched offset groups.

Shapes snap to any selected object and are named with a _CTRL suffix
ready to use as rig controls.


================================================================
  FILES INCLUDED IN THIS PACKAGE
================================================================

  install_wire_shape_tool.mel   <- Drag-and-drop installer (this runs the install)
  wire_shape_tool.py            <- The main tool script
  Shape_Icon.png                <- Shelf button icon
  README.txt                    <- This file

ALL FOUR FILES must be kept in the same folder before installing.


================================================================
  OPTION A - DRAG AND DROP INSTALL (Recommended)
================================================================

1. Extract / place all four files into the same folder on your
   computer (e.g. Desktop, Downloads - anywhere is fine).

2. Open Maya.

3. Open a viewport panel (Perspective, Top, etc.).

4. Drag  install_wire_shape_tool.mel  from Windows Explorer
   or macOS Finder directly onto the Maya viewport.

5. Maya will:
     - Copy  wire_shape_tool.py  ->  your Maya scripts folder
     - Copy  Shape_Icon.png      ->  your Maya icons folder
     - Add a shelf button to the "Custom" shelf

6. A confirmation dialog will appear when install is complete.

7. Click the shelf button (compass icon) to launch the tool.

That's it - you're done!


================================================================
  OPTION B - MANUAL INSTALL
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
       - Run the command above in the Script Editor
       - Middle-mouse drag the tab from the Script Editor
         input area onto any shelf


================================================================
  LAUNCHING THE TOOL AFTER INSTALL
================================================================

  - Click the shelf button (compass icon) on the "Custom" shelf, OR

  - Run in the Script Editor (Python tab):

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

  Shape sections     - Primitives, Arrows & Direction,
                       Rig Controls and Utility. Click any button
                       to create that control.

  Offset Dummy       - Choose the number of offset groups, then
                       "Create Offset Dummy" builds the gizmo
                       control inside its offset chain.
                       "Wrap Selection in Offset Groups" inserts
                       matched groups above the selected objects
                       without changing their world position.

  Snap to Selection  - When checked, the created control moves
                       to the pivot of your current selection
                       automatically.

  Search box         - Filter shapes by name in real time; empty
                       sections hide while filtering.

  Joint Mode         - Tick "Joint Mode", select joints, then click
                       any shape. Each control is placed on the
                       joint's pivot with the joint's rotation axes
                       and rotate order, so rotating the control X
                       turns the joint about the same X.

    Single Joint       One control on each selected joint.
    Multi-Joint Chain  Walks the chain and builds a control on
                       every joint:
                         Selected joint + all below - everything
                           under each selected joint
                         Start -> End - select the first joint,
                           then the last joint
                       Skip end joints  - no control on the tip
    Link controls      How each control follows the one above it
                       (Multi-Joint):
                         Parent-constraint chain (FK) - every
                           <control>_GRP stays flat in the
                           outliner and is parent-constrained to
                           the control above (default)
                         Nested hierarchy (FK) - each group is
                           parented under the control above
                         Not linked - independent controls
    Drive joints       No constraint, Parent, Orient or Point +
                       Orient constraint from each control to its
                       joint. Joints are never re-parented. A joint
                       that already has that constraint is skipped
                       with a warning (a second target would blend
                       old and new controls).
    Name               Naming pattern. # is the number (## pads to
                       01), {joint} is the joint's name.
                       FlagPole_#_CTRL -> FlagPole_1_CTRL,
                       FlagPole_2_CTRL, ...  Start # sets the first
                       number.
    Shape faces        "Down the chain (auto)" reads each joint's
                       orientation and turns the shape to face the
                       axis pointing at the next joint, so circles
                       ring the bone. Or pick a joint axis, or keep
                       the shape as built. Works with every shape.
    Size               A multiple of the joint radius or bone
                       length, or a fixed size in units.
    Zero group         Puts each control under <control>_GRP
                       matched to the joint, so its channels start
                       at zero.

  Best for Joints    (shown in Joint Mode) "Best Option" picks the
                     shape per joint from its name: root/world ->
                     Root, COG/pelvis/hips -> Circle 4-Arrow,
                     head/chest -> Cube, eye -> Sphere, jaw/
                     clavicle/toe -> Half Circle, hand -> Square,
                     _end/_tip joints -> Diamond 3D, any other
                     joint -> FK ring. The row below holds the
                     shapes that suit joint controls best.

  Per-joint shapes   (Multi-Joint) Click "Per-joint shapes...",
                     select the chain and "Load Joints from
                     Selection". Each joint gets a row: choose its
                     shape in the list, or select rows and click any
                     shape button to assign it. "Build Controls"
                     builds them all in one undo step.

  Batch Rename tab   Renames the selection in selection order from
                     a pattern (# numbers, {name} = current name)
                     with a start number and step. "Include
                     children (same type)" renames a whole joint
                     chain from its root. Also Search and Replace,
                     and Prefix / Suffix. Shapes are renamed to
                     match; one undo step per click.

  Joints should be oriented (Skeleton > Orient Joint) for the
  cleanest result; a warning names any joint whose axes do not
  follow its bone. One click is one undo step.

  All shapes are created at the world origin (or snapped to
  selection) and named with a _CTRL suffix.


================================================================
  COMPATIBILITY
================================================================

  Maya 2022    PySide2 / Qt5
  Maya 2023    PySide2 / Qt5
  Maya 2024    PySide2 / Qt5
  Maya 2025    PySide2 / Qt5
  Maya 2026    PySide6 / Qt6   <- Primary target

  The script auto-detects Qt version at load time.


================================================================
  TROUBLESHOOTING
================================================================

  "No module named 'wire_shape_tool'"
    -> The .py file is not in your scripts folder.
      Re-run the installer or copy it manually (see Option B).

  Shelf button shows no icon
    -> Shape_Icon.png was not found during install.
      Copy it manually to your Maya prefs/icons/ folder.

  Install dialog does not appear
    -> Make sure all four files are in the same folder before
      dragging the .mel file onto the viewport.

  Tool opens but shapes don't snap
    -> Ensure "Snap to Selection" is checked in the tool header.


================================================================
  UNINSTALL
================================================================

  1. Delete  wire_shape_tool.py  from your scripts folder.
  2. Delete  Shape_Icon.png  from your icons folder.
  3. Right-click the shelf button -> Delete Button.


================================================================
