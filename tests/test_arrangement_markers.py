"""Tests for arrangement marker/cue point features."""

import json
from unittest.mock import MagicMock, patch


class TestGetCuePoints:
    """Tests for get_cue_points tool."""

    async def test_returns_cue_points(self, mock_ableton_connection):
        """Test that get_cue_points returns all cue points."""
        from MCP_Server.server import get_cue_points

        mock_ableton_connection.send_command_async.return_value = {
            "cue_points": [
                {"index": 0, "name": "Intro", "time": 0.0},
                {"index": 1, "name": "Verse", "time": 32.0},
            ],
            "count": 2,
        }

        result = await get_cue_points(MagicMock())

        mock_ableton_connection.send_command_async.assert_called_once_with("get_cue_points")
        parsed = json.loads(result)
        assert len(parsed["cue_points"]) == 2
        assert parsed["cue_points"][0]["name"] == "Intro"

    async def test_returns_empty_cue_points(self, mock_ableton_connection):
        """Test get_cue_points with no cue points."""
        from MCP_Server.server import get_cue_points

        mock_ableton_connection.send_command_async.return_value = {
            "cue_points": [],
            "count": 0,
        }

        result = await get_cue_points(MagicMock())

        parsed = json.loads(result)
        assert parsed["count"] == 0
        assert len(parsed["cue_points"]) == 0


class TestJumpToCuePoint:
    """Tests for jump_to_cue_point tool."""

    async def test_jumps_to_cue_point(self, mock_ableton_connection):
        """Test that jump_to_cue_point navigates to marker."""
        from MCP_Server.server import jump_to_cue_point

        mock_ableton_connection.send_command_async.return_value = {
            "jumped_to": "Chorus",
            "time": 64.0,
        }

        result = await jump_to_cue_point(MagicMock(), index=2)

        mock_ableton_connection.send_command_async.assert_called_once_with(
            "jump_to_cue_point", {"index": 2}
        )
        assert "Chorus" in result

    async def test_handles_invalid_index(self, mock_ableton_connection):
        """Test jump_to_cue_point with invalid index."""
        from MCP_Server.server import jump_to_cue_point

        mock_ableton_connection.send_command_async.side_effect = Exception(
            "Cue point index out of range"
        )

        result = await jump_to_cue_point(MagicMock(), index=999)

        assert "Error" in result


class TestCreateCuePoint:
    """Tests for create_cue_point tool.

    The create_cue_point tool uses MCP server orchestration to work around
    Ableton's set_or_delete_cue() behavior which operates on the current
    playhead position. The sequence is:
    1. get_cue_points - check if cue point already exists
    2. set_song_time - move playhead to target position
    3. toggle_cue_at_playhead - create the cue point
    4. set_cue_point_name - set the name (if provided)
    """

    async def test_creates_cue_point_with_name(self, mock_ableton_connection):
        """Test that create_cue_point creates a marker with name using orchestration."""
        from MCP_Server.server import create_cue_point

        # Mock responses for each step of the orchestration
        mock_ableton_connection.send_command_async.side_effect = [
            # Step 1: get_cue_points - no existing cue points
            {"cue_points": [], "count": 0},
            # Step 2: set_song_time
            {"current_song_time": 32.0},
            # Step 3: toggle_cue_at_playhead
            {"toggled": True, "action": "created", "time": 32.0},
            # Step 4: set_cue_point_name
            {"success": True, "time": 32.0, "name": "Verse"},
        ]

        with patch("MCP_Server.server.anyio.sleep"):
            result = await create_cue_point(MagicMock(), time=32.0, name="Verse")

        # Verify the orchestration sequence
        calls = mock_ableton_connection.send_command_async.call_args_list
        assert len(calls) == 4
        assert calls[0][0] == ("get_cue_points", {})
        assert calls[1][0] == ("set_song_time", {"time": 32.0})
        assert calls[2][0] == ("toggle_cue_at_playhead", {})
        assert calls[3][0] == ("set_cue_point_name", {"time": 32.0, "name": "Verse"})

        assert "Verse" in result
        assert "32.0" in result

    async def test_creates_cue_point_without_name(self, mock_ableton_connection):
        """Test that create_cue_point works without a name."""
        from MCP_Server.server import create_cue_point

        mock_ableton_connection.send_command_async.side_effect = [
            # Step 1: get_cue_points - no existing cue points
            {"cue_points": [], "count": 0},
            # Step 2: set_song_time
            {"current_song_time": 16.0},
            # Step 3: toggle_cue_at_playhead
            {"toggled": True, "action": "created", "time": 16.0},
        ]

        with patch("MCP_Server.server.anyio.sleep"):
            result = await create_cue_point(MagicMock(), time=16.0)

        # Verify no set_cue_point_name call when no name provided
        calls = mock_ableton_connection.send_command_async.call_args_list
        assert len(calls) == 3
        assert calls[2][0] == ("toggle_cue_at_playhead", {})

        assert "16.0" in result

    async def test_updates_existing_cue_point(self, mock_ableton_connection):
        """Test that create_cue_point updates existing cue point instead of toggling."""
        from MCP_Server.server import create_cue_point

        mock_ableton_connection.send_command_async.side_effect = [
            # Step 1: get_cue_points - existing cue point at target time
            {
                "cue_points": [{"index": 0, "name": "Old Name", "time": 32.0}],
                "count": 1,
            },
            # Step 2: set_cue_point_name - update the name
            {"success": True, "time": 32.0, "name": "New Name"},
        ]

        with patch("MCP_Server.server.anyio.sleep"):
            result = await create_cue_point(MagicMock(), time=32.0, name="New Name")

        # Verify only get_cue_points and set_cue_point_name were called
        calls = mock_ableton_connection.send_command_async.call_args_list
        assert len(calls) == 2
        assert calls[0][0] == ("get_cue_points", {})
        assert calls[1][0] == ("set_cue_point_name", {"time": 32.0, "name": "New Name"})

        assert "already exists" in result
        assert "updated name" in result

    async def test_existing_cue_point_no_name_update(self, mock_ableton_connection):
        """Test message when cue point exists but no name provided."""
        from MCP_Server.server import create_cue_point

        mock_ableton_connection.send_command_async.side_effect = [
            # Step 1: get_cue_points - existing cue point at target time
            {
                "cue_points": [{"index": 0, "name": "Existing", "time": 32.0}],
                "count": 1,
            },
        ]

        with patch("MCP_Server.server.anyio.sleep"):
            result = await create_cue_point(MagicMock(), time=32.0)

        # Verify only get_cue_points was called (no toggle or rename)
        calls = mock_ableton_connection.send_command_async.call_args_list
        assert len(calls) == 1

        assert "already exists" in result

    async def test_handles_error(self, mock_ableton_connection):
        """Test error handling in create_cue_point."""
        from MCP_Server.server import create_cue_point

        mock_ableton_connection.send_command_async.side_effect = Exception("Connection lost")

        result = await create_cue_point(MagicMock(), time=32.0, name="Test")

        assert "Error" in result

    async def test_creates_cue_at_beat_zero(self, mock_ableton_connection):
        """Test creating cue point at beat 0 (regression test for timing issue)."""
        from MCP_Server.server import create_cue_point

        mock_ableton_connection.send_command_async.side_effect = [
            {"cue_points": [], "count": 0},
            {"current_song_time": 0.0},
            {"toggled": True, "action": "created", "time": 0.0},
            {"success": True, "time": 0.0, "name": "Intro"},
        ]

        with patch("MCP_Server.server.anyio.sleep"):
            result = await create_cue_point(MagicMock(), time=0.0, name="Intro")

        # Verify set_song_time was called with time=0.0
        calls = mock_ableton_connection.send_command_async.call_args_list
        assert calls[1][0] == ("set_song_time", {"time": 0.0})

        assert "Intro" in result
        assert "0.0" in result


class TestDeleteCuePoint:
    """Tests for delete_cue_point tool.

    The delete_cue_point tool uses MCP server orchestration to work around
    Ableton's set_or_delete_cue() behavior. The sequence is:
    1. get_cue_points - find the cue point by index to get its time
    2. set_song_time - move playhead to cue point position
    3. toggle_cue_at_playhead - delete the cue point
    """

    async def test_deletes_cue_point(self, mock_ableton_connection):
        """Test that delete_cue_point removes a marker using orchestration."""
        from MCP_Server.server import delete_cue_point

        mock_ableton_connection.send_command_async.side_effect = [
            # Step 1: get_cue_points - returns list with target cue point
            {
                "cue_points": [
                    {"index": 0, "name": "Intro", "time": 0.0},
                    {"index": 1, "name": "Verse", "time": 32.0},
                    {"index": 2, "name": "Chorus", "time": 64.0},
                    {"index": 3, "name": "Bridge", "time": 96.0},
                ],
                "count": 4,
            },
            # Step 2: set_song_time
            {"current_song_time": 96.0},
            # Step 3: toggle_cue_at_playhead
            {"toggled": True, "action": "deleted", "time": 96.0},
        ]

        with patch("MCP_Server.server.anyio.sleep"):
            result = await delete_cue_point(MagicMock(), index=3)

        # Verify the orchestration sequence
        calls = mock_ableton_connection.send_command_async.call_args_list
        assert len(calls) == 3
        assert calls[0][0] == ("get_cue_points", {})
        assert calls[1][0] == ("set_song_time", {"time": 96.0})
        assert calls[2][0] == ("toggle_cue_at_playhead", {})

        assert "Bridge" in result
        assert "Deleted" in result

    async def test_handles_invalid_index(self, mock_ableton_connection):
        """Test delete_cue_point with invalid index (out of range)."""
        from MCP_Server.server import delete_cue_point

        mock_ableton_connection.send_command_async.side_effect = [
            # get_cue_points returns only 2 cue points
            {
                "cue_points": [
                    {"index": 0, "name": "Intro", "time": 0.0},
                    {"index": 1, "name": "Verse", "time": 32.0},
                ],
                "count": 2,
            },
        ]

        with patch("MCP_Server.server.anyio.sleep"):
            result = await delete_cue_point(MagicMock(), index=5)

        # Should return error without calling set_song_time or toggle
        calls = mock_ableton_connection.send_command_async.call_args_list
        assert len(calls) == 1

        assert "Error" in result
        assert "out of range" in result

    async def test_handles_negative_index(self, mock_ableton_connection):
        """Test delete_cue_point with negative index."""
        from MCP_Server.server import delete_cue_point

        mock_ableton_connection.send_command_async.side_effect = [
            {
                "cue_points": [{"index": 0, "name": "Intro", "time": 0.0}],
                "count": 1,
            },
        ]

        with patch("MCP_Server.server.anyio.sleep"):
            result = await delete_cue_point(MagicMock(), index=-1)

        assert "Error" in result
        assert "out of range" in result

    async def test_handles_connection_error(self, mock_ableton_connection):
        """Test delete_cue_point with connection error."""
        from MCP_Server.server import delete_cue_point

        mock_ableton_connection.send_command_async.side_effect = Exception(
            "Connection lost"
        )

        result = await delete_cue_point(MagicMock(), index=0)

        assert "Error" in result

    async def test_deletes_first_cue_point(self, mock_ableton_connection):
        """Test deleting the first cue point (regression test for timing issue)."""
        from MCP_Server.server import delete_cue_point

        mock_ableton_connection.send_command_async.side_effect = [
            {
                "cue_points": [
                    {"index": 0, "name": "Start", "time": 0.0},
                    {"index": 1, "name": "Middle", "time": 16.0},
                ],
                "count": 2,
            },
            {"current_song_time": 0.0},
            {"toggled": True, "action": "deleted", "time": 0.0},
        ]

        with patch("MCP_Server.server.anyio.sleep"):
            result = await delete_cue_point(MagicMock(), index=0)

        calls = mock_ableton_connection.send_command_async.call_args_list
        assert calls[1][0] == ("set_song_time", {"time": 0.0})

        assert "Start" in result
        assert "0.0" in result


class TestJumpToNextCuePoint:
    """Tests for jump_to_next_cue_point tool."""

    async def test_jumps_to_next_cue_point(self, mock_ableton_connection):
        """Test that jump_to_next_cue_point navigates forward."""
        from MCP_Server.server import jump_to_next_cue_point

        mock_ableton_connection.send_command_async.return_value = {
            "jumped": True,
            "name": "Chorus",
            "time": 64.0,
        }

        result = await jump_to_next_cue_point(MagicMock())

        mock_ableton_connection.send_command_async.assert_called_once_with("jump_to_next_cue_point")
        assert "Chorus" in result
        assert "64.0" in result

    async def test_no_next_cue_point(self, mock_ableton_connection):
        """Test message when no next cue point exists."""
        from MCP_Server.server import jump_to_next_cue_point

        mock_ableton_connection.send_command_async.return_value = {
            "jumped": False,
            "message": "No cue point after current position",
        }

        result = await jump_to_next_cue_point(MagicMock())

        assert "No cue point after current position" in result


class TestJumpToPrevCuePoint:
    """Tests for jump_to_prev_cue_point tool."""

    async def test_jumps_to_prev_cue_point(self, mock_ableton_connection):
        """Test that jump_to_prev_cue_point navigates backward."""
        from MCP_Server.server import jump_to_prev_cue_point

        mock_ableton_connection.send_command_async.return_value = {
            "jumped": True,
            "name": "Intro",
            "time": 0.0,
        }

        result = await jump_to_prev_cue_point(MagicMock())

        mock_ableton_connection.send_command_async.assert_called_once_with("jump_to_prev_cue_point")
        assert "Intro" in result

    async def test_no_prev_cue_point(self, mock_ableton_connection):
        """Test message when no previous cue point exists."""
        from MCP_Server.server import jump_to_prev_cue_point

        mock_ableton_connection.send_command_async.return_value = {
            "jumped": False,
            "message": "No cue point before current position",
        }

        result = await jump_to_prev_cue_point(MagicMock())

        assert "No cue point before current position" in result
