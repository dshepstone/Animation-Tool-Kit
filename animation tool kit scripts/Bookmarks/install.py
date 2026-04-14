"""
Drag and drop installer for Maya 2022+

Can be run two ways:
  1. Drop install.mel onto the Maya viewport — the MEL file delegates here.
  2. Drop install.py directly onto the Maya viewport (Maya 2017+).

Adds a shelf button with Bookmark.png to whichever shelf tab is currently
active, adds src/ to sys.path for the running session, and writes a
persistent entry to userSetup.py.
"""
import os
import sys

try:
    import maya.cmds
    import maya.mel
    _IS_MAYA = True
except ImportError:
    _IS_MAYA = False


def onMayaDroppedPythonFile(*args, **kwargs):
    """Called by Maya when this .py file is dropped onto the viewport."""
    pass  # _onMayaDropped() handles everything below


def _onMayaDropped():
    tool_root = os.path.dirname(os.path.abspath(__file__))
    src_path  = os.path.normpath(os.path.join(tool_root, 'src'))
    icon_path = os.path.normpath(os.path.join(tool_root, 'icons', 'Bookmark.png'))

    if not os.path.exists(src_path):
        raise IOError('Cannot find source folder: ' + src_path)
    if not os.path.exists(icon_path):
        raise IOError('Cannot find icon: ' + icon_path)

    # Warn if already on the path (re-install is still allowed).
    for p in sys.path:
        if os.path.exists(os.path.join(p, 'time_bookmarks', '__init__.py')):
            maya.cmds.warning('Maya Time Bookmarks is already on sys.path at: ' + p)

    # ── 1. Add to sys.path for this session ──────────────────────────────────
    if src_path not in sys.path:
        sys.path.insert(0, src_path)

    # ── 2. Persist via userSetup.py ──────────────────────────────────────────
    _update_usersetup(src_path)

    # ── 3. Add shelf button to the currently active shelf tab ────────────────
    # The command removes all cached time_bookmarks modules before importing
    # so clicking the button always loads the latest file on disk.
    command = (
        "import sys, importlib\n"
        "if r'{path}' not in sys.path:\n"
        "    sys.path.insert(0, r'{path}')\n"
        "# Unload cached modules so the latest source is always used.\n"
        "for _m in [m for m in list(sys.modules) if m == 'time_bookmarks' or m.startswith('time_bookmarks.')]:\n"
        "    del sys.modules[_m]\n"
        "import time_bookmarks.main\n"
        "time_bookmarks.main.launch()\n"
    ).format(path=src_path)

    shelf    = maya.mel.eval('$gShelfTopLevel=$gShelfTopLevel')
    parent   = maya.cmds.tabLayout(shelf, query=True, selectTab=True)

    maya.cmds.shelfButton(
        command=command,
        annotation='Maya Time Bookmarks',
        sourceType='Python',
        image=icon_path,
        image1=icon_path,
        label='Time Bookmarks',
        parent=parent,
    )

    print('// Maya Time Bookmarks: shelf button added to "' + parent + '"')


def _update_usersetup(src_path):
    """Append a sys.path entry to userSetup.py (skipped if already present)."""
    pref_dir   = maya.cmds.internalVar(userPrefDir=True)
    setup_file = os.path.join(pref_dir, 'scripts', 'userSetup.py')
    insert_line = "sys.path.insert(0, r'{}')".format(src_path)

    existing = ''
    if os.path.exists(setup_file):
        with open(setup_file, 'r') as fh:
            existing = fh.read()

    if 'time_bookmarks' not in existing:
        with open(setup_file, 'a') as fh:
            fh.write('\n# Maya Time Bookmarks — added by installer\n')
            fh.write('import sys\n')
            fh.write(insert_line + '\n')
        print('// Maya Time Bookmarks: updated ' + setup_file)
    else:
        print('// Maya Time Bookmarks: userSetup.py already has an entry — skipped')


if _IS_MAYA:
    _onMayaDropped()
