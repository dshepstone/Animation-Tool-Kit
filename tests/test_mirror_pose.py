"""Mirror Pose: mirror math, naming and a whole-character run (no Maya).

The math tests check the exact mirror rule against independently built
frames. The scene test runs mirror_pose() on a small fake rig that has a
placement control, centre controls and left / right arms whose offset
groups are built differently on each side, then checks the result in world
space: every mirrored control must sit at the mirror image of where its
partner was.
"""
from pathlib import Path
import math
import random
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fake_maya  # noqa: E402

SCRIPT = (Path(__file__).resolve().parents[1] / "animation tool kit scripts"
          / "Mirror_Pose_1_0_0" / "mirror_pose.py")

TRANSLATE = ("translateX", "translateY", "translateZ")
ROTATE = ("rotateX", "rotateY", "rotateZ")
SCALE = ("scaleX", "scaleY", "scaleZ")


class RigScene(object):
    """A tiny DAG evaluator: translate, rotate, rotateOrder, jointOrient."""

    def __init__(self, mp):
        self.mp = mp
        self.nodes = {}           # long name -> data
        self.selection = []
        self.dialogs = []
        self.warnings = []
        self.keys = []
        self.undo_state = True
        self.chunks = []
        self.auto_key = False

    def add(self, name, parent=None, control=True, node_type="transform",
            t=(0, 0, 0), r=(0, 0, 0), ro=0, jo=(0, 0, 0), locked=(),
            custom=None):
        path = (parent or "") + "|" + name
        attrs = {}
        for i, a in enumerate(TRANSLATE):
            attrs[a] = float(t[i])
        for i, a in enumerate(ROTATE):
            attrs[a] = float(r[i])
        for a in SCALE:
            attrs[a] = 1.0
        attrs.update(custom or {})
        self.nodes[path] = {"type": node_type, "parent": parent,
                            "control": control, "attrs": attrs, "ro": ro,
                            "jo": list(jo), "locked": set(locked),
                            "animated": set()}
        return path

    # -- evaluation --------------------------------------------------------
    def local(self, node):
        d = self.nodes[node]
        a = d["attrs"]
        rot = self.mp.euler_to_m3([a[x] for x in ROTATE], d["ro"])
        if d["type"] == "joint":
            rot = self.mp.m3_mul(rot, self.mp.euler_to_m3(d["jo"], 0))
        return rot, [a[x] for x in TRANSLATE]

    def world(self, node):
        rot, t = self.local(node)
        parent = self.nodes[node]["parent"]
        if not parent:
            return rot, t
        prot, pt = self.world(parent)
        wt = self.mp.vec_mul_m3(t, prot)
        return self.mp.m3_mul(rot, prot), [wt[i] + pt[i] for i in range(3)]

    def _split(self, plug):
        node, _, attr = plug.partition(".")
        aliases = {"rotateOrder": "rotateOrder"}
        return node, aliases.get(attr, attr)

    # -- maya.cmds ---------------------------------------------------------
    def ls(self, *args, **kwargs):
        if kwargs.get("selection"):
            return list(self.selection)
        if kwargs.get("type") == "nurbsCurve":
            return [n + "|" + n.split("|")[-1] + "Shape"
                    for n, d in self.nodes.items() if d["control"]]
        return [a for a in args if a in self.nodes]

    def listRelatives(self, node, parent=False, **kwargs):
        if node.endswith("Shape"):
            return [node.rsplit("|", 1)[0]]
        p = self.nodes[node]["parent"]
        return [p] if p else []

    def xform(self, node, query=True, worldSpace=True, matrix=False,
              rotatePivot=False):
        rot, t = self.world(node)
        if matrix:
            return [rot[0][0], rot[0][1], rot[0][2], 0.0,
                    rot[1][0], rot[1][1], rot[1][2], 0.0,
                    rot[2][0], rot[2][1], rot[2][2], 0.0,
                    t[0], t[1], t[2], 1.0]
        return t

    def objExists(self, plug):
        node, attr = self._split(plug)
        return node in self.nodes and (not attr or attr in self.nodes[node]["attrs"])

    def getAttr(self, plug, lock=False, **kwargs):
        node, attr = self._split(plug)
        d = self.nodes[node]
        if lock:
            return attr in d["locked"]
        if attr == "rotateOrder":
            return d["ro"]
        if attr == "jointOrient":
            return [tuple(d["jo"])]
        if attr == "rotateAxis":
            return [(0.0, 0.0, 0.0)]
        return d["attrs"][attr]

    def setAttr(self, plug, value):
        node, attr = self._split(plug)
        d = self.nodes[node]
        if attr in d["locked"]:
            raise RuntimeError("locked")
        d["attrs"][attr] = value

    def listAttr(self, node, **kwargs):
        return list(self.nodes[node]["attrs"])

    def attributeQuery(self, attr, node=None, listDefault=False, exists=False):
        if exists:
            return attr != "offsetParentMatrix"
        return [1.0 if attr.startswith("scale") else 0.0]

    def nodeType(self, node):
        return self.nodes[node]["type"] if node in self.nodes else "animCurveTL"

    def listConnections(self, plug, **kwargs):
        return []

    def autoKeyframe(self, query=False, state=None):
        if query:
            return self.auto_key
        self.auto_key = state

    def undoInfo(self, query=False, state=None, stateWithoutFlush=None,
                 openChunk=False, closeChunk=False, chunkName=None):
        if query:
            return self.undo_state
        if stateWithoutFlush is not None:
            self.undo_state = stateWithoutFlush
        if openChunk:
            self.chunks.append("open")
        if closeChunk:
            self.chunks.append("close")

    def currentUnit(self, **kwargs):
        return "deg"

    def keyframe(self, plug, query=True, keyframeCount=True):
        node, attr = self._split(plug)
        return 2 if attr in self.nodes[node]["animated"] else 0

    def setKeyframe(self, plug):
        self.keys.append(plug)

    def warning(self, msg):
        self.warnings.append(msg)

    def about(self, batch=False):
        return False

    def confirmDialog(self, **kwargs):
        self.dialogs.append(kwargs)

    def inViewMessage(self, **kwargs):
        pass


def load():
    return fake_maya.load_tool(SCRIPT, object(), "mirror_pose_math")


def close(a, b, tol=1e-6):
    return all(abs(x - y) < tol for x, y in zip(a, b))


def m3_close(a, b, tol=1e-6):
    return all(abs(a[i][j] - b[i][j]) < tol for i in range(3) for j in range(3))


class EulerTests(unittest.TestCase):
    def test_round_trip_every_rotate_order(self):
        mp = load()
        rng = random.Random(7)
        for ro in range(6):
            for _ in range(50):
                angles = [rng.uniform(-170, 170) for _ in range(3)]
                m = mp.euler_to_m3(angles, ro)
                back = mp.m3_to_euler(m, ro, hint=angles)
                self.assertTrue(close(back, angles, 1e-6), (ro, angles, back))

    def test_gimbal_lock_still_rebuilds_the_matrix(self):
        mp = load()
        for ro in range(6):
            angles = [0.0, 0.0, 0.0]
            angles[mp.ROTATE_ORDERS[ro][1]] = 90.0
            angles[mp.ROTATE_ORDERS[ro][0]] = 30.0
            m = mp.euler_to_m3(angles, ro)
            back = mp.m3_to_euler(m, ro)
            self.assertTrue(m3_close(mp.euler_to_m3(back, ro), m, 1e-6), ro)

    def test_closest_turn_keeps_curves_continuous(self):
        mp = load()
        m = mp.euler_to_m3([0, 0, 10], 0)
        self.assertTrue(close(mp.m3_to_euler(m, 0, hint=[0, 0, 360]), [0, 0, 370]))


def sample(mp, base=None, r0=(0, 0, 0), ro=0, t0=(0, 0, 0), parent=None):
    base = base or mp.m3_identity()
    return {"base": base, "parent": parent or base, "ra": mp.m3_identity(),
            "ro": ro, "r0": list(r0), "t0": list(t0)}


class MirrorMathTests(unittest.TestCase):
    def setUp(self):
        self.mp = load()
        self.S = self.mp.reflection([1, 0, 0])

    def test_centre_control_flips_across_x(self):
        mp = self.mp
        c = sample(mp)
        rot = mp.mirror_rotation([20, 30, 40], c, c, self.S, hint=[20, 30, 40])
        # Tilting forward (X) stays; turning (Y) and leaning (Z) flip.
        self.assertTrue(close(rot, [20, -30, -40]), rot)
        self.assertTrue(close(mp.mirror_translation([3, 4, 5], c, c, self.S),
                              [-3, 4, 5]))

    def test_behaviour_mirrored_pair_copies_rotation(self):
        mp = self.mp
        left = sample(mp)
        neg = [[-1, 0, 0], [0, -1, 0], [0, 0, -1]]
        right = sample(mp, base=mp.m3_mul(neg, left["base"], self.S))
        rot = mp.mirror_rotation([10, 20, 30], left, right, self.S)
        self.assertTrue(close(rot, [10, 20, 30]), rot)
        self.assertTrue(close(mp.mirror_translation([1, 2, 3], left, right, self.S),
                              [-1, -2, -3]))

    def test_y180_offset_side(self):
        mp = self.mp
        left = sample(mp)
        right = sample(mp, base=mp.euler_to_m3([0, 180, 0]))
        rot = mp.mirror_rotation([10, 20, 30], left, right, self.S)
        m_expected = mp.m3_mul(self.S, mp.euler_to_m3([10, 20, 30]), self.S)
        got = mp.m3_mul(mp.euler_to_m3(rot), right["base"])
        # World result: correction (rest) . S . W_src . S
        c = mp.m3_mul(right["base"], mp.m3_inv(mp.m3_mul(self.S, left["base"], self.S)))
        self.assertTrue(m3_close(got, mp.m3_mul(c, m_expected)))

    def test_random_frames_satisfy_the_mirror_rule(self):
        mp = self.mp
        rng = random.Random(3)

        def rnd():
            return [rng.uniform(-180, 180) for _ in range(3)]

        for _ in range(100):
            S = mp.reflection([rng.uniform(-1, 1) for _ in range(3)])
            src = sample(mp, base=mp.euler_to_m3(rnd(), rng.randrange(6)),
                         r0=rnd(), ro=rng.randrange(6))
            dst = sample(mp, base=mp.euler_to_m3(rnd(), rng.randrange(6)),
                         r0=rnd(), ro=rng.randrange(6))
            src["ra"] = mp.euler_to_m3(rnd())
            dst["ra"] = mp.euler_to_m3(rnd())
            pose = rnd()
            rot = mp.mirror_rotation(pose, src, dst, S)

            def world(s, r):
                return mp.m3_mul(s["ra"], mp.euler_to_m3(r, s["ro"]), s["base"])

            ws, wd = world(src, pose), world(dst, rot)
            ws0, wd0 = world(src, src["r0"]), world(dst, dst["r0"])
            lhs = mp.m3_mul(wd, mp.m3_inv(mp.m3_mul(S, ws, S)))
            rhs = mp.m3_mul(wd0, mp.m3_inv(mp.m3_mul(S, ws0, S)))
            self.assertTrue(m3_close(lhs, rhs, 1e-6))
            # At rest the mirror gives the partner's rest pose.
            rest = mp.mirror_rotation(src["r0"], src, dst, S)
            self.assertTrue(m3_close(world(dst, rest), wd0, 1e-6))

    def test_mirror_plane_fit(self):
        mp = self.mp
        self.assertEqual(mp.fit_mirror_normal([]), [1.0, 0.0, 0.0])
        pairs = [([0.1, 5, 4], [0.1, 5, -4]), ([0, 1, 2], [0, 1, -2])]
        self.assertEqual(mp.fit_mirror_normal(pairs), [0.0, 0.0, 1.0])
        diag = mp.fit_mirror_normal([([1, 0, 1], [-1, 0, -1])])
        self.assertTrue(close(diag, [math.sqrt(0.5), 0, math.sqrt(0.5)]))


class NamingTests(unittest.TestCase):
    def setUp(self):
        self.mp = load()

    def test_sides(self):
        side = self.mp.side_of
        self.assertEqual(side("lf_arm_ctrl"), "left")
        self.assertEqual(side("arm_rt_ctrl"), "right")
        self.assertEqual(side("L_hand"), "left")
        self.assertEqual(side("footIK_R"), "right")
        self.assertEqual(side("armLeft_ctrl"), "left")
        self.assertEqual(side("handRT_ctrl"), "right")
        self.assertEqual(side("shirt_ctrl"), "middle")
        self.assertEqual(side("spine_pelvisMain_ctrl"), "middle")
        self.assertEqual(side("chest_ctrl"), "middle")
        self.assertEqual(side("armL"), "left")
        self.assertEqual(side("armR_ctrl"), "right")
        self.assertEqual(side("legL1_ctrl"), "left")
        self.assertEqual(side("headLook_ctrl"), "middle")
        self.assertEqual(side("spineIK_ctrl"), "middle")

    def test_partner_names_keep_case(self):
        cands = self.mp.partner_candidates
        self.assertEqual(cands("lf_arm_ctrl")[0], "rt_arm_ctrl")
        self.assertIn("L_hand", cands("R_hand"))
        self.assertIn("armRight_ctrl", cands("armLeft_ctrl"))
        self.assertEqual(cands("spine_ctrl"), [])
        self.assertEqual(cands("armL_ctrl"), ["armR_ctrl"])

    def test_placement_names(self):
        p = self.mp.is_placement_name
        for name in ("world_ctrl", "Main", "global01_ctl", "worldCtrl",
                     "root_ctrl", "C_master_CTL"):
            self.assertTrue(p(name), name)
        for name in ("spine_pelvisMain_ctrl", "cog_ctrl", "chest_ctrl",
                     "rootsy_ctrl"):
            self.assertFalse(p(name), name)


class SceneTests(unittest.TestCase):
    def build(self):
        mp_math = load()
        scene = RigScene(mp_math)
        mp = fake_maya.load_tool(SCRIPT, scene, "mirror_pose_scene")
        scene.mp = mp
        ns = "Delta_rig:"
        world = scene.add(ns + "world_ctrl", t=(5, 0, 2), r=(0, 30, 0))
        cog = scene.add(ns + "cog_ctrl", world, t=(1, 10, 0.5), r=(5, 10, 15),
                        ro=2)
        chest = scene.add(ns + "spine_chest_ctrl", cog, t=(0, 3, 0),
                          r=(12, -8, 20))
        head = scene.add(ns + "head_ctrl", chest, t=(0, 2, 0), r=(-10, 25, 5),
                         ro=4)
        # Left arm: plain offset group. Right arm: offset rotated 180 on Y
        # (a different build on each side).
        lgrp = scene.add(ns + "lf_arm_grp", chest, control=False, t=(2, 1, 0))
        rgrp = scene.add(ns + "rt_arm_grp", chest, control=False, t=(-2, 1, 0),
                         r=(0, 180, 0))
        larm = scene.add(ns + "lf_arm_ctrl", lgrp, r=(30, 40, -50),
                         t=(0.2, 0.1, 0.3), custom={"fingerCurl": 4.0})
        rarm = scene.add(ns + "rt_arm_ctrl", rgrp, r=(-10, 5, 60),
                         t=(0.0, -0.4, 0.1), custom={"fingerCurl": -2.0})
        # Joint control with a joint orient, behaviour mirrored.
        lleg = scene.add(ns + "lf_leg_fk", cog, node_type="joint",
                         t=(1, -1, 0), jo=(0, 0, -90), r=(10, 20, 30))
        rleg = scene.add(ns + "rt_leg_fk", cog, node_type="joint",
                         t=(-1, -1, 0), jo=(180, 0, 90), r=(-4, 2, 8))
        scene.selection = [head]
        return scene, mp, {"world": world, "cog": cog, "chest": chest,
                           "head": head, "larm": larm, "rarm": rarm,
                           "lleg": lleg, "rleg": rleg}

    def rest_worlds(self, scene, nodes):
        saved = {n: dict(scene.nodes[n]["attrs"]) for n in scene.nodes}
        for n, d in scene.nodes.items():
            if d["control"]:
                for a in TRANSLATE + ROTATE:
                    d["attrs"][a] = 0.0
        out = {k: scene.world(v) for k, v in nodes.items()}
        for n in scene.nodes:
            scene.nodes[n]["attrs"] = saved[n]
        return out

    def test_whole_pose_is_mirrored_in_character_space(self):
        scene, mp, n = self.build()
        rest = self.rest_worlds(scene, n)
        before = {k: scene.world(v) for k, v in n.items()}
        curl = {k: scene.nodes[n[k]]["attrs"]["fingerCurl"] for k in ("larm", "rarm")}
        world_before = dict(scene.nodes[n["world"]]["attrs"])

        self.assertTrue(mp.mirror_pose())
        self.assertEqual(scene.dialogs, [])
        self.assertEqual(scene.chunks, ["open", "close"])
        self.assertTrue(scene.undo_state)
        # The placement control is left alone.
        self.assertEqual(scene.nodes[n["world"]]["attrs"], world_before)

        # Character space = world control's rest frame (identity) so we can
        # check in "character" coordinates by undoing the world control.
        wrot, wt = scene.world(n["world"])
        inv = mp.m3_inv(wrot)
        S = mp.reflection([1, 0, 0])

        def char_space(frame):
            rot, t = frame
            local_t = mp.vec_mul_m3([t[i] - wt[i] for i in range(3)], inv)
            return mp.m3_mul(rot, inv), local_t

        pairs = [("cog", "cog"), ("chest", "chest"), ("head", "head"),
                 ("larm", "rarm"), ("rarm", "larm"), ("lleg", "rleg"),
                 ("rleg", "lleg")]
        after = {k: scene.world(v) for k, v in n.items()}
        for src, dst in pairs:
            s_rot, s_t = char_space(before[src])
            d_rot, d_t = char_space(after[dst])
            self.assertTrue(close(d_t, mp.vec_mul_m3(s_t, S), 1e-6),
                            (src, dst, s_t, d_t))
            # Rest correction between the two sides' frames.
            c = mp.m3_mul(rest[dst][0],
                          mp.m3_inv(mp.m3_mul(S, rest[src][0], S)))
            self.assertTrue(m3_close(d_rot, mp.m3_mul(c, S, s_rot, S), 1e-6),
                            (src, dst))

        # Custom attributes swap sides.
        self.assertEqual(scene.nodes[n["larm"]]["attrs"]["fingerCurl"], curl["rarm"])
        self.assertEqual(scene.nodes[n["rarm"]]["attrs"]["fingerCurl"], curl["larm"])

    def test_mirroring_twice_gives_the_pose_back(self):
        scene, mp, n = self.build()
        before = {k: dict(scene.nodes[v]["attrs"]) for k, v in n.items()}
        mp.mirror_pose()
        mp.mirror_pose()
        for k, v in n.items():
            for a, val in before[k].items():
                self.assertAlmostEqual(scene.nodes[v]["attrs"][a], val, 6, (k, a))

    def test_auto_key_keys_animated_channels_only(self):
        scene, mp, n = self.build()
        scene.auto_key = True
        scene.nodes[n["cog"]]["animated"].add("rotateY")
        mp.mirror_pose()
        self.assertEqual(scene.keys, [n["cog"] + ".rotateY"])
        self.assertTrue(scene.auto_key)

    def test_locked_channels_are_reported(self):
        scene, mp, n = self.build()
        scene.nodes[n["head"]]["locked"].add("rotateY")
        mp.mirror_pose()
        # Logged to the Script Editor, not a pop-up; the channel is untouched.
        self.assertEqual(scene.dialogs, [])
        self.assertEqual(scene.nodes[n["head"]]["attrs"]["rotateY"], 25.0)
        self.assertEqual(scene.nodes[n["head"]]["attrs"]["rotateZ"], -5.0)

    def test_one_sided_control_flips_in_place_without_a_popup(self):
        scene, mp, n = self.build()
        hair = scene.add("Delta_rig:R_hair_E0_Ik_ctrl", n["head"],
                         t=(-0.5, 1, 0), r=(10, 20, 30))
        mp.mirror_pose()
        self.assertEqual(scene.dialogs, [])
        a = scene.nodes[hair]["attrs"]
        self.assertTrue(close([a["rotateX"], a["rotateY"], a["rotateZ"]],
                              [10, -20, -30]))
        self.assertAlmostEqual(a["translateX"], 0.5)

    def test_auto_key_comes_back_when_rest_pose_fails(self):
        scene, mp, n = self.build()
        scene.auto_key = True
        real = scene.setAttr

        def refuse(plug, value):
            raise RuntimeError("refused")
        scene.setAttr = refuse
        self.assertIsNone(mp.mirror_pose())
        scene.setAttr = real
        self.assertTrue(scene.auto_key)
        self.assertTrue(scene.undo_state)
        self.assertTrue(scene.dialogs)

    def test_selected_only_leaves_the_rest(self):
        scene, mp, n = self.build()
        scene.selection = [n["larm"]]
        chest = dict(scene.nodes[n["chest"]]["attrs"])
        rarm_before = scene.nodes[n["rarm"]]["attrs"]["rotateX"]
        mp.mirror_selected()
        self.assertEqual(scene.nodes[n["chest"]]["attrs"], chest)
        self.assertNotEqual(scene.nodes[n["rarm"]]["attrs"]["rotateX"], rarm_before)

    def test_nothing_selected_pops_up(self):
        scene, mp, n = self.build()
        scene.selection = []
        self.assertIsNone(mp.mirror_pose())
        self.assertEqual(len(scene.dialogs), 1)
        self.assertIn("Nothing selected", scene.dialogs[0]["title"])

    def test_unexpected_error_pops_up_and_restores_undo(self):
        scene, mp, n = self.build()

        def boom(*a, **k):
            raise RuntimeError("bad node")
        scene.xform = boom
        self.assertIsNone(mp.mirror_pose())
        self.assertTrue(scene.undo_state)
        self.assertTrue(scene.dialogs)


if __name__ == "__main__":
    unittest.main()
