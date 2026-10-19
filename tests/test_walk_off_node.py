"""Walk Off Node against a small simulated Maya scene (no Maya needed).

The fake scene is translate-only: a base node slides forward along Z while a
child foot control cycles on a treadmill (planted -> slides back relative to
the base, then lifts and swings forward).  After the tool runs the base must
be still and the foot's local keys must reproduce the original world path.
"""
import importlib.util
from pathlib import Path
import sys
import types
import unittest

SCRIPT = (Path(__file__).resolve().parents[1] / "animation tool kit scripts"
          / "Walk_Off_Node_1_0_0" / "walk_off_node.py")
AXES = ("X", "Y", "Z")


class Curve(object):
    def __init__(self, keys, infinity="constant"):
        self.keys = dict(keys)
        self.pre = self.post = infinity

    def value(self, t):
        times = sorted(self.keys)
        first, last = times[0], times[-1]
        span = last - first
        if t > last and self.post == "cycle" and span:
            t = first + (t - first) % span
        if t < first and self.pre == "cycle" and span:
            t = last - (last - t) % span
        if t <= first:
            return self.keys[first]
        if t >= last:
            return self.keys[last]
        for a, b in zip(times, times[1:]):
            if a <= t <= b:
                w = (t - a) / float(b - a)
                return self.keys[a] + (self.keys[b] - self.keys[a]) * w


class FakeScene(object):
    def __init__(self):
        self.time = 1.0
        self.parents = {}      # long name -> parent long name or None
        self.static = {}       # plug -> value
        self.curves = {}       # plug -> Curve
        self.custom = {}       # node -> [custom attr names]
        self.override = {}     # plug -> value set this frame (Maya keeps it until time changes)
        self.warnings = []

    def add(self, name, parent=None, custom=()):
        path = (parent or "") + "|" + name
        self.parents[path] = parent
        for c in "trs":
            for ax in AXES:
                self.static["%s.%s%s" % (path, {"t": "translate", "r": "rotate", "s": "scale"}[c], ax)] = 1.0 if c == "s" else 0.0
        for attr in custom:
            self.static[path + "." + attr] = 0.0
        self.custom[path] = list(custom)
        return path

    def get(self, plug, t=None):
        if t is None and plug in self.override:
            return self.override[plug]
        t = self.time if t is None else t
        if plug in self.curves:
            return self.curves[plug].value(t)
        return self.static[plug]

    def world_t(self, node):
        local = [self.get(node + ".translate" + ax) for ax in AXES]
        parent = self.parents[node]
        if parent is None:
            return local
        return [a + b for a, b in zip(self.world_t(parent), local)]

    # -- maya.cmds surface ---------------------------------------------------
    def build_cmds(self):
        scene = self
        cmds = types.SimpleNamespace()

        def resolve(name):
            for path in scene.parents:
                if path == name or path.split("|")[-1] == name.split("|")[-1]:
                    return path
            return None

        def split(plug):
            node, attr = plug.split(".", 1)
            return resolve(node), attr

        cmds.ls = lambda node=None, long=True, type=None, sl=False: (
            [] if node is None else [p for p in [resolve(node)] if p])
        cmds.playbackOptions = lambda q=True, min=False, max=False: 1 if min else 48

        def currentTime(t=None, q=False, update=True):
            if q:
                return scene.time
            scene.time = float(t)
            scene.override.clear()
        cmds.currentTime = currentTime
        cmds.autoKeyframe = lambda q=False, state=None: False if q else None
        cmds.undoInfo = lambda **kw: None
        cmds.refresh = lambda **kw: None
        cmds.warning = scene.warnings.append

        def xform(node, q=False, ws=True, t=None, ro=None):
            node = resolve(node)
            if q:
                return scene.world_t(node) if t else [0.0, 0.0, 0.0]
            if t is not None:
                parent = scene.parents[node]
                pw = scene.world_t(parent) if parent else [0.0, 0.0, 0.0]
                for ax, w, p in zip(AXES, t, pw):
                    plug = node + ".translate" + ax
                    scene.static[plug] = scene.override[plug] = w - p
        cmds.xform = xform

        def attributeQuery(attr, node=None, exists=True):
            return (resolve(node) + "." + attr) in scene.static
        cmds.attributeQuery = attributeQuery

        def getAttr(plug, lock=False, settable=False, time=None):
            node, attr = split(plug)
            if lock:
                return False
            if settable:
                return True
            return scene.get(node + "." + attr, time)
        cmds.getAttr = getAttr

        def setAttr(plug, value):
            node, attr = split(plug)
            scene.static[node + "." + attr] = scene.override[node + "." + attr] = value
        cmds.setAttr = setAttr

        def plugs_for(node, attribute):
            node = resolve(node)
            attrs = attribute if isinstance(attribute, (list, tuple)) else [attribute]
            return [node + "." + a for a in attrs]

        def keyframe(target, q=True, keyframeCount=False, name=False, attribute=None):
            if attribute is not None:
                plugs = plugs_for(target, attribute)
            else:
                node, attr = split(target)
                plugs = [node + "." + attr]
            if keyframeCount:
                return sum(len(scene.curves[p].keys) for p in plugs if p in scene.curves)
            return [p for p in plugs if p in scene.curves] or None
        cmds.keyframe = keyframe

        cmds.listAttr = lambda node, keyable=True, scalar=True: (
            ["translate" + a for a in AXES] + ["rotate" + a for a in AXES]
            + ["scale" + a for a in AXES] + ["visibility"] + scene.custom[resolve(node)])

        def bakeResults(plugs, time=None, sampleBy=1, **kw):
            for plug in plugs:
                node, attr = split(plug)
                full = node + "." + attr
                curve = scene.curves[full]
                baked = {f: curve.value(f) for f in range(time[0], time[1] + 1, sampleBy)}
                curve.keys.update(baked)
        cmds.bakeResults = bakeResults

        def setInfinity(node, attribute=None, preInfinite=None, postInfinite=None):
            for plug in plugs_for(node, attribute):
                if plug in scene.curves:
                    scene.curves[plug].pre = preInfinite
                    scene.curves[plug].post = postInfinite
        cmds.setInfinity = setInfinity

        def cutKey(node, attribute=None, time=None, clear=True):
            for plug in plugs_for(node, attribute):
                curve = scene.curves.get(plug)
                if curve is None:
                    continue
                if time is not None:
                    for k in [k for k in curve.keys if time[0] <= k <= time[1]]:
                        del curve.keys[k]
                else:
                    curve.keys.clear()
                if not curve.keys:
                    del scene.curves[plug]
        cmds.cutKey = cutKey

        def setKeyframe(node, attribute=None, time=None):
            plug = resolve(node) + "." + attribute
            value = scene.get(plug)
            curve = scene.curves.setdefault(plug, Curve({}))
            curve.keys[time] = value
        cmds.setKeyframe = setKeyframe
        cmds.filterCurve = lambda curves, filter=None: None
        cmds.listConnections = lambda *a, **kw: []
        cmds.timeControl = lambda *a, **kw: False
        return cmds


def load_module(cmds):
    maya = types.ModuleType("maya")
    maya.cmds = cmds
    maya.mel = types.SimpleNamespace(eval=lambda s: "slider")
    maya.OpenMayaUI = types.SimpleNamespace(MQtUtil=None)
    qt = types.SimpleNamespace(QDialog=object)
    pyside = types.ModuleType("PySide6")
    pyside.QtCore = pyside.QtWidgets = qt
    shiboken = types.ModuleType("shiboken6")
    shiboken.wrapInstance = None
    saved = {k: sys.modules.get(k) for k in
             ("maya", "maya.cmds", "maya.mel", "maya.OpenMayaUI", "PySide6", "shiboken6")}
    sys.modules.update({"maya": maya, "maya.cmds": cmds, "maya.mel": maya.mel,
                        "maya.OpenMayaUI": maya.OpenMayaUI, "PySide6": pyside,
                        "shiboken6": shiboken})
    try:
        spec = importlib.util.spec_from_file_location("walk_off_node_under_test", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


def treadmill_scene():
    """24-frame cycle, base moves 2 units/frame, stride 32 units."""
    scene = FakeScene()
    base = scene.add("layout")
    foot = scene.add("foot_ik", parent=base, custom=("footRoll",))
    scene.curves[base + ".translateZ"] = Curve({1: 0.0, 49: 96.0})
    # Contact frames 1-17: foot slides back at the base's speed (stays planted
    # in world).  Frames 17-25: swings forward again.
    scene.curves[foot + ".translateZ"] = Curve({1: 16.0, 17: -16.0, 25: 16.0}, "cycle")
    scene.curves[foot + ".translateY"] = Curve({1: 0.0, 17: 0.0, 21: 4.0, 25: 0.0}, "cycle")
    scene.curves[foot + ".footRoll"] = Curve({1: 0.0, 13: 10.0, 25: 0.0}, "cycle")
    return scene, base, foot


class WalkOffNodeTests(unittest.TestCase):
    def setUp(self):
        self.scene, self.base, self.foot = treadmill_scene()
        self.mod = load_module(self.scene.build_cmds())
        self.world_before = {}
        for f in range(1, 49):
            self.scene.time = f
            self.world_before[f] = self.scene.world_t(self.foot)
        self.roll_before = {f: self.scene.get(self.foot + ".footRoll", f) for f in range(1, 49)}

    def run_tool(self, **kw):
        return self.mod.walk_off_node(["foot_ik"], ["layout"], 1, 48, **kw)

    def test_original_setup_really_plants_the_foot(self):
        planted = {round(self.world_before[f][2], 6) for f in range(1, 18)}
        self.assertEqual(planted, {16.0})

    def test_world_path_is_preserved_and_base_stops(self):
        self.run_tool()
        self.assertNotIn(self.base + ".translateZ", self.scene.curves)
        for f in range(1, 49):
            self.scene.time = f
            self.assertEqual(self.scene.get(self.base + ".translateZ"), 0.0)
            for got, want in zip(self.scene.world_t(self.foot), self.world_before[f]):
                self.assertAlmostEqual(got, want, places=6, msg="frame %d" % f)

    def test_cycle_is_removed_and_custom_attrs_keep_animating(self):
        self.run_tool()
        tz = self.scene.curves[self.foot + ".translateZ"]
        self.assertEqual((tz.pre, tz.post), ("constant", "constant"))
        roll = self.scene.curves[self.foot + ".footRoll"]
        self.assertEqual(roll.post, "constant")
        for f in range(1, 49):
            self.assertAlmostEqual(roll.value(f), self.roll_before[f], places=6)

    def test_foot_walks_forward_past_the_cycle(self):
        self.run_tool()
        self.assertGreater(self.scene.curves[self.foot + ".translateZ"].value(48), 60.0)

    def test_hold_start_keeps_base_first_frame_value(self):
        self.scene.curves[self.base + ".translateZ"] = Curve({1: 5.0, 49: 101.0})
        self.run_tool(base_mode=self.mod.BASE_HOLD_START)
        self.assertEqual(self.scene.static[self.base + ".translateZ"], 5.0)

    def test_step_still_keys_last_frame(self):
        self.assertEqual(self.mod._frames(1, 48, 5)[-1], 48)

    def test_rejects_missing_inputs(self):
        with self.assertRaises(ValueError):
            self.mod.walk_off_node([], ["layout"], 1, 48)
        with self.assertRaises(ValueError):
            self.mod.walk_off_node(["foot_ik"], [], 1, 48)


if __name__ == "__main__":
    unittest.main()
