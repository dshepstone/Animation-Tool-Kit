"""Tests for BookmarkController — orchestration with fake adapters."""

import pytest

from time_bookmarks.core.bookmark_service import BookmarkService
from time_bookmarks.core.controller import BookmarkController
from tests.fakes import FakeSignalSpy, FakeTimeAdapter, InMemoryPersistence


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def adapter() -> FakeTimeAdapter:
    return FakeTimeAdapter(current_frame=50, playback_range=(1, 100))


@pytest.fixture()
def persistence() -> InMemoryPersistence:
    return InMemoryPersistence()


@pytest.fixture()
def controller(adapter, persistence) -> BookmarkController:
    return BookmarkController(
        service=BookmarkService(),
        time_adapter=adapter,
        persistence=persistence,
    )


# ---------------------------------------------------------------------------
# Bookmark creation
# ---------------------------------------------------------------------------

class TestCreateBookmark:
    def test_create_at_current_range_uses_playback_range(self, controller, adapter):
        adapter.set_playback_range(10, 80)
        b = controller.create_bookmark_at_current_range("Hero Run", "#FF0000")
        assert b.start_frame == 10
        assert b.end_frame == 80

    def test_create_with_explicit_range(self, controller):
        b = controller.create_bookmark("Walk", 20, 60, "#00FF00")
        assert b.name == "Walk"
        assert b.start_frame == 20
        assert b.end_frame == 60

    def test_creation_emits_change(self, controller):
        spy = FakeSignalSpy()
        controller.on_bookmarks_changed(spy)
        controller.create_bookmark("A", 1, 10, "#000")
        assert spy.call_count == 1

    def test_empty_notes_stored_as_none(self, controller):
        b = controller.create_bookmark("A", 1, 10, "#000", notes="")
        assert b.notes is None


# ---------------------------------------------------------------------------
# Update and delete
# ---------------------------------------------------------------------------

class TestUpdateAndDelete:
    def test_update_name(self, controller):
        b = controller.create_bookmark("Old", 1, 10, "#000")
        controller.update_bookmark(b.id, name="New")
        assert controller.list_bookmarks()[0].name == "New"

    def test_update_emits_change(self, controller):
        b = controller.create_bookmark("A", 1, 10, "#000")
        spy = FakeSignalSpy()
        controller.on_bookmarks_changed(spy)
        controller.update_bookmark(b.id, name="B")
        assert spy.call_count == 1

    def test_delete_removes_bookmark(self, controller):
        b = controller.create_bookmark("A", 1, 10, "#000")
        controller.delete_bookmark(b.id)
        assert controller.list_bookmarks() == []

    def test_delete_emits_change(self, controller):
        b = controller.create_bookmark("A", 1, 10, "#000")
        spy = FakeSignalSpy()
        controller.on_bookmarks_changed(spy)
        controller.delete_bookmark(b.id)
        assert spy.call_count == 1


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------

class TestNavigation:
    def test_jump_to_bookmark_sets_frame(self, controller, adapter):
        b = controller.create_bookmark("A", 75, 100, "#000")
        controller.jump_to_bookmark(b.id)
        assert adapter.get_current_frame() == 75

    def test_navigate_next_moves_forward(self, controller, adapter):
        controller.create_bookmark("Near", 60, 80, "#000")
        controller.create_bookmark("Far", 200, 300, "#000")
        adapter.set_current_frame(50)
        nxt = controller.navigate_next()
        assert nxt is not None
        assert nxt.name == "Near"
        assert adapter.get_current_frame() == 60

    def test_navigate_next_returns_none_at_end(self, controller, adapter):
        controller.create_bookmark("Only", 10, 20, "#000")
        adapter.set_current_frame(100)
        assert controller.navigate_next() is None
        assert adapter.get_current_frame() == 100  # Frame unchanged.

    def test_navigate_prev_moves_backward(self, controller, adapter):
        controller.create_bookmark("Early", 1, 30, "#000")
        controller.create_bookmark("Mid", 50, 80, "#000")
        adapter.set_current_frame(90)
        prv = controller.navigate_prev()
        assert prv is not None
        assert prv.name == "Mid"
        assert adapter.get_current_frame() == 50

    def test_navigate_prev_returns_none_at_start(self, controller, adapter):
        controller.create_bookmark("Only", 50, 80, "#000")
        adapter.set_current_frame(1)
        assert controller.navigate_prev() is None


# ---------------------------------------------------------------------------
# Persistence — save and load
# ---------------------------------------------------------------------------

class TestPersistence:
    def test_save_then_load_restores_bookmarks(self, controller, persistence):
        b = controller.create_bookmark("Walk Cycle", 100, 140, "#4CAF50", notes="hero")
        controller.save_to_scene()

        # New controller, same persistence backend.
        controller2 = BookmarkController(
            service=BookmarkService(),
            time_adapter=FakeTimeAdapter(),
            persistence=persistence,
        )
        controller2.load_from_scene()

        bookmarks = controller2.list_bookmarks()
        assert len(bookmarks) == 1
        assert bookmarks[0].id == b.id
        assert bookmarks[0].name == "Walk Cycle"
        assert bookmarks[0].notes == "hero"

    def test_load_from_empty_persistence_gives_empty_list(self, controller):
        controller.load_from_scene()
        assert controller.list_bookmarks() == []

    def test_load_replaces_existing_bookmarks(self, controller, persistence):
        controller.create_bookmark("Original", 1, 10, "#000")
        controller.save_to_scene()
        controller.create_bookmark("Extra", 11, 20, "#000")

        controller.load_from_scene()
        names = {b.name for b in controller.list_bookmarks()}
        assert names == {"Original"}

    def test_load_emits_change(self, controller, persistence):
        controller.create_bookmark("A", 1, 10, "#000")
        controller.save_to_scene()
        spy = FakeSignalSpy()
        controller.on_bookmarks_changed(spy)
        controller.load_from_scene()
        assert spy.call_count == 1


# ---------------------------------------------------------------------------
# Visibility toggle
# ---------------------------------------------------------------------------

class TestVisibility:
    def test_initial_state_is_visible(self, controller):
        assert controller.overlay_visible is True

    def test_toggle_flips_state(self, controller):
        assert controller.toggle_visibility() is False
        assert controller.overlay_visible is False
        assert controller.toggle_visibility() is True

    def test_multiple_toggles(self, controller):
        for i in range(6):
            expected = (i % 2 == 0)  # starts True, flips each toggle
            assert controller.toggle_visibility() is not expected

    def test_toggle_emits_change(self, controller):
        spy = FakeSignalSpy()
        controller.on_bookmarks_changed(spy)
        controller.toggle_visibility()
        assert spy.call_count == 1

    def test_set_all_visible_updates_state(self, controller):
        controller.set_all_visible(False)
        assert controller.overlay_visible is False
        controller.set_all_visible(True)
        assert controller.overlay_visible is True

    def test_set_all_visible_no_op_when_unchanged(self, controller):
        spy = FakeSignalSpy()
        controller.on_bookmarks_changed(spy)
        controller.set_all_visible(True)  # already True
        assert spy.call_count == 0


class TestPerBookmarkVisibility:
    def test_new_bookmark_visible_by_default(self, controller):
        b = controller.create_bookmark("A", 1, 10, "#000")
        assert b.visible is True

    def test_set_bookmark_visible_updates_flag(self, controller):
        b = controller.create_bookmark("A", 1, 10, "#000")
        controller.set_bookmark_visible(b.id, False)
        assert controller.list_bookmarks()[0].visible is False

    def test_set_bookmark_visible_emits_change(self, controller):
        b = controller.create_bookmark("A", 1, 10, "#000")
        spy = FakeSignalSpy()
        controller.on_bookmarks_changed(spy)
        controller.set_bookmark_visible(b.id, False)
        assert spy.call_count == 1

    def test_toggle_bookmark_visible_flips_flag(self, controller):
        b = controller.create_bookmark("A", 1, 10, "#000")
        assert controller.toggle_bookmark_visible(b.id) is False
        assert controller.toggle_bookmark_visible(b.id) is True


class TestCreateAtCurrentFrame:
    def test_single_frame_bookmark_at_current_frame(self, controller, adapter):
        adapter.set_current_frame(42)
        b = controller.create_bookmark_at_current_frame("Pose", "#FFF")
        assert b.start_frame == b.end_frame == 42
        assert b.is_single_frame


# ---------------------------------------------------------------------------
# Callback registration
# ---------------------------------------------------------------------------

class TestCallbacks:
    def test_multiple_callbacks_all_called(self, controller):
        spy1, spy2 = FakeSignalSpy(), FakeSignalSpy()
        controller.on_bookmarks_changed(spy1)
        controller.on_bookmarks_changed(spy2)
        controller.create_bookmark("A", 1, 10, "#000")
        assert spy1.call_count == 1
        assert spy2.call_count == 1
