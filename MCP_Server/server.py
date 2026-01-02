# ableton_mcp_server.py
import json
import logging
import os
import socket
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

import anyio
from mcp.server.fastmcp import Context, FastMCP

from MCP_Server.decorators import ableton_tool
from MCP_Server.strategies import (
    CommandTimingStrategy,
    get_timing_strategy_from_env,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("AbletonMCPServer")

# MCP Server configuration
SERVER_PORT = int(os.environ.get("ABLETON_MCP_SERVER_PORT", "9877"))
SERVER_HOST = os.environ.get("ABLETON_MCP_SERVER_HOST", "127.0.0.1")

# Remote script configuration
REMOTE_SCRIPT_HOST = os.environ.get("ABLETON_REMOTE_SCRIPT_HOST", "127.0.0.1")
REMOTE_SCRIPT_PORT = int(os.environ.get("ABLETON_REMOTE_SCRIPT_PORT", "9899"))


@dataclass
class AbletonConnection:
    host: str
    port: int
    sock: socket.socket = None
    timing: CommandTimingStrategy = field(default_factory=get_timing_strategy_from_env)

    def connect(self) -> bool:
        """Connect to the Ableton Remote Script socket server"""
        if self.sock:
            return True

        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.host, self.port))
            logger.info(f"Connected to Ableton at {self.host}:{self.port}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Ableton: {str(e)}")
            self.sock = None
            return False

    def disconnect(self):
        """Disconnect from the Ableton Remote Script"""
        if self.sock:
            try:
                self.sock.close()
            except Exception as e:
                logger.error(f"Error disconnecting from Ableton: {str(e)}")
            finally:
                self.sock = None

    def receive_full_response(self, sock, buffer_size=8192):
        """Receive the complete response, potentially in multiple chunks"""
        chunks = []
        sock.settimeout(15.0)  # Increased timeout for operations that might take longer

        try:
            while True:
                try:
                    chunk = sock.recv(buffer_size)
                    if not chunk:
                        if not chunks:
                            raise Exception("Connection closed before receiving any data")
                        break

                    chunks.append(chunk)

                    # Check if we've received a complete JSON object
                    try:
                        data = b"".join(chunks)
                        json.loads(data.decode("utf-8"))
                        logger.info(f"Received complete response ({len(data)} bytes)")
                        return data
                    except json.JSONDecodeError:
                        # Incomplete JSON, continue receiving
                        continue
                except TimeoutError:
                    logger.warning("Socket timeout during chunked receive")
                    break
                except (ConnectionError, BrokenPipeError, ConnectionResetError) as e:
                    logger.error(f"Socket connection error during receive: {str(e)}")
                    raise
        except Exception as e:
            logger.error(f"Error during receive: {str(e)}")
            raise

        # If we get here, we either timed out or broke out of the loop
        if chunks:
            data = b"".join(chunks)
            logger.info(f"Returning data after receive completion ({len(data)} bytes)")
            try:
                json.loads(data.decode("utf-8"))
                return data  # pragma: no cover - JSON parsed earlier in loop
            except json.JSONDecodeError as e:
                raise Exception("Incomplete JSON response received") from e
        else:
            raise Exception("No data received")

    def send_command(self, command_type: str, params: dict[str, Any] = None) -> dict[str, Any]:
        """Send a command to Ableton and return the response"""
        if not self.sock and not self.connect():
            raise ConnectionError("Not connected to Ableton")

        command = {"type": command_type, "params": params or {}}

        try:
            logger.info(f"Sending command: {command_type} with params: {params}")

            # Pre-command delay (configured via timing strategy)
            pre_delay = self.timing.get_pre_delay(command_type)
            if pre_delay > 0:
                time.sleep(pre_delay)

            # Send the command
            self.sock.sendall(json.dumps(command).encode("utf-8"))
            logger.info("Command sent, waiting for response...")

            # Set timeout based on command type (configured via timing strategy)
            timeout = self.timing.get_timeout(command_type)
            self.sock.settimeout(timeout)

            # Receive the response
            response_data = self.receive_full_response(self.sock)
            logger.info(f"Received {len(response_data)} bytes of data")

            # Parse the response
            response = json.loads(response_data.decode("utf-8"))
            logger.info(f"Response parsed, status: {response.get('status', 'unknown')}")

            if response.get("status") == "error":
                logger.error(f"Ableton error: {response.get('message')}")
                raise Exception(response.get("message", "Unknown error from Ableton"))

            # Post-response delay (configured via timing strategy)
            post_delay = self.timing.get_post_delay(command_type)
            if post_delay > 0:
                time.sleep(post_delay)

            return response.get("result", {})
        except TimeoutError as e:
            logger.error("Socket timeout while waiting for response from Ableton")
            self.sock = None
            raise Exception("Timeout waiting for Ableton response") from e
        except (ConnectionError, BrokenPipeError, ConnectionResetError) as e:
            logger.error(f"Socket connection error: {str(e)}")
            self.sock = None
            raise Exception(f"Connection to Ableton lost: {str(e)}") from e
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON response from Ableton: {str(e)}")
            if "response_data" in locals() and response_data:
                logger.error(f"Raw response (first 200 bytes): {response_data[:200]}")
            self.sock = None
            raise Exception(f"Invalid response from Ableton: {str(e)}") from e
        except Exception as e:
            logger.error(f"Error communicating with Ableton: {str(e)}")
            self.sock = None
            raise Exception(f"Communication error with Ableton: {str(e)}") from e

    async def send_command_async(
        self, command_type: str, params: dict[str, Any] = None
    ) -> dict[str, Any]:
        """Async wrapper for send_command using anyio thread pool"""
        return await anyio.to_thread.run_sync(lambda: self.send_command(command_type, params))


@asynccontextmanager
async def server_lifespan(server: FastMCP) -> AsyncIterator[dict[str, Any]]:
    """Manage server startup and shutdown lifecycle"""
    try:
        logger.info("AbletonMCP server starting up")

        try:
            get_ableton_connection()
            logger.info("Successfully connected to Ableton on startup")
        except Exception as e:
            logger.warning(f"Could not connect to Ableton on startup: {str(e)}")
            logger.warning("Make sure the Ableton Remote Script is running")

        yield {}
    finally:
        global _ableton_connection
        if _ableton_connection:
            logger.info("Disconnecting from Ableton on shutdown")
            _ableton_connection.disconnect()
            _ableton_connection = None
        logger.info("AbletonMCP server shut down")


# Create the MCP server with lifespan support
mcp = FastMCP(
    "AbletonMCP",
    instructions="Ableton Live integration through the Model Context Protocol",
    lifespan=server_lifespan,
)

# Global connection for resources
_ableton_connection = None


def get_ableton_connection():
    """Get or create a persistent Ableton connection"""
    global _ableton_connection

    if _ableton_connection is not None:
        try:
            # Test the connection with a lightweight ping command
            _ableton_connection.sock.settimeout(2.0)
            ping_cmd = json.dumps({"type": "ping", "params": {}}).encode("utf-8")
            _ableton_connection.sock.sendall(ping_cmd)
            response = _ableton_connection.receive_full_response(_ableton_connection.sock)
            result = json.loads(response.decode("utf-8"))
            if result.get("status") == "success":
                return _ableton_connection
            else:
                raise Exception("Ping failed")
        except Exception as e:
            logger.warning(f"Existing connection is no longer valid: {str(e)}")
            try:
                _ableton_connection.disconnect()
            except Exception as disconnect_error:
                logger.warning(f"Error disconnecting stale connection: {str(disconnect_error)}")
            _ableton_connection = None

    # Connection doesn't exist or is invalid, create a new one
    if _ableton_connection is None:
        # Try to connect up to 3 times with a short delay between attempts
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            try:
                logger.info(f"Connecting to Ableton at {REMOTE_SCRIPT_HOST}:{REMOTE_SCRIPT_PORT} (attempt {attempt}/{max_attempts})...")
                _ableton_connection = AbletonConnection(host=REMOTE_SCRIPT_HOST, port=REMOTE_SCRIPT_PORT)
                if _ableton_connection.connect():
                    logger.info("Created new persistent connection to Ableton")

                    # Validate connection with a simple command
                    try:
                        # Get session info as a test
                        _ableton_connection.send_command("get_session_info")
                        logger.info("Connection validated successfully")
                        return _ableton_connection
                    except Exception as e:
                        logger.error(f"Connection validation failed: {str(e)}")
                        _ableton_connection.disconnect()
                        _ableton_connection = None
                        # Continue to next attempt
                else:
                    _ableton_connection = None
            except Exception as e:
                logger.error(f"Connection attempt {attempt} failed: {str(e)}")
                if _ableton_connection:
                    _ableton_connection.disconnect()
                    _ableton_connection = None

            # Wait before trying again, but only if we have more attempts left
            if attempt < max_attempts:
                import time

                time.sleep(1.0)

        # If we get here, all connection attempts failed
        if _ableton_connection is None:
            logger.error("Failed to connect to Ableton after multiple attempts")
            raise Exception("Could not connect to Ableton. Make sure the Remote Script is running.")

    return _ableton_connection  # pragma: no cover - returns at line 286 or raises at 309


# Core Tool endpoints


@mcp.tool()
@ableton_tool("get_session_info", error_prefix="Error getting session info")
async def get_session_info(ctx: Context) -> str:
    """Get detailed information about the current Ableton session"""
    pass


@mcp.tool()
@ableton_tool("get_track_info", error_prefix="Error getting track info")
async def get_track_info(ctx: Context, track_index: int) -> str:
    """
    Get detailed information about a specific track in Ableton.

    Parameters:
    - track_index: The index of the track to get information about
    """
    pass


@mcp.tool()
@ableton_tool(
    "create_midi_track",
    format_result=lambda r: f"Created new MIDI track: {r.get('name', 'unknown')}",
    error_prefix="Error creating MIDI track",
)
async def create_midi_track(ctx: Context, index: int = -1) -> str:
    """
    Create a new MIDI track in the Ableton session.

    Parameters:
    - index: The index to insert the track at (-1 = end of list)
    """
    pass


@mcp.tool()
@ableton_tool(
    "set_track_name",
    format_result=lambda r: f"Renamed track to: {r.get('name', 'unknown')}",
    error_prefix="Error setting track name",
)
async def set_track_name(ctx: Context, track_index: int, name: str) -> str:
    """
    Set the name of a track.

    Parameters:
    - track_index: The index of the track to rename
    - name: The new name for the track
    """
    pass


@mcp.tool()
@ableton_tool(
    "create_clip",
    format_result=lambda r: f"Created new clip at track {r.get('track_index', '?')}, slot {r.get('clip_index', '?')} with length {r.get('length', '?')} beats",
    error_prefix="Error creating clip",
)
async def create_clip(ctx: Context, track_index: int, clip_index: int, length: float = 4.0) -> str:
    """
    Create a new MIDI clip in the specified track and clip slot.

    Parameters:
    - track_index: The index of the track to create the clip in
    - clip_index: The index of the clip slot to create the clip in
    - length: The length of the clip in beats (default: 4.0)
    """
    pass


@mcp.tool()
@ableton_tool(
    "add_notes_to_clip",
    format_result=lambda r: f"Added {r.get('note_count', '?')} notes to clip",
    error_prefix="Error adding notes to clip",
)
async def add_notes_to_clip(
    ctx: Context, track_index: int, clip_index: int, notes: list[dict[str, int | float | bool]]
) -> str:
    """
    Add MIDI notes to a clip.

    Parameters:
    - track_index: The index of the track containing the clip
    - clip_index: The index of the clip slot containing the clip
    - notes: List of note dictionaries, each with pitch, start_time, duration, velocity, and mute
    """
    pass


@mcp.tool()
@ableton_tool(
    "set_clip_name",
    format_result=lambda r: f"Renamed clip to '{r.get('name', 'unknown')}'",
    error_prefix="Error setting clip name",
)
async def set_clip_name(ctx: Context, track_index: int, clip_index: int, name: str) -> str:
    """
    Set the name of a clip.

    Parameters:
    - track_index: The index of the track containing the clip
    - clip_index: The index of the clip slot containing the clip
    - name: The new name for the clip
    """
    pass


@mcp.tool()
@ableton_tool(
    "set_tempo",
    format_result=lambda r: f"Set tempo to {r.get('tempo', '?')} BPM",
    error_prefix="Error setting tempo",
)
async def set_tempo(ctx: Context, tempo: float) -> str:
    """
    Set the tempo of the Ableton session.

    Parameters:
    - tempo: The new tempo in BPM
    """
    pass


def _format_load_instrument(r: dict) -> str:
    """Format load instrument result."""
    track_index = r.get("track_index", "?")
    uri = r.get("uri", "unknown")
    if r.get("loaded", False):
        new_devices = r.get("new_devices", [])
        if new_devices:
            return f"Loaded instrument with URI '{uri}' on track {track_index}. New devices: {', '.join(new_devices)}"
        devices = r.get("devices_after", [])
        return f"Loaded instrument with URI '{uri}' on track {track_index}. Devices on track: {', '.join(devices)}"
    return f"Failed to load instrument with URI '{uri}'"


@mcp.tool()
@ableton_tool(error_prefix="Error loading instrument by URI")
async def load_instrument_or_effect(ctx: Context, track_index: int, uri: str) -> str:
    """
    Load an instrument or effect onto a track using its URI.

    Parameters:
    - track_index: The index of the track to load the instrument on
    - uri: The URI of the instrument or effect to load (e.g., 'query:Synths#Instrument%20Rack:Bass:FileId_5116')
    """
    ableton = get_ableton_connection()
    result = await ableton.send_command_async(
        "load_browser_item", {"track_index": track_index, "item_uri": uri}
    )
    result["track_index"] = track_index
    result["uri"] = uri
    return _format_load_instrument(result)


@mcp.tool()
@ableton_tool(
    "fire_clip",
    format_result=lambda r: f"Started playing clip at track {r.get('track_index', '?')}, slot {r.get('clip_index', '?')}",
    error_prefix="Error firing clip",
)
async def fire_clip(ctx: Context, track_index: int, clip_index: int) -> str:
    """
    Start playing a clip.

    Parameters:
    - track_index: The index of the track containing the clip
    - clip_index: The index of the clip slot containing the clip
    """
    pass


@mcp.tool()
@ableton_tool(
    "stop_clip",
    format_result=lambda r: f"Stopped clip at track {r.get('track_index', '?')}, slot {r.get('clip_index', '?')}",
    error_prefix="Error stopping clip",
)
async def stop_clip(ctx: Context, track_index: int, clip_index: int) -> str:
    """
    Stop playing a clip.

    Parameters:
    - track_index: The index of the track containing the clip
    - clip_index: The index of the clip slot containing the clip
    """
    pass


@mcp.tool()
@ableton_tool("start_playback", format_result=lambda _: "Started playback", error_prefix="Error starting playback")
async def start_playback(ctx: Context) -> str:
    """Start playing the Ableton session."""
    pass


@mcp.tool()
@ableton_tool("stop_playback", format_result=lambda _: "Stopped playback", error_prefix="Error stopping playback")
async def stop_playback(ctx: Context) -> str:
    """Stop playing the Ableton session."""
    pass


@mcp.tool()
@ableton_tool(
    "undo",
    format_result=lambda r: "Undid last action" if r.get("undone") else r.get("message", "Nothing to undo"),
    error_prefix="Error undoing",
)
async def undo(ctx: Context) -> str:
    """Undo the last action in Ableton."""
    pass


@mcp.tool()
@ableton_tool(
    "redo",
    format_result=lambda r: "Redid last action" if r.get("redone") else r.get("message", "Nothing to redo"),
    error_prefix="Error redoing",
)
async def redo(ctx: Context) -> str:
    """Redo the last undone action in Ableton."""
    pass


@mcp.tool()
@ableton_tool(
    "delete_track",
    format_result=lambda r: f"Deleted track: {r.get('track_name', 'unknown')}",
    error_prefix="Error deleting track",
)
async def delete_track(ctx: Context, track_index: int) -> str:
    """
    Delete a track from the Ableton session.

    Parameters:
    - track_index: The index of the track to delete
    """
    pass


@mcp.tool()
@ableton_tool(
    "create_audio_track",
    format_result=lambda r: f"Created new audio track: {r.get('name', 'unknown')}",
    error_prefix="Error creating audio track",
)
async def create_audio_track(ctx: Context, index: int = -1) -> str:
    """
    Create a new audio track in the Ableton session.

    Parameters:
    - index: The index to insert the track at (-1 = end of list)
    """
    pass


@mcp.tool()
@ableton_tool(
    "delete_clip",
    format_result=lambda r: f"Deleted clip: {r.get('clip_name', 'unknown')}",
    error_prefix="Error deleting clip",
)
async def delete_clip(ctx: Context, track_index: int, clip_index: int) -> str:
    """
    Delete a clip from a clip slot.

    Parameters:
    - track_index: The index of the track containing the clip
    - clip_index: The index of the clip slot containing the clip
    """
    pass


@mcp.tool()
@ableton_tool(
    "set_metronome",
    format_result=lambda r: f"Metronome {'enabled' if r.get('metronome') else 'disabled'}",
    error_prefix="Error setting metronome",
)
async def set_metronome(ctx: Context, enabled: bool) -> str:
    """
    Enable or disable the metronome.

    Parameters:
    - enabled: True to enable, False to disable
    """
    pass


@mcp.tool()
@ableton_tool(
    "fire_scene",
    format_result=lambda r: f"Fired scene: {r.get('scene_name', 'unknown')}",
    error_prefix="Error firing scene",
)
async def fire_scene(ctx: Context, scene_index: int) -> str:
    """
    Fire a scene (trigger all clips in a row).

    Parameters:
    - scene_index: The index of the scene to fire
    """
    pass


@mcp.tool()
@ableton_tool(
    "set_track_mute",
    format_result=lambda r: f"Track '{r.get('track_name')}' {'muted' if r.get('mute') else 'unmuted'}",
    error_prefix="Error setting track mute",
)
async def set_track_mute(ctx: Context, track_index: int, muted: bool) -> str:
    """
    Mute or unmute a track.

    Parameters:
    - track_index: The index of the track
    - muted: True to mute, False to unmute
    """
    pass


@mcp.tool()
@ableton_tool(
    "set_track_solo",
    format_result=lambda r: f"Track '{r.get('track_name')}' {'soloed' if r.get('solo') else 'unsoloed'}",
    error_prefix="Error setting track solo",
)
async def set_track_solo(ctx: Context, track_index: int, solo: bool) -> str:
    """
    Solo or unsolo a track.

    Parameters:
    - track_index: The index of the track
    - solo: True to solo, False to unsolo
    """
    pass


@mcp.tool()
@ableton_tool(
    "set_track_arm",
    format_result=lambda r: r.get("message") if "message" in r else f"Track '{r.get('track_name')}' {'armed' if r.get('arm') else 'disarmed'}",
    error_prefix="Error setting track arm",
)
async def set_track_arm(ctx: Context, track_index: int, armed: bool) -> str:
    """
    Arm or disarm a track for recording.

    Parameters:
    - track_index: The index of the track
    - armed: True to arm, False to disarm
    """
    pass


@mcp.tool()
@ableton_tool(
    "set_track_volume",
    format_result=lambda r: f"Track '{r.get('track_name')}' volume set to {r.get('volume', 0):.2f}",
    error_prefix="Error setting track volume",
)
async def set_track_volume(ctx: Context, track_index: int, volume: float) -> str:
    """
    Set track volume.

    Parameters:
    - track_index: The index of the track
    - volume: Volume level from 0.0 (silent) to 1.0 (full)
    """
    pass


def _format_panning(r: dict) -> str:
    """Format panning result for human readability."""
    pan_val = r.get("panning", 0)
    if pan_val < -0.01:
        pos = f"{abs(pan_val):.0%} left"
    elif pan_val > 0.01:
        pos = f"{pan_val:.0%} right"
    else:
        pos = "center"
    return f"Track '{r.get('track_name')}' panned to {pos}"


@mcp.tool()
@ableton_tool("set_track_panning", format_result=_format_panning, error_prefix="Error setting track panning")
async def set_track_panning(ctx: Context, track_index: int, pan: float) -> str:
    """
    Set track panning.

    Parameters:
    - track_index: The index of the track
    - pan: Panning from -1.0 (left) to 1.0 (right), 0.0 is center
    """
    pass


@mcp.tool()
@ableton_tool("get_notes_from_clip", error_prefix="Error getting notes from clip")
async def get_notes_from_clip(ctx: Context, track_index: int, clip_index: int) -> str:
    """
    Get all MIDI notes from a clip.

    Parameters:
    - track_index: The index of the track containing the clip
    - clip_index: The index of the clip slot containing the clip
    """
    pass


@mcp.tool()
@ableton_tool("get_scene_info", error_prefix="Error getting scene info")
async def get_scene_info(ctx: Context, scene_index: int) -> str:
    """
    Get information about a scene.

    Parameters:
    - scene_index: The index of the scene
    """
    pass


@mcp.tool()
@ableton_tool("get_arrangement_info", error_prefix="Error getting arrangement info")
async def get_arrangement_info(ctx: Context) -> str:
    """Get arrangement view information including playhead position, loop settings, and transport state."""
    pass


@mcp.tool()
@ableton_tool(
    "set_song_time",
    format_result=lambda r: f"Moved playhead to beat {r.get('current_song_time', 0)}",
    error_prefix="Error setting song time",
)
async def set_song_time(ctx: Context, time: float) -> str:
    """
    Set the song playhead position.

    Parameters:
    - time: Position in beats (e.g., 32.0 = start of bar 9 in 4/4 time, counting bars from 1)
    """
    pass


@mcp.tool()
@ableton_tool(
    "set_loop_region",
    format_result=lambda r: f"Set loop region: start={r.get('loop_start')}, length={r.get('loop_length')}",
    error_prefix="Error setting loop region",
)
async def set_loop_region(ctx: Context, start: float, length: float) -> str:
    """
    Set the arrangement loop region.

    Parameters:
    - start: Loop start position in beats
    - length: Loop length in beats
    """
    pass


@mcp.tool()
@ableton_tool(
    "set_loop_enabled",
    format_result=lambda r: f"Arrangement loop {'enabled' if r.get('loop_enabled') else 'disabled'}",
    error_prefix="Error setting loop enabled",
)
async def set_loop_enabled(ctx: Context, enabled: bool) -> str:
    """
    Enable or disable the arrangement loop.

    Parameters:
    - enabled: True to enable loop, False to disable
    """
    pass


@mcp.tool()
@ableton_tool(
    "continue_playing",
    format_result=lambda r: f"Continuing playback from beat {r.get('current_song_time', 0)}",
    error_prefix="Error continuing playback",
)
async def continue_playing(ctx: Context) -> str:
    """Continue playing from the current playhead position (no quantization)."""
    pass


def _format_jump_by_bars(r: dict) -> str:
    """Format jump by bars result."""
    bars = r.get("bars_jumped", 0)
    direction = "forward" if bars > 0 else "backward"
    return f"Jumped {abs(bars)} bars {direction} to beat {r.get('current_song_time', 0)}"


@mcp.tool()
@ableton_tool("jump_by_bars", format_result=_format_jump_by_bars, error_prefix="Error jumping by bars")
async def jump_by_bars(ctx: Context, bars: int) -> str:
    """
    Jump the playhead forward or backward by a number of bars.

    Parameters:
    - bars: Number of bars to jump (positive = forward, negative = backward)
    """
    pass


@mcp.tool()
@ableton_tool("get_cue_points", error_prefix="Error getting cue points")
async def get_cue_points(ctx: Context) -> str:
    """Get all cue points (markers) in the arrangement."""
    pass


@mcp.tool()
@ableton_tool(
    "jump_to_cue_point",
    format_result=lambda r: f"Jumped to '{r.get('jumped_to')}' at beat {r.get('time')}",
    error_prefix="Error jumping to cue point",
)
async def jump_to_cue_point(ctx: Context, index: int) -> str:
    """
    Jump to a cue point by its index.

    Parameters:
    - index: The index of the cue point to jump to
    """
    pass


@mcp.tool()
@ableton_tool(error_prefix="Error creating cue point")
async def create_cue_point(ctx: Context, time: float, name: str = "") -> str:
    """
    Create a cue point (marker) at a specific time in the arrangement.

    If a cue point already exists at the target time, it will not be deleted.
    Instead, the name will be updated if a new name is provided.

    Parameters:
    - time: Position in beats where the cue point should be created
    - name: Optional name for the cue point
    """
    ableton = get_ableton_connection()
    # First, check if cue point already exists at target time
    cue_points = await ableton.send_command_async("get_cue_points", {})
    existing_cue = None
    for cp in cue_points.get("cue_points", []):
        if abs(cp.get("time", -1) - time) < 0.001:
            existing_cue = cp
            break

    if existing_cue:
        # Cue point already exists - just update name if provided
        if name:
            await ableton.send_command_async("set_cue_point_name", {"time": time, "name": name})
            return f"Cue point already exists at beat {time}; updated name to '{name}'"
        return f"Cue point already exists at beat {time}"

    # Step 1: Move playhead to target position
    await ableton.send_command_async("set_song_time", {"time": time})

    # Step 2: Brief delay to ensure position is set
    await anyio.sleep(0.05)

    # Step 3: Toggle cue point at current playhead position
    result = await ableton.send_command_async("toggle_cue_at_playhead", {})

    # Step 4: Set name if provided
    if name and result.get("action") == "created":
        await anyio.sleep(0.02)
        await ableton.send_command_async("set_cue_point_name", {"time": time, "name": name})
        return f"Created cue point '{name}' at beat {time}"

    return f"Created cue point at beat {time}"


@mcp.tool()
@ableton_tool(error_prefix="Error deleting cue point")
async def delete_cue_point(ctx: Context, index: int) -> str:
    """
    Delete a cue point by its index.

    Parameters:
    - index: The index of the cue point to delete
    """
    ableton = get_ableton_connection()
    # First, get the cue point info to find its time position
    cue_points = await ableton.send_command_async("get_cue_points", {})
    cue_list = cue_points.get("cue_points", [])

    if index < 0 or index >= len(cue_list):
        return f"Error: Cue point index {index} out of range (0-{len(cue_list) - 1})"

    cue_to_delete = cue_list[index]
    cue_time = cue_to_delete.get("time")
    cue_name = cue_to_delete.get("name", "")

    # Step 1: Move playhead to cue point position
    await ableton.send_command_async("set_song_time", {"time": cue_time})

    # Step 2: Brief delay to ensure position is set
    await anyio.sleep(0.05)

    # Step 3: Toggle cue point at current playhead position (should delete it)
    await ableton.send_command_async("toggle_cue_at_playhead", {})

    return f"Deleted cue point '{cue_name}' at beat {cue_time}"


def _format_cue_jump(r: dict, fallback_msg: str) -> str:
    """Format cue point jump result."""
    if r.get("jumped"):
        return f"Jumped to '{r.get('name')}' at beat {r.get('time')}"
    return r.get("message", fallback_msg)


@mcp.tool()
@ableton_tool(
    "jump_to_next_cue_point",
    format_result=lambda r: _format_cue_jump(r, "No next cue point found"),
    error_prefix="Error jumping to next cue point",
)
async def jump_to_next_cue_point(ctx: Context) -> str:
    """Jump to the next cue point after the current playhead position."""
    pass


@mcp.tool()
@ableton_tool(
    "jump_to_prev_cue_point",
    format_result=lambda r: _format_cue_jump(r, "No previous cue point found"),
    error_prefix="Error jumping to previous cue point",
)
async def jump_to_prev_cue_point(ctx: Context) -> str:
    """Jump to the previous cue point before the current playhead position."""
    pass


@mcp.tool()
@ableton_tool(error_prefix="Error getting arrangement clips")
async def get_arrangement_clips(ctx: Context, track_index: int | None = None) -> str:
    """
    Get clips from the arrangement view.

    Parameters:
    - track_index: Optional track index. If None, returns clips from all tracks.
    """
    ableton = get_ableton_connection()
    params = {}
    if track_index is not None:
        params["track_index"] = track_index
    result = await ableton.send_command_async("get_arrangement_clips", params)
    return json.dumps(result, indent=2)


def _format_duplicate_clip(r: dict) -> str:
    """Format duplicate clip to arrangement result."""
    return (
        f"Duplicated '{r.get('clip_name')}' to arrangement at beat "
        f"{r.get('destination_time')} on track '{r.get('track_name')}'"
    )


@mcp.tool()
@ableton_tool(
    "duplicate_clip_to_arrangement",
    format_result=_format_duplicate_clip,
    error_prefix="Error duplicating clip to arrangement",
)
async def duplicate_clip_to_arrangement(
    ctx: Context, track_index: int, clip_index: int, time: float
) -> str:
    """
    Duplicate a session clip to the arrangement view at a specific time.

    Parameters:
    - track_index: The index of the track containing the clip
    - clip_index: The index of the clip slot containing the clip
    - time: The destination time in beats in the arrangement
    """
    pass


@mcp.tool()
@ableton_tool(
    "set_record_mode",
    format_result=lambda r: f"Record mode {'enabled' if r.get('record_mode') else 'disabled'}",
    error_prefix="Error setting record mode",
)
async def set_record_mode(ctx: Context, enabled: bool) -> str:
    """
    Enable or disable global record mode.

    Parameters:
    - enabled: True to enable recording, False to disable
    """
    pass


@mcp.tool()
@ableton_tool(
    "set_arrangement_overdub",
    format_result=lambda r: f"Arrangement overdub {'enabled' if r.get('arrangement_overdub') else 'disabled'}",
    error_prefix="Error setting arrangement overdub",
)
async def set_arrangement_overdub(ctx: Context, enabled: bool) -> str:
    """
    Enable or disable arrangement overdub mode.

    Parameters:
    - enabled: True to enable overdub, False to disable
    """
    pass


def _format_browser_tree_item(item: dict, indent: int = 0) -> str:
    """Format a single browser tree item with its children."""
    output = ""
    if item:
        prefix = "  " * indent
        name = item.get("name", "Unknown")
        path = item.get("path", "")
        has_more = item.get("has_more", False)

        # Add this item
        output += f"{prefix}• {name}"
        if path:
            output += f" (path: {path})"
        if has_more:
            output += " [...]"
        output += "\n"

        # Add children
        for child in item.get("children", []):
            output += _format_browser_tree_item(child, indent + 1)
    return output


@mcp.tool()
@ableton_tool(error_prefix="Error getting browser tree")
async def get_browser_tree(ctx: Context, category_type: str = "all") -> str:
    """
    Get a hierarchical tree of browser categories from Ableton.

    Parameters:
    - category_type: Type of categories to get ('all', 'instruments', 'sounds', 'drums', 'audio_effects', 'midi_effects')
    """
    ableton = get_ableton_connection()
    result = await ableton.send_command_async(
        "get_browser_tree", {"category_type": category_type}
    )

    # Check if we got any categories
    if "available_categories" in result and len(result.get("categories", [])) == 0:
        available_cats = result.get("available_categories", [])
        return (
            f"No categories found for '{category_type}'. "
            f"Available browser categories: {', '.join(available_cats)}"
        )

    # Format the tree in a more readable way
    total_folders = result.get("total_folders", 0)
    formatted_output = (
        f"Browser tree for '{category_type}' (showing {total_folders} folders):\n\n"
    )

    # Format each category
    for category in result.get("categories", []):
        formatted_output += _format_browser_tree_item(category)
        formatted_output += "\n"

    return formatted_output


@mcp.tool()
@ableton_tool(error_prefix="Error getting browser items at path")
async def get_browser_items_at_path(ctx: Context, path: str) -> str:
    """
    Get browser items at a specific path in Ableton's browser.

    Parameters:
    - path: Path in the format "category/folder/subfolder"
            where category is one of the available browser categories in Ableton
    """
    ableton = get_ableton_connection()
    result = await ableton.send_command_async("get_browser_items_at_path", {"path": path})

    # Check if there was an error with available categories
    if "error" in result and "available_categories" in result:
        error = result.get("error", "")
        available_cats = result.get("available_categories", [])
        return f"Error: {error}\nAvailable browser categories: {', '.join(available_cats)}"

    return json.dumps(result, indent=2)


@mcp.tool()
@ableton_tool(error_prefix="Error loading drum kit")
async def load_drum_kit(
    ctx: Context, track_index: int, rack_uri: str, kit_path: str
) -> str:
    """
    Load a drum rack and then load a specific drum kit into it.

    Parameters:
    - track_index: The index of the track to load on
    - rack_uri: The URI of the drum rack to load (e.g., 'Drums/Drum Rack')
    - kit_path: Path to the drum kit inside the browser (e.g., 'drums/acoustic/kit1')
    """
    ableton = get_ableton_connection()
    # Step 1: Load the drum rack
    result = await ableton.send_command_async(
        "load_browser_item", {"track_index": track_index, "item_uri": rack_uri}
    )

    if not result.get("loaded", False):
        return (
            f"Failed to load drum rack with URI '{rack_uri}'. "
            f"Use get_browser_tree('drums') to find valid drum rack URIs."
        )

    # Step 2: Get the drum kit items at the specified path
    kit_result = await ableton.send_command_async(
        "get_browser_items_at_path", {"path": kit_path}
    )

    if "error" in kit_result:
        return (
            f"Loaded drum rack but failed to find drum kit at path '{kit_path}': "
            f"{kit_result.get('error')}. Use get_browser_items_at_path() to explore available paths."
        )

    # Step 3: Find a loadable drum kit
    kit_items = kit_result.get("items", [])
    loadable_kits = [item for item in kit_items if item.get("is_loadable", False)]

    if not loadable_kits:
        available_items = [item.get("name", "unknown") for item in kit_items[:5]]
        return (
            f"Loaded drum rack but no loadable drum kits found at '{kit_path}'. "
            f"Found {len(kit_items)} items: {', '.join(available_items)}{'...' if len(kit_items) > 5 else ''}"
        )

    # Step 4: Load the first loadable kit
    kit_uri = loadable_kits[0].get("uri")
    await ableton.send_command_async(
        "load_browser_item", {"track_index": track_index, "item_uri": kit_uri}
    )

    return f"Loaded drum rack and kit '{loadable_kits[0].get('name')}' on track {track_index}"


# Main execution
def main():
    """Run the MCP server"""
    mcp.run()


if __name__ == "__main__":
    main()  # pragma: no cover
