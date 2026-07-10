"""Persistent frame metadata stored on a hidden Maya network node."""

from __future__ import annotations

import json
import uuid

try:
    from maya import cmds
except Exception:
    cmds = None

META_NODE = "bluePencilFlipbook_META"
META_ATTR = "frameDataJson"
FRAME_TYPES = {"KEY", "BREAKDOWN", "INBETWEEN"}


def _warn(message: str) -> None:
    if cmds:
        cmds.warning("Blue Pencil Flipbook Manager: {0}".format(message))
    else:
        print("Blue Pencil Flipbook Manager: {0}".format(message))


def _empty_data():
    return {"frames": []}


def get_or_create_metadata_node():
    if cmds is None:
        return None
    try:
        if not cmds.objExists(META_NODE):
            node = cmds.createNode("network", name=META_NODE, skipSelect=True)
            # hiddenInOutliner is not present on network nodes in some Maya
            # versions (2026 raises "No object matches name"); it's cosmetic,
            # so never let it abort metadata-node creation.
            try:
                cmds.setAttr(node + ".hiddenInOutliner", True)
            except Exception:
                pass
        else:
            node = META_NODE
        if not cmds.attributeQuery(META_ATTR, node=node, exists=True):
            cmds.addAttr(node, longName=META_ATTR, dataType="string")
            cmds.setAttr(node + "." + META_ATTR, json.dumps(_empty_data()), type="string")
        return node
    except Exception as exc:
        _warn("Could not create metadata node: {0}".format(exc))
        return None


def load_metadata():
    node = get_or_create_metadata_node()
    if cmds is None or not node:
        return _empty_data()
    try:
        raw = cmds.getAttr(node + "." + META_ATTR) or "{}"
        data = json.loads(raw)
        if not isinstance(data, dict) or "frames" not in data:
            return _empty_data()
        return data
    except Exception as exc:
        _warn("Could not read frame metadata: {0}".format(exc))
        return _empty_data()


def save_metadata(data):
    node = get_or_create_metadata_node()
    if cmds is None or not node:
        return False
    try:
        cmds.setAttr(node + "." + META_ATTR, json.dumps(data, indent=2, sort_keys=True), type="string")
        return True
    except Exception as exc:
        _warn("Could not save frame metadata: {0}".format(exc))
        return False


def _normalize_type(frame_type):
    value = (frame_type or "INBETWEEN").upper()
    return value if value in FRAME_TYPES else "INBETWEEN"


def add_or_update_frame(frame, camera, layer, frame_type="INBETWEEN"):
    data = load_metadata()
    existing = find_frame_by_time(camera, layer, frame, data=data)
    if existing:
        existing["type"] = _normalize_type(frame_type)
        existing.setdefault("thumbnail", "")
        existing.setdefault("note", "")
        save_metadata(data)
        return existing
    entry = {
        "uid": str(uuid.uuid4()),
        "camera": camera or "DefaultCamera",
        "layer": layer or "Default",
        "frame": int(frame),
        "type": _normalize_type(frame_type),
        "thumbnail": "",
        "note": "",
    }
    data["frames"].append(entry)
    save_metadata(data)
    return entry


def set_frame_type(uid, frame_type):
    data = load_metadata()
    for entry in data.get("frames", []):
        if entry.get("uid") == uid:
            entry["type"] = _normalize_type(frame_type)
            save_metadata(data)
            return entry
    return None


def set_thumbnail(uid, thumbnail_path):
    data = load_metadata()
    for entry in data.get("frames", []):
        if entry.get("uid") == uid:
            entry["thumbnail"] = thumbnail_path or ""
            save_metadata(data)
            return entry
    return None


def delete_frame_metadata(uid):
    data = load_metadata()
    frames = data.get("frames", [])
    data["frames"] = [entry for entry in frames if entry.get("uid") != uid]
    changed = len(data["frames"]) != len(frames)
    if changed:
        save_metadata(data)
    return changed


def find_frame_by_time(camera, layer, frame, data=None):
    data = data or load_metadata()
    for entry in data.get("frames", []):
        if entry.get("camera") == camera and entry.get("layer") == layer and int(entry.get("frame", -1)) == int(frame):
            return entry
    return None
