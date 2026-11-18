"""Small production helpers that sit next to the tweak tools.

Every function here works on the current selection, makes one Undo, and
stores nothing outside the scene except the channel clipboard, which is JSON
text in a Maya optionVar (data only: never a script file, never executed).
"""
import random

from maya import cmds

from . import core
from .engine import TweakError, resolve_mesh, short_name, undo_chunk

try:
    import maya.api.OpenMaya as om
except ImportError:
    om = None

CLIPBOARD_VAR = "atkTweakerChannelClipboard"
COLOUR_PREFIX = "atkColour_"


def _playback_range():
    return (int(cmds.playbackOptions(query=True, minTime=True)),
            int(cmds.playbackOptions(query=True, maxTime=True)))


# ---------------------------------------------------------------------------
# Bake a locator or card stuck to a vertex
# ---------------------------------------------------------------------------

def _basis_matrix(origin, normal, tangent, scale=1.0):
    z = core.v_normalize(normal)
    x = core.v_normalize(core.v_sub(tangent, core.v_scale(z, core.v_dot(tangent, z))), (1.0, 0.0, 0.0))
    y = core.v_cross(z, x)
    # A card (polyPlane) faces +Y, so map the normal onto Y.
    return [x[0] * scale, x[1] * scale, x[2] * scale, 0.0,
            z[0] * scale, z[1] * scale, z[2] * scale, 0.0,
            -y[0] * scale, -y[1] * scale, -y[2] * scale, 0.0,
            origin[0], origin[1], origin[2], 1.0]


def bake_followers(kind="locator", size=1.0, start=None, end=None):
    """Bake a locator (position) or card (position + orientation) on each selected vertex."""
    vertices = [v for v in cmds.ls(selection=True, flatten=True, long=True) or [] if ".vtx[" in v]
    if not vertices:
        raise TweakError("Select one or more vertices")
    first, last = _playback_range()
    start = first if start is None else int(start)
    end = last if end is None else int(end)
    created = []
    now = cmds.currentTime(query=True)
    with undo_chunk("bake followers"):
        targets = []
        for vertex in vertices:
            xf, shape = resolve_mesh(vertex)
            index = core.expand_components([vertex.split(".")[-1]])[0]
            label = "%s_vtx%d" % (short_name(xf).split(":")[-1], index)
            if kind == "card":
                node = cmds.polyPlane(name=label + "_card", width=size, height=size,
                                      subdivisionsX=1, subdivisionsY=1, constructionHistory=False)[0]
            else:
                node = cmds.spaceLocator(name=label + "_loc")[0]
                cmds.setAttr(node + ".localScale", size, size, size)
            neighbours = cmds.ls(cmds.polyListComponentConversion(
                cmds.polyListComponentConversion(vertex, toEdge=True), toVertex=True), flatten=True) or []
            neighbour = next((core.expand_components([n.split(".")[-1]])[0] for n in neighbours
                              if n.split(".")[-1] != vertex.split(".")[-1]), index)
            targets.append((node, shape, index, neighbour))
            created.append(node)
        cmds.refresh(suspend=True)
        try:
            for frame in range(start, end + 1):
                cmds.currentTime(frame, update=True)
                for node, shape, index, neighbour in targets:
                    fn = om.MFnMesh(_dag(shape))
                    p = fn.getPoint(index, om.MSpace.kWorld)
                    origin = (p.x, p.y, p.z)
                    if kind == "card":
                        n = fn.getVertexNormal(index, True, om.MSpace.kWorld)
                        q = fn.getPoint(neighbour, om.MSpace.kWorld)
                        tangent = core.v_sub((q.x, q.y, q.z), origin)
                        cmds.xform(node, worldSpace=True,
                                   matrix=_basis_matrix(origin, (n.x, n.y, n.z), tangent))
                        cmds.setKeyframe(node, attribute=["translate", "rotate"], time=frame)
                    else:
                        cmds.xform(node, worldSpace=True, translation=origin)
                        cmds.setKeyframe(node, attribute="translate", time=frame)
        finally:
            cmds.refresh(suspend=False)
            cmds.currentTime(now, update=True)
        if kind == "card":
            curves = cmds.listConnections(created, type="animCurveTA") or []
            if curves:
                cmds.filterCurve(curves, filter="euler")
        cmds.select(created, replace=True)
    return created


def _dag(node):
    sel = om.MSelectionList()
    sel.add(node)
    return sel.getDagPath(0)


# ---------------------------------------------------------------------------
# Bake transforms
# ---------------------------------------------------------------------------

def bake_transforms(nodes=None, start=None, end=None, remove_constraints=True):
    """Bake translate/rotate/scale of the selected objects to keys on every frame."""
    nodes = nodes or cmds.ls(selection=True, long=True, transforms=True) or []
    if not nodes:
        raise TweakError("Select the meshes (or groups) whose transforms to bake")
    first, last = _playback_range()
    start = first if start is None else start
    end = last if end is None else end
    with undo_chunk("bake transforms"):
        cmds.bakeResults(nodes, time=(start, end), simulation=True, preserveOutsideKeys=True,
                         attribute=["tx", "ty", "tz", "rx", "ry", "rz", "sx", "sy", "sz"])
        if remove_constraints:
            for node in nodes:
                doomed = cmds.listRelatives(node, type="constraint", fullPath=True) or []
                if doomed:
                    cmds.delete(doomed)
    return nodes


# ---------------------------------------------------------------------------
# Smooth preview
# ---------------------------------------------------------------------------

def _hierarchy_meshes(nodes):
    meshes = []
    for node in nodes:
        meshes += cmds.listRelatives(node, allDescendents=True, type="mesh", noIntermediate=True,
                                     fullPath=True) or []
        if cmds.nodeType(node) == "mesh":
            meshes.append(node)
    return sorted(set(meshes))


def toggle_smooth_preview(nodes=None):
    """Toggle smooth-mesh preview (the 1/3 keys) on every mesh under the selection."""
    nodes = nodes or cmds.ls(selection=True, long=True, objectsOnly=True) or []
    meshes = _hierarchy_meshes(nodes)
    if not meshes:
        raise TweakError("Select meshes or a group that contains them")
    state = (cmds.displaySmoothness(meshes[0], query=True, polygonObject=True) or [1])[0]
    level = 1 if state == 3 else 3
    cmds.displaySmoothness(meshes, polygonObject=level)
    return level == 3


# ---------------------------------------------------------------------------
# Camera cycling
# ---------------------------------------------------------------------------

def _active_panel():
    panel = cmds.getPanel(withFocus=True)
    if panel and cmds.getPanel(typeOf=panel) == "modelPanel":
        return panel
    try:
        panel = cmds.playblast(activeEditor=True)
        return panel.split("|")[-1]
    except Exception:
        visible = [p for p in cmds.getPanel(visiblePanels=True) or []
                   if cmds.getPanel(typeOf=p) == "modelPanel"]
        if not visible:
            raise TweakError("No viewport is open")
        return visible[0]


def scene_cameras():
    out = []
    for shape in cmds.ls(type="camera", long=True) or []:
        xf = cmds.listRelatives(shape, parent=True, fullPath=True)[0]
        out.append((xf, bool(cmds.getAttr(shape + ".orthographic"))))
    return sorted(out)


def cycle_camera(skip_ortho=True):
    """Look through the next scene camera in the active viewport."""
    panel = _active_panel()
    current = cmds.modelPanel(panel, query=True, camera=True)
    found = cmds.ls(current, long=True) or [current]
    current = found[0]
    if cmds.nodeType(current) == "camera":
        current = cmds.listRelatives(current, parent=True, fullPath=True)[0]
    nxt = core.next_camera(scene_cameras(), current, skip_ortho)
    if nxt is None:
        raise TweakError("No perspective cameras in the scene")
    cmds.lookThru(panel, nxt)
    return nxt


# ---------------------------------------------------------------------------
# Quick colour materials
# ---------------------------------------------------------------------------

def _colour_group(hex_colour):
    name = COLOUR_PREFIX + hex_colour.lstrip("#").lower()
    if cmds.objExists(name):
        groups = cmds.listConnections(name + ".outColor", type="shadingEngine") or []
        if groups:
            return groups[0]
    shader = cmds.shadingNode("lambert", asShader=True, name=name)
    cmds.setAttr(shader + ".color", *core.hex_to_rgb(hex_colour), type="double3")
    group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=name + "SG")
    cmds.connectAttr(shader + ".outColor", group + ".surfaceShader", force=True)
    return group


def apply_colour(hex_colour=None, nodes=None, rng=None):
    """Assign a flat colour material to the selected meshes or faces. ``None`` = random."""
    nodes = nodes or cmds.ls(selection=True, long=True) or []
    if not nodes:
        raise TweakError("Select meshes or faces to colour")
    colour = hex_colour or core.random_colour(rng or random.Random())
    with undo_chunk("colour material"):
        cmds.sets(nodes, edit=True, forceElement=_colour_group(colour))
    return colour


# ---------------------------------------------------------------------------
# Channel copy / paste (JSON in an optionVar)
# ---------------------------------------------------------------------------

def _channel_box_selection():
    try:
        return cmds.channelBox("mainChannelBox", query=True, selectedMainAttributes=True) or []
    except Exception:
        return []


def copy_channels(nodes=None):
    nodes = nodes or cmds.ls(selection=True, long=True) or []
    if not nodes:
        raise TweakError("Select the objects to copy channel values from")
    chosen = _channel_box_selection()
    values = {}
    for node in nodes:
        attrs = chosen or cmds.listAttr(node, keyable=True, unlocked=True, scalar=True) or []
        out = {}
        for attr in attrs:
            plug = "%s.%s" % (node, attr)
            if not cmds.objExists(plug):
                continue
            value = cmds.getAttr(plug)
            if isinstance(value, (int, float, bool)):
                out[attr] = value
        values[short_name(node)] = out
    cmds.optionVar(stringValue=(CLIPBOARD_VAR, core.encode_clipboard(values)))
    return sum(len(v) for v in values.values())


def paste_channels(nodes=None):
    nodes = nodes or cmds.ls(selection=True, long=True) or []
    clipboard = core.decode_clipboard(cmds.optionVar(query=CLIPBOARD_VAR)
                                      if cmds.optionVar(exists=CLIPBOARD_VAR) else "")
    if not clipboard:
        raise TweakError("Nothing copied yet")
    plan = core.paste_plan(clipboard, nodes)
    if not plan:
        raise TweakError("Select the objects to paste onto")
    auto_key = cmds.autoKeyframe(query=True, state=True)
    done = 0
    with undo_chunk("paste channels"):
        for node, attr, value in plan:
            plug = "%s.%s" % (node, attr)
            if not cmds.objExists(plug) or not cmds.getAttr(plug, settable=True):
                continue
            cmds.setAttr(plug, value)
            if auto_key:
                cmds.setKeyframe(plug)
            done += 1
    return done


# ---------------------------------------------------------------------------
# Extract faces as a live copy
# ---------------------------------------------------------------------------

def extract_faces(faces=None):
    """Make a separate mesh of the selected faces that keeps following the original.

    The copy is fed by a ``deleteComponent`` node that removes the other
    faces from the original's evaluated mesh, so skinning, tweaks and other
    deformers carry through live.
    """
    faces = faces or [f for f in cmds.ls(selection=True, flatten=True, long=True) or [] if ".f[" in f]
    if not faces:
        raise TweakError("Select the faces to extract")
    xf, shape = resolve_mesh(faces[0])
    keep = set(core.expand_components(["vtx[" + f.split(".f[")[-1] for f in faces
                                       if resolve_mesh(f)[0] == xf]))
    total = cmds.polyEvaluate(shape, face=True)
    drop = [i for i in range(total) if i not in keep]
    with undo_chunk("extract faces"):
        name = short_name(xf).split(":")[-1] + "_extract"
        copy = cmds.createNode("transform", name=name)
        copy_shape = cmds.createNode("mesh", name=name + "Shape", parent=copy)
        cutter = cmds.createNode("deleteComponent", name=name + "_cut")
        components = core.compress_indices(drop, prefix="f")
        cmds.setAttr(cutter + ".deleteComponents", len(components), *components, type="componentList")
        cmds.connectAttr(shape + ".outMesh", cutter + ".inputGeometry")
        cmds.connectAttr(cutter + ".outputGeometry", copy_shape + ".inMesh")
        cmds.connectAttr(xf + ".worldMatrix[0]", copy + ".offsetParentMatrix")
        cmds.sets(copy, edit=True, forceElement="initialShadingGroup")
        cmds.select(copy, replace=True)
    return cmds.ls(copy, long=True)[0]
