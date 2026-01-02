"""Tests for COMMAND_DELAY configuration."""

import os
import sys
import time
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestCommandDelayConfiguration:
    """Test COMMAND_DELAY environment variable configuration."""

    def test_default_delay_is_zero(self):
        """Test that default COMMAND_DELAY is 0."""
        # Reload module to pick up env var
        with patch.dict(os.environ, {}, clear=True):
            # Remove the key if it exists
            os.environ.pop("ABLETON_MCP_COMMAND_DELAY", None)

            # Need to reimport to get fresh value
            import importlib

            import MCP_Server.server

            importlib.reload(MCP_Server.server)

            assert MCP_Server.server.COMMAND_DELAY == 0.0

    def test_delay_from_env_var(self):
        """Test that COMMAND_DELAY reads from environment variable."""
        with patch.dict(os.environ, {"ABLETON_MCP_COMMAND_DELAY": "0.1"}):
            import importlib

            import MCP_Server.server

            importlib.reload(MCP_Server.server)

            assert MCP_Server.server.COMMAND_DELAY == 0.1

    def test_delay_accepts_float_values(self):
        """Test that COMMAND_DELAY accepts various float values."""
        test_values = ["0.05", "0.1", "0.5", "1.0"]

        for val in test_values:
            with patch.dict(os.environ, {"ABLETON_MCP_COMMAND_DELAY": val}):
                import importlib

                import MCP_Server.server

                importlib.reload(MCP_Server.server)

                assert float(val) == MCP_Server.server.COMMAND_DELAY


class TestCommandDelayBehavior:
    """Test that COMMAND_DELAY affects modifying commands."""

    def test_modifying_command_with_delay(self, mock_tcp_server):
        """Test that modifying commands apply delay when configured."""
        mock_tcp_server.set_response(
            "create_midi_track",
            {"status": "success", "result": {"index": 0, "name": "1-MIDI"}},
        )

        # Set a small delay
        with patch.dict(os.environ, {"ABLETON_MCP_COMMAND_DELAY": "0.05"}):
            import importlib

            import MCP_Server.server

            importlib.reload(MCP_Server.server)

            conn = MCP_Server.server.AbletonConnection(host="localhost", port=mock_tcp_server.port)

            start_time = time.time()
            conn.send_command("create_midi_track", {"index": -1})
            elapsed = time.time() - start_time

            # Should take at least the delay time (2x because pre and post delay)
            # But allow some margin for test flakiness
            assert elapsed >= 0.05  # At least one delay applied

    def test_non_modifying_command_no_delay(self, mock_tcp_server):
        """Test that non-modifying commands don't apply delay."""
        mock_tcp_server.set_response(
            "get_session_info",
            {"status": "success", "result": {"tempo": 120.0}},
        )

        # Set a delay
        with patch.dict(os.environ, {"ABLETON_MCP_COMMAND_DELAY": "0.5"}):
            import importlib

            import MCP_Server.server

            importlib.reload(MCP_Server.server)

            conn = MCP_Server.server.AbletonConnection(host="localhost", port=mock_tcp_server.port)

            start_time = time.time()
            conn.send_command("get_session_info")
            elapsed = time.time() - start_time

            # Should be fast - no delay applied for non-modifying commands
            assert elapsed < 0.5  # Should be much faster than the configured delay

    def test_zero_delay_skips_sleep(self, mock_tcp_server):
        """Test that zero delay skips the sleep call entirely."""
        mock_tcp_server.set_response(
            "create_midi_track",
            {"status": "success", "result": {"index": 0, "name": "1-MIDI"}},
        )

        with patch.dict(os.environ, {"ABLETON_MCP_COMMAND_DELAY": "0"}):
            import importlib

            import MCP_Server.server

            importlib.reload(MCP_Server.server)

            conn = MCP_Server.server.AbletonConnection(host="localhost", port=mock_tcp_server.port)

            with patch("time.sleep") as mock_sleep:
                conn.send_command("create_midi_track", {"index": -1})
                # Sleep should not be called when delay is 0
                mock_sleep.assert_not_called()


class TestDelaySourceCodeVerification:
    """Verify delay implementation in source code."""

    def test_delay_check_condition(self):
        """Verify the delay only applies when COMMAND_DELAY > 0."""
        import inspect

        from MCP_Server.server import AbletonConnection

        source = inspect.getsource(AbletonConnection.send_command)

        # Should check if COMMAND_DELAY > 0 before sleeping
        assert "COMMAND_DELAY > 0" in source
        assert "is_modifying_command" in source

    def test_modifying_commands_defined(self):
        """Verify modifying commands list includes key commands."""
        import inspect

        from MCP_Server.server import AbletonConnection

        source = inspect.getsource(AbletonConnection.send_command)

        # These should all be in the modifying commands list
        expected = [
            "create_midi_track",
            "create_clip",
            "add_notes_to_clip",
            "set_tempo",
            "fire_clip",
            "stop_clip",
            "start_playback",
            "stop_playback",
            "load_instrument_or_effect",
        ]

        for cmd in expected:
            assert cmd in source, f"{cmd} should be in modifying commands list"
