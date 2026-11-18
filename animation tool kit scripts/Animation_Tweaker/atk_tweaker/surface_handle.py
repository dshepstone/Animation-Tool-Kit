"""Surface Handle: a softMod whose handle rides the deforming surface.

Node graph
----------
::

    upstream geometry --> uvPin --> multMatrix(x mesh worldMatrix) --+--> choice[0]
                                       \\--> decompose -> compose ----+--> choice[1]
    choice.output (selector = handle.orientToWorld) --> <name>_pin.offsetParentMatrix
    <name>_pin
      <name>_aim            (optional aim constraint; carries the falloff sphere)
        <name>_handle       (the softMod handle the artist moves)

The uvPin reads the geometry *entering* the softMod, so the handle follows
the skin and earlier tweaks without a cycle through its own deformation. The
softMod's bind matrix is the aim group's inverse world matrix: with the handle
at rest the softMod does nothing, wherever the pin is carried.

A mesh without UVs cannot be pinned; the handle is then placed at the vertex
and stays there, with a warning.
"""
import json

from maya import cmds

from . import core
from .engine import TweakError, resolve_mesh, short_name, undo_chunk

HANDLE_TAG = "atkTweakHandle"


def _selected_vertex():
    for item in cmds.ls(selection=True, flatten=True, long=True) or []:
        if ".vtx[" in item:
            return item
    raise TweakError("Select one vertex where the handle should sit")


def _vertex_uv(vertex):
    uvs = cmds.ls(cmds.polyListComponentConversion(vertex, toUV=True), flatten=True) or []
    if not uvs:
        return None
    u, v = cmds.polyEditUV(uvs[0], query=True)[:2]
    return u, v


def _handles():
    return cmds.ls("*.%s" % HANDLE_TAG, objectsOnly=True, long=True, recursive=True) or []


def handle_record(handle):
    if not cmds.attributeQuery(HANDLE_TAG, node=handle, exists=True):
        raise TweakError("%s is not a Surface Handle" % short_name(handle))
    return json.loads(cmds.getAttr(handle + "." + HANDLE_TAG))


def selected_handle():
    for item in cmds.ls(selection=True, long=True, objectsOnly=True) or []:
        node = item
        while node:
            if cmds.attributeQuery(HANDLE_TAG, node=node, exists=True):
                return node
            parents = cmds.listRelatives(node, parent=True, fullPath=True)
            node = parents[0] if parents else None
        for child in cmds.listRelatives(item, allDescendents=True, fullPath=True, type="transform") or []:
            if cmds.attributeQuery(HANDLE_TAG, node=child, exists=True):
                return child
    raise TweakError("Select a Surface Handle")


def _add(node, name, **kwargs):
    if not cmds.attributeQuery(name, node=node, exists=True):
        cmds.addAttr(node, longName=name, **kwargs)
    return "%s.%s" % (node, name)


def _connect_if(source, node, attr):
    if cmds.attributeQuery(attr, node=node, exists=True):
        cmds.connectAttr(source, "%s.%s" % (node, attr), force=True)
        return True
    return False


def create_handle(vertex=None, radius=None, name=None):
    """Create a surface handle on ``vertex`` (default: the selected vertex)."""
    vertex = vertex or _selected_vertex()
    xf, shape = resolve_mesh(vertex)
    position = cmds.pointPosition(vertex, world=True)
    if radius is None:
        bbox = cmds.exactWorldBoundingBox(xf)
        radius = max(0.01, 0.15 * max(bbox[3] - bbox[0], bbox[4] - bbox[1], bbox[5] - bbox[2]))
    base = name or (short_name(xf).split(":")[-1] + "_surfHandle")
    uv = _vertex_uv(vertex) if cmds.polyEvaluate(shape, uvcoord=True) else None
    with undo_chunk("create surface handle"):
        try:
            soft, handle = cmds.softMod(xf, name=base + "_softMod", falloffRadius=radius,
                                        falloffCenter=position, falloffAroundSelection=False,
                                        after=True)[:2]
        except TypeError:
            soft, handle = cmds.softMod(xf, name=base + "_softMod", falloffRadius=radius,
                                        falloffCenter=position, falloffAroundSelection=False)[:2]
        handle = cmds.rename(handle, base + "_handle")
        pin = cmds.createNode("transform", name=base + "_pin")
        aim = cmds.createNode("transform", name=base + "_aim", parent=pin)
        handle = cmds.parent(handle, aim)[0]
        handle = cmds.ls(handle, long=True)[0]
        aim = cmds.ls(aim, long=True)[0]
        for attr, value in (("translate", (0, 0, 0)), ("rotate", (0, 0, 0)), ("scale", (1, 1, 1)),
                            ("rotatePivot", (0, 0, 0)), ("scalePivot", (0, 0, 0))):
            cmds.setAttr(handle + "." + attr, *value)
        for handle_shape in cmds.listRelatives(handle, shapes=True, fullPath=True) or []:
            if cmds.attributeQuery("origin", node=handle_shape, exists=True):
                cmds.setAttr(handle_shape + ".origin", 0, 0, 0)

        record = {"mesh": xf, "softMod": soft, "pin": cmds.ls(pin, long=True)[0], "aim": aim,
                  "uvPin": None, "nodes": []}
        if uv is None:
            cmds.warning("Animation Tweaker: %s has no UVs, so the handle cannot ride the "
                         "surface. It was placed at the vertex and will not follow the skin. "
                         "Lay out UVs and recreate it to pin it." % short_name(xf))
            cmds.xform(pin, worldSpace=True, translation=position)
        else:
            record.update(_pin_to_surface(soft, xf, uv, pin, base))

        # softMod reads its rest frame from the aim group.
        if not _connect_if(aim + ".worldInverseMatrix[0]", soft, "bindPreMatrix"):
            _connect_if(aim + ".worldInverseMatrix[0]", soft, "preMatrix")
            _connect_if(aim + ".worldMatrix[0]", soft, "postMatrix")
        centre = cmds.createNode("decomposeMatrix", name=base + "_centre")
        cmds.connectAttr(aim + ".worldMatrix[0]", centre + ".inputMatrix")
        cmds.connectAttr(centre + ".outputTranslate", soft + ".falloffCenter", force=True)
        if cmds.attributeQuery("falloffAroundSelection", node=soft, exists=True):
            cmds.setAttr(soft + ".falloffAroundSelection", False)
        record["nodes"].append(centre)

        sphere = _build_sphere(aim, base)
        record["sphere"] = sphere
        _build_handle_attrs(handle, soft, sphere, record, radius)
        _add(handle, HANDLE_TAG, dataType="string")
        cmds.setAttr(handle + "." + HANDLE_TAG, json.dumps(record), type="string")
        apply_falloff_curve(handle, "Smooth")
        cmds.select(handle, replace=True)
    return handle


def _pin_to_surface(soft, xf, uv, pin, base):
    sources = cmds.listConnections(soft + ".input[0].inputGeometry", source=True,
                                   destination=False, plugs=True) or []
    _xf, shape = resolve_mesh(xf)
    source = sources[0] if sources else shape + ".outMesh"
    uv_pin = cmds.createNode("uvPin", name=base + "_uvPin")
    cmds.connectAttr(source, uv_pin + ".deformedGeometry", force=True)
    cmds.setAttr(uv_pin + ".coordinate[0].coordinateU", uv[0])
    cmds.setAttr(uv_pin + ".coordinate[0].coordinateV", uv[1])
    world = cmds.createNode("multMatrix", name=base + "_toWorld")
    cmds.connectAttr(uv_pin + ".outputMatrix[0]", world + ".matrixIn[0]")
    cmds.connectAttr(xf + ".worldMatrix[0]", world + ".matrixIn[1]")
    split = cmds.createNode("decomposeMatrix", name=base + "_split")
    cmds.connectAttr(world + ".matrixSum", split + ".inputMatrix")
    flat = cmds.createNode("composeMatrix", name=base + "_worldAligned")
    cmds.connectAttr(split + ".outputTranslate", flat + ".inputTranslate")
    chooser = cmds.createNode("choice", name=base + "_orient")
    cmds.connectAttr(world + ".matrixSum", chooser + ".input[0]")
    cmds.connectAttr(flat + ".outputMatrix", chooser + ".input[1]")
    cmds.connectAttr(chooser + ".output", pin + ".offsetParentMatrix", force=True)
    return {"uvPin": uv_pin, "choice": chooser, "nodes": [uv_pin, world, split, flat, chooser]}


def _build_sphere(aim, base):
    sphere_xf = cmds.createNode("transform", name=base + "_falloff", parent=aim)
    sphere = cmds.createNode("implicitSphere", name=base + "_falloffShape", parent=sphere_xf)
    sphere = cmds.ls(sphere, long=True)[0]
    cmds.setAttr(sphere + ".overrideEnabled", True)
    for node in (sphere_xf,):
        for attr in ("translate", "rotate", "scale"):
            cmds.setAttr("%s.%s" % (node, attr), lock=True)
    _set_rgb(sphere, (0.95, 0.75, 0.25))
    return sphere


def _set_rgb(shape, rgb):
    cmds.setAttr(shape + ".overrideEnabled", True)
    if cmds.attributeQuery("overrideRGBColors", node=shape, exists=True):
        cmds.setAttr(shape + ".overrideRGBColors", True)
        cmds.setAttr(shape + ".overrideColorRGB", *rgb)


def _build_handle_attrs(handle, soft, sphere, record, radius):
    _add(handle, "falloffRadius", attributeType="double", minValue=0.0, defaultValue=radius, keyable=True)
    cmds.setAttr(handle + ".falloffRadius", radius)
    cmds.connectAttr(handle + ".falloffRadius", soft + ".falloffRadius", force=True)
    cmds.connectAttr(handle + ".falloffRadius", sphere + ".radius", force=True)
    _add(handle, "falloffMode", attributeType="enum", enumName="Volume:Surface", keyable=True)
    cmds.connectAttr(handle + ".falloffMode", soft + ".falloffMode", force=True)
    _add(handle, "falloffShape", attributeType="enum", enumName=":".join(core.FALLOFF_NAMES))
    cmds.setAttr(handle + ".falloffShape", edit=True, channelBox=True)
    _add(handle, "envelope", attributeType="double", minValue=0.0, maxValue=1.0,
         defaultValue=1.0, keyable=True)
    cmds.connectAttr(handle + ".envelope", soft + ".envelope", force=True)
    _add(handle, "showFalloff", attributeType="bool", defaultValue=True)
    cmds.setAttr(handle + ".showFalloff", edit=True, channelBox=True)
    cmds.connectAttr(handle + ".showFalloff", sphere + ".visibility", force=True)
    _add(handle, "orientToWorld", attributeType="bool", defaultValue=False)
    cmds.setAttr(handle + ".orientToWorld", edit=True, channelBox=True)
    if record.get("choice"):
        cmds.connectAttr(handle + ".orientToWorld", record["choice"] + ".selector", force=True)


def apply_falloff_curve(handle, preset):
    """Replace the softMod's falloff ramp with a named shape."""
    if preset not in core.FALLOFF_PRESETS:
        raise TweakError("Unknown falloff shape '%s'" % preset)
    record = handle_record(handle)
    soft = record["softMod"]
    with undo_chunk("falloff shape"):
        for index in cmds.getAttr(soft + ".falloffCurve", multiIndices=True) or []:
            cmds.removeMultiInstance("%s.falloffCurve[%d]" % (soft, index), b=True)
        for i, (position, value, interp) in enumerate(core.FALLOFF_PRESETS[preset]):
            plug = "%s.falloffCurve[%d]" % (soft, i)
            cmds.setAttr(plug + ".falloffCurve_Position", position)
            cmds.setAttr(plug + ".falloffCurve_FloatValue", value)
            cmds.setAttr(plug + ".falloffCurve_Interp", interp)
        cmds.setAttr(handle + ".falloffShape", core.FALLOFF_NAMES.index(preset))


def set_radius(handle, radius):
    cmds.setAttr(handle + ".falloffRadius", max(0.0, radius))


def set_mode(handle, surface):
    cmds.setAttr(handle + ".falloffMode", 1 if surface else 0)


def show_falloff(handle, visible):
    cmds.setAttr(handle + ".showFalloff", bool(visible))


def set_falloff_colour(handle, hex_colour):
    _set_rgb(handle_record(handle)["sphere"], core.hex_to_rgb(hex_colour))


def orient_to_world(handle, enabled=True):
    record = handle_record(handle)
    if not record.get("choice"):
        raise TweakError("This handle is not pinned to the surface, so it is already world-aligned")
    cmds.setAttr(handle + ".orientToWorld", bool(enabled))


def aim_at(handle, target=None):
    """Aim the handle's frame at ``target`` (default: the second selected object)."""
    record = handle_record(handle)
    if target is None:
        others = [n for n in cmds.ls(selection=True, long=True, objectsOnly=True) or []
                  if n != handle and not n.startswith(record["pin"])]
        if not others:
            raise TweakError("Select the handle, then the object to aim at")
        target = others[0]
    with undo_chunk("aim handle"):
        clear_aim(handle, undo=False)
        cmds.aimConstraint(target, record["aim"], maintainOffset=False, aimVector=(0, 0, 1),
                           upVector=(0, 1, 0), worldUpType="scene")


def clear_aim(handle, undo=True):
    record = handle_record(handle)
    constraints = cmds.listRelatives(record["aim"], type="aimConstraint", fullPath=True) or []
    if constraints:
        cmds.delete(constraints)
    cmds.setAttr(record["aim"] + ".rotate", 0, 0, 0)


def add_geometry(handle, meshes=None):
    record = handle_record(handle)
    meshes = meshes or [resolve_mesh(n)[0] for n in cmds.ls(selection=True, long=True, objectsOnly=True)
                        if n != handle and _is_mesh(n)]
    if not meshes:
        raise TweakError("Select the handle and the meshes to add")
    with undo_chunk("add geometry to handle"):
        for mesh in meshes:
            cmds.deformer(record["softMod"], edit=True, geometry=mesh)


def remove_geometry(handle, meshes=None):
    record = handle_record(handle)
    meshes = meshes or [resolve_mesh(n)[0] for n in cmds.ls(selection=True, long=True, objectsOnly=True)
                        if n != handle and _is_mesh(n)]
    if not meshes:
        raise TweakError("Select the handle and the meshes to remove")
    with undo_chunk("remove geometry from handle"):
        for mesh in meshes:
            cmds.deformer(record["softMod"], edit=True, remove=True, geometry=mesh)


def _is_mesh(node):
    try:
        resolve_mesh(node)
        return True
    except TweakError:
        return False


def delete_handle(handle):
    record = handle_record(handle)
    with undo_chunk("delete surface handle"):
        doomed = [n for n in [record["softMod"], record["pin"]] + record.get("nodes", [])
                  if n and cmds.objExists(n)]
        cmds.delete(doomed)


def list_handles():
    return _handles()
