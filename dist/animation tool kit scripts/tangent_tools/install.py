"""
Drag and drop installer for Tangent Tools — Maya 2022+

Can be run two ways:
  1. Drop install.mel onto the Maya viewport — the MEL file delegates here.
  2. Drop install.py directly onto the Maya viewport (Maya 2017+).

Adds a shelf button (using curveTool.png) to whichever shelf tab is
currently active, adds src/ to sys.path for the running session, and
writes a persistent entry to userSetup.py.

Re-running this installer is safe:
  * Any existing Tangent Tools shelf buttons are removed first so the
    shelf never ends up with duplicates.
  * userSetup.py is rewritten so only one tangent_tools block remains,
    pointing at the current src path.

The shelf button the installer creates reloads the latest source on every
click: it strips cached ``tangent_tools`` modules from ``sys.modules`` and
calls ``importlib.invalidate_caches()`` before re-importing, so code
edits become visible without restarting Maya.
"""
import os
import sys

try:
    import maya.cmds
    import maya.mel
    _IS_MAYA = True
except ImportError:
    _IS_MAYA = False


SHELF_BUTTON_ANNOTATION = 'Tangent Tools'
SHELF_BUTTON_LABEL      = 'TangentTools'
USERSETUP_MARKER        = '# Tangent Tools — added by installer'


def onMayaDroppedPythonFile(*args, **kwargs):
    """Called by Maya when this .py file is dropped onto the viewport."""
    pass  # _onMayaDropped() handles everything below


def _onMayaDropped():
    tool_root = os.path.dirname(os.path.abspath(__file__))
    src_path  = os.path.normpath(os.path.join(tool_root, 'src'))
    icon_path = os.path.normpath(os.path.join(tool_root, 'curveTool.png'))

    if not os.path.exists(src_path):
        raise IOError('Cannot find source folder: ' + src_path)
    if not os.path.exists(icon_path):
        raise IOError('Cannot find icon: ' + icon_path)

    # -- 1. Add to sys.path for this session ---------------------------------
    if src_path not in sys.path:
        sys.path.insert(0, src_path)

    # -- 2. Persist via userSetup.py (dedupes old entries) -------------------
    _update_usersetup(src_path)

    # -- 3. Remove any stale Tangent Tools shelf buttons ---------------------
    _remove_existing_shelf_buttons()

    # -- 4. Add a fresh shelf button to the active shelf tab -----------------
    shelf  = maya.mel.eval('$gShelfTopLevel=$gShelfTopLevel')
    parent = maya.cmds.tabLayout(shelf, query=True, selectTab=True)

    maya.cmds.shelfButton(
        command=_build_shelf_command(src_path),
        annotation=SHELF_BUTTON_ANNOTATION,
        sourceType='Python',
        image=icon_path,
        image1=icon_path,
        label=SHELF_BUTTON_LABEL,
        parent=parent,
    )

    print('// Tangent Tools: shelf button added to "' + parent + '"')


def _build_shelf_command(src_path):
    """Return the Python string baked into the shelf button.

    Each click:
      * Makes sure *src_path* is on ``sys.path`` (and at the front).
      * Strips every cached ``tangent_tools`` module from ``sys.modules``.
      * Calls ``importlib.invalidate_caches()`` so freshly-added files are
        discovered.
      * Closes any panel from a previous session before relaunching, so the
        user always sees a panel built from the latest source.
      * Imports ``tangent_tools.main`` and calls ``launch()``.
    """
    return (
        "import sys, importlib\n"
        "_tt_path = r'{path}'\n"
        "# Move our src path to the front of sys.path so this copy wins.\n"
        "while _tt_path in sys.path:\n"
        "    sys.path.remove(_tt_path)\n"
        "sys.path.insert(0, _tt_path)\n"
        "# Strip any cached tangent_tools modules so edits on disk are picked up.\n"
        "for _m in [m for m in list(sys.modules) if m == 'tangent_tools' or m.startswith('tangent_tools.')]:\n"
        "    del sys.modules[_m]\n"
        "importlib.invalidate_caches()\n"
        "# Close an already-open panel so it is rebuilt from fresh source.\n"
        "try:\n"
        "    from PySide6 import QtWidgets as _QtW  # Maya 2025+\n"
        "except ImportError:\n"
        "    try:\n"
        "        from PySide2 import QtWidgets as _QtW  # Maya 2022-2024\n"
        "    except ImportError:\n"
        "        _QtW = None\n"
        "if _QtW is not None:\n"
        "    _app = _QtW.QApplication.instance()\n"
        "    if _app is not None:\n"
        "        for _w in _app.topLevelWidgets():\n"
        "            if _w.objectName() == 'TangentToolsPanel':\n"
        "                try:\n"
        "                    _w.close()\n"
        "                    _w.deleteLater()\n"
        "                except Exception:\n"
        "                    pass\n"
        "import tangent_tools.main\n"
        "tangent_tools.main.launch()\n"
    ).format(path=src_path)


def _remove_existing_shelf_buttons():
    """Delete any shelf buttons that look like Tangent Tools buttons.

    Matches on annotation first, falling back to the label.  Safe to call
    when no buttons exist.
    """
    shelf_top = maya.mel.eval('$gShelfTopLevel=$gShelfTopLevel')
    try:
        tabs = maya.cmds.tabLayout(shelf_top, query=True, childArray=True) or []
    except Exception:
        tabs = []
    removed = 0
    for tab in tabs:
        try:
            buttons = maya.cmds.shelfLayout(tab, query=True, childArray=True) or []
        except Exception:
            continue
        for btn in buttons:
            if not maya.cmds.shelfButton(btn, exists=True):
                continue
            try:
                ann = maya.cmds.shelfButton(btn, query=True, annotation=True) or ''
                lbl = maya.cmds.shelfButton(btn, query=True, label=True) or ''
            except Exception:
                continue
            if ann == SHELF_BUTTON_ANNOTATION or lbl == SHELF_BUTTON_LABEL:
                try:
                    maya.cmds.deleteUI(btn)
                    removed += 1
                except Exception:
                    pass
    if removed:
        print('// Tangent Tools: removed {} stale shelf button(s)'.format(removed))


def _update_usersetup(src_path):
    """Rewrite userSetup.py so exactly one tangent_tools block is present.

    If the file already has older Tangent Tools entries (possibly pointing
    at stale paths, or duplicated from repeat installs), they are stripped
    and replaced with a single block that points at *src_path*.
    """
    pref_dir   = maya.cmds.internalVar(userPrefDir=True)
    setup_file = os.path.join(pref_dir, 'scripts', 'userSetup.py')

    existing = ''
    if os.path.exists(setup_file):
        with open(setup_file, 'r') as fh:
            existing = fh.read()

    cleaned_lines = []
    skip_next_imports = 0
    for line in existing.splitlines():
        stripped = line.strip()
        if stripped == USERSETUP_MARKER:
            # Skip this marker line and the next 2 lines (import + insert).
            skip_next_imports = 2
            continue
        if skip_next_imports > 0:
            skip_next_imports -= 1
            continue
        if 'tangent_tools' in stripped and stripped.startswith('sys.path.insert'):
            # Also strip any orphaned sys.path.insert lines that reference
            # tangent_tools, even without the marker above them.
            continue
        cleaned_lines.append(line)

    cleaned = '\n'.join(cleaned_lines).rstrip()
    block = (
        '\n\n' + USERSETUP_MARKER + '\n'
        'import sys\n'
        "sys.path.insert(0, r'{}')\n".format(src_path)
    )

    new_content = (cleaned + block) if cleaned else block.lstrip('\n')

    # Ensure the target directory exists before writing.
    os.makedirs(os.path.dirname(setup_file), exist_ok=True)
    with open(setup_file, 'w') as fh:
        fh.write(new_content)
    print('// Tangent Tools: userSetup.py rewritten at ' + setup_file)


if _IS_MAYA:
    _onMayaDropped()
