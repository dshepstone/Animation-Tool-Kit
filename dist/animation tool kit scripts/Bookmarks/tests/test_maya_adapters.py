"""Unit tests for Maya adapter classes.

``maya.cmds`` is mocked via ``sys.modules`` patching.  Because all Maya
calls are deferred inside method bodies (never at import time), the adapters
can be imported and exercised without a running Maya session.
"""

from __future__ import annotations

import json
import sys
from types import ModuleType
from unittest.mock import MagicMock, call, patch

import pytest

from time_bookmarks.data.models import Bookmark


# ---------------------------------------------------------------------------
# Shared fixture — injects a fake maya.cmds for every test in this module
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_cmds():
    """Return a MagicMock wired into sys.modules as maya.cmds."""
    fake_cmds = MagicMock()

    fake_maya = ModuleType("maya")
    fake_maya.cmds = fake_cmds  # type: ignore[attr-defined]

    with patch.dict(sys.modules, {"maya": fake_maya, "maya.cmds": fake_cmds}):
        yield fake_cmds


# ---------------------------------------------------------------------------
# MayaTimeAdapter
# ---------------------------------------------------------------------------

class TestMayaTimeAdapter:
    @pytest.fixture()
    def adapter(self, mock_cmds):
        from time_bookmarks.maya.adapter import MayaTimeAdapter
        return MayaTimeAdapter()

    def test_get_current_frame_calls_current_time(self, adapter, mock_cmds):
        mock_cmds.currentTime.return_value = 42.0
        result = adapter.get_current_frame()
        mock_cmds.currentTime.assert_called_once_with(q=True)
        assert result == 42

    def test_get_current_frame_returns_int(self, adapter, mock_cmds):
        mock_cmds.currentTime.return_value = 73.9  # Maya can return a float
        assert isinstance(adapter.get_current_frame(), int)

    def test_set_current_frame_calls_current_time(self, adapter, mock_cmds):
        adapter.set_current_frame(100)
        mock_cmds.currentTime.assert_called_once_with(100)

    def test_get_playback_range_returns_tuple(self, adapter, mock_cmds):
        mock_cmds.playbackOptions.side_effect = lambda **kw: (
            1.0 if kw.get("min") else 200.0
        )
        start, end = adapter.get_playback_range()
        assert start == 1
        assert end == 200

    def test_get_playback_range_queries_min_and_max(self, adapter, mock_cmds):
        mock_cmds.playbackOptions.return_value = 1.0
        adapter.get_playback_range()
        calls = mock_cmds.playbackOptions.call_args_list
        assert any(c == call(q=True, min=True) for c in calls)
        assert any(c == call(q=True, max=True) for c in calls)

    def test_get_playback_range_returns_ints(self, adapter, mock_cmds):
        mock_cmds.playbackOptions.return_value = 1.5
        start, end = adapter.get_playback_range()
        assert isinstance(start, int)
        assert isinstance(end, int)

    def test_set_playback_range_calls_playback_options(self, adapter, mock_cmds):
        adapter.set_playback_range(10, 250)
        mock_cmds.playbackOptions.assert_called_once_with(min=10, max=250)

    def test_implements_protocol(self, adapter):
        from time_bookmarks.core.protocols import TimeAdapterProtocol
        assert isinstance(adapter, TimeAdapterProtocol)


# ---------------------------------------------------------------------------
# MayaScenePersistence
# ---------------------------------------------------------------------------

class TestMayaScenePersistence:
    @pytest.fixture()
    def persistence(self, mock_cmds):
        from time_bookmarks.maya.persistence import MayaScenePersistence
        return MayaScenePersistence()

    @pytest.fixture()
    def sample_bookmarks(self):
        return [
            Bookmark(
                id="test-id-1",
                name="Walk Cycle",
                start_frame=1,
                end_frame=50,
                color_hex="#4CAF50",
                notes="hero walk",
            ),
            Bookmark(
                id="test-id-2",
                name="Jump",
                start_frame=60,
                end_frame=80,
                color_hex="#E57373",
            ),
        ]

    # ---- save() ----------------------------------------------------------

    def test_save_calls_file_info_with_correct_key(
        self, persistence, mock_cmds, sample_bookmarks
    ):
        persistence.save(sample_bookmarks)
        args = mock_cmds.fileInfo.call_args
        assert args[0][0] == "time_bookmarks_v1"

    def test_save_stores_valid_json(
        self, persistence, mock_cmds, sample_bookmarks
    ):
        persistence.save(sample_bookmarks)
        stored_str = mock_cmds.fileInfo.call_args[0][1]
        parsed = json.loads(stored_str)
        assert isinstance(parsed, list)
        assert len(parsed) == 2

    def test_save_preserves_all_fields(
        self, persistence, mock_cmds, sample_bookmarks
    ):
        persistence.save(sample_bookmarks)
        stored_str = mock_cmds.fileInfo.call_args[0][1]
        data = json.loads(stored_str)
        assert data[0]["id"] == "test-id-1"
        assert data[0]["name"] == "Walk Cycle"
        assert data[0]["start_frame"] == 1
        assert data[0]["end_frame"] == 50
        assert data[0]["color_hex"] == "#4CAF50"
        assert data[0]["notes"] == "hero walk"

    def test_save_empty_list(self, persistence, mock_cmds):
        persistence.save([])
        stored_str = mock_cmds.fileInfo.call_args[0][1]
        assert json.loads(stored_str) == []

    # ---- load() ----------------------------------------------------------

    def test_load_returns_empty_when_key_absent(self, persistence, mock_cmds):
        mock_cmds.fileInfo.return_value = []
        result = persistence.load()
        assert result == []

    def test_load_deserialises_stored_bookmarks(
        self, persistence, mock_cmds, sample_bookmarks
    ):
        from time_bookmarks.core.bookmark_serializer import BookmarkSerializer
        json_str = BookmarkSerializer.collection_to_json(sample_bookmarks)
        mock_cmds.fileInfo.return_value = [json_str]

        result = persistence.load()
        assert len(result) == 2
        assert result[0].id == "test-id-1"
        assert result[0].name == "Walk Cycle"
        assert result[1].id == "test-id-2"

    def test_load_queries_correct_key(self, persistence, mock_cmds):
        mock_cmds.fileInfo.return_value = []
        persistence.load()
        mock_cmds.fileInfo.assert_called_once_with("time_bookmarks_v1", q=True)

    def test_load_returns_empty_on_malformed_json(
        self, persistence, mock_cmds, caplog
    ):
        mock_cmds.fileInfo.return_value = ["{not valid json"]
        import logging
        with caplog.at_level(logging.WARNING):
            result = persistence.load()
        assert result == []
        assert any("corrupt" in r.message.lower() or "parse" in r.message.lower()
                   for r in caplog.records)

    def test_load_handles_missing_required_field(
        self, persistence, mock_cmds, caplog
    ):
        # JSON is valid but missing required Bookmark fields.
        bad_data = json.dumps([{"name": "Oops"}])
        mock_cmds.fileInfo.return_value = [bad_data]
        import logging
        with caplog.at_level(logging.WARNING):
            result = persistence.load()
        assert result == []

    def test_round_trip(self, persistence, mock_cmds, sample_bookmarks):
        """save() followed by load() returns equivalent bookmarks."""
        # Capture what save() passed to fileInfo.
        saved_value: list[str] = []

        def capture_save(key, value):
            saved_value.append(value)

        def return_saved(key, q):
            return saved_value if saved_value else []

        mock_cmds.fileInfo.side_effect = lambda *a, **kw: (
            capture_save(*a) if not kw.get("q") else return_saved(*a, **kw)
        )

        persistence.save(sample_bookmarks)
        restored = persistence.load()

        assert len(restored) == len(sample_bookmarks)
        for orig, rest in zip(sample_bookmarks, restored):
            assert rest.id == orig.id
            assert rest.name == orig.name
            assert rest.start_frame == orig.start_frame
            assert rest.end_frame == orig.end_frame

    def test_implements_protocol(self, persistence):
        from time_bookmarks.core.protocols import PersistenceProtocol
        assert isinstance(persistence, PersistenceProtocol)


# ---------------------------------------------------------------------------
# MayaQtBridge — import-level smoke test (no Maya runtime needed)
# ---------------------------------------------------------------------------

class TestMayaQtBridgeImport:
    def test_module_imports_without_maya(self):
        """qt_bridge.py must be importable even when maya is not installed."""
        # The module should already be importable (no top-level maya import).
        import importlib
        mod = importlib.import_module("time_bookmarks.maya.qt_bridge")
        assert hasattr(mod, "MayaQtBridge")

    def test_get_qt_binding_returns_string(self, mock_cmds):
        from time_bookmarks.maya.qt_bridge import MayaQtBridge
        result = MayaQtBridge.get_qt_binding()
        assert result in ("PySide6", "PySide2")
