"""Tests for recording control features."""

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


class TestSetRecordMode:
    """Tests for set_record_mode tool."""

    async def test_enables_record_mode(self, mock_ableton_connection):
        """Test that set_record_mode enables recording."""
        from MCP_Server.server import set_record_mode

        mock_ableton_connection.send_command_async.return_value = {
            "record_mode": True,
        }

        result = await set_record_mode(MagicMock(), enabled=True)

        mock_ableton_connection.send_command_async.assert_called_once_with(
            "set_record_mode", {"enabled": True}
        )
        assert "enabled" in result

    async def test_disables_record_mode(self, mock_ableton_connection):
        """Test that set_record_mode disables recording."""
        from MCP_Server.server import set_record_mode

        mock_ableton_connection.send_command_async.return_value = {
            "record_mode": False,
        }

        result = await set_record_mode(MagicMock(), enabled=False)

        mock_ableton_connection.send_command_async.assert_called_once_with(
            "set_record_mode", {"enabled": False}
        )
        assert "disabled" in result


class TestSetArrangementOverdub:
    """Tests for set_arrangement_overdub tool."""

    async def test_enables_arrangement_overdub(self, mock_ableton_connection):
        """Test that set_arrangement_overdub enables overdub."""
        from MCP_Server.server import set_arrangement_overdub

        mock_ableton_connection.send_command_async.return_value = {
            "arrangement_overdub": True,
        }

        result = await set_arrangement_overdub(MagicMock(), enabled=True)

        mock_ableton_connection.send_command_async.assert_called_once_with(
            "set_arrangement_overdub", {"enabled": True}
        )
        assert "enabled" in result

    async def test_disables_arrangement_overdub(self, mock_ableton_connection):
        """Test that set_arrangement_overdub disables overdub."""
        from MCP_Server.server import set_arrangement_overdub

        mock_ableton_connection.send_command_async.return_value = {
            "arrangement_overdub": False,
        }

        result = await set_arrangement_overdub(MagicMock(), enabled=False)

        mock_ableton_connection.send_command_async.assert_called_once_with(
            "set_arrangement_overdub", {"enabled": False}
        )
        assert "disabled" in result
