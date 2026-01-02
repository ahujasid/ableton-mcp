"""
Timing strategies for command execution.

This module provides pluggable timing behavior for MCP server commands,
allowing different delay and timeout configurations for different use cases.
"""

import os
from typing import Protocol

# Command types that modify Ableton's state and may need extra time to process.
# IMPORTANT: Keep in sync with ModifyingCommand subclasses in
# AbletonMCP_Remote_Script/commands/__init__.py
MODIFYING_COMMANDS = frozenset(
    [
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
        "set_song_time",
        "set_loop_region",
        "set_loop_enabled",
        "continue_playing",
        "jump_by_bars",
        "jump_to_cue_point",
        "create_cue_point",
        "delete_cue_point",
        "jump_to_next_cue_point",
        "jump_to_prev_cue_point",
        "duplicate_clip_to_arrangement",
        "set_record_mode",
        "set_arrangement_overdub",
        "toggle_cue_at_playhead",
        "set_cue_point_name",
        "load_browser_item",
    ]
)


class CommandTimingStrategy(Protocol):
    """Protocol for command timing strategies."""

    def get_pre_delay(self, command_type: str) -> float:
        """Get delay before sending command (seconds)."""
        ...

    def get_post_delay(self, command_type: str) -> float:
        """Get delay after receiving response (seconds)."""
        ...

    def get_timeout(self, command_type: str) -> float:
        """Get socket timeout for command (seconds)."""
        ...

    def is_modifying_command(self, command_type: str) -> bool:
        """Check if command modifies Ableton state."""
        ...


class DefaultTimingStrategy:
    """
    Default timing strategy with configurable base delay.

    Applies delays to state-modifying commands to ensure Ableton
    has time to process changes before the next command.
    """

    def __init__(
        self,
        base_delay: float = 0.1,
        modifying_timeout: float = 15.0,
        read_timeout: float = 10.0,
    ):
        """
        Initialize timing strategy.

        Args:
            base_delay: Delay in seconds for modifying commands (default 0.1)
            modifying_timeout: Socket timeout for modifying commands (default 15.0)
            read_timeout: Socket timeout for read-only commands (default 10.0)
        """
        self._base_delay = base_delay
        self._modifying_timeout = modifying_timeout
        self._read_timeout = read_timeout

    def get_pre_delay(self, command_type: str) -> float:
        """Get delay before sending command."""
        if self._base_delay > 0 and command_type in MODIFYING_COMMANDS:
            return self._base_delay
        return 0.0

    def get_post_delay(self, command_type: str) -> float:
        """Get delay after receiving response."""
        if self._base_delay > 0 and command_type in MODIFYING_COMMANDS:
            return self._base_delay
        return 0.0

    def get_timeout(self, command_type: str) -> float:
        """Get socket timeout for command."""
        if command_type in MODIFYING_COMMANDS:
            return self._modifying_timeout
        return self._read_timeout

    def is_modifying_command(self, command_type: str) -> bool:
        """Check if command modifies Ableton state."""
        return command_type in MODIFYING_COMMANDS


class NoDelayStrategy:
    """
    Strategy with no delays for testing or low-latency requirements.

    Disables all pre/post delays while maintaining reasonable timeouts.
    """

    def __init__(self, timeout: float = 10.0):
        """
        Initialize no-delay strategy.

        Args:
            timeout: Socket timeout for all commands (default 10.0)
        """
        self._timeout = timeout

    def get_pre_delay(self, _command_type: str) -> float:
        """No pre-delay."""
        return 0.0

    def get_post_delay(self, _command_type: str) -> float:
        """No post-delay."""
        return 0.0

    def get_timeout(self, _command_type: str) -> float:
        """Same timeout for all commands."""
        return self._timeout

    def is_modifying_command(self, command_type: str) -> bool:
        """Check if command modifies Ableton state."""
        return command_type in MODIFYING_COMMANDS


class AggressiveTimingStrategy:
    """
    Strategy with longer delays for unreliable connections.

    Use when experiencing connection issues or when Ableton
    is under heavy load.
    """

    def __init__(self, base_delay: float = 0.2, timeout: float = 30.0):
        """
        Initialize aggressive timing strategy.

        Args:
            base_delay: Delay in seconds for modifying commands (default 0.2)
            timeout: Socket timeout for all commands (default 30.0)
        """
        self._base_delay = base_delay
        self._timeout = timeout

    def get_pre_delay(self, command_type: str) -> float:
        """Get delay before sending command."""
        if command_type in MODIFYING_COMMANDS:
            return self._base_delay
        return 0.0

    def get_post_delay(self, command_type: str) -> float:
        """Get delay after receiving response."""
        if command_type in MODIFYING_COMMANDS:
            return self._base_delay * 1.5  # Extra post-delay
        return 0.0

    def get_timeout(self, _command_type: str) -> float:
        """Longer timeout for all commands."""
        return self._timeout

    def is_modifying_command(self, command_type: str) -> bool:
        """Check if command modifies Ableton state."""
        return command_type in MODIFYING_COMMANDS


def get_timing_strategy_from_env() -> CommandTimingStrategy:
    """
    Get timing strategy based on environment variables.

    Environment variables:
        ABLETON_MCP_TIMING_STRATEGY: Strategy name ('default', 'none', 'aggressive')
        ABLETON_MCP_COMMAND_DELAY: Base delay for default strategy (seconds)
        ABLETON_MCP_TIMEOUT: Base timeout (seconds)

    Returns:
        Configured timing strategy
    """
    strategy_name = os.environ.get("ABLETON_MCP_TIMING_STRATEGY", "default").lower()
    base_delay = float(os.environ.get("ABLETON_MCP_COMMAND_DELAY", "0.1"))
    timeout = float(os.environ.get("ABLETON_MCP_TIMEOUT", "15.0"))

    if strategy_name == "none":
        return NoDelayStrategy(timeout=timeout)
    elif strategy_name == "aggressive":
        return AggressiveTimingStrategy(base_delay=base_delay, timeout=timeout)
    else:
        # Default strategy
        return DefaultTimingStrategy(
            base_delay=base_delay,
            modifying_timeout=timeout,
            read_timeout=10.0,
        )
