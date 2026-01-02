"""Tests for command timing strategy configuration."""

import os
import sys
import time
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestTimingStrategyConfiguration:
    """Test timing strategy environment variable configuration."""

    def test_default_strategy_returns_default_delay(self):
        """Test that default strategy returns 0.1 seconds for modifying commands."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("ABLETON_MCP_COMMAND_DELAY", None)
            os.environ.pop("ABLETON_MCP_TIMING_STRATEGY", None)

            import importlib

            import MCP_Server.strategies

            importlib.reload(MCP_Server.strategies)

            strategy = MCP_Server.strategies.get_timing_strategy_from_env()
            # Default is 0.1 seconds for modifying commands
            assert strategy.get_pre_delay("create_midi_track") == 0.1

    def test_strategy_from_env_var(self):
        """Test that strategy reads delay from environment variable."""
        with patch.dict(os.environ, {"ABLETON_MCP_COMMAND_DELAY": "0.2"}):
            import importlib

            import MCP_Server.strategies

            importlib.reload(MCP_Server.strategies)

            strategy = MCP_Server.strategies.get_timing_strategy_from_env()
            assert strategy.get_pre_delay("create_midi_track") == 0.2

    def test_strategy_accepts_float_values(self):
        """Test that strategy accepts various float delay values."""
        test_values = ["0.05", "0.1", "0.5", "1.0"]

        for val in test_values:
            with patch.dict(os.environ, {"ABLETON_MCP_COMMAND_DELAY": val}):
                import importlib

                import MCP_Server.strategies

                importlib.reload(MCP_Server.strategies)

                strategy = MCP_Server.strategies.get_timing_strategy_from_env()
                assert strategy.get_pre_delay("create_midi_track") == float(val)


class TestTimingStrategyBehavior:
    """Test that timing strategy affects modifying commands."""

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
            import MCP_Server.strategies

            importlib.reload(MCP_Server.strategies)
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
            import MCP_Server.strategies

            importlib.reload(MCP_Server.strategies)
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
            import MCP_Server.strategies

            importlib.reload(MCP_Server.strategies)
            importlib.reload(MCP_Server.server)

            conn = MCP_Server.server.AbletonConnection(host="localhost", port=mock_tcp_server.port)

            with patch("time.sleep") as mock_sleep:
                conn.send_command("create_midi_track", {"index": -1})
                # Sleep should not be called when delay is 0
                mock_sleep.assert_not_called()


class TestTimingStrategyVerification:
    """Verify timing strategy implementation."""

    def test_strategy_uses_timing_methods(self):
        """Verify send_command uses timing strategy methods."""
        import inspect

        from MCP_Server.server import AbletonConnection

        source = inspect.getsource(AbletonConnection.send_command)

        # Should use timing strategy methods
        assert "timing.get_pre_delay" in source or "self.timing.get_pre_delay" in source
        assert "timing.get_timeout" in source or "self.timing.get_timeout" in source
        assert "timing.get_post_delay" in source or "self.timing.get_post_delay" in source

    def test_modifying_commands_defined_in_strategies(self):
        """Verify modifying commands are defined in strategies module."""
        from MCP_Server.strategies import MODIFYING_COMMANDS

        # These should all be in the modifying commands set
        expected = [
            "create_midi_track",
            "create_clip",
            "add_notes_to_clip",
            "set_tempo",
            "fire_clip",
            "stop_clip",
            "start_playback",
            "stop_playback",
            "load_browser_item",
        ]

        for cmd in expected:
            assert cmd in MODIFYING_COMMANDS, f"{cmd} should be in MODIFYING_COMMANDS"

    def test_no_delay_strategy_available(self):
        """Test that NoDelayStrategy is available for testing."""
        with patch.dict(os.environ, {"ABLETON_MCP_TIMING_STRATEGY": "none"}):
            import importlib

            import MCP_Server.strategies

            importlib.reload(MCP_Server.strategies)

            strategy = MCP_Server.strategies.get_timing_strategy_from_env()
            # NoDelayStrategy should return 0 for all delays
            assert strategy.get_pre_delay("create_midi_track") == 0.0
            assert strategy.get_post_delay("create_midi_track") == 0.0

    def test_aggressive_strategy_available(self):
        """Test that AggressiveTimingStrategy is available."""
        with patch.dict(
            os.environ,
            {"ABLETON_MCP_TIMING_STRATEGY": "aggressive", "ABLETON_MCP_COMMAND_DELAY": "0.2"},
        ):
            import importlib

            import MCP_Server.strategies

            importlib.reload(MCP_Server.strategies)

            strategy = MCP_Server.strategies.get_timing_strategy_from_env()
            # AggressiveTimingStrategy should have higher delays
            assert strategy.get_pre_delay("create_midi_track") == 0.2
            # Post delay is 1.5x pre delay
            assert strategy.get_post_delay("create_midi_track") == pytest.approx(0.3)
