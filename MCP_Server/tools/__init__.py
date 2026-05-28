"""Register all Ableton MCP tools with the FastMCP instance."""

from typing import Callable

# Type for get_ableton_connection: callable that returns connection
GetAbletonConnection = Callable[[], object]


def register_all(mcp: object, get_ableton_connection: GetAbletonConnection) -> None:
    """Register all tool modules with the given mcp and connection getter."""
    from . import session
    from . import tracks
    from . import clips
    from . import mixer
    from . import devices
    from . import browser
    from . import scenes
    from . import arrangement
    from . import audio
    from . import midi

    session.register(mcp, get_ableton_connection)
    tracks.register(mcp, get_ableton_connection)
    clips.register(mcp, get_ableton_connection)
    mixer.register(mcp, get_ableton_connection)
    devices.register(mcp, get_ableton_connection)
    browser.register(mcp, get_ableton_connection)
    scenes.register(mcp, get_ableton_connection)
    arrangement.register(mcp, get_ableton_connection)
    audio.register(mcp, get_ableton_connection)
    midi.register(mcp, get_ableton_connection)
