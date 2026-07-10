# Blue Pencil Flipbook Manager

A dockable Maya 2026 Python tool (PySide6, with PySide2 fallback) designed to improve the Autodesk Maya Blue Pencil workflow with thumbnails, frame types, filtered playback, quick tool buttons, frame actions, hotkeys, and HTML help. The interface uses a modern dark theme styled to match the Animation Tool Kit.

## Launch in Maya

Add the repository parent folder to `PYTHONPATH`, then run:

```python
import blue_pencil_flipbook.launch as bp
bp.show()
```

## Reloading after an update (development)

Maya caches imported Python modules, so re-running `bp.show()` after copying new
files keeps the old code. The drag-and-drop installer's shelf button already does
a full reload on every click, so **reinstalling and clicking the shelf button
picks up your changes** without restarting Maya.

To reload from the Script Editor:

```python
import blue_pencil_flipbook.dev_reload as r
r.reload()
```

Or a fully self-contained snippet (works even if the package is mid-edit) — put
it on a shelf button or run it in the Script Editor after reinstalling:

```python
import sys
import maya.cmds as cmds

# Close the window if it's open.
wc = "BluePencilFlipbookManagerWorkspaceControl"
if cmds.workspaceControl(wc, exists=True):
    cmds.deleteUI(wc)

# Make sure the scripts dir is importable.
scripts_dir = cmds.internalVar(userScriptDir=True)
if scripts_dir not in sys.path:
    sys.path.insert(0, scripts_dir)

# Drop every cached submodule so the new files load.
for m in [m for m in list(sys.modules)
          if m == "blue_pencil_flipbook" or m.startswith("blue_pencil_flipbook.")]:
    del sys.modules[m]

# Relaunch fresh.
import blue_pencil_flipbook.launch as bp
bp.show()
```
