# ableton_mcp_server.py
from mcp.server.fastmcp import FastMCP, Context
import socket
import json
import logging
from dataclasses import dataclass
from contextlib import asynccontextmanager
from typing import AsyncIterator, Dict, Any, List, Union

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("AbletonMCPServer")

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
        """Send a command to Ableton and return the response"""
        if not self.sock and not self.connect():
            raise ConnectionError("Not connected to Ableton")
        
        command = {
            "type": command_type,
            "params": params or {}
        }
        
        # Check if this is a state-modifying command
        is_modifying_command = command_type in [
            "create_midi_track", "create_audio_track", "set_track_name",
            "create_clip", "add_notes_to_clip", "set_clip_name",
            "set_tempo", "fire_clip", "stop_clip", "set_device_parameter",
            "start_playback", "stop_playback", "load_instrument_or_effect",
            "arm_track", "disarm_track", "set_arrangement_overdub",
            "start_arrangement_recording", "stop_arrangement_recording",
            "set_loop_start", "set_loop_end", "set_loop_length", "set_playback_position",
            "create_scene", "delete_scene", "duplicate_scene", "trigger_scene", "set_scene_name",
            "set_track_color", "set_clip_color",
            "quantize_clip", "transpose_clip", "duplicate_clip",
            "group_tracks", "set_track_volume", "set_track_pan", "set_track_mute", "set_track_solo",
            "load_audio_sample", "set_warp_mode", "set_clip_warp", "crop_clip", "reverse_clip",
            "set_clip_loop_points", "set_clip_start_marker", "set_clip_end_marker", "set_track_send",
            "copy_clip_to_arrangement", "create_automation", "clear_automation",
            "delete_time", "duplicate_time", "insert_silence", "create_locator",
            "delete_clip", "set_metronome", "tap_tempo", "set_macro_value", "capture_midi", "apply_groove"
        ]
        
        try:
            logger.info(f"Sending command: {command_type} with params: {params}")
            
            # Send the command
            self.sock.sendall(json.dumps(command).encode('utf-8'))
            logger.info(f"Command sent, waiting for response...")
            
            # For state-modifying commands, add a small delay to give Ableton time to process
            if is_modifying_command:
                import time
                time.sleep(0.1)  # 100ms delay
            
            # Set timeout based on command type
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
            if 'response_data' in locals() and response_data:
                logger.error(f"Raw response (first 200 bytes): {response_data[:200]}")
            self.sock = None
            raise Exception(f"Invalid response from Ableton: {str(e)}")
        except Exception as e:
            logger.error(f"Error communicating with Ableton: {str(e)}")
            self.sock = None
            raise Exception(f"Communication error with Ableton: {str(e)}")

@asynccontextmanager
async def server_lifespan(server: FastMCP) -> AsyncIterator[Dict[str, Any]]:
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
    lifespan=server_lifespan
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
            _ableton_connection.sock.sendall(b'')
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
                logger.info(f"Connecting to Ableton (attempt {attempt}/{max_attempts})...")
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
            raise Exception("Could not connect to Ableton. Make sure the Remote Script is running.")
    
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
        result = ableton.send_command("set_track_name", {"track_index": track_index, "name": name})
        return f"Renamed track to: {result.get('name', name)}"
    except Exception as e:
        logger.error(f"Error setting track name: {str(e)}")
        return f"Error setting track name: {str(e)}"

@mcp.tool()
def create_clip(ctx: Context, track_index: int, clip_index: int, length: float = 4.0) -> str:
    """
    Create a new MIDI clip in the specified track and clip slot.
    
    Parameters:
    - track_index: The index of the track to create the clip in
    - clip_index: The index of the clip slot to create the clip in
    - length: The length of the clip in beats (default: 4.0)
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
def add_notes_to_clip(
    ctx: Context, 
    track_index: int, 
    clip_index: int, 
    notes: List[Dict[str, Union[int, float, bool]]]
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
def fire_clip(ctx: Context, track_index: int, clip_index: int) -> str:
    """
    Start playing a clip.
    
    Parameters:
    - track_index: The index of the track containing the clip
    - clip_index: The index of the clip slot containing the clip
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
def stop_clip(ctx: Context, track_index: int, clip_index: int) -> str:
    """
    Stop playing a clip.
    
    Parameters:
    - track_index: The index of the track containing the clip
    - clip_index: The index of the clip slot containing the clip
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
    """Stop playing the Ableton session."""
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("stop_playback")
        return "Stopped playback"
    except Exception as e:
        logger.error(f"Error stopping playback: {str(e)}")
        return f"Error stopping playback: {str(e)}"

@mcp.tool()
def get_browser_tree(ctx: Context, category_type: str = "all") -> str:
    """
    Get a hierarchical tree of browser categories from Ableton.
    
    Parameters:
    - category_type: Type of categories to get ('all', 'instruments', 'sounds', 'drums', 'audio_effects', 'midi_effects')
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
def get_browser_items_at_path(ctx: Context, path: str) -> str:
    """
    Get browser items at a specific path in Ableton's browser.
    
    Parameters:
    - path: Path in the format "category/folder/subfolder"
            where category is one of the available browser categories in Ableton
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
def arm_track(ctx: Context, track_index: int) -> str:
    """
    Arm a track for recording.

    Parameters:
    - track_index: The index of the track to arm
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("arm_track", {"track_index": track_index})
        return f"Armed track {track_index} for recording"
    except Exception as e:
        logger.error(f"Error arming track: {str(e)}")
        return f"Error arming track: {str(e)}"

@mcp.tool()
def disarm_track(ctx: Context, track_index: int) -> str:
    """
    Disarm a track from recording.

    Parameters:
    - track_index: The index of the track to disarm
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("disarm_track", {"track_index": track_index})
        return f"Disarmed track {track_index}"
    except Exception as e:
        logger.error(f"Error disarming track: {str(e)}")
        return f"Error disarming track: {str(e)}"

@mcp.tool()
def set_arrangement_overdub(ctx: Context, enabled: bool) -> str:
    """
    Enable or disable arrangement overdub mode.

    Parameters:
    - enabled: True to enable overdub, False to disable
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_arrangement_overdub", {"enabled": enabled})
        status = "enabled" if enabled else "disabled"
        return f"Arrangement overdub {status}"
    except Exception as e:
        logger.error(f"Error setting arrangement overdub: {str(e)}")
        return f"Error setting arrangement overdub: {str(e)}"

@mcp.tool()
def start_arrangement_recording(ctx: Context) -> str:
    """
    Start recording into the arrangement view.
    This will start playback and begin recording on all armed tracks.
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("start_arrangement_recording")
        return "Started arrangement recording"
    except Exception as e:
        logger.error(f"Error starting arrangement recording: {str(e)}")
        return f"Error starting arrangement recording: {str(e)}"

@mcp.tool()
def stop_arrangement_recording(ctx: Context) -> str:
    """
    Stop arrangement recording and stop playback.
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("stop_arrangement_recording")
        return "Stopped arrangement recording"
    except Exception as e:
        logger.error(f"Error stopping arrangement recording: {str(e)}")
        return f"Error stopping arrangement recording: {str(e)}"

@mcp.tool()
def get_recording_status(ctx: Context) -> str:
    """
    Get the current recording status including armed tracks and recording modes.
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_recording_status")
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting recording status: {str(e)}")
        return f"Error getting recording status: {str(e)}"

@mcp.tool()
def set_loop_start(ctx: Context, position: float) -> str:
    """
    Set the loop start position in beats.

    Parameters:
    - position: Position in beats where the loop should start
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_loop_start", {"position": position})
        return f"Set loop start to {position} beats"
    except Exception as e:
        logger.error(f"Error setting loop start: {str(e)}")
        return f"Error setting loop start: {str(e)}"

@mcp.tool()
def set_loop_end(ctx: Context, position: float) -> str:
    """
    Set the loop end position in beats.

    Parameters:
    - position: Position in beats where the loop should end
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_loop_end", {"position": position})
        return f"Set loop end to {position} beats"
    except Exception as e:
        logger.error(f"Error setting loop end: {str(e)}")
        return f"Error setting loop end: {str(e)}"

@mcp.tool()
def set_loop_length(ctx: Context, length: float) -> str:
    """
    Set the loop length in beats (adjusts loop end based on current loop start).

    Parameters:
    - length: Length of the loop in beats
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_loop_length", {"length": length})
        return f"Set loop length to {length} beats"
    except Exception as e:
        logger.error(f"Error setting loop length: {str(e)}")
        return f"Error setting loop length: {str(e)}"

@mcp.tool()
def get_loop_info(ctx: Context) -> str:
    """
    Get information about the current loop settings.
    Returns loop start, end, length, and whether loop is enabled.
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_loop_info")
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting loop info: {str(e)}")
        return f"Error getting loop info: {str(e)}"

@mcp.tool()
def set_playback_position(ctx: Context, position: float) -> str:
    """
    Jump to a specific position in the arrangement (in beats).

    Parameters:
    - position: Position in beats to jump to
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_playback_position", {"position": position})
        return f"Jumped to position {position} beats"
    except Exception as e:
        logger.error(f"Error setting playback position: {str(e)}")
        return f"Error setting playback position: {str(e)}"

@mcp.tool()
def create_scene(ctx: Context, index: int = -1, name: str = "") -> str:
    """
    Create a new scene at the specified index.

    Parameters:
    - index: Index where to insert the scene (-1 = end of list)
    - name: Optional name for the scene
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("create_scene", {"index": index, "name": name})
        return f"Created scene at index {result.get('index', index)}"
    except Exception as e:
        logger.error(f"Error creating scene: {str(e)}")
        return f"Error creating scene: {str(e)}"

@mcp.tool()
def delete_scene(ctx: Context, scene_index: int) -> str:
    """
    Delete a scene at the specified index.

    Parameters:
    - scene_index: Index of the scene to delete
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("delete_scene", {"scene_index": scene_index})
        return f"Deleted scene at index {scene_index}"
    except Exception as e:
        logger.error(f"Error deleting scene: {str(e)}")
        return f"Error deleting scene: {str(e)}"

@mcp.tool()
def duplicate_scene(ctx: Context, scene_index: int) -> str:
    """
    Duplicate a scene at the specified index.

    Parameters:
    - scene_index: Index of the scene to duplicate
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("duplicate_scene", {"scene_index": scene_index})
        return f"Duplicated scene {scene_index}, new scene at index {result.get('new_index', scene_index + 1)}"
    except Exception as e:
        logger.error(f"Error duplicating scene: {str(e)}")
        return f"Error duplicating scene: {str(e)}"

@mcp.tool()
def trigger_scene(ctx: Context, scene_index: int) -> str:
    """
    Trigger/fire a scene to play all clips in that scene.

    Parameters:
    - scene_index: Index of the scene to trigger
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("trigger_scene", {"scene_index": scene_index})
        return f"Triggered scene {scene_index}"
    except Exception as e:
        logger.error(f"Error triggering scene: {str(e)}")
        return f"Error triggering scene: {str(e)}"

@mcp.tool()
def set_scene_name(ctx: Context, scene_index: int, name: str) -> str:
    """
    Set the name of a scene.

    Parameters:
    - scene_index: Index of the scene to rename
    - name: New name for the scene
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_scene_name", {"scene_index": scene_index, "name": name})
        return f"Renamed scene {scene_index} to '{name}'"
    except Exception as e:
        logger.error(f"Error setting scene name: {str(e)}")
        return f"Error setting scene name: {str(e)}"

@mcp.tool()
def set_track_color(ctx: Context, track_index: int, color_index: int) -> str:
    """
    Set the color of a track.

    Parameters:
    - track_index: Index of the track
    - color_index: Color index (0-69, Ableton's color palette)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_track_color", {"track_index": track_index, "color_index": color_index})
        return f"Set track {track_index} color to index {color_index}"
    except Exception as e:
        logger.error(f"Error setting track color: {str(e)}")
        return f"Error setting track color: {str(e)}"

@mcp.tool()
def set_clip_color(ctx: Context, track_index: int, clip_index: int, color_index: int) -> str:
    """
    Set the color of a clip.

    Parameters:
    - track_index: Index of the track containing the clip
    - clip_index: Index of the clip slot
    - color_index: Color index (0-69, Ableton's color palette)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_clip_color", {
            "track_index": track_index,
            "clip_index": clip_index,
            "color_index": color_index
        })
        return f"Set clip color at track {track_index}, slot {clip_index} to index {color_index}"
    except Exception as e:
        logger.error(f"Error setting clip color: {str(e)}")
        return f"Error setting clip color: {str(e)}"

@mcp.tool()
def get_device_parameters(ctx: Context, track_index: int, device_index: int) -> str:
    """
    Get all parameters for a specific device on a track.

    Parameters:
    - track_index: Index of the track
    - device_index: Index of the device on that track
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_device_parameters", {
            "track_index": track_index,
            "device_index": device_index
        })
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting device parameters: {str(e)}")
        return f"Error getting device parameters: {str(e)}"

@mcp.tool()
def set_device_parameter(ctx: Context, track_index: int, device_index: int, parameter_index: int, value: float) -> str:
    """
    Set a device parameter value.

    Parameters:
    - track_index: Index of the track
    - device_index: Index of the device on that track
    - parameter_index: Index of the parameter
    - value: Value to set (0.0 to 1.0 for most parameters)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_device_parameter", {
            "track_index": track_index,
            "device_index": device_index,
            "parameter_index": parameter_index,
            "value": value
        })
        return f"Set device parameter to {value}"
    except Exception as e:
        logger.error(f"Error setting device parameter: {str(e)}")
        return f"Error setting device parameter: {str(e)}"

@mcp.tool()
def quantize_clip(ctx: Context, track_index: int, clip_index: int, quantize_to: float = 0.25) -> str:
    """
    Quantize all notes in a MIDI clip.

    Parameters:
    - track_index: Index of the track containing the clip
    - clip_index: Index of the clip slot
    - quantize_to: Quantization grid in beats (e.g., 0.25 = 16th notes, 0.5 = 8th notes, 1.0 = quarter notes)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("quantize_clip", {
            "track_index": track_index,
            "clip_index": clip_index,
            "quantize_to": quantize_to
        })
        return f"Quantized clip at track {track_index}, slot {clip_index} to {quantize_to} beats"
    except Exception as e:
        logger.error(f"Error quantizing clip: {str(e)}")
        return f"Error quantizing clip: {str(e)}"

@mcp.tool()
def transpose_clip(ctx: Context, track_index: int, clip_index: int, semitones: int) -> str:
    """
    Transpose all notes in a MIDI clip by a number of semitones.

    Parameters:
    - track_index: Index of the track containing the clip
    - clip_index: Index of the clip slot
    - semitones: Number of semitones to transpose (positive or negative)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("transpose_clip", {
            "track_index": track_index,
            "clip_index": clip_index,
            "semitones": semitones
        })
        return f"Transposed clip by {semitones} semitones"
    except Exception as e:
        logger.error(f"Error transposing clip: {str(e)}")
        return f"Error transposing clip: {str(e)}"

@mcp.tool()
def duplicate_clip(ctx: Context, source_track: int, source_clip: int, dest_track: int, dest_clip: int) -> str:
    """
    Duplicate a clip from one slot to another.

    Parameters:
    - source_track: Index of the source track
    - source_clip: Index of the source clip slot
    - dest_track: Index of the destination track
    - dest_clip: Index of the destination clip slot
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("duplicate_clip", {
            "source_track": source_track,
            "source_clip": source_clip,
            "dest_track": dest_track,
            "dest_clip": dest_clip
        })
        return f"Duplicated clip from track {source_track}, slot {source_clip} to track {dest_track}, slot {dest_clip}"
    except Exception as e:
        logger.error(f"Error duplicating clip: {str(e)}")
        return f"Error duplicating clip: {str(e)}"

@mcp.tool()
def create_audio_track(ctx: Context, index: int = -1) -> str:
    """
    Create a new audio track in the Ableton session.

    Parameters:
    - index: The index to insert the track at (-1 = end of list)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("create_audio_track", {"index": index})
        return f"Created new audio track: {result.get('name', 'unknown')}"
    except Exception as e:
        logger.error(f"Error creating audio track: {str(e)}")
        return f"Error creating audio track: {str(e)}"

@mcp.tool()
def group_tracks(ctx: Context, track_indices: List[int], name: str = "Group") -> str:
    """
    Group multiple tracks together.

    Parameters:
    - track_indices: List of track indices to group
    - name: Name for the group track
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("group_tracks", {
            "track_indices": track_indices,
            "name": name
        })
        return f"Grouped {len(track_indices)} tracks into '{name}'"
    except Exception as e:
        logger.error(f"Error grouping tracks: {str(e)}")
        return f"Error grouping tracks: {str(e)}"

@mcp.tool()
def set_track_volume(ctx: Context, track_index: int, volume: float) -> str:
    """
    Set the volume of a track.

    Parameters:
    - track_index: Index of the track
    - volume: Volume level (0.0 = -inf dB, 0.85 = 0 dB, 1.0 = +6 dB)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_track_volume", {
            "track_index": track_index,
            "volume": volume
        })
        return f"Set track {track_index} volume to {volume}"
    except Exception as e:
        logger.error(f"Error setting track volume: {str(e)}")
        return f"Error setting track volume: {str(e)}"

@mcp.tool()
def set_track_pan(ctx: Context, track_index: int, pan: float) -> str:
    """
    Set the panning of a track.

    Parameters:
    - track_index: Index of the track
    - pan: Pan position (-1.0 = full left, 0.0 = center, 1.0 = full right)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_track_pan", {
            "track_index": track_index,
            "pan": pan
        })
        return f"Set track {track_index} pan to {pan}"
    except Exception as e:
        logger.error(f"Error setting track pan: {str(e)}")
        return f"Error setting track pan: {str(e)}"

@mcp.tool()
def set_track_mute(ctx: Context, track_index: int, mute: bool) -> str:
    """
    Mute or unmute a track.

    Parameters:
    - track_index: Index of the track
    - mute: True to mute, False to unmute
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_track_mute", {
            "track_index": track_index,
            "mute": mute
        })
        status = "muted" if mute else "unmuted"
        return f"Track {track_index} {status}"
    except Exception as e:
        logger.error(f"Error setting track mute: {str(e)}")
        return f"Error setting track mute: {str(e)}"

@mcp.tool()
def set_track_solo(ctx: Context, track_index: int, solo: bool) -> str:
    """
    Solo or unsolo a track.

    Parameters:
    - track_index: Index of the track
    - solo: True to solo, False to unsolo
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_track_solo", {
            "track_index": track_index,
            "solo": solo
        })
        status = "soloed" if solo else "unsoloed"
        return f"Track {track_index} {status}"
    except Exception as e:
        logger.error(f"Error setting track solo: {str(e)}")
        return f"Error setting track solo: {str(e)}"

@mcp.tool()
def load_audio_sample(ctx: Context, track_index: int, clip_index: int, file_path: str = "", browser_uri: str = "") -> str:
    """
    Load an audio sample into a clip slot.

    Parameters:
    - track_index: Index of the track
    - clip_index: Index of the clip slot
    - file_path: Path to the audio file to load (WAV, MP3, AIFF, etc.)
    - browser_uri: URI of the sample in Ableton's browser (alternative to file_path)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("load_audio_sample", {
            "track_index": track_index,
            "clip_index": clip_index,
            "file_path": file_path,
            "browser_uri": browser_uri
        })
        return f"Loaded audio sample into track {track_index}, slot {clip_index}"
    except Exception as e:
        logger.error(f"Error loading audio sample: {str(e)}")
        return f"Error loading audio sample: {str(e)}"

@mcp.tool()
def get_audio_clip_info(ctx: Context, track_index: int, clip_index: int) -> str:
    """
    Get information about an audio clip including warp settings.

    Parameters:
    - track_index: Index of the track
    - clip_index: Index of the clip slot
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_audio_clip_info", {
            "track_index": track_index,
            "clip_index": clip_index
        })
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting audio clip info: {str(e)}")
        return f"Error getting audio clip info: {str(e)}"

@mcp.tool()
def set_warp_mode(ctx: Context, track_index: int, clip_index: int, warp_mode: str) -> str:
    """
    Set the warp mode for an audio clip.

    Parameters:
    - track_index: Index of the track
    - clip_index: Index of the clip slot
    - warp_mode: Warp mode (beats, tones, texture, re_pitch, complex, complex_pro)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_warp_mode", {
            "track_index": track_index,
            "clip_index": clip_index,
            "warp_mode": warp_mode
        })
        return f"Set warp mode to {warp_mode} for clip at track {track_index}, slot {clip_index}"
    except Exception as e:
        logger.error(f"Error setting warp mode: {str(e)}")
        return f"Error setting warp mode: {str(e)}"

@mcp.tool()
def set_clip_warp(ctx: Context, track_index: int, clip_index: int, warping_enabled: bool) -> str:
    """
    Enable or disable warping for an audio clip.

    Parameters:
    - track_index: Index of the track
    - clip_index: Index of the clip slot
    - warping_enabled: True to enable warping, False to disable
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_clip_warp", {
            "track_index": track_index,
            "clip_index": clip_index,
            "warping_enabled": warping_enabled
        })
        status = "enabled" if warping_enabled else "disabled"
        return f"Warping {status} for clip at track {track_index}, slot {clip_index}"
    except Exception as e:
        logger.error(f"Error setting clip warp: {str(e)}")
        return f"Error setting clip warp: {str(e)}"

@mcp.tool()
def crop_clip(ctx: Context, track_index: int, clip_index: int) -> str:
    """
    Crop an audio clip to its loop boundaries.

    Parameters:
    - track_index: Index of the track
    - clip_index: Index of the clip slot
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("crop_clip", {
            "track_index": track_index,
            "clip_index": clip_index
        })
        return f"Cropped clip at track {track_index}, slot {clip_index}"
    except Exception as e:
        logger.error(f"Error cropping clip: {str(e)}")
        return f"Error cropping clip: {str(e)}"

@mcp.tool()
def reverse_clip(ctx: Context, track_index: int, clip_index: int) -> str:
    """
    Reverse an audio clip's sample.

    Parameters:
    - track_index: Index of the track
    - clip_index: Index of the clip slot
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("reverse_clip", {
            "track_index": track_index,
            "clip_index": clip_index
        })
        return f"Reversed clip at track {track_index}, slot {clip_index}"
    except Exception as e:
        logger.error(f"Error reversing clip: {str(e)}")
        return f"Error reversing clip: {str(e)}"

@mcp.tool()
def analyze_audio_clip(ctx: Context, track_index: int, clip_index: int) -> str:
    """
    Analyze an audio clip to provide detailed information about its characteristics.

    Returns comprehensive analysis including:
    - BPM and tempo information
    - Key/pitch detection (if available)
    - Warp markers and transient positions
    - Audio file properties (sample rate, bit depth, duration)
    - Frequency characteristics (brightness, spectral centroid estimates)
    - Waveform envelope description

    Parameters:
    - track_index: Index of the track
    - clip_index: Index of the clip slot
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("analyze_audio_clip", {
            "track_index": track_index,
            "clip_index": clip_index
        })
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error analyzing audio clip: {str(e)}")
        return f"Error analyzing audio clip: {str(e)}"

@mcp.tool()
def get_clip_notes(ctx: Context, track_index: int, clip_index: int) -> str:
    """
    Read all MIDI notes from a clip.

    Returns all notes with their properties:
    - pitch (0-127, MIDI note number)
    - start_time (in beats)
    - duration (in beats)
    - velocity (0-127)
    - mute (boolean)

    This enables analyzing existing MIDI, suggesting changes, transposing,
    harmonizing, or understanding musical content.

    Parameters:
    - track_index: Index of the track
    - clip_index: Index of the clip slot
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_clip_notes", {
            "track_index": track_index,
            "clip_index": clip_index
        })
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting clip notes: {str(e)}")
        return f"Error getting clip notes: {str(e)}"

@mcp.tool()
def set_clip_loop_points(ctx: Context, track_index: int, clip_index: int, loop_start: float, loop_end: float) -> str:
    """
    Set the loop start and end points for a clip.

    Parameters:
    - track_index: Index of the track
    - clip_index: Index of the clip slot
    - loop_start: Loop start position in beats
    - loop_end: Loop end position in beats
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_clip_loop_points", {
            "track_index": track_index,
            "clip_index": clip_index,
            "loop_start": loop_start,
            "loop_end": loop_end
        })
        return f"Set loop points: start={loop_start}, end={loop_end}"
    except Exception as e:
        logger.error(f"Error setting clip loop points: {str(e)}")
        return f"Error setting clip loop points: {str(e)}"

@mcp.tool()
def set_clip_start_marker(ctx: Context, track_index: int, clip_index: int, start_marker: float) -> str:
    """
    Set the start marker position for an audio clip.

    Parameters:
    - track_index: Index of the track
    - clip_index: Index of the clip slot
    - start_marker: Start marker position in sample time
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_clip_start_marker", {
            "track_index": track_index,
            "clip_index": clip_index,
            "start_marker": start_marker
        })
        return f"Set clip start marker to {start_marker}"
    except Exception as e:
        logger.error(f"Error setting clip start marker: {str(e)}")
        return f"Error setting clip start marker: {str(e)}"

@mcp.tool()
def set_clip_end_marker(ctx: Context, track_index: int, clip_index: int, end_marker: float) -> str:
    """
    Set the end marker position for an audio clip.

    Parameters:
    - track_index: Index of the track
    - clip_index: Index of the clip slot
    - end_marker: End marker position in sample time
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_clip_end_marker", {
            "track_index": track_index,
            "clip_index": clip_index,
            "end_marker": end_marker
        })
        return f"Set clip end marker to {end_marker}"
    except Exception as e:
        logger.error(f"Error setting clip end marker: {str(e)}")
        return f"Error setting clip end marker: {str(e)}"

@mcp.tool()
def set_track_send(ctx: Context, track_index: int, send_index: int, value: float) -> str:
    """
    Set the send level for a track to a return track.

    Parameters:
    - track_index: Index of the track
    - send_index: Index of the send (0 for Send A, 1 for Send B, etc.)
    - value: Send level (0.0 to 1.0)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_track_send", {
            "track_index": track_index,
            "send_index": send_index,
            "value": value
        })
        return f"Set send {send_index} on track {track_index} to {value}"
    except Exception as e:
        logger.error(f"Error setting track send: {str(e)}")
        return f"Error setting track send: {str(e)}"

@mcp.tool()
def copy_clip_to_arrangement(ctx: Context, track_index: int, clip_index: int, arrangement_time: float) -> str:
    """
    Copy a clip from session view to arrangement view at a specific time position.

    This enables building arrangements by placing session clips into the timeline.

    Parameters:
    - track_index: Index of the source track
    - clip_index: Index of the clip slot to copy from
    - arrangement_time: Time position in beats where to place the clip in arrangement
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("copy_clip_to_arrangement", {
            "track_index": track_index,
            "clip_index": clip_index,
            "arrangement_time": arrangement_time
        })
        return f"Copied clip from track {track_index}, slot {clip_index} to arrangement at {arrangement_time} beats"
    except Exception as e:
        logger.error(f"Error copying clip to arrangement: {str(e)}")
        return f"Error copying clip to arrangement: {str(e)}"

@mcp.tool()
def create_automation(ctx: Context, track_index: int, parameter_name: str, automation_points: str) -> str:
    """
    Create automation for a track parameter.

    Parameters:
    - track_index: Index of the track
    - parameter_name: Name of the parameter to automate (e.g., "Volume", "Pan", or device parameter)
    - automation_points: JSON string of automation points, e.g., '[{"time": 0, "value": 0.5}, {"time": 4, "value": 0.8}]'
      Each point has "time" in beats and "value" (0.0 to 1.0)

    Common parameter names:
    - "Volume" - Track volume
    - "Pan" - Track panning
    - "Send A", "Send B" - Send levels
    - Device parameters: "Device 0 Parameter 1", etc.

    Example automation_points:
    '[{"time": 0, "value": 0.0}, {"time": 4, "value": 1.0}, {"time": 8, "value": 0.5}]'
    """
    try:
        import json as json_module
        points = json_module.loads(automation_points)

        ableton = get_ableton_connection()
        result = ableton.send_command("create_automation", {
            "track_index": track_index,
            "parameter_name": parameter_name,
            "automation_points": points
        })
        return f"Created automation for {parameter_name} on track {track_index} with {len(points)} points"
    except Exception as e:
        logger.error(f"Error creating automation: {str(e)}")
        return f"Error creating automation: {str(e)}"

@mcp.tool()
def clear_automation(ctx: Context, track_index: int, parameter_name: str, start_time: float = 0.0, end_time: float = 999999.0) -> str:
    """
    Clear automation for a track parameter in a time range.

    Parameters:
    - track_index: Index of the track
    - parameter_name: Name of the parameter (e.g., "Volume", "Pan")
    - start_time: Start time in beats (default: 0.0)
    - end_time: End time in beats (default: very large number for "all")
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("clear_automation", {
            "track_index": track_index,
            "parameter_name": parameter_name,
            "start_time": start_time,
            "end_time": end_time
        })
        return f"Cleared automation for {parameter_name} on track {track_index}"
    except Exception as e:
        logger.error(f"Error clearing automation: {str(e)}")
        return f"Error clearing automation: {str(e)}"

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

@mcp.tool()
def get_arrangement_clips(ctx: Context, track_index: int) -> str:
    """
    Get all clips in arrangement view for a specific track.

    Returns information about clips placed in the arrangement timeline including
    their positions, lengths, names, and properties.

    Parameters:
    - track_index: Index of the track to inspect
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_arrangement_clips", {
            "track_index": track_index
        })
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting arrangement clips: {str(e)}")
        return f"Error getting arrangement clips: {str(e)}"

@mcp.tool()
def delete_time(ctx: Context, start_time: float, end_time: float) -> str:
    """
    Delete a section of time from the arrangement.

    Removes all clips and automation between start and end time,
    shifting everything after the deleted section to the left.

    Parameters:
    - start_time: Start position in beats
    - end_time: End position in beats
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("delete_time", {
            "start_time": start_time,
            "end_time": end_time
        })
        return f"Deleted time from {start_time} to {end_time} beats"
    except Exception as e:
        logger.error(f"Error deleting time: {str(e)}")
        return f"Error deleting time: {str(e)}"

@mcp.tool()
def duplicate_time(ctx: Context, start_time: float, end_time: float) -> str:
    """
    Duplicate a section of time in the arrangement.

    Copies all clips and automation between start and end time,
    and pastes them immediately after the end time.

    Parameters:
    - start_time: Start position in beats
    - end_time: End position in beats
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("duplicate_time", {
            "start_time": start_time,
            "end_time": end_time
        })
        return f"Duplicated time from {start_time} to {end_time} beats"
    except Exception as e:
        logger.error(f"Error duplicating time: {str(e)}")
        return f"Error duplicating time: {str(e)}"

@mcp.tool()
def insert_silence(ctx: Context, position: float, length: float) -> str:
    """
    Insert silence at a position in the arrangement.

    Shifts all clips and automation after the position to the right
    by the specified length, creating empty space.

    Parameters:
    - position: Position in beats where to insert silence
    - length: Length of silence to insert in beats
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("insert_silence", {
            "position": position,
            "length": length
        })
        return f"Inserted {length} beats of silence at position {position}"
    except Exception as e:
        logger.error(f"Error inserting silence: {str(e)}")
        return f"Error inserting silence: {str(e)}"

@mcp.tool()
def create_locator(ctx: Context, position: float, name: str = "") -> str:
    """
    Create a locator/marker at a position in the arrangement.

    Locators help mark important sections like verse, chorus, bridge, etc.

    Parameters:
    - position: Position in beats where to create the locator
    - name: Optional name for the locator (e.g., "Verse", "Chorus")
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("create_locator", {
            "position": position,
            "name": name
        })
        return f"Created locator '{name}' at position {position} beats"
    except Exception as e:
        logger.error(f"Error creating locator: {str(e)}")
        return f"Error creating locator: {str(e)}"

@mcp.tool()
def delete_clip(ctx: Context, track_index: int, clip_index: int) -> str:
    """
    Delete a clip from a clip slot.

    Parameters:
    - track_index: Index of the track
    - clip_index: Index of the clip slot
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("delete_clip", {
            "track_index": track_index,
            "clip_index": clip_index
        })
        return f"Deleted clip at track {track_index}, slot {clip_index}"
    except Exception as e:
        logger.error(f"Error deleting clip: {str(e)}")
        return f"Error deleting clip: {str(e)}"

@mcp.tool()
def set_metronome(ctx: Context, enabled: bool) -> str:
    """
    Enable or disable the metronome.

    Parameters:
    - enabled: True to enable metronome, False to disable
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_metronome", {
            "enabled": enabled
        })
        status = "enabled" if enabled else "disabled"
        return f"Metronome {status}"
    except Exception as e:
        logger.error(f"Error setting metronome: {str(e)}")
        return f"Error setting metronome: {str(e)}"

@mcp.tool()
def tap_tempo(ctx: Context) -> str:
    """
    Tap tempo - call this repeatedly to set tempo by tapping.

    Tap this function multiple times in rhythm to set the song tempo.
    Ableton will calculate the tempo based on the time between taps.
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("tap_tempo")
        return f"Tempo tap registered. Current tempo: {result.get('tempo', 'unknown')} BPM"
    except Exception as e:
        logger.error(f"Error tapping tempo: {str(e)}")
        return f"Error tapping tempo: {str(e)}"

@mcp.tool()
def get_macro_values(ctx: Context, track_index: int, device_index: int) -> str:
    """
    Get the values of all 8 macro controls on a rack device.

    Racks (Instrument Rack, Drum Rack, Audio Effect Rack, MIDI Effect Rack)
    have 8 macro knobs that can control multiple parameters at once.

    Parameters:
    - track_index: Index of the track
    - device_index: Index of the rack device on that track
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_macro_values", {
            "track_index": track_index,
            "device_index": device_index
        })
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting macro values: {str(e)}")
        return f"Error getting macro values: {str(e)}"

@mcp.tool()
def set_macro_value(ctx: Context, track_index: int, device_index: int, macro_index: int, value: float) -> str:
    """
    Set the value of a specific macro control on a rack device.

    Parameters:
    - track_index: Index of the track
    - device_index: Index of the rack device on that track
    - macro_index: Index of the macro (0-7 for Macro 1-8)
    - value: Value to set (0.0 to 1.0)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_macro_value", {
            "track_index": track_index,
            "device_index": device_index,
            "macro_index": macro_index,
            "value": value
        })
        return f"Set Macro {macro_index + 1} to {value}"
    except Exception as e:
        logger.error(f"Error setting macro value: {str(e)}")
        return f"Error setting macro value: {str(e)}"

@mcp.tool()
def capture_midi(ctx: Context, track_index: int, clip_index: int) -> str:
    """
    Capture recently played MIDI into a clip slot.

    This captures MIDI notes that were recently played (even if not recording),
    and creates a new clip with those notes. This is a Live 11+ feature.

    Great for capturing spontaneous ideas without having to record first.

    Parameters:
    - track_index: Index of the track to capture MIDI to
    - clip_index: Index of the clip slot to create the captured clip in
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("capture_midi", {
            "track_index": track_index,
            "clip_index": clip_index
        })
        return f"Captured MIDI to track {track_index}, slot {clip_index}"
    except Exception as e:
        logger.error(f"Error capturing MIDI: {str(e)}")
        return f"Error capturing MIDI: {str(e)}"

@mcp.tool()
def apply_groove(ctx: Context, track_index: int, clip_index: int, groove_amount: float = 1.0) -> str:
    """
    Apply groove/swing to a MIDI clip.

    Groove adds timing variations and velocity changes to create more human feel.
    Uses the global groove pool settings in Ableton.

    Parameters:
    - track_index: Index of the track containing the clip
    - clip_index: Index of the clip slot
    - groove_amount: Amount of groove to apply (0.0 = none, 1.0 = full)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("apply_groove", {
            "track_index": track_index,
            "clip_index": clip_index,
            "groove_amount": groove_amount
        })
        return f"Applied groove (amount: {groove_amount}) to clip at track {track_index}, slot {clip_index}"
    except Exception as e:
        logger.error(f"Error applying groove: {str(e)}")
        return f"Error applying groove: {str(e)}"

# Main execution
def main():
    """Run the MCP server"""
    mcp.run()

if __name__ == "__main__":
    main()