"""Tests for arrangement marker/cue point features."""

import json
from unittest.mock import MagicMock


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
    """Tests for create_cue_point tool."""

    async def test_creates_cue_point_with_name(self, mock_ableton_connection):
        """Test that create_cue_point creates a marker with name."""
        from MCP_Server.server import create_cue_point

        mock_ableton_connection.send_command_async.return_value = {
            "created": True,
            "time": 32.0,
            "name": "Verse",
        }

        result = await create_cue_point(MagicMock(), time=32.0, name="Verse")

        mock_ableton_connection.send_command_async.assert_called_once_with(
            "create_cue_point", {"time": 32.0, "name": "Verse"}
        )
        assert "Verse" in result
        assert "32.0" in result

    async def test_creates_cue_point_without_name(self, mock_ableton_connection):
        """Test that create_cue_point works without a name."""
        from MCP_Server.server import create_cue_point

        mock_ableton_connection.send_command_async.return_value = {
            "created": True,
            "time": 16.0,
            "name": "",
        }

        result = await create_cue_point(MagicMock(), time=16.0)

        mock_ableton_connection.send_command_async.assert_called_once_with(
            "create_cue_point", {"time": 16.0, "name": ""}
        )
        assert "16.0" in result

    async def test_updates_existing_cue_point(self, mock_ableton_connection):
        """Test that create_cue_point updates existing cue point instead of toggling."""
        from MCP_Server.server import create_cue_point

        mock_ableton_connection.send_command_async.return_value = {
            "created": False,
            "updated": True,
            "time": 32.0,
            "name": "New Name",
            "message": "Cue point already exists at this time; updated name",
        }

        result = await create_cue_point(MagicMock(), time=32.0, name="New Name")

        mock_ableton_connection.send_command_async.assert_called_once_with(
            "create_cue_point", {"time": 32.0, "name": "New Name"}
        )
        assert "already exists" in result
        assert "updated name" in result

    async def test_existing_cue_point_no_name_update(self, mock_ableton_connection):
        """Test message when cue point exists but no name provided."""
        from MCP_Server.server import create_cue_point

        mock_ableton_connection.send_command_async.return_value = {
            "created": False,
            "updated": True,
            "time": 32.0,
            "name": "Existing",
            "message": "Cue point already exists at this time",
        }

        result = await create_cue_point(MagicMock(), time=32.0)

        assert "already exists" in result

    async def test_handles_error(self, mock_ableton_connection):
        """Test error handling in create_cue_point."""
        from MCP_Server.server import create_cue_point

        mock_ableton_connection.send_command_async.side_effect = Exception("Connection lost")

        result = await create_cue_point(MagicMock(), time=32.0, name="Test")

        assert "Error" in result


class TestDeleteCuePoint:
    """Tests for delete_cue_point tool."""

    async def test_deletes_cue_point(self, mock_ableton_connection):
        """Test that delete_cue_point removes a marker."""
        from MCP_Server.server import delete_cue_point

        mock_ableton_connection.send_command_async.return_value = {
            "deleted": True,
            "name": "Bridge",
            "time": 96.0,
        }

        result = await delete_cue_point(MagicMock(), index=3)

        mock_ableton_connection.send_command_async.assert_called_once_with(
            "delete_cue_point", {"index": 3}
        )
        assert "Bridge" in result
        assert "Deleted" in result

    async def test_handles_invalid_index(self, mock_ableton_connection):
        """Test delete_cue_point with invalid index."""
        from MCP_Server.server import delete_cue_point

        mock_ableton_connection.send_command_async.side_effect = Exception(
            "Cue point index out of range"
        )

        result = await delete_cue_point(MagicMock(), index=-1)

        assert "Error" in result


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
