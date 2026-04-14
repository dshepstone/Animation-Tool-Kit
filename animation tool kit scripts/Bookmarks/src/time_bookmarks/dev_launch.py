"""Standalone development entry point — no Maya required.

Launches ``BookmarkPanel`` wired to in-memory fakes so the full Qt UI can be
developed and tested outside of Maya.

Usage::

    python -m time_bookmarks.dev_launch

The panel is pre-populated with representative example bookmarks so all UI
paths (edit, delete, jump, colour picker, scroll) can be exercised immediately.
"""

from __future__ import annotations

import sys


def main() -> None:
    from time_bookmarks.qt_compat import QtWidgets, exec_app

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    app.setApplicationName("Time Bookmarks (dev)")

    # Import here so that QApplication exists before any widget is constructed.
    from time_bookmarks.core.bookmark_service import BookmarkService
    from time_bookmarks.core.controller import BookmarkController
    from time_bookmarks.ui.bookmark_panel import BookmarkPanel

    # Inline fakes so this file has no dependency on the tests/ package.
    from time_bookmarks.core.bookmark_serializer import BookmarkSerializer
    from time_bookmarks.core.protocols import PersistenceProtocol, TimeAdapterProtocol
    from time_bookmarks.data.models import Bookmark

    class _FakeTimeAdapter(TimeAdapterProtocol):
        def __init__(self) -> None:
            self._frame = 1
            self._range = (1, 300)

        def get_current_frame(self) -> int:
            return self._frame

        def set_current_frame(self, frame: int) -> None:
            self._frame = frame
            print(f"[dev] current frame → {frame}")

        def get_playback_range(self):
            return self._range

        def set_playback_range(self, start: int, end: int) -> None:
            self._range = (start, end)

    class _FakePersistence(PersistenceProtocol):
        def __init__(self) -> None:
            self._data = "[]"

        def save(self, bookmarks: list) -> None:
            self._data = BookmarkSerializer.collection_to_json(bookmarks)
            print(f"[dev] saved {len(bookmarks)} bookmark(s)")

        def load(self) -> list:
            return BookmarkSerializer.collection_from_json(self._data)

    service = BookmarkService()
    controller = BookmarkController(
        service=service,
        time_adapter=_FakeTimeAdapter(),
        persistence=_FakePersistence(),
    )

    # Pre-populate with representative examples matching the screenshots.
    controller.create_bookmark("First Move",    1,   73, "#E57373")
    controller.create_bookmark("Jump and Spin", 75, 126, "#4CAF50")
    controller.create_bookmark("Last Dance",   198, 271, "#64B5F6")
    controller.create_bookmark("Chomp",        253, 305, "#E57373")

    panel = BookmarkPanel(controller=controller)
    panel.show()

    sys.exit(exec_app(app))


if __name__ == "__main__":
    main()
