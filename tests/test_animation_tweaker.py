"""Animation Tweaker without Maya: the maths, keying plans, metadata and the
engine's blendShape bookkeeping against a small fake ``maya.cmds``.

Run:  python -m unittest discover -s tests -p "test_animation_tweaker.py"
"""
import ast
import importlib
import json
import math
from pathlib import Path
import random
import sys
import types
import unittest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIR = ROOT / "animation tool kit scripts" / "Animation_Tweaker"
SOURCE = PACKAGE_DIR / "atk_tweaker"
if str(PACKAGE_DIR) not in sys.path:
    sys.path.insert(0, str(PACKAGE_DIR))

from atk_tweaker import core  # noqa: E402  (core never imports Maya)


def close(test, a, b, places=6):
    test.assertEqual(len(a), len(b))
    for x, y in zip(a, b):
        test.assertAlmostEqual(x, y, places=places)


def grid(n=5, spacing=1.0):
    """An n x n plane in XZ, faces as quads."""
    points = [(x * spacing, 0.0, z * spacing) for z in range(n) for x in range(n)]
    faces = []
    for z in range(n - 1):
        for x in range(n - 1):
            a = z * n + x
            faces.append([a, a + n, a + n + 1, a + 1])
    return points, faces


# ---------------------------------------------------------------------------
# Deltas
# ---------------------------------------------------------------------------

class DeltaTests(unittest.TestCase):
    def test_delta_is_sparse_and_masked(self):
        base = [(0, 0, 0), (1, 0, 0), (2, 0, 0)]
        sculpt = [(0, 0, 0), (1, 1, 0), (2, 2, 0)]
        self.assertEqual(core.compute_delta(base, sculpt), {1: (0, 1, 0), 2: (0, 2, 0)})
        masked = core.compute_delta(base, sculpt, mask={1: 0.5})
        self.assertEqual(masked, {1: (0, 0.5, 0)})

    def test_topology_change_is_reported(self):
        with self.assertRaises(ValueError):
            core.compute_delta([(0, 0, 0)], [(0, 0, 0), (1, 1, 1)])

    def test_scale_add_and_refine(self):
        d = {0: (1.0, 0.0, 0.0), 3: (0.0, 2.0, 0.0)}
        self.assertEqual(core.scale_delta(d, 2.0), {0: (2.0, 0.0, 0.0), 3: (0.0, 4.0, 0.0)})
        self.assertEqual(core.scale_delta(d, 0.0), {})
        summed = core.add_deltas(d, {0: (-1.0, 0.0, 0.0), 5: (0.0, 0.0, 1.0)})
        self.assertEqual(summed, {3: (0.0, 2.0, 0.0), 5: (0.0, 0.0, 1.0)})
        # A correction sculpted while the tweak shows at 0.5 counts double.
        refined = core.refine_delta(d, {0: (0.5, 0.0, 0.0)}, 0.5)
        self.assertEqual(refined[0], (2.0, 0.0, 0.0))
        with self.assertRaises(ValueError):
            core.refine_delta(d, {0: (1.0, 0.0, 0.0)}, 0.0)

    def test_refined_tweak_matches_the_sculpt_at_that_weight(self):
        base = [(0.0, 0.0, 0.0)] * 3
        tweak = {1: (0.0, 1.0, 0.0)}
        weight = 0.4
        shown = core.apply_delta(base, tweak, weight)
        sculpt = list(shown)
        sculpt[1] = (0.0, 0.9, 0.3)
        refined = core.refine_delta(tweak, core.compute_delta(shown, sculpt), weight)
        close(self, core.apply_delta(base, refined, weight)[1], sculpt[1])

    def test_component_ranges_round_trip(self):
        indices = [0, 1, 2, 5, 7, 8, 100]
        comps = core.compress_indices(indices)
        self.assertEqual(comps, ["vtx[0:2]", "vtx[5]", "vtx[7:8]", "vtx[100]"])
        self.assertEqual(core.expand_components(comps), indices)
        self.assertEqual(core.expand_components(["|grp|body.vtx[3:4]", "junk"]), [3, 4])
        self.assertEqual(core.compress_indices([3, 4], prefix="f"), ["f[3:4]"])

    def test_target_arrays_round_trip(self):
        delta = {4: (0.1, 0.2, 0.3), 1: (1.0, 0.0, -1.0), 2: (0.0, 0.5, 0.0)}
        comps, points = core.delta_to_target(delta)
        self.assertEqual(comps, ["vtx[1:2]", "vtx[4]"])
        self.assertEqual(points[0], (1.0, 0.0, -1.0, 1.0))
        self.assertEqual(core.target_to_delta(comps, points), delta)
        self.assertEqual(core.delta_to_target({}), ([], []))
        with self.assertRaises(ValueError):
            core.target_to_delta(["vtx[0:3]"], [(0, 0, 0, 1)])


# ---------------------------------------------------------------------------
# Inflate and relax
# ---------------------------------------------------------------------------

class ShapeTests(unittest.TestCase):
    def test_plane_normals_point_up(self):
        points, faces = grid(3)
        for n in core.vertex_normals(points, faces):
            close(self, (abs(n[0]), abs(n[1]), abs(n[2])), (0.0, 1.0, 0.0))

    def test_inflate_moves_along_normals_by_mask(self):
        points = [(1, 0, 0), (0, 1, 0), (0, 0, 1)]
        normals = [(1, 0, 0), (0, 1, 0), (0, 0, 1)]
        delta = core.inflate_delta(points, normals, 0.5, mask={0: 1.0, 2: 0.5})
        self.assertEqual(delta, {0: (0.5, 0, 0), 2: (0, 0, 0.25)})
        deflate = core.inflate_delta(points, normals, -0.2)
        close(self, deflate[1], (0, -0.2, 0))

    def test_inflate_sphere_grows_radius(self):
        ring = [(math.cos(a), math.sin(a), 0.0) for a in (0, 1, 2, 3)]
        normals = [core.v_normalize(p) for p in ring]
        moved = core.apply_delta(ring, core.inflate_delta(ring, normals, 0.25))
        for p in moved:
            self.assertAlmostEqual(core.v_length(p), 1.25)

    def test_relax_smooths_a_spike(self):
        points, faces = grid(5)
        adjacency = core.adjacency_from_faces(len(points), faces)
        self.assertEqual(adjacency[12], [7, 11, 13, 17])
        spiked = list(points)
        spiked[12] = (2.0, 1.0, 2.0)
        relaxed = core.relax_points(spiked, adjacency, iterations=1, strength=1.0)
        self.assertAlmostEqual(relaxed[12][1], 0.0)          # pulled to the neighbours' average
        weaker = core.relax_points(spiked, adjacency, iterations=1, strength=0.5)
        self.assertAlmostEqual(weaker[12][1], 0.5)
        more = core.relax_points(spiked, adjacency, iterations=10, strength=0.5)
        self.assertLess(max(abs(p[1]) for p in more), 0.5)

    def test_relax_respects_the_mask(self):
        points, faces = grid(5)
        adjacency = core.adjacency_from_faces(len(points), faces)
        spiked = list(points)
        spiked[12] = (2.0, 1.0, 2.0)
        delta = core.relax_delta(spiked, adjacency, 3, 0.5, mask={7: 1.0})
        self.assertEqual(set(delta), {7})                       # only the masked vertex moves
        self.assertGreater(delta[7][1], 0.0)                    # toward the spike
        self.assertEqual(core.relax_delta(spiked, adjacency, 3, 0.0), {})

    def test_relax_keeps_a_flat_grid_flat(self):
        points, faces = grid(4)
        adjacency = core.adjacency_from_faces(len(points), faces)
        for p in core.relax_points(points, adjacency, 5, 0.7):
            self.assertAlmostEqual(p[1], 0.0)


# ---------------------------------------------------------------------------
# Temporal filtering
# ---------------------------------------------------------------------------

class TemporalTests(unittest.TestCase):
    def test_kernel_is_normalised_and_symmetric(self):
        kernel = core.gaussian_kernel(2.0)
        self.assertEqual(len(kernel), 13)
        self.assertAlmostEqual(sum(kernel), 1.0)
        close(self, kernel, list(reversed(kernel)))
        self.assertEqual(core.gaussian_kernel(0), [1.0])

    def test_constant_and_linear_motion_are_kept(self):
        still = [[(1.0, 2.0, 3.0)] for _ in range(10)]
        self.assertEqual(core.smooth_motion_deltas(still, 2.0), [{}] * 10)
        moving = [[(float(f), 0.0, 0.0)] for f in range(20)]
        smoothed = core.temporal_gaussian(moving, 1.5)
        for f in range(5, 15):                                  # away from the clamped ends
            self.assertAlmostEqual(smoothed[f][0][0], float(f))

    def test_jitter_is_reduced_and_mask_applies(self):
        rng = random.Random(4)
        series = [[(rng.uniform(-1, 1), 0.0, 0.0), (rng.uniform(-1, 1), 0.0, 0.0)] for _ in range(40)]
        smoothed = core.temporal_gaussian(series, 2.0)

        def roughness(frames, i):
            return sum(abs(frames[f + 1][i][0] - frames[f][i][0]) for f in range(len(frames) - 1))
        self.assertLess(roughness(smoothed, 0), roughness(series, 0) * 0.4)
        deltas = core.smooth_motion_deltas(series, 2.0, mask={0: 0.5})
        for frame, delta in zip(range(40), deltas):
            self.assertNotIn(1, delta)
            if 0 in delta:
                expected = (smoothed[frame][0][0] - series[frame][0][0]) * 0.5
                self.assertAlmostEqual(delta[0][0], expected)


# ---------------------------------------------------------------------------
# Matrices and surfaces
# ---------------------------------------------------------------------------

def translate_scale(t, s=1.0):
    return (s, 0, 0, 0, 0, s, 0, 0, 0, 0, s, 0, t[0], t[1], t[2], 1)


def rotate_z(angle, t=(0, 0, 0)):
    c, s = math.cos(angle), math.sin(angle)
    return (c, s, 0, 0, -s, c, 0, 0, 0, 0, 1, 0, t[0], t[1], t[2], 1)


class MatrixAndSurfaceTests(unittest.TestCase):
    def test_inverse_and_object_space(self):
        m = core.mat_mult(rotate_z(0.7), translate_scale((3, -2, 5), 2.0))
        close(self, core.mat_mult(m, core.mat_inverse(m)), core.IDENTITY)
        world = {0: (2.0, 0.0, 0.0)}
        local = core.world_delta_to_object(world, m)
        close(self, core.xform_vector(local[0], m), world[0])
        close(self, core.xform_point((1, 0, 0), translate_scale((1, 2, 3))), (2, 2, 3))

    def test_closest_point_on_triangle_regions(self):
        a, b, c = (0, 0, 0), (2, 0, 0), (0, 2, 0)
        q, bary = core.closest_point_on_triangle((0.5, 0.5, 3), a, b, c)
        close(self, q, (0.5, 0.5, 0))
        close(self, core.barycentric_point([a, b, c], (0, 1, 2), bary), q)
        q, bary = core.closest_point_on_triangle((-1, -1, 0), a, b, c)
        self.assertEqual(q, a)
        q, _bary = core.closest_point_on_triangle((3, 3, 0), a, b, c)
        close(self, q, (1, 1, 0))

    def test_stick_follows_a_moving_driver(self):
        driver = [(0, 0, 0), (2, 0, 0), (0, 2, 0), (2, 2, 0)]
        tris = [(0, 1, 2), (1, 3, 2)]
        point = (0.5, 0.5, 0.25)
        binding = core.bind_to_surface(point, driver, tris)
        close(self, core.follow_surface(binding, driver, tris), point)
        m = rotate_z(math.pi / 2, (5, 1, 0))
        moved = [core.xform_point(p, m) for p in driver]
        close(self, core.follow_surface(binding, moved, tris), core.xform_point(point, m))

    def test_push_out(self):
        surface, normal = (0, 0, 0), (0, 1, 0)
        close(self, core.push_out_point((1, -0.5, 0), surface, normal, 0.1), (1, 0.1, 0))
        self.assertEqual(core.push_out_point((1, 0.5, 0), surface, normal, 0.1), (1, 0.5, 0))
        close(self, core.push_out_point((0, 0.05, 0), surface, (0, 2, 0), 0.1), (0, 0.1, 0))


# ---------------------------------------------------------------------------
# Keying plans
# ---------------------------------------------------------------------------

class KeyingTests(unittest.TestCase):
    def test_pulse(self):
        self.assertEqual(core.pulse_keys(10, 3, 5), [(7.0, 0.0), (10.0, 1.0), (15.0, 0.0)])
        self.assertEqual(core.pulse_keys(10, 0, 0), [(9.0, 0.0), (10.0, 1.0), (11.0, 0.0)])

    def test_sequence_neighbours_crossfade(self):
        plan = core.sequence_plan([(4, 20), (2, 10), (7, 35)])
        self.assertEqual(plan[2], [(10.0, 1.0), (20.0, 0.0)])
        self.assertEqual(plan[4], [(10.0, 0.0), (20.0, 1.0), (35.0, 0.0)])
        self.assertEqual(plan[7], [(20.0, 0.0), (35.0, 1.0)])
        for frame in (10, 12.5, 15, 20, 27, 35):
            total = sum(core.evaluate_linear(keys, frame) for keys in plan.values())
            self.assertAlmostEqual(total, 1.0)
        # Ends hold: the first pose is fully on before it, the last after it.
        self.assertEqual(core.evaluate_linear(plan[2], 0), 1.0)
        self.assertEqual(core.evaluate_linear(plan[7], 50), 1.0)

    def test_effect_levels_fade_out_at_the_ends(self):
        plan = core.sequence_plan([(0, 1), (1, 2), (2, 3)], fade_ends=True)
        self.assertEqual(plan[0][0], (0.0, 0.0))
        self.assertEqual(plan[2][-1], (4.0, 0.0))
        self.assertEqual(core.evaluate_linear(plan[0], -5), 0.0)
        single = core.sequence_plan([(9, 12)], fade_ends=True)
        self.assertEqual(single[9], [(11.0, 0.0), (12.0, 1.0), (13.0, 0.0)])
        self.assertEqual(core.sequence_plan([(9, 12)]), {9: [(12.0, 1.0)]})

    def test_duplicate_frames_are_rejected(self):
        with self.assertRaises(ValueError):
            core.sequence_plan([(0, 5), (1, 5)])

    def test_levels_are_independent_and_hold_finds_previous(self):
        meta = core.empty_metadata()
        meta["targets"][0] = core.make_entry("a", mode=core.MODE_SEQUENCE, frame=10, layer="L1")
        meta["targets"][1] = core.make_entry("b", mode=core.MODE_SEQUENCE, frame=20, layer="L1")
        meta["targets"][2] = core.make_entry("c", mode=core.MODE_SEQUENCE, frame=15, layer="L2")
        meta["targets"][3] = core.make_entry("d", mode=core.MODE_STATIC)
        meta["targets"][4] = core.make_entry("e", mode=core.MODE_PULSE, frame=3)
        self.assertEqual(core.level_entries(meta, "L1"), [(0, 10.0), (1, 20.0)])
        self.assertEqual(core.level_entries(meta, "L2"), [(2, 15.0)])
        self.assertEqual(core.previous_pose(core.level_entries(meta, "L1"), 18), 0)
        self.assertEqual(core.previous_pose(core.level_entries(meta, "L1"), 25), 1)
        self.assertIsNone(core.previous_pose(core.level_entries(meta, "L1"), 10))
        self.assertEqual(core.find_sequence_target(meta, "L1", 20.0), 1)
        self.assertIsNone(core.find_sequence_target(meta, "L2", 20.0))
        self.assertEqual(core.targets_to_mute(meta, core.MUTE_NONE), [])
        self.assertEqual(core.targets_to_mute(meta, core.MUTE_ALL), [0, 1, 2, 3, 4])
        self.assertEqual(core.targets_to_mute(meta, core.MUTE_STATIC), [3, 4])
        self.assertEqual(core.targets_to_mute(meta, core.MUTE_SEQUENCE), [0, 1, 2])
        self.assertEqual(core.targets_to_mute(meta, core.MUTE_LEVEL, "L2"), [2])


# ---------------------------------------------------------------------------
# Metadata and names
# ---------------------------------------------------------------------------

class MetadataTests(unittest.TestCase):
    def test_round_trip(self):
        meta = core.empty_metadata()
        meta["targets"][3] = core.make_entry("brow fix", core.KIND_SCULPT, core.MODE_PULSE, 12, "pulse", 2, 4)
        meta["targets"][10] = core.make_entry("smooth", core.KIND_SMOOTH, core.MODE_SEQUENCE, 5, "fx_smooth_motion")
        text = core.encode_metadata(meta)
        self.assertEqual(json.loads(text)["version"], core.METADATA_VERSION)
        self.assertEqual(core.decode_metadata(text), meta)

    def test_bad_data_gives_an_empty_record(self):
        for text in (None, "", "not json", "[1, 2]", '{"targets": 4}'):
            self.assertEqual(core.decode_metadata(text), core.empty_metadata())
        loose = core.decode_metadata('{"targets": {"x": {}, "2": {"mode": "weird"}}}')
        self.assertEqual(list(loose["targets"]), [2])
        self.assertEqual(loose["targets"][2]["mode"], core.MODE_STATIC)

    def test_aliases_are_valid_and_unique(self):
        self.assertEqual(core.safe_alias("brow fix!", []), "tw_brow_fix_")
        self.assertEqual(core.safe_alias("3d", []), "tw__3d")
        self.assertEqual(core.safe_alias("a", ["tw_a", "tw_a_2"]), "tw_a_3")
        self.assertEqual(core.frame_label("sculpt", 12.5, "L1"), "sculpt_L1_f12p5")
        self.assertEqual(core.frame_label("pin", -3, "fx_pin"), "pin_fm3")


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

class UtilityTests(unittest.TestCase):
    def test_camera_cycle(self):
        cams = [("|front", True), ("|persp", False), ("|shotCam", False), ("|top", True)]
        self.assertEqual(core.next_camera(cams, "|persp"), "|shotCam")
        self.assertEqual(core.next_camera(cams, "|shotCam"), "|persp")
        self.assertEqual(core.next_camera(cams, "|top"), "|persp")
        self.assertEqual(core.next_camera(cams, "|persp", skip_ortho=False), "|shotCam")
        self.assertEqual(core.next_camera(cams, "|shotCam", skip_ortho=False), "|top")
        self.assertIsNone(core.next_camera([("|top", True)], "|top"))

    def test_colours(self):
        self.assertEqual(core.rgb_to_hex(core.hex_to_rgb("#3a7bd5")), "#3a7bd5")
        first = core.random_colour(random.Random(1))
        self.assertEqual(first, core.random_colour(random.Random(1)))
        self.assertRegex(first, r"^#[0-9a-f]{6}$")
        for colour in core.PALETTE:
            core.hex_to_rgb(colour)

    def test_channel_clipboard(self):
        text = core.encode_clipboard({"|rig|arm_ctl": {"tx": 1, "visibility": True},
                                      "leg_ctl": {"ry": 45.0}})
        clip = core.decode_clipboard(text)
        self.assertEqual(clip["|rig|arm_ctl"], {"tx": 1.0, "visibility": True})
        self.assertEqual(core.decode_clipboard("print('no')"), {})
        self.assertEqual(core.decode_clipboard('{"format": "other"}'), {})
        plan = core.paste_plan(clip, ["|b:leg_ctl", "|other"])
        self.assertEqual(plan[0], ("|b:leg_ctl", "ry", 45.0))
        one = core.paste_plan({"src": {"tx": 2.0}}, ["|a", "|b"])
        self.assertEqual(one, [("|a", "tx", 2.0), ("|b", "tx", 2.0)])
        with self.assertRaises(ValueError):
            core.encode_clipboard({"n": {"x": object()}})

    def test_alembic_job_and_version_names(self):
        job = core.abc_job(["|char|body"], "C:\\caches\\shot 01\\body_v002.abc", 1, 48,
                           attrs=("atkCacheSource",))
        self.assertIn("-frameRange 1 48", job)
        self.assertIn("-attr atkCacheSource", job)
        self.assertIn("-root |char|body", job)
        self.assertTrue(job.endswith('-file "C:/caches/shot 01/body_v002.abc"'))
        with self.assertRaises(ValueError):
            core.abc_job([], "x.abc", 1, 2)
        self.assertEqual(core.version_label("/a/body_v002.ABC", []), "body_v002")
        self.assertEqual(core.version_label("/a/body_v002.abc", ["body_v002"]), "body_v002_2")

    def test_falloff_presets(self):
        self.assertEqual(set(core.FALLOFF_NAMES), set(core.FALLOFF_PRESETS))
        for points in core.FALLOFF_PRESETS.values():
            self.assertEqual(points[0][:2], (0.0, 1.0))
            self.assertEqual(points[-1][:2], (1.0, 0.0))
            self.assertEqual(list(points), sorted(points))


class SourceRulesTests(unittest.TestCase):
    def test_no_exec_or_eval_and_no_script_files(self):
        for path in SOURCE.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    self.assertNotIn(node.func.id, ("exec", "eval", "compile", "execfile"),
                                     "%s calls %s()" % (path.name, node.func.id))
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("open(", text.replace("QtWidgets.QFileDialog", ""),
                             "%s writes files; Animation Tweaker keeps data in the scene or an optionVar" % path.name)

    def test_core_does_not_import_maya_or_qt(self):
        tree = ast.parse((SOURCE / "core.py").read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [a.name for a in node.names] + [getattr(node, "module", "") or ""]
                for name in names:
                    self.assertFalse(name.startswith(("maya", "PySide", "shiboken")), name)

    def test_package_files_exist(self):
        for name in ("__init__.py", "qt_compat.py", "core.py", "engine.py", "ui.py",
                     "resources/help.html", "assets/animation_tweaker_32.png",
                     "assets/animation_tweaker.svg"):
            self.assertTrue((SOURCE / name).is_file(), name)
        self.assertTrue((PACKAGE_DIR / "README.md").is_file())
        self.assertTrue((PACKAGE_DIR / "DESIGN.md").is_file())


# ---------------------------------------------------------------------------
# Engine against a fake maya.cmds
# ---------------------------------------------------------------------------

class FakeCmds(object):
    """Just enough of maya.cmds for the tweak-node bookkeeping."""

    def __init__(self):
        self.types = {"|body": "transform", "|body|bodyShape": "mesh"}
        self.parents = {"|body|bodyShape": "|body"}
        self.values = {"|body.visibility": True}
        self.attrs = {"|body": ["visibility", "translateX"]}
        self.aliases = {}           # node -> {alias: "weight[i]"}
        self.keys = {}              # plug -> {time: value}
        self.connections = {}       # destination plug -> source plug
        self.history = {"|body|bodyShape": []}
        self.curves = {}            # plug -> animCurve name
        self.time = 1.0
        self.undo = []

    # -- helpers
    def _plug(self, plug):
        node, _, attr = plug.partition(".")
        node = self._long(node)
        alias = self.aliases.get(node, {}).get(attr)
        return "%s.%s" % (node, alias or attr)

    def _long(self, name):
        if name in self.types:
            return name
        for long_name in self.types:
            if long_name.split("|")[-1] == name:
                return long_name
        return name

    # -- scene queries
    def ls(self, *names, **kwargs):
        out = []
        for name in names:
            n = self._long(name.split(".")[0])
            if n in self.types:
                out.append(n)
        return out

    def nodeType(self, node):
        return self.types[self._long(node)]

    def objExists(self, name):
        if "." in name:
            return self._plug(name) in self.values
        return self._long(name) in self.types

    def listRelatives(self, node, shapes=False, parent=False, **kwargs):
        node = self._long(node)
        if parent:
            return [self.parents[node]] if node in self.parents else None
        if shapes:
            return [c for c, p in self.parents.items() if p == node and self.types[c] == "mesh"]
        return []

    def listHistory(self, shape, **kwargs):
        return list(self.history.get(self._long(shape), []))

    def attributeQuery(self, attr, node=None, exists=False):
        return attr in self.attrs.get(self._long(node), [])

    def listAttr(self, node, **kwargs):
        return list(self.attrs.get(self._long(node), []))

    def currentTime(self, *args, **kwargs):
        return self.time

    def undoInfo(self, **kwargs):
        self.undo.append(kwargs)

    # -- creation
    def blendShape(self, xf, name=None, after=False):
        assert after, "the tweak node must sit after the skinCluster"
        self.types[name] = "blendShape"
        self.attrs[name] = []
        self.aliases[name] = {}
        self.history[self.listRelatives(xf, shapes=True)[0]].append(name)
        return [name]

    def addAttr(self, node, longName=None, **kwargs):
        node = self._long(node)
        self.attrs.setdefault(node, []).append(longName)
        self.values["%s.%s" % (node, longName)] = kwargs.get("defaultValue", None)

    def deleteAttr(self, plug):
        node, attr = plug.split(".")
        self.attrs[self._long(node)].remove(attr)
        self.values.pop(self._plug(plug), None)

    # -- values
    def setAttr(self, plug, *values, **kwargs):
        if kwargs.get("type") in ("pointArray", "componentList"):
            self.values[self._plug(plug)] = list(values[1:])
            assert values[0] == len(values) - 1
        elif kwargs.get("type") == "string":
            self.values[self._plug(plug)] = values[0]
        elif values:
            self.values[self._plug(plug)] = values[0] if len(values) == 1 else values

    def getAttr(self, plug, multiIndices=False, **kwargs):
        plug = self._plug(plug)
        if multiIndices:
            prefix = plug + "["
            found = set()
            for key in self.values:
                if key.startswith(prefix):
                    found.add(int(key[len(prefix):].split("]")[0]))
            return sorted(found) or None
        return self.values.get(plug)

    def aliasAttr(self, *args, **kwargs):
        if kwargs.get("query"):
            node = self._long(args[0])
            pairs = []
            for alias, attr in sorted(self.aliases.get(node, {}).items()):
                pairs += [alias, attr]
            return pairs
        if kwargs.get("remove"):
            node, alias = args[0].split(".")
            self.aliases[self._long(node)].pop(alias)
            return None
        alias, plug = args
        node, attr = plug.split(".")
        self.aliases.setdefault(self._long(node), {})[alias] = attr

    def removeMultiInstance(self, plug, b=False):
        plug = self._plug(plug)
        for key in [k for k in self.values if k == plug or k.startswith(plug + ".")]:
            del self.values[key]

    # -- keys and connections
    def setKeyframe(self, plug, time=None, value=None, **kwargs):
        plug = self._plug(plug)
        self.keys.setdefault(plug, {})[float(time)] = float(value)
        curve = "curve%d" % (len(self.curves) + 1)
        self.curves.setdefault(plug, curve)
        self.connections[plug] = self.curves[plug] + ".output"

    def cutKey(self, plug, clear=False):
        plug = self._plug(plug)
        self.keys.pop(plug, None)
        self.connections.pop(plug, None)
        self.curves.pop(plug, None)

    def listConnections(self, plug, source=True, destination=True, type=None, plugs=False):
        source_plug = self.connections.get(self._plug(plug))
        if not source_plug:
            return None
        if type == "animCurve" and not source_plug.startswith("curve"):
            return None
        return [source_plug if plugs else source_plug.split(".")[0]]

    def delete(self, nodes):
        for node in nodes if isinstance(nodes, list) else [nodes]:
            for plug in [p for p, c in self.curves.items() if c == node]:
                self.cutKey(plug)


def load_engine(fake):
    maya = types.ModuleType("maya")
    maya.cmds = fake
    maya.mel = types.SimpleNamespace(eval=lambda text: None)
    api = types.ModuleType("maya.api")
    sys.modules.update({"maya": maya, "maya.cmds": fake, "maya.mel": maya.mel, "maya.api": api})
    sys.modules.pop("maya.api.OpenMaya", None)
    sys.modules.pop("atk_tweaker.engine", None)
    return importlib.import_module("atk_tweaker.engine")


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.saved = {k: sys.modules.get(k) for k in ("maya", "maya.cmds", "maya.mel", "maya.api")}
        self.cmds = FakeCmds()
        self.engine = load_engine(self.cmds)
        self.node = "body_atkTweaks"

    def tearDown(self):
        for key, module in self.saved.items():
            if module is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = module
        sys.modules.pop("atk_tweaker.engine", None)

    def weight_keys(self, index):
        return sorted(self.cmds.keys.get("%s.weight[%d]" % (self.node, index), {}).items())

    def test_static_tweak_writes_target_alias_and_metadata(self):
        e = self.engine
        delta = {0: (0.0, 1.0, 0.0), 1: (0.0, 0.5, 0.0), 7: (1.0, 0.0, 0.0)}
        with e.undo_chunk("test"):
            index = e.commit_delta("|body", delta, core.MODE_STATIC, 1.0, label="brow")
        self.assertEqual(index, 0)
        self.assertTrue(self.cmds.undo[0]["openChunk"] and self.cmds.undo[-1]["closeChunk"])
        item = "%s.inputTarget[0].inputTargetGroup[0].inputTargetItem[6000]" % self.node
        self.assertEqual(self.cmds.values[item + ".inputComponentsTarget"], ["vtx[0:1]", "vtx[7]"])
        self.assertEqual(self.cmds.values[item + ".inputPointsTarget"][2], (1.0, 0.0, 0.0, 1.0))
        self.assertEqual(e.read_target(self.node, 0), delta)
        self.assertEqual(e.alias_map(self.node), {0: "tw_brow"})
        self.assertEqual(self.cmds.values[self.node + ".weight[0]"], 1.0)
        meta = e.read_meta(self.node)
        self.assertEqual(meta["targets"][0]["mode"], core.MODE_STATIC)
        self.assertIn("atkTweakerNode", self.cmds.attrs[self.node])
        # A second tweak reuses the same node.
        e.commit_delta("|body", {2: (0, 0, 1)}, core.MODE_PULSE, 10.0, ramp_in=2, ramp_out=4)
        self.assertEqual(self.cmds.history["|body|bodyShape"], [self.node])
        self.assertEqual(self.weight_keys(1), [(8.0, 0.0), (10.0, 1.0), (14.0, 0.0)])

    def test_sequence_keys_rekey_on_insert_and_delete(self):
        e = self.engine
        a = e.commit_delta("|body", {0: (0, 1, 0)}, core.MODE_SEQUENCE, 10.0, "L1")
        b = e.commit_delta("|body", {0: (0, 2, 0)}, core.MODE_SEQUENCE, 30.0, "L1")
        c = e.commit_delta("|body", {1: (0, 2, 0)}, core.MODE_SEQUENCE, 20.0, "L2")
        self.assertEqual(self.weight_keys(a), [(10.0, 1.0), (30.0, 0.0)])
        self.assertEqual(self.weight_keys(b), [(10.0, 0.0), (30.0, 1.0)])
        self.assertEqual(self.weight_keys(c), [(20.0, 1.0)])          # level L2 is separate
        mid = e.commit_delta("|body", {0: (0, 3, 0)}, core.MODE_SEQUENCE, 20.0, "L1")
        self.assertEqual(self.weight_keys(a), [(10.0, 1.0), (20.0, 0.0)])
        self.assertEqual(self.weight_keys(mid), [(10.0, 0.0), (20.0, 1.0), (30.0, 0.0)])
        # The same frame again refines the existing pose instead of adding one.
        again = e.commit_delta("|body", {0: (0, 1, 0)}, core.MODE_SEQUENCE, 20.0, "L1")
        self.assertEqual(again, mid)
        self.assertEqual(e.read_target(self.node, mid), {0: (0, 4, 0)})
        e.delete_tweaks("|body", [mid])
        self.assertEqual(self.weight_keys(a), [(10.0, 1.0), (30.0, 0.0)])
        self.assertEqual(self.weight_keys(mid), [])
        self.assertNotIn(mid, e.read_meta(self.node)["targets"])
        self.assertNotIn(mid, e.alias_map(self.node))
        self.assertNotIn("%s.weight[%d]" % (self.node, mid), self.cmds.values)

    def test_hold_and_blank_poses(self):
        e = self.engine
        e.commit_delta("|body", {3: (1, 0, 0)}, core.MODE_SEQUENCE, 5.0, "L1")
        self.cmds.time = 12.0
        hold = e.hold_pose("|body", "L1")
        self.assertEqual(e.read_target(self.node, hold), {3: (1, 0, 0)})
        self.assertEqual(e.read_meta(self.node)["targets"][hold]["kind"], core.KIND_HOLD)
        self.cmds.time = 20.0
        blank = e.blank_pose("|body", "L1")
        self.assertEqual(e.read_target(self.node, blank), {})
        self.assertEqual(self.weight_keys(hold), [(5.0, 0.0), (12.0, 1.0), (20.0, 0.0)])
        with self.assertRaises(e.TweakError):
            e.blank_pose("|body", "L1")                                 # frame 20 is taken
        self.cmds.time = 1.0
        with self.assertRaises(e.TweakError):
            e.hold_pose("|body", "L1")                                  # nothing before frame 1

    def test_scale_and_effect_layer_removal(self):
        e = self.engine
        index = e.commit_delta("|body", {0: (0, 1, 0)}, core.MODE_STATIC, 1.0)
        e.scale_tweak("|body", index, 1.5)
        self.assertEqual(e.read_target(self.node, index), {0: (0, 1.5, 0)})
        for frame in (1, 2, 3):
            e.add_tweak("|body", {0: (0, frame, 0)},
                        core.make_entry("fx", core.KIND_PIN, core.MODE_SEQUENCE, frame, "fx_pin"),
                        rekey=False)
        e.rekey_level(self.node, "fx_pin")
        self.assertEqual(self.weight_keys(1), [(0.0, 0.0), (1.0, 1.0), (2.0, 0.0)])
        self.assertEqual(e.delete_layer("|body", "fx_pin"), 3)
        self.assertEqual(sorted(e.read_meta(self.node)["targets"]), [index])


def tearDownModule():
    # Other suites inspect sys.modules for loaded ATK tools; leave none behind.
    for name in [n for n in sys.modules if n == "atk_tweaker" or n.startswith("atk_tweaker.")]:
        del sys.modules[name]


if __name__ == "__main__":
    unittest.main()
