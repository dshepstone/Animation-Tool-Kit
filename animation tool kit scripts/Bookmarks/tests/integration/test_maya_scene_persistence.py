"""Integration tests for MayaScenePersistence.

MUST be run inside Maya's Script Editor or via mayapy.

Usage inside Maya::

    import sys
    sys.path.insert(0, "/path/to/Bookmarks/src")
    sys.path.insert(0, "/path/to/Bookmarks/tests")

    import integration.test_maya_scene_persistence as t
    t.run_all()

NOTE: These tests modify and then clean up the current scene's fileInfo.
They do NOT save the scene to disk.
"""

try:
    import maya.cmds as cmds
except ImportError as exc:
    raise ImportError(
        "Integration tests must be run inside Maya (maya.cmds not found)."
    ) from exc

from time_bookmarks.data.models import Bookmark
from time_bookmarks.maya.persistence import MayaScenePersistence

_KEY = "time_bookmarks_v1"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cleanup() -> None:
    """Remove the test key from scene fileInfo."""
    try:
        cmds.fileInfo(rm=_KEY)
    except Exception:
        pass


def _make_bookmarks() -> list[Bookmark]:
    return [
        Bookmark(id="int-1", name="Walk Cycle",   start_frame=1,   end_frame=50,  color_hex="#4CAF50"),
        Bookmark(id="int-2", name="Jump and Spin", start_frame=60,  end_frame=120, color_hex="#E57373"),
        Bookmark(id="int-3", name="Last Dance",    start_frame=130, end_frame=200, color_hex="#64B5F6"),
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_load_returns_empty_when_no_key() -> None:
    _cleanup()
    persistence = MayaScenePersistence()
    result = persistence.load()
    assert result == [], f"Expected [], got {result}"
    print("PASS  test_load_returns_empty_when_no_key")


def test_save_then_load_round_trip() -> None:
    _cleanup()
    bookmarks = _make_bookmarks()
    persistence = MayaScenePersistence()

    persistence.save(bookmarks)
    restored = persistence.load()

    assert len(restored) == 3, f"Expected 3, got {len(restored)}"
    for orig, rest in zip(bookmarks, restored):
        assert rest.id == orig.id, f"id mismatch: {rest.id!r} != {orig.id!r}"
        assert rest.name == orig.name
        assert rest.start_frame == orig.start_frame
        assert rest.end_frame == orig.end_frame
        assert rest.color_hex == orig.color_hex

    _cleanup()
    print("PASS  test_save_then_load_round_trip")


def test_save_empty_list() -> None:
    _cleanup()
    persistence = MayaScenePersistence()
    persistence.save([])
    result = persistence.load()
    assert result == [], f"Expected [], got {result}"
    _cleanup()
    print("PASS  test_save_empty_list")


def test_overwrites_previous_data() -> None:
    _cleanup()
    persistence = MayaScenePersistence()
    bookmarks = _make_bookmarks()

    persistence.save(bookmarks)
    persistence.save(bookmarks[:1])  # Overwrite with just one.

    result = persistence.load()
    assert len(result) == 1, f"Expected 1, got {len(result)}"
    assert result[0].id == "int-1"

    _cleanup()
    print("PASS  test_overwrites_previous_data")


def test_notes_preserved() -> None:
    _cleanup()
    b = Bookmark(
        id="note-test", name="Noted", start_frame=1, end_frame=10,
        color_hex="#9C27B0", notes="Hero moment — do not cut"
    )
    persistence = MayaScenePersistence()
    persistence.save([b])
    result = persistence.load()

    assert result[0].notes == "Hero moment — do not cut"
    _cleanup()
    print("PASS  test_notes_preserved")


def run_all() -> None:
    test_load_returns_empty_when_no_key()
    test_save_then_load_round_trip()
    test_save_empty_list()
    test_overwrites_previous_data()
    test_notes_preserved()
    print("\nAll MayaScenePersistence integration tests passed.")
