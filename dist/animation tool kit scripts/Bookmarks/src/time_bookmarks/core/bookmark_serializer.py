"""Serialisation helpers for converting Bookmark objects to/from JSON.

This module is intentionally free of Maya and Qt imports so that it can be
used in tests and offline tooling without any external dependencies.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from time_bookmarks.data.models import Bookmark


class BookmarkSerializer:
    """Stateless converter between ``Bookmark`` objects and plain dicts / JSON."""

    # ------------------------------------------------------------------
    # Single-bookmark conversions
    # ------------------------------------------------------------------

    @staticmethod
    def to_dict(bookmark: Bookmark) -> Dict[str, Any]:
        """Return a JSON-safe dict representation of *bookmark*."""
        return {
            "id": bookmark.id,
            "name": bookmark.name,
            "start_frame": bookmark.start_frame,
            "end_frame": bookmark.end_frame,
            "color_hex": bookmark.color_hex,
            "notes": bookmark.notes,
            "visible": bookmark.visible,
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> Bookmark:
        """Reconstruct a ``Bookmark`` from a plain dict.

        Raises ``KeyError`` if a required field is missing.  ``visible``
        defaults to ``True`` when absent so pre-existing saved data keeps
        working.
        """
        return Bookmark(
            id=data["id"],
            name=data["name"],
            start_frame=int(data["start_frame"]),
            end_frame=int(data["end_frame"]),
            color_hex=data["color_hex"],
            notes=data.get("notes"),
            visible=bool(data.get("visible", True)),
        )

    # ------------------------------------------------------------------
    # Collection conversions
    # ------------------------------------------------------------------

    @staticmethod
    def collection_to_json(bookmarks: List[Bookmark]) -> str:
        """Serialise a list of bookmarks to a compact JSON string."""
        payload = [BookmarkSerializer.to_dict(b) for b in bookmarks]
        return json.dumps(payload, separators=(",", ":"))

    @staticmethod
    def collection_from_json(json_str: str) -> List[Bookmark]:
        """Deserialise a JSON string back to a list of ``Bookmark`` objects.

        Raises ``json.JSONDecodeError`` on malformed input.
        """
        payload: List[Dict[str, Any]] = json.loads(json_str)
        return [BookmarkSerializer.from_dict(item) for item in payload]
