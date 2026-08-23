# ableton_mcp_server.py
from mcp.server.fastmcp import FastMCP, Context
from MCP_Server import als
import os
import socket
import json
import logging
from dataclasses import dataclass
from contextlib import asynccontextmanager
from typing import AsyncIterator, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("AbletonMCPServer")


@dataclass
class AbletonConnection:
    host: str
    port: int
    sock: socket.socket | None = None

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
                            raise Exception(
                                "Connection closed before receiving any data"
                            )
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
            data = b"".join(chunks)
            logger.info(f"Returning data after receive completion ({len(data)} bytes)")
            try:
                json.loads(data.decode("utf-8"))
                return data
            except json.JSONDecodeError:
                raise Exception("Incomplete JSON response received")
        else:
            raise Exception("No data received")

    def send_command(
        self, command_type: str, params: dict[str, Any] | None = None, timeout: float | None = None
    ) -> dict[str, Any]:
        """Send a command to Ableton and return the response"""
        if not self.sock and not self.connect():
            raise ConnectionError("Not connected to Ableton")

        command = {"type": command_type, "params": params or {}}

        # Check if this is a state-modifying command
        is_modifying_command = command_type in [
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
        ]

        try:
            logger.info(f"Sending command: {command_type} with params: {params}")

            # Send the command
            if not self.sock:
                raise Exception("Not connected to Ableton")
            self.sock.sendall(json.dumps(command).encode("utf-8"))
            logger.info("Command sent, waiting for response...")

            # For state-modifying commands, add a small delay to give Ableton time to process
            if is_modifying_command:
                import time

                time.sleep(0.1)  # 100ms delay

            # Set timeout based on command type
            if timeout is None:
                timeout = 15.0 if is_modifying_command else 10.0
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

            # For state-modifying commands, add another small delay after receiving response
            if is_modifying_command:
                import time

                time.sleep(0.1)  # 100ms delay

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
            if "response_data" in locals() and response_data:
                logger.error(f"Raw response (first 200 bytes): {response_data[:200]}")
            self.sock = None
            raise Exception(f"Invalid response from Ableton: {str(e)}")
        except Exception as e:
            logger.error(f"Error communicating with Ableton: {str(e)}")
            self.sock = None
            raise Exception(f"Communication error with Ableton: {str(e)}")


@asynccontextmanager
async def server_lifespan(server: FastMCP) -> AsyncIterator[dict[str, Any]]:
    """Manage server startup and shutdown lifecycle"""
    try:
        logger.info("AbletonMCP server starting up")

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
    description="Ableton Live integration through the Model Context Protocol",
    lifespan=server_lifespan,
)

# Global connection for resources
_ableton_connection = None


def get_ableton_connection():
    """Get or create a persistent Ableton connection"""
    global _ableton_connection

    if _ableton_connection is not None:
        try:
            # Test the connection with a simple ping
            # We'll try to send an empty message, which should fail if the connection is dead
            # but won't affect Ableton if it's alive
            _ableton_connection.sock.settimeout(1.0)
            _ableton_connection.sock.sendall(b"")
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
        # Try to connect up to 3 times with a short delay between attempts
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            try:
                logger.info(
                    f"Connecting to Ableton (attempt {attempt}/{max_attempts})..."
                )
                _ableton_connection = AbletonConnection(host="localhost", port=9877)
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
            raise Exception(
                "Could not connect to Ableton. Make sure the Remote Script is running."
            )

    return _ableton_connection


# Core Tool endpoints


@mcp.tool()
def get_session_info(ctx: Context) -> str:
    """Get detailed information about the current Ableton session"""
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_session_info")
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting session info from Ableton: {str(e)}")
        return f"Error getting session info: {str(e)}"


@mcp.tool()
def get_track_info(ctx: Context, track_index: int) -> str:
    """
    Get detailed information about a specific track in Ableton.

    Parameters:
    - track_index: The index of the track to get information about
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_track_info", {"track_index": track_index})
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting track info from Ableton: {str(e)}")
        return f"Error getting track info: {str(e)}"


@mcp.tool()
def create_midi_track(ctx: Context, index: int = -1) -> str:
    """
    Create a new MIDI track in the Ableton session.

    Parameters:
    - index: The index to insert the track at (-1 = end of list)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("create_midi_track", {"index": index})
        return f"Created new MIDI track: {result.get('name', 'unknown')}"
    except Exception as e:
        logger.error(f"Error creating MIDI track: {str(e)}")
        return f"Error creating MIDI track: {str(e)}"


@mcp.tool()
def set_track_name(ctx: Context, track_index: int, name: str) -> str:
    """
    Set the name of a track.

    Parameters:
    - track_index: The index of the track to rename
    - name: The new name for the track
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command(
            "set_track_name", {"track_index": track_index, "name": name}
        )
        return f"Renamed track to: {result.get('name', name)}"
    except Exception as e:
        logger.error(f"Error setting track name: {str(e)}")
        return f"Error setting track name: {str(e)}"


@mcp.tool()
def create_clip(
    ctx: Context, track_index: int, clip_index: int, length: float = 4.0
) -> str:
    """
    Create a new MIDI clip in the specified track and clip slot.

    Parameters:
    - track_index: The index of the track to create the clip in
    - clip_index: The index of the clip slot to create the clip in
    - length: The length of the clip in beats (default: 4.0)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command(
            "create_clip",
            {"track_index": track_index, "clip_index": clip_index, "length": length},
        )
        return f"Created new clip at track {track_index}, slot {clip_index} with length {length} beats"
    except Exception as e:
        logger.error(f"Error creating clip: {str(e)}")
        return f"Error creating clip: {str(e)}"


@mcp.tool()
def add_notes_to_clip(
    ctx: Context,
    track_index: int,
    clip_index: int,
    notes: list[dict[str, int | float | bool]],
) -> str:
    """
    Add MIDI notes to a clip.

    Parameters:
    - track_index: The index of the track containing the clip
    - clip_index: The index of the clip slot containing the clip
    - notes: List of note dictionaries, each with pitch, start_time, duration, velocity, and mute
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command(
            "add_notes_to_clip",
            {"track_index": track_index, "clip_index": clip_index, "notes": notes},
        )
        return f"Added {len(notes)} notes to clip at track {track_index}, slot {clip_index}"
    except Exception as e:
        logger.error(f"Error adding notes to clip: {str(e)}")
        return f"Error adding notes to clip: {str(e)}"


@mcp.tool()
def set_clip_name(ctx: Context, track_index: int, clip_index: int, name: str) -> str:
    """
    Set the name of a clip.

    Parameters:
    - track_index: The index of the track containing the clip
    - clip_index: The index of the clip slot containing the clip
    - name: The new name for the clip
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command(
            "set_clip_name",
            {"track_index": track_index, "clip_index": clip_index, "name": name},
        )
        return f"Renamed clip at track {track_index}, slot {clip_index} to '{name}'"
    except Exception as e:
        logger.error(f"Error setting clip name: {str(e)}")
        return f"Error setting clip name: {str(e)}"


@mcp.tool()
def set_tempo(ctx: Context, tempo: float) -> str:
    """
    Set the tempo of the Ableton session.

    Parameters:
    - tempo: The new tempo in BPM
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_tempo", {"tempo": tempo})
        return f"Set tempo to {tempo} BPM"
    except Exception as e:
        logger.error(f"Error setting tempo: {str(e)}")
        return f"Error setting tempo: {str(e)}"


@mcp.tool()
def load_instrument_or_effect(ctx: Context, track_index: int, uri: str) -> str:
    """
    Load an instrument or effect onto a track using its URI.

    Parameters:
    - track_index: The index of the track to load the instrument on
    - uri: The URI of the instrument or effect to load (e.g., 'query:Synths#Instrument%20Rack:Bass:FileId_5116')
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command(
            "load_browser_item", {"track_index": track_index, "item_uri": uri}
        )

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
def fire_clip(ctx: Context, track_index: int, clip_index: int) -> str:
    """
    Start playing a clip.

    Parameters:
    - track_index: The index of the track containing the clip
    - clip_index: The index of the clip slot containing the clip
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command(
            "fire_clip", {"track_index": track_index, "clip_index": clip_index}
        )
        return f"Started playing clip at track {track_index}, slot {clip_index}"
    except Exception as e:
        logger.error(f"Error firing clip: {str(e)}")
        return f"Error firing clip: {str(e)}"


@mcp.tool()
def stop_clip(ctx: Context, track_index: int, clip_index: int) -> str:
    """
    Stop playing a clip.

    Parameters:
    - track_index: The index of the track containing the clip
    - clip_index: The index of the clip slot containing the clip
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command(
            "stop_clip", {"track_index": track_index, "clip_index": clip_index}
        )
        return f"Stopped clip at track {track_index}, slot {clip_index}"
    except Exception as e:
        logger.error(f"Error stopping clip: {str(e)}")
        return f"Error stopping clip: {str(e)}"


@mcp.tool()
def start_playback(ctx: Context) -> str:
    """Start playing the Ableton session."""
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("start_playback")
        return "Started playback"
    except Exception as e:
        logger.error(f"Error starting playback: {str(e)}")
        return f"Error starting playback: {str(e)}"


@mcp.tool()
def stop_playback(ctx: Context) -> str:
    """Stop Ableton Live's playback."""
    try:
        ableton = get_ableton_connection()
        ableton.send_command("stop_playback")
        return "Playback stopped successfully."
    except Exception as e:
        logger.error(f"Error stopping playback: {str(e)}")
        raise Exception(f"Failed to stop playback: {str(e)}")


@mcp.tool()
def delete_track(ctx: Context, track_index: int) -> str:
    """Delete the track at the specified index.
    Use get_session_info to find the correct index first.
    Indices start from 0."""
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("delete_track", {"track_index": track_index})
        return result.get("message", f"Track {track_index} deleted successfully.")
    except Exception as e:
        logger.error(f"Error deleting track {track_index}: {str(e)}")
        raise Exception(f"Failed to delete track {track_index}: {str(e)}")


@mcp.tool()
def delete_clip(ctx: Context, track_index: int, clip_index: int) -> str:
    """Delete the clip at the specified track and clip index (slot index).
    Use get_track_info to find the correct indices first.
    Indices start from 0."""
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command(
            "delete_clip", {"track_index": track_index, "clip_index": clip_index}
        )
        return result.get(
            "message", f"Clip {clip_index} on track {track_index} deleted successfully."
        )
    except Exception as e:
        logger.error(
            f"Error deleting clip {clip_index} on track {track_index}: {str(e)}"
        )
        raise Exception(
            f"Failed to delete clip {clip_index} on track {track_index}: {str(e)}"
        )


@mcp.tool()
def delete_device(ctx: Context, track_index: int, device_index: int) -> str:
    """Delete a device from a track's device chain. Use get_track_info to see devices.
    Needed to swap instruments, since loading always appends to the chain."""
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command(
            "delete_device", {"track_index": track_index, "device_index": device_index}
        )
        return json.dumps(result)
    except Exception as e:
        logger.error(f"Error deleting device: {str(e)}")
        raise Exception(f"Failed to delete device: {str(e)}")


@mcp.tool()
def get_clip_notes(ctx: Context, track_index: int, clip_index: int) -> str:
    """Read all MIDI notes (pitch, start_time, duration, velocity, mute) from a session clip.
    Use before modifying an existing clip so edits build on what is actually there."""
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command(
            "get_clip_notes", {"track_index": track_index, "clip_index": clip_index}
        )
        return json.dumps(result)
    except Exception as e:
        logger.error(f"Error reading clip notes: {str(e)}")
        raise Exception(f"Failed to read clip notes: {str(e)}")


@mcp.tool()
def get_device_params(ctx: Context, track_index: int, device_index: int) -> str:
    """List a device's parameters: index, name, value, min, max, display string.
    Use to discover what a device exposes before setting values."""
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command(
            "get_device_params",
            {"track_index": track_index, "device_index": device_index},
        )
        return json.dumps(result)
    except Exception as e:
        logger.error(f"Error getting device params: {str(e)}")
        raise Exception(f"Failed to get device params: {str(e)}")


@mcp.tool()
def set_device_param(
    ctx: Context, track_index: int, device_index: int, param: str, value: float
) -> str:
    """Set a device parameter by name (or numeric index) to a value in its native range.
    Returns the resulting display value (e.g. '2.50 dB', '450 Hz') for verification.
    Frequencies on EQ Eight are log-normalized 0-1; set, read the display, iterate."""
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command(
            "set_device_param",
            {
                "track_index": track_index,
                "device_index": device_index,
                "param": param,
                "value": value,
            },
        )
        return json.dumps(result)
    except Exception as e:
        logger.error(f"Error setting device param: {str(e)}")
        raise Exception(f"Failed to set device param: {str(e)}")


@mcp.tool()
def get_device_chains(ctx: Context, track_index: int, device_index: int) -> str:
    """List the chains of a rack device (e.g. drum rack pads) with names and volumes."""
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command(
            "get_device_chains",
            {"track_index": track_index, "device_index": device_index},
        )
        return json.dumps(result)
    except Exception as e:
        logger.error(f"Error listing device chains: {str(e)}")
        raise Exception(f"Failed to list device chains: {str(e)}")


@mcp.tool()
def set_chain_volume(
    ctx: Context, track_index: int, device_index: int, chain_index: int, value: float
) -> str:
    """Set the mixer volume (0.0-1.0, 0.85 = 0dB) of a rack chain, e.g. one drum pad.
    The right fix for a single overbearing sample across all clips."""
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command(
            "set_chain_volume",
            {
                "track_index": track_index,
                "device_index": device_index,
                "chain_index": chain_index,
                "value": value,
            },
        )
        return json.dumps(result)
    except Exception as e:
        logger.error(f"Error setting chain volume: {str(e)}")
        raise Exception(f"Failed to set chain volume: {str(e)}")


@mcp.tool()
def get_clip_envelope(
    ctx: Context,
    track_index: int,
    clip_index: int,
    device_index: int,
    param: str,
    resolution: float = 0.25,
) -> str:
    """Sample a clip's recorded automation envelope for a device parameter (by name).
    Returns time/value/display samples across the clip, or has_envelope: false."""
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command(
            "get_clip_envelope",
            {
                "track_index": track_index,
                "clip_index": clip_index,
                "device_index": device_index,
                "param": param,
                "resolution": resolution,
            },
        )
        return json.dumps(result)
    except Exception as e:
        logger.error(f"Error reading clip envelope: {str(e)}")
        raise Exception(f"Failed to read clip envelope: {str(e)}")


@mcp.tool()
def set_clip_envelope(
    ctx: Context,
    track_index: int,
    clip_index: int,
    device_index: int,
    param: str,
    steps: list[dict[str, float]],
    clear: bool = True,
) -> str:
    """Write step automation into a clip's envelope for a device parameter.
    steps: [{"time": beats, "length": beats, "value": native-range value}, ...].
    Clears any existing envelope for that parameter first unless clear=False."""
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command(
            "set_clip_envelope",
            {
                "track_index": track_index,
                "clip_index": clip_index,
                "device_index": device_index,
                "param": param,
                "steps": steps,
                "clear": clear,
            },
        )
        return json.dumps(result)
    except Exception as e:
        logger.error(f"Error writing clip envelope: {str(e)}")
        raise Exception(f"Failed to write clip envelope: {str(e)}")


@mcp.tool()
def set_track_volume(ctx: Context, track_index: int, value: float) -> str:
    """Set a track's mixer volume. 0.0-1.0 where 0.85 = 0dB."""
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command(
            "set_track_volume", {"track_index": track_index, "value": value}
        )
        return json.dumps(result)
    except Exception as e:
        logger.error(f"Error setting track volume: {str(e)}")
        raise Exception(f"Failed to set track volume: {str(e)}")


@mcp.tool()
def set_send_level(
    ctx: Context, track_index: int, send_index: int, value: float
) -> str:
    """Set a track's send level (0.0-1.0) to a return track."""
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command(
            "set_send_level",
            {"track_index": track_index, "send_index": send_index, "value": value},
        )
        return json.dumps(result)
    except Exception as e:
        logger.error(f"Error setting send level: {str(e)}")
        raise Exception(f"Failed to set send level: {str(e)}")


@mcp.tool()
def set_master_volume(ctx: Context, value: float) -> str:
    """Set the master output volume. 0.0-1.0 where 0.85 = 0dB."""
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_master_volume", {"value": value})
        return json.dumps(result)
    except Exception as e:
        logger.error(f"Error setting master volume: {str(e)}")
        raise Exception(f"Failed to set master volume: {str(e)}")


@mcp.tool()
def get_set_overview(ctx: Context, include_params: bool = False) -> str:
    """Read the whole set in one call: every track, return track and the master —
    mixer (volume/pan/sends), input/output routing, and the device chain on each.
    Devices report any sidechain/routing info Live exposes. include_params=True also
    lists every device parameter (large)."""
    try:
        ableton = get_ableton_connection()
        return json.dumps(ableton.send_command("get_set_overview", {"include_params": include_params}), indent=2)
    except Exception as e:
        return f"Error getting set overview: {str(e)}"


@mcp.tool()
def get_routing(ctx: Context, track_index: int, device_index: int | None = None) -> str:
    """Routing for a track (input/output type+channel and the available options) or,
    with device_index, for a device — e.g. a compressor's sidechain source."""
    try:
        ableton = get_ableton_connection()
        params: dict[str, Any] = {"track_index": track_index}
        if device_index is not None:
            params["device_index"] = device_index
        return json.dumps(ableton.send_command("get_routing", params), indent=2)
    except Exception as e:
        return f"Error getting routing: {str(e)}"


@mcp.tool()
def introspect(ctx: Context, path: str = "", include_methods: bool = False) -> str:
    """Low-level discovery: dir() any Live Object Model object and read its attributes.
    path is relative to the song, e.g. 'tracks[0].devices[1]', 'master_track.devices[0]',
    'return_tracks[0].mixer_device', 'view'. Use this when a higher-level tool doesn't
    expose something — it shows what Live actually has before we build a tool for it."""
    try:
        ableton = get_ableton_connection()
        return json.dumps(ableton.send_command("introspect", {"path": path, "include_methods": include_methods}), indent=2)
    except Exception as e:
        return f"Error introspecting {path!r}: {str(e)}"


@mcp.tool()
def get_params(ctx: Context, path: str) -> str:
    """Parameters (name, value, display string, range) of any device by LOM path —
    reaches master/return devices and devices nested in rack chains, e.g.
    'tracks[2].devices[1]', 'master_track.devices[1].chains[0].devices[1]'.
    Paths come from get_set_overview."""
    try:
        ableton = get_ableton_connection()
        return json.dumps(ableton.send_command("get_params", {"path": path}), indent=2)
    except Exception as e:
        return f"Error getting params for {path!r}: {str(e)}"


@mcp.tool()
def set_param(ctx: Context, path: str, param: str | int, value: float) -> str:
    """Set one parameter (by name or index) on the device at path. value is in the
    parameter's native range (see get_params min/max); it is clamped. Returns before/after."""
    try:
        ableton = get_ableton_connection()
        return json.dumps(ableton.send_command("set_param", {"path": path, "param": param, "value": value}), indent=2)
    except Exception as e:
        return f"Error setting {param!r} on {path!r}: {str(e)}"


@mcp.tool()
def set_routing(ctx: Context, path: str, routing_type: str | None = None, routing_channel: str | None = None) -> str:
    """Set the input routing of a device (a compressor's sidechain source) or a track,
    by display name as listed in get_routing/get_params 'available_*'. Set the type first;
    the available channels depend on it."""
    try:
        ableton = get_ableton_connection()
        return json.dumps(ableton.send_command("set_routing", {"path": path, "routing_type": routing_type, "routing_channel": routing_channel}), indent=2)
    except Exception as e:
        return f"Error setting routing on {path!r}: {str(e)}"


@mcp.tool()
def get_automated_params(ctx: Context) -> str:
    """Every parameter in the set that has automation (device params, recursing racks,
    plus mixer volume/pan/sends on tracks, returns and master): track, device, param,
    param_path, automation state and current value. The inventory to read before
    judging continuity of motion across the arrangement."""
    try:
        ableton = get_ableton_connection()
        return json.dumps(ableton.send_command("get_automated_params"), indent=2)
    except Exception as e:
        return f"Error listing automated params: {str(e)}"


@mcp.tool()
def get_arrangement_envelope(ctx: Context, param_path: str, resolution: float = 1.0) -> str:
    """Sample a parameter's *clip* envelopes across the track's arrangement clips, in beats.
    Note: Live's API does not expose track-lane arrangement automation here (has_envelope
    will be false for it) — use start_capture/stop_capture with automation=True and play
    the song to record what the lanes actually do."""
    try:
        ableton = get_ableton_connection()
        return json.dumps(ableton.send_command("get_arrangement_envelope", {"param_path": param_path, "resolution": resolution}), indent=2)
    except Exception as e:
        return f"Error reading envelope for {param_path!r}: {str(e)}"


@mcp.tool()
def start_capture(ctx: Context, meters: bool = True, automation: bool = True) -> str:
    """Begin recording inside Live, once per timer tick (~10/s) on Live's main thread:
    every track's (and the master's) output meter, and the value of every automated
    parameter against song position. Drive playback yourself (play the whole song, loop a
    section); then stop_capture returns the report, get_capture peeks without stopping.
    Meter values are Live's raw 0.0-1.0 readings — no documented dB mapping, compare
    relatively."""
    try:
        ableton = get_ableton_connection()
        return json.dumps(ableton.send_command("start_capture", {"meters": meters, "automation": automation}), indent=2)
    except Exception as e:
        return f"Error starting capture: {str(e)}"


@mcp.tool()
def get_capture(ctx: Context, resolution: float = 1.0) -> str:
    """Peek at the running (or last) capture. Automation series are bucketed by song
    position at `resolution` beats (mean per bucket)."""
    try:
        ableton = get_ableton_connection()
        return json.dumps(ableton.send_command("get_capture", {"resolution": resolution}), indent=2)
    except Exception as e:
        return f"Error reading capture: {str(e)}"


@mcp.tool()
def stop_capture(ctx: Context, resolution: float = 1.0) -> str:
    """Stop the capture and return the report: meters (peak/mean/clip frames per track,
    loudest first) and, per automated parameter, observed range plus a [beat, value]
    series bucketed at `resolution` beats."""
    try:
        ableton = get_ableton_connection()
        return json.dumps(ableton.send_command("stop_capture", {"resolution": resolution}), indent=2)
    except Exception as e:
        return f"Error stopping capture: {str(e)}"


@mcp.tool()
def set_current_song_time(ctx: Context, time: float) -> str:
    """Move the arrangement playhead to a position in beats."""
    try:
        ableton = get_ableton_connection()
        return json.dumps(ableton.send_command("set_current_song_time", {"time": time}), indent=2)
    except Exception as e:
        return f"Error setting song time: {str(e)}"


def _resolve_als_path(path: str | None) -> str:
    if path:
        return os.path.expanduser(path)
    ableton = get_ableton_connection()
    fp = ableton.send_command("get_song_file").get("file_path")
    if not fp:
        raise Exception("the open set has never been saved; pass a path")
    return fp


@mcp.tool()
def get_automation_grid(ctx: Context, path: str | None = None, bar_beats: float = 4.0) -> str:
    """Every arrangement automation lane in the set as one text grid: a row per lane
    (track / device / param, observed min→max), one character per bar (· = at the lane's
    min, 9 = at its max). Read from the saved .als (defaults to the file Live has open) —
    exact breakpoints, no playback. The file reflects the last save: save in Live first
    if you changed automation."""
    try:
        p = _resolve_als_path(path)
        r = als.read_automation(p)
        return "file: %s\n%d envelopes\n\n%s" % (p, len(r["envelopes"]), als.grid(r, bar_beats=bar_beats))
    except Exception as e:
        return f"Error reading automation: {str(e)}"


@mcp.tool()
def get_automation(ctx: Context, path: str | None = None, track: str | None = None) -> str:
    """Arrangement automation lanes with their exact breakpoints ([time_beats, value], plus
    bezier handles where Live drew curves), read from the saved .als (defaults to the open
    set's file). Optional track filter (substring match on track name). Values are the
    file's native units (e.g. mixer volume 0..1 where 0.85 ≈ 0 dB in Live's scale, gain in
    dB, on/off as 0/1)."""
    try:
        p = _resolve_als_path(path)
        r = als.envelopes_as_dicts(als.read_automation(p))
        if track:
            r["envelopes"] = [e for e in r["envelopes"] if track.lower() in e["track"].lower()]
        for e in r["envelopes"]:
            e["events"] = [[ev["time"], ev["value"]] + ([ev["curve"]] if ev["curve"] else []) for ev in e["events"]]
        return json.dumps(r, indent=2)
    except Exception as e:
        return f"Error reading automation: {str(e)}"


@mcp.tool()
def get_browser_tree(ctx: Context, category_type: str = "all") -> str:
    """
    Get a hierarchical tree of browser categories from Ableton.

    Parameters:
    - category_type: Type of categories to get ('all', 'instruments', 'sounds', 'drums', 'audio_effects', 'midi_effects')
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command(
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
            return "Error: The Ableton browser is not available. Make sure Ableton Live is fully loaded and try again."
        elif "Could not access Live application" in error_msg:
            logger.error(f"Could not access Live application: {error_msg}")
            return "Error: Could not access the Ableton Live application. Make sure Ableton Live is running and the Remote Script is loaded."
        else:
            logger.error(f"Error getting browser tree: {error_msg}")
            return f"Error getting browser tree: {error_msg}"


@mcp.tool()
def get_browser_items_at_path(ctx: Context, path: str) -> str:
    """
    Get browser items at a specific path in Ableton's browser.

    Parameters:
    - path: Path in the format "category/folder/subfolder"
            where category is one of the available browser categories in Ableton
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_browser_items_at_path", {"path": path})

        # Check if there was an error with available categories
        if "error" in result and "available_categories" in result:
            error = result.get("error", "")
            available_cats = result.get("available_categories", [])
            return (
                f"Error: {error}\n"
                f"Available browser categories: {', '.join(available_cats)}"
            )

        return json.dumps(result, indent=2)
    except Exception as e:
        error_msg = str(e)
        if "Browser is not available" in error_msg:
            logger.error(f"Browser is not available in Ableton: {error_msg}")
            return "Error: The Ableton browser is not available. Make sure Ableton Live is fully loaded and try again."
        elif "Could not access Live application" in error_msg:
            logger.error(f"Could not access Live application: {error_msg}")
            return "Error: Could not access the Ableton Live application. Make sure Ableton Live is running and the Remote Script is loaded."
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
def load_drum_kit(ctx: Context, track_index: int, rack_uri: str, kit_path: str) -> str:
    """
    Load a drum rack and then load a specific drum kit into it.

    Parameters:
    - track_index: The index of the track to load on
    - rack_uri: The URI of the drum rack to load (e.g., 'Drums/Drum Rack')
    - kit_path: Path to the drum kit inside the browser (e.g., 'drums/acoustic/kit1')
    """
    try:
        ableton = get_ableton_connection()

        # Step 1: Load the drum rack
        result = ableton.send_command(
            "load_browser_item", {"track_index": track_index, "item_uri": rack_uri}
        )

        if not result.get("loaded", False):
            return f"Failed to load drum rack with URI '{rack_uri}'"

        # Step 2: Get the drum kit items at the specified path
        kit_result = ableton.send_command(
            "get_browser_items_at_path", {"path": kit_path}
        )

        if "error" in kit_result:
            return f"Loaded drum rack but failed to find drum kit: {kit_result.get('error')}"

        # Step 3: Find a loadable drum kit
        kit_items = kit_result.get("items", [])
        loadable_kits = [item for item in kit_items if item.get("is_loadable", False)]

        if not loadable_kits:
            return f"Loaded drum rack but no loadable drum kits found at '{kit_path}'"

        # Step 4: Load the first loadable kit
        kit_uri = loadable_kits[0].get("uri")
        load_result = ableton.send_command(
            "load_browser_item", {"track_index": track_index, "item_uri": kit_uri}
        )

        return f"Loaded drum rack and kit '{loadable_kits[0].get('name')}' on track {track_index}"
    except Exception as e:
        logger.error(f"Error loading drum kit: {str(e)}")
        return f"Error loading drum kit: {str(e)}"


# Main execution
def main():
    """Run the MCP server"""
    mcp.run()


if __name__ == "__main__":
    main()
