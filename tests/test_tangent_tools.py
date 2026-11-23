"""Tangent Tools quick tangent buttons: which keys they change (no Maya)."""
from pathlib import Path
import unittest

from fake_maya import FakeScene, load_tool

CORE = (Path(__file__).resolve().parents[1] / "animation tool kit scripts"
        / "tangent_tools" / "src" / "tangent_tools" / "core.py")
SLIDER = "timeControl1"


class TangentScene(FakeScene):
    """FakeScene plus a Time Slider and an editable keyTangent."""

    def __init__(self):
        super(TangentScene, self).__init__()
        self.range = None            # (start, exclusive_end) or None
        self.slider_curves = None    # None: every curve on the selection
        self.edits = []              # (curve, time, flags)

    def timeControl(self, slider, **kwargs):
        if kwargs.get("rangeVisible"):
            return self.range is not None
        if kwargs.get("rangeArray"):
            return list(self.range) if self.range else [self.current_time,
                                                        self.current_time + 1]
        if kwargs.get("animCurveNames"):
            if self.slider_curves is not None:
                return list(self.slider_curves)
            return [c for node in self.selection for c in self.curves_of(node)]
        return None

    def keyTangent(self, curve, **kwargs):
        if kwargs.get("edit"):
            start, end = kwargs["time"]
            flags = {k: v for k, v in kwargs.items() if k.endswith("TangentType")}
            for t in self.times(curve):
                if start <= t <= end:
                    self.edits.append((curve, t, flags))
            return None
        return super(TangentScene, self).keyTangent(curve, **kwargs)


class SetTangentTypeTests(unittest.TestCase):
    def setUp(self):
        self.scene = TangentScene()
        self.core = load_tool(CORE, self.scene)
        self.core.mel.eval = lambda *a, **k: SLIDER
        keys = {1.0: 0, 5.0: 1, 10.0: 2, 15.0: 3, 20.0: 4}
        self.tx = self.scene.add_curve("ball", "tx", keys)
        self.ty = self.scene.add_curve("ball", "ty", keys)
        self.other = self.scene.add_curve("box", "tx", keys)
        self.scene.selection = ["ball"]

    def edited(self):
        return sorted((c, t) for c, t, _ in self.scene.edits)

    def test_current_frame_changes_only_that_key(self):
        self.scene.current_time = 10.0
        self.core.set_tangent_type("linear")
        self.assertEqual(self.edited(), [(self.tx, 10.0), (self.ty, 10.0)])
        self.assertEqual(self.scene.edits[0][2],
                         {"inTangentType": "linear", "outTangentType": "linear"})

    def test_current_frame_without_a_key_changes_nothing(self):
        self.scene.current_time = 7.0
        self.assertEqual(self.core.set_tangent_type("linear"), 0)
        self.assertEqual(self.scene.edits, [])
        self.assertTrue(self.scene.warnings)

    def test_highlighted_range_changes_only_keys_inside_it(self):
        # Shift-drag over frames 5-15: rangeArray reports [5, 16].
        self.scene.range = (5.0, 16.0)
        self.scene.current_time = 1.0
        self.core.set_tangent_type("auto_legacy")
        self.assertEqual(self.edited(), [
            (self.tx, 5.0), (self.tx, 10.0), (self.tx, 15.0),
            (self.ty, 5.0), (self.ty, 10.0), (self.ty, 15.0)])

    def test_range_end_frame_is_exclusive(self):
        self.scene.range = (5.0, 15.0)   # frames 5-14 highlighted
        self.core.set_tangent_type("linear")
        self.assertNotIn((self.tx, 15.0), self.edited())

    def test_range_respects_channel_box_narrowing(self):
        self.scene.slider_curves = [self.ty]
        self.scene.range = (1.0, 21.0)
        self.core.set_tangent_type("linear")
        self.assertEqual({c for c, _ in self.edited()}, {self.ty})

    def test_graph_editor_selected_keys_change_only_those(self):
        self.scene.current_time = 1.0
        self.scene.selected_keys = {self.tx: [5.0, 20.0], self.other: [10.0]}
        self.core.set_tangent_type("stepped")
        self.assertEqual(self.edited(), [
            (self.tx, 5.0), (self.tx, 20.0), (self.other, 10.0)])
        self.assertEqual(self.scene.edits[0][2], {"outTangentType": "step"})

    def test_highlighted_range_wins_over_graph_selection(self):
        self.scene.selected_keys = {self.tx: [1.0]}
        self.scene.range = (20.0, 21.0)
        self.core.set_tangent_type("linear")
        self.assertEqual(self.edited(), [(self.tx, 20.0), (self.ty, 20.0)])

    def test_change_is_one_undo_chunk(self):
        self.scene.range = (1.0, 21.0)
        self.core.set_tangent_type("linear")
        self.assertEqual(self.scene.max_undo_depth, 1)
        self.assertEqual(self.scene.undo_depth, 0)


if __name__ == "__main__":
    unittest.main()
