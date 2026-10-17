"""Create an animated FK test chain without clearing the current scene."""
from maya import cmds
from .maya_engine import scene_state


def create_demo():
    with scene_state("Kinequill demo"):
        group = cmds.group(empty=True, name="Kinequill_demo#")
        controls = []
        parent = group
        for i in range(4):
            control = cmds.circle(name="KQ_demo_{}_CTRL#".format(i + 1),
                                  normal=(1, 0, 0), radius=.7, constructionHistory=False)[0]
            cmds.parent(control, parent, relative=True)
            cmds.setAttr(control + ".tx", 0 if i == 0 else 4)
            cmds.setAttr(control + ".overrideEnabled", True)
            cmds.setAttr(control + ".overrideColor", 17)
            controls.append(control)
            parent = control
        for frame, value in ((1, 0), (12, 6), (24, -4), (36, 3), (48, 0), (72, 0)):
            cmds.setKeyframe(controls[0], attribute="ty", time=frame, value=value)
            cmds.setKeyframe(controls[0], attribute="rz", time=frame, value=value * 5)
    cmds.select(controls, replace=True)
    return controls
