"""
Command Pattern implementation for AbletonMCP Remote Script.

This module provides the base classes and registry for all commands that
can be executed by the MCP server. Commands are organized into categories:
- session: Session and track information queries
- tracks: Track creation and manipulation
- clips: Clip creation and manipulation
- transport: Playback control
- arrangement: Arrangement view, cue points, loop settings
- browser: Browser navigation and instrument loading
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional, Type

if TYPE_CHECKING:
    from ..facade import LiveSessionFacade

# Single source of truth for commands that modify Live's state
# These commands must be scheduled on Ableton's main thread
# IMPORTANT: Keep in sync with MCP_Server/server.py modifying commands list
MODIFYING_COMMANDS = frozenset([
    "create_midi_track",
    "create_audio_track",
    "set_track_name",
    "create_clip",
    "add_notes_to_clip",
    "set_clip_name",
    "set_tempo",
    "fire_clip",
    "stop_clip",
    "start_playback",
    "stop_playback",
    "load_browser_item",
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
    "toggle_cue_at_playhead",
    "set_cue_point_name",
    "jump_to_next_cue_point",
    "jump_to_prev_cue_point",
    "duplicate_clip_to_arrangement",
    "set_record_mode",
    "set_arrangement_overdub",
])


class Command(ABC):
    """
    Base class for all commands.

    Commands encapsulate operations that can be executed against Ableton Live.
    Each command has a unique command_type identifier and an execute method
    that performs the operation.
    """

    # Subclasses must define this
    command_type: str = None

    # Whether this command modifies Live's state (requires main thread)
    requires_main_thread: bool = False

    @abstractmethod
    def execute(self, context: "CommandContext", params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the command.

        Args:
            context: The command context providing access to Live's objects
            params: Command parameters from the client

        Returns:
            A dictionary containing the command result
        """
        pass


class ModifyingCommand(Command):
    """
    Base class for commands that modify Live's state.

    These commands must be executed on Ableton's main thread using
    schedule_message. The CommandDispatcher handles this automatically.
    """

    requires_main_thread: bool = True


class CommandContext:
    """
    Context object passed to commands providing access to Live's objects.

    This encapsulates the dependencies that commands need, making them
    easier to test and keeping them decoupled from the AbletonMCP class.

    The facade property provides a clean, typed interface to the LOM.
    Commands can use either the facade (preferred) or direct song/application
    access for operations not yet in the facade.
    """

    def __init__(
        self,
        song: Any,
        application: Any,
        log_message: Callable[[str], None],
        show_message: Callable[[str], None],
        schedule_message: Callable[[int, Callable], None],
        browser_uri_cache: Dict[str, Any],
    ):
        self.song = song
        self.application = application
        self.log_message = log_message
        self.show_message = show_message
        self.schedule_message = schedule_message
        self.browser_uri_cache = browser_uri_cache
        self._facade: Optional["LiveSessionFacade"] = None

    @property
    def facade(self) -> "LiveSessionFacade":
        """
        Get the LiveSessionFacade for clean LOM access.

        The facade is created lazily on first access.
        """
        if self._facade is None:
            from ..facade import LiveSessionFacade

            self._facade = LiveSessionFacade(self.song, self.application)
        return self._facade

    def log(self, message: str) -> None:
        """Log a message to Ableton's log."""
        self.log_message(message)


class CommandRegistry:
    """
    Registry for command classes.

    Commands register themselves with the registry, and the dispatcher
    uses the registry to look up the appropriate command for a request.

    Usage:
        # Register a command
        @CommandRegistry.register
        class GetSessionInfoCommand(Command):
            command_type = "get_session_info"
            ...

        # Look up a command
        command_class = CommandRegistry.get("get_session_info")
        command = command_class()
        result = command.execute(context, params)
    """

    _commands: Dict[str, Type[Command]] = {}

    @classmethod
    def register(cls, command_class: Type[Command]) -> Type[Command]:
        """
        Register a command class with the registry.

        Can be used as a decorator:
            @CommandRegistry.register
            class MyCommand(Command):
                command_type = "my_command"
        """
        if command_class.command_type is None:
            raise ValueError(f"Command class {command_class.__name__} must define command_type")

        cls._commands[command_class.command_type] = command_class
        return command_class

    @classmethod
    def get(cls, command_type: str) -> Optional[Type[Command]]:
        """Get a command class by its command_type."""
        return cls._commands.get(command_type)

    @classmethod
    def has(cls, command_type: str) -> bool:
        """Check if a command type is registered."""
        return command_type in cls._commands

    @classmethod
    def is_modifying(cls, command_type: str) -> bool:
        """Check if a command type modifies Live's state."""
        command_class = cls.get(command_type)
        if command_class:
            return command_class.requires_main_thread
        # Fall back to the static list for unregistered commands
        return command_type in MODIFYING_COMMANDS

    @classmethod
    def all_command_types(cls) -> list:
        """Get all registered command types."""
        return list(cls._commands.keys())

    @classmethod
    def clear(cls) -> None:
        """Clear all registered commands (useful for testing)."""
        cls._commands.clear()


# Import command modules to trigger registration
# These imports must be at the bottom to avoid circular imports
# ruff: noqa: E402
from . import (
    arrangement,  # noqa: F401
    browser,  # noqa: F401
    clips,  # noqa: F401
    session,  # noqa: F401
    tracks,  # noqa: F401
    transport,  # noqa: F401
)
