"""Frame-baked effects: Smooth Motion, Stick to Surface, Push Out and Pin to World.

Each effect samples the mesh over a frame range, works out a per-frame
correction for the masked vertices, and stores one sequence target per frame
on its own level (``fx_<effect>``). Neighbouring frame targets crossfade
linearly, and the ends fade to 0 one frame outside the range.

Running an effect again replaces its previous result. The old level is
removed *before* sampling, so the new result is never computed on top of the
old one. Every run is one Undo.
"""
from maya import cmds

from . import core
from .engine import (TweakError, add_tweak, delete_layer, ensure_tweak_node, mask_for,
                     read_meta, rekey_level, resolve_mesh, sample_mesh_fn, sample_points,
                     undo_chunk, world_matrix)

try:
    import maya.api.OpenMaya as om
except ImportError:
    om = None


def frame_range(start=None, end=None):
    """Default to the playback range."""
    if start is None:
        start = cmds.playbackOptions(query=True, minTime=True)
    if end is None:
        end = cmds.playbackOptions(query=True, maxTime=True)
    start, end = int(round(start)), int(round(end))
    if end < start:
        raise TweakError("The end frame is before the start frame")
    return list(range(start, end + 1))


def _world_points(points, matrix):
    return [core.xform_point(p, matrix) for p in points]


def _store(mesh, kind, frames, deltas):
    """One sequence target per frame on the effect's level."""
    layer = core.effect_layer(kind)
    ensure_tweak_node(mesh)
    count = 0
    for frame, delta in zip(frames, deltas):
        entry = core.make_entry(core.frame_label(kind, frame), kind, core.MODE_SEQUENCE,
                                frame, layer)
        add_tweak(mesh, delta, entry, rekey=False)
        count += 1
    node = ensure_tweak_node(mesh)
    rekey_level(node, layer, read_meta(node), resolve_mesh(mesh)[0])
    return count


def _prepare(mesh, kind, mask):
    xf, shape = resolve_mesh(mesh)
    if mask is None:
        mask = mask_for(shape)
    delete_layer(xf, core.effect_layer(kind))
    return xf, shape, mask


def _to_object(xf, frames, world_deltas):
    return [core.world_delta_to_object(d, world_matrix(xf, f)) for f, d in zip(frames, world_deltas)]


def smooth_motion(mesh, start=None, end=None, sigma=2.0, world_space=True, mask=None):
    """Gaussian-filter the masked vertices' motion over time."""
    frames = frame_range(start, end)
    with undo_chunk("smooth motion"):
        xf, shape, mask = _prepare(mesh, core.KIND_SMOOTH, mask)
        series = [sample_points(shape, f) for f in frames]
        if world_space:
            series = [_world_points(pts, world_matrix(xf, f)) for pts, f in zip(series, frames)]
        deltas = core.smooth_motion_deltas(series, sigma, mask)
        if world_space:
            deltas = _to_object(xf, frames, deltas)
        return _store(xf, core.KIND_SMOOTH, frames, deltas)


def pin_to_world(mesh, start=None, end=None, bind_frame=None, mask=None):
    """Hold the masked vertices where they were in world space on the bind frame."""
    frames = frame_range(start, end)
    bind = frames[0] if bind_frame is None else bind_frame
    with undo_chunk("pin to world"):
        xf, shape, mask = _prepare(mesh, core.KIND_PIN, mask)
        target = _world_points(sample_points(shape, bind), world_matrix(xf, bind))
        indices = core.masked_indices(mask, len(target))
        deltas = []
        for frame in frames:
            current = _world_points(sample_points(shape, frame), world_matrix(xf, frame))
            deltas.append(_masked_pull(current, target, indices, mask))
        return _store(xf, core.KIND_PIN, frames, _to_object(xf, frames, deltas))


def _masked_pull(current, target, indices, mask):
    delta = {}
    for i in indices:
        d = core.v_scale(core.v_sub(target[i], current[i]), core.mask_weight(mask, i))
        if core.v_length(d) > 1e-7:
            delta[i] = d
    return delta


def _driver_world(driver_shape, driver_xf, frame):
    return _world_points(sample_points(driver_shape, frame), world_matrix(driver_xf, frame))


def _face_triangles(fn):
    """``{face_id: [(a, b, c), ...]}`` from an MFnMesh."""
    counts, ids = fn.getTriangles()
    out, at = {}, 0
    for face, count in enumerate(counts):
        out[face] = [(ids[at + 3 * k], ids[at + 3 * k + 1], ids[at + 3 * k + 2]) for k in range(count)]
        at += 3 * count
    return out


def stick_to_surface(mesh, driver, start=None, end=None, bind_frame=None, mask=None):
    """Keep each masked vertex at its bind-frame offset from the closest point on ``driver``."""
    frames = frame_range(start, end)
    bind = frames[0] if bind_frame is None else bind_frame
    driver_xf, driver_shape = resolve_mesh(driver)
    with undo_chunk("stick to surface"):
        xf, shape, mask = _prepare(mesh, core.KIND_STICK, mask)
        if driver_shape == shape:
            raise TweakError("Pick a different mesh as the driver")
        fn = sample_mesh_fn(driver_shape, bind)
        per_face = _face_triangles(fn)
        triangles = [t for face in sorted(per_face) for t in per_face[face]]
        driver_bind = _driver_world(driver_shape, driver_xf, bind)
        driver_inverse = core.mat_inverse(world_matrix(driver_xf, bind))
        points = _world_points(sample_points(shape, bind), world_matrix(xf, bind))
        indices = core.masked_indices(mask, len(points))
        bindings = {}
        for i in indices:
            local = core.xform_point(points[i], driver_inverse)
            try:
                _point, face = fn.getClosestPoint(om.MPoint(*local), om.MSpace.kObject)
                candidates = per_face.get(face) or triangles
            except Exception:
                candidates = triangles
            t_index, bary, _q = core.closest_on_triangles(points[i], driver_bind, candidates)
            tri = candidates[t_index]
            frame_axes = core.triangle_frame(*(driver_bind[k] for k in tri))
            offset = core.v_sub(points[i], core.barycentric_point(driver_bind, tri, bary))
            bindings[i] = (tri, bary, tuple(core.v_dot(offset, a) for a in frame_axes))
        deltas = []
        for frame in frames:
            driver_now = _driver_world(driver_shape, driver_xf, frame)
            current = _world_points(sample_points(shape, frame), world_matrix(xf, frame))
            delta = {}
            for i, (tri, bary, local) in bindings.items():
                target = core.follow_surface((0, bary, local), driver_now, [tri])
                d = core.v_scale(core.v_sub(target, current[i]), core.mask_weight(mask, i))
                if core.v_length(d) > 1e-7:
                    delta[i] = d
            deltas.append(delta)
        return _store(xf, core.KIND_STICK, frames, _to_object(xf, frames, deltas))


def push_out(mesh, driver, start=None, end=None, skin_offset=0.1, mask=None):
    """Push masked vertices that sink into ``driver`` back out, ``skin_offset`` above it."""
    frames = frame_range(start, end)
    driver_xf, driver_shape = resolve_mesh(driver)
    with undo_chunk("push out"):
        xf, shape, mask = _prepare(mesh, core.KIND_PUSH, mask)
        if driver_shape == shape:
            raise TweakError("Pick a different mesh as the collider")
        deltas = []
        for frame in frames:
            fn = sample_mesh_fn(driver_shape, frame)
            d_matrix = world_matrix(driver_xf, frame)
            d_inverse = core.mat_inverse(d_matrix)
            current = _world_points(sample_points(shape, frame), world_matrix(xf, frame))
            delta = {}
            for i in core.masked_indices(mask, len(current)):
                local = core.xform_point(current[i], d_inverse)
                point, normal, _face = fn.getClosestPointAndNormal(om.MPoint(*local), om.MSpace.kObject)
                surface = core.xform_point((point.x, point.y, point.z), d_matrix)
                n_world = core.xform_normal((normal.x, normal.y, normal.z), d_matrix)
                fixed = core.push_out_point(current[i], surface, n_world, skin_offset)
                d = core.v_scale(core.v_sub(fixed, current[i]), core.mask_weight(mask, i))
                if core.v_length(d) > 1e-7:
                    delta[i] = d
            deltas.append(delta)
        return _store(xf, core.KIND_PUSH, frames, _to_object(xf, frames, deltas))


def remove_effect(mesh, kind):
    with undo_chunk("remove effect"):
        return delete_layer(resolve_mesh(mesh)[0], core.effect_layer(kind))
