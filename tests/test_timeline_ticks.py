"""Controller checks without requiring Maya or Qt."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

SOURCE = Path(__file__).resolve().parents[1] / "animation tool kit scripts/Timeline_Ticks_1_0_0/timeline_ticks.py"
spec = importlib.util.spec_from_file_location("timeline_ticks", SOURCE)
ticks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ticks)


class TickTests(unittest.TestCase):
    def setUp(self):
        self.cmds = Mock()
        self.cmds.timeControl.side_effect = lambda *a, **k: (
            ["curveA", "curveB", "driven"] if k.get("animCurveNames") else
            [10, 12] if k.get("rangeArray") else True)
        self.cmds.nodeType.side_effect = lambda c: "animCurveUU" if c == "driven" else "animCurveTL"
        self.cmds.ls.side_effect = lambda c, **k: [c + "-uuid"]
        self.cmds.currentTime.return_value = 10
        self.cmds.keyframe.side_effect = self.keys
        self.controller = ticks.Controller(self.cmds, "slider", lambda frame: frame / 24.0)
        self.controller.store = Mock()
        self.controller.store.read.return_value = {}

    @staticmethod
    def keys(curve, **flags):
        if flags.get("edit"):
            return 1
        times = [10, 10.5, 11, 12] if curve == "curveA" else [10]
        if flags.get("selected"):
            return [10.5] if curve == "curveA" else []
        if "time" in flags:
            start, end = flags["time"]
            times = [t for t in times if start <= t <= end]
        return times

    def test_current_frame_and_curve_filter(self):
        self.assertEqual(self.controller.targets("Current frame"), [("curveA", 10), ("curveB", 10)])

    def test_range_excludes_upper_bound_preserves_subframes(self):
        self.assertEqual(self.controller.targets("Highlighted range"),
                         [("curveA", 10), ("curveA", 10.5), ("curveA", 11), ("curveB", 10)])

    def test_selected_keys_do_not_expand_to_other_channels(self):
        self.assertEqual(self.controller.targets("Selected keys"), [("curveA", 10.5)])

    def test_breakdown_and_single_undo_chunk(self):
        self.controller.apply("Current frame", kind="Breakdown")
        edits = [c for c in self.cmds.keyframe.call_args_list if c.kwargs.get("edit")]
        self.assertEqual(len(edits), 2)
        self.assertTrue(all(c.kwargs["breakdown"] for c in edits))
        self.assertEqual(self.cmds.undoInfo.call_count, 2)
        marks = self.controller.store.write.call_args.args[0]
        self.assertEqual(len(marks), 2)
        self.assertTrue(all(m["kind"] == "Breakdown" for m in marks.values()))

    def test_colour_and_clear_preserve_breakdown_state(self):
        identity = self.controller.identity("curveA", 10)
        self.controller.store.read.return_value = {identity: {"kind": "Extreme", "color": "#f5cf58"}}
        self.controller.apply("Current frame", color="#60a5fa")
        self.assertEqual(self.controller.store.write.call_args.args[0][identity],
                         {"kind": "Extreme", "color": "#60a5fa"})
        self.controller.apply("Current frame", clear=True)
        self.assertNotIn(identity, self.controller.store.write.call_args.args[0])
        self.assertFalse(any(c.kwargs.get("edit") for c in self.cmds.keyframe.call_args_list))

    def test_empty_scope_never_writes(self):
        self.cmds.currentTime.return_value = 100
        self.assertEqual(self.controller.apply("Current frame", kind="Key"), 0)
        self.controller.store.write.assert_not_called()
        self.cmds.undoInfo.assert_not_called()

    def test_failed_edit_always_closes_chunk(self):
        def fail(curve, **flags):
            if flags.get("edit"):
                raise RuntimeError("Locked curve")
            return [10]
        self.cmds.keyframe.side_effect = fail
        with self.assertRaises(RuntimeError):
            self.controller.apply("Current frame", kind="Key")
        self.assertEqual(self.cmds.undoInfo.call_args.kwargs, {"closeChunk": True})
        self.controller.store.write.assert_not_called()

    def test_corrupt_store_rejected_before_mutation(self):
        self.controller.store.read.side_effect = ValueError("invalid")
        with self.assertRaises(ValueError):
            self.controller.apply("Current frame", kind="Key")
        self.cmds.undoInfo.assert_not_called()

    def test_visible_keys_filter_stale_annotations_and_keep_mixed_styles(self):
        self.controller.store.read.return_value = {
            self.controller.identity("curveA", 10): {"kind": "Key", "color": "#ef6464"},
            self.controller.identity("curveB", 10): {"kind": "Extreme", "color": "#f5cf58"},
            self.controller.identity("curveA", 50): {"kind": "Breakdown", "color": "#60a5fa"}}
        self.assertEqual(self.controller.visible_marks(), {10: {("Key", "#ef6464"), ("Extreme", "#f5cf58")}})

    def test_frame_cell_mapping(self):
        self.assertEqual(ticks.frame_x(1, 1, 10, 100), 5)
        self.assertEqual(ticks.frame_x(10, 1, 10, 100), 95)

    def test_toolbar_quick_actions_use_range_without_opening_dialog(self):
        window = Mock()
        window.timer.isActive.return_value = True
        window.controller.cmds.timeControl.return_value = True
        window.controller.apply.return_value = 2
        with patch.object(ticks, "_window", window), patch.object(ticks, "show") as show:
            self.assertEqual(ticks.apply_yellow(), 2)
            window.controller.apply.assert_called_with("Highlighted range", color="#f5cf58")
            window.controller.cmds.timeControl.return_value = False
            ticks.apply_red()
            window.controller.apply.assert_called_with("Current frame", color="#ef6464")
            ticks.apply_blue()
            window.controller.apply.assert_called_with("Current frame", color="#60a5fa")
            ticks.mark_breakdown()
            window.controller.apply.assert_called_with("Current frame", kind="Breakdown")
            ticks.clear_ticks()
            window.controller.apply.assert_called_with("Current frame", clear=True)
            show.assert_not_called()

    def test_first_quick_action_starts_hidden_overlay(self):
        window = Mock()
        with patch.object(ticks, "_window", None), patch.object(ticks, "show", return_value=window):
            ticks.apply_blue()
            window.hide.assert_called_once()
            window.refresh.assert_called_once()

    def test_decode_rejects_future_and_corrupt_data(self):
        for raw in ('{}', '{"version":2,"marks":{}}', '{"version":1,"marks":[]}'):
            with self.assertRaises(ValueError):
                ticks.decode(raw)
        self.assertEqual(ticks.decode('{"version":1,"marks":{}}'), {})


if __name__ == "__main__":
    unittest.main()
