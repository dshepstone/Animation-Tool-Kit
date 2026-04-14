"""Test-only fake implementations of the protocol interfaces.

These fakes implement ``TimeAdapterProtocol`` and ``PersistenceProtocol``
using plain Python — no Maya, no Qt.  They let the full controller logic be
exercised in ordinary pytest runs.
"""

from __future__ import annotations

from typing import List, Tuple

from time_bookmarks.core.bookmark_serializer import BookmarkSerializer
from time_bookmarks.core.protocols import PersistenceProtocol, TimeAdapterProtocol
from time_bookmarks.data.models import Bookmark


class FakeTimeAdapter(TimeAdapterProtocol):
    """In-memory stand-in for MayaTimeAdapter.

    Attributes are publicly settable so tests can arrange any timeline state:

        adapter = FakeTimeAdapter(current_frame=50, playback_range=(1, 120))
    """

    def __init__(
        self,
        current_frame: int = 1,
        playback_range: Tuple[int, int] = (1, 100),
    ) -> None:
        self._current_frame = current_frame
        self._playback_range = playback_range

    def get_current_frame(self) -> int:
        return self._current_frame

    def set_current_frame(self, frame: int) -> None:
        self._current_frame = frame

    def get_playback_range(self) -> Tuple[int, int]:
        return self._playback_range

    def set_playback_range(self, start: int, end: int) -> None:
        self._playback_range = (start, end)


class InMemoryPersistence(PersistenceProtocol):
    """In-memory stand-in for MayaScenePersistence.

    ``save`` serialises to a JSON string held in ``self._data``.
    ``load`` deserialises it back.  This exercises the serialiser round-trip
    without touching the filesystem or a Maya scene.
    """

    def __init__(self) -> None:
        self._data: str = "[]"

    def save(self, bookmarks: List[Bookmark]) -> None:
        self._data = BookmarkSerializer.collection_to_json(bookmarks)

    def load(self) -> List[Bookmark]:
        return BookmarkSerializer.collection_from_json(self._data)


class FakeSignalSpy:
    """Records emissions from a ``BookmarkController`` change callback.

    Usage::

        spy = FakeSignalSpy()
        controller.on_bookmarks_changed(spy)
        controller.create_bookmark(...)
        assert spy.call_count == 1
    """

    def __init__(self) -> None:
        self.call_count: int = 0

    def __call__(self) -> None:
        self.call_count += 1
