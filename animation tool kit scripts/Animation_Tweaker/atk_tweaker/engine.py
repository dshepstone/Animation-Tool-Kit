"""Maya engine for Animation Tweaker: the tweak node, its targets, keys and sculpting.

No Qt in this module. The window, tests and scripts all go through these
functions.

Scene layout
------------
Each mesh gets one blendShape node, ``<mesh>_atkTweaks``, inserted *after* the
skinCluster and other deformers. Every tweak is one target on that node. A
target has no geometry connected: its object-space offsets are written
straight into ``inputTarget[0].inputTargetGroup[i].inputTargetItem[6000]``.
Nothing else is left in the scene, so deleting the node removes Animation
Tweaker completely.

The node carries three extra attributes:

* ``atkTweakerNode``   (bool)   marks the node as ours.
* ``atkTweakerMeta``   (string) JSON describing each target (see core.py).
* ``atkTweakerProxies`` (bool)  weights are driven from proxy channels on the
  mesh transform, below a ``TWEAKS`` divider.

Writes use ``cmds.setAttr``, so each operation is one Undo. Reads use
OpenMaya 2 for speed.
"""
import contextlib
import json

from maya import cmds, mel

try:
    import maya.api.OpenMaya as om
except ImportError:          # the unit tests run without Maya
    om = None

from . import core

MARKER_ATTR = "atkTweakerNode"
META_ATTR = "atkTweakerMeta"
PROXY_FLAG_ATTR = "atkTweakerProxies"
DIVIDER_ATTR = "TWEAKS"
TARGET_ITEM = 6000
NODE_SUFFIX = "_atkTweaks"

SCULPT_TAG_ATTR = "atkTweakerSculpt"       # JSON session record on the sculpt mesh
SCULPT_SHADER = "atkTweakerSculpt_MAT"


class TweakError(RuntimeError):
    """A problem the artist can fix (shown in the window, not as a traceback)."""


@contextlib.contextmanager
def undo_chunk(name):
    cmds.undoInfo(openChunk=True, chunkName="Animation Tweaker: " + name)
    try:
        yield
    finally:
        cmds.undoInfo(closeChunk=True)


# ---------------------------------------------------------------------------
# Mesh lookup
# ---------------------------------------------------------------------------

def resolve_mesh(node):
    """``(transform, shape)`` long names for a mesh transform, shape or component."""
    node = node.split(".")[0]
    found = cmds.ls(node, long=True) or []
    if not found:
        raise TweakError("'%s' does not exist" % node)
    node = found[0]
    if cmds.nodeType(node) == "mesh":
        return cmds.listRelatives(node, parent=True, fullPath=True)[0], node
    shapes = cmds.listRelatives(node, shapes=True, noIntermediate=True,
                                type="mesh", fullPath=True) or []
    if not shapes:
        raise TweakError("'%s' is not a polygon mesh" % node.split("|")[-1])
    return node, shapes[0]


def selected_mesh():
    """The first mesh in the selection (object or components)."""
    for item in cmds.ls(selection=True, long=True, flatten=False) or []:
        try:
            return resolve_mesh(item)[0]
        except TweakError:
            continue
    raise TweakError("Select a polygon mesh (or some of its vertices)")


def short_name(node):
    return node.split("|")[-1]


# ---------------------------------------------------------------------------
# OpenMaya reads
# ---------------------------------------------------------------------------

def _mobject(node):
    sel = om.MSelectionList()
    sel.add(node)
    return sel.getDependNode(0)


def _dag(node):
    sel = om.MSelectionList()
    sel.add(node)
    return sel.getDagPath(0)


def read_points(shape, world=False):
    """Evaluated vertex positions of a mesh shape."""
    fn = om.MFnMesh(_dag(shape))
    space = om.MSpace.kWorld if world else om.MSpace.kObject
    return [(p.x, p.y, p.z) for p in fn.getPoints(space)]


def mesh_faces(shape):
    counts, ids = om.MFnMesh(_dag(shape)).getVertices()
    faces, at = [], 0
    for count in counts:
        faces.append(list(ids[at:at + count]))
        at += count
    return faces


def mesh_triangles_from_fn(fn):
    _counts, ids = fn.getTriangles()
    return [(ids[i], ids[i + 1], ids[i + 2]) for i in range(0, len(ids), 3)]


def vertex_normals(shape):
    try:
        normals = om.MFnMesh(_dag(shape)).getVertexNormals(False, om.MSpace.kObject)
        return [core.v_normalize((n.x, n.y, n.z)) for n in normals]
    except Exception:
        return core.vertex_normals(read_points(shape), mesh_faces(shape))


def _mesh_data_at(shape, frame):
    """The shape's ``outMesh`` evaluated at ``frame`` without changing the time."""
    plug = om.MFnDependencyNode(_mobject(shape)).findPlug("outMesh", False)
    context = om.MDGContext(om.MTime(float(frame), om.MTime.uiUnit()))
    guard = getattr(om, "MDGContextGuard", None)
    if guard is not None:
        with guard(context):
            return plug.asMObject()
    try:
        return plug.asMObject(context)
    except TypeError:
        previous = context.makeCurrent()
        try:
            return plug.asMObject()
        finally:
            previous.makeCurrent()


def sample_points(shape, frame):
    """Object-space points at ``frame``, sampled through an MDGContext."""
    try:
        data = _mesh_data_at(shape, frame)
        return [(p.x, p.y, p.z) for p in om.MFnMesh(data).getPoints(om.MSpace.kObject)]
    except Exception:
        # Last resort for Maya builds whose context API differs: move the time.
        now = cmds.currentTime(query=True)
        try:
            cmds.currentTime(frame, update=True)
            return read_points(shape)
        finally:
            cmds.currentTime(now, update=True)


def sample_mesh_fn(shape, frame):
    """An MFnMesh over the shape's data at ``frame`` (for closest-point queries)."""
    return om.MFnMesh(_mesh_data_at(shape, frame))


def world_matrix(transform, frame=None):
    if frame is None:
        return tuple(cmds.getAttr(transform + ".worldMatrix[0]"))
    return tuple(cmds.getAttr(transform + ".worldMatrix[0]", time=frame))


# ---------------------------------------------------------------------------
# Masks from soft selection
# ---------------------------------------------------------------------------

def soft_selection_masks():
    """``{shape: mask}`` from the current (soft) selection.

    A whole object selected gives ``None`` (no mask). Vertex selections carry
    their soft-selection falloff. Face and edge selections are converted to
    vertices at full weight.
    """
    masks = {}
    try:
        selection = om.MGlobal.getRichSelection().getSelection()
    except Exception:
        selection = om.MGlobal.getActiveSelectionList()
    it = om.MItSelectionList(selection)
    while not it.isDone():
        try:
            dag, component = it.getComponent()
        except Exception:
            it.next()
            continue
        try:
            dag.extendToShape()
        except Exception:
            pass
        if dag.apiType() != om.MFn.kMesh:
            it.next()
            continue
        shape = dag.fullPathName()
        if component.isNull():
            masks[shape] = None
        else:
            mask = masks.setdefault(shape, {})
            if mask is None:
                it.next()
                continue
            if component.apiType() == om.MFn.kMeshVertComponent:
                fn = om.MFnSingleIndexedComponent(component)
                weighted = fn.hasWeights
                for k, index in enumerate(fn.getElements()):
                    weight = fn.weight(k).influence if weighted else 1.0
                    mask[index] = max(mask.get(index, 0.0), weight)
            else:
                fn = om.MFnSingleIndexedComponent(component)
                kind = {om.MFn.kMeshPolygonComponent: "f",
                        om.MFn.kMeshEdgeComponent: "e"}.get(component.apiType())
                if kind:
                    names = ["%s.%s[%d]" % (shape, kind, i) for i in fn.getElements()]
                    verts = cmds.ls(cmds.polyListComponentConversion(names, toVertex=True),
                                    flatten=True) or []
                    for index in core.expand_components(v.split(".")[-1] for v in verts):
                        mask[index] = 1.0
        it.next()
    return masks


def mask_for(shape):
    """Mask for one mesh from the selection; ``None`` means the whole mesh."""
    masks = soft_selection_masks()
    for key, mask in masks.items():
        if key == shape or key.split("|")[-1] == shape.split("|")[-1]:
            return mask
    return None


# ---------------------------------------------------------------------------
# The tweak node
# ---------------------------------------------------------------------------

def find_tweak_node(mesh):
    _xf, shape = resolve_mesh(mesh)
    for node in cmds.listHistory(shape, pruneDagObjects=True) or []:
        if cmds.nodeType(node) == "blendShape" and cmds.attributeQuery(MARKER_ATTR, node=node, exists=True):
            return node
    return None


def ensure_tweak_node(mesh):
    node = find_tweak_node(mesh)
    if node:
        return node
    xf, shape = resolve_mesh(mesh)
    name = short_name(xf).split(":")[-1] + NODE_SUFFIX
    # ``cmds.deformer`` appends to the end of the chain (after the skinCluster)
    # on the existing shape. ``blendShape(after=True)`` would instead create a
    # second "...ShapeDeformed" shape, leaving callers holding a stale shape.
    node = cmds.deformer(shape, type="blendShape", name=name)[0]
    cmds.addAttr(node, longName=MARKER_ATTR, attributeType="bool", defaultValue=True)
    cmds.addAttr(node, longName=META_ATTR, dataType="string")
    cmds.addAttr(node, longName=PROXY_FLAG_ATTR, attributeType="bool", defaultValue=False)
    write_meta(node, core.empty_metadata())
    return node


def read_meta(node):
    return core.decode_metadata(cmds.getAttr(node + "." + META_ATTR))


def write_meta(node, meta):
    cmds.setAttr(node + "." + META_ATTR, core.encode_metadata(meta), type="string")


def target_indices(node):
    return sorted(cmds.getAttr(node + ".weight", multiIndices=True) or [])


def next_target_index(node):
    used = set(target_indices(node))
    used.update(cmds.getAttr(node + ".inputTarget[0].inputTargetGroup", multiIndices=True) or [])
    return max(used) + 1 if used else 0


def alias_map(node):
    """``{index: alias}`` of the node's named weights."""
    pairs = cmds.aliasAttr(node, query=True) or []
    out = {}
    for alias, plug in zip(pairs[::2], pairs[1::2]):
        if plug.startswith("weight["):
            out[int(plug[7:-1])] = alias
    return out


def _item_plug(node, index):
    return "%s.inputTarget[0].inputTargetGroup[%d].inputTargetItem[%d]" % (node, index, TARGET_ITEM)


def write_target(node, index, delta):
    components, points = core.delta_to_target(delta)
    item = _item_plug(node, index)
    cmds.setAttr(item + ".inputPointsTarget", len(points), *points, type="pointArray")
    cmds.setAttr(item + ".inputComponentsTarget", len(components), *components, type="componentList")


def read_target(node, index):
    item = _item_plug(node, index)
    points = cmds.getAttr(item + ".inputPointsTarget") or []
    components = cmds.getAttr(item + ".inputComponentsTarget") or []
    return core.target_to_delta(components, points)


def weight_plug(node, index):
    return "%s.weight[%d]" % (node, index)


def proxies_enabled(node):
    return bool(cmds.getAttr(node + "." + PROXY_FLAG_ATTR))


def driver_plug(node, index, mesh=None):
    """The plug artists key: the proxy channel when proxies are on, else the weight."""
    if proxies_enabled(node):
        xf = mesh or _mesh_of(node)
        alias = alias_map(node).get(index)
        if alias and cmds.attributeQuery(alias, node=xf, exists=True):
            return "%s.%s" % (xf, alias)
    return weight_plug(node, index)


def _mesh_of(node):
    shapes = cmds.deformer(node, query=True, geometry=True) or []
    if not shapes:
        raise TweakError("%s has no mesh" % node)
    return resolve_mesh(shapes[0])[0]


# ---------------------------------------------------------------------------
# Keys
# ---------------------------------------------------------------------------

def _set_keys(plug, keys):
    cmds.cutKey(plug, clear=True)
    for frame, value in keys:
        cmds.setKeyframe(plug, time=frame, value=value,
                         inTangentType="linear", outTangentType="linear")


def apply_keys(node, index, meta, mesh=None):
    """Key one tweak according to its mode (sequence tweaks rekey their level)."""
    entry = meta["targets"][index]
    plug = driver_plug(node, index, mesh)
    if entry["mode"] == core.MODE_STATIC:
        cmds.cutKey(plug, clear=True)
        cmds.setAttr(plug, 1.0)
    elif entry["mode"] == core.MODE_PULSE:
        _set_keys(plug, core.pulse_keys(entry["frame"], entry["ramp_in"], entry["ramp_out"]))
    elif entry["mode"] == core.MODE_MANUAL:
        # Hand-keyed tweaks keep their keys. A new one starts with one key at 1.
        if not key_times(plug):
            frame = entry["frame"] if entry["frame"] is not None else cmds.currentTime(query=True)
            cmds.setKeyframe(plug, time=frame, value=1.0,
                             inTangentType="linear", outTangentType="linear")
    else:
        rekey_level(node, entry["layer"], meta, mesh)


def rekey_level(node, layer, meta=None, mesh=None):
    meta = meta or read_meta(node)
    fade = layer.startswith("fx_")
    plan = core.sequence_plan(core.level_entries(meta, layer), fade_ends=fade)
    for index, keys in plan.items():
        _set_keys(driver_plug(node, index, mesh), keys)


def key_times(plug):
    """Times of the keys driving ``plug`` (empty when it is not animated)."""
    if not cmds.listConnections(plug, source=True, destination=False, type="animCurve"):
        return []
    return sorted(cmds.keyframe(plug, query=True, timeChange=True) or [])


def _take_over(node, meta, indices, xf):
    """Hand-keying a tweak switches it to manual mode, so automatic keying
    (pulse ramps, sequence rekeys) never overwrites the animator's keys.
    A sequence pose that leaves its level drops out of that level's
    crossfade, and the rest of the level is rekeyed."""
    levels = set()
    changed = False
    for index in indices:
        entry = meta["targets"].get(index)
        if entry is None or entry["mode"] == core.MODE_MANUAL:
            continue
        if entry["mode"] == core.MODE_SEQUENCE:
            levels.add(entry["layer"])
        entry["mode"] = core.MODE_MANUAL
        entry["layer"] = core.MODE_MANUAL
        changed = True
    if changed:
        write_meta(node, meta)
    for layer in levels:
        rekey_level(node, layer, meta, xf)


def key_tweaks(mesh, indices, value=None, frame=None):
    """Key the weight of each tweak on ``frame`` (default: now).

    ``value`` None keys the weight it shows now (including an unkeyed slider
    change). The tweaks switch to manual mode.
    """
    node = _require_node(mesh)
    xf = resolve_mesh(mesh)[0]
    frame = cmds.currentTime(query=True) if frame is None else frame
    with undo_chunk("key tweaks"):
        values = {i: (cmds.getAttr(driver_plug(node, i, xf)) if value is None else value)
                  for i in indices}
        _take_over(node, read_meta(node), indices, xf)
        for index in indices:
            cmds.setKeyframe(driver_plug(node, index, xf), time=frame, value=values[index],
                             inTangentType="linear", outTangentType="linear")
    return len(indices)


def remove_tweak_keys(mesh, indices, frame=None):
    """Remove the key on ``frame`` (default: now). Returns how many keys went."""
    node = _require_node(mesh)
    xf = resolve_mesh(mesh)[0]
    frame = cmds.currentTime(query=True) if frame is None else frame
    with undo_chunk("remove tweak keys"):
        hits = [i for i in indices
                if core.key_state(key_times(driver_plug(node, i, xf)), frame) == "key"]
        _take_over(node, read_meta(node), hits, xf)
        for index in hits:
            # cutKey(clear=True) reports 0 even when it removes a key, so count hits.
            cmds.cutKey(driver_plug(node, index, xf), time=(frame, frame), clear=True)
    return len(hits)


def clear_tweak_keys(mesh, indices):
    """Delete all keys, holding each tweak at the weight it shows now."""
    node = _require_node(mesh)
    xf = resolve_mesh(mesh)[0]
    with undo_chunk("clear tweak keys"):
        values = {i: cmds.getAttr(driver_plug(node, i, xf)) for i in indices}
        _take_over(node, read_meta(node), indices, xf)
        for index in indices:
            plug = driver_plug(node, index, xf)
            _delete_curves(plug)
            cmds.setAttr(plug, values[index])
    return len(indices)


def set_tweak_mode(mesh, indices, mode, frame=None, layer="L1", ramp_in=3.0, ramp_out=3.0):
    """Change how tweaks are keyed and rekey them.

    Static: always 1. Pulse: 0-1-0 around ``frame``. Sequence: a pose on
    ``layer`` at ``frame`` (one tweak, on a free frame). Manual: keep the keys.
    """
    if mode not in core.MODES:
        raise TweakError("Unknown keying mode %r" % mode)
    node = _require_node(mesh)
    xf = resolve_mesh(mesh)[0]
    frame = cmds.currentTime(query=True) if frame is None else float(frame)
    layer = layer or "L1"
    meta = read_meta(node)
    if mode == core.MODE_SEQUENCE:
        if len(indices) != 1:
            raise TweakError("Move one tweak at a time into a sequence level")
        taken = core.find_sequence_target(meta, layer, frame)
        if taken is not None and taken != indices[0]:
            raise TweakError("Level %s already has a pose on frame %g" % (layer, frame))
    with undo_chunk("set tweak mode"):
        levels = set()
        for index in indices:
            entry = meta["targets"].get(index) or core.make_entry(
                alias_map(node).get(index, "tweak%d" % index))
            if entry["mode"] == core.MODE_SEQUENCE:
                levels.add(entry["layer"])
            entry["mode"] = mode
            if mode == core.MODE_STATIC:
                entry["frame"], entry["layer"] = None, mode
            elif mode == core.MODE_MANUAL:
                entry["layer"] = mode
            else:
                entry["frame"] = frame
                entry["layer"] = layer if mode == core.MODE_SEQUENCE else mode
                if mode == core.MODE_PULSE:
                    entry["ramp_in"], entry["ramp_out"] = float(ramp_in), float(ramp_out)
            meta["targets"][index] = entry
        write_meta(node, meta)
        if mode == core.MODE_SEQUENCE:
            levels.add(layer)
        else:
            for index in indices:
                apply_keys(node, index, meta, xf)
        for level in levels:
            rekey_level(node, level, meta, xf)
    return len(indices)


def jump_to_key(mesh, indices, direction):
    """Move the current time to the previous (-1) or next (+1) key of these
    tweaks (all tweaks on the mesh when ``indices`` is empty)."""
    node = _require_node(mesh)
    xf = resolve_mesh(mesh)[0]
    indices = list(indices) or target_indices(node)
    times = set()
    for index in indices:
        times.update(key_times(driver_plug(node, index, xf)))
    target = core.adjacent_time(sorted(times), cmds.currentTime(query=True), direction)
    if target is None:
        raise TweakError("No %s tweak key" % ("later" if direction > 0 else "earlier"))
    cmds.currentTime(target)
    return target


def key_weight(mesh, index, value=None):
    """Key a tweak's weight (or proxy) on the current frame (switches it to manual)."""
    return key_tweaks(mesh, [index], value)


def set_weight(mesh, index, value):
    node = _require_node(mesh)
    plug = driver_plug(node, index)
    if cmds.listConnections(plug, source=True, destination=False):
        # Keyed: the new value lasts until the frame changes unless it is keyed.
        cmds.setAttr(plug, value)
        return False
    cmds.setAttr(plug, value)
    return True


def _require_node(mesh):
    node = find_tweak_node(mesh)
    if not node:
        raise TweakError("%s has no tweaks yet" % short_name(resolve_mesh(mesh)[0]))
    return node


# ---------------------------------------------------------------------------
# Proxy channels
# ---------------------------------------------------------------------------

def _ensure_divider(xf):
    if not cmds.attributeQuery(DIVIDER_ATTR, node=xf, exists=True):
        cmds.addAttr(xf, longName=DIVIDER_ATTR, attributeType="enum", enumName="--------")
        cmds.setAttr(xf + "." + DIVIDER_ATTR, edit=True, channelBox=True)
        cmds.setAttr(xf + "." + DIVIDER_ATTR, lock=True)


def _add_proxy(node, xf, index, alias):
    if not cmds.attributeQuery(alias, node=xf, exists=True):
        cmds.addAttr(xf, longName=alias, attributeType="double", keyable=True,
                     softMinValue=0.0, softMaxValue=1.0, defaultValue=0.0)
    proxy = "%s.%s" % (xf, alias)
    weight = weight_plug(node, index)
    sources = cmds.listConnections(weight, source=True, destination=False, plugs=True) or []
    if sources and sources[0] != proxy:
        # Move the weight's animation onto the proxy.
        cmds.disconnectAttr(sources[0], weight)
        cmds.connectAttr(sources[0], proxy, force=True)
    elif not sources:
        cmds.setAttr(proxy, cmds.getAttr(weight))
    if not cmds.isConnected(proxy, weight):
        cmds.connectAttr(proxy, weight, force=True)


def _remove_proxy(node, xf, index, alias):
    proxy = "%s.%s" % (xf, alias)
    if not cmds.attributeQuery(alias, node=xf, exists=True):
        return
    weight = weight_plug(node, index)
    value = cmds.getAttr(proxy)
    sources = cmds.listConnections(proxy, source=True, destination=False, plugs=True) or []
    if cmds.isConnected(proxy, weight):
        cmds.disconnectAttr(proxy, weight)
    if sources:
        cmds.disconnectAttr(sources[0], proxy)
        cmds.connectAttr(sources[0], weight, force=True)
    else:
        cmds.setAttr(weight, value)
    cmds.deleteAttr(proxy)


def set_proxies(mesh, enabled):
    """Show (or remove) keyable proxy channels for every tweak on the mesh transform."""
    node = _require_node(mesh)
    xf = resolve_mesh(mesh)[0]
    with undo_chunk("proxy channels"):
        cmds.setAttr(node + "." + PROXY_FLAG_ATTR, bool(enabled))
        aliases = alias_map(node)
        if enabled:
            _ensure_divider(xf)
        for index in target_indices(node):
            if index not in aliases:
                continue
            if enabled:
                _add_proxy(node, xf, index, aliases[index])
            else:
                _remove_proxy(node, xf, index, aliases[index])
        if not enabled and cmds.attributeQuery(DIVIDER_ATTR, node=xf, exists=True):
            cmds.setAttr(xf + "." + DIVIDER_ATTR, lock=False)
            cmds.deleteAttr(xf + "." + DIVIDER_ATTR)


# ---------------------------------------------------------------------------
# Adding, changing and removing tweaks
# ---------------------------------------------------------------------------

def add_tweak(mesh, delta, entry, rekey=True):
    """Store ``delta`` as a new target and key it. Returns the target index.

    Call inside an undo chunk.
    """
    node = ensure_tweak_node(mesh)
    xf = resolve_mesh(mesh)[0]
    meta = read_meta(node)
    index = next_target_index(node)
    taken = set(alias_map(node).values()) | set(cmds.listAttr(xf) or [])
    alias = core.safe_alias(entry["label"], taken)
    cmds.setAttr(weight_plug(node, index), 0.0)
    write_target(node, index, delta)
    cmds.aliasAttr(alias, weight_plug(node, index))
    meta["targets"][index] = entry
    write_meta(node, meta)
    if proxies_enabled(node):
        _ensure_divider(xf)
        _add_proxy(node, xf, index, alias)
    if rekey:
        apply_keys(node, index, meta, xf)
    return index


def _delete_curves(plug):
    curves = cmds.listConnections(plug, source=True, destination=False, type="animCurve") or []
    if curves:
        cmds.delete(curves)


def delete_tweak(mesh, index, rekey=True):
    """Remove a target with its keys and proxy, then rekey its sequence level."""
    node = _require_node(mesh)
    xf = resolve_mesh(mesh)[0]
    meta = read_meta(node)
    entry = meta["targets"].pop(index, None)
    alias = alias_map(node).get(index)
    weight = weight_plug(node, index)
    if alias and cmds.attributeQuery(alias, node=xf, exists=True):
        proxy = "%s.%s" % (xf, alias)
        _delete_curves(proxy)
        if cmds.isConnected(proxy, weight):
            cmds.disconnectAttr(proxy, weight)
        cmds.deleteAttr(proxy)
    _delete_curves(weight)
    if alias:
        cmds.aliasAttr(node + "." + alias, remove=True)
    cmds.removeMultiInstance(weight, b=True)
    cmds.removeMultiInstance("%s.inputTarget[0].inputTargetGroup[%d]" % (node, index), b=True)
    write_meta(node, meta)
    if rekey and entry and entry["mode"] == core.MODE_SEQUENCE:
        rekey_level(node, entry["layer"], meta, xf)
    return entry


def delete_tweaks(mesh, indices):
    with undo_chunk("delete tweaks"):
        node = _require_node(mesh)
        layers = set()
        for index in sorted(indices, reverse=True):
            entry = delete_tweak(mesh, index, rekey=False)
            if entry and entry["mode"] == core.MODE_SEQUENCE:
                layers.add(entry["layer"])
        meta = read_meta(node)
        for layer in layers:
            rekey_level(node, layer, meta)


def delete_layer(mesh, layer):
    node = find_tweak_node(mesh)
    if not node:
        return 0
    doomed = [t for t, e in read_meta(node)["targets"].items() if e["layer"] == layer]
    for index in sorted(doomed, reverse=True):
        delete_tweak(mesh, index, rekey=False)
    return len(doomed)


def scale_tweak(mesh, index, factor):
    """Amplify (factor > 1), reduce or flip (negative) a tweak's offsets."""
    node = _require_node(mesh)
    with undo_chunk("amplify tweak"):
        write_target(node, index, core.scale_delta(read_target(node, index), factor))


def rename_tweak(mesh, index, label):
    node = _require_node(mesh)
    xf = resolve_mesh(mesh)[0]
    with undo_chunk("rename tweak"):
        meta = read_meta(node)
        meta["targets"][index]["label"] = label
        old = alias_map(node).get(index)
        taken = (set(alias_map(node).values()) | set(cmds.listAttr(xf) or [])) - {old}
        alias = core.safe_alias(label, taken)
        if old != alias:
            if old and cmds.attributeQuery(old, node=xf, exists=True):
                cmds.renameAttr("%s.%s" % (xf, old), alias)
            if old:
                cmds.aliasAttr(node + "." + old, remove=True)
            cmds.aliasAttr(alias, weight_plug(node, index))
        write_meta(node, meta)


def list_tweaks(mesh, from_curves=False):
    """Rows for the tweak list: index, alias, label, kind, mode, frame, layer, weight, keyed.

    ``from_curves`` reads keyed weights from their curves on the current frame
    (for frame changes); otherwise a dragged, unkeyed preview value is kept.
    """
    node = find_tweak_node(mesh)
    if not node:
        return []
    meta = read_meta(node)
    aliases = alias_map(node)
    now = cmds.currentTime(query=True)
    rows = []
    for index in target_indices(node):
        entry = meta["targets"].get(index) or core.make_entry(aliases.get(index, "target%d" % index))
        plug = driver_plug(node, index)
        times = key_times(plug)
        rows.append(dict(entry, index=index, alias=aliases.get(index, ""),
                         weight=_weight_now(plug, times, now, from_curves),
                         keyed=bool(times), keys=len(times), key_state=core.key_state(times, now)))
    return rows


def _weight_now(plug, times, now, from_curves):
    """The weight on ``now``. A keyed weight is read from its curve at that
    time, so a frame-change callback never sees a value Maya has not
    evaluated yet."""
    if times and from_curves:
        return cmds.getAttr(plug, time=now)
    return cmds.getAttr(plug)


def tweak_meshes():
    """Every mesh transform in the scene with a tweak node."""
    out = []
    for node in cmds.ls(type="blendShape") or []:
        if cmds.attributeQuery(MARKER_ATTR, node=node, exists=True):
            try:
                out.append(_mesh_of(node))
            except TweakError:
                pass
    return sorted(set(out))


def level_contribution(node, layer, frame, exclude=()):
    """What a sequence level currently adds on ``frame``: its poses times their weights."""
    weighted = []
    for index, _pose_frame in core.level_entries(read_meta(node), layer):
        if index in exclude:
            continue
        weight = cmds.getAttr(weight_plug(node, index), time=frame)
        weighted.append((read_target(node, index), weight))
    return core.blend_deltas(weighted)


def commit_delta(mesh, delta, mode, frame, layer="", ramp_in=3.0, ramp_out=3.0,
                 kind=core.KIND_SCULPT, label=None, carry_level=True, exclude=()):
    """Store an offset with a keying mode. A sequence pose on an occupied frame is refined.

    ``delta`` is measured against the mesh as it shows on ``frame``. A new
    sequence pose replaces its level on that frame (the neighbours are keyed
    to 0 there), so with ``carry_level`` the level's current in-between shape
    is folded into the new pose and the sculpt looks the same after commit.
    ``exclude`` lists targets that were muted while measuring ``delta``.
    """
    if mode == core.MODE_SEQUENCE and not layer:
        layer = "L1"
    node = ensure_tweak_node(mesh)
    if mode == core.MODE_SEQUENCE:
        existing = core.find_sequence_target(read_meta(node), layer, frame)
        if existing is not None:
            write_target(node, existing, core.add_deltas(read_target(node, existing), delta))
            return existing
        if carry_level:
            delta = core.add_deltas(level_contribution(node, layer, frame, exclude), delta)
    label = label or core.frame_label(kind, frame if mode != core.MODE_STATIC else None,
                                      layer if mode == core.MODE_SEQUENCE else "")
    entry = core.make_entry(label, kind, mode,
                            frame if mode != core.MODE_STATIC else None,
                            layer if mode == core.MODE_SEQUENCE else mode,
                            ramp_in, ramp_out)
    return add_tweak(mesh, delta, entry)


def blank_pose(mesh, layer="L1", frame=None):
    frame = cmds.currentTime(query=True) if frame is None else frame
    node = ensure_tweak_node(mesh)
    with undo_chunk("blank pose"):
        if core.find_sequence_target(read_meta(node), layer, frame) is not None:
            raise TweakError("Level %s already has a pose on frame %g" % (layer, frame))
        return commit_delta(mesh, {}, core.MODE_SEQUENCE, frame, layer, kind=core.KIND_BLANK,
                            carry_level=False)


def hold_pose(mesh, layer="L1", frame=None):
    """Copy the previous pose on the level to this frame."""
    frame = cmds.currentTime(query=True) if frame is None else frame
    node = _require_node(mesh)
    meta = read_meta(node)
    if core.find_sequence_target(meta, layer, frame) is not None:
        raise TweakError("Level %s already has a pose on frame %g" % (layer, frame))
    previous = core.previous_pose(core.level_entries(meta, layer), frame)
    if previous is None:
        raise TweakError("Level %s has no pose before frame %g to hold" % (layer, frame))
    with undo_chunk("hold pose"):
        return commit_delta(mesh, read_target(node, previous), core.MODE_SEQUENCE, frame,
                            layer, kind=core.KIND_HOLD, carry_level=False)


def paint_mask(mesh, index):
    """Open Maya's blendShape weight painting on this tweak's per-vertex weights."""
    node = _require_node(mesh)
    alias = alias_map(node).get(index, "")
    cmds.select(resolve_mesh(mesh)[0], replace=True)
    mel.eval("ArtPaintBlendShapeWeightsTool")
    try:
        cmds.setAttr(node + ".inputTarget[0].paintTargetIndex", index)
    except Exception:
        pass
    if alias:
        try:
            mel.eval('artBlendShapeSelectTarget artAttrCtx "%s"' % alias)
        except Exception:
            cmds.warning("Animation Tweaker: choose '%s' in the paint tool's target list" % alias)


# ---------------------------------------------------------------------------
# Shape operations at the current frame
# ---------------------------------------------------------------------------

def inflate(mesh, amount, mode=core.MODE_STATIC, layer="", ramp_in=3.0, ramp_out=3.0, mask=None,
            use_selection_mask=True):
    xf, shape = resolve_mesh(mesh)
    if use_selection_mask and mask is None:
        mask = mask_for(shape)
    delta = core.inflate_delta(read_points(shape), vertex_normals(shape), amount, mask)
    if not delta:
        raise TweakError("Nothing to inflate: the mask is empty or the amount is 0")
    kind = core.KIND_INFLATE
    with undo_chunk("inflate"):
        return commit_delta(xf, delta, mode, cmds.currentTime(query=True), layer, ramp_in, ramp_out,
                            kind=kind, label=core.frame_label("inflate" if amount >= 0 else "deflate",
                                                              cmds.currentTime(query=True)))


def relax(mesh, iterations=5, strength=0.5, mode=core.MODE_STATIC, layer="", ramp_in=3.0,
          ramp_out=3.0, mask=None, use_selection_mask=True):
    xf, shape = resolve_mesh(mesh)
    if use_selection_mask and mask is None:
        mask = mask_for(shape)
    points = read_points(shape)
    adjacency = core.adjacency_from_faces(len(points), mesh_faces(shape))
    delta = core.relax_delta(points, adjacency, iterations, strength, mask)
    if not delta:
        raise TweakError("Nothing to relax: the mask is empty or the strength is 0")
    with undo_chunk("relax"):
        return commit_delta(xf, delta, mode, cmds.currentTime(query=True), layer, ramp_in, ramp_out,
                            kind=core.KIND_RELAX)


# ---------------------------------------------------------------------------
# Sculpt sessions
# ---------------------------------------------------------------------------
# A session lives entirely in the scene: the sculpt mesh carries a JSON record
# of what it is for, which tweaks were muted and whether the original was
# hidden. A session survives Reload Scripts and can always be cancelled.

def _mute(node, indices):
    record = []
    for index in indices:
        plug = weight_plug(node, index)
        sources = cmds.listConnections(plug, source=True, destination=False, plugs=True) or []
        if sources:
            cmds.disconnectAttr(sources[0], plug)
        record.append([index, sources[0] if sources else None, cmds.getAttr(plug)])
        cmds.setAttr(plug, 0.0)
    return record


def _unmute(node, record):
    for index, source, value in record:
        plug = weight_plug(node, index)
        if not cmds.objExists(plug):
            continue
        if source and cmds.objExists(source):
            cmds.connectAttr(source, plug, force=True)
        else:
            cmds.setAttr(plug, value)


def _sculpt_material():
    if cmds.objExists(SCULPT_SHADER):
        groups = cmds.listConnections(SCULPT_SHADER + ".outColor", type="shadingEngine") or []
        if groups:
            return groups[0]
    shader = cmds.shadingNode("lambert", asShader=True, name=SCULPT_SHADER)
    cmds.setAttr(shader + ".color", 0.38, 0.72, 0.95, type="double3")
    cmds.setAttr(shader + ".ambientColor", 0.08, 0.12, 0.16, type="double3")
    group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=SCULPT_SHADER + "SG")
    cmds.connectAttr(shader + ".outColor", group + ".surfaceShader", force=True)
    return group


def _cleanup_sculpt_material():
    if not cmds.objExists(SCULPT_SHADER):
        return
    groups = cmds.listConnections(SCULPT_SHADER + ".outColor", type="shadingEngine") or []
    if all(not cmds.sets(g, query=True) for g in groups):
        cmds.delete([SCULPT_SHADER] + groups)


def active_sessions():
    """``{sculpt_transform: record}`` for every sculpt mesh in the scene."""
    out = {}
    for xf in cmds.ls("*.%s" % SCULPT_TAG_ATTR, objectsOnly=True, long=True, recursive=True) or []:
        try:
            out[xf] = json.loads(cmds.getAttr(xf + "." + SCULPT_TAG_ATTR))
        except (TypeError, ValueError):
            continue
    return out


def session_for(mesh):
    xf = resolve_mesh(mesh)[0]
    for sculpt, record in active_sessions().items():
        if record.get("mesh") == xf:
            return sculpt, record
    return None, None


def start_sculpt(mesh, mode=core.MODE_STATIC, layer="L1", ramp_in=3.0, ramp_out=3.0,
                 mute=core.MUTE_NONE, highlight=True, hide_original=True, refine=None):
    """Make an editable copy of the evaluated mesh at the current frame.

    ``refine`` is a target index: the sculpt is added to that tweak on commit.
    """
    xf, shape = resolve_mesh(mesh)
    existing, _record = session_for(xf)
    if existing:
        raise TweakError("%s is already being sculpted; commit or cancel first" % short_name(xf))
    frame = cmds.currentTime(query=True)
    with undo_chunk("start sculpt"):
        node = ensure_tweak_node(xf)
        meta = read_meta(node)
        refine_weight = 1.0
        if refine is not None:
            if refine not in meta["targets"]:
                raise TweakError("Tweak %d no longer exists" % refine)
            refine_weight = cmds.getAttr(weight_plug(node, refine))
            core.refine_delta({}, {}, refine_weight)          # raises when weight is 0
        muted = _mute(node, core.targets_to_mute(meta, mute, layer)) if refine is None else []
        sculpt = cmds.createNode("transform", name=short_name(xf).split(":")[-1] + "_atkSculpt")
        sculpt = cmds.ls(sculpt, long=True)[0]
        cmds.xform(sculpt, worldSpace=True, matrix=cmds.xform(xf, query=True, worldSpace=True, matrix=True))
        om.MFnMesh().copy(_mobject(shape), _mobject(sculpt))
        sculpt_shape = cmds.listRelatives(sculpt, shapes=True, fullPath=True)[0]
        cmds.rename(sculpt_shape, short_name(sculpt) + "Shape")
        group = _sculpt_material() if highlight else "initialShadingGroup"
        cmds.sets(sculpt, edit=True, forceElement=group)
        was_visible = cmds.getAttr(xf + ".visibility")
        if hide_original and not cmds.listConnections(xf + ".visibility", source=True, destination=False):
            cmds.setAttr(xf + ".visibility", False)
        record = {"mesh": xf, "frame": frame, "mode": mode, "layer": layer, "ramp_in": ramp_in,
                  "ramp_out": ramp_out, "muted": muted, "refine": refine,
                  "refine_weight": refine_weight, "was_visible": bool(was_visible)}
        cmds.addAttr(sculpt, longName=SCULPT_TAG_ATTR, dataType="string")
        cmds.setAttr(sculpt + "." + SCULPT_TAG_ATTR, json.dumps(record), type="string")
        cmds.select(sculpt, replace=True)
    return sculpt


def _end_session(sculpt, record):
    xf = record["mesh"]
    node = find_tweak_node(xf) if cmds.objExists(xf) else None
    if node:
        _unmute(node, record.get("muted", []))
    if cmds.objExists(xf) and record.get("was_visible", True) and not cmds.listConnections(
            xf + ".visibility", source=True, destination=False):
        cmds.setAttr(xf + ".visibility", True)
    if cmds.objExists(sculpt):
        cmds.delete(sculpt)
    _cleanup_sculpt_material()


def commit_sculpt(mesh_or_sculpt=None):
    """Store the sculpt as a tweak (or add it to the tweak being refined)."""
    sculpt, record = _find_session(mesh_or_sculpt)
    xf = record["mesh"]
    _xf, shape = resolve_mesh(xf)
    with undo_chunk("commit sculpt"):
        base = sample_points(shape, record["frame"])          # muted tweaks still muted here
        sculpt_shape = resolve_mesh(sculpt)[1]
        delta = core.compute_delta(base, read_points(sculpt_shape))
        _end_session(sculpt, record)
        if not delta:
            cmds.warning("Animation Tweaker: the sculpt matches the mesh; nothing was stored")
            return None
        node = find_tweak_node(xf)
        if record.get("refine") is not None:
            index = record["refine"]
            write_target(node, index, core.refine_delta(read_target(node, index), delta,
                                                         record.get("refine_weight", 1.0)))
            return index
        muted = [index for index, _source, _value in record.get("muted", [])]
        return commit_delta(xf, delta, record["mode"], record["frame"], record["layer"],
                            record["ramp_in"], record["ramp_out"], exclude=muted)


def cancel_sculpt(mesh_or_sculpt=None):
    sculpt, record = _find_session(mesh_or_sculpt)
    with undo_chunk("cancel sculpt"):
        _end_session(sculpt, record)


def _find_session(mesh_or_sculpt):
    sessions = active_sessions()
    if not sessions:
        raise TweakError("No sculpt in progress")
    if mesh_or_sculpt is None:
        selection = cmds.ls(selection=True, long=True, objectsOnly=True) or []
        for item in selection:
            for sculpt, record in sessions.items():
                if item in (sculpt, record["mesh"]) or item.startswith(sculpt + "|"):
                    return sculpt, record
        if len(sessions) == 1:
            return next(iter(sessions.items()))
        raise TweakError("Several sculpts are open; select the one to commit or cancel")
    target = cmds.ls(mesh_or_sculpt, long=True) or [mesh_or_sculpt]
    for sculpt, record in sessions.items():
        if target[0] in (sculpt, record["mesh"]):
            return sculpt, record
    raise TweakError("No sculpt in progress for %s" % short_name(mesh_or_sculpt))
