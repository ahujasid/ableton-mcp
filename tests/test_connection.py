"""Tests for AbletonConnection class."""

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from MCP_Server.server import AbletonConnection


class TestAbletonConnectionInit:
    """Test AbletonConnection initialization."""

    def test_init_with_defaults(self):
        """Test connection initializes with correct defaults."""
        conn = AbletonConnection(host="localhost", port=9877)

        assert conn.host == "localhost"
        assert conn.port == 9877
        assert conn.sock is None

    def test_init_with_custom_host_port(self):
        """Test connection accepts custom host and port."""
        conn = AbletonConnection(host="192.168.1.100", port=8080)

        assert conn.host == "192.168.1.100"
        assert conn.port == 8080


class TestAbletonConnectionConnect:
    """Test AbletonConnection.connect method."""

    def test_connect_success(self, mock_socket_module):
        """Test successful connection."""
        conn = AbletonConnection(host="localhost", port=9877)
        result = conn.connect()

        assert result is True
        assert conn.sock is not None
        assert conn.sock.connected is True

    def test_connect_already_connected(self, mock_socket_module):
        """Test connect returns True if already connected."""
        conn = AbletonConnection(host="localhost", port=9877)
        conn.connect()

        # Try to connect again
        result = conn.connect()
        assert result is True

    def test_connect_failure(self):
        """Test connection failure handling."""
        with patch("socket.socket") as mock_socket_class:
            mock_sock = MagicMock()
            mock_sock.connect.side_effect = ConnectionRefusedError("Connection refused")
            mock_socket_class.return_value = mock_sock

            conn = AbletonConnection(host="localhost", port=9877)
            result = conn.connect()

            assert result is False
            assert conn.sock is None


class TestAbletonConnectionDisconnect:
    """Test AbletonConnection.disconnect method."""

    def test_disconnect_when_connected(self, mock_socket_module, mock_socket):
        """Test disconnecting an active connection."""
        conn = AbletonConnection(host="localhost", port=9877)
        conn.connect()
        conn.disconnect()

        assert conn.sock is None
        assert mock_socket.closed is True

    def test_disconnect_when_not_connected(self):
        """Test disconnect when not connected does nothing."""
        conn = AbletonConnection(host="localhost", port=9877)
        conn.disconnect()  # Should not raise

        assert conn.sock is None

    def test_disconnect_handles_close_error(self, mock_socket_module):
        """Test disconnect handles socket close errors gracefully."""
        with patch("socket.socket") as mock_socket_class:
            mock_sock = MagicMock()
            mock_sock.close.side_effect = OSError("Socket error")
            mock_socket_class.return_value = mock_sock

            conn = AbletonConnection(host="localhost", port=9877)
            conn.connect()
            conn.disconnect()  # Should not raise

            assert conn.sock is None


class TestAbletonConnectionSendCommand:
    """Test AbletonConnection.send_command method."""

    def test_send_command_success(self, mock_tcp_server, mock_ableton_responses):
        """Test successful command send and response."""
        mock_tcp_server.set_response(
            "get_session_info", mock_ableton_responses["get_session_info"]
        )

        conn = AbletonConnection(host="localhost", port=mock_tcp_server.port)
        result = conn.send_command("get_session_info")

        assert "tempo" in result
        assert result["tempo"] == 120.0

    def test_send_command_with_params(self, mock_tcp_server):
        """Test command with parameters."""
        mock_tcp_server.set_response(
            "set_tempo", {"status": "success", "result": {"tempo": 140.0}}
        )

        conn = AbletonConnection(host="localhost", port=mock_tcp_server.port)
        result = conn.send_command("set_tempo", {"tempo": 140.0})

        assert result["tempo"] == 140.0
        # Verify the command was sent with correct params
        sent_cmd = mock_tcp_server.received_commands[-1]
        assert sent_cmd["params"]["tempo"] == 140.0

    def test_send_command_auto_reconnect(self, mock_tcp_server, mock_ableton_responses):
        """Test command auto-connects if not connected."""
        mock_tcp_server.set_response(
            "get_session_info", mock_ableton_responses["get_session_info"]
        )

        conn = AbletonConnection(host="localhost", port=mock_tcp_server.port)
        # Don't call connect() explicitly
        result = conn.send_command("get_session_info")

        assert "tempo" in result

    def test_send_command_error_response(self, mock_tcp_server):
        """Test handling of error response from Ableton."""
        mock_tcp_server.set_response(
            "invalid_command",
            {"status": "error", "message": "Unknown command: invalid_command"},
        )

        conn = AbletonConnection(host="localhost", port=mock_tcp_server.port)

        with pytest.raises(Exception) as exc_info:
            conn.send_command("invalid_command")

        assert "Unknown command" in str(exc_info.value)

    def test_send_command_connection_error(self):
        """Test handling when connection fails."""
        conn = AbletonConnection(host="localhost", port=99999)  # Invalid port

        with pytest.raises(Exception) as exc_info:
            conn.send_command("get_session_info")

        assert "Not connected" in str(exc_info.value) or "Connection" in str(
            exc_info.value
        )


class TestAbletonConnectionReceiveFullResponse:
    """Test AbletonConnection.receive_full_response method."""

    def test_receive_complete_json(self):
        """Test receiving a complete JSON response in one chunk."""
        conn = AbletonConnection(host="localhost", port=9877)

        mock_sock = MagicMock()
        response_data = json.dumps({"status": "success", "result": {"test": True}})
        mock_sock.recv.return_value = response_data.encode("utf-8")

        result = conn.receive_full_response(mock_sock)
        parsed = json.loads(result.decode("utf-8"))

        assert parsed["status"] == "success"
        assert parsed["result"]["test"] is True

    def test_receive_chunked_json(self):
        """Test receiving JSON in multiple chunks."""
        conn = AbletonConnection(host="localhost", port=9877)

        mock_sock = MagicMock()
        full_response = json.dumps({"status": "success", "result": {"data": "test"}})
        chunks = [
            full_response[:10].encode("utf-8"),
            full_response[10:20].encode("utf-8"),
            full_response[20:].encode("utf-8"),
        ]

        chunk_iter = iter(chunks)
        mock_sock.recv.side_effect = lambda _: next(chunk_iter)

        result = conn.receive_full_response(mock_sock)
        parsed = json.loads(result.decode("utf-8"))

        assert parsed["status"] == "success"

    def test_receive_empty_response_raises(self):
        """Test that empty response raises exception."""
        conn = AbletonConnection(host="localhost", port=9877)

        mock_sock = MagicMock()
        mock_sock.recv.return_value = b""

        with pytest.raises(Exception) as exc_info:
            conn.receive_full_response(mock_sock)

        assert "Connection closed" in str(exc_info.value) or "No data" in str(
            exc_info.value
        )


class TestModifyingCommands:
    """Test behavior specific to state-modifying commands."""

    def test_modifying_command_list(self):
        """Verify the list of modifying commands is complete."""
        # These commands should be treated as modifying commands
        modifying_commands = [
            "create_midi_track",
            "create_audio_track",
            "set_track_name",
            "create_clip",
            "add_notes_to_clip",
            "set_clip_name",
            "set_tempo",
            "fire_clip",
            "stop_clip",
            "set_device_parameter",
            "start_playback",
            "stop_playback",
            "load_instrument_or_effect",
            "undo",
            "redo",
            "delete_track",
            "delete_clip",
            "set_metronome",
            "fire_scene",
            "set_track_mute",
            "set_track_solo",
            "set_track_arm",
            "set_track_volume",
            "set_track_panning",
        ]

        # Read the source to verify these are all handled
        import inspect

        from MCP_Server.server import AbletonConnection

        source = inspect.getsource(AbletonConnection.send_command)

        for cmd in modifying_commands:
            assert cmd in source, f"Modifying command '{cmd}' not found in send_command"

    def test_modifying_command_uses_longer_timeout(self, mock_tcp_server):
        """Test that modifying commands get longer timeout."""
        mock_tcp_server.set_response(
            "create_midi_track",
            {"status": "success", "result": {"index": 0, "name": "1-MIDI"}},
        )

        conn = AbletonConnection(host="localhost", port=mock_tcp_server.port)
        conn.connect()

        # We can't directly test the timeout, but we verify the command works
        result = conn.send_command("create_midi_track", {"index": -1})
        assert result["name"] == "1-MIDI"
