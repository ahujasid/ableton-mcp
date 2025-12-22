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
            "create_midi_track", "create_audio_track", "delete_track", "set_track_name",
            "create_clip", "add_notes_to_clip", "set_clip_name",
            "set_tempo", "fire_clip", "stop_clip", "set_device_parameter",
            "start_playback", "stop_playback", "load_instrument_or_effect",
            # Arrangement view
            "create_clip_in_arrangement", "add_notes_to_arrangement_clip",
            "duplicate_clip_to_arrangement", "delete_arrangement_clip",
            # Scene operations
            "create_scene", "set_scene_name", "fire_scene",
            # Mixer operations
            "set_track_volume", "set_track_pan", "set_track_mute",
            "set_track_solo", "set_track_arm", "set_send_level",
            # Clip operations
            "duplicate_clip", "set_clip_loop", "set_clip_start_end", "clear_clip_notes"
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
    description="Ableton Live integration through the Model Context Protocol",
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
def get_all_track_info(ctx: Context) -> str:
    """
    Get information about all tracks in the Ableton session.
    Returns a list of all tracks with their properties, clip slots, and devices.
    More efficient than calling get_track_info for each track individually.
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_all_track_info", {})
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting all track info from Ableton: {str(e)}")
        return f"Error getting all track info: {str(e)}"

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


# ============================================
# ARRANGEMENT VIEW OPERATIONS
# ============================================

@mcp.tool()
def get_arrangement_clips(ctx: Context, track_index: int) -> str:
    """
    Get all clips in the arrangement view for a track.

    Parameters:
    - track_index: The index of the track to get arrangement clips from
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_arrangement_clips", {"track_index": track_index})
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting arrangement clips: {str(e)}")
        return f"Error getting arrangement clips: {str(e)}"


@mcp.tool()
def create_clip_in_arrangement(ctx: Context, track_index: int, start_time: float, length: float = 4.0) -> str:
    """
    Create a MIDI clip in the arrangement view.

    Parameters:
    - track_index: The index of the MIDI track to create the clip in
    - start_time: The start time in beats where the clip should be created
    - length: The length of the clip in beats (default: 4.0)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("create_clip_in_arrangement", {
            "track_index": track_index,
            "start_time": start_time,
            "length": length
        })
        return f"Created arrangement clip at beat {start_time} with length {length} on track {track_index}"
    except Exception as e:
        logger.error(f"Error creating arrangement clip: {str(e)}")
        return f"Error creating arrangement clip: {str(e)}"


@mcp.tool()
def add_notes_to_arrangement_clip(
    ctx: Context,
    track_index: int,
    clip_index: int,
    notes: List[Dict[str, Union[int, float, bool]]]
) -> str:
    """
    Add MIDI notes to an arrangement clip.

    Parameters:
    - track_index: The index of the track containing the clip
    - clip_index: The index of the arrangement clip
    - notes: List of note dictionaries, each with pitch, start_time, duration, velocity, and mute
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("add_notes_to_arrangement_clip", {
            "track_index": track_index,
            "clip_index": clip_index,
            "notes": notes
        })
        return f"Added {len(notes)} notes to arrangement clip {clip_index} on track {track_index}"
    except Exception as e:
        logger.error(f"Error adding notes to arrangement clip: {str(e)}")
        return f"Error adding notes to arrangement clip: {str(e)}"


@mcp.tool()
def duplicate_clip_to_arrangement(ctx: Context, track_index: int, clip_slot_index: int, destination_time: float) -> str:
    """
    Duplicate a session view clip to the arrangement view.

    Parameters:
    - track_index: The index of the track containing the clip
    - clip_slot_index: The index of the session clip slot to duplicate from
    - destination_time: The time in beats where the clip should be placed in the arrangement
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("duplicate_clip_to_arrangement", {
            "track_index": track_index,
            "clip_slot_index": clip_slot_index,
            "destination_time": destination_time
        })
        return f"Duplicated clip from slot {clip_slot_index} to arrangement at beat {destination_time}"
    except Exception as e:
        logger.error(f"Error duplicating clip to arrangement: {str(e)}")
        return f"Error duplicating clip to arrangement: {str(e)}"


@mcp.tool()
def delete_arrangement_clip(ctx: Context, track_index: int, clip_index: int) -> str:
    """
    Delete a clip from the arrangement view.

    Parameters:
    - track_index: The index of the track containing the clip
    - clip_index: The index of the arrangement clip to delete
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("delete_arrangement_clip", {
            "track_index": track_index,
            "clip_index": clip_index
        })
        return f"Deleted arrangement clip {clip_index} from track {track_index}"
    except Exception as e:
        logger.error(f"Error deleting arrangement clip: {str(e)}")
        return f"Error deleting arrangement clip: {str(e)}"


@mcp.tool()
def split_arrangement_clip(ctx: Context, track_index: int, clip_index: int, split_time: float) -> str:
    """
    Split an arrangement clip at a specific time, creating two clips.
    Useful for sectioning audio for macro alignment before micro-warping.

    Parameters:
    - track_index: The index of the track containing the clip
    - clip_index: The index of the arrangement clip to split
    - split_time: The beat position where to split the clip
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("split_arrangement_clip", {
            "track_index": track_index,
            "clip_index": clip_index,
            "split_time": split_time
        })
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error splitting arrangement clip: {str(e)}")
        return f"Error splitting arrangement clip: {str(e)}"


@mcp.tool()
def move_arrangement_clip(ctx: Context, track_index: int, clip_index: int, new_start_time: float) -> str:
    """
    Move an arrangement clip to a new start time.
    Useful for aligning sections to a target groove.

    Parameters:
    - track_index: The index of the track containing the clip
    - clip_index: The index of the arrangement clip to move
    - new_start_time: The new beat position for the clip start
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("move_arrangement_clip", {
            "track_index": track_index,
            "clip_index": clip_index,
            "new_start_time": new_start_time
        })
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error moving arrangement clip: {str(e)}")
        return f"Error moving arrangement clip: {str(e)}"


@mcp.tool()
def set_arrangement_clip_file_position(
    ctx: Context,
    track_index: int,
    clip_index: int,
    start_marker: float = None,
    end_marker: float = None,
    loop_start: float = None,
    loop_end: float = None
) -> str:
    """
    Set the file position markers for an arrangement clip.
    Controls which part of the source audio file is played.

    For audio clips:
    - loop_start/loop_end control which beats in the audio file are played
    - Changing loop_start effectively shifts where in the audio the clip starts

    Parameters:
    - track_index: The index of the track containing the clip
    - clip_index: The index of the arrangement clip
    - start_marker: Start marker position (optional)
    - end_marker: End marker position (optional)
    - loop_start: Which beat in the audio file to start from (optional)
    - loop_end: Which beat in the audio file to end at (optional)
    """
    try:
        ableton = get_ableton_connection()
        params = {
            "track_index": track_index,
            "clip_index": clip_index
        }
        if start_marker is not None:
            params["start_marker"] = start_marker
        if end_marker is not None:
            params["end_marker"] = end_marker
        if loop_start is not None:
            params["loop_start"] = loop_start
        if loop_end is not None:
            params["loop_end"] = loop_end

        result = ableton.send_command("set_arrangement_clip_file_position", params)
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error setting clip file position: {str(e)}")
        return f"Error setting clip file position: {str(e)}"


@mcp.tool()
def duplicate_arrangement_clip_to_time(ctx: Context, track_index: int, clip_index: int, destination_time: float) -> str:
    """
    Duplicate an arrangement clip to a new time position.
    Creates a copy of the clip at the specified beat position.

    Parameters:
    - track_index: The index of the track containing the clip
    - clip_index: The index of the arrangement clip to duplicate
    - destination_time: The beat position where to place the copy
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("duplicate_arrangement_clip_to_time", {
            "track_index": track_index,
            "clip_index": clip_index,
            "destination_time": destination_time
        })
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error duplicating arrangement clip: {str(e)}")
        return f"Error duplicating arrangement clip: {str(e)}"


# ============================================
# DEVICE PARAMETER OPERATIONS
# ============================================

@mcp.tool()
def get_track_devices(ctx: Context, track_index: int) -> str:
    """
    Get all devices on a track.

    Parameters:
    - track_index: The index of the track to get devices from
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_track_devices", {"track_index": track_index})
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting track devices: {str(e)}")
        return f"Error getting track devices: {str(e)}"


@mcp.tool()
def get_device_parameters(ctx: Context, track_index: int, device_index: int) -> str:
    """
    Get all parameters of a device on a track.

    Parameters:
    - track_index: The index of the track containing the device
    - device_index: The index of the device on the track
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
    - track_index: The index of the track containing the device
    - device_index: The index of the device on the track
    - parameter_index: The index of the parameter to set
    - value: The new value for the parameter (will be clamped to valid range)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_device_parameter", {
            "track_index": track_index,
            "device_index": device_index,
            "parameter_index": parameter_index,
            "value": value
        })
        return f"Set {result.get('parameter_name', 'parameter')} to {result.get('new_value', value)} on {result.get('device_name', 'device')}"
    except Exception as e:
        logger.error(f"Error setting device parameter: {str(e)}")
        return f"Error setting device parameter: {str(e)}"


# ============================================
# SCENE OPERATIONS
# ============================================

@mcp.tool()
def get_scenes(ctx: Context) -> str:
    """Get all scenes in the session."""
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_scenes")
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting scenes: {str(e)}")
        return f"Error getting scenes: {str(e)}"


@mcp.tool()
def create_scene(ctx: Context, index: int = -1) -> str:
    """
    Create a new scene.

    Parameters:
    - index: The index where to insert the scene (-1 = end of list)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("create_scene", {"index": index})
        return f"Created scene '{result.get('name', 'Scene')}' at index {result.get('index', index)}"
    except Exception as e:
        logger.error(f"Error creating scene: {str(e)}")
        return f"Error creating scene: {str(e)}"


@mcp.tool()
def set_scene_name(ctx: Context, scene_index: int, name: str) -> str:
    """
    Set the name of a scene.

    Parameters:
    - scene_index: The index of the scene to rename
    - name: The new name for the scene
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_scene_name", {
            "scene_index": scene_index,
            "name": name
        })
        return f"Renamed scene {scene_index} to '{name}'"
    except Exception as e:
        logger.error(f"Error setting scene name: {str(e)}")
        return f"Error setting scene name: {str(e)}"


@mcp.tool()
def fire_scene(ctx: Context, scene_index: int) -> str:
    """
    Fire (trigger) a scene to play all clips in that row.

    Parameters:
    - scene_index: The index of the scene to fire
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("fire_scene", {"scene_index": scene_index})
        return f"Fired scene {scene_index} ('{result.get('name', 'Scene')}')"
    except Exception as e:
        logger.error(f"Error firing scene: {str(e)}")
        return f"Error firing scene: {str(e)}"


# ============================================
# MIXER OPERATIONS
# ============================================

@mcp.tool()
def set_track_volume(ctx: Context, track_index: int, value: float) -> str:
    """
    Set the volume of a track.

    Parameters:
    - track_index: The index of the track
    - value: Volume level from 0.0 (silence) to 1.0 (0dB, full volume)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_track_volume", {
            "track_index": track_index,
            "value": value
        })
        return f"Set track {track_index} volume to {result.get('volume', value)}"
    except Exception as e:
        logger.error(f"Error setting track volume: {str(e)}")
        return f"Error setting track volume: {str(e)}"


@mcp.tool()
def set_track_pan(ctx: Context, track_index: int, value: float) -> str:
    """
    Set the pan of a track.

    Parameters:
    - track_index: The index of the track
    - value: Pan value from -1.0 (full left) to 1.0 (full right), 0.0 is center
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_track_pan", {
            "track_index": track_index,
            "value": value
        })
        return f"Set track {track_index} pan to {result.get('pan', value)}"
    except Exception as e:
        logger.error(f"Error setting track pan: {str(e)}")
        return f"Error setting track pan: {str(e)}"


@mcp.tool()
def set_track_mute(ctx: Context, track_index: int, muted: bool) -> str:
    """
    Set the mute state of a track.

    Parameters:
    - track_index: The index of the track
    - muted: True to mute, False to unmute
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_track_mute", {
            "track_index": track_index,
            "muted": muted
        })
        state = "muted" if result.get('muted', muted) else "unmuted"
        return f"Track {track_index} is now {state}"
    except Exception as e:
        logger.error(f"Error setting track mute: {str(e)}")
        return f"Error setting track mute: {str(e)}"


@mcp.tool()
def set_track_solo(ctx: Context, track_index: int, soloed: bool) -> str:
    """
    Set the solo state of a track.

    Parameters:
    - track_index: The index of the track
    - soloed: True to solo, False to unsolo
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_track_solo", {
            "track_index": track_index,
            "soloed": soloed
        })
        state = "soloed" if result.get('soloed', soloed) else "unsoloed"
        return f"Track {track_index} is now {state}"
    except Exception as e:
        logger.error(f"Error setting track solo: {str(e)}")
        return f"Error setting track solo: {str(e)}"


@mcp.tool()
def set_track_arm(ctx: Context, track_index: int, armed: bool) -> str:
    """
    Set the arm state of a track for recording.

    Parameters:
    - track_index: The index of the track
    - armed: True to arm for recording, False to disarm
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_track_arm", {
            "track_index": track_index,
            "armed": armed
        })
        state = "armed" if result.get('armed', armed) else "disarmed"
        return f"Track {track_index} is now {state}"
    except Exception as e:
        logger.error(f"Error setting track arm: {str(e)}")
        return f"Error setting track arm: {str(e)}"


@mcp.tool()
def set_send_level(ctx: Context, track_index: int, send_index: int, value: float) -> str:
    """
    Set a send level for a track.

    Parameters:
    - track_index: The index of the track
    - send_index: The index of the send (corresponds to return track order)
    - value: Send level from 0.0 to 1.0
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_send_level", {
            "track_index": track_index,
            "send_index": send_index,
            "value": value
        })
        return f"Set track {track_index} send {send_index} to {result.get('value', value)}"
    except Exception as e:
        logger.error(f"Error setting send level: {str(e)}")
        return f"Error setting send level: {str(e)}"


# ============================================
# CLIP OPERATIONS
# ============================================

@mcp.tool()
def get_clip_notes(ctx: Context, track_index: int, clip_index: int) -> str:
    """
    Get all MIDI notes from a clip.

    Parameters:
    - track_index: The index of the track containing the clip
    - clip_index: The index of the clip slot containing the clip
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
def get_arrangement_clip_notes(ctx: Context, track_index: int, clip_index: int) -> str:
    """
    Get all MIDI notes from an arrangement clip.

    Parameters:
    - track_index: The index of the track containing the clip
    - clip_index: The index of the arrangement clip
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_arrangement_clip_notes", {
            "track_index": track_index,
            "clip_index": clip_index
        })
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting arrangement clip notes: {str(e)}")
        return f"Error getting arrangement clip notes: {str(e)}"


@mcp.tool()
def duplicate_clip(ctx: Context, track_index: int, source_slot: int, dest_slot: int) -> str:
    """
    Duplicate a clip to another slot in the same track.

    Parameters:
    - track_index: The index of the track containing the clip
    - source_slot: The index of the source clip slot
    - dest_slot: The index of the destination clip slot (must be empty)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("duplicate_clip", {
            "track_index": track_index,
            "source_slot": source_slot,
            "dest_slot": dest_slot
        })
        return f"Duplicated clip from slot {source_slot} to slot {dest_slot}"
    except Exception as e:
        logger.error(f"Error duplicating clip: {str(e)}")
        return f"Error duplicating clip: {str(e)}"


@mcp.tool()
def set_clip_loop(ctx: Context, track_index: int, clip_index: int, loop_start: float, loop_end: float) -> str:
    """
    Set the loop points of a clip.

    Parameters:
    - track_index: The index of the track containing the clip
    - clip_index: The index of the clip slot containing the clip
    - loop_start: The loop start point in beats
    - loop_end: The loop end point in beats
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_clip_loop", {
            "track_index": track_index,
            "clip_index": clip_index,
            "loop_start": loop_start,
            "loop_end": loop_end
        })
        return f"Set loop from {loop_start} to {loop_end} beats on clip '{result.get('clip_name', 'clip')}'"
    except Exception as e:
        logger.error(f"Error setting clip loop: {str(e)}")
        return f"Error setting clip loop: {str(e)}"


@mcp.tool()
def set_clip_start_end(ctx: Context, track_index: int, clip_index: int, start: float, end: float) -> str:
    """
    Set the start and end markers of a clip.

    Parameters:
    - track_index: The index of the track containing the clip
    - clip_index: The index of the clip slot containing the clip
    - start: The start marker position in beats
    - end: The end marker position in beats
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_clip_start_end", {
            "track_index": track_index,
            "clip_index": clip_index,
            "start": start,
            "end": end
        })
        return f"Set markers from {start} to {end} beats on clip '{result.get('clip_name', 'clip')}'"
    except Exception as e:
        logger.error(f"Error setting clip start/end: {str(e)}")
        return f"Error setting clip start/end: {str(e)}"


@mcp.tool()
def clear_clip_notes(ctx: Context, track_index: int, clip_index: int) -> str:
    """
    Clear all MIDI notes from a clip.

    Parameters:
    - track_index: The index of the track containing the clip
    - clip_index: The index of the clip slot containing the clip
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("clear_clip_notes", {
            "track_index": track_index,
            "clip_index": clip_index
        })
        return f"Cleared all notes from clip '{result.get('clip_name', 'clip')}'"
    except Exception as e:
        logger.error(f"Error clearing clip notes: {str(e)}")
        return f"Error clearing clip notes: {str(e)}"


# ============================================
# AUDIO TRACK SUPPORT
# ============================================

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
        return f"Created new audio track: {result.get('name', 'Audio Track')} at index {result.get('index', index)}"
    except Exception as e:
        logger.error(f"Error creating audio track: {str(e)}")
        return f"Error creating audio track: {str(e)}"


@mcp.tool()
def delete_track(ctx: Context, track_index: int, track_name: str) -> str:
    """
    Delete a track from the Ableton session.

    For safety, both the track index and name must be provided and must match.
    This prevents accidental deletion if track indices have shifted.

    Parameters:
    - track_index: The index of the track to delete
    - track_name: The expected name of the track (must match for deletion to proceed)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("delete_track", {
            "track_index": track_index,
            "track_name": track_name
        })
        return f"Deleted track '{result.get('deleted_track', track_name)}' at index {track_index}"
    except Exception as e:
        logger.error(f"Error deleting track: {str(e)}")
        return f"Error deleting track: {str(e)}"


@mcp.tool()
def get_cue_points(ctx: Context) -> str:
    """
    Get all cue points (locators) in the arrangement.

    Returns a list of all locators with their time positions and names.
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_cue_points", {})
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting cue points: {str(e)}")
        return f"Error getting cue points: {str(e)}"


@mcp.tool()
def create_cue_point(ctx: Context, time: float) -> str:
    """
    Create a cue point (locator) at the specified time in the arrangement.

    Parameters:
    - time: The time position in beats where the locator should be created

    Note: Locator names cannot be set via the API in Live 11 - they auto-number.
    Rename manually in Arrangement View by double-clicking the locator.
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("create_cue_point", {
            "time": time
        })
        return f"Created locator at beat {time}"
    except Exception as e:
        logger.error(f"Error creating cue point: {str(e)}")
        return f"Error creating cue point: {str(e)}"


@mcp.tool()
def delete_cue_point(ctx: Context, time: float) -> str:
    """
    Delete a cue point (locator) at the specified time.

    Parameters:
    - time: The time position in beats of the locator to delete
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("delete_cue_point", {
            "time": time
        })
        return f"Deleted locator at beat {time}"
    except Exception as e:
        logger.error(f"Error deleting cue point: {str(e)}")
        return f"Error deleting cue point: {str(e)}"


# ============================================
# AUDIO ANALYSIS OPERATIONS
# ============================================

@mcp.tool()
def analyze_audio_technical(ctx: Context, file_path: str) -> str:
    """
    Perform technical analysis of an audio file.

    Returns BPM, time signature, beat positions, and chord progression with timestamps.
    Uses ChordMini API (free, rate limited to 2 requests/minute per endpoint).

    Parameters:
    - file_path: Absolute path to the audio file (WAV, MP3, AIFF, AAC, OGG, FLAC, M4A)
    """
    try:
        from MCP_Server.audio_analysis import analyze_audio_technical as do_analysis
        result = do_analysis(file_path)
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error analyzing audio: {str(e)}")
        return f"Error analyzing audio: {str(e)}"


@mcp.tool()
def analyze_audio_describe(ctx: Context, file_path: str, prompt: str) -> str:
    """
    Ask questions about an audio file using AI (Google Gemini).

    Use this to describe, understand, or ask questions about audio content.
    Examples: "What instruments are playing?", "Describe the mood of this track",
    "What genre would you classify this as?", "Are there any issues with the mix?"

    Parameters:
    - file_path: Absolute path to the audio file (WAV, MP3, AIFF, AAC, OGG, FLAC, M4A)
    - prompt: Your question or instruction about the audio

    Note: Requires GOOGLE_API_KEY environment variable to be set.
    """
    try:
        from MCP_Server.audio_analysis import analyze_audio_describe as do_describe
        result = do_describe(file_path, prompt)
        return result
    except ValueError as e:
        # Missing API key or invalid file
        logger.error(f"Audio analysis configuration error: {str(e)}")
        return f"Configuration error: {str(e)}"
    except ImportError as e:
        logger.error(f"Missing dependency: {str(e)}")
        return f"Missing dependency: {str(e)}. Run: pip install google-generativeai"
    except Exception as e:
        logger.error(f"Error analyzing audio: {str(e)}")
        return f"Error analyzing audio: {str(e)}"


@mcp.tool()
def analyze_song_structure(ctx: Context, file_path: str, include_beats: bool = False, target_bpm: float = None) -> str:
    """
    Analyze song structure to identify sections (intro, verse, chorus, bridge, outro, etc.).

    Uses Replicate's All-In-One Music Structure Analyzer which provides:
    - BPM detection
    - Beat and downbeat tracking
    - Functional segment boundaries with labels

    Parameters:
    - file_path: Absolute path to the audio file (WAV, MP3, AIFF, AAC, OGG, FLAC, M4A)
    - include_beats: Include full beat/downbeat arrays (default False to reduce output size)
    - target_bpm: Lock BPM detection to this value (±1 BPM). Use when tempo is misdetected
                  (e.g., 140 BPM track detected as 81 BPM due to half-time feel).

    Note: Requires REPLICATE_API_TOKEN environment variable. Costs ~$0.10 per track.

    Returns JSON with:
    - bpm: tempo in beats per minute
    - segments: list of {start, end, label} where label is intro/verse/chorus/bridge/outro/etc
    - beats: list of beat timestamps in seconds (if include_beats=True)
    - downbeats: list of downbeat timestamps in seconds (if include_beats=True)
    """
    try:
        from MCP_Server.audio_analysis import analyze_song_structure as do_analysis
        result = do_analysis(file_path, include_beats, target_bpm=target_bpm)
        return json.dumps(result, indent=2)
    except ValueError as e:
        logger.error(f"Song structure analysis configuration error: {str(e)}")
        return f"Configuration error: {str(e)}"
    except ImportError as e:
        logger.error(f"Missing dependency: {str(e)}")
        return f"Missing dependency: {str(e)}. Run: pip install replicate"
    except Exception as e:
        logger.error(f"Error analyzing song structure: {str(e)}")
        return f"Error analyzing song structure: {str(e)}"


@mcp.tool()
def vocal_to_midi(ctx: Context, audio_path: str, output_midi_path: str, bpm: float = 120.0) -> str:
    """
    Convert vocal audio to MIDI based on phoneme categorization.

    Analyzes vocal onsets and categorizes them by phoneme type:
    - Plosives (P/B/T/K) → MIDI note 60 (C4) - Percussive hits
    - Fricatives (S/Sh/F) → MIDI note 62 (D4) - High hat sounds
    - Vowels/Nasals (A/E/M/N) → MIDI note 64 (E4) - Tonal body

    Parameters:
    - audio_path: Path to the vocal audio file
    - output_midi_path: Path to save the output MIDI file
    - bpm: Tempo in BPM (default: 120)

    Returns summary with onset count and phoneme categories.
    """
    try:
        from MCP_Server.audio_analysis import vocal_to_midi as do_vocal_to_midi
        result = do_vocal_to_midi(audio_path, output_midi_path, bpm)
        return (
            f"Converted vocals to MIDI: {result['output_path']}\n"
            f"Duration: {result['duration']:.1f}s, BPM: {result['bpm']}\n"
            f"Onsets: {result['onset_count']} total\n"
            f"  - Plosives (C4): {result['categories']['plosive']}\n"
            f"  - Fricatives (D4): {result['categories']['fricative']}\n"
            f"  - Vowels (E4): {result['categories']['vowel']}"
        )
    except Exception as e:
        logger.error(f"Error converting vocal to MIDI: {str(e)}")
        return f"Error converting vocal to MIDI: {str(e)}"


# ============================================
# AUDIO CAPTURE OPERATIONS
# ============================================

CAPTURE_FILE_PATH = "/tmp/ableton_capture.wav"


def _find_audio_capture_device(ableton) -> tuple:
    """Find the AudioCapture M4L device. Returns (track_index, device_index) or (None, None).
    Checks master track first (track_index=-1), then regular tracks."""

    # Check master track first (track_index=-1)
    try:
        devices_result = ableton.send_command("get_track_devices", {"track_index": -1})
        devices = devices_result.get("devices", [])
        for j, device in enumerate(devices):
            if "AudioCapture" in device.get("name", ""):
                return (-1, j)
    except Exception as e:
        logger.warning(f"Could not check master track devices: {e}")

    # Check regular tracks
    session = ableton.send_command("get_session_info")
    tracks = session.get("tracks", [])

    for i, track in enumerate(tracks):
        devices_result = ableton.send_command("get_track_devices", {"track_index": i})
        devices = devices_result.get("devices", [])
        for j, device in enumerate(devices):
            if "AudioCapture" in device.get("name", ""):
                return (i, j)
    return (None, None)


@mcp.tool()
def audio_capture(ctx: Context, start_time: float, duration: float) -> str:
    """
    Capture audio from Ableton starting at a specific position.

    Seeks to start position, records audio via the AudioCapture M4L device,
    stops after the duration, and restores the original playhead position.

    The AudioCapture device must be loaded on a track (usually Master).

    Parameters:
    - start_time: Start position in beats (e.g., 0 for beginning, 32 for bar 9)
    - duration: Recording duration in seconds

    Returns the path to the captured WAV file, which can be used with
    analyze_audio_technical or analyze_audio_describe.
    """
    import time
    import os

    try:
        ableton = get_ableton_connection()

        # Find the AudioCapture device
        track_idx, device_idx = _find_audio_capture_device(ableton)
        if track_idx is None:
            return "Error: AudioCapture device not found. Please load it on a track (e.g., Master) first."

        # Save original playhead position
        original_position = ableton.send_command("get_playhead_position").get("position", 0)

        # Seek to start position
        ableton.send_command("set_playhead_position", {"position": start_time})

        # Start recording
        ableton.send_command("set_device_parameter", {
            "track_index": track_idx,
            "device_index": device_idx,
            "parameter_index": 1,  # Record parameter
            "value": 1.0
        })

        # Start playback
        ableton.send_command("start_playback")

        # Wait for duration
        time.sleep(duration)

        # Stop playback
        ableton.send_command("stop_playback")

        # Stop recording (triggers auto-save via Max patch)
        ableton.send_command("set_device_parameter", {
            "track_index": track_idx,
            "device_index": device_idx,
            "parameter_index": 1,
            "value": 0.0
        })

        # Small delay for file to be written
        time.sleep(0.5)

        # Restore original playhead position
        ableton.send_command("set_playhead_position", {"position": original_position})

        # Verify file exists
        if os.path.exists(CAPTURE_FILE_PATH):
            size = os.path.getsize(CAPTURE_FILE_PATH)
            return f"Captured {duration}s of audio from beat {start_time} to {CAPTURE_FILE_PATH} ({size} bytes)"
        else:
            return f"Recording completed but file not found at {CAPTURE_FILE_PATH}"

    except Exception as e:
        logger.error(f"Error during audio capture: {str(e)}")
        return f"Error during audio capture: {str(e)}"


# ============================================
# GROOVE ALIGNMENT TOOLS
# ============================================

@mcp.tool()
def groove_analyze(
    ctx: Context,
    source_track_index: int,
    source_clip_index: int,
    target_track_index: int,
    target_clip_index: int,
    source_offset: float = 0.0
) -> str:
    """
    Analyze alignment between source MIDI (e.g., vocal rhythm) and target MIDI (e.g., drums).

    Compares timing of notes in both clips and calculates how far off each note is.
    Use this to understand how well two patterns align before quantizing.

    Parameters:
    - source_track_index: Track index of the source MIDI clip (e.g., vocal rhythm)
    - source_clip_index: Arrangement clip index for source
    - target_track_index: Track index of the target MIDI clip (e.g., drums)
    - target_clip_index: Arrangement clip index for target
    - source_offset: Beat offset to add to source times (e.g., if source clip starts at beat 104)

    Returns analysis with per-note offsets and statistics.
    """
    try:
        from MCP_Server.audio_analysis import groove_align_analyze

        ableton = get_ableton_connection()

        # Get session tempo
        session = ableton.send_command("get_session_info")
        bpm = session.get("result", {}).get("tempo", 120.0)

        # Get source notes
        source_result = ableton.send_command("get_arrangement_clip_notes", {
            "track_index": source_track_index,
            "clip_index": source_clip_index
        })
        source_notes = source_result.get("result", {}).get("notes", [])

        # Get target notes
        target_result = ableton.send_command("get_arrangement_clip_notes", {
            "track_index": target_track_index,
            "clip_index": target_clip_index
        })
        target_notes = target_result.get("result", {}).get("notes", [])

        if not source_notes:
            return "Error: No notes found in source clip"
        if not target_notes:
            return "Error: No notes found in target clip"

        # Analyze alignment
        analysis = groove_align_analyze(
            source_notes, target_notes, source_offset, bpm, match_by_pitch=True
        )

        stats = analysis['statistics']
        summary = f"""Groove Alignment Analysis:
- Source notes: {len(source_notes)}
- Target notes: {len(target_notes)}
- Matched alignments: {stats['total_notes']}

Timing Statistics:
- Mean offset: {stats['mean_offset_ms']:.1f}ms ({stats['mean_offset_beats']:.3f} beats)
- Std deviation: {stats['std_offset_ms']:.1f}ms
- Range: {stats['min_offset_ms']:.1f}ms to {stats['max_offset_ms']:.1f}ms

BPM: {bpm}
Source offset: {source_offset} beats"""

        return summary

    except Exception as e:
        logger.error(f"Error analyzing groove alignment: {str(e)}")
        return f"Error analyzing groove alignment: {str(e)}"


@mcp.tool()
def groove_quantize_to_track(
    ctx: Context,
    source_track_index: int,
    source_clip_index: int,
    target_track_index: int,
    target_clip_index: int,
    source_offset: float = 0.0,
    output_track_name: str = "Quantized"
) -> str:
    """
    Create a new MIDI track with source notes quantized to match target groove.

    Takes a source MIDI clip (e.g., vocal rhythm) and snaps each note to the
    nearest note in the target clip (e.g., drums). Creates a new track with
    the quantized MIDI that can be used as a warp guide.

    Parameters:
    - source_track_index: Track index of the source MIDI clip
    - source_clip_index: Arrangement clip index for source
    - target_track_index: Track index of the target MIDI clip (groove to snap to)
    - target_clip_index: Arrangement clip index for target
    - source_offset: Beat offset for source clip start position
    - output_track_name: Name for the new quantized track

    Returns confirmation with the new track index.
    """
    try:
        from MCP_Server.audio_analysis import groove_align_quantize

        ableton = get_ableton_connection()

        # Get source clip info
        source_result = ableton.send_command("get_arrangement_clip_notes", {
            "track_index": source_track_index,
            "clip_index": source_clip_index
        })
        source_data = source_result.get("result", {})
        source_notes = source_data.get("notes", [])
        source_start = source_data.get("start_time", source_offset)
        source_length = source_data.get("length", 64)

        # Get target notes
        target_result = ableton.send_command("get_arrangement_clip_notes", {
            "track_index": target_track_index,
            "clip_index": target_clip_index
        })
        target_notes = target_result.get("result", {}).get("notes", [])

        if not source_notes:
            return "Error: No notes found in source clip"
        if not target_notes:
            return "Error: No notes found in target clip"

        # Quantize notes
        quantized_notes = groove_align_quantize(
            source_notes, target_notes, source_offset, max_snap_beats=1.0, match_by_pitch=True
        )

        # Create new track
        track_result = ableton.send_command("create_midi_track", {"index": -1})
        new_track_index = track_result.get("result", {}).get("index")

        if new_track_index is None:
            # Parse from message
            import re
            msg = track_result.get("message", "")
            match = re.search(r'(\d+)-', msg)
            if match:
                new_track_index = int(match.group(1)) - 1

        # Rename track
        ableton.send_command("set_track_name", {
            "track_index": new_track_index,
            "name": output_track_name
        })

        # Create clip in arrangement
        ableton.send_command("create_clip_in_arrangement", {
            "track_index": new_track_index,
            "start_time": source_start,
            "length": source_length
        })

        # Add quantized notes in batches
        batch_size = 100
        for i in range(0, len(quantized_notes), batch_size):
            batch = quantized_notes[i:i+batch_size]
            ableton.send_command("add_notes_to_arrangement_clip", {
                "track_index": new_track_index,
                "clip_index": 0,
                "notes": batch
            })

        return f"Created '{output_track_name}' track (index {new_track_index}) with {len(quantized_notes)} quantized notes aligned to target groove"

    except Exception as e:
        logger.error(f"Error creating quantized track: {str(e)}")
        return f"Error creating quantized track: {str(e)}"


@mcp.tool()
def groove_export_warp_markers(
    ctx: Context,
    source_track_index: int,
    source_clip_index: int,
    target_track_index: int,
    target_clip_index: int,
    source_offset: float = 0.0,
    min_offset_ms: float = 20.0,
    min_spacing_beats: float = 0.0,
    pitch_filter: str = "",
    max_markers: int = 0,
    quantize_targets_to: float = 0.0,
    output_path: str = "/tmp/warp_markers.json"
) -> str:
    """
    Export warp marker data for aligning source audio to target groove.

    Generates a list of time adjustments needed to align source to target.
    Can be used manually or with a Max for Live device to apply warping.

    Parameters:
    - source_track_index: Track index of the source MIDI clip (vocal rhythm)
    - source_clip_index: Arrangement clip index for source
    - target_track_index: Track index of the target MIDI clip (drums)
    - target_clip_index: Arrangement clip index for target
    - source_offset: Beat offset for source clip start position
    - min_offset_ms: Minimum timing offset to include (ignore smaller adjustments)
    - min_spacing_beats: Minimum spacing between markers in beats (e.g., 2.0 = half notes, 4.0 = bars)
    - pitch_filter: Comma-separated pitches to include (e.g., "36,38" for kick/snare only, empty = all)
    - max_markers: Maximum number of markers (0 = unlimited, prioritizes largest offsets)
    - quantize_targets_to: Snap target beats to grid (e.g., 1.0 = quarter notes, 4.0 = bars)
    - output_path: Path to save the warp markers file

    Returns path to the exported file with warp marker count.
    """
    try:
        from MCP_Server.audio_analysis import generate_warp_markers, export_warp_markers_to_file

        ableton = get_ableton_connection()

        # Get session tempo
        session = ableton.send_command("get_session_info")
        bpm = session.get("result", {}).get("tempo", 120.0)

        # Get source notes
        source_result = ableton.send_command("get_arrangement_clip_notes", {
            "track_index": source_track_index,
            "clip_index": source_clip_index
        })
        source_notes = source_result.get("result", {}).get("notes", [])

        # Get target notes
        target_result = ableton.send_command("get_arrangement_clip_notes", {
            "track_index": target_track_index,
            "clip_index": target_clip_index
        })
        target_notes = target_result.get("result", {}).get("notes", [])

        if not source_notes:
            return "Error: No notes found in source clip"
        if not target_notes:
            return "Error: No notes found in target clip"

        # Parse pitch filter
        pitch_list = None
        if pitch_filter:
            pitch_list = [int(p.strip()) for p in pitch_filter.split(",")]

        # Generate warp markers
        warp_markers = generate_warp_markers(
            source_notes,
            target_notes,
            source_offset,
            bpm,
            min_offset_ms,
            match_by_pitch=True,
            min_spacing_beats=min_spacing_beats,
            pitch_filter=pitch_list,
            max_markers=max_markers,
            quantize_targets_to=quantize_targets_to
        )

        # Export to file
        file_format = "csv" if output_path.endswith(".csv") else "json"
        export_warp_markers_to_file(warp_markers, output_path, file_format)

        return f"Exported {len(warp_markers)} warp markers to {output_path} (offset >= {min_offset_ms}ms, spacing >= {min_spacing_beats} beats)"

    except Exception as e:
        logger.error(f"Error exporting warp markers: {str(e)}")
        return f"Error exporting warp markers: {str(e)}"


# Main execution
def main():
    """Run the MCP server"""
    mcp.run()

if __name__ == "__main__":
    main()