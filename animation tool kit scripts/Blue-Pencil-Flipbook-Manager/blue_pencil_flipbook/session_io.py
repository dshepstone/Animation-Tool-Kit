"""Export and import Blue Pencil Flipbook sessions.

A session bundles the tracked-frame metadata (frame types, cameras, layers,
notes) together with the captured thumbnail images so it can be archived and
re-imported later - into another scene, machine, or Maya session.

Export layout (a self-contained folder)::

    BluePencilFlipbook_Session_<timestamp>/
        session.json          # frame metadata; thumbnails stored as relative paths
        thumbnails/
            <uid>.png         # one image per tracked frame that had a thumbnail

Import reads that folder (or its session.json), copies the thumbnails back into
the tool's cache, rewrites the paths, and writes the frames into the scene's
metadata node (replacing or merging with what is already there).
"""

from __future__ import annotations

import datetime
import json
import os
import shutil

from . import maya_blue_pencil_api as bp
from . import metadata_store, thumbnail_cache

SESSION_JSON = "session.json"
THUMB_DIR = "thumbnails"
ARCHIVE_FILE = "blue_pencil.zip"
SESSION_VERSION = 1


def _timestamp():
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")


def _export_blue_pencil_archive(session_dir):
    """Export the Blue Pencil drawing archive (.zip) into session_dir.

    Returns the archive filename (relative to session_dir), or "" if nothing was
    written (e.g. no Blue Pencil frames in the scene).
    """
    try:
        path = os.path.join(session_dir, ARCHIVE_FILE)
        bp.export_archive(path)
        if os.path.exists(path):
            return ARCHIVE_FILE
    except Exception:
        pass
    return ""


def export_session(dest_dir):
    """Write a session folder under ``dest_dir``. Returns the folder path.

    Raises OSError/IOError on filesystem failures so the UI can report them.
    """
    data = metadata_store.load_metadata()
    frames = data.get("frames", [])

    session_dir = os.path.join(dest_dir, "BluePencilFlipbook_Session_" + _timestamp())
    thumbs_dir = os.path.join(session_dir, THUMB_DIR)
    os.makedirs(thumbs_dir, exist_ok=True)

    # Save the actual Blue Pencil drawing archive so imports restore the strokes,
    # not just the frame metadata and thumbnails.
    archive_name = _export_blue_pencil_archive(session_dir)

    exported_frames = []
    for entry in frames:
        record = dict(entry)
        src = entry.get("thumbnail") or ""
        rel_thumb = ""
        if src and os.path.exists(src):
            ext = os.path.splitext(src)[1] or ".png"
            name = (entry.get("uid") or "frame") + ext
            try:
                shutil.copy2(src, os.path.join(thumbs_dir, name))
                rel_thumb = THUMB_DIR + "/" + name
            except Exception:
                rel_thumb = ""
        # Store the thumbnail as a path relative to the session folder.
        record["thumbnail"] = rel_thumb
        exported_frames.append(record)

    payload = {
        "version": SESSION_VERSION,
        "exported": _timestamp(),
        "blue_pencil_archive": archive_name,
        "frames": exported_frames,
    }
    with open(os.path.join(session_dir, SESSION_JSON), "w") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
    return session_dir


def _resolve_json(session_path):
    """Return (session_dir, json_path) from a folder or a session.json path."""
    if os.path.isfile(session_path):
        return os.path.dirname(session_path), session_path
    return session_path, os.path.join(session_path, SESSION_JSON)


def import_session(session_path, replace=True):
    """Import a session folder (or its session.json).

    Copies thumbnails into the tool cache, rewrites paths, and writes the frames
    into the metadata store. When ``replace`` is False, imported frames are
    merged into the current set (matched by uid). Returns the frame count.
    """
    session_dir, json_path = _resolve_json(session_path)
    with open(json_path) as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("Not a Blue Pencil Flipbook session file.")

    # Restore the actual Blue Pencil strokes first via the drawing archive, which
    # re-creates the frames on their camera. (Also accept the short-lived
    # "blue_pencil_scene" key from an intermediate build.)
    archive = payload.get("blue_pencil_archive") or payload.get("blue_pencil_scene") or ""
    if archive:
        archive_path = os.path.join(session_dir, archive)
        if os.path.exists(archive_path):
            bp.import_archive(archive_path)

    cache = thumbnail_cache.cache_dir()
    imported = []
    for entry in payload.get("frames", []):
        record = dict(entry)
        rel = entry.get("thumbnail") or ""
        record["thumbnail"] = ""
        if rel:
            src = rel if os.path.isabs(rel) else os.path.join(session_dir, rel)
            if os.path.exists(src):
                dst = os.path.join(cache, os.path.basename(src))
                try:
                    shutil.copy2(src, dst)
                    record["thumbnail"] = dst
                except Exception:
                    record["thumbnail"] = ""
        imported.append(record)

    if replace:
        data = {"frames": imported}
    else:
        data = metadata_store.load_metadata()
        by_uid = {frame.get("uid"): frame for frame in data.get("frames", [])}
        for record in imported:
            by_uid[record.get("uid")] = record
        data = {"frames": list(by_uid.values())}

    metadata_store.save_metadata(data)
    return len(imported)
