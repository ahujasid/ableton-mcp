"""Tests for arrangement view navigation features."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_ableton_connection():
    """Create a mock Ableton connection."""
    with patch("MCP_Server.server.get_ableton_connection") as mock_get_conn:
        mock_conn = MagicMock()
        mock_conn.send_command_async = AsyncMock()
        mock_get_conn.return_value = mock_conn
        yield mock_conn


class TestGetArrangementInfo:
    """Tests for get_arrangement_info tool."""

    async def test_returns_arrangement_state(self, mock_ableton_connection):
        """Test that get_arrangement_info returns arrangement state."""
        from MCP_Server.server import get_arrangement_info

        mock_ableton_connection.send_command_async.return_value = {
            "current_song_time": 32.0,
            "loop_start": 16.0,
            "loop_length": 16.0,
            "loop_enabled": True,
            "is_playing": False,
            "record_mode": False,
            "arrangement_overdub": False,
            "signature_numerator": 4,
            "signature_denominator": 4,
        }

        result = await get_arrangement_info(MagicMock())

        mock_ableton_connection.send_command_async.assert_called_once_with("get_arrangement_info")
        parsed = json.loads(result)
        assert parsed["current_song_time"] == 32.0
        assert parsed["loop_enabled"] is True

    async def test_handles_error(self, mock_ableton_connection):
        """Test error handling."""
        from MCP_Server.server import get_arrangement_info

        mock_ableton_connection.send_command_async.side_effect = Exception("Connection lost")

        result = await get_arrangement_info(MagicMock())

        assert "Error" in result


class TestSetSongTime:
    """Tests for set_song_time tool."""

    async def test_sets_playhead_position(self, mock_ableton_connection):
        """Test that set_song_time moves playhead."""
        from MCP_Server.server import set_song_time

        mock_ableton_connection.send_command_async.return_value = {"current_song_time": 64.0}

        result = await set_song_time(MagicMock(), time=64.0)

        mock_ableton_connection.send_command_async.assert_called_once_with(
            "set_song_time", {"time": 64.0}
        )
        assert "64.0" in result

    async def test_handles_error(self, mock_ableton_connection):
        """Test error handling."""
        from MCP_Server.server import set_song_time

        mock_ableton_connection.send_command_async.side_effect = Exception("Invalid time")

        result = await set_song_time(MagicMock(), time=-5.0)

        assert "Error" in result


class TestSetLoopRegion:
    """Tests for set_loop_region tool."""

    async def test_sets_loop_region(self, mock_ableton_connection):
        """Test that set_loop_region sets loop start and length."""
        from MCP_Server.server import set_loop_region

        mock_ableton_connection.send_command_async.return_value = {
            "loop_start": 16.0,
            "loop_length": 16.0,
        }

        result = await set_loop_region(MagicMock(), start=16.0, length=16.0)

        mock_ableton_connection.send_command_async.assert_called_once_with(
            "set_loop_region", {"start": 16.0, "length": 16.0}
        )
        assert "16.0" in result


class TestSetLoopEnabled:
    """Tests for set_loop_enabled tool."""

    async def test_enables_loop(self, mock_ableton_connection):
        """Test that set_loop_enabled enables/disables loop."""
        from MCP_Server.server import set_loop_enabled

        mock_ableton_connection.send_command_async.return_value = {"loop_enabled": True}

        result = await set_loop_enabled(MagicMock(), enabled=True)

        mock_ableton_connection.send_command_async.assert_called_once_with(
            "set_loop_enabled", {"enabled": True}
        )
        assert "enabled" in result.lower()


class TestContinuePlaying:
    """Tests for continue_playing tool."""

    async def test_continues_playback(self, mock_ableton_connection):
        """Test that continue_playing resumes from current position."""
        from MCP_Server.server import continue_playing

        mock_ableton_connection.send_command_async.return_value = {
            "is_playing": True,
            "current_song_time": 32.0,
        }

        result = await continue_playing(MagicMock())

        mock_ableton_connection.send_command_async.assert_called_once_with("continue_playing")
        assert "32.0" in result or "playing" in result.lower()


class TestJumpByBars:
    """Tests for jump_by_bars tool."""

    async def test_jumps_forward(self, mock_ableton_connection):
        """Test that jump_by_bars moves playhead by bars."""
        from MCP_Server.server import jump_by_bars

        mock_ableton_connection.send_command_async.return_value = {
            "current_song_time": 48.0,
            "bars_jumped": 4,
        }

        result = await jump_by_bars(MagicMock(), bars=4)

        mock_ableton_connection.send_command_async.assert_called_once_with(
            "jump_by_bars", {"bars": 4}
        )
        assert "4" in result

    async def test_jumps_backward(self, mock_ableton_connection):
        """Test that negative bars jumps backward."""
        from MCP_Server.server import jump_by_bars

        mock_ableton_connection.send_command_async.return_value = {
            "current_song_time": 16.0,
            "bars_jumped": -4,
        }

        result = await jump_by_bars(MagicMock(), bars=-4)

        assert "-4" in result or "backward" in result.lower()
