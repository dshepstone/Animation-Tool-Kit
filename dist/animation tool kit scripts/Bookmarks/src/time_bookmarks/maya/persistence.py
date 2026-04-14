"""MayaScenePersistence — stores bookmarks in the Maya scene via fileInfo.

``cmds.fileInfo`` embeds arbitrary key/value strings directly in the ``.ma``
or ``.mb`` file, so bookmarks travel with the scene when it is saved, emailed,
or submitted to a render farm.

The storage key is ``"time_bookmarks_v1"``.  The ``v1`` suffix makes future
format migrations detectable: a ``v2`` writer can detect the old key, upgrade
the data, write the new key, and delete the old one without breaking existing
scenes.

All ``maya.cmds`` calls are deferred inside method bodies so the module is
safe to import outside of Maya.
"""

from __future__ import annotations

import json
import logging
from typing import List

from time_bookmarks.core.bookmark_serializer import BookmarkSerializer
from time_bookmarks.core.protocols import PersistenceProtocol
from time_bookmarks.data.models import Bookmark

_log = logging.getLogger(__name__)

_FILEINFO_KEY = "time_bookmarks_v1"


class MayaScenePersistence(PersistenceProtocol):
    """Implements ``PersistenceProtocol`` using ``cmds.fileInfo``."""

    def save(self, bookmarks: List[Bookmark]) -> None:
        """Serialise *bookmarks* to JSON and write it to the scene's fileInfo.

        The write happens immediately; the user still needs to save the scene
        file itself for the data to be persisted to disk.
        """
        import maya.cmds as cmds  # noqa: PLC0415

        json_str = BookmarkSerializer.collection_to_json(bookmarks)
        cmds.fileInfo(_FILEINFO_KEY, json_str)
        _log.debug("Saved %d bookmark(s) to scene fileInfo.", len(bookmarks))

    def load(self) -> List[Bookmark]:
        """Read and deserialise bookmarks from the scene's fileInfo.

        Returns an empty list when no bookmark data is present or when the
        stored JSON is malformed (a warning is logged in that case).
        """
        import maya.cmds as cmds  # noqa: PLC0415

        result = cmds.fileInfo(_FILEINFO_KEY, q=True)

        # fileInfo returns [] when the key does not exist.
        if not result:
            return []

        raw = result[0]

        # Maya escapes backslashes inside fileInfo values.  Un-escape so that
        # the JSON parser sees clean input.
        raw = raw.replace('\\"', '"').replace("\\\\", "\\")

        try:
            bookmarks = BookmarkSerializer.collection_from_json(raw)
            _log.debug("Loaded %d bookmark(s) from scene fileInfo.", len(bookmarks))
            return bookmarks
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            _log.warning(
                "time_bookmarks: failed to parse scene bookmark data (%s). "
                "The data may be corrupt — bookmarks have been reset.",
                exc,
            )
            return []
