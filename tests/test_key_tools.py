"""Key Cleanup, Stagger Keys and Add/Remove Frames against a fake scene (no Maya)."""
from pathlib import Path
import unittest

from fake_maya import FakeScene, load_tool

TOOLS = Path(__file__).resolve().parents[1] / "animation tool kit scripts"
KEY_CLEANUP = TOOLS / "Key_Cleanup_1_0_0" / "key_cleanup.py"
STAGGER = TOOLS / "Stagger_Keys_1_0_0" / "stagger_keys.py"
FRAMES = TOOLS / "Add-Remove-Inbetweens_1_0_1" / "insert_remove_frames_tool.py"

try:
    import PySide6  # noqa: F401
    HAVE_QT = True
except ImportError:
    try:
        import PySide2  # noqa: F401
        HAVE_QT = True
    except ImportError:
        HAVE_QT = False


@unittest.skipUnless(HAVE_QT, "PySide is required to import the tool modules")
class KeyCleanupTests(unittest.TestCase):
    def setUp(self):
        self.scene = FakeScene()
        self.tool = load_tool(KEY_CLEANUP, self.scene)

    def test_redundant_indices_keep_the_ends_of_each_hold(self):
        find = self.tool.redundant_key_indices
        self.assertEqual(find([0, 0, 0, 0, 5]), [1, 2])
        self.assertEqual(find([0, 5, 5, 5, 0]), [2])
        self.assertEqual(find([0, 1, 2, 3]), [])
        self.assertEqual(find([1, 1]), [])
        self.assertEqual(find([]), [])

    def test_redundant_indices_respect_tolerance_and_tangents(self):
        find = self.tool.redundant_key_indices
        self.assertEqual(find([0, 0.0004, 0], tolerance=0.001), [1])
        self.assertEqual(find([0, 0.01, 0], tolerance=0.001), [])
        # A key with a bent tangent shapes the curve and must stay.
        self.assertEqual(find([0, 0, 0], flat=[True, False, True]), [])

    def test_remove_redundant_keys_in_scene(self):
        s = self.scene
        curve = s.add_curve("ctrl", "translateX", {1: 0, 5: 0, 10: 0, 15: 0, 20: 4})
        s.selection = ["ctrl"]
        removed = self.tool.remove_redundant_keys()
        self.assertEqual(removed, 2)
        self.assertEqual(s.times(curve), [1, 15, 20])
        self.assertEqual(s.undo_depth, 0)

    def test_remove_redundant_keys_honours_the_frame_range(self):
        s = self.scene
        curve = s.add_curve("ctrl", "translateX", {1: 0, 5: 0, 10: 0, 15: 0, 20: 4})
        s.selection = ["ctrl"]
        self.assertEqual(self.tool.remove_redundant_keys(time_range=(8, 12)), 1)
        self.assertEqual(s.times(curve), [1, 5, 15, 20])

    def test_delete_static_channels_skips_referenced_and_animated(self):
        s = self.scene
        static = s.add_curve("ctrl", "translateX", {1: 2.0, 10: 2.0})
        moving = s.add_curve("ctrl", "translateY", {1: 0.0, 10: 3.0})
        ref = s.add_curve("ctrl", "translateZ", {1: 1.0, 10: 1.0})
        s.referenced.add(ref)
        s.selection = ["ctrl"]
        self.assertEqual(self.tool.delete_static_channels(), 1)
        self.assertNotIn(static, s.curves)
        self.assertIn(moving, s.curves)
        self.assertIn(ref, s.curves)

    def test_snap_keys_to_whole_frames(self):
        s = self.scene
        curve = s.add_curve("ctrl", "translateX", {1.0: 0, 4.5: 1, 9.25: 2})
        s.selection = ["ctrl"]
        self.assertEqual(self.tool.snap_keys_to_frames(), 2)
        self.assertEqual(s.times(curve), [1.0, 4.0, 9.0])

    def test_euler_filter_uses_all_three_rotate_curves_per_object(self):
        s = self.scene
        for node in ("a", "b"):
            for axis in "XYZ":
                s.add_curve(node, "rotate" + axis, {1: 0, 10: 90}, "animCurveTA")
        s.add_curve("a", "translateX", {1: 0, 10: 1})
        # Only one rotate curve of 'a' has selected keys.
        s.selected_keys = {"a_rotateX": [1]}
        self.assertEqual(self.tool.euler_filter(), 1)
        self.assertEqual(s.filtered, [["a_rotateX", "a_rotateY", "a_rotateZ"]])

    def test_locked_and_driven_key_curves_are_ignored(self):
        s = self.scene
        locked = s.add_curve("ctrl", "translateX", {1: 0, 5: 0, 9: 0})
        s.locked.add(locked)
        s.add_curve("ctrl", "translateY", {1: 0, 5: 0, 9: 0}, "animCurveUL")
        s.selection = ["ctrl"]
        self.assertEqual(self.tool.target_curves(), [])
        self.assertEqual(self.tool.remove_redundant_keys(), 0)

    def test_clean_all_is_balanced_and_reports_counts(self):
        s = self.scene
        s.add_curve("ctrl", "translateX", {1: 0, 5: 0, 10: 0, 15: 3})
        s.add_curve("ctrl", "translateY", {1: 1, 10: 1})
        s.selection = ["ctrl"]
        counts = self.tool.clean_all()
        self.assertEqual(counts["redundant"], 1)
        self.assertEqual(counts["static"], 1)
        self.assertEqual(s.undo_depth, 0)

    def test_nothing_selected_warns(self):
        self.assertEqual(self.tool.remove_redundant_keys(), 0)
        self.assertTrue(self.scene.warnings)


@unittest.skipUnless(HAVE_QT, "PySide is required to import the tool modules")
class StaggerKeysTests(unittest.TestCase):
    def setUp(self):
        self.scene = FakeScene()
        self.tool = load_tool(STAGGER, self.scene)
        for node in ("a", "b", "c"):
            self.scene.add_curve(node, "rotateX", {1: 0, 10: 5}, "animCurveTA")
        self.scene.selection = ["a", "b", "c"]

    def test_offsets(self):
        offsets = self.tool.stagger_offsets
        self.assertEqual(offsets(4, 2), [0, 2, 4, 6])
        self.assertEqual(offsets(3, 2, reverse=True), [4, 2, 0])
        self.assertEqual(offsets(3, -1), [0, -1, -2])
        self.assertEqual(offsets(0, 2), [])

    def test_stagger_by_selection_order(self):
        self.assertEqual(self.tool.stagger(2), 2)
        s = self.scene
        self.assertEqual(s.times("a_rotateX"), [1, 10])
        self.assertEqual(s.times("b_rotateX"), [3, 12])
        self.assertEqual(s.times("c_rotateX"), [5, 14])
        self.assertEqual(s.undo_depth, 0)
        self.assertEqual(s.max_undo_depth, 1)

    def test_stagger_reverse(self):
        self.tool.stagger(1, reverse=True)
        s = self.scene
        self.assertEqual(s.times("a_rotateX"), [3, 12])
        self.assertEqual(s.times("c_rotateX"), [1, 10])

    def test_offset_all(self):
        self.assertEqual(self.tool.offset_all(-1), 3)
        for node in ("a", "b", "c"):
            self.assertEqual(self.scene.times(node + "_rotateX"), [0, 9])

    def test_only_selected_keys_move(self):
        s = self.scene
        s.selected_keys = {"b_rotateX": [10]}
        self.tool.stagger(3)
        self.assertEqual(s.times("b_rotateX"), [1, 13])
        self.assertEqual(s.times("c_rotateX"), [1, 10])  # no selected keys on c

    def test_needs_two_objects(self):
        self.scene.selection = ["a"]
        self.assertEqual(self.tool.stagger(1), 0)
        self.assertTrue(self.scene.warnings)


@unittest.skipUnless(HAVE_QT, "PySide is required to import the tool modules")
class RemovableFramesTests(unittest.TestCase):
    """Removing frames must never push keys onto or past earlier keys."""

    def setUp(self):
        self.scene = FakeScene()
        self.tool = load_tool(FRAMES, self.scene)

    def test_limit_is_the_smallest_gap_across_curves(self):
        s = self.scene
        a = s.add_curve("a", "translateX", {1: 0, 10: 1})     # 8 blank frames
        b = s.add_curve("b", "translateX", {1: 0, 5: 1})      # 3 blank frames
        self.assertEqual(self.tool.removable_frames([a], 2), 8)
        self.assertEqual(self.tool.removable_frames([a, b], 2), 3)

    def test_no_limit_without_keys_on_both_sides(self):
        s = self.scene
        a = s.add_curve("a", "translateX", {8: 0, 13: 1})
        self.assertIsNone(self.tool.removable_frames([a], 5))

    def test_adjacent_keys_leave_nothing_to_remove(self):
        s = self.scene
        a = s.add_curve("a", "translateX", {1: 0, 2: 1})
        self.assertEqual(self.tool.removable_frames([a], 2), 0)


if __name__ == "__main__":
    unittest.main()
