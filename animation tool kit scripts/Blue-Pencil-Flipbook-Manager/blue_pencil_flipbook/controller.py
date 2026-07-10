"""Controller layer connecting UI events to Maya and persistence services."""

from __future__ import annotations

from . import maya_blue_pencil_api as bp
from . import metadata_store, session_io, thumbnail_cache
from .playback import FlipbookPlayer


class FlipbookController(object):
    def __init__(self):
        self.player = FlipbookPlayer()

    def cameras(self): return bp.cameras()
    def layers(self, camera=None): return bp.blue_pencil_layers(camera)
    def frames(self, camera=None, layer=None):
        frames = metadata_store.load_metadata().get("frames", [])
        return sorted([f for f in frames if (not camera or f.get("camera") == camera) and (not layer or f.get("layer") == layer)], key=lambda e: int(e.get("frame", 0)))

    def go_to_frame(self, entry): bp.set_current_time(entry.get("frame"))

    def entry_at(self, camera, layer, frame=None):
        """Tracked entry for a camera/layer at a frame (current time if omitted)."""
        frame = bp.current_time() if frame is None else frame
        return metadata_store.find_frame_by_time(camera, layer, frame)

    def mark_current(self, frame_type, camera, layer, isolate=False):
        entry = metadata_store.add_or_update_frame(bp.current_time(), camera, layer, frame_type)
        # Capture a viewport thumbnail on first mark so the card shows the actual
        # drawing instead of a "No Thumbnail" placeholder.
        if entry and not thumbnail_cache.has_thumbnail(entry):
            thumbnail_cache.capture_thumbnail(entry, isolate=isolate)
        return entry
    def set_frame_type(self, entry, frame_type): return metadata_store.set_frame_type(entry.get("uid"), frame_type)
    def delete_metadata(self, entry):
        # Remove the tracked drawing's metadata and its cached thumbnail image.
        thumbnail_cache.delete_thumbnail(entry)
        return metadata_store.delete_frame_metadata(entry.get("uid"))
    def regenerate_thumbnail(self, entry, isolate=False): return thumbnail_cache.capture_thumbnail(entry, isolate=isolate)
    def regenerate_all_thumbnails(self, camera=None, layer=None, isolate=False): return thumbnail_cache.regenerate_all(camera, layer, isolate=isolate)

    def export_session(self, dest_dir): return session_io.export_session(dest_dir)
    def import_session(self, path, replace=True): return session_io.import_session(path, replace)

    def tool_action(self, name, *args):
        return getattr(bp, name)(*args)
