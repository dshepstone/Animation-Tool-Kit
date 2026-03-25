Maya Reset Tool
===============

Creator
-------
David Shepstone

What the script does
-------------------
The Reset Tool provides a modern Maya UI to reset transforms on selected
objects. It can reset translate, rotate, scale, or all channels at once,
while automatically skipping locked or non-settable attributes.

The tool also includes a hotkey setup system so you can trigger any reset
function directly from the keyboard without opening the UI.

How to use it
------------
1. Select one or more transform nodes in your Maya scene.
2. Open the Reset Tool window from the shelf button (installed via the
   installer) or by running transform_reset_tool.show() in the Script Editor.
3. Click one of the buttons:
   - Reset Translate : sets tx/ty/tz to 0.
   - Reset Rotate    : sets rx/ry/rz to 0.
   - Reset Scale     : sets sx/sy/sz to 1.
   - Reset All       : resets translate, rotate, and scale in one click.

Setting up hotkeys
------------------
1. In the Reset Tool window, click "Setup / Edit Hotkeys..." in the
   Shortcuts section at the bottom.

2. If your active hotkey set is Maya_Default (which is locked), you will
   be prompted to either select an existing custom set or create a new one.
   The new set is automatically copied from Maya_Default so your existing
   shortcuts are preserved.

3. The Hotkey Setup dialog opens with a dropdown to switch between custom
   hotkey sets and a refresh button to pick up sets created outside the tool.

4. Click into any key-sequence field and press the key combination you want
   to assign (e.g. Ctrl+Shift+R). Supported input: letters, numbers, F1-F12,
   and modifier keys Ctrl / Alt / Shift.

5. Click Apply. The tool registers runtime commands under
   Custom Scripts > Reset Tool in Maya's Hotkey Editor, assigns the chosen
   shortcuts, and saves your hotkey preferences immediately.

6. To remove all assignments, click "Clear All" in the same dialog.

   The four assignable actions are:
   - Reset All Transforms
   - Reset Translate
   - Reset Rotate
   - Reset Scale

How to install it
----------------
Method 1 — Drag and drop installer (recommended)
  a. Place these files in the same folder:
       install_reset.mel
       transform_reset_tool.py
       reset_icon.png  (optional but recommended)
  b. In Maya, drag and drop install_reset.mel into the viewport.
  c. The installer:
       - Copies transform_reset_tool.py to your Maya user scripts folder.
       - Copies reset_icon.png to your Maya user icons folder (if present).
       - Adds a "Reset All" shelf button to your currently active shelf.
  d. Click the "Reset All" shelf button to launch the tool.

Method 2 — Manual install
  a. Copy transform_reset_tool.py to your Maya user scripts folder, e.g.:
       Windows : C:\Users\<you>\Documents\maya\<version>\scripts\
       macOS   : ~/Library/Preferences/Autodesk/maya/<version>/scripts/
       Linux   : ~/maya/<version>/scripts/
  b. In Maya's Script Editor (Python tab), run:
       import transform_reset_tool
       transform_reset_tool.show()
  c. Optionally, create a shelf button with the above two lines as its
     command (source type: Python) using reset_icon.png as the icon.

Files
-----
transform_reset_tool.py : The Python tool, UI, and hotkey system.
install_reset.mel        : Drag-and-drop installer — copies files and
                           creates a shelf button automatically.
reset_icon.png           : Icon used for the shelf button (optional).
