# ableton_mcp_server.py
from mcp.server.fastmcp import FastMCP, Context
import socket
import json
import logging
import os
import threading
from dataclasses import dataclass, field
from contextlib import asynccontextmanager
from typing import AsyncIterator, Dict, Any, List, Union

from .telemetry import record_startup
from .telemetry_decorator import telemetry_tool, rich_telemetry_tool
from .dataset import dataset_enabled, get_recorder
from .dataset.trajectory_decorator import trajectory_tool

ABLETON_HOST = os.environ.get("ABLETON_HOST", "localhost")
ABLETON_PORT = int(os.environ.get("ABLETON_PORT", "9877"))

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("AbletonMCPServer")


class AbletonCommandError(Exception):
    """Live received the command and refused it (status "error").

    The connection is fine: the message is Live's own explanation
    (out-of-range index, master track can't be muted, ...).
    """


@dataclass
class AbletonConnection:
    host: str
    port: int
    sock: socket.socket = None

    # One socket, several threads: tool calls run on the MCP worker while the
    # passive poller drains events on its own thread. Serialise so their
    # sendall/recv pairs cannot interleave.
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

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
        with self._lock:
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
                        data = b''.join(chunks)
                        json.loads(data.decode('utf-8'))
                        logger.info(f"Received complete response ({len(data)} bytes)")
                        return data
                    except json.JSONDecodeError:
                        # Incomplete JSON, continue receiving
                        continue
                except socket.timeout:
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
            data = b''.join(chunks)
            logger.info(f"Returning data after receive completion ({len(data)} bytes)")
            try:
                json.loads(data.decode('utf-8'))
                return data
            except json.JSONDecodeError:
                raise Exception("Incomplete JSON response received")
        else:
            raise Exception("No data received")

    def send_command(self, command_type: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Send a command to Ableton and return the response.

        Serialised on ``self._lock``: the request and its response are one
        indivisible exchange on a shared socket. Holding the lock across the
        whole round-trip (including reconnect) is what keeps a concurrent
        caller from reading someone else's reply.
        """
        with self._lock:
            return self._send_command_locked(command_type, params)

    def _send_command_locked(self, command_type: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        if not self.sock and not self.connect():
            raise ConnectionError("Not connected to Ableton")

        command = {
            "type": command_type,
            "params": params or {}
        }
        
        # Check if this is a state-modifying command
        is_modifying_command = command_type in [
            "create_midi_track", "create_audio_track", "set_track_name",
            "create_clip", "create_audio_clip", "add_notes_to_clip", "set_clip_name",
            "delete_clip",
            "clear_notes_from_clip",
            "set_tempo", "fire_clip", "stop_clip", "set_device_parameter",
            "start_playback", "stop_playback", "load_instrument_or_effect",
            # Arrangement view commands
            "switch_to_arrangement_view", "set_current_song_time",
            "duplicate_session_clip_to_arrangement",
            "create_locator"
        ]

        # Commands whose work on Live's main thread can take noticeably longer
        # than the default modifying-command budget (e.g. importing/decoding a
        # large audio file). Give them a wider socket timeout so we don't time
        # out before the Remote Script's own queue does.
        long_running_commands = {"create_audio_clip": 65.0}
        
        try:
            logger.info(f"Sending command: {command_type} with params: {params}")
            
            # Send the command
            self.sock.sendall(json.dumps(command).encode('utf-8'))
            logger.info(f"Command sent, waiting for response...")
            
            # Set timeout based on command type
            if command_type in long_running_commands:
                timeout = long_running_commands[command_type]
            else:
                timeout = 15.0 if is_modifying_command else 10.0
            self.sock.settimeout(timeout)

            # Receive the response
            response_data = self.receive_full_response(self.sock)
            logger.info(f"Received {len(response_data)} bytes of data")

            # Parse the response
            response = json.loads(response_data.decode('utf-8'))
            logger.info(f"Response parsed, status: {response.get('status', 'unknown')}")

            if response.get("status") == "error":
                logger.error(f"Ableton error: {response.get('message')}")
                raise AbletonCommandError(response.get("message", "Unknown error from Ableton"))
            
            return response.get("result", {})
        except socket.timeout:
            logger.error("Socket timeout while waiting for response from Ableton")
            self.sock = None
            raise Exception("Timeout waiting for Ableton response")
        except (ConnectionError, BrokenPipeError, ConnectionResetError) as e:
            logger.error(f"Socket connection error: {str(e)}")
            self.sock = None
            raise Exception(f"Connection to Ableton lost: {str(e)}")
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON response from Ableton: {str(e)}")
            if 'response_data' in locals() and response_data:
                logger.error(f"Raw response (first 200 bytes): {response_data[:200]}")
            self.sock = None
            raise Exception(f"Invalid response from Ableton: {str(e)}")
        except AbletonCommandError:
            # A refusal from Live, not a transport failure: keep the socket
            # and pass Live's message through unchanged.
            raise
        except Exception as e:
            logger.error(f"Error communicating with Ableton: {str(e)}")
            self.sock = None
            raise Exception(f"Communication error with Ableton: {str(e)}")

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

        script_info = None
        try:
            ableton = get_ableton_connection()
            logger.info("Successfully connected to Ableton on startup")
            from .script_handshake import handshake

            script_info = handshake(ableton.send_command)
        except Exception as e:
            logger.warning(f"Could not connect to Ableton on startup: {str(e)}")
            logger.warning("Make sure the Ableton Remote Script is running")

        if dataset_enabled():
            try:
                recorder = get_recorder()
                if recorder:
                    logger.info(
                        "Dataset recording enabled → Supabase session %s",
                        recorder.session_id,
                    )
                from .script_handshake import script_has_capability
                from .dataset.passive_poller import start_passive_poller

                # Runs even without Live-UI events: it also settles implicit
                # preferences for agent actions.
                start_passive_poller()
                if not script_has_capability("drain_passive_events"):
                    logger.warning(
                        "Passive Live listeners unavailable — Remote Script outdated "
                        "or not loaded. Restart Ableton after script update."
                    )
            except Exception as e:
                logger.warning(f"Failed to start dataset recorder: {e}")
        else:
            reason = "unknown"
            try:
                from .config import telemetry_config  # noqa: F401
                from .telemetry import get_telemetry_consent, is_telemetry_enabled

                if not is_telemetry_enabled():
                    reason = "telemetry disabled (config.enabled=False or DISABLE_TELEMETRY)"
                elif not get_telemetry_consent():
                    reason = "no dataset consent yet — the user has not opted in"
                else:
                    reason = "ABLETON_MCP_DISABLE_DATASET or unexpected gate failure"
            except Exception:
                reason = "MCP_Server/config.py missing or unreadable (gitignored; required for Supabase)"
            logger.info("Dataset recording off — %s", reason)

        yield {"script_info": script_info}
    finally:
        global _ableton_connection
        try:
            from .dataset.passive_poller import stop_passive_poller

            stop_passive_poller()
        except Exception as e:
            logger.debug(f"Failed to stop passive poller: {e}")
        if _ableton_connection:
            logger.info("Disconnecting from Ableton on shutdown")
            _ableton_connection.disconnect()
            _ableton_connection = None
        try:
            recorder = get_recorder()
            if recorder:
                # Bounded wait so queued rows land before the daemon worker
                # is killed at exit.
                recorder.end(timeout=float(
                    os.environ.get("ABLETON_MCP_DATASET_FLUSH_SEC", "5")
                ))
        except Exception as e:
            logger.debug(f"Failed to end dataset session: {e}")
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
            # Passive events stop arriving while disconnected, so any cached
            # state hash may describe a Live session that has since moved on.
            try:
                recorder = get_recorder()
                if recorder:
                    recorder.invalidate_cached_state()
            except Exception:
                pass
    
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


# Core Tool endpoints

@mcp.tool()
def set_dataset_consent(ctx: Context, consent: bool, user_said: str = "") -> str:
    """Record the user's answer to the dataset consent question.

    Call this ONLY after the user has answered in their own words. Never infer
    the answer, never call it on their behalf, and never call it because
    contributing seems helpful — consent the user did not give is not consent.
    If they have not been asked yet, ask first and wait for their reply.

    Parameters:
    - consent: True if the user agreed to contribute, False if they declined
    - user_said: The user's reply, quoted as closely as possible
    """
    # Intentionally undecorated: recording this call would mean collecting data
    # from someone who may have just declined.
    try:
        from .dataset.consent import record_consent

        state = record_consent(consent, quote=user_said)
    except Exception as e:
        logger.error(f"Could not record dataset consent: {str(e)}")
        return f"Error recording consent: {str(e)}"

    if not consent:
        return (
            "Recorded: dataset contribution declined. Nothing is uploaded, and "
            "you will not be asked again."
        )

    try:
        from .telemetry import refresh_consent_from_dataset

        refresh_consent_from_dataset()
        recorder = get_recorder()
        # Under opt-in the poller is almost never started at boot — consent did
        # not exist yet — so a grant has to start it here or passive Live events
        # would be missed for the rest of the session. Idempotent and
        # self-gating, so this is safe even if startup did start it.
        from .dataset.passive_poller import start_passive_poller

        start_passive_poller()
    except Exception as e:
        logger.error(f"Consent saved but recording failed to start: {str(e)}")
        return (
            "Consent saved, but recording could not start in this session. "
            "It will begin after a restart."
        )

    if recorder is None:
        return (
            "Consent saved, but recording is unavailable (telemetry may be "
            f"disabled). State: {state}."
        )
    return (
        "Thank you — this session is now being contributed to the open dataset. "
        "Say so at any time to stop, or set ABLETON_MCP_DISABLE_DATASET=1."
    )


@mcp.tool()
@telemetry_tool("get_session_info")
@trajectory_tool("get_session_info")
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
@telemetry_tool("get_remote_script_info")
@trajectory_tool("get_remote_script_info", modifying=False)
def get_remote_script_info(ctx: Context, user_prompt: str = "") -> str:
    """
    Report Ableton Remote Script version and capabilities (handshake).

    Use this to verify the Live-side bridge matches this MCP server package.
    """
    try:
        from .remote_script_install import EXPECTED_REMOTE_SCRIPT_VERSION
        from .script_handshake import get_cached_script_info, handshake

        ableton = get_ableton_connection()
        info = handshake(ableton.send_command)
        cached = dict(get_cached_script_info() or info)
        cached["expected_version"] = EXPECTED_REMOTE_SCRIPT_VERSION
        return json.dumps(cached, indent=2)
    except Exception as e:
        logger.error(f"Error getting remote script info: {str(e)}")
        return f"Error getting remote script info: {str(e)}"

@mcp.tool()
@telemetry_tool("get_track_info")
@trajectory_tool("get_track_info")
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


def _note_params(track_index: int, clip_index: int, location: str) -> Dict[str, Any]:
    """Command params; location is only sent for the Arrangement, so calls
    on Session clips stay exactly what older Remote Scripts expect."""
    params: Dict[str, Any] = {"track_index": track_index, "clip_index": clip_index}
    location = (location or "session").lower()
    if location not in ("session", "arrangement"):
        raise ValueError("location must be 'session' or 'arrangement'")
    if location == "arrangement":
        params["location"] = "arrangement"
    return params


def _arrangement_notes_missing(location: str) -> Union[str, None]:
    """An older Remote Script would ignore location and edit the Session clip
    instead, so refuse unless it advertises arrangement_notes."""
    if (location or "session").lower() != "arrangement":
        return None
    from .script_handshake import require_capability

    return require_capability("arrangement_notes")


@mcp.tool()
@telemetry_tool("get_clip_notes")
@trajectory_tool("get_clip_notes")
def get_clip_notes(
    ctx: Context,
    track_index: int,
    clip_index: int,
    location: str = "session",
    user_prompt: str = "",
) -> str:
    """
    Read all MIDI notes from a Session clip or an Arrangement clip.

    Returns pitch, start_time, duration, velocity, mute (and extended fields when available).
    Note times are in clip beats (0 = clip start). For an Arrangement clip the
    reply also gives arrangement_start / arrangement_end (song beats) and
    start_marker: a note plays at arrangement_start + (start_time - start_marker)
    when the clip isn't looping.

    Parameters:
    - track_index: Track that owns the clip
    - clip_index: Session slot index, or Arrangement clip index (get_arrangement_clips)
    - location: "session" (default) or "arrangement"
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        from .script_handshake import require_capability

        missing = require_capability("get_clip_notes") or _arrangement_notes_missing(location)
        if missing:
            return missing
        ableton = get_ableton_connection()
        result = ableton.send_command(
            "get_clip_notes", _note_params(track_index, clip_index, location),
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting clip notes: {str(e)}")
        return f"Error getting clip notes: {str(e)}"


@mcp.tool()
@telemetry_tool("get_device_parameters")
@trajectory_tool("get_device_parameters")
def get_device_parameters(
    ctx: Context,
    track_index: int,
    device_index: int,
    user_prompt: str = "",
) -> str:
    """
    Read all parameters for a device on a track (name, value, min, max).

    Parameters:
    - track_index: Track that owns the device
    - device_index: Index into the track's device chain
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command(
            "get_device_parameters",
            {"track_index": track_index, "device_index": device_index},
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting device parameters: {str(e)}")
        return f"Error getting device parameters: {str(e)}"


@mcp.tool()
@rich_telemetry_tool("set_device_parameter")
@trajectory_tool("set_device_parameter")
def set_device_parameter(
    ctx: Context,
    track_index: int,
    device_index: int,
    parameter_index: int,
    value: float,
    user_prompt: str = "",
) -> str:
    """
    Set a device parameter to a specific value.

    Use get_device_parameters first to discover parameter indices and ranges.

    Parameters:
    - track_index: Track that owns the device
    - device_index: Index into the track's device chain
    - parameter_index: Index into device.parameters
    - value: New parameter value (Live parameter units)
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command(
            "set_device_parameter",
            {
                "track_index": track_index,
                "device_index": device_index,
                "parameter_index": parameter_index,
                "value": value,
            },
        )
        return (
            f"Set {result.get('name', 'parameter')} "
            f"{result.get('old_value')} → {result.get('value')}"
        )
    except Exception as e:
        logger.error(f"Error setting device parameter: {str(e)}")
        return f"Error setting device parameter: {str(e)}"


@mcp.tool()
@telemetry_tool("get_session_snapshot")
@trajectory_tool("get_session_snapshot")
def get_session_snapshot(
    ctx: Context,
    include_notes: bool = True,
    include_params: bool = True,
    user_prompt: str = "",
) -> str:
    """
    Capture a full project state snapshot for trajectory recording.

    Includes session metadata, every track (mixer, devices, session clips,
    arrangement clips), optional MIDI notes, and optional device parameters.
    Used to version musical state S_t → S_{t+1}.

    Parameters:
    - include_notes: Include MIDI note arrays in clips (default True)
    - include_params: Include device parameter values (default True)
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        from .script_handshake import require_capability

        missing = require_capability("get_session_snapshot")
        if missing:
            return missing
        ableton = get_ableton_connection()
        result = ableton.send_command(
            "get_session_snapshot",
            {
                "include_notes": include_notes,
                "include_params": include_params,
            },
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting session snapshot: {str(e)}")
        return f"Error getting session snapshot: {str(e)}"


@mcp.tool()
@telemetry_tool("create_midi_track")
@trajectory_tool("create_midi_track")
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
@telemetry_tool("create_audio_track")
@trajectory_tool("create_audio_track")
def create_audio_track(ctx: Context, index: int = -1, user_prompt: str = "") -> str:
    """
    Create a new audio track in the Ableton session.

    Use this for recorded or imported audio (samples, stems, vocals). For MIDI
    instruments use create_midi_track instead.

    Parameters:
    - index: The index to insert the track at (-1 = end of list)
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("create_audio_track", {"index": index})
        return f"Created new audio track: {result.get('name', 'unknown')}"
    except Exception as e:
        logger.error(f"Error creating audio track: {str(e)}")
        return f"Error creating audio track: {str(e)}"


@mcp.tool()
@rich_telemetry_tool("set_track_name")
@trajectory_tool("set_track_name")
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
@trajectory_tool("create_clip")
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
@trajectory_tool("create_audio_clip")
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
@trajectory_tool("add_notes_to_clip")
def add_notes_to_clip(
    ctx: Context,
    track_index: int,
    clip_index: int,
    notes: List[Dict[str, Union[int, float, bool]]],
    location: str = "session",
    user_prompt: str = ""
) -> str:
    """
    Add MIDI notes to a Session clip or an Arrangement clip. Notes are added
    to the existing ones; to replace, clear_notes_from_clip or remove_notes first.

    Parameters:
    - track_index: The index of the track containing the clip
    - clip_index: Session slot index, or Arrangement clip index (get_arrangement_clips)
    - notes: List of note dictionaries, each with pitch, start_time (clip
      beats, 0 = clip start), duration, velocity, and mute
    - location: "session" (default) or "arrangement"
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        missing = _arrangement_notes_missing(location)
        if missing:
            return missing
        params = _note_params(track_index, clip_index, location)
        params["notes"] = notes
        ableton = get_ableton_connection()
        result = ableton.send_command("add_notes_to_clip", params)
        if "location" in params:
            return f"Added {len(notes)} notes to arrangement clip {clip_index} on track {track_index}"
        return f"Added {len(notes)} notes to clip at track {track_index}, slot {clip_index}"
    except Exception as e:
        logger.error(f"Error adding notes to clip: {str(e)}")
        return f"Error adding notes to clip: {str(e)}"

@mcp.tool()
@rich_telemetry_tool("clear_notes_from_clip")
def clear_notes_from_clip(
    ctx: Context,
    track_index: int,
    clip_index: int,
    location: str = "session",
    user_prompt: str = ""
) -> str:
    """
    Remove all MIDI notes from a Session clip or an Arrangement clip.

    Writes are additive (add_notes_to_clip only appends), so to truly *modify*
    a clip you clear it first, then add the new notes. Use this with
    get_clip_notes and add_notes_to_clip for a real read -> modify -> write
    loop: read the notes, edit the list, clear_notes_from_clip, then
    add_notes_to_clip the edited notes.

    To change only part of a clip, use remove_notes instead.

    Parameters:
    - track_index: The index of the track containing the clip
    - clip_index: Session slot index, or Arrangement clip index (get_arrangement_clips)
    - location: "session" (default) or "arrangement"
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        from .script_handshake import require_capability

        missing = require_capability("clear_notes_from_clip") or _arrangement_notes_missing(location)
        if missing:
            return missing
        ableton = get_ableton_connection()
        result = ableton.send_command(
            "clear_notes_from_clip", _note_params(track_index, clip_index, location))
        return "Cleared {n} note(s) from clip '{name}' (track {t}, {where} {c})".format(
            n=result.get("cleared_count", "?"),
            name=result.get("clip_name", "clip"),
            t=track_index,
            where="arrangement clip" if (location or "").lower() == "arrangement" else "slot",
            c=clip_index,
        )
    except Exception as e:
        logger.error(f"Error clearing notes from clip: {str(e)}")
        return f"Error clearing notes from clip: {str(e)}"


@mcp.tool()
@telemetry_tool("remove_notes")
def remove_notes(
    ctx: Context,
    track_index: int,
    clip_index: int,
    from_time: float = 0.0,
    time_span: Union[float, None] = None,
    from_pitch: int = 0,
    pitch_span: int = 128,
    location: str = "session",
    user_prompt: str = "",
) -> str:
    """
    Remove the notes that start inside a time range and a pitch range, leaving
    the others. Use it to rewrite one bar or one drum lane: remove that range,
    then add_notes_to_clip the new notes.

    Parameters:
    - track_index: The index of the track containing the clip
    - clip_index: Session slot index, or Arrangement clip index (get_arrangement_clips)
    - from_time: Start of the range, in clip beats (0 = clip start)
    - time_span: Length of the range in beats (default: to the end of the clip)
    - from_pitch: Lowest MIDI pitch of the range (0-127, default 0)
    - pitch_span: Number of pitches from from_pitch (default 128 = all; 1 = a single pitch)
    - location: "session" (default) or "arrangement"
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        params = _note_params(track_index, clip_index, location)
    except ValueError as e:
        return f"Error removing notes: {e}"
    params.update(_without_none({
        "from_time": from_time, "time_span": time_span,
        "from_pitch": from_pitch, "pitch_span": pitch_span,
    }))
    return _send_with_capability("remove_notes", params, "removing notes")

@mcp.tool()
@rich_telemetry_tool("set_clip_name")
@trajectory_tool("set_clip_name")
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
@rich_telemetry_tool("set_arrangement_clip_name")
@trajectory_tool("set_arrangement_clip_name")
def set_arrangement_clip_name(ctx: Context, track_index: int, clip_index: int, name: str, user_prompt: str = "") -> str:
    """
    Set the name of a clip placed in the Arrangement timeline.

    Parameters:
    - track_index: The index of the track containing the clip
    - clip_index: The index of the clip within track.arrangement_clips, in the
      same order returned by get_arrangement_clips (i.e. ordered by start_time)
    - name: The new name for the clip
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_arrangement_clip_name", {
            "track_index": track_index,
            "clip_index": clip_index,
            "name": name
        })
        return f"Renamed arrangement clip at track {track_index}, index {clip_index} to '{name}'"
    except Exception as e:
        logger.error(f"Error setting arrangement clip name: {str(e)}")
        return f"Error setting arrangement clip name: {str(e)}"

@mcp.tool()
@rich_telemetry_tool("set_tempo")
@trajectory_tool("set_tempo")
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
@trajectory_tool("load_instrument_or_effect")
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
            devices = result.get("devices_after", [])
            if result.get("in_place"):
                if result.get("settled"):
                    return (f"Reloaded '{uri}' in place on track {track_index}: "
                            f"Live kept the existing device and reset its parameters")
                return (f"Requested reload of '{uri}' on track {track_index}. Live "
                        f"reloads an identical device in place, and no parameter "
                        f"changed (they may already be at their defaults). "
                        f"Devices on track: {', '.join(devices) or 'none'}")
            if new_devices:
                return f"Loaded instrument with URI '{uri}' on track {track_index}. New devices: {', '.join(new_devices)}"
            elif result.get("settled") is False:
                return (f"Requested load of '{uri}' on track {track_index}, but Live "
                        f"had not changed the device chain yet. Devices on track: "
                        f"{', '.join(devices) or 'none'}. Check with get_track_info.")
            else:
                return f"Loaded instrument with URI '{uri}' on track {track_index}. Devices on track: {', '.join(devices) or 'none'}"
        else:
            return f"Failed to load instrument with URI '{uri}'"
    except Exception as e:
        logger.error(f"Error loading instrument by URI: {str(e)}")
        return f"Error loading instrument by URI: {str(e)}"

@mcp.tool()
@telemetry_tool("fire_clip")
@trajectory_tool("fire_clip")
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
@trajectory_tool("stop_clip")
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
@telemetry_tool("delete_clip")
def delete_clip(ctx: Context, track_index: int, clip_index: int, user_prompt: str = "") -> str:
    """
    Delete the clip in the given clip slot, freeing it for reuse.

    Use this before create_clip when you want to overwrite an existing clip
    (create_clip itself refuses to write into an occupied slot).

    Parameters:
    - track_index: The index of the track containing the clip
    - clip_index: The index of the clip slot to clear
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        from .script_handshake import require_capability

        missing = require_capability("delete_clip")
        if missing:
            return missing
        ableton = get_ableton_connection()
        result = ableton.send_command("delete_clip", {
            "track_index": track_index,
            "clip_index": clip_index,
        })
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error deleting clip: {str(e)}")
        return f"Error deleting clip: {str(e)}"


# ── Mixer / tracks / scenes ──────────────────────────────────────────────────

def _send_with_capability(command: str, params: Dict[str, Any], label: str) -> str:
    """Send a command after checking the Remote Script supports it."""
    try:
        from .script_handshake import require_capability

        missing = require_capability(command)
        if missing:
            return missing
        ableton = get_ableton_connection()
        result = ableton.send_command(command, params)
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error {label}: {str(e)}")
        return f"Error {label}: {str(e)}"


@mcp.tool()
@telemetry_tool("set_track_volume")
def set_track_volume(
    ctx: Context, track_index: int, volume: float, track_type: str = "track", user_prompt: str = ""
) -> str:
    """
    Set a track's volume fader.

    Parameters:
    - track_index: Index of the track (ignored when track_type is "master")
    - volume: Normalized fader value 0.0–1.0 (0.85 ≈ 0 dB, 0.0 = -inf)
    - track_type: "track" (default), "return" or "master"
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    return _send_with_capability("set_track_volume", {
        "track_index": track_index, "volume": volume, "track_type": track_type,
    }, "setting track volume")


@mcp.tool()
@telemetry_tool("set_track_panning")
def set_track_panning(
    ctx: Context, track_index: int, panning: float, track_type: str = "track", user_prompt: str = ""
) -> str:
    """
    Set a track's panning.

    Parameters:
    - track_index: Index of the track (ignored when track_type is "master")
    - panning: -1.0 = full left, 0.0 = center, 1.0 = full right
    - track_type: "track" (default), "return" or "master"
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    return _send_with_capability("set_track_panning", {
        "track_index": track_index, "panning": panning, "track_type": track_type,
    }, "setting track panning")


@mcp.tool()
@telemetry_tool("set_track_send")
def set_track_send(
    ctx: Context, track_index: int, send_index: int, value: float,
    track_type: str = "track", user_prompt: str = ""
) -> str:
    """
    Set the level of a send from a track to a return track.

    Parameters:
    - track_index: Index of the track
    - send_index: Index of the send (0 = Send A / first return track)
    - value: Send level 0.0–1.0
    - track_type: "track" (default) or "return"
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    return _send_with_capability("set_track_send", {
        "track_index": track_index, "send_index": send_index,
        "value": value, "track_type": track_type,
    }, "setting track send")


@mcp.tool()
@telemetry_tool("set_track_mute")
def set_track_mute(
    ctx: Context, track_index: int, mute: bool, track_type: str = "track", user_prompt: str = ""
) -> str:
    """
    Mute or unmute a track.

    Parameters:
    - track_index: Index of the track
    - mute: True to mute, False to unmute
    - track_type: "track" (default) or "return"
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    return _send_with_capability("set_track_mute", {
        "track_index": track_index, "mute": mute, "track_type": track_type,
    }, "setting track mute")


@mcp.tool()
@telemetry_tool("set_track_solo")
def set_track_solo(
    ctx: Context, track_index: int, solo: bool, track_type: str = "track", user_prompt: str = ""
) -> str:
    """
    Solo or unsolo a track.

    Parameters:
    - track_index: Index of the track
    - solo: True to solo, False to unsolo
    - track_type: "track" (default) or "return"
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    return _send_with_capability("set_track_solo", {
        "track_index": track_index, "solo": solo, "track_type": track_type,
    }, "setting track solo")


@mcp.tool()
@telemetry_tool("set_track_arm")
def set_track_arm(ctx: Context, track_index: int, arm: bool, user_prompt: str = "") -> str:
    """
    Arm or disarm a track for recording.

    Parameters:
    - track_index: Index of the track
    - arm: True to arm, False to disarm
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    return _send_with_capability("set_track_arm", {
        "track_index": track_index, "arm": arm,
    }, "setting track arm")


@mcp.tool()
@telemetry_tool("delete_track")
def delete_track(ctx: Context, track_index: int, user_prompt: str = "") -> str:
    """
    Delete a track. Destructive: confirm with the user before calling.
    Indexes of the following tracks shift down by one.

    Parameters:
    - track_index: Index of the track to delete
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    return _send_with_capability("delete_track", {"track_index": track_index}, "deleting track")


@mcp.tool()
@telemetry_tool("duplicate_track")
def duplicate_track(ctx: Context, track_index: int, user_prompt: str = "") -> str:
    """
    Duplicate a track (with its clips and devices). The copy is inserted right after it.

    Parameters:
    - track_index: Index of the track to duplicate
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    return _send_with_capability("duplicate_track", {"track_index": track_index}, "duplicating track")


@mcp.tool()
@telemetry_tool("get_scenes")
def get_scenes(ctx: Context, user_prompt: str = "") -> str:
    """
    List the Session view scenes (index, name, tempo).

    Parameters:
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    return _send_with_capability("get_scenes", {}, "getting scenes")


@mcp.tool()
@telemetry_tool("create_scene")
def create_scene(ctx: Context, index: int = -1, user_prompt: str = "") -> str:
    """
    Create a new scene in the Session view.

    Parameters:
    - index: Position to insert the scene (-1 = at the end)
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    return _send_with_capability("create_scene", {"index": index}, "creating scene")


@mcp.tool()
@telemetry_tool("delete_scene")
def delete_scene(ctx: Context, scene_index: int, user_prompt: str = "") -> str:
    """
    Delete a scene and all clips in its row. Destructive: confirm with the user first.

    Parameters:
    - scene_index: Index of the scene to delete
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    return _send_with_capability("delete_scene", {"scene_index": scene_index}, "deleting scene")


@mcp.tool()
@telemetry_tool("duplicate_scene")
def duplicate_scene(ctx: Context, scene_index: int, user_prompt: str = "") -> str:
    """
    Duplicate a scene (with its clips). The copy is inserted right after it.

    Parameters:
    - scene_index: Index of the scene to duplicate
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    return _send_with_capability("duplicate_scene", {"scene_index": scene_index}, "duplicating scene")


@mcp.tool()
@telemetry_tool("fire_scene")
def fire_scene(ctx: Context, scene_index: int, user_prompt: str = "") -> str:
    """
    Launch a scene (all clips in its row).

    Parameters:
    - scene_index: Index of the scene to launch
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    return _send_with_capability("fire_scene", {"scene_index": scene_index}, "firing scene")


@mcp.tool()
@telemetry_tool("set_scene_name")
def set_scene_name(ctx: Context, scene_index: int, name: str, user_prompt: str = "") -> str:
    """
    Rename a scene.

    Parameters:
    - scene_index: Index of the scene
    - name: New scene name
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    return _send_with_capability("set_scene_name", {
        "scene_index": scene_index, "name": name,
    }, "renaming scene")


@mcp.tool()
@telemetry_tool("delete_arrangement_clip")
def delete_arrangement_clip(ctx: Context, track_index: int, clip_index: int, user_prompt: str = "") -> str:
    """
    Delete a clip from the Arrangement timeline (Live 11+).

    Parameters:
    - track_index: Index of the track
    - clip_index: Index of the clip as listed by get_arrangement_clips
      (indexes of later clips shift down after deletion)
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    return _send_with_capability("delete_arrangement_clip", {
        "track_index": track_index, "clip_index": clip_index,
    }, "deleting arrangement clip")


def _without_none(params: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in params.items() if v is not None}


@mcp.tool()
@telemetry_tool("get_clip_loop")
def get_clip_loop(
    ctx: Context, track_index: int, clip_index: int, location: str = "session", user_prompt: str = ""
) -> str:
    """
    Read a clip's loop switch, loop brace (loop_start / loop_end) and start /
    end markers. Units are beats, except for an unwarped audio clip, where
    Live uses seconds of the file (see "units" in the reply). For an
    Arrangement clip the reply also gives its place in the song.

    Parameters:
    - track_index: Index of the track
    - clip_index: Session slot index, or Arrangement clip index (get_arrangement_clips)
    - location: "session" (default) or "arrangement"
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    return _send_with_capability("get_clip_loop", {
        "track_index": track_index, "clip_index": clip_index, "location": location,
    }, "reading clip loop")


@mcp.tool()
@telemetry_tool("set_clip_loop")
def set_clip_loop(
    ctx: Context,
    track_index: int,
    clip_index: int,
    location: str = "session",
    looping: Union[bool, None] = None,
    loop_start: Union[float, None] = None,
    loop_end: Union[float, None] = None,
    loop_length: Union[float, None] = None,
    start_marker: Union[float, None] = None,
    end_marker: Union[float, None] = None,
    user_prompt: str = "",
) -> str:
    """
    Change a clip's loop and markers. Arguments left out are untouched.

    - The loop brace (loop_start → loop_end) is the part that repeats when
      looping is on. Shorten a 4-bar loop to its first bar with
      loop_start=0, loop_length=4.
    - Looping on: playback starts at start_marker, then the brace repeats.
      Looping off: Live plays loop_start -> loop_end once (start_marker
      follows loop_start; end_marker is unused). Markers given for a clip
      that doesn't loop are written to loop_start/loop_end for you.
    - get_clip_loop's "playback" field says what actually plays.
    - Turning warping off then on again resets an audio clip's warp markers.

    Units are beats (seconds for an unwarped audio clip: check get_clip_loop).
    The order of the writes is handled so the start never passes the end on
    the way. The reply shows what Live applied; "adjusted" lists any value
    it changed.

    Parameters:
    - track_index: Index of the track
    - clip_index: Session slot index, or Arrangement clip index (get_arrangement_clips)
    - location: "session" (default) or "arrangement"
    - looping: Loop switch on or off
    - loop_start, loop_end: Loop brace
    - loop_length: Sets loop_end = loop_start + loop_length (instead of loop_end)
    - start_marker, end_marker: Playback start / end markers
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    return _send_with_capability("set_clip_loop", _without_none({
        "track_index": track_index, "clip_index": clip_index, "location": location,
        "looping": looping, "loop_start": loop_start, "loop_end": loop_end,
        "loop_length": loop_length, "start_marker": start_marker, "end_marker": end_marker,
    }), "setting clip loop")


@mcp.tool()
@telemetry_tool("get_clip_warp")
def get_clip_warp(
    ctx: Context, track_index: int, clip_index: int, location: str = "session", user_prompt: str = ""
) -> str:
    """
    Read an audio clip's warp settings: warping on/off, warp mode, available
    modes, warp markers (beat_time ↔ sample_time in seconds), pitch, gain,
    clip length and the sample's duration.

    Parameters:
    - track_index: Index of the track
    - clip_index: Session slot index, or Arrangement clip index as listed by
      get_arrangement_clips
    - location: "session" (default) or "arrangement"
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    return _send_with_capability("get_clip_warp", {
        "track_index": track_index, "clip_index": clip_index, "location": location,
    }, "reading clip warp")


@mcp.tool()
@telemetry_tool("set_clip_warp")
def set_clip_warp(
    ctx: Context,
    track_index: int,
    clip_index: int,
    location: str = "session",
    warping: Union[bool, None] = None,
    warp_mode: Union[str, None] = None,
    original_bpm: Union[float, None] = None,
    pitch_coarse: Union[int, None] = None,
    pitch_fine: Union[float, None] = None,
    gain: Union[float, None] = None,
    user_prompt: str = "",
) -> str:
    """
    Change an audio clip's warp settings. Arguments left out are untouched.

    To make a loop follow the song tempo, pass its original tempo as
    original_bpm (sample packs usually put it in the file name, e.g.
    "..._131_..."): warping is turned on and the warp markers are rebuilt so
    the file is read at that tempo.

    Parameters:
    - track_index: Index of the audio track
    - clip_index: Session slot index, or Arrangement clip index (get_arrangement_clips)
    - location: "session" (default) or "arrangement"
    - warping: Turn warping on or off
    - warp_mode: "beats", "tones", "texture", "re_pitch", "complex",
      "complex_pro" (or Live's index 0–6). Beats suits drums, Complex/Complex
      Pro full mixes, Tones monophonic parts, Re-Pitch vinyl-style speed changes.
    - original_bpm: The loop's own tempo; conforms it to the song tempo
    - pitch_coarse: Transpose in semitones (-48 to 48)
    - pitch_fine: Detune in cents (-50 to 50)
    - gain: Clip gain, normalized 0.0–1.0 (see gain_display in the reply)
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    return _send_with_capability("set_clip_warp", _without_none({
        "track_index": track_index, "clip_index": clip_index, "location": location,
        "warping": warping, "warp_mode": warp_mode, "original_bpm": original_bpm,
        "pitch_coarse": pitch_coarse, "pitch_fine": pitch_fine, "gain": gain,
    }), "setting clip warp")


@mcp.tool()
@telemetry_tool("edit_warp_markers")
def edit_warp_markers(
    ctx: Context,
    track_index: int,
    clip_index: int,
    location: str = "session",
    add: Union[List[Dict[str, float]], None] = None,
    move: Union[List[Dict[str, float]], None] = None,
    remove: Union[List[float], None] = None,
    user_prompt: str = "",
) -> str:
    """
    Edit an audio clip's warp markers (Live 11+; warping must be on).
    Applied in this order: remove, move, add. Use get_clip_warp to see the
    current markers.

    Parameters:
    - track_index: Index of the audio track
    - clip_index: Session slot index, or Arrangement clip index (get_arrangement_clips)
    - location: "session" (default) or "arrangement"
    - add: [{"beat_time": 8.0, "sample_time": 3.66}] — pin a point of the
      file (sample_time, seconds) to a beat; both are required
    - move: [{"beat_time": 8.0, "beat_time_distance": 0.25}] — shift the
      marker at beat_time by that many beats
    - remove: [8.0, 16.0] — beat times of the markers to remove
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    return _send_with_capability("edit_warp_markers", _without_none({
        "track_index": track_index, "clip_index": clip_index, "location": location,
        "add": add, "move": move, "remove": remove,
    }), "editing warp markers")


@mcp.tool()
@telemetry_tool("set_clip_automation")
def set_clip_automation(
    ctx: Context,
    track_index: int,
    clip_index: int,
    points: List[Dict[str, float]],
    location: str = "session",
    device_index: int = -1,
    parameter_index: int = 0,
    mixer_parameter: str = "",
    interpolation: str = "linear",
    resolution: float = 0.25,
    clear_first: bool = True,
    user_prompt: str = "",
) -> str:
    """
    Write a clip automation envelope for one parameter on a Session clip; the
    envelope plays whenever the clip plays. Live's API refuses clip automation
    on Arrangement clips, and Arrangement automation lanes aren't reachable.

    Target either a device parameter (device_index + parameter_index, see
    get_device_parameters) or a track mixer control (mixer_parameter).

    Parameters:
    - track_index: Index of the track that owns the clip and the parameter
    - clip_index: Session slot index
    - points: [{"time": 0, "value": 0.2}, {"time": 16, "value": 0.9}] — time in
      beats in clip time (0 = clip start, like MIDI note start_time), value in
      the parameter's units (clamped to its min/max). The last point holds
      until the clip's end. An empty list with clear_first=true removes the
      envelope.
    - location: "session" (the only location Live accepts for writing)
    - device_index: Device in the track's chain (ignored when mixer_parameter is set)
    - parameter_index: Index into the device's parameters
    - mixer_parameter: "volume", "panning" or "send:N" (N = return track index)
    - interpolation: "linear" ramps between points (drawn as steps of
      `resolution` beats), "step" holds each value until the next point
    - resolution: Step size in beats for linear ramps (default 0.25 = a 16th)
    - clear_first: Remove the parameter's existing envelope in this clip first
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    return _send_with_capability("set_clip_automation", {
        "track_index": track_index, "clip_index": clip_index, "location": location,
        "device_index": device_index, "parameter_index": parameter_index,
        "mixer_parameter": mixer_parameter, "points": points,
        "interpolation": interpolation, "resolution": resolution,
        "clear_first": clear_first,
    }, "setting clip automation")


@mcp.tool()
@telemetry_tool("get_clip_automation")
def get_clip_automation(
    ctx: Context,
    track_index: int,
    clip_index: int,
    location: str = "session",
    device_index: int = -1,
    parameter_index: int = 0,
    mixer_parameter: str = "",
    resolution: float = 1.0,
    user_prompt: str = "",
) -> str:
    """
    Read a clip's automation envelope for one parameter, sampled every
    `resolution` beats across the clip. Reports has_envelope=false when the
    parameter isn't automated in this clip.

    Parameters:
    - track_index, clip_index, location: as in set_clip_automation
    - device_index, parameter_index, mixer_parameter: as in set_clip_automation
    - resolution: Sampling step in beats (default 1.0)
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    return _send_with_capability("get_clip_automation", {
        "track_index": track_index, "clip_index": clip_index, "location": location,
        "device_index": device_index, "parameter_index": parameter_index,
        "mixer_parameter": mixer_parameter, "resolution": resolution,
    }, "reading clip automation")


@mcp.tool()
@telemetry_tool("start_playback")
@trajectory_tool("start_playback")
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
@trajectory_tool("stop_playback")
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
@trajectory_tool("get_browser_tree")
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
@trajectory_tool("get_browser_items_at_path")
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
@trajectory_tool("load_drum_kit")
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
@trajectory_tool("switch_to_arrangement_view")
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
@trajectory_tool("set_arrangement_time")
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
        current = result.get('current_song_time', time)
        if result.get("settled") is False:
            return (f"Requested playhead move to beat {time}, but Live still "
                    f"reports beat {current}")
        return f"Playhead moved to beat {current}"
    except Exception as e:
        logger.error(f"Error setting arrangement time: {str(e)}")
        return f"Error setting arrangement time: {str(e)}"


@mcp.tool()
@telemetry_tool("get_arrangement_clips")
@trajectory_tool("get_arrangement_clips")
def get_arrangement_clips(ctx: Context, track_index: int, user_prompt: str = "") -> str:
    """
    List all clips placed in the Arrangement timeline for a track.

    Returns each clip's name, start_time, end_time, length, and type.

    Parameters:
    - track_index: The index of the track to inspect
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_arrangement_clips", {"track_index": track_index})
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting arrangement clips: {str(e)}")
        return f"Error getting arrangement clips: {str(e)}"


@mcp.tool()
@rich_telemetry_tool("duplicate_to_arrangement")
@trajectory_tool("duplicate_to_arrangement")
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
@rich_telemetry_tool("create_locator")
def create_locator(
    ctx: Context,
    name: str,
    time: float,
    user_prompt: str = ""
) -> str:
    """
    Create a named locator (cue point) in the Arrangement at a beat position.

    If a locator already exists at that beat (within ~1e-3 tolerance) it is
    renamed instead of toggled off. Time is in beats from the start of the
    arrangement (e.g. 0.0 = start, 16.0 = bar 5 in 4/4).

    Parameters:
    - name: The locator label (e.g. "Chorus", "Verse 1", "Drop")
    - time: Beat position where the locator should sit
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        from .script_handshake import require_capability

        missing = require_capability("create_locator")
        if missing:
            return missing
        ableton = get_ableton_connection()
        result = ableton.send_command(
            "create_locator",
            {"name": name, "time": time}
        )
        return (
            f"Locator '{result.get('name', name)}' set at beat "
            f"{result.get('time', time)}"
        )
    except Exception as e:
        logger.error(f"Error creating locator: {str(e)}")
        return f"Error creating locator: {str(e)}"


# ── Dataset / preference tools (Supabase trajectory recording) ─────────────────

@mcp.tool()
@telemetry_tool("submit_intent")
@trajectory_tool("submit_intent", modifying=False)
def submit_intent(
    ctx: Context,
    text: str,
    level: int = 5,
    user_prompt: str = "",
) -> str:
    """
    Record the human's creative intent for subsequent actions in this session.

    Call this before a sequence of edits so trajectory steps are conditioned on intent.
    Levels: 1=atomic, 2=musical op, 3=section, 4=song, 5=creative goal.

    Requires telemetry consent. Data is stored in Supabase (same project as telemetry).

    Parameters:
    - text: Natural-language intent (e.g. "make the chorus feel bigger")
    - level: Hierarchical intent level 1–5 (default 5)
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    recorder = get_recorder()
    if recorder is None:
        return (
            "Dataset recording is off (telemetry disabled or user has not consented)."
        )
    try:
        event = recorder.set_intent(text=text, level=level)
        return (
            f"Recorded intent {event.intent_id} (level {level}): {text!r}. "
            f"Session: {recorder.session_id}"
        )
    except Exception as e:
        logger.error(f"Error submitting intent: {str(e)}")
        return f"Error submitting intent: {str(e)}"


@mcp.tool()
@telemetry_tool("rate_last_action")
@trajectory_tool("rate_last_action", modifying=False)
def rate_last_action(
    ctx: Context,
    rating: str,
    tags: str = "",
    note: str = "",
    user_prompt: str = "",
) -> str:
    """
    Rate the most recent recorded action (or the track after an edit).

    Ratings: better | same | worse | keep | reject | thumbs_up | thumbs_down
    Optional tags (comma-separated): groove, harmony, melody, sound, arrangement,
    energy, mix, emotion

    Requires telemetry consent.

    Parameters:
    - rating: Preference label
    - tags: Comma-separated aspect tags
    - note: Optional free-text reason
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    recorder = get_recorder()
    if recorder is None:
        return (
            "Dataset recording is off (telemetry disabled or user has not consented)."
        )
    try:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
        event = recorder.record_preference(
            rating=rating.strip().lower(),
            tags=tag_list,
            note=note or None,
        )
        target = event.target_action_id or "none"
        return f"Recorded preference {rating!r} for action {target}"
    except Exception as e:
        logger.error(f"Error rating action: {str(e)}")
        return f"Error rating action: {str(e)}"


@mcp.tool()
@telemetry_tool("prefer_candidate")
@trajectory_tool("prefer_candidate", modifying=False)
def prefer_candidate(
    ctx: Context,
    candidate_a: str,
    candidate_b: str,
    winner: str,
    reason: str = "",
    user_prompt: str = "",
) -> str:
    """
    Record a pairwise preference between two candidate actions or auditions.

    winner should be 'a', 'b', or an explicit candidate id matching A or B.

    Requires telemetry consent.

    Parameters:
    - candidate_a: Id / URI / label for option A
    - candidate_b: Id / URI / label for option B
    - winner: 'a', 'b', or the winning id
    - reason: Optional reason ("C has the right attack")
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    recorder = get_recorder()
    if recorder is None:
        return (
            "Dataset recording is off (telemetry disabled or user has not consented)."
        )
    try:
        w = winner.strip().lower()
        if w == "a":
            w = candidate_a
        elif w == "b":
            w = candidate_b
        event = recorder.record_preference(
            rating="pairwise",
            winner=w,
            candidate_a=candidate_a,
            candidate_b=candidate_b,
            note=reason or None,
        )
        return f"Recorded pairwise preference: winner={w!r} (event {event.event_id})"
    except Exception as e:
        logger.error(f"Error recording pairwise preference: {str(e)}")
        return f"Error recording pairwise preference: {str(e)}"


@mcp.tool()
@telemetry_tool("reject_last_action")
@trajectory_tool("reject_last_action", modifying=False)
def reject_last_action(
    ctx: Context,
    reason: str = "",
    user_prompt: str = "",
) -> str:
    """
    Mark the last action as rejected (exploration / preference boundary).

    Use when the human undoes or discards an agent edit. Requires telemetry consent.

    Parameters:
    - reason: Optional why it was rejected
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    recorder = get_recorder()
    if recorder is None:
        return (
            "Dataset recording is off (telemetry disabled or user has not consented)."
        )
    try:
        event = recorder.record_preference(
            rating="reject",
            note=reason or None,
        )
        return f"Recorded rejection for action {event.target_action_id or 'none'}"
    except Exception as e:
        logger.error(f"Error rejecting action: {str(e)}")
        return f"Error rejecting action: {str(e)}"


@mcp.tool()
@rich_telemetry_tool("record_audition")
@trajectory_tool("record_audition", modifying=False)
def record_audition(
    ctx: Context,
    uri: str,
    kept: bool = False,
    search_query: str = "",
    dwell_ms: float = 0.0,
    user_prompt: str = "",
) -> str:
    """
    Log a browser/preset/sample audition (keep or reject) for preference learning.

    Call once per candidate auditioned. Does not load the device — use
    load_instrument_or_effect when kept=True and you want to commit.

    Requires telemetry consent.

    Parameters:
    - uri: Browser item URI (or stable preset/sample id)
    - kept: Whether this candidate was kept
    - search_query: Optional search text that led here (e.g. "analog bass")
    - dwell_ms: Optional time spent auditioning
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    recorder = get_recorder()
    if recorder is None:
        return (
            "Dataset recording is off (telemetry disabled or user has not consented)."
        )
    try:
        event = recorder.record_audition(
            uri=uri,
            kept=kept,
            search_query=search_query or None,
            dwell_ms=dwell_ms if dwell_ms > 0 else None,
        )
        status = "kept" if kept else "rejected"
        return f"Recorded audition ({status}) uri={uri!r} event={event.event_id}"
    except Exception as e:
        logger.error(f"Error recording audition: {str(e)}")
        return f"Error recording audition: {str(e)}"



# Main execution
def main():
    """Run the MCP server"""
    mcp.run()

if __name__ == "__main__":
    main()