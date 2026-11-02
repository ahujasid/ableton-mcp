"""Tools for the Remote Script's extended commands (undo, track deletion, and
later mixer, routing, monitoring and meters).

Kept out of server.py so the upstream file only gains one register() call.
Every tool returns the Remote Script's result as JSON on success and a string
starting with "Error" on failure, like the upstream tools.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

from mcp.server.fastmcp import Context, FastMCP

from . import script_handshake
from .telemetry_decorator import telemetry_tool

logger = logging.getLogger("AbletonMCPServer")

# Extended commands that change the set; the connection gives them the longer
# modifying-command socket timeout.
MODIFYING_COMMANDS = frozenset({"undo", "redo", "delete_track"})

TRACK_TYPE_DOC = (
    "track_type: 'track' (default, track_index counts regular tracks), 'return' "
    "(track_index counts return tracks, A=0) or 'master' (track_index ignored)"
)


def _call(get_connection: Callable[[], Any], command: str, params: dict | None, label: str) -> str:
    try:
        missing = script_handshake.require_capability(command)
        if missing:
            return missing
        result = get_connection().send_command(command, params or {})
        return json.dumps(result, indent=2)
    except Exception as e:  # noqa: BLE001 - reported to the agent as text
        logger.error("Error %s: %s", label, e)
        return f"Error {label}: {e}"


def register(mcp: FastMCP, get_connection: Callable[[], Any]) -> None:
    """Add the extended tools to the server."""

    @mcp.tool()
    @telemetry_tool("get_undo_state")
    def get_undo_state(ctx: Context, user_prompt: str = "") -> str:
        """Report whether Live's undo history has a step to undo or redo.

        Parameters:
        - user_prompt: leave empty
        """
        return _call(get_connection, "get_undo_state", {}, "getting undo state")

    @mcp.tool()
    @telemetry_tool("undo")
    def undo(ctx: Context, user_prompt: str = "") -> str:
        """Undo the most recent step in Live's undo history (same as Ctrl+Z).

        Live keeps one history for everything, so this undoes the last change
        whoever made it - possibly the user's own edit, not this agent's. Call it
        right after the step you mean to revert, and say what you are undoing.

        Parameters:
        - user_prompt: leave empty
        """
        return _call(get_connection, "undo", {}, "undoing")

    @mcp.tool()
    @telemetry_tool("redo")
    def redo(ctx: Context, user_prompt: str = "") -> str:
        """Redo the most recently undone step (same as Ctrl+Shift+Z).

        Parameters:
        - user_prompt: leave empty
        """
        return _call(get_connection, "redo", {}, "redoing")

    @mcp.tool()
    @telemetry_tool("delete_track")
    def delete_track(
        ctx: Context,
        track_index: int,
        expected_name: str,
        track_type: str = "track",
        user_prompt: str = "",
    ) -> str:
        """Delete a track or return track. Undo (Ctrl+Z or the undo tool) restores it.

        expected_name must equal the track's current name exactly. Read it with
        get_session_info or get_track_info first; if the indices have shifted the
        delete is refused instead of removing the wrong track. The master track
        and a set's last remaining track cannot be deleted.

        Parameters:
        - track_index: index of the track to delete (0-based)
        - expected_name: the track's current name, as a safety check
        - track_type: 'track' (default) or 'return'
        - user_prompt: leave empty
        """
        return _call(get_connection, "delete_track", {
            "track_index": track_index,
            "expected_name": expected_name,
            "track_type": track_type,
        }, "deleting track")
