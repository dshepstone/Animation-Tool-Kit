"""Data models for timeline bookmarks."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Bookmark:
    """Represents a timeline bookmark span."""

    name: str
    start_frame: int
    end_frame: int
    color_hex: str = "#55AA55"
    notes: Optional[str] = None
    visible: bool = True
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    @property
    def is_single_frame(self) -> bool:
        """True when the bookmark represents a single frame pose."""
        return self.start_frame == self.end_frame


@dataclass
class BookmarkCollection:
    """A thin wrapper around a list of bookmarks with computed range properties."""

    bookmarks: List[Bookmark] = field(default_factory=list)

    @property
    def min_frame(self) -> Optional[int]:
        if not self.bookmarks:
            return None
        return min(b.start_frame for b in self.bookmarks)

    @property
    def max_frame(self) -> Optional[int]:
        if not self.bookmarks:
            return None
        return max(b.end_frame for b in self.bookmarks)
