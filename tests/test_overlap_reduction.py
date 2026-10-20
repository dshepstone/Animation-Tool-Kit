"""Overlap's optimized bake: key reduction keeps the motion within tolerance."""
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "animation tool kit scripts" / "Overlap"))
from atk_overlap.reduction import anchor_indices, reduce_keys  # noqa: E402


def damped_swing(frames=100):
    return [(f, 20 * math.exp(-f / 15.0) * math.cos(f / 3.0)) for f in range(1, frames + 1)]


def max_error(samples, keys):
    worst = 0.0
    for time, value in samples:
        for (t0, v0), (t1, v1) in zip(keys, keys[1:]):
            if t0 <= time <= t1:
                worst = max(worst, abs(value - (v0 + (v1 - v0) * (time - t0) / (t1 - t0))))
                break
    return worst


class ReduceKeysTest(unittest.TestCase):
    def test_error_bound_and_endpoints(self):
        samples = damped_swing()
        keys = reduce_keys(samples, .25)
        self.assertEqual(keys[0], samples[0])
        self.assertEqual(keys[-1], samples[-1])
        self.assertLessEqual(max_error(samples, keys), .25 + 1e-9)

    def test_large_peaks_kept(self):
        samples = damped_swing()
        kept = {t for t, _ in reduce_keys(samples, .25)}
        for i in range(1, len(samples) - 1):
            prev, value, nxt = samples[i - 1][1], samples[i][1], samples[i + 1][1]
            if abs(value) > 2 and (value - prev) * (nxt - value) < 0:
                self.assertIn(samples[i][0], kept)

    def test_settling_jitter_not_keyed_every_frame(self):
        # Swing that settles into sub-tolerance alternating noise.
        samples = damped_swing(40) + [(f, .01 * (-1) ** f) for f in range(41, 101)]
        keys = reduce_keys(samples, .25)
        self.assertLess(len([t for t, _ in keys if t > 40]), 5)
        self.assertLessEqual(max_error(samples, keys), .25 + 1e-9)

    def test_zero_tolerance_keeps_shape(self):
        samples = damped_swing(30)
        self.assertAlmostEqual(max_error(samples, reduce_keys(samples, 0)), 0, places=9)

    def test_anchors_skip_jitter_peaks(self):
        samples = [(1, 0), (2, 10), (3, 0), (4, .1), (5, 0), (6, .1), (7, 0)]
        self.assertEqual(anchor_indices(samples, .25), {0, 1, 6})


if __name__ == "__main__":
    unittest.main()
