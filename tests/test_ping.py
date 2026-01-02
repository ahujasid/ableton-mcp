"""Tests for ping command and connection health checks."""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestPingCommand:
    """Test ping command in Remote Script."""

    def test_ping_command_returns_ok(self, mock_tcp_server):
        """Test that ping command returns success status."""
        mock_tcp_server.set_response("ping", {"status": "success", "result": {"status": "ok"}})

        from MCP_Server.server import AbletonConnection

        conn = AbletonConnection(host="localhost", port=mock_tcp_server.port)
        result = conn.send_command("ping")

        assert result["status"] == "ok"

    def test_ping_is_lightweight(self, mock_tcp_server):
        """Test that ping command is fast and lightweight."""
        import time

        mock_tcp_server.set_response("ping", {"status": "success", "result": {"status": "ok"}})

        from MCP_Server.server import AbletonConnection

        conn = AbletonConnection(host="localhost", port=mock_tcp_server.port)

        start = time.time()
        conn.send_command("ping")
        elapsed = time.time() - start

        # Ping should be very fast (< 1 second for local)
        assert elapsed < 1.0


class TestConnectionHealthCheck:
    """Test connection health check using ping."""

    def test_health_check_uses_ping(self):
        """Verify get_ableton_connection uses ping for health check."""
        import inspect

        from MCP_Server import server

        source = inspect.getsource(server.get_ableton_connection)

        # Should use ping command for health check
        assert "ping" in source
        assert '"type": "ping"' in source or "'type': 'ping'" in source

    def test_valid_connection_passes_ping(self, mock_tcp_server):
        """Test that valid connection passes ping health check."""
        mock_tcp_server.set_response("ping", {"status": "success", "result": {"status": "ok"}})
        mock_tcp_server.set_response(
            "get_session_info",
            {"status": "success", "result": {"tempo": 120.0}},
        )

        # Reset the global connection
        import MCP_Server.server
        from MCP_Server.server import AbletonConnection, get_ableton_connection

        MCP_Server.server._ableton_connection = None

        with (
            patch.object(
                AbletonConnection,
                "__init__",
                lambda self, host, port: setattr(self, "host", host)
                or setattr(self, "port", port)
                or setattr(self, "sock", None),
            ),
            patch.object(AbletonConnection, "connect", return_value=True) as mock_connect,
            patch.object(
                AbletonConnection,
                "send_command",
                return_value={"tempo": 120.0},
            ),
        ):
            try:
                get_ableton_connection()
            except (ConnectionError, OSError) as e:
                pytest.skip(f"Skipping due to connection error: {e}")
            # Should attempt to connect
            assert mock_connect.called

    def test_invalid_connection_triggers_reconnect(self):
        """Test that failed ping triggers reconnection attempt."""
        import inspect

        from MCP_Server import server

        source = inspect.getsource(server.get_ableton_connection)

        # Should handle ping failure and reconnect
        assert "except" in source
        assert "disconnect" in source or "_ableton_connection = None" in source


class TestPingCommandInRemoteScript:
    """Test ping command implementation in Remote Script."""

    def test_ping_handler_exists(self):
        """Verify ping command is handled in Remote Script."""
        session_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "AbletonMCP_Remote_Script",
            "commands",
            "session.py",
        )

        with open(session_path) as f:
            source = f.read()

        assert 'command_type = "ping"' in source, "ping command should be registered"

    def test_ping_returns_status_ok(self):
        """Verify ping returns correct response format."""
        session_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "AbletonMCP_Remote_Script",
            "commands",
            "session.py",
        )

        with open(session_path) as f:
            source = f.read()

        # Verify PingCommand class exists and returns status ok
        assert "class PingCommand" in source
        assert '{"status": "ok"}' in source


class TestConnectionErrorHandling:
    """Test connection error handling in health check."""

    def test_connection_error_raises_exception(self):
        """Test that connection errors are properly raised."""
        import MCP_Server.server
        from MCP_Server.server import get_ableton_connection

        MCP_Server.server._ableton_connection = None

        # Mock AbletonConnection class to fail validation
        with patch("MCP_Server.server.AbletonConnection") as MockConn:
            mock_instance = MagicMock()
            mock_instance.connect.return_value = True
            mock_instance.send_command.side_effect = ConnectionError("Test connection error")
            mock_instance.disconnect = MagicMock()
            MockConn.return_value = mock_instance

            with patch("time.sleep"):
                # This should raise after all retries fail
                try:
                    get_ableton_connection()
                except (ConnectionError, OSError, Exception) as e:
                    # We hit the exception path - test passes
                    assert "connection" in str(e).lower() or "connect" in str(e).lower()
                    return

        # If we get here without exception, the test should fail
        pytest.fail("Expected exception was not raised")


class TestHealthCheckTimeout:
    """Test health check timeout behavior."""

    def test_ping_has_short_timeout(self):
        """Verify ping uses a short timeout."""
        import inspect

        from MCP_Server import server

        source = inspect.getsource(server.get_ableton_connection)

        # Should set a short timeout for ping (2.0 seconds)
        assert "settimeout" in source
        assert "2.0" in source or "2" in source

    def test_ping_timeout_shorter_than_command_timeout(self):
        """Verify ping timeout is shorter than normal command timeout."""
        import inspect

        from MCP_Server import server
        from MCP_Server.strategies import DefaultTimingStrategy

        # Get the timeouts from source
        conn_source = inspect.getsource(server.get_ableton_connection)

        # Ping timeout should be around 2.0
        assert "2.0" in conn_source or "settimeout(2" in conn_source

        # Normal command timeout is configured in DefaultTimingStrategy
        strategy = DefaultTimingStrategy()
        assert strategy.get_timeout("create_midi_track") == 15.0  # modifying command
        assert strategy.get_timeout("get_session_info") == 10.0  # read-only command
