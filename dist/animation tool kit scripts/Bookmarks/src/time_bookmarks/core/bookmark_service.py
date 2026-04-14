"""Core logic for creating and managing timeline bookmarks."""

from __future__ import annotations

from typing import Dict, List, Optional

from time_bookmarks.data.models import Bookmark


class BookmarkService:
    """In-memory bookmark store with id-keyed CRUD and navigation helpers."""

    def __init__(self) -> None:
        self._bookmarks: Dict[str, Bookmark] = {}

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create_bookmark(
        self,
        name: str,
        start_frame: int,
        end_frame: int,
        color_hex: str,
        notes: Optional[str] = None,
        visible: bool = True,
    ) -> Bookmark:
        """Create, store, and return a new bookmark."""
        if end_frame < start_frame:
            raise ValueError("end_frame must be greater than or equal to start_frame")

        bookmark = Bookmark(
            name=name,
            start_frame=start_frame,
            end_frame=end_frame,
            color_hex=color_hex,
            notes=notes,
            visible=visible,
        )
        self._bookmarks[bookmark.id] = bookmark
        return bookmark

    def get_bookmark(self, bookmark_id: str) -> Bookmark:
        """Return the bookmark with the given id, or raise KeyError."""
        if bookmark_id not in self._bookmarks:
            raise KeyError(f"No bookmark with id '{bookmark_id}'")
        return self._bookmarks[bookmark_id]

    def update_bookmark(self, bookmark_id: str, **kwargs: object) -> Bookmark:
        """Update fields on an existing bookmark and return it.

        Only ``name``, ``start_frame``, ``end_frame``, ``color_hex``, and
        ``notes`` may be updated.  Attempting to change ``id`` raises
        ``ValueError``.  Passing an invalid frame range raises ``ValueError``.
        """
        allowed = {"name", "start_frame", "end_frame", "color_hex", "notes", "visible"}
        invalid = set(kwargs) - allowed
        if invalid:
            raise ValueError(f"Cannot update field(s): {invalid}")

        bookmark = self.get_bookmark(bookmark_id)

        # Resolve the final frame range before applying any change.
        new_start = int(kwargs.get("start_frame", bookmark.start_frame))  # type: ignore[arg-type]
        new_end = int(kwargs.get("end_frame", bookmark.end_frame))  # type: ignore[arg-type]
        if new_end < new_start:
            raise ValueError("end_frame must be greater than or equal to start_frame")

        for key, value in kwargs.items():
            object.__setattr__(bookmark, key, value)

        return bookmark

    def delete_bookmark(self, bookmark_id: str) -> None:
        """Remove the bookmark with the given id. Silent no-op if not found."""
        self._bookmarks.pop(bookmark_id, None)

    def list_bookmarks(self) -> List[Bookmark]:
        """Return bookmarks sorted by start_frame."""
        return sorted(self._bookmarks.values(), key=lambda b: b.start_frame)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def find_at_frame(self, frame: int) -> List[Bookmark]:
        """Return all bookmarks whose range includes *frame* (inclusive)."""
        return [
            b for b in self._bookmarks.values()
            if b.start_frame <= frame <= b.end_frame
        ]

    def next_bookmark(self, from_frame: int) -> Optional[Bookmark]:
        """Return the nearest bookmark that starts *after* from_frame, or None."""
        candidates = [
            b for b in self._bookmarks.values()
            if b.start_frame > from_frame
        ]
        if not candidates:
            return None
        return min(candidates, key=lambda b: b.start_frame)

    def prev_bookmark(self, from_frame: int) -> Optional[Bookmark]:
        """Return the nearest bookmark that ends *before* from_frame, or None."""
        candidates = [
            b for b in self._bookmarks.values()
            if b.end_frame < from_frame
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda b: b.end_frame)
