"""Error-bounded reduction of piecewise-linear animation curves, without Maya."""
import math


def reduce_keys(samples, tolerance):
    """Return retained (time, value) pairs, preserving endpoints and turning points.

    Error is vertical/channel-value error, not distance in a time/value plot.
    With linear tangents the bound holds between samples as well as on them.
    No Euler wrapping is performed: intentional continuous turns remain intact.
    """
    samples = list(samples)
    if not math.isfinite(tolerance) or tolerance < 0:
        raise ValueError("Key tolerance must be finite and non-negative")
    for i, (time, value) in enumerate(samples):
        if not math.isfinite(time) or not math.isfinite(value):
            raise ValueError("Key samples must be finite")
        if i and time <= samples[i - 1][0]:
            raise ValueError("Key sample times must increase")
    if len(samples) < 3:
        return samples
    keep = {0, len(samples) - 1}
    # Pin both ends of a flat peak/valley, and each ordinary turning point.
    previous_direction = 0
    previous_change = 0
    for i in range(1, len(samples)):
        difference = samples[i][1] - samples[i - 1][1]
        direction = (difference > 0) - (difference < 0)
        if direction:
            if previous_direction and direction != previous_direction:
                keep.update((previous_change, i - 1))
            previous_direction = direction
            previous_change = i
    anchors = sorted(keep)
    pending = list(zip(anchors, anchors[1:]))
    while pending:
        left, right = pending.pop()
        t0, v0 = samples[left]
        t1, v1 = samples[right]
        error, furthest = -1.0, None
        for index in range(left + 1, right):
            time, value = samples[index]
            predicted = v0 + (v1 - v0) * (time - t0) / (t1 - t0)
            deviation = abs(value - predicted)
            if deviation > error:
                error, furthest = deviation, index
        if error > tolerance:
            keep.add(furthest)
            pending.extend(((left, furthest), (furthest, right)))
    return [samples[index] for index in sorted(keep)]
