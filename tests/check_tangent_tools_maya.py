"""Run with mayapy. Checks which keys the quick tangent buttons change.

Uses real Maya curves, keyTangent, key selection and undo.  Only the
interactive Time Slider (``timeControl``) is substituted in standalone Maya.
"""
import sys
from pathlib import Path

import maya.standalone
maya.standalone.initialize(name="python")
import maya.cmds as cmds

sys.path.insert(0, str(Path(__file__).resolve().parents[1] /
                       "animation tool kit scripts/tangent_tools/src"))
from tangent_tools import core

FRAMES = (1, 5, 10, 15, 20)


class Slider(object):
    """Stand-in Time Slider: a highlight range and Channel Box narrowing."""
    range = None
    attrs = None

    def timeControl(self, slider, **flags):
        if flags.get("rangeVisible"):
            return self.range is not None
        if flags.get("rangeArray"):
            return list(self.range)
        if flags.get("animCurveNames"):
            sel = cmds.ls(selection=True) or []
            if not sel:
                return []
            kw = {"attribute": self.attrs} if self.attrs else {}
            return cmds.keyframe(sel, query=True, name=True, **kw) or []
        raise RuntimeError("unexpected timeControl flags %r" % flags)


class Cmds(object):
    def __init__(self, slider):
        self.slider = slider

    def __getattr__(self, name):
        if name == "timeControl":
            return self.slider.timeControl
        return getattr(cmds, name)


SLIDER = Slider()
core.cmds = Cmds(SLIDER)
core.mel.eval = lambda *a, **k: "timeControl1"


def reset():
    cmds.file(new=True, force=True)
    cmds.undoInfo(state=True)
    cmds.keyTangent(g=True, itt="clamped", ott="clamped")
    SLIDER.range = None
    SLIDER.attrs = None
    for node in ("ball", "box"):
        cmds.createNode("transform", name=node)
        for attr in ("tx", "ty"):
            for f in FRAMES:
                cmds.setKeyframe(node, attribute=attr, time=f, value=f * 2,
                                 itt="clamped", ott="clamped")
    cmds.select("ball")
    cmds.selectKey(clear=True)
    cmds.currentTime(1)


def tangents():
    """{(node.attr, frame): (in, out)} for every key in the scene."""
    out = {}
    for node in ("ball", "box"):
        for attr in ("tx", "ty"):
            plug = "%s.%s" % (node, attr)
            for f in FRAMES:
                itt = cmds.keyTangent(plug, q=True, time=(f, f), itt=True)[0]
                ott = cmds.keyTangent(plug, q=True, time=(f, f), ott=True)[0]
                out[(plug, f)] = (itt, ott)
    return out


def changed(before):
    after = tangents()
    return {k: after[k] for k in after if after[k] != before[k]}


def check(name, setup, kind, expect_keys, expect_value):
    reset()
    setup()
    before = tangents()
    core.set_tangent_type(kind)
    diff = changed(before)
    assert set(diff) == set(expect_keys), "%s: changed %s, expected %s" % (
        name, sorted(diff), sorted(expect_keys))
    for k, v in diff.items():
        assert v == expect_value, "%s: %s became %s, expected %s" % (name, k, v, expect_value)
    cmds.undo()
    assert not changed(before), "%s: one undo did not restore every key" % name
    print("PASS: " + name)


def main():
    lin = ("linear", "linear")

    # 1. Timeline cursor on a key, nothing highlighted.
    check("timeline: only the key on the current frame",
          lambda: cmds.currentTime(10), "linear",
          [("ball.tx", 10), ("ball.ty", 10)], lin)

    # 1b. Channel Box narrowing on the current frame.
    def cb():
        cmds.currentTime(10)
        SLIDER.attrs = ["ty"]
    check("timeline: Channel Box channel narrows it",
          cb, "linear", [("ball.ty", 10)], lin)

    # 1c. Cursor between keys changes nothing.
    check("timeline: no key on the current frame changes nothing",
          lambda: cmds.currentTime(7), "linear", [], lin)

    # 2. Shift-dragged range 5-15 (rangeArray reports [5, 16]).
    def rng():
        SLIDER.range = (5, 16)
    check("timeline: highlighted range only",
          rng, "auto_legacy",
          [(p, f) for p in ("ball.tx", "ball.ty") for f in (5, 10, 15)],
          ("spline", "spline"))

    # 3. Keys selected in the Graph Editor (any object).
    def sel():
        cmds.currentTime(1)
        cmds.selectKey("ball.tx", time=(5, 5))
        cmds.selectKey("box.ty", time=(20, 20), add=True)
    check("graph editor: only the selected keys",
          sel, "linear", [("ball.tx", 5), ("box.ty", 20)], lin)

    # 3b. Stepped changes only the out tangent of selected keys.
    def sel2():
        cmds.selectKey("ball.tx", time=(5, 10))
    check("graph editor: stepped on selected keys",
          sel2, "stepped", [("ball.tx", 5), ("ball.tx", 10)],
          ("clamped", "step"))

    # 4. Graph Editor with nothing selected: key under the current frame.
    def ge():
        cmds.currentTime(15)
        cmds.selectKey(clear=True)
    check("graph editor: nothing selected, key on current frame",
          ge, "linear", [("ball.tx", 15), ("ball.ty", 15)], lin)

    print("ALL PASS")


if __name__ == "__main__":
    try:
        main()
    finally:
        maya.standalone.uninitialize()
