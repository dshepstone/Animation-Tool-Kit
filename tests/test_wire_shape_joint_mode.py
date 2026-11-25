"""Wire Shapes Joint Mode against a small simulated joint scene (no Maya needed).

Covers the pure helpers (axis mapping, naming), reading a joint's aim axis
from its world orientation, collecting joints for Single / Multi-Joint mode
and building a named FK control chain with zero groups and constraints.
"""
import importlib.util
import math
from pathlib import Path
import sys
import types
import unittest

SCRIPT = (Path(__file__).resolve().parents[1] / "animation tool kit scripts"
          / "WireShape_Tool_1_0_0" / "wire_shape_tool.py")


def _rot_matrix(rx, ry, rz):
    """Rows = world X/Y/Z axes of a node rotated XYZ (degrees)."""
    def rot(axis, deg):
        c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
        if axis == 0:
            return [[1, 0, 0], [0, c, s], [0, -s, c]]
        if axis == 1:
            return [[c, 0, -s], [0, 1, 0], [s, 0, c]]
        return [[c, s, 0], [-s, c, 0], [0, 0, 1]]

    def mul(a, b):
        return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)]
                for i in range(3)]
    return mul(mul(rot(0, rx), rot(1, ry)), rot(2, rz))


def _apply(rot_deg, vec):
    """Row vector times the rotation matrix (Maya convention)."""
    m = _rot_matrix(*rot_deg)
    return tuple(round(sum(vec[k] * m[k][j] for k in range(3)), 6) for j in range(3))


class Node(object):
    _next = [0]

    def __init__(self, name, ntype, parent=None):
        Node._next[0] += 1
        self.uuid = "UUID-%d" % Node._next[0]
        self.name = name
        self.type = ntype
        self.parent = parent
        self.attrs = {"rotateOrder": 0, "radius": 1.0}
        self.pos = (0.0, 0.0, 0.0)
        self.axes = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
        self.shape = None


class FakeScene(object):
    def __init__(self):
        self.nodes = []
        self.selection = []
        self.constraints = []
        self.rotations = {}     # uuid -> euler baked into the shape
        self.scales = {}

    # -- helpers -----------------------------------------------------------
    def path(self, node):
        parts = []
        while node:
            parts.append(node.name)
            node = node.parent
        return "|" + "|".join(reversed(parts))

    def find(self, key):
        key = key[0] if isinstance(key, (list, tuple)) else key
        for n in self.nodes:
            if key in (n.uuid, n.name, self.path(n)) or self.path(n).endswith("|" + key):
                return n
        raise KeyError(key)

    def add_joint(self, name, parent, pos, axes):
        n = Node(name, "joint", self.find(parent) if parent else None)
        n.pos, n.axes = tuple(pos), [list(r) for r in axes]
        self.nodes.append(n)
        return self.path(n)

    # -- maya.cmds -----------------------------------------------------------
    def ls(self, *args, **kw):
        if kw.get("sl") or kw.get("selection"):
            return list(self.selection)
        items = args[0] if args else []
        items = items if isinstance(items, (list, tuple)) else [items]
        out = []
        for it in items:
            try:
                n = self.find(it)
            except KeyError:
                continue
            if "type" in kw and n.type != kw["type"]:
                continue
            out.append(n.uuid if kw.get("uuid") else self.path(n))
        return out

    def nodeType(self, node):
        return self.find(node).type

    def listRelatives(self, node, **kw):
        n = self.find(node)
        if kw.get("parent"):
            return [self.path(n.parent)] if n.parent else []
        if kw.get("shapes"):
            if n.shape and kw.get("type", n.shape) == n.shape:
                return [self.path(n) + "Shape"]
            return []
        kids = [c for c in self.nodes if c.parent is n]
        if "type" in kw:
            kids = [c for c in kids if c.type == kw["type"]]
        return [self.path(c) for c in kids]

    def xform(self, node, **kw):
        n = self.find(node)
        if kw.get("q"):
            if kw.get("m"):
                return [*n.axes[0], 0, *n.axes[1], 0, *n.axes[2], 0, *n.pos, 1]
            return list(n.pos)
        if "m" in kw:
            m = kw["m"]
            n.axes = [m[0:3], m[4:7], m[8:11]]
            n.pos = tuple(m[12:15])
        if "ro" in kw and n.type == "transform":
            self.rotations[n.uuid] = tuple(kw["ro"])
        if "s" in kw and n.type == "transform":
            self.scales[n.uuid] = kw["s"][0]

    def getAttr(self, plug):
        node, attr = plug.split(".")
        return self.find(node).attrs[attr]

    def setAttr(self, plug, *values, **kw):
        node, attr = plug.split(".")
        self.find(node).attrs[attr] = values[0] if len(values) == 1 else values

    def select(self, *args, **kw):
        self.selection = [] if kw.get("clear") else list(args[0])

    def group(self, *args, **kw):
        n = Node(kw["name"], "group")
        self.nodes.append(n)
        return n.name

    def rename(self, node, new):
        self.find(node).name = new
        return new

    def parent(self, child, parent, **kw):
        c, p = self.find(child), self.find(parent)
        if kw.get("relative"):
            c.pos, c.axes = p.pos, [list(r) for r in p.axes]
        c.parent = p
        return [c.name]

    def delete(self, *args, **kw):
        pass

    def makeIdentity(self, *args, **kw):
        pass

    def warning(self, msg):
        pass

    def orientConstraint(self, ctrl, jnt, **kw):
        self.constraints.append(("orient", self.find(ctrl).name, self.find(jnt).name))

    parentConstraint = orientConstraint


_STUBBED = ("maya", "maya.cmds", "maya.mel", "PySide6", "PySide6.QtWidgets",
            "PySide6.QtCore", "PySide6.QtGui", "shiboken6")


def load_tool(scene):
    """Import the tool against ``scene``; leaves sys.modules as it found it."""
    saved = {k: sys.modules.get(k) for k in _STUBBED}
    try:
        return _load_tool(scene)
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


def _load_tool(scene):
    maya = types.ModuleType("maya")
    maya.cmds = types.ModuleType("maya.cmds")
    for name in dir(scene):
        if not name.startswith("_"):
            setattr(maya.cmds, name, getattr(scene, name))
    maya.mel = types.ModuleType("maya.mel")
    sys.modules.update({"maya": maya, "maya.cmds": maya.cmds, "maya.mel": maya.mel})
    try:
        import PySide6  # noqa: F401
    except ImportError:
        qt = types.ModuleType("PySide6")
        for sub in ("QtWidgets", "QtCore", "QtGui"):
            setattr(qt, sub, types.ModuleType(sub))
            sys.modules["PySide6." + sub] = getattr(qt, sub)
        shib = types.ModuleType("shiboken6")
        shib.wrapInstance = None
        sys.modules.update({"PySide6": qt, "shiboken6": shib})
    spec = importlib.util.spec_from_file_location("wire_shape_tool_under_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


IDENTITY = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
# A vertical chain oriented X-down-the-bone: local X points world +Y.
X_UP = [[0, 1, 0], [-1, 0, 0], [0, 0, 1]]


class PureHelpers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.wst = load_tool(FakeScene())

    def test_axis_align_rotation_maps_every_axis(self):
        axes = [(1, 0, 0), (0, 1, 0), (0, 0, 1), (-1, 0, 0), (0, -1, 0), (0, 0, -1)]
        for src in axes:
            for dst in axes:
                rot = self.wst.axis_align_rotation(src, dst)
                self.assertEqual(_apply(rot, src), tuple(float(c) for c in dst),
                                 "%s -> %s via %s" % (src, dst, rot))

    def test_dominant_axis(self):
        self.assertEqual(self.wst.dominant_axis((0.1, -2.0, 0.5)), (0, -1, 0))
        self.assertIsNone(self.wst.dominant_axis((0, 0, 0)))

    def test_naming_pattern(self):
        f = self.wst.format_control_name
        self.assertEqual(f("FlagPole_#_JNT", 1, "|a|joint1"), "FlagPole_1_JNT")
        self.assertEqual(f("FlagPole_##_CTRL", 3), "FlagPole_03_CTRL")
        self.assertEqual(f("{joint}_CTRL", 1, "|root|ns:spine2"), "spine2_CTRL")
        self.assertEqual(f("", 1, "elbow"), "elbow_CTRL")
        self.assertEqual(f("my ctrl-#", 2), "my_ctrl_2")
        self.assertTrue(self.wst.pattern_needs_number("FK_CTRL"))
        self.assertFalse(self.wst.pattern_needs_number("FK_#_CTRL"))


class JointScene(unittest.TestCase):
    def build_chain(self, axes, count=4):
        scene = FakeScene()
        parent = None
        for i in range(count):
            parent = scene.add_joint("joint%d" % (i + 1), parent, (0, i * 2.0, 0), axes)
        return scene

    def test_aim_axis_reads_orientation(self):
        scene = self.build_chain(X_UP)
        wst = load_tool(scene)
        self.assertEqual(wst.joint_aim_axis("joint1"), ((1, 0, 0), 1.0))
        # End joint: falls back to the bone coming in from the parent.
        self.assertEqual(wst.joint_aim_axis("joint4")[0], (1, 0, 0))

        scene = self.build_chain(IDENTITY)   # unoriented: bone runs world/local +Y
        wst = load_tool(scene)
        self.assertEqual(wst.joint_aim_axis("joint2")[0], (0, 1, 0))

    def test_gather_joints(self):
        scene = self.build_chain(X_UP)
        wst = load_tool(scene)
        names = lambda js: [j.split("|")[-1] for j in js]
        self.assertEqual(names(wst.gather_joints(["joint2"], False)), ["joint2"])
        self.assertEqual(names(wst.gather_joints(["joint1"], True)),
                         ["joint1", "joint2", "joint3"])
        self.assertEqual(names(wst.gather_joints(["joint1"], True, skip_end_joints=False)),
                         ["joint1", "joint2", "joint3", "joint4"])
        self.assertEqual(names(wst.gather_joints(["joint3", "joint1"], True,
                                                 wst.CHAIN_RANGE, False)),
                         ["joint1", "joint2", "joint3"])
        with self.assertRaises(ValueError):
            wst.gather_joints(["joint1"], True, wst.CHAIN_RANGE)

    def test_multi_joint_fk_chain(self):
        scene = self.build_chain(X_UP)
        wst = load_tool(scene)
        for i in range(4):
            scene.find("joint%d" % (i + 1)).attrs["radius"] = 0.5

        def creator():
            n = Node("circleY_CTRL", "transform")
            n.shape = "nurbsCurve"
            scene.nodes.append(n)
            return [n.name]
        shape = wst.ShapeDef("circleY", "Circle Y", creator, [], "", "Primitives")

        joints = wst.gather_joints(["joint1"], True)
        opts = wst.JointModeOptions(multi=True, name_pattern="FlagPole_#_JNT",
                                    constraint=wst.CONSTRAINT_ORIENT)
        built = wst.create_joint_controls(shape, joints, opts)

        ctrls = [scene.find(c) for _, c, _ in built]
        self.assertEqual([c.name for c in ctrls],
                         ["FlagPole_1_JNT", "FlagPole_2_JNT", "FlagPole_3_JNT"])
        for (jnt, c, top), ctrl in zip(built, ctrls):
            j = scene.find(jnt)
            grp = scene.find(top)
            self.assertEqual(grp.name, ctrl.name + "_GRP")
            self.assertIs(ctrl.parent, grp)
            # Control sits on the joint with the joint's axes.
            self.assertEqual(ctrl.pos, j.pos)
            self.assertEqual([list(map(float, r)) for r in ctrl.axes],
                             [list(map(float, r)) for r in j.axes])
            # Circle Y turned so its normal faces the joint's X (down the chain).
            self.assertEqual(_apply(scene.rotations[ctrl.uuid], (0, 1, 0)), (1.0, 0.0, 0.0))
            self.assertAlmostEqual(scene.scales[ctrl.uuid], 1.0)   # 0.5 radius x 2
        # FK hierarchy: each group lives under the previous control.
        self.assertIsNone(scene.find(built[0][2]).parent)
        self.assertIs(scene.find(built[1][2]).parent, ctrls[0])
        self.assertIs(scene.find(built[2][2]).parent, ctrls[1])
        self.assertEqual([c[1:] for c in scene.constraints],
                         [("FlagPole_%d_JNT" % (i + 1), "joint%d" % (i + 1)) for i in range(3)])


if __name__ == "__main__":
    unittest.main()
