"""MayaTimeAdapter — wraps maya.cmds timeline queries.

All ``maya.cmds`` calls are deferred inside method bodies so this module can
be imported safely in non-Maya environments (the import itself never fails).
Only instantiate this class when running inside Maya.
"""

from __future__ import annotations

from time_bookmarks.core.protocols import TimeAdapterProtocol


class MayaTimeAdapter(TimeAdapterProtocol):
    """Implements ``TimeAdapterProtocol`` using ``maya.cmds``."""

    def get_current_frame(self) -> int:
        """Return the frame the timeline cursor is currently on."""
        import maya.cmds as cmds  # noqa: PLC0415
        return int(cmds.currentTime(q=True))

    def set_current_frame(self, frame: int) -> None:
        """Move the timeline cursor to *frame*."""
        import maya.cmds as cmds  # noqa: PLC0415
        cmds.currentTime(frame)

    def get_playback_range(self) -> tuple:
        """Return ``(start_frame, end_frame)`` of the active playback range."""
        import maya.cmds as cmds  # noqa: PLC0415
        start = int(cmds.playbackOptions(q=True, min=True))
        end = int(cmds.playbackOptions(q=True, max=True))
        return (start, end)

    def set_playback_range(self, start: int, end: int) -> None:
        """Set the active playback range to ``[start, end]``."""
        import maya.cmds as cmds  # noqa: PLC0415
        cmds.playbackOptions(min=start, max=end)

    def get_timeline_selection(self) -> "tuple | None":
        """Return the frame range the user has dragged-selected on the timeline.

        Maya's ``timeControl -rangeArray`` returns ``[start, exclusiveEnd]``.
        A selection is considered real when ``exclusiveEnd - start > 1``
        (a single-frame position returns ``[frame, frame+1]``).

        Returns ``None`` when there is no explicit selection so callers can
        fall back to the playback range.
        """
        try:
            import maya.cmds as cmds  # noqa: PLC0415
            import maya.mel as mel   # noqa: PLC0415
            slider = mel.eval("$_tmp=$gPlayBackSlider")
            arr = cmds.timeControl(slider, q=True, rangeArray=True)
            if arr and (arr[1] - arr[0]) > 1:
                return (int(arr[0]), int(arr[1]) - 1)  # make end inclusive
        except Exception:
            pass
        return None
