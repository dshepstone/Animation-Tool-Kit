"""Tests for BookmarkSerializer — round-trip JSON serialisation."""

import json
import pytest

from time_bookmarks.core.bookmark_serializer import BookmarkSerializer
from time_bookmarks.data.models import Bookmark


@pytest.fixture()
def sample_bookmark() -> Bookmark:
    return Bookmark(
        id="test-uuid-1234",
        name="Walk Cycle",
        start_frame=100,
        end_frame=140,
        color_hex="#4CAF50",
        notes="Hero walk",
    )


class TestToDict:
    def test_all_fields_present(self, sample_bookmark):
        d = BookmarkSerializer.to_dict(sample_bookmark)
        assert d["id"] == "test-uuid-1234"
        assert d["name"] == "Walk Cycle"
        assert d["start_frame"] == 100
        assert d["end_frame"] == 140
        assert d["color_hex"] == "#4CAF50"
        assert d["notes"] == "Hero walk"

    def test_none_notes_preserved(self):
        b = Bookmark(id="x", name="Pose", start_frame=1, end_frame=1, color_hex="#FFF")
        d = BookmarkSerializer.to_dict(b)
        assert d["notes"] is None


class TestFromDict:
    def test_round_trip(self, sample_bookmark):
        d = BookmarkSerializer.to_dict(sample_bookmark)
        restored = BookmarkSerializer.from_dict(d)
        assert restored.id == sample_bookmark.id
        assert restored.name == sample_bookmark.name
        assert restored.start_frame == sample_bookmark.start_frame
        assert restored.end_frame == sample_bookmark.end_frame
        assert restored.color_hex == sample_bookmark.color_hex
        assert restored.notes == sample_bookmark.notes

    def test_missing_required_field_raises(self):
        incomplete = {"id": "x", "name": "A", "start_frame": 1, "color_hex": "#FFF"}
        with pytest.raises(KeyError):
            BookmarkSerializer.from_dict(incomplete)

    def test_string_frame_values_coerced_to_int(self):
        d = {
            "id": "x",
            "name": "A",
            "start_frame": "10",
            "end_frame": "20",
            "color_hex": "#FFF",
        }
        b = BookmarkSerializer.from_dict(d)
        assert isinstance(b.start_frame, int)
        assert b.start_frame == 10


class TestCollectionJson:
    def test_empty_list_round_trip(self):
        json_str = BookmarkSerializer.collection_to_json([])
        result = BookmarkSerializer.collection_from_json(json_str)
        assert result == []

    def test_single_bookmark_round_trip(self, sample_bookmark):
        json_str = BookmarkSerializer.collection_to_json([sample_bookmark])
        result = BookmarkSerializer.collection_from_json(json_str)
        assert len(result) == 1
        assert result[0].id == sample_bookmark.id

    def test_multiple_bookmarks_order_preserved(self):
        bookmarks = [
            Bookmark(id=f"id-{i}", name=f"B{i}", start_frame=i * 10,
                     end_frame=i * 10 + 5, color_hex="#000")
            for i in range(5)
        ]
        json_str = BookmarkSerializer.collection_to_json(bookmarks)
        result = BookmarkSerializer.collection_from_json(json_str)
        assert [b.id for b in result] == [b.id for b in bookmarks]

    def test_unicode_name_round_trip(self):
        b = Bookmark(id="u1", name="アニメーション", start_frame=0,
                     end_frame=10, color_hex="#000")
        json_str = BookmarkSerializer.collection_to_json([b])
        result = BookmarkSerializer.collection_from_json(json_str)
        assert result[0].name == "アニメーション"

    def test_malformed_json_raises(self):
        with pytest.raises(json.JSONDecodeError):
            BookmarkSerializer.collection_from_json("{not valid json")

    def test_output_is_valid_json(self, sample_bookmark):
        json_str = BookmarkSerializer.collection_to_json([sample_bookmark])
        parsed = json.loads(json_str)
        assert isinstance(parsed, list)


class TestVisibleField:
    def test_visible_defaults_to_true_when_absent(self):
        d = {
            "id": "x",
            "name": "Legacy",
            "start_frame": 1,
            "end_frame": 10,
            "color_hex": "#FFF",
        }
        b = BookmarkSerializer.from_dict(d)
        assert b.visible is True

    def test_visible_round_trip_false(self):
        b = Bookmark(
            id="x",
            name="Hidden",
            start_frame=1,
            end_frame=10,
            color_hex="#FFF",
            visible=False,
        )
        d = BookmarkSerializer.to_dict(b)
        assert d["visible"] is False
        restored = BookmarkSerializer.from_dict(d)
        assert restored.visible is False

    def test_visible_field_in_collection_json(self):
        b = Bookmark(
            id="x", name="A", start_frame=0, end_frame=5,
            color_hex="#000", visible=False,
        )
        json_str = BookmarkSerializer.collection_to_json([b])
        result = BookmarkSerializer.collection_from_json(json_str)
        assert result[0].visible is False
