"""BookmarkController — the central orchestrator between layers.

The controller owns no UI widgets and makes no direct Maya calls.
All Maya-specific behaviour is injected via the protocol interfaces defined
in ``time_bookmarks.core.protocols``.

Qt signals are emitted through a lightweight ``_Notifier`` QObject that is
created lazily only when a Qt application is running.  When Qt is absent
(e.g. in pure unit tests) the notifier is not created and signal emission is
skipped gracefully.
"""

from __future__ import annotations

from typing import Callable, List, Optional

from time_bookmarks.core.bookmark_serializer import BookmarkSerializer
from time_bookmarks.core.bookmark_service import BookmarkService
from time_bookmarks.core.protocols import PersistenceProtocol, TimeAdapterProtocol
from time_bookmarks.data.models import Bookmark


# ---------------------------------------------------------------------------
# Optional Qt notifier
# ---------------------------------------------------------------------------

def _make_notifier():  # type: ignore[return]
    """Return a QObject subclass with typed signals, or None if Qt is absent."""
    try:
        from time_bookmarks.qt_compat import QtCore, Signal  # type: ignore[import]
    except ImportError:
        return None

    class _Notifier(QtCore.QObject):
        bookmarks_changed = Signal()
        visibility_changed = Signal(bool)

    return _Notifier


# ---------------------------------------------------------------------------
# Controller
# ---------------------------------------------------------------------------

class BookmarkController:
    """Orchestrates bookmark CRUD, persistence, navigation, and visibility.

    Parameters
    ----------
    service:
        The bookmark store.
    time_adapter:
        Provides access to Maya's current frame and playback range.
    persistence:
        Handles saving and loading bookmarks to/from durable storage.
    """

    def __init__(
        self,
        service: BookmarkService,
        time_adapter: TimeAdapterProtocol,
        persistence: PersistenceProtocol,
    ) -> None:
        self._service = service
        self._time_adapter = time_adapter
        self._persistence = persistence
        self._overlay_visible: bool = True
        self._on_change_callbacks: List[Callable[[], None]] = []

        # Lazily create Qt notifier when Qt is available.
        NotifierClass = _make_notifier()
        self._notifier = NotifierClass() if NotifierClass is not None else None

    # ------------------------------------------------------------------
    # Public signal-like interface (works with and without Qt)
    # ------------------------------------------------------------------

    def on_bookmarks_changed(self, callback: Callable[[], None]) -> None:
        """Register a plain Python callback invoked whenever bookmarks change.

        In Qt environments, prefer connecting to ``notifier.bookmarks_changed``
        instead.
        """
        self._on_change_callbacks.append(callback)

    @property
    def notifier(self):  # type: ignore[return]
        """The ``_Notifier`` QObject, or ``None`` when Qt is unavailable."""
        return self._notifier

    def _emit_change(self) -> None:
        for cb in self._on_change_callbacks:
            cb()
        if self._notifier is not None:
            self._notifier.bookmarks_changed.emit()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create_bookmark_at_current_range(
        self,
        name: str,
        color_hex: str,
        notes: str = "",
    ) -> Bookmark:
        """Create a bookmark spanning the current playback range."""
        start, end = self._time_adapter.get_playback_range()
        bookmark = self._service.create_bookmark(
            name=name,
            start_frame=start,
            end_frame=end,
            color_hex=color_hex,
            notes=notes or None,
        )
        self._emit_change()
        return bookmark

    def create_bookmark(
        self,
        name: str,
        start_frame: int,
        end_frame: int,
        color_hex: str,
        notes: str = "",
        visible: bool = True,
    ) -> Bookmark:
        """Create a bookmark with an explicitly specified frame range."""
        bookmark = self._service.create_bookmark(
            name=name,
            start_frame=start_frame,
            end_frame=end_frame,
            color_hex=color_hex,
            notes=notes or None,
            visible=visible,
        )
        self._emit_change()
        return bookmark

    def create_bookmark_at_current_frame(
        self,
        name: str,
        color_hex: str,
        notes: str = "",
    ) -> Bookmark:
        """Create a single-frame bookmark at the timeline's current frame."""
        current = self._time_adapter.get_current_frame()
        return self.create_bookmark(
            name=name,
            start_frame=current,
            end_frame=current,
            color_hex=color_hex,
            notes=notes,
        )

    def update_bookmark(self, bookmark_id: str, **kwargs: object) -> Bookmark:
        """Update fields on an existing bookmark."""
        bookmark = self._service.update_bookmark(bookmark_id, **kwargs)
        self._emit_change()
        return bookmark

    def delete_bookmark(self, bookmark_id: str) -> None:
        """Delete the bookmark with the given id."""
        self._service.delete_bookmark(bookmark_id)
        self._emit_change()

    def delete_all_bookmarks(self) -> int:
        """Remove every bookmark from the store and return how many were removed."""
        count = len(self._service.list_bookmarks())
        if count == 0:
            return 0
        for bookmark in list(self._service.list_bookmarks()):
            self._service.delete_bookmark(bookmark.id)
        self._emit_change()
        return count

    def list_bookmarks(self) -> List[Bookmark]:
        """Return all bookmarks sorted by start_frame."""
        return self._service.list_bookmarks()

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def jump_to_bookmark(self, bookmark_id: str) -> None:
        """Set the timeline to the start_frame of the given bookmark."""
        bookmark = self._service.get_bookmark(bookmark_id)
        self._time_adapter.set_current_frame(bookmark.start_frame)

    def navigate_next(self) -> Optional[Bookmark]:
        """Move to the next bookmark after the current frame and return it."""
        current = self._time_adapter.get_current_frame()
        bookmark = self._service.next_bookmark(current)
        if bookmark is not None:
            self._time_adapter.set_current_frame(bookmark.start_frame)
        return bookmark

    def navigate_prev(self) -> Optional[Bookmark]:
        """Move to the previous bookmark before the current frame and return it."""
        current = self._time_adapter.get_current_frame()
        bookmark = self._service.prev_bookmark(current)
        if bookmark is not None:
            self._time_adapter.set_current_frame(bookmark.start_frame)
        return bookmark

    def get_current_frame(self) -> int:
        """Return the frame the timeline cursor is currently on."""
        return self._time_adapter.get_current_frame()

    def remove_at_current_frame(self) -> None:
        """Remove the first bookmark whose range includes the current frame.

        Silent no-op when no bookmark covers the current position.
        """
        current = self._time_adapter.get_current_frame()
        candidates = self._service.find_at_frame(current)
        if candidates:
            self._service.delete_bookmark(candidates[0].id)
            self._emit_change()

    def jump_to_bookmark_at_current_frame(self) -> Optional[Bookmark]:
        """Set the playback range to the bookmark covering the current frame.

        Returns the bookmark jumped to, or ``None`` when no bookmark is found.
        """
        current = self._time_adapter.get_current_frame()
        candidates = self._service.find_at_frame(current)
        if not candidates:
            return None
        bookmark = candidates[0]
        self._time_adapter.set_playback_range(bookmark.start_frame, bookmark.end_frame)
        self._time_adapter.set_current_frame(bookmark.start_frame)
        return bookmark

    # ------------------------------------------------------------------
    # Playback range query (used by creation dialog for pre-filling)
    # ------------------------------------------------------------------

    def get_playback_range(self) -> tuple:
        """Return the current playback range as (start, end)."""
        return self._time_adapter.get_playback_range()

    def get_timeline_selection(self) -> "tuple | None":
        """Return the user's dragged timeline selection, or None.

        Delegates to the time adapter.  Returns ``None`` when the adapter does
        not support selection queries or when no range is selected.
        """
        return self._time_adapter.get_timeline_selection()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save_to_scene(self) -> None:
        """Persist current bookmarks to the scene via the persistence backend."""
        self._persistence.save(self._service.list_bookmarks())

    def load_from_scene(self) -> None:
        """Load bookmarks from the persistence backend, replacing current state."""
        bookmarks = self._persistence.load()
        # Reload the service state from the loaded bookmarks.
        self._service = BookmarkService()
        for b in bookmarks:
            self._service._bookmarks[b.id] = b
        self._emit_change()

    # ------------------------------------------------------------------
    # Visibility
    # ------------------------------------------------------------------

    def toggle_visibility(self) -> bool:
        """Toggle overlay visibility and return the new state."""
        self._overlay_visible = not self._overlay_visible
        if self._notifier is not None:
            self._notifier.visibility_changed.emit(self._overlay_visible)
        self._emit_change()
        return self._overlay_visible

    def set_all_visible(self, visible: bool) -> None:
        """Explicitly set the global overlay visibility state.

        This is the back-end for the panel's "Show/Hide All" toggle button.
        """
        if self._overlay_visible == visible:
            return
        self._overlay_visible = visible
        if self._notifier is not None:
            self._notifier.visibility_changed.emit(self._overlay_visible)
        self._emit_change()

    def set_bookmark_visible(self, bookmark_id: str, visible: bool) -> Bookmark:
        """Set the ``visible`` flag on a single bookmark."""
        bookmark = self._service.update_bookmark(bookmark_id, visible=bool(visible))
        self._emit_change()
        return bookmark

    def toggle_bookmark_visible(self, bookmark_id: str) -> bool:
        """Flip the ``visible`` flag on a single bookmark and return the new state."""
        bookmark = self._service.get_bookmark(bookmark_id)
        new_state = not bookmark.visible
        self._service.update_bookmark(bookmark_id, visible=new_state)
        self._emit_change()
        return new_state

    @property
    def overlay_visible(self) -> bool:
        return self._overlay_visible
