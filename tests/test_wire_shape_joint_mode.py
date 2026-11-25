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
        self.warnings = []
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
        if kw.get("shapes"):
            return []
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
        self.warnings.append(msg)

    def objExists(self, node):
        try:
            self.find(node)
            return True
        except KeyError:
            return False

    def _constraint(self, kind, driver, driven):
        d = self.find(driven)
        node = Node("%s_%s1" % (d.name, kind), kind, d)
        self.nodes.append(node)
        self.constraints.append((kind, self.find(driver).name, d.name))
        return [node.name]

    def parentConstraint(self, driver, driven, **kw):
        return self._constraint("parentConstraint", driver, driven)

    def orientConstraint(self, driver, driven, **kw):
        return self._constraint("orientConstraint", driver, driven)

    def pointConstraint(self, driver, driven, **kw):
        return self._constraint("pointConstraint", driver, driven)


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
                                    hierarchy=wst.HIER_PARENT,
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

    # -- helpers for the tests below -----------------------------------------
    def fake_defs(self, scene, wst, keys=("circleY", "cube", "rootControl",
                                          "diamond3D", "square", "halfCircle")):
        defs = {}
        for key in keys:
            def creator(key=key):
                n = Node(key + "_CTRL", "transform")
                n.shape = "nurbsCurve"
                scene.nodes.append(n)
                return [n.name]
            defs[key] = wst.ShapeDef(key, key, creator, [], "", "Primitives")
        wst.shape_defs_by_key = lambda: dict(defs)
        return defs

    def test_parent_constraint_chain_is_flat(self):
        scene = self.build_chain(X_UP)
        wst = load_tool(scene)
        defs = self.fake_defs(scene, wst)
        joints = wst.gather_joints(["joint1"], True)
        opts = wst.JointModeOptions(multi=True, name_pattern="Sign_CTRL",
                                    zero_group=False,   # forced on for a chain
                                    constraint=wst.CONSTRAINT_PARENT)
        self.assertEqual(opts.hierarchy, wst.HIER_CONSTRAINT)   # the default
        built = wst.create_joint_controls(defs["circleY"], joints, opts)

        tops = [scene.find(t) for _, _, t in built]
        ctrls = [scene.find(c) for _, c, _ in built]
        self.assertEqual([c.name for c in ctrls], ["Sign_CTRL_1", "Sign_CTRL_2", "Sign_CTRL_3"])
        # Nothing nested: every group stays at the top of the outliner.
        self.assertEqual([t.name for t in tops],
                         ["Sign_CTRL_1_GRP", "Sign_CTRL_2_GRP", "Sign_CTRL_3_GRP"])
        self.assertTrue(all(t.parent is None for t in tops))
        # Groups follow the control above by parent constraint; joints are
        # parent-constrained to their controls (never parented).
        self.assertEqual(scene.constraints, [
            ("parentConstraint", "Sign_CTRL_1", "Sign_CTRL_2_GRP"),
            ("parentConstraint", "Sign_CTRL_2", "Sign_CTRL_3_GRP"),
            ("parentConstraint", "Sign_CTRL_1", "joint1"),
            ("parentConstraint", "Sign_CTRL_2", "joint2"),
            ("parentConstraint", "Sign_CTRL_3", "joint3"),
        ])
        self.assertEqual(scene.find("joint2").parent.name, "joint1")

    def test_rebuild_skips_joints_that_already_have_the_constraint(self):
        scene = self.build_chain(X_UP)
        wst = load_tool(scene)
        defs = self.fake_defs(scene, wst)
        joints = wst.gather_joints(["joint1"], True)
        opts = wst.JointModeOptions(multi=True, name_pattern="Sign_CTRL",
                                    constraint=wst.CONSTRAINT_PARENT)
        wst.create_joint_controls(defs["circleY"], joints, opts)
        before = len([c for c in scene.constraints if c[2].startswith("joint")])
        wst.create_joint_controls(defs["circleY"], joints, opts)
        after = len([c for c in scene.constraints if c[2].startswith("joint")])
        self.assertEqual(before, after)
        self.assertTrue(any("already has" in w for w in scene.warnings))
        self.assertTrue(any("already exist" in w for w in scene.warnings))

    def test_best_option_and_per_joint_shapes(self):
        scene = FakeScene()
        parent = None
        for i, name in enumerate(("root", "spine1", "head", "head_end")):
            parent = scene.add_joint(name, parent, (0, i * 2.0, 0), X_UP)
        wst = load_tool(scene)
        defs = self.fake_defs(scene, wst)
        self.assertEqual(wst.best_shape_key("|root"), "rootControl")
        self.assertEqual(wst.best_shape_key("L_Clavicle"), "halfCircle")
        self.assertEqual(wst.best_shape_key("spine1"), "circleY")
        self.assertEqual(wst.best_shape_key("joint7", has_children=False), "diamond3D")
        self.assertEqual(wst.best_shape_key("thread"), "circleY")   # 'head' is a word match only

        joints = wst.gather_joints(["root"], True, skip_end_joints=False)
        resolved = wst.resolve_joint_shapes(joints, wst.BEST_SHAPE)
        self.assertEqual([d.key for d in resolved],
                         ["rootControl", "circleY", "cube", "diamond3D"])

        per_joint = ["square", wst.BEST_SHAPE, defs["halfCircle"], "cube"]
        opts = wst.JointModeOptions(multi=True, name_pattern="{joint}_CTRL",
                                    hierarchy=wst.HIER_NONE)
        built = wst.create_joint_controls(per_joint, joints, opts)
        made = [scene.find(c) for _, c, _ in built]
        self.assertEqual([c.name for c in made],
                         ["root_CTRL", "spine1_CTRL", "head_CTRL", "head_end_CTRL"])
        with self.assertRaises(ValueError):
            wst.resolve_joint_shapes(joints, ["square"])


class BatchRename(unittest.TestCase):
    def test_rename_chain_from_root(self):
        scene = FakeScene()
        parent = None
        for i in range(4):
            parent = scene.add_joint("joint%d" % (i + 1), parent, (0, i, 0), X_UP)
        scene.nodes.append(Node("joint2_parentConstraint1", "parentConstraint",
                                scene.find("joint2")))
        wst = load_tool(scene)
        renamed = wst.batch_rename(["joint1"], "FlagPole_#_JNT", hierarchy=True)
        self.assertEqual([r.split("|")[-1] for r in renamed],
                         ["FlagPole_1_JNT", "FlagPole_2_JNT", "FlagPole_3_JNT", "FlagPole_4_JNT"])
        # The constraint under joint2 is another type and keeps its name.
        self.assertTrue(scene.objExists("joint2_parentConstraint1"))

    def test_rename_can_swap_names_and_pad(self):
        scene = FakeScene()
        a = scene.add_joint("b_2", None, (0, 0, 0), X_UP)
        b = scene.add_joint("b_1", None, (1, 0, 0), X_UP)
        wst = load_tool(scene)
        renamed = wst.batch_rename([a, b], "b_#", start=1)
        self.assertEqual([r.split("|")[-1] for r in renamed], ["b_1", "b_2"])
        self.assertEqual(wst.format_rename("Arm_##_JNT", 3), "Arm_03_JNT")
        self.assertEqual(wst.format_rename("L_{name}", 1, "|x|elbow"), "L_elbow")

    def test_search_replace_and_prefix_suffix(self):
        scene = FakeScene()
        j1 = scene.add_joint("joint1", None, (0, 0, 0), X_UP)
        scene.add_joint("joint2", "joint1", (0, 1, 0), X_UP)
        wst = load_tool(scene)
        out = wst.search_replace_names([j1], "joint", "spine", hierarchy=True)
        self.assertEqual([r.split("|")[-1] for r in out], ["spine1", "spine2"])
        out = wst.prefix_suffix_names(["spine1"], "C_", "_JNT", hierarchy=True)
        self.assertEqual([r.split("|")[-1] for r in out], ["C_spine1_JNT", "C_spine2_JNT"])


if __name__ == "__main__":
    unittest.main()
