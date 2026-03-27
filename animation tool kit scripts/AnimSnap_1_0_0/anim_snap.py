"""
AnimSnap - Maya Python tool for snapping one object to another using world-space transforms.

Usage:
    1. Select two objects in Maya (source first, then target)
    2. Run: anim_snap.snap()

The first selected object will be moved to match the position and orientation
of the second selected object in world space.
"""

import maya.cmds as cmds


def snap(translate=True, rotate=True):
    """Snap the first selected object to the second selected object in world space.

    Args:
        translate: Apply world-space translation from target. Default True.
        rotate: Apply world-space rotation from target. Default True.
    """
    sel = cmds.ls(selection=True)

    if len(sel) < 2:
        cmds.warning("Select two objects: source then target")
        return

    # If more than 2 selected, use the last two
    source = sel[-2]
    target = sel[-1]

    if not translate and not rotate:
        cmds.warning("Nothing to snap: both translate and rotate are disabled")
        return

    # Query target world-space transforms
    target_translation = cmds.xform(target, query=True, worldSpace=True, translation=True)
    target_rotation = cmds.xform(target, query=True, worldSpace=True, rotation=True)

    # Apply to source in world space (handles parent hierarchies correctly)
    if translate:
        cmds.xform(source, worldSpace=True, translation=target_translation)
    if rotate:
        cmds.xform(source, worldSpace=True, rotation=target_rotation)

    # Confirmation
    mode = "translate + rotate"
    if translate and not rotate:
        mode = "translate only"
    elif rotate and not translate:
        mode = "rotate only"

    print("AnimSnap: Snapped '{}' -> '{}' ({})".format(source, target, mode))


def snap_translate():
    """Snap translation only."""
    snap(translate=True, rotate=False)


def snap_rotate():
    """Snap rotation only."""
    snap(translate=False, rotate=True)


# ---------------------------------------------------------------------------
# Optional UI
# ---------------------------------------------------------------------------

def create_ui():
    """Create a simple AnimSnap window with snap options."""
    window_name = "animSnapWindow"

    if cmds.window(window_name, exists=True):
        cmds.deleteUI(window_name)

    cmds.window(window_name, title="AnimSnap", widthHeight=(250, 120))
    cmds.columnLayout(adjustableColumn=True, rowSpacing=6, columnOffset=("both", 8))

    cmds.separator(height=4, style="none")
    cmds.text(label="Select source then target, then click:")
    cmds.separator(height=4, style="none")

    cmds.button(label="Snap (Translate + Rotate)", command=lambda _: snap())
    cmds.button(label="Snap Translate Only", command=lambda _: snap_translate())
    cmds.button(label="Snap Rotate Only", command=lambda _: snap_rotate())

    cmds.showWindow(window_name)


def launch():
    """Launch the AnimSnap UI — called by the ATK Toolbar."""
    create_ui()


def add_shelf_button():
    """Add an AnimSnap button to the current shelf."""
    current_shelf = cmds.tabLayout("ShelfLayout", query=True, selectTab=True)
    cmds.shelfButton(
        parent=current_shelf,
        label="AnimSnap",
        annotation="Snap source object to target (select two objects)",
        command="import anim_snap; anim_snap.snap()",
        image1="snapTogether.png",
    )
    print("AnimSnap: Shelf button added to '{}'".format(current_shelf))
