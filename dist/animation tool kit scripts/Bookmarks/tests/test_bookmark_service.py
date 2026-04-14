"""Tests for BookmarkService — id-keyed CRUD and navigation queries."""

import pytest

from time_bookmarks.core.bookmark_service import BookmarkService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def service() -> BookmarkService:
    return BookmarkService()


@pytest.fixture()
def populated(service: BookmarkService) -> BookmarkService:
    """Service pre-loaded with three non-overlapping bookmarks."""
    service.create_bookmark("First Move", 1, 50, "#FF5555")
    service.create_bookmark("Jump and Spin", 60, 120, "#55FF55")
    service.create_bookmark("Last Dance", 130, 200, "#5555FF")
    return service


# ---------------------------------------------------------------------------
# create_bookmark
# ---------------------------------------------------------------------------

class TestCreateBookmark:
    def test_returns_bookmark_with_correct_fields(self, service):
        b = service.create_bookmark("Walk Cycle", 100, 140, "#4CAF50")
        assert b.name == "Walk Cycle"
        assert b.start_frame == 100
        assert b.end_frame == 140
        assert b.color_hex == "#4CAF50"
        assert b.notes is None

    def test_assigns_unique_ids(self, service):
        b1 = service.create_bookmark("A", 1, 10, "#000000")
        b2 = service.create_bookmark("B", 11, 20, "#000000")
        assert b1.id != b2.id

    def test_single_frame_bookmark_allowed(self, service):
        b = service.create_bookmark("Pose", 42, 42, "#FFFFFF")
        assert b.start_frame == b.end_frame == 42

    def test_invalid_frame_range_raises(self, service):
        with pytest.raises(ValueError, match="end_frame"):
            service.create_bookmark("Bad", 100, 50, "#000000")

    def test_optional_notes_stored(self, service):
        b = service.create_bookmark("Noted", 1, 10, "#000000", notes="hero moment")
        assert b.notes == "hero moment"


# ---------------------------------------------------------------------------
# list_bookmarks
# ---------------------------------------------------------------------------

class TestListBookmarks:
    def test_empty_initially(self, service):
        assert service.list_bookmarks() == []

    def test_returns_copy(self, service):
        service.create_bookmark("A", 1, 10, "#000000")
        result = service.list_bookmarks()
        result.clear()
        assert len(service.list_bookmarks()) == 1

    def test_sorted_by_start_frame(self, service):
        service.create_bookmark("Late", 200, 300, "#000000")
        service.create_bookmark("Early", 10, 50, "#000000")
        service.create_bookmark("Mid", 100, 150, "#000000")
        names = [b.name for b in service.list_bookmarks()]
        assert names == ["Early", "Mid", "Late"]


# ---------------------------------------------------------------------------
# get_bookmark
# ---------------------------------------------------------------------------

class TestGetBookmark:
    def test_returns_correct_bookmark(self, service):
        b = service.create_bookmark("A", 1, 10, "#000000")
        assert service.get_bookmark(b.id) is b

    def test_missing_id_raises_key_error(self, service):
        with pytest.raises(KeyError):
            service.get_bookmark("non-existent-id")


# ---------------------------------------------------------------------------
# update_bookmark
# ---------------------------------------------------------------------------

class TestUpdateBookmark:
    def test_updates_name(self, service):
        b = service.create_bookmark("Old Name", 1, 10, "#000000")
        service.update_bookmark(b.id, name="New Name")
        assert service.get_bookmark(b.id).name == "New Name"

    def test_updates_frame_range(self, service):
        b = service.create_bookmark("A", 1, 10, "#000000")
        service.update_bookmark(b.id, start_frame=5, end_frame=15)
        updated = service.get_bookmark(b.id)
        assert updated.start_frame == 5
        assert updated.end_frame == 15

    def test_invalid_frame_range_raises(self, service):
        b = service.create_bookmark("A", 1, 10, "#000000")
        with pytest.raises(ValueError):
            service.update_bookmark(b.id, start_frame=50, end_frame=10)

    def test_invalid_field_raises(self, service):
        b = service.create_bookmark("A", 1, 10, "#000000")
        with pytest.raises(ValueError, match="Cannot update"):
            service.update_bookmark(b.id, id="hacked")

    def test_missing_id_raises(self, service):
        with pytest.raises(KeyError):
            service.update_bookmark("no-such-id", name="X")


# ---------------------------------------------------------------------------
# delete_bookmark
# ---------------------------------------------------------------------------

class TestDeleteBookmark:
    def test_removes_bookmark(self, service):
        b = service.create_bookmark("A", 1, 10, "#000000")
        service.delete_bookmark(b.id)
        assert service.list_bookmarks() == []

    def test_delete_non_existent_is_silent(self, service):
        service.delete_bookmark("ghost-id")  # Should not raise.

    def test_only_target_deleted(self, service):
        b1 = service.create_bookmark("A", 1, 10, "#000000")
        b2 = service.create_bookmark("B", 11, 20, "#000000")
        service.delete_bookmark(b1.id)
        remaining = service.list_bookmarks()
        assert len(remaining) == 1
        assert remaining[0].id == b2.id


# ---------------------------------------------------------------------------
# find_at_frame
# ---------------------------------------------------------------------------

class TestFindAtFrame:
    def test_finds_bookmark_at_start(self, populated):
        results = populated.find_at_frame(1)
        assert any(b.name == "First Move" for b in results)

    def test_finds_bookmark_at_end(self, populated):
        results = populated.find_at_frame(50)
        assert any(b.name == "First Move" for b in results)

    def test_no_match_in_gap(self, populated):
        # Gap between First Move (1-50) and Jump and Spin (60-120).
        assert populated.find_at_frame(55) == []

    def test_multiple_overlapping(self, populated):
        # Create a bookmark that overlaps with Jump and Spin.
        populated.create_bookmark("Overlay", 80, 100, "#000000")
        results = populated.find_at_frame(90)
        names = {b.name for b in results}
        assert "Jump and Spin" in names
        assert "Overlay" in names


# ---------------------------------------------------------------------------
# next_bookmark / prev_bookmark
# ---------------------------------------------------------------------------

class TestNavigation:
    def test_next_returns_nearest_after_frame(self, populated):
        nxt = populated.next_bookmark(from_frame=55)
        assert nxt is not None
        assert nxt.name == "Jump and Spin"

    def test_next_returns_none_past_last(self, populated):
        assert populated.next_bookmark(from_frame=250) is None

    def test_prev_returns_nearest_before_frame(self, populated):
        # Jump and Spin ends at 120, which is the closest end before frame 125.
        prv = populated.prev_bookmark(from_frame=125)
        assert prv is not None
        assert prv.name == "Jump and Spin"

    def test_prev_returns_none_before_first(self, populated):
        assert populated.prev_bookmark(from_frame=1) is None
