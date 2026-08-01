# ableton_mcp_server.py
from mcp.server.fastmcp import FastMCP, Context
import socket
import json
import logging
import os
from dataclasses import dataclass
from contextlib import asynccontextmanager
from typing import AsyncIterator, Dict, Any, List, Union, Optional

from typing_extensions import Literal, TypedDict

from .telemetry import record_startup
from .telemetry_decorator import telemetry_tool, rich_telemetry_tool

ABLETON_HOST = os.environ.get("ABLETON_HOST", "localhost")
ABLETON_PORT = int(os.environ.get("ABLETON_PORT", "9877"))

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("AbletonMCPServer")


class AbletonError(Exception):
    """Structured error raised while talking to the Remote Script."""

    error_type = "ableton_error"

    def __init__(
        self,
        message: str,
        *,
        command: Optional[str] = None,
        code: Optional[str] = None,
        details: Any = None,
    ):
        super().__init__(message)
        self.message = message
        self.command = command
        self.code = code
        self.details = details

    def as_dict(self) -> Dict[str, Any]:
        return {
            "type": self.error_type,
            "message": self.message,
            "command": self.command,
            "code": self.code,
            "details": self.details,
        }


class AbletonRemoteError(AbletonError):
    """An error returned by the Remote Script, retaining its full payload."""

    error_type = "remote_error"


class AbletonTimeoutError(AbletonError):
    """The client timed out waiting for Live's main-thread response."""

    error_type = "timeout"


class AbletonConnectionError(AbletonError):
    """The socket could not be used for a command."""

    error_type = "connection_error"


class AbletonProtocolError(AbletonError):
    """The Remote Script returned a response that was not valid JSON."""

    error_type = "protocol_error"


# The Remote Script waits up to ten seconds for a scheduled main-thread task.
# Keep the client budget above that queue budget so a valid mutation is not
# reported as a client timeout first.  Long-running audio import retains its
# existing wider budget.
MUTATION_TIMEOUT_SECONDS = 15.0
READ_TIMEOUT_SECONDS = 10.0
LONG_RUNNING_COMMAND_TIMEOUTS = {"create_audio_clip": 65.0}

MODIFYING_COMMANDS = frozenset(
    {
        "create_midi_track",
        "create_audio_track",
        "set_track_name",
        "create_clip",
        "create_audio_clip",
        "add_notes_to_clip",
        "set_clip_name",
        "set_tempo",
        "fire_clip",
        "stop_clip",
        "set_mixer_parameter",
        "set_mixer_parameters",
        "set_device_parameter",
        "set_device_parameters",
        "replace_clip_notes",
        "clear_clip_notes",
        "set_clip_loop",
        "delete_session_clip",
        "duplicate_session_clip",
        "duplicate_session_scene_clips",
        "fire_scene",
        "stop_all_clips",
        "back_to_arrangement",
        "start_playback",
        "stop_playback",
        "load_instrument_or_effect",
        "load_browser_item",
        "switch_to_arrangement_view",
        "set_current_song_time",
        "duplicate_session_clip_to_arrangement",
        "delete_arrangement_clip",
    }
)


@dataclass
class AbletonConnection:
    host: str
    port: int
    sock: socket.socket = None
    
    def connect(self) -> bool:
        """Connect to the Ableton Remote Script socket server"""
        if self.sock:
            return True

        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(5.0)
            self.sock.connect((self.host, self.port))
            self.sock.settimeout(None)
            logger.info(f"Connected to Ableton at {self.host}:{self.port}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Ableton at {self.host}:{self.port}: {str(e)}")
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

        try:
            while True:
                chunk = sock.recv(buffer_size)
                if not chunk:
                    if not chunks:
                        raise ConnectionError("Connection closed before receiving any data")
                    raise ValueError("Incomplete JSON response received")

                chunks.append(chunk)

                # The Remote Script sends one JSON object per request without a
                # delimiter.  Parse only when the accumulated bytes form a
                # complete object; socket.timeout is intentionally allowed to
                # propagate so send_command can classify it correctly.
                data = b"".join(chunks)
                try:
                    json.loads(data.decode("utf-8"))
                except json.JSONDecodeError:
                    continue
                logger.info(f"Received complete response ({len(data)} bytes)")
                return data

        except (socket.timeout, ConnectionError, BrokenPipeError, ConnectionResetError):
            raise
        except Exception as exc:
            logger.error(f"Error during receive: {exc}")
            raise

    @staticmethod
    def is_modifying_command(command_type: str) -> bool:
        return command_type in MODIFYING_COMMANDS

    @classmethod
    def timeout_for_command(cls, command_type: str) -> float:
        if command_type in LONG_RUNNING_COMMAND_TIMEOUTS:
            return LONG_RUNNING_COMMAND_TIMEOUTS[command_type]
        if cls.is_modifying_command(command_type):
            return MUTATION_TIMEOUT_SECONDS
        return READ_TIMEOUT_SECONDS

    @staticmethod
    def _remote_error_payload(command_type: str, response: Dict[str, Any]):
        error = response.get("error")
        if isinstance(error, dict):
            message = error.get("message") or response.get("message") or "Unknown error from Ableton"
            code = error.get("code", response.get("code"))
            details = error.get("details", error.get("data", response.get("details")))
        else:
            message = response.get("message") or "Unknown error from Ableton"
            code = response.get("code", response.get("error_code"))
            details = response.get("details")
        return AbletonRemoteError(
            str(message), command=command_type, code=code, details=details
        )

    def send_command(self, command_type: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Send a command to Ableton and return the response"""
        if not self.sock and not self.connect():
            raise AbletonConnectionError(
                "Not connected to Ableton", command=command_type
            )

        command = {
            "type": command_type,
            "params": params or {}
        }

        timeout = self.timeout_for_command(command_type)
        try:
            logger.info(f"Sending command: {command_type} with params: {params}")

            # Send the command
            self.sock.sendall(json.dumps(command).encode('utf-8'))
            logger.info(f"Command sent, waiting for response...")
            self.sock.settimeout(timeout)

            # Receive the response
            response_data = self.receive_full_response(self.sock)
            logger.info(f"Received {len(response_data)} bytes of data")

            # Parse the response
            response = json.loads(response_data.decode('utf-8'))
            logger.info(f"Response parsed, status: {response.get('status', 'unknown')}")

            if response.get("status") == "error":
                logger.error(f"Ableton error: {response.get('message')}")
                raise self._remote_error_payload(command_type, response)

            return response.get("result", {})
        except socket.timeout:
            logger.error("Socket timeout while waiting for response from Ableton")
            self.disconnect()
            raise AbletonTimeoutError(
                f"Timeout waiting for Ableton response after {timeout:.1f}s",
                command=command_type,
                code="socket_timeout",
                details={"timeout_seconds": timeout},
            )
        except (ConnectionError, BrokenPipeError, ConnectionResetError) as e:
            logger.error(f"Socket connection error: {str(e)}")
            self.disconnect()
            raise AbletonConnectionError(
                f"Connection to Ableton lost: {str(e)}", command=command_type
            ) from e
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON response from Ableton: {str(e)}")
            if 'response_data' in locals() and response_data:
                logger.error(f"Raw response (first 200 bytes): {response_data[:200]}")
            self.disconnect()
            raise AbletonProtocolError(
                f"Invalid response from Ableton: {str(e)}", command=command_type
            ) from e
        except AbletonError:
            # Remote errors are operation failures, not socket failures. Keep a
            # healthy connection available for the next command.
            raise
        except Exception as e:
            logger.error(f"Error communicating with Ableton: {str(e)}")
            self.disconnect()
            raise AbletonError(
                f"Communication error with Ableton: {str(e)}", command=command_type
            ) from e

@asynccontextmanager
async def server_lifespan(server: FastMCP) -> AsyncIterator[Dict[str, Any]]:
    """Manage server startup and shutdown lifecycle"""
    try:
        logger.info("AbletonMCP server starting up")

        # Record startup event for telemetry
        try:
            record_startup()
        except Exception as e:
            logger.debug(f"Failed to record startup telemetry: {e}")

        try:
            ableton = get_ableton_connection()
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
    lifespan=server_lifespan
)

# Global connection for resources
_ableton_connection = None

def get_ableton_connection():
    """Get or create a persistent Ableton connection"""
    global _ableton_connection

    if _ableton_connection is not None and _ableton_connection.sock is not None:
        try:
            # Check if the socket is still alive by peeking for data
            # MSG_PEEK + MSG_DONTWAIT will raise BlockingIOError if alive but no data,
            # or return b'' if the remote end has closed the connection.
            _ableton_connection.sock.setblocking(False)
            try:
                data = _ableton_connection.sock.recv(1, socket.MSG_PEEK)
                if data == b'':
                    raise ConnectionError("Remote end closed")
            except BlockingIOError:
                pass  # Socket is alive, just no data waiting — this is normal
            finally:
                _ableton_connection.sock.setblocking(True)
            return _ableton_connection
        except Exception as e:
            logger.warning(f"Existing connection is no longer valid: {str(e)}")
            try:
                _ableton_connection.disconnect()
            except:
                pass
            _ableton_connection = None
    
    # Connection doesn't exist or is invalid, create a new one
    if _ableton_connection is None:
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            try:
                logger.info(f"Connecting to Ableton at {ABLETON_HOST}:{ABLETON_PORT} (attempt {attempt}/{max_attempts})...")
                _ableton_connection = AbletonConnection(host=ABLETON_HOST, port=ABLETON_PORT)
                if _ableton_connection.connect():
                    logger.info("Created new persistent connection to Ableton")
                    return _ableton_connection
                else:
                    _ableton_connection = None
            except Exception as e:
                logger.error(f"Connection attempt {attempt} failed: {str(e)}")
                if _ableton_connection:
                    _ableton_connection.disconnect()
                    _ableton_connection = None

            if attempt < max_attempts:
                import time
                time.sleep(1.0)
        
        # If we get here, all connection attempts failed
        if _ableton_connection is None:
            logger.error("Failed to connect to Ableton after multiple attempts")
            raise Exception("Could not connect to Ableton. Make sure the Remote Script is running.")
    
    return _ableton_connection


class DevicePathItem(TypedDict, total=False):
    """One expected device in a rack/chain path."""

    type: Literal["device", "chain"]
    kind: Literal["device", "chain"]
    index: int
    device_index: int
    chain_index: int
    expected_name: str
    expected_device_name: str
    expected_chain_name: str
    expected_class_name: str
    expected_device_class_name: str
    expected_chain_class_name: str


class TrackSelector(TypedDict, total=False):
    """A track subset item with an optional return/main kind."""

    track_index: int
    expected_track_name: str
    track_kind: Literal["track", "return", "main", "master"]


class ClipNote(TypedDict, total=False):
    """JSON-safe MIDI note fields accepted by Live 12 when exposed."""

    pitch: int
    start_time: float
    duration: float
    velocity: int
    mute: bool
    probability: float
    velocity_deviation: float
    release_velocity: int


class MixerParameterChange(TypedDict, total=False):
    track_index: int
    expected_track_name: str
    track_kind: Literal["track", "return", "main", "master"]
    parameter_name: str
    parameter_index: int
    expected_parameter_name: str
    value: Union[bool, int, float]
    expected_current_value: Union[bool, int, float]
    tolerance: float


class DeviceParameterChange(TypedDict, total=False):
    track_index: int
    expected_track_name: str
    track_kind: Literal["track", "return", "main", "master"]
    device_path: List[DevicePathItem]
    parameter_index: int
    expected_parameter_name: str
    value: Union[bool, int, float]
    expected_current_value: Union[bool, int, float]
    tolerance: float


def _structured_error(command_type: str, exc: Exception) -> Dict[str, Any]:
    """Serialize a command failure without losing Remote Script details."""
    if isinstance(exc, AbletonError):
        error = exc.as_dict()
        if error.get("command") is None:
            error["command"] = command_type
        return error
    return {
        "type": "tool_error",
        "message": str(exc),
        "command": command_type,
        "code": None,
        "details": None,
    }


def _production_command(
    command_type: str, params: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Run one production-control command through the existing connection."""
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command(command_type, params or {})
        return {
            "status": "success",
            "command": command_type,
            "result": result,
        }
    except Exception as exc:
        logger.error("Error running %s: %s", command_type, exc)
        return {
            "status": "error",
            "command": command_type,
            "error": _structured_error(command_type, exc),
        }


# Core Tool endpoints

@mcp.tool()
@telemetry_tool("get_session_info")
def get_session_info(ctx: Context, user_prompt: str = "") -> str:
    """Get detailed information about the current Ableton session

    Parameters:
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_session_info")
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting session info from Ableton: {str(e)}")
        return f"Error getting session info: {str(e)}"

@mcp.tool()
@telemetry_tool("get_track_info")
def get_track_info(ctx: Context, track_index: int, user_prompt: str = "") -> str:
    """
    Get detailed information about a specific track in Ableton.

    Parameters:
    - track_index: The index of the track to get information about
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_track_info", {"track_index": track_index})
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting track info from Ableton: {str(e)}")
        return f"Error getting track info: {str(e)}"

@mcp.tool()
@telemetry_tool("create_midi_track")
def create_midi_track(ctx: Context, index: int = -1, user_prompt: str = "") -> str:
    """
    Create a new MIDI track in the Ableton session.

    Parameters:
    - index: The index to insert the track at (-1 = end of list)
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("create_midi_track", {"index": index})
        return f"Created new MIDI track: {result.get('name', 'unknown')}"
    except Exception as e:
        logger.error(f"Error creating MIDI track: {str(e)}")
        return f"Error creating MIDI track: {str(e)}"


@mcp.tool()
@rich_telemetry_tool("set_track_name")
def set_track_name(ctx: Context, track_index: int, name: str, user_prompt: str = "") -> str:
    """
    Set the name of a track.

    Parameters:
    - track_index: The index of the track to rename
    - name: The new name for the track
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_track_name", {"track_index": track_index, "name": name})
        return f"Renamed track to: {result.get('name', name)}"
    except Exception as e:
        logger.error(f"Error setting track name: {str(e)}")
        return f"Error setting track name: {str(e)}"

@mcp.tool()
@rich_telemetry_tool("create_clip")
def create_clip(ctx: Context, track_index: int, clip_index: int, length: float = 4.0, user_prompt: str = "") -> str:
    """
    Create a new MIDI clip in the specified track and clip slot.

    Parameters:
    - track_index: The index of the track to create the clip in
    - clip_index: The index of the clip slot to create the clip in
    - length: The length of the clip in beats (default: 4.0)
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("create_clip", {
            "track_index": track_index, 
            "clip_index": clip_index, 
            "length": length
        })
        return f"Created new clip at track {track_index}, slot {clip_index} with length {length} beats"
    except Exception as e:
        logger.error(f"Error creating clip: {str(e)}")
        return f"Error creating clip: {str(e)}"

@mcp.tool()
@rich_telemetry_tool("create_audio_clip")
def create_audio_clip(ctx: Context, track_index: int, clip_index: int, path: str, user_prompt: str = "") -> str:
    """
    Create a new audio clip in an audio track's clip slot by importing a file.

    Requires Ableton Live 12.0.5 or newer — the underlying
    ClipSlot.create_audio_clip Live API was introduced in 12.0.5 and is not
    available in earlier 12.0.x releases.

    Parameters:
    - track_index: The index of the audio track to create the clip in
    - clip_index: The index of the clip slot to create the clip in
    - path: Absolute path to a supported audio file (e.g. a .wav). The target
      track must be an audio track and the clip slot must be empty.
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("create_audio_clip", {
            "track_index": track_index,
            "clip_index": clip_index,
            "path": path
        })
        return f"Created audio clip '{result.get('name', 'clip')}' at track {track_index}, slot {clip_index} (length {result.get('length', '?')} beats)"
    except Exception as e:
        logger.error(f"Error creating audio clip: {str(e)}")
        return f"Error creating audio clip: {str(e)}"

@mcp.tool()
@rich_telemetry_tool("add_notes_to_clip", capture_notes=True)
def add_notes_to_clip(
    ctx: Context,
    track_index: int,
    clip_index: int,
    notes: List[Dict[str, Union[int, float, bool]]],
    user_prompt: str = ""
) -> str:
    """
    Add MIDI notes to a clip.

    Parameters:
    - track_index: The index of the track containing the clip
    - clip_index: The index of the clip slot containing the clip
    - notes: List of note dictionaries, each with pitch, start_time, duration, velocity, and mute
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("add_notes_to_clip", {
            "track_index": track_index,
            "clip_index": clip_index,
            "notes": notes
        })
        return f"Added {len(notes)} notes to clip at track {track_index}, slot {clip_index}"
    except Exception as e:
        logger.error(f"Error adding notes to clip: {str(e)}")
        return f"Error adding notes to clip: {str(e)}"

@mcp.tool()
@rich_telemetry_tool("set_clip_name")
def set_clip_name(ctx: Context, track_index: int, clip_index: int, name: str, user_prompt: str = "") -> str:
    """
    Set the name of a clip.

    Parameters:
    - track_index: The index of the track containing the clip
    - clip_index: The index of the clip slot containing the clip
    - name: The new name for the clip
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_clip_name", {
            "track_index": track_index,
            "clip_index": clip_index,
            "name": name
        })
        return f"Renamed clip at track {track_index}, slot {clip_index} to '{name}'"
    except Exception as e:
        logger.error(f"Error setting clip name: {str(e)}")
        return f"Error setting clip name: {str(e)}"

@mcp.tool()
@rich_telemetry_tool("set_tempo")
def set_tempo(ctx: Context, tempo: float, user_prompt: str = "") -> str:
    """
    Set the tempo of the Ableton session.

    Parameters:
    - tempo: The new tempo in BPM
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_tempo", {"tempo": tempo})
        return f"Set tempo to {tempo} BPM"
    except Exception as e:
        logger.error(f"Error setting tempo: {str(e)}")
        return f"Error setting tempo: {str(e)}"


@mcp.tool()
@rich_telemetry_tool("load_instrument_or_effect")
def load_instrument_or_effect(ctx: Context, track_index: int, uri: str, user_prompt: str = "") -> str:
    """
    Load an instrument or effect onto a track using its URI.

    Parameters:
    - track_index: The index of the track to load the instrument on
    - uri: The URI of the instrument or effect to load (e.g., 'query:Synths#Instrument%20Rack:Bass:FileId_5116')
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("load_browser_item", {
            "track_index": track_index,
            "item_uri": uri
        })
        
        # Check if the instrument was loaded successfully
        if result.get("loaded", False):
            new_devices = result.get("new_devices", [])
            if new_devices:
                return f"Loaded instrument with URI '{uri}' on track {track_index}. New devices: {', '.join(new_devices)}"
            else:
                devices = result.get("devices_after", [])
                return f"Loaded instrument with URI '{uri}' on track {track_index}. Devices on track: {', '.join(devices)}"
        else:
            return f"Failed to load instrument with URI '{uri}'"
    except Exception as e:
        logger.error(f"Error loading instrument by URI: {str(e)}")
        return f"Error loading instrument by URI: {str(e)}"

@mcp.tool()
@telemetry_tool("fire_clip")
def fire_clip(ctx: Context, track_index: int, clip_index: int, user_prompt: str = "") -> str:
    """
    Start playing a clip.

    Parameters:
    - track_index: The index of the track containing the clip
    - clip_index: The index of the clip slot containing the clip
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("fire_clip", {
            "track_index": track_index,
            "clip_index": clip_index
        })
        return f"Started playing clip at track {track_index}, slot {clip_index}"
    except Exception as e:
        logger.error(f"Error firing clip: {str(e)}")
        return f"Error firing clip: {str(e)}"

@mcp.tool()
@telemetry_tool("stop_clip")
def stop_clip(ctx: Context, track_index: int, clip_index: int, user_prompt: str = "") -> str:
    """
    Stop playing a clip.

    Parameters:
    - track_index: The index of the track containing the clip
    - clip_index: The index of the clip slot containing the clip
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("stop_clip", {
            "track_index": track_index,
            "clip_index": clip_index
        })
        return f"Stopped clip at track {track_index}, slot {clip_index}"
    except Exception as e:
        logger.error(f"Error stopping clip: {str(e)}")
        return f"Error stopping clip: {str(e)}"

@mcp.tool()
@telemetry_tool("start_playback")
def start_playback(ctx: Context, user_prompt: str = "") -> str:
    """Start playing the Ableton session.

    Parameters:
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("start_playback")
        return "Started playback"
    except Exception as e:
        logger.error(f"Error starting playback: {str(e)}")
        return f"Error starting playback: {str(e)}"

@mcp.tool()
@telemetry_tool("stop_playback")
def stop_playback(ctx: Context, user_prompt: str = "") -> str:
    """Stop playing the Ableton session.

    Parameters:
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("stop_playback")
        return "Stopped playback"
    except Exception as e:
        logger.error(f"Error stopping playback: {str(e)}")
        return f"Error stopping playback: {str(e)}"

@mcp.tool()
@rich_telemetry_tool("get_browser_tree")
def get_browser_tree(ctx: Context, category_type: str = "all", user_prompt: str = "") -> str:
    """
    Get a hierarchical tree of browser categories from Ableton.

    Parameters:
    - category_type: Type of categories to get ('all', 'instruments', 'sounds', 'drums', 'audio_effects', 'midi_effects')
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_browser_tree", {
            "category_type": category_type
        })
        
        # Check if we got any categories
        if "available_categories" in result and len(result.get("categories", [])) == 0:
            available_cats = result.get("available_categories", [])
            return (f"No categories found for '{category_type}'. "
                   f"Available browser categories: {', '.join(available_cats)}")
        
        # Format the tree in a more readable way
        total_folders = result.get("total_folders", 0)
        formatted_output = f"Browser tree for '{category_type}' (showing {total_folders} folders):\n\n"
        
        def format_tree(item, indent=0):
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
                    output += format_tree(child, indent + 1)
            return output
        
        # Format each category
        for category in result.get("categories", []):
            formatted_output += format_tree(category)
            formatted_output += "\n"
        
        return formatted_output
    except Exception as e:
        error_msg = str(e)
        if "Browser is not available" in error_msg:
            logger.error(f"Browser is not available in Ableton: {error_msg}")
            return f"Error: The Ableton browser is not available. Make sure Ableton Live is fully loaded and try again."
        elif "Could not access Live application" in error_msg:
            logger.error(f"Could not access Live application: {error_msg}")
            return f"Error: Could not access the Ableton Live application. Make sure Ableton Live is running and the Remote Script is loaded."
        else:
            logger.error(f"Error getting browser tree: {error_msg}")
            return f"Error getting browser tree: {error_msg}"

@mcp.tool()
@rich_telemetry_tool("get_browser_items_at_path")
def get_browser_items_at_path(ctx: Context, path: str, user_prompt: str = "") -> str:
    """
    Get browser items at a specific path in Ableton's browser.

    Parameters:
    - path: Path in the format "category/folder/subfolder"
            where category is one of the available browser categories in Ableton
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_browser_items_at_path", {
            "path": path
        })
        
        # Check if there was an error with available categories
        if "error" in result and "available_categories" in result:
            error = result.get("error", "")
            available_cats = result.get("available_categories", [])
            return (f"Error: {error}\n"
                   f"Available browser categories: {', '.join(available_cats)}")
        
        return json.dumps(result, indent=2)
    except Exception as e:
        error_msg = str(e)
        if "Browser is not available" in error_msg:
            logger.error(f"Browser is not available in Ableton: {error_msg}")
            return f"Error: The Ableton browser is not available. Make sure Ableton Live is fully loaded and try again."
        elif "Could not access Live application" in error_msg:
            logger.error(f"Could not access Live application: {error_msg}")
            return f"Error: Could not access the Ableton Live application. Make sure Ableton Live is running and the Remote Script is loaded."
        elif "Unknown or unavailable category" in error_msg:
            logger.error(f"Invalid browser category: {error_msg}")
            return f"Error: {error_msg}. Please check the available categories using get_browser_tree."
        elif "Path part" in error_msg and "not found" in error_msg:
            logger.error(f"Path not found: {error_msg}")
            return f"Error: {error_msg}. Please check the path and try again."
        else:
            logger.error(f"Error getting browser items at path: {error_msg}")
            return f"Error getting browser items at path: {error_msg}"

@mcp.tool()
@rich_telemetry_tool("load_drum_kit")
def load_drum_kit(ctx: Context, track_index: int, rack_uri: str, kit_path: str, user_prompt: str = "") -> str:
    """
    Load a drum rack and then load a specific drum kit into it.

    Parameters:
    - track_index: The index of the track to load on
    - rack_uri: The URI of the drum rack to load (e.g., 'Drums/Drum Rack')
    - kit_path: Path to the drum kit inside the browser (e.g., 'drums/acoustic/kit1')
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        ableton = get_ableton_connection()
        
        # Step 1: Load the drum rack
        result = ableton.send_command("load_browser_item", {
            "track_index": track_index,
            "item_uri": rack_uri
        })
        
        if not result.get("loaded", False):
            return f"Failed to load drum rack with URI '{rack_uri}'"
        
        # Step 2: Get the drum kit items at the specified path
        kit_result = ableton.send_command("get_browser_items_at_path", {
            "path": kit_path
        })
        
        if "error" in kit_result:
            return f"Loaded drum rack but failed to find drum kit: {kit_result.get('error')}"
        
        # Step 3: Find a loadable drum kit
        kit_items = kit_result.get("items", [])
        loadable_kits = [item for item in kit_items if item.get("is_loadable", False)]
        
        if not loadable_kits:
            return f"Loaded drum rack but no loadable drum kits found at '{kit_path}'"
        
        # Step 4: Load the first loadable kit
        kit_uri = loadable_kits[0].get("uri")
        load_result = ableton.send_command("load_browser_item", {
            "track_index": track_index,
            "item_uri": kit_uri
        })
        
        return f"Loaded drum rack and kit '{loadable_kits[0].get('name')}' on track {track_index}"
    except Exception as e:
        logger.error(f"Error loading drum kit: {str(e)}")
        return f"Error loading drum kit: {str(e)}"

# ── Arrangement view tools ────────────────────────────────────────────────────

@mcp.tool()
@telemetry_tool("switch_to_arrangement_view")
def switch_to_arrangement_view(ctx: Context, user_prompt: str = "") -> str:
    """Switch Ableton's main window to the Arrangement view.

    Parameters:
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        ableton = get_ableton_connection()
        ableton.send_command("switch_to_arrangement_view")
        return "Switched to Arrangement view"
    except Exception as e:
        logger.error(f"Error switching to arrangement view: {str(e)}")
        return f"Error switching to arrangement view: {str(e)}"


@mcp.tool()
@rich_telemetry_tool("set_arrangement_time")
def set_arrangement_time(ctx: Context, time: float, user_prompt: str = "") -> str:
    """
    Move the arrangement playhead to a specific position.

    Parameters:
    - time: Position in beats from the start of the arrangement (e.g. 8.0 = bar 3 in 4/4)
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_current_song_time", {"time": time})
        return f"Playhead moved to beat {result.get('current_song_time', time)}"
    except Exception as e:
        logger.error(f"Error setting arrangement time: {str(e)}")
        return f"Error setting arrangement time: {str(e)}"


@mcp.tool()
@telemetry_tool("get_arrangement_clips")
def get_arrangement_clips(
    ctx: Context,
    track_index: int,
    expected_track_name: Optional[str] = None,
    user_prompt: str = "",
) -> Dict[str, Any]:
    """
    List all clips placed in the Arrangement timeline for a track.

    Returns each clip's name, start_time, end_time, length, and type.

    Parameters:
    - track_index: The index of the track to inspect
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    params: Dict[str, Any] = {"track_index": track_index}
    if expected_track_name is not None:
        params["expected_track_name"] = expected_track_name
    return _production_command("get_arrangement_clips", params)


@mcp.tool()
@rich_telemetry_tool("duplicate_to_arrangement")
def duplicate_to_arrangement(
    ctx: Context,
    track_index: int,
    clip_index: int,
    destination_time: float,
    user_prompt: str = ""
) -> str:
    """
    Copy a Session-view clip into the Arrangement timeline.

    Uses Live's track.duplicate_clip_to_arrangement() API (Live 11 / 12).
    The clip is placed at destination_time beats from the start of the
    arrangement on the same track it lives in.

    Typical workflow:
      1. create_clip / add_notes_to_clip to build a Session clip
      2. Call duplicate_to_arrangement once per bar/section you need
      3. Call switch_to_arrangement_view to confirm the result in Live

    Parameters:
    - track_index:       Index of the track that owns the Session clip
    - clip_index:        Index of the clip slot in that track (Session view)
    - destination_time:  Beat position in the arrangement to place the clip
                         (e.g. 0.0 = start, 8.0 = bar 3 in 4/4)
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command(
            "duplicate_session_clip_to_arrangement",
            {
                "track_index": track_index,
                "clip_index": clip_index,
                "destination_time": destination_time
            }
        )
        clip_name = result.get("clip_name", "clip")
        track_name = result.get("track_name", f"track {track_index}")
        return (
            f"Duplicated '{clip_name}' from Session slot {clip_index} "
            f"on '{track_name}' to arrangement at beat {destination_time}"
        )
    except Exception as e:
        logger.error(f"Error duplicating clip to arrangement: {str(e)}")
        return f"Error duplicating clip to arrangement: {str(e)}"


@mcp.tool()
@telemetry_tool("get_capabilities")
def get_capabilities(ctx: Context, user_prompt: str = "") -> Dict[str, Any]:
    """Read Live version and safe LOM capability probes from the Remote Script."""
    return _production_command("get_capabilities")


@mcp.tool()
@telemetry_tool("get_mixer_parameters")
def get_mixer_parameters(
    ctx: Context,
    track_index: int,
    expected_track_name: str,
    track_kind: Literal["track", "return", "main", "master"] = "track",
    parameters: Optional[List[str]] = None,
    user_prompt: str = "",
) -> Dict[str, Any]:
    """Read mixer values for a validated track, return track, or Main track."""
    params: Dict[str, Any] = {
        "track_index": track_index,
        "expected_track_name": expected_track_name,
        "track_kind": track_kind,
    }
    if parameters is not None:
        params["parameters"] = parameters
    return _production_command("get_mixer_parameters", params)


@mcp.tool()
@telemetry_tool("set_mixer_parameter")
def set_mixer_parameter(
    ctx: Context,
    track_index: int,
    expected_track_name: str,
    parameter_name: str,
    value: Union[bool, int, float],
    track_kind: Literal["track", "return", "main", "master"] = "track",
    parameter_index: Optional[int] = None,
    expected_parameter_name: Optional[str] = None,
    expected_current_value: Optional[Union[bool, int, float]] = None,
    tolerance: float = 0.0,
    dry_run: bool = False,
    overwrite: bool = False,
    user_prompt: str = "",
) -> Dict[str, Any]:
    """Set one mixer value after Remote Script target resolution and preflight."""
    params: Dict[str, Any] = {
        "track_index": track_index,
        "expected_track_name": expected_track_name,
        "track_kind": track_kind,
        "parameter_name": parameter_name,
        "value": value,
        "tolerance": tolerance,
        "dry_run": dry_run,
        "overwrite": overwrite,
    }
    if parameter_index is not None:
        params["parameter_index"] = parameter_index
    if expected_parameter_name is not None:
        params["expected_parameter_name"] = expected_parameter_name
    if expected_current_value is not None:
        params["expected_current_value"] = expected_current_value
    return _production_command("set_mixer_parameter", params)


@mcp.tool()
@telemetry_tool("set_mixer_parameters")
def set_mixer_parameters(
    ctx: Context,
    parameters: List[MixerParameterChange],
    dry_run: bool = False,
    overwrite: bool = False,
    user_prompt: str = "",
) -> Dict[str, Any]:
    """Preflight and apply a validated batch of mixer changes atomically."""
    return _production_command(
        "set_mixer_parameters",
        {"parameters": parameters, "dry_run": dry_run, "overwrite": overwrite},
    )


@mcp.tool()
@telemetry_tool("get_device_parameters")
def get_device_parameters(
    ctx: Context,
    track_index: int,
    expected_track_name: str,
    device_path: List[DevicePathItem],
    track_kind: Literal["track", "return", "main", "master"] = "track",
    parameter_index: Optional[int] = None,
    expected_parameter_name: Optional[str] = None,
    parameters: Optional[List[int]] = None,
    user_prompt: str = "",
) -> Dict[str, Any]:
    """Read parameters for a device path validated by index, name, and class."""
    params: Dict[str, Any] = {
        "track_index": track_index,
        "expected_track_name": expected_track_name,
        "track_kind": track_kind,
        "device_path": device_path,
    }
    if parameter_index is not None:
        params["parameter_index"] = parameter_index
    if expected_parameter_name is not None:
        params["expected_parameter_name"] = expected_parameter_name
    if parameters is not None:
        params["parameters"] = parameters
    return _production_command("get_device_parameters", params)


@mcp.tool()
@telemetry_tool("set_device_parameter")
def set_device_parameter(
    ctx: Context,
    track_index: int,
    expected_track_name: str,
    device_path: List[DevicePathItem],
    parameter_index: int,
    expected_parameter_name: str,
    value: Union[bool, int, float],
    track_kind: Literal["track", "return", "main", "master"] = "track",
    expected_current_value: Optional[Union[bool, int, float]] = None,
    tolerance: float = 0.0,
    dry_run: bool = False,
    overwrite: bool = False,
    user_prompt: str = "",
) -> Dict[str, Any]:
    """Set one continuous or quantized device parameter and read it back."""
    params: Dict[str, Any] = {
        "track_index": track_index,
        "expected_track_name": expected_track_name,
        "track_kind": track_kind,
        "device_path": device_path,
        "parameter_index": parameter_index,
        "expected_parameter_name": expected_parameter_name,
        "value": value,
        "tolerance": tolerance,
        "dry_run": dry_run,
        "overwrite": overwrite,
    }
    if expected_current_value is not None:
        params["expected_current_value"] = expected_current_value
    return _production_command("set_device_parameter", params)


@mcp.tool()
@telemetry_tool("set_device_parameters")
def set_device_parameters(
    ctx: Context,
    parameters: List[DeviceParameterChange],
    dry_run: bool = False,
    overwrite: bool = False,
    user_prompt: str = "",
) -> Dict[str, Any]:
    """Preflight and apply a batch of nested device parameter changes."""
    return _production_command(
        "set_device_parameters",
        {"parameters": parameters, "dry_run": dry_run, "overwrite": overwrite},
    )


@mcp.tool()
@telemetry_tool("get_clip_notes")
def get_clip_notes(
    ctx: Context,
    track_index: int,
    expected_track_name: str,
    clip_index: int,
    expected_clip_name: str,
    from_time: Optional[float] = None,
    from_pitch: Optional[int] = None,
    time_span: Optional[float] = None,
    pitch_span: Optional[int] = None,
    user_prompt: str = "",
) -> Dict[str, Any]:
    """Read MIDI notes from one strictly identified Session clip."""
    params: Dict[str, Any] = {
        "track_index": track_index,
        "expected_track_name": expected_track_name,
        "clip_index": clip_index,
        "expected_clip_name": expected_clip_name,
    }
    if from_time is not None:
        params["from_time"] = from_time
    if from_pitch is not None:
        params["from_pitch"] = from_pitch
    if time_span is not None:
        params["time_span"] = time_span
    if pitch_span is not None:
        params["pitch_span"] = pitch_span
    return _production_command("get_clip_notes", params)


@mcp.tool()
@telemetry_tool("replace_clip_notes")
def replace_clip_notes(
    ctx: Context,
    track_index: int,
    expected_track_name: str,
    clip_index: int,
    expected_clip_name: str,
    notes: List[ClipNote],
    from_time: Optional[float] = None,
    from_pitch: Optional[int] = None,
    time_span: Optional[float] = None,
    pitch_span: Optional[int] = None,
    dry_run: bool = False,
    overwrite: bool = False,
    user_prompt: str = "",
) -> Dict[str, Any]:
    """Replace a clip or range of notes with Remote Script read-back/rollback."""
    params: Dict[str, Any] = {
        "track_index": track_index,
        "expected_track_name": expected_track_name,
        "clip_index": clip_index,
        "expected_clip_name": expected_clip_name,
        "notes": notes,
        "dry_run": dry_run,
        "overwrite": overwrite,
    }
    if from_time is not None:
        params["from_time"] = from_time
    if from_pitch is not None:
        params["from_pitch"] = from_pitch
    if time_span is not None:
        params["time_span"] = time_span
    if pitch_span is not None:
        params["pitch_span"] = pitch_span
    return _production_command("replace_clip_notes", params)


@mcp.tool()
@telemetry_tool("clear_clip_notes")
def clear_clip_notes(
    ctx: Context,
    track_index: int,
    expected_track_name: str,
    clip_index: int,
    expected_clip_name: str,
    from_time: Optional[float] = None,
    from_pitch: Optional[int] = None,
    time_span: Optional[float] = None,
    pitch_span: Optional[int] = None,
    dry_run: bool = False,
    overwrite: bool = False,
    user_prompt: str = "",
) -> Dict[str, Any]:
    """Clear all notes or one time range from a strictly identified clip."""
    params: Dict[str, Any] = {
        "track_index": track_index,
        "expected_track_name": expected_track_name,
        "clip_index": clip_index,
        "expected_clip_name": expected_clip_name,
        "dry_run": dry_run,
        "overwrite": overwrite,
    }
    if from_time is not None:
        params["from_time"] = from_time
    if from_pitch is not None:
        params["from_pitch"] = from_pitch
    if time_span is not None:
        params["time_span"] = time_span
    if pitch_span is not None:
        params["pitch_span"] = pitch_span
    return _production_command("clear_clip_notes", params)


@mcp.tool()
@telemetry_tool("get_clip_properties")
def get_clip_properties(
    ctx: Context,
    track_index: int,
    expected_track_name: str,
    clip_index: int,
    expected_clip_name: str,
    user_prompt: str = "",
) -> Dict[str, Any]:
    """Read properties for one strictly identified Session clip."""
    return _production_command(
        "get_clip_properties",
        {
            "track_index": track_index,
            "expected_track_name": expected_track_name,
            "clip_index": clip_index,
            "expected_clip_name": expected_clip_name,
        },
    )


@mcp.tool()
@telemetry_tool("get_output_meter_levels")
def get_output_meter_levels(
    ctx: Context,
    track_index: int,
    expected_track_name: str,
    track_kind: Literal["track", "return", "main", "master"] = "track",
    user_prompt: str = "",
) -> Dict[str, Any]:
    """Read current output meter levels for one strictly identified track."""
    return _production_command(
        "get_output_meter_levels",
        {
            "track_index": track_index,
            "expected_track_name": expected_track_name,
            "track_kind": track_kind,
        },
    )


@mcp.tool()
@telemetry_tool("set_clip_loop")
def set_clip_loop(
    ctx: Context,
    track_index: int,
    expected_track_name: str,
    clip_index: int,
    expected_clip_name: str,
    loop: Optional[bool] = None,
    loop_start: Optional[float] = None,
    loop_end: Optional[float] = None,
    start_marker: Optional[float] = None,
    end_marker: Optional[float] = None,
    dry_run: bool = False,
    overwrite: bool = False,
    user_prompt: str = "",
) -> Dict[str, Any]:
    """Set clip loop and marker positions with strict clip resolution."""
    params: Dict[str, Any] = {
        "track_index": track_index,
        "expected_track_name": expected_track_name,
        "clip_index": clip_index,
        "expected_clip_name": expected_clip_name,
        "dry_run": dry_run,
        "overwrite": overwrite,
    }
    if loop is not None:
        params["loop"] = loop
    for name, value in (
        ("loop_start", loop_start),
        ("loop_end", loop_end),
        ("start_marker", start_marker),
        ("end_marker", end_marker),
    ):
        if value is not None:
            params[name] = value
    return _production_command("set_clip_loop", params)


@mcp.tool()
@telemetry_tool("delete_session_clip")
def delete_session_clip(
    ctx: Context,
    track_index: int,
    expected_track_name: str,
    clip_index: int,
    expected_clip_name: str,
    dry_run: bool = False,
    overwrite: bool = False,
    user_prompt: str = "",
) -> Dict[str, Any]:
    """Delete only a Session clip whose expected name matches exactly."""
    return _production_command(
        "delete_session_clip",
        {
            "track_index": track_index,
            "expected_track_name": expected_track_name,
            "clip_index": clip_index,
            "expected_clip_name": expected_clip_name,
            "dry_run": dry_run,
            "overwrite": overwrite,
        },
    )


@mcp.tool()
@telemetry_tool("duplicate_session_clip")
def duplicate_session_clip(
    ctx: Context,
    source_track_index: int,
    expected_source_track_name: str,
    source_clip_index: int,
    expected_source_clip_name: str,
    destination_track_index: int,
    expected_destination_track_name: str,
    destination_clip_index: int,
    expected_destination_clip_name: Optional[str] = None,
    source_track_kind: Literal["track", "return", "main", "master"] = "track",
    destination_track_kind: Literal["track", "return", "main", "master"] = "track",
    overwrite: bool = False,
    dry_run: bool = False,
    user_prompt: str = "",
) -> Dict[str, Any]:
    """Preflight and duplicate one Session clip to one destination slot."""
    params: Dict[str, Any] = {
        "source_track_index": source_track_index,
        "expected_source_track_name": expected_source_track_name,
        "source_clip_index": source_clip_index,
        "expected_source_clip_name": expected_source_clip_name,
        "destination_track_index": destination_track_index,
        "expected_destination_track_name": expected_destination_track_name,
        "destination_clip_index": destination_clip_index,
        "source_track_kind": source_track_kind,
        "destination_track_kind": destination_track_kind,
        "overwrite": overwrite,
        "dry_run": dry_run,
    }
    if expected_destination_clip_name is not None:
        params["expected_destination_clip_name"] = expected_destination_clip_name
    return _production_command("duplicate_session_clip", params)


@mcp.tool()
@telemetry_tool("duplicate_session_scene_clips")
def duplicate_session_scene_clips(
    ctx: Context,
    source_scene_index: int,
    expected_source_scene_name: str,
    destination_scene_index: int,
    expected_destination_scene_name: Optional[str] = None,
    track_subset: Optional[List[TrackSelector]] = None,
    overwrite: bool = False,
    dry_run: bool = False,
    user_prompt: str = "",
) -> Dict[str, Any]:
    """Duplicate a scene with an optional explicit track subset after preflight."""
    params: Dict[str, Any] = {
        "source_scene_index": source_scene_index,
        "expected_source_scene_name": expected_source_scene_name,
        "destination_scene_index": destination_scene_index,
        "overwrite": overwrite,
        "dry_run": dry_run,
    }
    if expected_destination_scene_name is not None:
        params["expected_destination_scene_name"] = expected_destination_scene_name
    if track_subset is not None:
        params["track_subset"] = track_subset
    return _production_command("duplicate_session_scene_clips", params)


@mcp.tool()
@telemetry_tool("fire_scene")
def fire_scene(
    ctx: Context,
    scene_index: int,
    expected_scene_name: str,
    expected_global_quantization: Optional[int] = None,
    user_prompt: str = "",
) -> Dict[str, Any]:
    """Fire one scene after optionally verifying Live's global quantization."""
    params: Dict[str, Any] = {
        "scene_index": scene_index,
        "expected_scene_name": expected_scene_name,
    }
    if expected_global_quantization is not None:
        params["expected_global_quantization"] = expected_global_quantization
    return _production_command("fire_scene", params)


@mcp.tool()
@telemetry_tool("stop_all_clips")
def stop_all_clips(
    ctx: Context,
    track_subset: Optional[List[TrackSelector]] = None,
    quantized: Optional[bool] = None,
    dry_run: bool = False,
    user_prompt: str = "",
) -> Dict[str, Any]:
    """Stop Session clips, optionally limited to an explicit track subset."""
    params: Dict[str, Any] = {}
    if track_subset is not None:
        params["track_subset"] = track_subset
    if quantized is not None:
        params["quantized"] = quantized
    params["dry_run"] = dry_run
    return _production_command("stop_all_clips", params)


@mcp.tool()
@telemetry_tool("back_to_arrangement")
def back_to_arrangement(
    ctx: Context,
    dry_run: bool = False,
    user_prompt: str = "",
) -> Dict[str, Any]:
    """Return playback control to Arrangement when Live exposes the operation."""
    return _production_command("back_to_arrangement", {"dry_run": dry_run})


@mcp.tool()
@telemetry_tool("duplicate_session_clip_to_arrangement")
def duplicate_session_clip_to_arrangement(
    ctx: Context,
    track_index: int,
    expected_track_name: str,
    clip_index: int,
    expected_clip_name: str,
    destination_time: float,
    track_kind: Literal["track", "return", "main", "master"] = "track",
    dry_run: bool = False,
    overwrite: bool = False,
    user_prompt: str = "",
) -> Dict[str, Any]:
    """Copy one strictly identified Session clip into Arrangement."""
    return _production_command(
        "duplicate_session_clip_to_arrangement",
        {
            "track_index": track_index,
            "expected_track_name": expected_track_name,
            "clip_index": clip_index,
            "expected_clip_name": expected_clip_name,
            "destination_time": destination_time,
            "track_kind": track_kind,
            "dry_run": dry_run,
            "overwrite": overwrite,
        },
    )


@mcp.tool()
@telemetry_tool("delete_arrangement_clip")
def delete_arrangement_clip(
    ctx: Context,
    track_index: int,
    expected_track_name: str,
    expected_clip_name: str,
    start_time: float,
    duration: float,
    dry_run: bool = False,
    overwrite: bool = False,
    user_prompt: str = "",
) -> Dict[str, Any]:
    """Guarded deletion for one uniquely identified Arrangement clip."""
    return _production_command(
        "delete_arrangement_clip",
        {
            "track_index": track_index,
            "expected_track_name": expected_track_name,
            "expected_clip_name": expected_clip_name,
            "start_time": start_time,
            "duration": duration,
            "dry_run": dry_run,
            "overwrite": overwrite,
        },
    )


# Main execution
def main():
    """Run the MCP server"""
    mcp.run()

if __name__ == "__main__":
    main()
