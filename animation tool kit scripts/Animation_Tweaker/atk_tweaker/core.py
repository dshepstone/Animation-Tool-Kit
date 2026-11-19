"""Pure-Python maths and planning for Animation Tweaker.

Nothing in this module imports Maya. The Maya-facing modules gather points,
matrices and selections, hand them to these functions, and write the result
back. Keeping the numbers here lets the test suite check them without Maya.

Conventions
-----------
* A point is a 3-tuple of floats. A point list is indexed by vertex id.
* A *delta* is a sparse dict ``{vertex_id: (dx, dy, dz)}``. Vertices that do
  not move are left out, which keeps blendShape targets small.
* A *mask* is a dict ``{vertex_id: weight}`` with weights in 0..1, or None for
  "every vertex at full weight".
* Matrices are 16 floats, row-major, in Maya's row-vector convention:
  ``world = local * M`` with the translation in elements 12..14.
"""
import json
import math
import random
import re

EPSILON = 1e-6
METADATA_VERSION = 1

# Keying modes and the layer names they use.
MODE_STATIC = "static"
MODE_PULSE = "pulse"
MODE_SEQUENCE = "sequence"
MODE_MANUAL = "manual"        # keyed by hand; never rekeyed automatically
MODES = (MODE_STATIC, MODE_PULSE, MODE_SEQUENCE, MODE_MANUAL)

KIND_SCULPT = "sculpt"
KIND_BLANK = "blank"
KIND_HOLD = "hold"
KIND_INFLATE = "inflate"
KIND_RELAX = "relax"
KIND_SMOOTH = "smooth_motion"
KIND_STICK = "stick"
KIND_PUSH = "push_out"
KIND_PIN = "pin"
EFFECT_KINDS = (KIND_SMOOTH, KIND_STICK, KIND_PUSH, KIND_PIN)

# Mute-while-sculpting choices: which existing tweaks are switched off.
MUTE_NONE = "none"
MUTE_ALL = "all"
MUTE_STATIC = "static"
MUTE_SEQUENCE = "sequence"
MUTE_LEVEL = "level"
MUTE_MODES = (MUTE_NONE, MUTE_ALL, MUTE_STATIC, MUTE_SEQUENCE, MUTE_LEVEL)


# ---------------------------------------------------------------------------
# Vector helpers
# ---------------------------------------------------------------------------

def v_add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def v_sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def v_scale(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def v_dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def v_cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def v_length(a):
    return math.sqrt(v_dot(a, a))


def v_normalize(a, fallback=(0.0, 1.0, 0.0)):
    length = v_length(a)
    if length < EPSILON:
        return tuple(fallback)
    return (a[0] / length, a[1] / length, a[2] / length)


def _is_zero(vector, tol):
    return abs(vector[0]) <= tol and abs(vector[1]) <= tol and abs(vector[2]) <= tol


# ---------------------------------------------------------------------------
# Masks and deltas
# ---------------------------------------------------------------------------

def mask_weight(mask, index):
    """Weight of one vertex. ``None`` means every vertex is fully selected."""
    if mask is None:
        return 1.0
    return max(0.0, min(1.0, float(mask.get(index, 0.0))))


def masked_indices(mask, count):
    """Vertex ids with a non-zero weight, in order."""
    if mask is None:
        return list(range(count))
    return sorted(i for i, w in mask.items() if w > EPSILON and 0 <= i < count)


def compute_delta(base, sculpt, mask=None, tol=1e-5):
    """Sparse object-space difference ``sculpt - base``, weighted by ``mask``."""
    if len(base) != len(sculpt):
        raise ValueError("Sculpt has %d vertices but the mesh has %d; the topology "
                         "changed while sculpting." % (len(sculpt), len(base)))
    delta = {}
    for index, (a, b) in enumerate(zip(base, sculpt)):
        weight = mask_weight(mask, index)
        if weight <= 0.0:
            continue
        d = v_scale(v_sub(b, a), weight)
        if not _is_zero(d, tol):
            delta[index] = d
    return delta


def scale_delta(delta, factor, tol=1e-7):
    """Amplify (factor > 1) or reduce a tweak."""
    out = {}
    for index, d in delta.items():
        s = v_scale(d, factor)
        if not _is_zero(s, tol):
            out[index] = s
    return out


def add_deltas(a, b, scale_b=1.0, tol=1e-7):
    """Return ``a + b * scale_b`` as a new sparse delta."""
    out = dict(a)
    for index, d in b.items():
        total = v_add(out.get(index, (0.0, 0.0, 0.0)), v_scale(d, scale_b))
        if _is_zero(total, tol):
            out.pop(index, None)
        else:
            out[index] = total
    return out


def refine_delta(existing, correction, current_weight):
    """Fold a correction sculpted on top of a tweak back into that tweak.

    The correction was sculpted while the tweak showed at ``current_weight``.
    Dividing by that weight makes the refined tweak look exactly like the
    sculpt at the same weight.
    """
    if current_weight < 1e-3:
        raise ValueError("The tweak's weight is 0 on this frame. Go to a frame where "
                         "it shows, or set its weight above 0, then refine it.")
    return add_deltas(existing, correction, 1.0 / current_weight)


def blend_deltas(weighted):
    """Sum of ``[(delta, weight), ...]``: what several targets add together."""
    out = {}
    for delta, weight in weighted:
        if abs(weight) > 1e-9:
            out = add_deltas(out, delta, weight)
    return out


def apply_delta(points, delta, weight=1.0):
    out = list(points)
    for index, d in delta.items():
        out[index] = v_add(out[index], v_scale(d, weight))
    return out


# ---------------------------------------------------------------------------
# blendShape target encoding
# ---------------------------------------------------------------------------

_COMPONENT = re.compile(r"^(?:[\w:|]+\.)?vtx\[(\d+)(?::(\d+))?\]$")


def compress_indices(indices, prefix="vtx"):
    """``[0, 1, 2, 5]`` -> ``['vtx[0:2]', 'vtx[5]']`` for a componentList."""
    out = []
    ordered = sorted(set(int(i) for i in indices))
    start = prev = None
    for index in ordered:
        if start is None:
            start = prev = index
        elif index == prev + 1:
            prev = index
        else:
            out.append(_range_text(prefix, start, prev))
            start = prev = index
    if start is not None:
        out.append(_range_text(prefix, start, prev))
    return out


def _range_text(prefix, start, end):
    if start == end:
        return "%s[%d]" % (prefix, start)
    return "%s[%d:%d]" % (prefix, start, end)


def expand_components(components):
    """Inverse of :func:`compress_indices`. Unknown entries are ignored."""
    indices = []
    for text in components or ():
        match = _COMPONENT.match(text.strip())
        if not match:
            continue
        start = int(match.group(1))
        end = int(match.group(2)) if match.group(2) is not None else start
        indices.extend(range(start, end + 1))
    return indices


def delta_to_target(delta):
    """Split a delta into the two arrays a blendShape target item stores."""
    order = sorted(delta)
    components = compress_indices(order)
    points = [(delta[i][0], delta[i][1], delta[i][2], 1.0) for i in order]
    return components, points


def target_to_delta(components, points):
    indices = expand_components(components)
    if len(indices) != len(points or ()):
        raise ValueError("Target has %d components but %d points" % (len(indices), len(points or ())))
    return {i: (float(p[0]), float(p[1]), float(p[2])) for i, p in zip(indices, points)}


# ---------------------------------------------------------------------------
# Shape operations: inflate and relax
# ---------------------------------------------------------------------------

def vertex_normals(points, faces):
    """Area-weighted vertex normals from polygon faces (lists of vertex ids)."""
    sums = [(0.0, 0.0, 0.0)] * len(points)
    for face in faces:
        if len(face) < 3:
            continue
        # Newell's method handles n-gons and concave faces.
        normal = (0.0, 0.0, 0.0)
        for i, a_id in enumerate(face):
            a = points[a_id]
            b = points[face[(i + 1) % len(face)]]
            normal = v_add(normal, ((a[1] - b[1]) * (a[2] + b[2]),
                                    (a[2] - b[2]) * (a[0] + b[0]),
                                    (a[0] - b[0]) * (a[1] + b[1])))
        for vid in face:
            sums[vid] = v_add(sums[vid], normal)
    return [v_normalize(n) for n in sums]


def adjacency_from_faces(count, faces):
    """Edge neighbours of each vertex, from polygon faces."""
    neighbours = [set() for _ in range(count)]
    for face in faces:
        for i, a in enumerate(face):
            b = face[(i + 1) % len(face)]
            if a != b:
                neighbours[a].add(b)
                neighbours[b].add(a)
    return [sorted(n) for n in neighbours]


def inflate_delta(points, normals, amount, mask=None):
    """Move each masked vertex ``amount`` along its normal (negative deflates)."""
    delta = {}
    for index in masked_indices(mask, len(points)):
        d = v_scale(normals[index], amount * mask_weight(mask, index))
        if not _is_zero(d, 1e-9):
            delta[index] = d
    return delta


def relax_points(points, adjacency, iterations=5, strength=0.5, mask=None):
    """Laplacian smoothing. Each pass moves a vertex toward its neighbours' average.

    Unmasked vertices stay where they are but still pull on their neighbours,
    so the relaxed area blends into the rest of the mesh.
    """
    strength = max(0.0, min(1.0, float(strength)))
    current = list(points)
    active = masked_indices(mask, len(points))
    for _ in range(max(0, int(iterations))):
        nxt = list(current)
        for index in active:
            ring = adjacency[index]
            if not ring:
                continue
            avg = (0.0, 0.0, 0.0)
            for n in ring:
                avg = v_add(avg, current[n])
            avg = v_scale(avg, 1.0 / len(ring))
            step = strength * mask_weight(mask, index)
            nxt[index] = v_add(current[index], v_scale(v_sub(avg, current[index]), step))
        current = nxt
    return current


def relax_delta(points, adjacency, iterations=5, strength=0.5, mask=None):
    return compute_delta(points, relax_points(points, adjacency, iterations, strength, mask), tol=1e-9)


# ---------------------------------------------------------------------------
# Temporal filtering
# ---------------------------------------------------------------------------

def gaussian_kernel(sigma, radius=None):
    """Normalised Gaussian weights for offsets ``-radius..radius``."""
    sigma = float(sigma)
    if sigma <= 0.0:
        return [1.0]
    if radius is None:
        radius = int(math.ceil(3.0 * sigma))
    weights = [math.exp(-(k * k) / (2.0 * sigma * sigma)) for k in range(-radius, radius + 1)]
    total = sum(weights)
    return [w / total for w in weights]


def temporal_gaussian(series, sigma, indices=None):
    """Smooth vertex paths over time.

    ``series`` is a list (one entry per frame) of point lists. Frames past the
    ends repeat the first/last frame, so the range ends do not drift. Only
    ``indices`` are filtered; other vertices are copied unchanged.
    """
    if not series:
        return []
    kernel = gaussian_kernel(sigma)
    radius = len(kernel) // 2
    last = len(series) - 1
    count = len(series[0])
    if indices is None:
        indices = range(count)
    out = [list(frame) for frame in series]
    for f in range(len(series)):
        for index in indices:
            x = y = z = 0.0
            for k, w in enumerate(kernel):
                src = series[min(last, max(0, f + k - radius))][index]
                x += src[0] * w
                y += src[1] * w
                z += src[2] * w
            out[f][index] = (x, y, z)
    return out


def smooth_motion_deltas(series, sigma, mask=None):
    """Per-frame deltas that replace masked vertex motion with its Gaussian average."""
    if not series:
        return []
    indices = masked_indices(mask, len(series[0]))
    smoothed = temporal_gaussian(series, sigma, indices)
    deltas = []
    for raw, smooth in zip(series, smoothed):
        delta = {}
        for index in indices:
            d = v_scale(v_sub(smooth[index], raw[index]), mask_weight(mask, index))
            if not _is_zero(d, 1e-7):
                delta[index] = d
        deltas.append(delta)
    return deltas


# ---------------------------------------------------------------------------
# Matrices (row-vector convention, 16 floats row-major)
# ---------------------------------------------------------------------------

IDENTITY = (1.0, 0.0, 0.0, 0.0,
            0.0, 1.0, 0.0, 0.0,
            0.0, 0.0, 1.0, 0.0,
            0.0, 0.0, 0.0, 1.0)


def mat_mult(a, b):
    return tuple(sum(a[r * 4 + k] * b[k * 4 + c] for k in range(4))
                 for r in range(4) for c in range(4))


def mat_inverse(m):
    """General 4x4 inverse by Gauss-Jordan elimination."""
    rows = [list(m[r * 4:r * 4 + 4]) + [1.0 if r == c else 0.0 for c in range(4)] for r in range(4)]
    for col in range(4):
        pivot = max(range(col, 4), key=lambda r: abs(rows[r][col]))
        if abs(rows[pivot][col]) < 1e-12:
            raise ValueError("Matrix is not invertible (zero scale?)")
        rows[col], rows[pivot] = rows[pivot], rows[col]
        p = rows[col][col]
        rows[col] = [v / p for v in rows[col]]
        for r in range(4):
            if r != col:
                f = rows[r][col]
                rows[r] = [a - f * b for a, b in zip(rows[r], rows[col])]
    return tuple(v for r in rows for v in r[4:])


def xform_point(p, m):
    return (p[0] * m[0] + p[1] * m[4] + p[2] * m[8] + m[12],
            p[0] * m[1] + p[1] * m[5] + p[2] * m[9] + m[13],
            p[0] * m[2] + p[1] * m[6] + p[2] * m[10] + m[14])


def xform_vector(v, m):
    return (v[0] * m[0] + v[1] * m[4] + v[2] * m[8],
            v[0] * m[1] + v[1] * m[5] + v[2] * m[9],
            v[0] * m[2] + v[1] * m[6] + v[2] * m[10])


def xform_normal(n, m):
    """Transform a surface normal: by the inverse transpose of ``m``'s linear part.

    Unlike :func:`xform_vector`, this keeps the normal perpendicular to the
    surface when ``m`` has non-uniform scale or shear.
    """
    inv = mat_inverse(m)
    return v_normalize((n[0] * inv[0] + n[1] * inv[1] + n[2] * inv[2],
                        n[0] * inv[4] + n[1] * inv[5] + n[2] * inv[6],
                        n[0] * inv[8] + n[1] * inv[9] + n[2] * inv[10]))


def world_delta_to_object(delta, world_matrix):
    """Turn world-space offsets into the mesh's object space."""
    inverse = mat_inverse(world_matrix)
    return {i: xform_vector(d, inverse) for i, d in delta.items()}


# ---------------------------------------------------------------------------
# Surface relationships: stick, push out, pin
# ---------------------------------------------------------------------------

def closest_point_on_triangle(p, a, b, c):
    """Closest point to ``p`` on triangle abc and its barycentric weights."""
    ab, ac, ap = v_sub(b, a), v_sub(c, a), v_sub(p, a)
    d1, d2 = v_dot(ab, ap), v_dot(ac, ap)
    if d1 <= 0.0 and d2 <= 0.0:
        return a, (1.0, 0.0, 0.0)
    bp = v_sub(p, b)
    d3, d4 = v_dot(ab, bp), v_dot(ac, bp)
    if d3 >= 0.0 and d4 <= d3:
        return b, (0.0, 1.0, 0.0)
    vc = d1 * d4 - d3 * d2
    if vc <= 0.0 and d1 >= 0.0 and d3 <= 0.0:
        t = d1 / (d1 - d3)
        return v_add(a, v_scale(ab, t)), (1.0 - t, t, 0.0)
    cp = v_sub(p, c)
    d5, d6 = v_dot(ab, cp), v_dot(ac, cp)
    if d6 >= 0.0 and d5 <= d6:
        return c, (0.0, 0.0, 1.0)
    vb = d5 * d2 - d1 * d6
    if vb <= 0.0 and d2 >= 0.0 and d6 <= 0.0:
        t = d2 / (d2 - d6)
        return v_add(a, v_scale(ac, t)), (1.0 - t, 0.0, t)
    va = d3 * d6 - d5 * d4
    if va <= 0.0 and (d4 - d3) >= 0.0 and (d5 - d6) >= 0.0:
        t = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        return v_add(b, v_scale(v_sub(c, b), t)), (0.0, 1.0 - t, t)
    denom = 1.0 / (va + vb + vc)
    v = vb * denom
    w = vc * denom
    return v_add(a, v_add(v_scale(ab, v), v_scale(ac, w))), (1.0 - v - w, v, w)


def closest_on_triangles(p, points, triangles):
    """Closest point over a triangle list: ``(triangle_index, bary, point)``."""
    best = None
    for t_index, (i, j, k) in enumerate(triangles):
        q, bary = closest_point_on_triangle(p, points[i], points[j], points[k])
        dist = v_length(v_sub(p, q))
        if best is None or dist < best[0]:
            best = (dist, t_index, bary, q)
    if best is None:
        raise ValueError("Driver mesh has no triangles")
    return best[1], best[2], best[3]


def triangle_frame(a, b, c):
    """Orthonormal frame (tangent, normal, binormal) of a triangle."""
    tangent = v_normalize(v_sub(b, a), (1.0, 0.0, 0.0))
    normal = v_normalize(v_cross(v_sub(b, a), v_sub(c, a)))
    binormal = v_cross(normal, tangent)
    return tangent, normal, binormal


def barycentric_point(points, tri, bary):
    a, b, c = (points[i] for i in tri)
    return v_add(v_add(v_scale(a, bary[0]), v_scale(b, bary[1])), v_scale(c, bary[2]))


def bind_to_surface(p, driver_points, triangles):
    """Record where ``p`` sits relative to the driver: triangle, bary, local offset."""
    t_index, bary, q = closest_on_triangles(p, driver_points, triangles)
    frame = triangle_frame(*(driver_points[i] for i in triangles[t_index]))
    offset = v_sub(p, q)
    local = tuple(v_dot(offset, axis) for axis in frame)
    return t_index, bary, local


def follow_surface(binding, driver_points, triangles):
    """Where a bound point is on a later frame of the driver."""
    t_index, bary, local = binding
    tri = triangles[t_index]
    anchor = barycentric_point(driver_points, tri, bary)
    frame = triangle_frame(*(driver_points[i] for i in tri))
    offset = (0.0, 0.0, 0.0)
    for axis, amount in zip(frame, local):
        offset = v_add(offset, v_scale(axis, amount))
    return v_add(anchor, offset)


def push_out_point(p, surface_point, surface_normal, skin_offset=0.0):
    """Push ``p`` out to ``skin_offset`` above a surface if it is closer or inside."""
    n = v_normalize(surface_normal)
    depth = v_dot(v_sub(p, surface_point), n)
    if depth >= skin_offset:
        return p
    return v_add(p, v_scale(n, skin_offset - depth))


def blend_toward(current, target, weight):
    return v_add(current, v_scale(v_sub(target, current), weight))


# ---------------------------------------------------------------------------
# Keying plans
# ---------------------------------------------------------------------------

def pulse_keys(frame, ramp_in=3, ramp_out=3):
    """0 -> 1 -> 0 around ``frame``. A ramp shorter than one frame is one frame."""
    ramp_in = max(1.0, float(ramp_in))
    ramp_out = max(1.0, float(ramp_out))
    frame = float(frame)
    return [(frame - ramp_in, 0.0), (frame, 1.0), (frame + ramp_out, 0.0)]


def sequence_plan(entries, fade_ends=False):
    """Pose-to-pose keys for one sequence level.

    ``entries`` is ``[(target_index, frame), ...]``. Each target is keyed 1 on
    its own frame and 0 on its neighbours' frames, so with linear tangents the
    weights of neighbouring poses always sum to 1 and the poses crossfade.
    The first and last poses hold outside the level's range, unless
    ``fade_ends`` is set, in which case they reach 0 one frame outside it.
    """
    ordered = sorted(entries, key=lambda e: (float(e[1]), e[0]))
    frames = [float(f) for _t, f in ordered]
    if len(set(frames)) != len(frames):
        raise ValueError("Two tweaks on the same level share a frame")
    plan = {}
    for i, (target, frame) in enumerate(ordered):
        keys = []
        if i > 0:
            keys.append((frames[i - 1], 0.0))
        elif fade_ends:
            keys.append((frames[i] - 1.0, 0.0))
        keys.append((frames[i], 1.0))
        if i < len(ordered) - 1:
            keys.append((frames[i + 1], 0.0))
        elif fade_ends:
            keys.append((frames[i] + 1.0, 0.0))
        plan[target] = keys
    return plan


def adjacent_time(times, current, direction, tol=1e-4):
    """The nearest key time after (``direction`` > 0) or before ``current``, or None."""
    if direction > 0:
        later = [t for t in times if t > current + tol]
        return min(later) if later else None
    earlier = [t for t in times if t < current - tol]
    return max(earlier) if earlier else None


def key_state(times, current, tol=1e-4):
    """Channel Box style state: "none", "animated" or "key" (a key on this frame)."""
    if not times:
        return "none"
    return "key" if any(abs(t - current) < tol for t in times) else "animated"


def evaluate_linear(keys, frame):
    """Value of linear keys with constant extrapolation (matches Maya's default)."""
    if not keys:
        return None
    keys = sorted(keys)
    if frame <= keys[0][0]:
        return keys[0][1]
    if frame >= keys[-1][0]:
        return keys[-1][1]
    for (t0, v0), (t1, v1) in zip(keys, keys[1:]):
        if t0 <= frame <= t1:
            return v0 + (v1 - v0) * (frame - t0) / (t1 - t0)
    return keys[-1][1]


def previous_pose(entries, frame):
    """Target of the latest pose before ``frame`` on a level, or None."""
    earlier = [(f, t) for t, f in entries if float(f) < float(frame)]
    return max(earlier)[1] if earlier else None


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------

def empty_metadata():
    return {"version": METADATA_VERSION, "targets": {}}


def decode_metadata(text):
    """Parse the node's JSON. Bad or missing data gives an empty record."""
    if not text:
        return empty_metadata()
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return empty_metadata()
    if not isinstance(data, dict) or not isinstance(data.get("targets"), dict):
        return empty_metadata()
    targets = {}
    for key, info in data["targets"].items():
        try:
            index = int(key)
        except (TypeError, ValueError):
            continue
        if isinstance(info, dict):
            targets[index] = normalise_entry(info)
    return {"version": int(data.get("version", METADATA_VERSION)), "targets": targets}


def encode_metadata(meta):
    targets = {str(k): v for k, v in sorted(meta.get("targets", {}).items())}
    return json.dumps({"version": METADATA_VERSION, "targets": targets}, sort_keys=True)


def normalise_entry(info):
    mode = info.get("mode", MODE_STATIC)
    if mode not in MODES:
        mode = MODE_STATIC
    frame = info.get("frame")
    return {
        "label": str(info.get("label", "tweak")),
        "kind": str(info.get("kind", KIND_SCULPT)),
        "mode": mode,
        "frame": float(frame) if frame is not None else None,
        "layer": str(info.get("layer", "")),
        "ramp_in": float(info.get("ramp_in", 3.0)),
        "ramp_out": float(info.get("ramp_out", 3.0)),
    }


def make_entry(label, kind=KIND_SCULPT, mode=MODE_STATIC, frame=None, layer="",
               ramp_in=3.0, ramp_out=3.0):
    return normalise_entry({"label": label, "kind": kind, "mode": mode, "frame": frame,
                            "layer": layer, "ramp_in": ramp_in, "ramp_out": ramp_out})


def level_entries(meta, layer):
    """``[(target, frame)]`` of the sequence tweaks on one level."""
    return [(t, e["frame"]) for t, e in sorted(meta["targets"].items())
            if e["mode"] == MODE_SEQUENCE and e["layer"] == layer and e["frame"] is not None]


def find_sequence_target(meta, layer, frame):
    for t, f in level_entries(meta, layer):
        if abs(f - float(frame)) < 1e-4:
            return t
    return None


def targets_to_mute(meta, mute_mode, layer=""):
    """Which tweaks are switched off while you sculpt."""
    if mute_mode == MUTE_NONE:
        return []
    out = []
    for t, e in sorted(meta["targets"].items()):
        if mute_mode == MUTE_ALL:
            out.append(t)
        elif mute_mode == MUTE_STATIC and e["mode"] in (MODE_STATIC, MODE_PULSE, MODE_MANUAL):
            out.append(t)
        elif mute_mode == MUTE_SEQUENCE and e["mode"] == MODE_SEQUENCE:
            out.append(t)
        elif mute_mode == MUTE_LEVEL and e["mode"] == MODE_SEQUENCE and e["layer"] == layer:
            out.append(t)
    return out


def effect_layer(kind):
    return "fx_" + kind


_ALIAS_BAD = re.compile(r"[^A-Za-z0-9_]")


def safe_alias(label, taken, prefix="tw_"):
    """A valid, unique Maya attribute name for a tweak's weight."""
    base = _ALIAS_BAD.sub("_", str(label).strip()) or "tweak"
    if base[0].isdigit():
        base = "_" + base
    base = prefix + base
    name, n = base, 1
    taken = set(taken)
    while name in taken:
        n += 1
        name = "%s_%d" % (base, n)
    return name


def frame_label(kind, frame=None, layer=""):
    parts = [kind]
    if layer and not layer.startswith("fx_"):
        parts.append(layer)
    if frame is not None:
        parts.append("f%s" % ("%g" % float(frame)).replace(".", "p").replace("-", "m"))
    return "_".join(parts)


# ---------------------------------------------------------------------------
# Utilities: cameras, colours, channel clipboard, Alembic job
# ---------------------------------------------------------------------------

def next_camera(cameras, current, skip_ortho=True):
    """Next camera after ``current`` in ``[(name, is_ortho), ...]``, wrapping round."""
    usable = [name for name, ortho in cameras if not (skip_ortho and ortho)]
    if not usable:
        return None
    if current not in usable:
        return usable[0]
    return usable[(usable.index(current) + 1) % len(usable)]


PALETTE = ("#d9534f", "#f0ad4e", "#f5d76e", "#5cb85c", "#5bc0de",
           "#428bca", "#9b59b6", "#e98fb4", "#c7c7c7", "#5a5a5a")


def hex_to_rgb(text):
    text = text.lstrip("#")
    if len(text) != 6:
        raise ValueError("Expected a colour such as #3a7bd5")
    return tuple(int(text[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def rgb_to_hex(rgb):
    return "#" + "".join("%02x" % int(round(max(0.0, min(1.0, c)) * 255)) for c in rgb)


def random_colour(rng=None):
    """A saturated, mid-bright colour that reads well in the viewport."""
    import colorsys
    rng = rng or random.Random()
    return rgb_to_hex(colorsys.hsv_to_rgb(rng.random(), 0.45 + 0.35 * rng.random(),
                                          0.65 + 0.3 * rng.random()))


CLIPBOARD_FORMAT = "atk_tweaker_channels"


def encode_clipboard(values):
    """``{node: {attr: value}}`` -> JSON text for an optionVar."""
    clean = {}
    for node, attrs in values.items():
        clean[str(node)] = {str(a): _plain(v) for a, v in attrs.items()}
    return json.dumps({"format": CLIPBOARD_FORMAT, "version": 1, "nodes": clean}, sort_keys=True)


def _plain(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, str):
        return value
    raise ValueError("Channel value of type %s cannot be stored" % type(value).__name__)


def decode_clipboard(text):
    """Parse the clipboard. Data only: JSON, never executed."""
    try:
        data = json.loads(text or "")
    except ValueError:
        return {}
    if not isinstance(data, dict) or data.get("format") != CLIPBOARD_FORMAT:
        return {}
    nodes = data.get("nodes")
    return nodes if isinstance(nodes, dict) else {}


def paste_plan(clipboard, targets):
    """``[(target_node, attr, value)]``.

    One copied node pastes onto every target. Several copied nodes paste by
    matching short name first, then by selection order.
    """
    if not clipboard or not targets:
        return []
    sources = sorted(clipboard)
    plan = []
    for i, target in enumerate(targets):
        short = target.split("|")[-1].split(":")[-1]
        if len(sources) == 1:
            source = sources[0]
        else:
            by_name = [s for s in sources if s.split("|")[-1].split(":")[-1] == short]
            source = by_name[0] if by_name else (sources[i] if i < len(sources) else None)
        if source is None:
            continue
        for attr, value in sorted(clipboard[source].items()):
            plan.append((target, attr, value))
    return plan


def abc_job(roots, path, start, end, attrs=(), world_space=True):
    """AbcExport ``-j`` job string. Paths with spaces are quoted."""
    if not roots:
        raise ValueError("Select at least one mesh to export")
    parts = ["-frameRange %d %d" % (int(start), int(end)), "-uvWrite", "-writeVisibility",
             "-dataFormat ogawa"]
    if world_space:
        parts.append("-worldSpace")
    for attr in attrs:
        parts.append("-attr %s" % attr)
    for root in roots:
        parts.append("-root %s" % root)
    parts.append('-file "%s"' % str(path).replace("\\", "/"))
    return " ".join(parts)


def version_label(path, existing):
    """``hero_v003`` from ``.../hero_v003.abc``; unique among ``existing``."""
    stem = re.split(r"[\\/]", str(path))[-1]
    stem = re.sub(r"\.abc$", "", stem, flags=re.I)
    stem = _ALIAS_BAD.sub("_", stem) or "version"
    name, n = stem, 1
    while name in existing:
        n += 1
        name = "%s_%d" % (stem, n)
    return name


# ---------------------------------------------------------------------------
# Surface handle falloff shapes
# ---------------------------------------------------------------------------
# (position, value, interpolation) ramp points. Position 0 is the handle
# centre, 1 the radius. Interpolation uses Maya's ramp codes:
# 0 none, 1 linear, 2 smooth, 3 spline.
FALLOFF_PRESETS = {
    "Smooth": ((0.0, 1.0, 2), (1.0, 0.0, 2)),
    "Linear": ((0.0, 1.0, 1), (1.0, 0.0, 1)),
    "Sharp": ((0.0, 1.0, 3), (0.25, 0.35, 3), (1.0, 0.0, 3)),
    "Dome": ((0.0, 1.0, 3), (0.6, 0.85, 3), (1.0, 0.0, 3)),
    "Plateau": ((0.0, 1.0, 1), (0.5, 1.0, 2), (1.0, 0.0, 2)),
}
FALLOFF_NAMES = ("Smooth", "Linear", "Sharp", "Dome", "Plateau")
