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
            "create_return_track", "set_send", "set_return_track_name",
            "load_device_on_return",
            "set_track_volume", "set_track_panning", "set_track_mute",
            "set_track_solo", "set_track_arm", "set_track_color",
            "set_return_track_volume", "set_return_track_panning",
            "set_return_track_mute", "set_return_track_color",
            "set_master_volume", "set_master_panning",
            "set_current_song_time", "set_arrangement_record",
            "set_session_record", "set_overdub", "set_metronome",
            "tap_tempo", "set_nudge_up", "set_nudge_down",
            "undo", "redo"
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
            item_name = result.get("item_name", uri)
            track_name = result.get("track_name", str(track_index))
            return f"Loaded '{item_name}' onto track '{track_name}' (index {track_index})"
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
def get_current_song_time(ctx: Context) -> str:
    """Get the current playback position in beats."""
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_current_song_time")
        return f"Current song time: {result['current_song_time']:.3f} beats"
    except Exception as e:
        logger.error(f"Error getting song time: {str(e)}")
        return f"Error getting song time: {str(e)}"

@mcp.tool()
def set_current_song_time(ctx: Context, time: float) -> str:
    """
    Jump the playback position to a beat position.

    Parameters:
    - time: Position in beats (>= 0)
    """
    try:
        ableton = get_ableton_connection()
        ableton.send_command("set_current_song_time", {"time": time})
        return f"Song time set to {time:.3f} beats"
    except Exception as e:
        logger.error(f"Error setting song time: {str(e)}")
        return f"Error setting song time: {str(e)}"

@mcp.tool()
def set_arrangement_record(ctx: Context, record: bool) -> str:
    """
    Enable or disable arrangement recording.

    Parameters:
    - record: True to enable arrangement record, False to disable
    """
    try:
        ableton = get_ableton_connection()
        ableton.send_command("set_arrangement_record", {"record": record})
        state = "enabled" if record else "disabled"
        return f"Arrangement record {state}"
    except Exception as e:
        logger.error(f"Error setting arrangement record: {str(e)}")
        return f"Error setting arrangement record: {str(e)}"

@mcp.tool()
def set_session_record(ctx: Context, record: bool) -> str:
    """
    Enable or disable session recording.

    Parameters:
    - record: True to enable session record, False to disable
    """
    try:
        ableton = get_ableton_connection()
        ableton.send_command("set_session_record", {"record": record})
        state = "enabled" if record else "disabled"
        return f"Session record {state}"
    except Exception as e:
        logger.error(f"Error setting session record: {str(e)}")
        return f"Error setting session record: {str(e)}"

@mcp.tool()
def set_overdub(ctx: Context, overdub: bool) -> str:
    """
    Enable or disable overdub.

    Parameters:
    - overdub: True to enable overdub, False to disable
    """
    try:
        ableton = get_ableton_connection()
        ableton.send_command("set_overdub", {"overdub": overdub})
        state = "enabled" if overdub else "disabled"
        return f"Overdub {state}"
    except Exception as e:
        logger.error(f"Error setting overdub: {str(e)}")
        return f"Error setting overdub: {str(e)}"

@mcp.tool()
def set_metronome(ctx: Context, metronome: bool) -> str:
    """
    Enable or disable the metronome.

    Parameters:
    - metronome: True to enable, False to disable
    """
    try:
        ableton = get_ableton_connection()
        ableton.send_command("set_metronome", {"metronome": metronome})
        state = "enabled" if metronome else "disabled"
        return f"Metronome {state}"
    except Exception as e:
        logger.error(f"Error setting metronome: {str(e)}")
        return f"Error setting metronome: {str(e)}"

@mcp.tool()
def tap_tempo(ctx: Context) -> str:
    """Send a tap tempo pulse. Call repeatedly in rhythm to set tempo by tapping."""
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("tap_tempo")
        return f"Tap received. Current tempo: {result['tempo']:.2f} BPM"
    except Exception as e:
        logger.error(f"Error tapping tempo: {str(e)}")
        return f"Error tapping tempo: {str(e)}"

@mcp.tool()
def set_nudge_up(ctx: Context, nudge: bool) -> str:
    """
    Set the nudge-up state. Set to True to nudge tempo up, False to release.

    Parameters:
    - nudge: True to activate nudge up, False to release
    """
    try:
        ableton = get_ableton_connection()
        ableton.send_command("set_nudge_up", {"nudge": nudge})
        return f"Nudge up {'activated' if nudge else 'released'}"
    except Exception as e:
        logger.error(f"Error setting nudge up: {str(e)}")
        return f"Error setting nudge up: {str(e)}"

@mcp.tool()
def set_nudge_down(ctx: Context, nudge: bool) -> str:
    """
    Set the nudge-down state. Set to True to nudge tempo down, False to release.

    Parameters:
    - nudge: True to activate nudge down, False to release
    """
    try:
        ableton = get_ableton_connection()
        ableton.send_command("set_nudge_down", {"nudge": nudge})
        return f"Nudge down {'activated' if nudge else 'released'}"
    except Exception as e:
        logger.error(f"Error setting nudge down: {str(e)}")
        return f"Error setting nudge down: {str(e)}"

@mcp.tool()
def undo(ctx: Context) -> str:
    """Undo the last action in Ableton."""
    try:
        ableton = get_ableton_connection()
        ableton.send_command("undo")
        return "Undo successful"
    except Exception as e:
        logger.error(f"Error undoing: {str(e)}")
        return f"Error undoing: {str(e)}"

@mcp.tool()
def redo(ctx: Context) -> str:
    """Redo the last undone action in Ableton."""
    try:
        ableton = get_ableton_connection()
        ableton.send_command("redo")
        return "Redo successful"
    except Exception as e:
        logger.error(f"Error redoing: {str(e)}")
        return f"Error redoing: {str(e)}"

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
def load_drum_kit(ctx: Context, track_index: int, rack_uri: str, kit_uri: str) -> str:
    """
    Load a drum rack and then load a specific drum kit into it.

    Parameters:
    - track_index: The index of the track to load on
    - rack_uri: The URI of the drum rack (use 'query:Drums#Drum%20Rack')
    - kit_uri: The URI of the drum kit to load (e.g. 'query:Drums#FileId_12860' for 808 Core Kit).
               Use get_browser_items_at_path('Drums') to enumerate available kits and their URIs.
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

        # Step 2: Load the specific kit by URI
        kit_result = ableton.send_command("load_browser_item", {
            "track_index": track_index,
            "item_uri": kit_uri
        })

        if not kit_result.get("loaded", False):
            return f"Loaded drum rack but failed to load kit with URI '{kit_uri}'"

        kit_name = kit_result.get("item_name", kit_uri)
        track_name = kit_result.get("track_name", str(track_index))
        return f"Loaded drum rack and kit '{kit_name}' on track '{track_name}' (index {track_index})"
    except Exception as e:
        logger.error(f"Error loading drum kit: {str(e)}")
        return f"Error loading drum kit: {str(e)}"

@mcp.tool()
def get_return_tracks(ctx: Context) -> str:
    """Get information about all return tracks in the Ableton session."""
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_return_tracks")
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting return tracks: {str(e)}")
        return f"Error getting return tracks: {str(e)}"

@mcp.tool()
def create_return_track(ctx: Context) -> str:
    """Create a new return track in the Ableton session."""
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("create_return_track")
        return f"Created return track '{result.get('name', 'unknown')}' at index {result.get('index', '?')}"
    except Exception as e:
        logger.error(f"Error creating return track: {str(e)}")
        return f"Error creating return track: {str(e)}"

@mcp.tool()
def set_return_track_name(ctx: Context, return_track_index: int, name: str) -> str:
    """
    Set the name of a return track.

    Parameters:
    - return_track_index: The index of the return track to rename (0-based)
    - name: The new name for the return track
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_return_track_name", {
            "return_track_index": return_track_index,
            "name": name
        })
        return f"Renamed return track {return_track_index} to '{result.get('name', name)}'"
    except Exception as e:
        logger.error(f"Error setting return track name: {str(e)}")
        return f"Error setting return track name: {str(e)}"

@mcp.tool()
def set_send(ctx: Context, source_track_index: int, return_track_index: int, send_amount: float) -> str:
    """
    Set the send amount from a source track to a return track.

    Parameters:
    - source_track_index: Index of the source track
    - return_track_index: Index of the return track (0-based)
    - send_amount: Send level from 0.0 (off) to 1.0 (full)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_send", {
            "source_track_index": source_track_index,
            "return_track_index": return_track_index,
            "send_amount": send_amount
        })
        return (f"Set send from '{result.get('source_track')}' to return {return_track_index} "
                f"-> {result.get('send_amount', send_amount):.2f}")
    except Exception as e:
        logger.error(f"Error setting send: {str(e)}")
        return f"Error setting send: {str(e)}"

@mcp.tool()
def set_track_volume(ctx: Context, track_index: int, volume: float) -> str:
    """
    Set the volume of a track.

    Parameters:
    - track_index: Index of the track
    - volume: Volume level from 0.0 (silent) to 1.0 (full). Default unity is ~0.85.
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_track_volume", {"track_index": track_index, "volume": volume})
        return f"Set volume of '{result.get('track')}' to {result.get('volume'):.3f}"
    except Exception as e:
        return f"Error setting track volume: {str(e)}"

@mcp.tool()
def set_track_panning(ctx: Context, track_index: int, panning: float) -> str:
    """
    Set the panning of a track.

    Parameters:
    - track_index: Index of the track
    - panning: Pan position from -1.0 (full left) to 1.0 (full right), 0.0 = center
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_track_panning", {"track_index": track_index, "panning": panning})
        return f"Set panning of '{result.get('track')}' to {result.get('panning'):.3f}"
    except Exception as e:
        return f"Error setting track panning: {str(e)}"

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
        result = ableton.send_command("set_track_mute", {"track_index": track_index, "mute": mute})
        state = "muted" if result.get("mute") else "unmuted"
        return f"Track '{result.get('track')}' {state}"
    except Exception as e:
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
        result = ableton.send_command("set_track_solo", {"track_index": track_index, "solo": solo})
        state = "soloed" if result.get("solo") else "unsoloed"
        return f"Track '{result.get('track')}' {state}"
    except Exception as e:
        return f"Error setting track solo: {str(e)}"

@mcp.tool()
def set_track_arm(ctx: Context, track_index: int, arm: bool) -> str:
    """
    Arm or disarm a track for recording.

    Parameters:
    - track_index: Index of the track
    - arm: True to arm, False to disarm
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_track_arm", {"track_index": track_index, "arm": arm})
        state = "armed" if result.get("arm") else "disarmed"
        return f"Track '{result.get('track')}' {state}"
    except Exception as e:
        return f"Error setting track arm: {str(e)}"

@mcp.tool()
def set_track_color(ctx: Context, track_index: int, color: int) -> str:
    """
    Set the color of a track.

    Parameters:
    - track_index: Index of the track
    - color: RGB color as an integer (e.g. 0xFF0000 for red)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_track_color", {"track_index": track_index, "color": color})
        return f"Set color of '{result.get('track')}' to {hex(result.get('color', 0))}"
    except Exception as e:
        return f"Error setting track color: {str(e)}"

@mcp.tool()
def set_return_track_volume(ctx: Context, return_track_index: int, volume: float) -> str:
    """
    Set the volume of a return track.

    Parameters:
    - return_track_index: Index of the return track (0-based)
    - volume: Volume level from 0.0 to 1.0
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_return_track_volume", {"return_track_index": return_track_index, "volume": volume})
        return f"Set volume of return '{result.get('track')}' to {result.get('volume'):.3f}"
    except Exception as e:
        return f"Error setting return track volume: {str(e)}"

@mcp.tool()
def set_return_track_panning(ctx: Context, return_track_index: int, panning: float) -> str:
    """
    Set the panning of a return track.

    Parameters:
    - return_track_index: Index of the return track (0-based)
    - panning: Pan position from -1.0 (left) to 1.0 (right), 0.0 = center
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_return_track_panning", {"return_track_index": return_track_index, "panning": panning})
        return f"Set panning of return '{result.get('track')}' to {result.get('panning'):.3f}"
    except Exception as e:
        return f"Error setting return track panning: {str(e)}"

@mcp.tool()
def set_return_track_mute(ctx: Context, return_track_index: int, mute: bool) -> str:
    """
    Mute or unmute a return track.

    Parameters:
    - return_track_index: Index of the return track (0-based)
    - mute: True to mute, False to unmute
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_return_track_mute", {"return_track_index": return_track_index, "mute": mute})
        state = "muted" if result.get("mute") else "unmuted"
        return f"Return track '{result.get('track')}' {state}"
    except Exception as e:
        return f"Error setting return track mute: {str(e)}"

@mcp.tool()
def set_return_track_color(ctx: Context, return_track_index: int, color: int) -> str:
    """
    Set the color of a return track.

    Parameters:
    - return_track_index: Index of the return track (0-based)
    - color: RGB color as an integer (e.g. 0xFF0000 for red)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_return_track_color", {"return_track_index": return_track_index, "color": color})
        return f"Set color of return '{result.get('track')}' to {hex(result.get('color', 0))}"
    except Exception as e:
        return f"Error setting return track color: {str(e)}"

@mcp.tool()
def set_master_volume(ctx: Context, volume: float) -> str:
    """
    Set the master track volume.

    Parameters:
    - volume: Volume level from 0.0 to 1.0
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_master_volume", {"volume": volume})
        return f"Set master volume to {result.get('volume'):.3f}"
    except Exception as e:
        return f"Error setting master volume: {str(e)}"

@mcp.tool()
def set_master_panning(ctx: Context, panning: float) -> str:
    """
    Set the master track panning.

    Parameters:
    - panning: Pan position from -1.0 (left) to 1.0 (right), 0.0 = center
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_master_panning", {"panning": panning})
        return f"Set master panning to {result.get('panning'):.3f}"
    except Exception as e:
        return f"Error setting master panning: {str(e)}"

@mcp.tool()
def load_device_on_return(ctx: Context, return_track_index: int, uri: str) -> str:
    """
    Load an instrument or effect onto a return track using its URI.

    Parameters:
    - return_track_index: Index of the return track (0-based)
    - uri: The URI of the device to load (e.g. 'query:AudioFx#Hybrid%20Reverb')
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("load_device_on_return", {
            "return_track_index": return_track_index,
            "item_uri": uri
        })
        return (f"Loaded '{result.get('device_name')}' onto return track "
                f"'{result.get('return_track_name')}' (index {return_track_index})")
    except Exception as e:
        logger.error(f"Error loading device on return track: {str(e)}")
        return f"Error loading device on return track: {str(e)}"

# -------------------------------------------------------------------------
# Phase 2 — Scene Management
# -------------------------------------------------------------------------

@mcp.tool()
def get_scenes(ctx: Context) -> str:
    """Get all scenes in the Ableton session, including name, color, and tempo."""
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_scenes", {})
        scenes = result.get("scenes", [])
        lines = [f"Scenes ({result.get('scene_count', 0)} total):"]
        for s in scenes:
            tempo_str = f", tempo={s['tempo']:.1f}" if s.get("tempo") else ""
            lines.append(f"  [{s['index']}] '{s['name']}' color={hex(s.get('color', 0))}{tempo_str}")
        return "\n".join(lines)
    except Exception as e:
        return f"Error getting scenes: {str(e)}"

@mcp.tool()
def create_scene(ctx: Context, index: int = -1) -> str:
    """
    Create a new empty scene.

    Parameters:
    - index: Position to insert the scene (-1 appends at end)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("create_scene", {"index": index})
        return f"Created scene '{result.get('name')}' at index {result.get('index')}"
    except Exception as e:
        return f"Error creating scene: {str(e)}"

@mcp.tool()
def delete_scene(ctx: Context, scene_index: int) -> str:
    """
    Delete a scene.

    Parameters:
    - scene_index: Index of the scene to delete
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("delete_scene", {"scene_index": scene_index})
        return f"Deleted scene '{result.get('name')}' (was index {result.get('deleted_index')})"
    except Exception as e:
        return f"Error deleting scene: {str(e)}"

@mcp.tool()
def fire_scene(ctx: Context, scene_index: int) -> str:
    """
    Launch all clips in a scene simultaneously.

    Parameters:
    - scene_index: Index of the scene to fire
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("fire_scene", {"scene_index": scene_index})
        return f"Fired scene '{result.get('name')}' (index {result.get('index')})"
    except Exception as e:
        return f"Error firing scene: {str(e)}"

@mcp.tool()
def set_scene_name(ctx: Context, scene_index: int, name: str) -> str:
    """
    Rename a scene.

    Parameters:
    - scene_index: Index of the scene
    - name: New name for the scene
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_scene_name", {"scene_index": scene_index, "name": name})
        return f"Renamed scene {result.get('index')} to '{result.get('name')}'"
    except Exception as e:
        return f"Error setting scene name: {str(e)}"

@mcp.tool()
def set_scene_color(ctx: Context, scene_index: int, color: int) -> str:
    """
    Set the color of a scene.

    Parameters:
    - scene_index: Index of the scene
    - color: RGB color as an integer (e.g. 0xFF0000 for red)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_scene_color", {"scene_index": scene_index, "color": color})
        return f"Set color of scene '{result.get('name')}' to {hex(result.get('color', 0))}"
    except Exception as e:
        return f"Error setting scene color: {str(e)}"

@mcp.tool()
def set_scene_tempo(ctx: Context, scene_index: int, tempo: float) -> str:
    """
    Set the tempo override on a scene. When fired, Live jumps to this BPM.
    Pass 0.0 to clear the override.

    Parameters:
    - scene_index: Index of the scene
    - tempo: BPM value (e.g. 128.0), or 0.0 to clear
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_scene_tempo", {"scene_index": scene_index, "tempo": tempo})
        tempo_val = result.get("tempo", 0.0)
        tempo_str = f"{tempo_val:.1f} BPM" if tempo_val else "cleared"
        return f"Scene '{result.get('name')}' tempo {tempo_str}"
    except Exception as e:
        return f"Error setting scene tempo: {str(e)}"

@mcp.tool()
def duplicate_scene(ctx: Context, scene_index: int) -> str:
    """
    Duplicate a scene, inserting the copy immediately after the original.

    Parameters:
    - scene_index: Index of the scene to duplicate
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("duplicate_scene", {"scene_index": scene_index})
        return f"Duplicated scene {result.get('source_index')} -> new scene '{result.get('name')}' at index {result.get('new_index')}"
    except Exception as e:
        return f"Error duplicating scene: {str(e)}"

@mcp.tool()
def stop_all_clips(ctx: Context) -> str:
    """Stop all currently playing clips across all tracks."""
    try:
        ableton = get_ableton_connection()
        ableton.send_command("stop_all_clips", {})
        return "All clips stopped"
    except Exception as e:
        return f"Error stopping all clips: {str(e)}"


@mcp.tool()
def get_device_parameters(ctx: Context, track_index: int, device_index: int) -> str:
    """
    Get all parameters for a device on a track.

    Parameters:
    - track_index: The index of the track
    - device_index: The index of the device on the track (from get_track_info)
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
def set_device_parameter(ctx: Context, track_index: int, device_index: int, param_index: int, value: float) -> str:
    """
    Set a parameter value on a device.

    Parameters:
    - track_index: The index of the track
    - device_index: The index of the device on the track
    - param_index: The index of the parameter (from get_device_parameters)
    - value: The new value (will be clamped to the parameter's min/max range)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_device_parameter", {
            "track_index": track_index,
            "device_index": device_index,
            "param_index": param_index,
            "value": value
        })
        return (f"Set '{result.get('device_name')}' param '{result.get('param_name')}' "
                f"to {result.get('value_string')} (raw: {result.get('value'):.4f})")
    except Exception as e:
        logger.error(f"Error setting device parameter: {str(e)}")
        return f"Error setting device parameter: {str(e)}"


@mcp.tool()
def get_notes_from_clip(ctx: Context, track_index: int, clip_index: int) -> str:
    """
    Get all MIDI notes from a clip.

    Parameters:
    - track_index: The index of the track
    - clip_index: The index of the clip slot
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_notes_from_clip", {
            "track_index": track_index,
            "clip_index": clip_index,
        })
        notes = result.get("notes", [])
        return (f"Clip '{result.get('clip_name')}' (length {result.get('clip_length')} bars) "
                f"has {len(notes)} note(s):\n" +
                "\n".join(
                    f"  pitch={n['pitch']} start={n['start_time']:.3f} "
                    f"dur={n['duration']:.3f} vel={n['velocity']} mute={n['mute']}"
                    for n in notes
                ))
    except Exception as e:
        logger.error(f"Error getting notes from clip: {str(e)}")
        return f"Error getting notes from clip: {str(e)}"


@mcp.tool()
def remove_notes_from_clip(ctx: Context, track_index: int, clip_index: int,
                           from_pitch: int = 0, pitch_span: int = 128,
                           from_time: float = 0.0, time_span: float = 1e9) -> str:
    """
    Remove notes from a MIDI clip within a pitch and time range.

    Parameters:
    - track_index: Index of the track (0-based)
    - clip_index: Index of the clip slot (0-based)
    - from_pitch: Lowest pitch to remove (0-127, default 0)
    - pitch_span: Number of pitches to cover (default 128 = all)
    - from_time: Start time in beats (default 0.0)
    - time_span: Duration in beats to cover (default 1e9 = all)

    Omit all range parameters to remove every note in the clip.
    """
    try:
        ableton = get_ableton_connection()
        ableton.send_command("remove_notes_from_clip", {
            "track_index": track_index,
            "clip_index": clip_index,
            "from_pitch": from_pitch,
            "pitch_span": pitch_span,
            "from_time": from_time,
            "time_span": time_span,
        })
        return f"Notes removed from clip {track_index}/{clip_index}"
    except Exception as e:
        logger.error(f"Error removing notes from clip: {str(e)}")
        return f"Error removing notes from clip: {str(e)}"


@mcp.tool()
def apply_note_modifications(ctx: Context, track_index: int, clip_index: int, notes: list) -> str:
    """
    Modify existing notes in a MIDI clip in place.

    Each entry in `notes` identifies a note by its current pitch and start_time,
    then specifies new values for any fields to change.

    Parameters:
    - track_index: Index of the track (0-based)
    - clip_index: Index of the clip slot (0-based)
    - notes: List of modification objects, each with:
        - pitch: Current pitch of the note to modify (required, for lookup)
        - start_time: Current start time of the note to modify (required, for lookup)
        - new_pitch: New pitch (optional)
        - new_start_time: New start time in beats (optional)
        - new_duration: New duration in beats (optional)
        - new_velocity: New velocity 0-127 (optional)
        - new_mute: New mute state (optional)

    Workflow: call get_notes_from_clip first to inspect current state, then call
    this tool with the modifications you want to apply.
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("apply_note_modifications", {
            "track_index": track_index,
            "clip_index": clip_index,
            "notes": notes,
        })
        return f"Updated {result.get('updated', 0)} note(s) in clip {track_index}/{clip_index}"
    except Exception as e:
        logger.error(f"Error applying note modifications: {str(e)}")
        return f"Error applying note modifications: {str(e)}"


@mcp.tool()
def set_clip_loop(ctx: Context, track_index: int, clip_index: int,
                  loop_start: float, loop_end: float, loop_on: bool = True) -> str:
    """
    Set the loop region and enable/disable looping for a clip.

    Parameters:
    - track_index: The index of the track
    - clip_index: The index of the clip slot
    - loop_start: Loop start position in beats
    - loop_end: Loop end position in beats
    - loop_on: Whether looping is enabled (default True)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_clip_loop", {
            "track_index": track_index,
            "clip_index": clip_index,
            "loop_start": loop_start,
            "loop_end": loop_end,
            "loop_on": loop_on,
        })
        return (f"Loop set: start={result['loop_start']} end={result['loop_end']} "
                f"looping={result['looping']}")
    except Exception as e:
        logger.error(f"Error setting clip loop: {str(e)}")
        return f"Error setting clip loop: {str(e)}"


@mcp.tool()
def set_clip_color(ctx: Context, track_index: int, clip_index: int, color: int) -> str:
    """
    Set the color of a clip.

    Parameters:
    - track_index: The index of the track
    - clip_index: The index of the clip slot
    - color: RGB color as an integer (e.g. 16711680 for red)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_clip_color", {
            "track_index": track_index,
            "clip_index": clip_index,
            "color": color,
        })
        return f"Clip color set to {result['color']}"
    except Exception as e:
        logger.error(f"Error setting clip color: {str(e)}")
        return f"Error setting clip color: {str(e)}"


@mcp.tool()
def duplicate_clip(ctx: Context, track_index: int, clip_index: int,
                   target_clip_index: int) -> str:
    """
    Duplicate a clip into another empty slot on the same track.

    Parameters:
    - track_index: The index of the track
    - clip_index: The source clip slot index
    - target_clip_index: The destination clip slot index (must be empty)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("duplicate_clip", {
            "track_index": track_index,
            "clip_index": clip_index,
            "target_clip_index": target_clip_index,
        })
        return (f"Clip duplicated from slot {result['source_clip_index']} "
                f"to slot {result['target_clip_index']} ('{result['clip_name']}')")
    except Exception as e:
        logger.error(f"Error duplicating clip: {str(e)}")
        return f"Error duplicating clip: {str(e)}"


@mcp.tool()
def quantize_clip(ctx: Context, track_index: int, clip_index: int,
                  quantize_to: float = 0.25, amount: float = 1.0) -> str:
    """
    Quantize notes in a MIDI clip.

    Parameters:
    - track_index: The index of the track
    - clip_index: The index of the clip slot
    - quantize_to: Note division to quantize to (1.0=quarter note, 0.5=8th, 0.25=16th, 0.125=32nd)
    - amount: Quantize strength from 0.0 (none) to 1.0 (full)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("quantize_clip", {
            "track_index": track_index,
            "clip_index": clip_index,
            "quantize_to": quantize_to,
            "amount": amount,
        })
        return (f"Quantized clip at track {result['track_index']} slot {result['clip_index']} "
                f"to {result['quantize_to']} with amount {result['amount']}")
    except Exception as e:
        logger.error(f"Error quantizing clip: {str(e)}")
        return f"Error quantizing clip: {str(e)}"


@mcp.tool()
def get_clip_info(ctx: Context, track_index: int, clip_index: int) -> str:
    """
    Get detailed information about a clip.

    Parameters:
    - track_index: Index of the track (0-based)
    - clip_index: Index of the clip slot (0-based)

    Returns name, length, color, type (audio/midi), playback state, and loop settings.
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_clip_info", {
            "track_index": track_index,
            "clip_index": clip_index,
        })
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting clip info: {str(e)}")
        return f"Error getting clip info: {str(e)}"


@mcp.tool()
def get_clip_slot_info(ctx: Context, track_index: int, clip_index: int) -> str:
    """
    Get the state of a clip slot.

    Parameters:
    - track_index: Index of the track (0-based)
    - clip_index: Index of the clip slot (0-based)

    Returns has_clip, has_stop_button, is_triggered, and basic clip info if a clip is present.
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_clip_slot_info", {
            "track_index": track_index,
            "clip_index": clip_index,
        })
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting clip slot info: {str(e)}")
        return f"Error getting clip slot info: {str(e)}"


@mcp.tool()
def set_time_signature(ctx: Context, numerator: int, denominator: int) -> str:
    """
    Set the song time signature.

    Parameters:
    - numerator: Top number (1–99, e.g. 4 for 4/4)
    - denominator: Bottom number — must be one of: 1, 2, 4, 8, 16, 32
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_time_signature", {
            "numerator": numerator,
            "denominator": denominator,
        })
        return f"Time signature set to {result['numerator']}/{result['denominator']}"
    except Exception as e:
        logger.error(f"Error setting time signature: {str(e)}")
        return f"Error setting time signature: {str(e)}"


@mcp.tool()
def get_track_routing(ctx: Context, track_index: int) -> str:
    """
    Get the current input and output routing for a track.

    Parameters:
    - track_index: Index of the track (0-based)

    Returns the current input_routing_type, input_routing_channel, output_routing_type,
    and output_routing_channel display names.
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_track_routing", {"track_index": track_index})
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting track routing: {str(e)}")
        return f"Error getting track routing: {str(e)}"


@mcp.tool()
def get_available_routings(ctx: Context, track_index: int) -> str:
    """
    Get all available input and output routing types for a track.

    Parameters:
    - track_index: Index of the track (0-based)

    Returns lists of available_input_routing_types and available_output_routing_types
    as display name strings. Use these names with set_input_routing / set_output_routing.
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_available_routings", {"track_index": track_index})
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting available routings: {str(e)}")
        return f"Error getting available routings: {str(e)}"


@mcp.tool()
def set_input_routing(ctx: Context, track_index: int, routing_type_name: str) -> str:
    """
    Set the input routing type for a track.

    Parameters:
    - track_index: Index of the track (0-based)
    - routing_type_name: Display name of the routing type (e.g. "No Input", "Ext. In").
      Use get_available_routings to see valid values for this track.
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_input_routing", {
            "track_index": track_index,
            "routing_type_name": routing_type_name,
        })
        return f"Input routing set to '{result['input_routing_type']}' on track {track_index}"
    except Exception as e:
        logger.error(f"Error setting input routing: {str(e)}")
        return f"Error setting input routing: {str(e)}"


@mcp.tool()
def set_output_routing(ctx: Context, track_index: int, routing_type_name: str) -> str:
    """
    Set the output routing type for a track.

    Parameters:
    - track_index: Index of the track (0-based)
    - routing_type_name: Display name of the routing type (e.g. "Master", "Sends Only").
      Use get_available_routings to see valid values for this track.
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_output_routing", {
            "track_index": track_index,
            "routing_type_name": routing_type_name,
        })
        return f"Output routing set to '{result['output_routing_type']}' on track {track_index}"
    except Exception as e:
        logger.error(f"Error setting output routing: {str(e)}")
        return f"Error setting output routing: {str(e)}"


@mcp.tool()
def get_audio_clip_info(ctx: Context, track_index: int, clip_index: int) -> str:
    """
    Get audio-specific properties of an audio clip.

    Parameters:
    - track_index: Index of the track (0-based)
    - clip_index: Index of the clip slot (0-based)

    Returns gain (0.0-1.0), gain_display_string (dB label), warping (bool),
    warp_mode (int) and warp_mode_name, pitch_coarse (semitones), pitch_fine (cents),
    and sample_name. Errors if the slot has no clip or the clip is not an audio clip.
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_audio_clip_info", {
            "track_index": track_index,
            "clip_index": clip_index,
        })
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting audio clip info: {str(e)}")
        return f"Error getting audio clip info: {str(e)}"


@mcp.tool()
def set_audio_clip_gain(ctx: Context, track_index: int, clip_index: int, gain: float) -> str:
    """
    Set the gain of an audio clip.

    Parameters:
    - track_index: Index of the track (0-based)
    - clip_index: Index of the clip slot (0-based)
    - gain: Linear gain value (0.0 = silent, 1.0 = 0 dB unity). Range: 0.0-1.0.

    Errors if the clip is not an audio clip.
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_audio_clip_gain", {
            "track_index": track_index,
            "clip_index": clip_index,
            "gain": gain,
        })
        return result
    except Exception as e:
        logger.error(f"Error setting audio clip gain: {str(e)}")
        return f"Error setting audio clip gain: {str(e)}"


@mcp.tool()
def set_audio_clip_pitch(
    ctx: Context,
    track_index: int,
    clip_index: int,
    pitch_coarse: int = None,
    pitch_fine: float = None,
) -> str:
    """
    Set the transposition of an audio clip.

    Parameters:
    - track_index: Index of the track (0-based)
    - clip_index: Index of the clip slot (0-based)
    - pitch_coarse: Semitone shift (-48 to 48). Omit to leave unchanged.
    - pitch_fine: Cent shift (-50.0 to 50.0). Omit to leave unchanged.

    Errors if the clip is not an audio clip.
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_audio_clip_pitch", {
            "track_index": track_index,
            "clip_index": clip_index,
            "pitch_coarse": pitch_coarse,
            "pitch_fine": pitch_fine,
        })
        return result
    except Exception as e:
        logger.error(f"Error setting audio clip pitch: {str(e)}")
        return f"Error setting audio clip pitch: {str(e)}"


@mcp.tool()
def set_audio_clip_warp(
    ctx: Context,
    track_index: int,
    clip_index: int,
    warping: bool = None,
    warp_mode: str = None,
) -> str:
    """
    Set warping on/off and/or the warp mode of an audio clip.

    Parameters:
    - track_index: Index of the track (0-based)
    - clip_index: Index of the clip slot (0-based)
    - warping: True to enable warping, False to disable. Omit to leave unchanged.
    - warp_mode: One of "Beats", "Tones", "Texture", "Re-Pitch", "Complex", "Complex Pro".
      Omit to leave unchanged. Warping must be enabled for warp_mode to have effect.

    Errors if the clip is not an audio clip.
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_audio_clip_warp", {
            "track_index": track_index,
            "clip_index": clip_index,
            "warping": warping,
            "warp_mode": warp_mode,
        })
        return result
    except Exception as e:
        logger.error(f"Error setting audio clip warp: {str(e)}")
        return f"Error setting audio clip warp: {str(e)}"


@mcp.tool()
def get_arrangement_clips(ctx: Context, track_index: int) -> str:
    """
    Get all clips in the arrangement view for a track.

    Parameters:
    - track_index: Index of the track (0-based)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_arrangement_clips", {"track_index": track_index})
        clips = result.get("clips", [])
        if not clips:
            return f"Track {track_index} has no arrangement clips."
        lines = [f"Track {track_index} has {len(clips)} arrangement clip(s):"]
        for c in clips:
            kind = "audio" if c.get("is_audio_clip") else "MIDI"
            lines.append(f"  '{c['name']}' [{kind}] start={c['start_time']:.3f} end={c['end_time']:.3f} len={c['length']:.3f}")
        return "\n".join(lines)
    except Exception as e:
        logger.error(f"Error getting arrangement clips: {str(e)}")
        return f"Error getting arrangement clips: {str(e)}"


@mcp.tool()
def get_cue_points(ctx: Context) -> str:
    """
    Get all cue points (locators) in the arrangement.
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_cue_points", {})
        cue_points = result.get("cue_points", [])
        if not cue_points:
            return "No cue points in arrangement."
        lines = [f"{len(cue_points)} cue point(s):"]
        for cp in cue_points:
            lines.append(f"  '{cp['name']}' at {cp['time']:.3f}")
        return "\n".join(lines)
    except Exception as e:
        logger.error(f"Error getting cue points: {str(e)}")
        return f"Error getting cue points: {str(e)}"


@mcp.tool()
def set_or_delete_cue(ctx: Context) -> str:
    """
    Create or delete a cue point at the current song time.
    If no cue exists at the current position, one is created. If one exists, it is deleted.
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_or_delete_cue", {})
        action = result.get("action", "unknown")
        cue_points = result.get("cue_points", [])
        return f"Cue point {action}. Total cue points: {len(cue_points)}"
    except Exception as e:
        logger.error(f"Error setting/deleting cue: {str(e)}")
        return f"Error setting/deleting cue: {str(e)}"


@mcp.tool()
def get_arrangement_loop(ctx: Context) -> str:
    """
    Get the current arrangement loop and punch state.
    Returns loop_start, loop_length, loop on/off, punch_in, punch_out.
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_arrangement_loop", {})
        return (
            f"Loop: {'on' if result['loop'] else 'off'}, "
            f"start={result['loop_start']:.3f}, length={result['loop_length']:.3f} | "
            f"Punch in: {'on' if result['punch_in'] else 'off'}, "
            f"Punch out: {'on' if result['punch_out'] else 'off'}"
        )
    except Exception as e:
        logger.error(f"Error getting arrangement loop: {str(e)}")
        return f"Error getting arrangement loop: {str(e)}"


@mcp.tool()
def set_arrangement_loop(ctx: Context,
                         loop_start: float = None,
                         loop_length: float = None,
                         loop_on: bool = None) -> str:
    """
    Set the arrangement loop region and/or enable/disable loop.

    Parameters:
    - loop_start: Loop start in beats (optional)
    - loop_length: Loop length in beats (optional)
    - loop_on: Enable or disable looping (optional)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_arrangement_loop", {
            "loop_start": loop_start,
            "loop_length": loop_length,
            "loop_on": loop_on,
        })
        return (
            f"Loop: {'on' if result['loop'] else 'off'}, "
            f"start={result['loop_start']:.3f}, length={result['loop_length']:.3f}"
        )
    except Exception as e:
        logger.error(f"Error setting arrangement loop: {str(e)}")
        return f"Error setting arrangement loop: {str(e)}"


@mcp.tool()
def set_punch_points(ctx: Context, punch_in: bool = None, punch_out: bool = None) -> str:
    """
    Enable or disable punch in/out recording.

    Parameters:
    - punch_in: Enable punch-in (optional)
    - punch_out: Enable punch-out (optional)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_punch_points", {
            "punch_in": punch_in,
            "punch_out": punch_out,
        })
        return (
            f"Punch in: {'on' if result['punch_in'] else 'off'}, "
            f"Punch out: {'on' if result['punch_out'] else 'off'}"
        )
    except Exception as e:
        logger.error(f"Error setting punch points: {str(e)}")
        return f"Error setting punch points: {str(e)}"


@mcp.tool()
def jump_to_cue(ctx: Context, direction: str = "next") -> str:
    """
    Jump to the next or previous cue point in the arrangement.

    Parameters:
    - direction: "next" or "prev" (default: "next")
    """
    try:
        ableton = get_ableton_connection()
        ableton.send_command("jump_to_cue", {"direction": direction})
        # current_song_time read-back is unreliable immediately after jump_to_next/prev_cue()
        # (Live applies the jump asynchronously). Use get_current_song_time to verify position.
        return f"Jumped to {direction} cue."
    except Exception as e:
        logger.error(f"Error jumping to cue: {str(e)}")
        return f"Error jumping to cue: {str(e)}"


@mcp.tool()
def get_clip_follow_action(ctx: Context, track_index: int, clip_index: int) -> str:
    """
    Get follow action settings for a session clip.

    Parameters:
    - track_index: Track index (0-based)
    - clip_index: Clip slot index (0-based)

    Returns follow_actions_enabled, follow_action_a/b (0-8), follow_action_chance_a/b, follow_action_time (bars).
    Follow action values: 0=Stop, 1=Play Again, 2=Previous, 3=Next, 4=First, 5=Last, 6=Any, 7=Other, 8=Jump
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_clip_follow_action", {
            "track_index": track_index,
            "clip_index": clip_index,
        })
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting clip follow action: {str(e)}")
        return f"Error getting clip follow action: {str(e)}"


@mcp.tool()
def set_clip_follow_action(
    ctx: Context,
    track_index: int,
    clip_index: int,
    follow_action_a: Union[int, str, None] = None,
    follow_action_b: Union[int, str, None] = None,
    follow_action_chance_a: float = None,
    follow_action_time: float = None,
    follow_actions_enabled: bool = None,
) -> str:
    """
    Set follow action settings for a session clip. All parameters are optional — omit to leave unchanged.

    Parameters:
    - track_index: Track index (0-based)
    - clip_index: Clip slot index (0-based)
    - follow_action_a: Action A — int 0-8 or name string (Stop, Play Again, Previous, Next, First, Last, Any, Other, Jump)
    - follow_action_b: Action B — int 0-8 or name string
    - follow_action_chance_a: Probability of action A (0.0-1.0). Chance B is set to 1 - chance_a automatically.
    - follow_action_time: Time in bars before follow action fires (>= 0)
    - follow_actions_enabled: Enable or disable follow actions for this clip
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_clip_follow_action", {
            "track_index": track_index,
            "clip_index": clip_index,
            "follow_action_a": follow_action_a,
            "follow_action_b": follow_action_b,
            "follow_action_chance_a": follow_action_chance_a,
            "follow_action_time": follow_action_time,
            "follow_actions_enabled": follow_actions_enabled,
        })
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error setting clip follow action: {str(e)}")
        return f"Error setting clip follow action: {str(e)}"


# Main execution
def main():
    """Run the MCP server"""
    mcp.run()

if __name__ == "__main__":
    main()