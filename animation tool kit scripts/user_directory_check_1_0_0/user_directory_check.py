"""User Directory Check tool for Maya.

Shows key user-directory paths and indicates whether they exist.
"""

import os

import maya.cmds as cmds

_WINDOW_NAME = "ATKUserDirectoryCheckWindow"


def _rows():
    return [
        ("User Pref Dir", cmds.internalVar(userPrefDir=True)),
        ("User Script Dir", cmds.internalVar(userScriptDir=True)),
        ("User App Dir", cmds.internalVar(userAppDir=True)),
        ("User Shelf Dir", cmds.internalVar(userShelfDir=True)),
        ("User Workspace Dir", cmds.internalVar(userWorkspaceDir=True)),
        ("User Bitmaps Dir", cmds.internalVar(userBitmapsDir=True)),
    ]


def _copy_path(path):
    try:
        cmds.clipboard(path)
    except Exception:
        cmds.warning("User Directory Check: could not copy path to clipboard")


def show():
    if cmds.window(_WINDOW_NAME, exists=True):
        cmds.deleteUI(_WINDOW_NAME)

    win = cmds.window(_WINDOW_NAME, title="User Directory Check", sizeable=True, widthHeight=(720, 320))
    cmds.columnLayout(adjustableColumn=True, rowSpacing=6)

    cmds.text(label="Maya user directories and validation", align="left")
    cmds.separator(height=8, style="in")

    cols = [(1, 140), (2, 440), (3, 70), (4, 70)]
    cmds.rowColumnLayout(numberOfColumns=4, columnWidth=cols)

    cmds.text(label="Directory", align="left", font="boldLabelFont")
    cmds.text(label="Path", align="left", font="boldLabelFont")
    cmds.text(label="Exists", align="left", font="boldLabelFont")
    cmds.text(label="Action", align="left", font="boldLabelFont")

    for label, path in _rows():
        exists = os.path.isdir(path)
        cmds.text(label=label, align="left")
        cmds.textField(text=path, editable=False)
        cmds.text(label="Yes" if exists else "No", align="left")
        cmds.button(label="Copy", c=lambda _x, p=path: _copy_path(p))

    cmds.setParent("..")
    cmds.separator(height=10, style="none")

    cmds.rowLayout(numberOfColumns=2, adjustableColumn=1)
    cmds.text(label="Tip: if a required folder is missing, create it before installing tools.", align="left")
    cmds.button(label="Refresh", c=lambda *_: show(), width=90)
    cmds.setParent("..")

    cmds.showWindow(win)


if __name__ == "__main__":
    show()
