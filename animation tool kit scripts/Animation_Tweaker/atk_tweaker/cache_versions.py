"""Cache versions: export polished meshes to Alembic, re-import and swap versions.

Workflow
--------
1. **Export** the selected meshes. Each mesh gets an ``atkCacheSource``
   string attribute holding its full DAG path, which Alembic carries along
   (``-attr atkCacheSource``).
2. **Import** one or more caches. Each becomes a version group under the
   control node ``ATK_TweakCache_CTL``.
3. **Attach** the active version onto the original meshes: one blendShape per
   original, placed after its other deformers, weight 1. The control's
   ``envelope`` drives every attach blendShape, so you can fade the cache in
   and out or key it.
4. **Swap** to another version: the attach blendShapes are re-pointed at the
   new version's meshes and only that version is shown.
5. **Delete** a version, or detach everything.

State is JSON in a string attribute on the control. Nothing is evaluated as
code: version records are read with ``json`` only.
"""
import json

from maya import cmds

from . import core
from .engine import TweakError, resolve_mesh, short_name, undo_chunk

SOURCE_ATTR = "atkCacheSource"
CONTROL = "ATK_TweakCache_CTL"
STATE_ATTR = "atkCacheState"


def _load_plugins():
    for plugin in ("AbcExport", "AbcImport"):
        if not cmds.pluginInfo(plugin, query=True, loaded=True):
            cmds.loadPlugin(plugin, quiet=True)


def tag_sources(nodes):
    for node in nodes:
        xf = resolve_mesh(node)[0]
        if not cmds.attributeQuery(SOURCE_ATTR, node=xf, exists=True):
            cmds.addAttr(xf, longName=SOURCE_ATTR, dataType="string")
        cmds.setAttr(xf + "." + SOURCE_ATTR, xf, type="string")


def export_selected(path, start=None, end=None, nodes=None):
    nodes = nodes or [n for n in cmds.ls(selection=True, long=True, transforms=True) or [] if _is_mesh(n)]
    if not nodes:
        raise TweakError("Select the meshes to export")
    start = cmds.playbackOptions(query=True, minTime=True) if start is None else start
    end = cmds.playbackOptions(query=True, maxTime=True) if end is None else end
    _load_plugins()
    with undo_chunk("tag cache sources"):
        tag_sources(nodes)
    job = core.abc_job(nodes, path, start, end, attrs=(SOURCE_ATTR,))
    cmds.AbcExport(jobArg=job)
    return path


def _is_mesh(node):
    try:
        resolve_mesh(node)
        return True
    except TweakError:
        return False


# ---------------------------------------------------------------------------
# The control node
# ---------------------------------------------------------------------------

def _state():
    if not cmds.objExists(CONTROL):
        return {"versions": [], "active": None, "attached": []}
    try:
        data = json.loads(cmds.getAttr(CONTROL + "." + STATE_ATTR) or "{}")
    except ValueError:
        data = {}
    data.setdefault("versions", [])
    data.setdefault("active", None)
    data.setdefault("attached", [])
    return data


def _save(state):
    cmds.setAttr(CONTROL + "." + STATE_ATTR, json.dumps(state, sort_keys=True), type="string")
    labels = [v["label"] for v in state["versions"]] or ["none"]
    cmds.addAttr(CONTROL + ".version", edit=True, enumName=":".join(labels))
    if state["active"] in labels:
        cmds.setAttr(CONTROL + ".version", labels.index(state["active"]))


def _ensure_control():
    if cmds.objExists(CONTROL):
        return CONTROL
    cmds.createNode("transform", name=CONTROL)
    cmds.addAttr(CONTROL, longName=STATE_ATTR, dataType="string")
    cmds.addAttr(CONTROL, longName="version", attributeType="enum", enumName="none")
    cmds.setAttr(CONTROL + ".version", edit=True, channelBox=True)
    cmds.addAttr(CONTROL, longName="envelope", attributeType="double", minValue=0.0, maxValue=1.0,
                 defaultValue=1.0, keyable=True)
    for attr in ("tx", "ty", "tz", "rx", "ry", "rz", "sx", "sy", "sz"):
        cmds.setAttr(CONTROL + "." + attr, lock=True, keyable=False, channelBox=False)
    _save({"versions": [], "active": None, "attached": []})
    return CONTROL


def list_versions():
    state = _state()
    return [dict(v, active=(v["label"] == state["active"])) for v in state["versions"]]


def import_version(path):
    """Import an Alembic cache as a new version group under the control."""
    _load_plugins()
    with undo_chunk("import cache version"):
        control = _ensure_control()
        state = _state()
        label = core.version_label(path, [v["label"] for v in state["versions"]])
        before = set(cmds.ls(assemblies=True, long=True) or [])
        cmds.AbcImport(path, mode="import")
        new = [n for n in cmds.ls(assemblies=True, long=True) or [] if n not in before]
        group = cmds.createNode("transform", name=label + "_GRP", parent=control)
        if new:
            cmds.parent(new, group)
        state["versions"].append({"label": label, "path": str(path).replace("\\", "/"),
                                  "group": cmds.ls(group, long=True)[0]})
        if state["active"] is None:
            state["active"] = label
        _save(state)
        _show_only(state)
    return label


def _version(state, label):
    for version in state["versions"]:
        if version["label"] == label:
            return version
    raise TweakError("No cache version called '%s'" % label)


def _show_only(state):
    for version in state["versions"]:
        if cmds.objExists(version["group"]):
            cmds.setAttr(version["group"] + ".visibility", version["label"] == state["active"])


def _cache_meshes(version):
    """``{original_path: cache_mesh}`` for one version, from the atkCacheSource tags."""
    out = {}
    if not cmds.objExists(version["group"]):
        return out
    for xf in cmds.listRelatives(version["group"], allDescendents=True, type="transform",
                                 fullPath=True) or []:
        if cmds.attributeQuery(SOURCE_ATTR, node=xf, exists=True) and _is_mesh(xf):
            source = cmds.getAttr(xf + "." + SOURCE_ATTR)
            if source:
                out[source] = xf
    if not out:
        # Caches exported elsewhere: fall back to matching short names.
        for xf in cmds.listRelatives(version["group"], allDescendents=True, type="transform",
                                     fullPath=True) or []:
            if not _is_mesh(xf):
                continue
            matches = [m for m in cmds.ls(short_name(xf), long=True) or []
                       if not m.startswith("|" + CONTROL)]
            if matches:
                out[matches[0]] = xf
    return out


def attach(label=None):
    """Drive the original meshes from the active (or given) version."""
    state = _state()
    if not state["versions"]:
        raise TweakError("Import a cache version first")
    label = label or state["active"]
    version = _version(state, label)
    pairs = _cache_meshes(version)
    if not pairs:
        raise TweakError("No meshes in '%s' match the scene's originals" % label)
    with undo_chunk("attach cache"):
        detach(undo=False)
        state = _state()
        attached = []
        for original, cache in sorted(pairs.items()):
            if not cmds.objExists(original):
                cmds.warning("Animation Tweaker: original %s is missing; skipped" % original)
                continue
            # Append after the skinCluster on the existing shape (blendShape's
            # own after=True would create a second "...ShapeDeformed" shape),
            # then add the cache as a world-space target.
            _xf, shape = resolve_mesh(original)
            node = cmds.deformer(shape, type="blendShape",
                                 name=short_name(original).split(":")[-1] + "_atkCache")[0]
            cmds.setAttr(node + ".origin", 0)      # 0 = world
            cmds.blendShape(node, edit=True, target=(shape, 0, cache, 1.0))
            cmds.setAttr(node + ".weight[0]", 1.0)
            cmds.connectAttr(CONTROL + ".envelope", node + ".envelope", force=True)
            attached.append({"original": original, "blendShape": node})
        state["attached"] = attached
        state["active"] = label
        _save(state)
        _show_only(state)
    return len(attached)


def swap(label):
    """Make ``label`` the active version and re-point the attach blendShapes at it."""
    state = _state()
    version = _version(state, label)
    with undo_chunk("swap cache version"):
        pairs = _cache_meshes(version)
        for record in state["attached"]:
            node = record["blendShape"]
            cache = pairs.get(record["original"])
            if not cache or not cmds.objExists(node):
                cmds.warning("Animation Tweaker: %s has no mesh for %s" % (label, record["original"]))
                continue
            _xf, cache_shape = resolve_mesh(cache)
            cmds.connectAttr(cache_shape + ".worldMesh[0]",
                             node + ".inputTarget[0].inputTargetGroup[0].inputTargetItem[6000].inputGeomTarget",
                             force=True)
        state["active"] = label
        _save(state)
        _show_only(state)


def detach(undo=True):
    state = _state()
    doomed = [r["blendShape"] for r in state["attached"] if cmds.objExists(r["blendShape"])]
    if doomed:
        cmds.delete(doomed)
    if cmds.objExists(CONTROL):
        state["attached"] = []
        _save(state)
    return len(doomed)


def delete_version(label):
    state = _state()
    version = _version(state, label)
    with undo_chunk("delete cache version"):
        if state["active"] == label and state["attached"]:
            detach(undo=False)
            state = _state()
        if cmds.objExists(version["group"]):
            cmds.delete(version["group"])
        state["versions"] = [v for v in state["versions"] if v["label"] != label]
        if state["active"] == label:
            state["active"] = state["versions"][0]["label"] if state["versions"] else None
        _save(state)
        _show_only(state)


def delete_all():
    with undo_chunk("delete cache control"):
        detach(undo=False)
        if cmds.objExists(CONTROL):
            cmds.delete(CONTROL)
