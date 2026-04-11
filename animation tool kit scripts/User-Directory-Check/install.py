"""
Drag-and-drop installer for Maya 2018+.
Drops a shelf button that launches User Directory Check.
"""

import os
import sys

try:
    import maya.mel
    import maya.cmds
    is_maya = True
except ImportError:
    is_maya = False


def onMayaDroppedPythonFile(*args, **kwargs):
    """Maya entry point (Maya 2017 Update 3+)."""
    _on_maya_dropped()


def _on_maya_dropped():
    """Create a shelf button that launches the tool."""
    base_path = os.path.dirname(__file__)
    script_path = os.path.join(base_path, "User_Directory_Check")
    icon_path = os.path.join(base_path, "user_directory_check_icon.png")

    script_path = os.path.normpath(script_path)
    icon_path = os.path.normpath(icon_path)

    if not os.path.exists(script_path):
        raise IOError("Cannot find script: {}".format(script_path))

    if not os.path.exists(icon_path):
        maya.cmds.warning("Icon not found, using Maya default icon: {}".format(icon_path))
        icon_path = "commandButton.png"

    command = '''
# -----------------------------------
# User Directory Check
# -----------------------------------
import os
import runpy

script_path = r"{script_path}"

if not os.path.exists(script_path):
    raise IOError('The script path "{{}}" does not exist!'.format(script_path))

namespace = runpy.run_path(script_path)
window_class = namespace.get("UserDirCheckWindow")
if window_class is None:
    raise RuntimeError("UserDirCheckWindow was not found in script")

window_class.show_window()
'''.format(script_path=script_path)

    shelf_top_level = maya.mel.eval('$gShelfTopLevel=$gShelfTopLevel')
    parent_shelf = maya.cmds.tabLayout(shelf_top_level, query=True, selectTab=True)

    maya.cmds.shelfButton(
        command=command,
        annotation='User Directory Check',
        sourceType='Python',
        image=icon_path,
        image1=icon_path,
        label='UserDirChk',
        parent=parent_shelf,
    )


if is_maya:
    _on_maya_dropped()
