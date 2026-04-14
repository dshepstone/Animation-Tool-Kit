"""Integration tests for MayaTimeAdapter.

MUST be run inside Maya's Script Editor or via mayapy.  These tests will
raise ImportError immediately when executed in a standard Python environment.

Usage inside Maya::

    import sys
    sys.path.insert(0, "/path/to/Bookmarks/src")
    sys.path.insert(0, "/path/to/Bookmarks/tests")

    import importlib, integration.test_maya_time_adapter as t
    t.run_all()
"""

try:
    import maya.cmds as cmds
except ImportError as exc:
    raise ImportError(
        "Integration tests must be run inside Maya (maya.cmds not found)."
    ) from exc

from time_bookmarks.maya.adapter import MayaTimeAdapter


def test_get_current_frame_matches_maya() -> None:
    expected = int(cmds.currentTime(q=True))
    adapter = MayaTimeAdapter()
    assert adapter.get_current_frame() == expected, (
        f"Expected {expected}, got {adapter.get_current_frame()}"
    )
    print("PASS  test_get_current_frame_matches_maya")


def test_set_current_frame_moves_cursor() -> None:
    original = int(cmds.currentTime(q=True))
    target = original + 10

    adapter = MayaTimeAdapter()
    adapter.set_current_frame(target)
    assert int(cmds.currentTime(q=True)) == target

    # Restore
    cmds.currentTime(original)
    print("PASS  test_set_current_frame_moves_cursor")


def test_get_playback_range_matches_maya() -> None:
    expected_start = int(cmds.playbackOptions(q=True, min=True))
    expected_end = int(cmds.playbackOptions(q=True, max=True))

    adapter = MayaTimeAdapter()
    start, end = adapter.get_playback_range()

    assert start == expected_start, f"start: {start} != {expected_start}"
    assert end == expected_end, f"end: {end} != {expected_end}"
    print("PASS  test_get_playback_range_matches_maya")


def test_set_playback_range_updates_maya() -> None:
    original_start = int(cmds.playbackOptions(q=True, min=True))
    original_end = int(cmds.playbackOptions(q=True, max=True))

    adapter = MayaTimeAdapter()
    adapter.set_playback_range(5, 150)

    assert int(cmds.playbackOptions(q=True, min=True)) == 5
    assert int(cmds.playbackOptions(q=True, max=True)) == 150

    # Restore
    cmds.playbackOptions(min=original_start, max=original_end)
    print("PASS  test_set_playback_range_updates_maya")


def run_all() -> None:
    test_get_current_frame_matches_maya()
    test_set_current_frame_moves_cursor()
    test_get_playback_range_matches_maya()
    test_set_playback_range_updates_maya()
    print("\nAll MayaTimeAdapter integration tests passed.")
