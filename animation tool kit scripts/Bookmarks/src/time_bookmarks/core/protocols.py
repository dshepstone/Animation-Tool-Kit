"""Abstract base classes that decouple the controller from Maya-specific code.

These ABCs are the dependency-injection seam of the architecture.
The real Maya implementations live in ``time_bookmarks.maya``.
Test-friendly fake implementations live in ``tests.fakes``.
"""

from __future__ import annotations

import abc
from typing import List, TYPE_CHECKING

if TYPE_CHECKING:
    from time_bookmarks.data.models import Bookmark


class TimeAdapterProtocol(abc.ABC):
    """Interface for querying and mutating Maya's timeline state."""

    @abc.abstractmethod
    def get_current_frame(self) -> int:
        """Return the frame the timeline cursor is currently on."""

    @abc.abstractmethod
    def set_current_frame(self, frame: int) -> None:
        """Move the timeline cursor to *frame*."""

    @abc.abstractmethod
    def get_playback_range(self) -> tuple:
        """Return ``(start_frame, end_frame)`` of the current playback range."""

    @abc.abstractmethod
    def set_playback_range(self, start: int, end: int) -> None:
        """Set the playback range to [start, end]."""

    def get_timeline_selection(self) -> "tuple | None":
        """Return the user's dragged timeline selection as (start, end), or None.

        A concrete default returning ``None`` is provided so existing subclasses
        do not need to implement this method.  Override it in real host adapters
        (e.g. ``MayaTimeAdapter``) to read the actual selection from the host.
        """
        return None


class PersistenceProtocol(abc.ABC):
    """Interface for saving and loading bookmark collections."""

    @abc.abstractmethod
    def save(self, bookmarks: List["Bookmark"]) -> None:
        """Persist *bookmarks* to the underlying storage backend."""

    @abc.abstractmethod
    def load(self) -> List["Bookmark"]:
        """Load and return bookmarks from the underlying storage backend.

        Returns an empty list when no data is found.
        """
