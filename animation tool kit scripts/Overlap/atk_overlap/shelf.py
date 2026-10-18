"""Install or update the Overlap launcher on a Maya shelf."""
from pathlib import Path


def icon_path():
    return Path(__file__).resolve().parent / 'assets' / 'overlap_32.png'


def add_to_shelf(shelf=None, save=True):
    from maya import cmds, mel
    if shelf is None:
        shelf = cmds.tabLayout(mel.eval('$overlapShelf=$gShelfTopLevel'), query=True, selectTab=True)
    if not shelf or not cmds.shelfLayout(shelf, exists=True):
        raise ValueError('Select a shelf in Maya before adding Overlap')
    root = str(Path(__file__).resolve().parent.parent)
    # A string callback survives Maya saving/reloading the shelf. Explicit path
    # makes the launcher work after restart, including a direct-source launch.
    command = 'import sys\np = {!r}\nif p not in sys.path:\n    sys.path.insert(0, p)\nimport atk_overlap\natk_overlap.show()'.format(root)
    children = cmds.shelfLayout(shelf, query=True, childArray=True) or []
    known = ('Launch Kinequill spring overlap', 'Launch Overlap animation tool')
    buttons = [n for n in children if cmds.objectTypeUI(n) == 'shelfButton'
               and cmds.shelfButton(n, query=True, annotation=True) in known]
    args = dict(label='Overlap', annotation='Launch Overlap animation tool',
                image=str(icon_path()), sourceType='python', command=command, width=32, height=32)
    if buttons:
        for button in buttons:
            cmds.shelfButton(button, edit=True, **args)
        button = buttons[0]
    else:
        button = cmds.shelfButton(parent=shelf, **args)
    if save:
        folder = Path(cmds.internalVar(userShelfDir=True))
        folder.mkdir(parents=True, exist_ok=True)
        name = shelf.rsplit('|', 1)[-1]
        if not cmds.saveShelf(shelf, str(folder / ('shelf_' + name))):
            raise RuntimeError('Shelf button added, but Maya could not save the shelf')
    return button
