"""Tests for arrangement clip features."""

import json
from unittest.mock import MagicMock


class TestGetArrangementClips:
    """Tests for get_arrangement_clips tool."""

    async def test_returns_clips_from_all_tracks(self, mock_ableton_connection):
        """Test that get_arrangement_clips returns clips from all tracks."""
        from MCP_Server.server import get_arrangement_clips

        mock_ableton_connection.send_command_async.return_value = {
            "tracks": [
                {
                    "track_index": 0,
                    "track_name": "Drums",
                    "clips": [
                        {
                            "name": "Beat 1",
                            "start_time": 0.0,
                            "end_time": 16.0,
                            "length": 16.0,
                            "is_midi_clip": True,
                            "is_audio_clip": False,
                        }
                    ],
                    "clip_count": 1,
                },
                {
                    "track_index": 1,
                    "track_name": "Bass",
                    "clips": [
                        {
                            "name": "Bass Line",
                            "start_time": 0.0,
                            "end_time": 32.0,
                            "length": 32.0,
                            "is_midi_clip": True,
                            "is_audio_clip": False,
                        }
                    ],
                    "clip_count": 1,
                },
            ],
            "total_clips": 2,
        }

        result = await get_arrangement_clips(MagicMock())

        mock_ableton_connection.send_command_async.assert_called_once_with(
            "get_arrangement_clips", {}
        )
        parsed = json.loads(result)
        assert parsed["total_clips"] == 2
        assert len(parsed["tracks"]) == 2
        assert parsed["tracks"][0]["track_name"] == "Drums"

    async def test_returns_clips_from_specific_track(self, mock_ableton_connection):
        """Test that get_arrangement_clips filters by track index."""
        from MCP_Server.server import get_arrangement_clips

        mock_ableton_connection.send_command_async.return_value = {
            "tracks": [
                {
                    "track_index": 2,
                    "track_name": "Synth",
                    "clips": [
                        {
                            "name": "Pad",
                            "start_time": 16.0,
                            "end_time": 48.0,
                            "length": 32.0,
                            "is_midi_clip": True,
                            "is_audio_clip": False,
                        }
                    ],
                    "clip_count": 1,
                }
            ],
            "total_clips": 1,
        }

        result = await get_arrangement_clips(MagicMock(), track_index=2)

        mock_ableton_connection.send_command_async.assert_called_once_with(
            "get_arrangement_clips", {"track_index": 2}
        )
        parsed = json.loads(result)
        assert parsed["total_clips"] == 1
        assert parsed["tracks"][0]["track_index"] == 2

    async def test_returns_empty_when_no_clips(self, mock_ableton_connection):
        """Test that get_arrangement_clips handles empty arrangement."""
        from MCP_Server.server import get_arrangement_clips

        mock_ableton_connection.send_command_async.return_value = {
            "tracks": [
                {
                    "track_index": 0,
                    "track_name": "Empty Track",
                    "clips": [],
                    "clip_count": 0,
                }
            ],
            "total_clips": 0,
        }

        result = await get_arrangement_clips(MagicMock())

        parsed = json.loads(result)
        assert parsed["total_clips"] == 0
        assert parsed["tracks"][0]["clip_count"] == 0


    async def test_handles_error(self, mock_ableton_connection):
        """Test error handling for get_arrangement_clips."""
        from MCP_Server.server import get_arrangement_clips

        mock_ableton_connection.send_command_async.side_effect = Exception("Connection lost")

        result = await get_arrangement_clips(MagicMock())

        assert "Error" in result


class TestDuplicateClipToArrangement:
    """Tests for duplicate_clip_to_arrangement tool."""

    async def test_duplicates_clip_to_arrangement(self, mock_ableton_connection):
        """Test that duplicate_clip_to_arrangement copies clip to timeline."""
        from MCP_Server.server import duplicate_clip_to_arrangement

        mock_ableton_connection.send_command_async.return_value = {
            "duplicated": True,
            "clip_name": "My Clip",
            "destination_time": 32.0,
            "clip_length": 8.0,
            "track_name": "Lead",
        }

        result = await duplicate_clip_to_arrangement(
            MagicMock(), track_index=0, clip_index=1, time=32.0
        )

        mock_ableton_connection.send_command_async.assert_called_once_with(
            "duplicate_clip_to_arrangement",
            {"track_index": 0, "clip_index": 1, "time": 32.0},
        )
        assert "My Clip" in result
        assert "32.0" in result
        assert "Lead" in result

    async def test_handles_invalid_track_index(self, mock_ableton_connection):
        """Test duplicate_clip_to_arrangement with invalid track index."""
        from MCP_Server.server import duplicate_clip_to_arrangement

        mock_ableton_connection.send_command_async.side_effect = Exception(
            "Track index out of range"
        )

        result = await duplicate_clip_to_arrangement(
            MagicMock(), track_index=999, clip_index=0, time=0.0
        )

        assert "Error" in result

    async def test_handles_empty_clip_slot(self, mock_ableton_connection):
        """Test duplicate_clip_to_arrangement with empty clip slot."""
        from MCP_Server.server import duplicate_clip_to_arrangement

        mock_ableton_connection.send_command_async.side_effect = Exception("No clip in slot")

        result = await duplicate_clip_to_arrangement(
            MagicMock(), track_index=0, clip_index=5, time=0.0
        )

        assert "Error" in result
