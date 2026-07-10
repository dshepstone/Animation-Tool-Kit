"""Developer helper: fully reload the tool after reinstalling/updating files.

Maya caches imported Python modules, so copying new files into the scripts
folder and re-running the shelf button keeps the *old* code (``importlib.reload``
on a single module does not touch the submodules where most of the code lives).
This helper closes the window, drops every cached ``blue_pencil_flipbook.*``
module, and relaunches from the freshly copied files.

Usage in the Script Editor (Python tab) or a shelf button:

    import blue_pencil_flipbook.dev_reload as r
    r.reload()

If the package might be in a broken state, use the self-contained snippet from
the README instead - it purges the modules without importing the package first.
"""

from __future__ import annotations

import sys

try:
    from maya import cmds
except Exception:
    cmds = None

PACKAGE = "blue_pencil_flipbook"
WORKSPACE_CONTROL = "BluePencilFlipbookManagerWorkspaceControl"


def purge_modules():
    """Remove every cached module of the package from sys.modules."""
    stale = [m for m in list(sys.modules) if m == PACKAGE or m.startswith(PACKAGE + ".")]
    for name in stale:
        del sys.modules[name]
    return stale


def reload(show=True):
    """Close, purge, and relaunch the tool from the currently installed files."""
    if cmds is None:
        print("blue_pencil_flipbook.dev_reload: run this inside Maya.")
        return None

    # 1) Close the current window / workspace control if it exists.
    try:
        if cmds.workspaceControl(WORKSPACE_CONTROL, exists=True):
            cmds.deleteUI(WORKSPACE_CONTROL)
    except Exception:
        pass

    # 2) Make sure the user scripts dir (where the installer copies to) imports.
    try:
        scripts_dir = cmds.internalVar(userScriptDir=True)
        if scripts_dir and scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
    except Exception:
        pass

    # 3) Drop every cached submodule so the new files are imported fresh.
    purge_modules()

    # 4) Re-import from disk and (optionally) show the window.
    import importlib
    launch = importlib.import_module(PACKAGE + ".launch")
    if show:
        return launch.show()
    return launch
