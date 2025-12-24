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
            "duplicate_clip", "set_clip_loop", "set_clip_start_end", "clear_clip_notes",
            # Rack/Chain operations
            "insert_chain", "delete_chain", "set_chain_name", "set_chain_volume",
            "set_chain_mute", "insert_device_to_chain"
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
def split_arrangement_clip_multi(ctx: Context, track_index: int, clip_index: int, split_times: list) -> str:
    """
    Split an arrangement clip at multiple times in a single operation.

    More reliable than calling split multiple times - handles all splits in the
    correct order (left to right) to prevent clip corruption from overlapping
    duplicates.

    Parameters:
    - track_index: The index of the track containing the clip
    - clip_index: The index of the arrangement clip to split
    - split_times: List of beat positions to split at (will be sorted automatically)

    Returns JSON with list of resulting clips after all splits.
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("split_arrangement_clip_multi", {
            "track_index": track_index,
            "clip_index": clip_index,
            "split_times": split_times
        })
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error in multi-split: {str(e)}")
        return f"Error in multi-split: {str(e)}"


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
def align_clips_to_groove(ctx: Context, track_index: int, shift_beats: float) -> str:
    """
    Shift all arrangement clips on a track to align with target groove.

    Moves every clip on the specified track by the same amount.
    Use analyze_groove_timing to calculate the recommended shift.

    Parameters:
    - track_index: Track containing clips to shift
    - shift_beats: Amount to shift (positive = later, negative = earlier)

    Returns summary with list of moved clips.
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("align_clips_to_groove", {
            "track_index": track_index,
            "shift_beats": shift_beats
        })
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error aligning clips to groove: {str(e)}")
        return f"Error aligning clips to groove: {str(e)}"


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


@mcp.tool()
def get_compressor_sidechain_routing(ctx: Context, track_index: int, device_index: int) -> str:
    """
    Get sidechain routing info for a Compressor device.

    Parameters:
    - track_index: The index of the track containing the Compressor
    - device_index: The index of the Compressor device on the track

    Returns available routing types/channels and current routing selection.
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_compressor_sidechain_routing", {
            "track_index": track_index,
            "device_index": device_index
        })
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting compressor sidechain routing: {str(e)}")
        return f"Error getting compressor sidechain routing: {str(e)}"


@mcp.tool()
def set_compressor_sidechain_routing(ctx: Context, track_index: int, device_index: int, routing_type: str = None, routing_channel: str = None) -> str:
    """
    Set sidechain routing for a Compressor device.

    Parameters:
    - track_index: The index of the track containing the Compressor
    - device_index: The index of the Compressor device on the track
    - routing_type: The display name of the routing type (e.g., track name like "3-VOCALS")
    - routing_channel: The display name of the routing channel (e.g., "Post FX")

    Use get_compressor_sidechain_routing first to see available options.
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_compressor_sidechain_routing", {
            "track_index": track_index,
            "device_index": device_index,
            "routing_type": routing_type,
            "routing_channel": routing_channel
        })
        output = f"Updated sidechain routing on {result.get('device_name', 'Compressor')}"
        if "new_routing_type" in result:
            output += f"\n  Type: {result['new_routing_type']}"
        if "new_routing_channel" in result:
            output += f"\n  Channel: {result['new_routing_channel']}"
        return output
    except Exception as e:
        logger.error(f"Error setting compressor sidechain routing: {str(e)}")
        return f"Error setting compressor sidechain routing: {str(e)}"


@mcp.tool()
def setup_sidechain(ctx: Context, target_track: int, target_device: int, source_track: int, source_channel: str = "Post FX") -> str:
    """
    Configure sidechain routing on a Compressor to use audio from another track.

    This is a convenience tool that:
    1. Gets the source track name
    2. Sets the Compressor's sidechain input to that track
    3. Enables sidechain (S/C On parameter)

    Parameters:
    - target_track: Track index containing the Compressor to configure
    - target_device: Device index of the Compressor on target_track
    - source_track: Track index to use as sidechain source (e.g., vocals)
    - source_channel: Channel type - "Post FX" (default) or "Pre FX"

    Example: setup_sidechain(0, 0, 2) - sets track 0's first Compressor to sidechain from track 2
    """
    try:
        ableton = get_ableton_connection()

        # Get source track name
        track_info = ableton.send_command("get_track_info", {"track_index": source_track})
        source_track_name = track_info.get("name", f"{source_track + 1}-Audio")

        # Set sidechain routing
        result = ableton.send_command("set_compressor_sidechain_routing", {
            "track_index": target_track,
            "device_index": target_device,
            "routing_type": source_track_name,
            "routing_channel": source_channel
        })

        # Enable sidechain (S/C On is typically parameter index 20)
        # First get device parameters to find S/C On
        params = ableton.send_command("get_device_parameters", {
            "track_index": target_track,
            "device_index": target_device
        })

        sc_on_index = None
        for p in params.get("parameters", []):
            if p.get("name") == "S/C On":
                sc_on_index = p.get("index")
                break

        if sc_on_index is not None:
            ableton.send_command("set_device_parameter", {
                "track_index": target_track,
                "device_index": target_device,
                "parameter_index": sc_on_index,
                "value": 1.0
            })

        return f"Configured sidechain on {result.get('device_name', 'Compressor')}:\n  Source: {source_track_name} ({source_channel})\n  Sidechain: Enabled"
    except Exception as e:
        logger.error(f"Error setting up sidechain: {str(e)}")
        return f"Error setting up sidechain: {str(e)}"


# ============================================
# RACK/CHAIN OPERATIONS
# ============================================

@mcp.tool()
def get_rack_chains(ctx: Context, track_index: int, device_index: int) -> str:
    """
    Get all chains in a rack device (Audio Effect Rack, Instrument Rack, etc.).

    Parameters:
    - track_index: The index of the track containing the rack (-1 for master track)
    - device_index: The index of the rack device on the track

    Returns chain info including name, volume, mute state, and devices in each chain.
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_rack_chains", {
            "track_index": track_index,
            "device_index": device_index
        })
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting rack chains: {str(e)}")
        return f"Error getting rack chains: {str(e)}"


@mcp.tool()
def insert_chain(ctx: Context, track_index: int, device_index: int, chain_index: int = None) -> str:
    """
    Insert a new chain into a rack device. Requires Live 12+.

    Parameters:
    - track_index: The index of the track containing the rack
    - device_index: The index of the rack device on the track
    - chain_index: Optional index where to insert the chain (default: end of list)
    """
    try:
        ableton = get_ableton_connection()
        params = {
            "track_index": track_index,
            "device_index": device_index
        }
        if chain_index is not None:
            params["chain_index"] = chain_index
        result = ableton.send_command("insert_chain", params)
        return f"Inserted chain at index {result.get('chain_index')} in {result.get('device_name')} (total chains: {result.get('chain_count')})"
    except Exception as e:
        logger.error(f"Error inserting chain: {str(e)}")
        return f"Error inserting chain: {str(e)}"


@mcp.tool()
def delete_chain(ctx: Context, track_index: int, device_index: int, chain_index: int) -> str:
    """
    Delete a chain from a rack device. Requires Live 12+.

    Parameters:
    - track_index: The index of the track containing the rack
    - device_index: The index of the rack device on the track
    - chain_index: The index of the chain to delete
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("delete_chain", {
            "track_index": track_index,
            "device_index": device_index,
            "chain_index": chain_index
        })
        return f"Deleted chain '{result.get('deleted_chain_name')}' from {result.get('device_name')} (remaining chains: {result.get('chain_count')})"
    except Exception as e:
        logger.error(f"Error deleting chain: {str(e)}")
        return f"Error deleting chain: {str(e)}"


@mcp.tool()
def set_chain_name(ctx: Context, track_index: int, device_index: int, chain_index: int, name: str) -> str:
    """
    Set the name of a chain in a rack device.

    Parameters:
    - track_index: The index of the track containing the rack
    - device_index: The index of the rack device on the track
    - chain_index: The index of the chain to rename
    - name: The new name for the chain
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_chain_name", {
            "track_index": track_index,
            "device_index": device_index,
            "chain_index": chain_index,
            "name": name
        })
        return f"Renamed chain from '{result.get('old_name')}' to '{result.get('new_name')}' in {result.get('device_name')}"
    except Exception as e:
        logger.error(f"Error setting chain name: {str(e)}")
        return f"Error setting chain name: {str(e)}"


@mcp.tool()
def set_chain_volume(ctx: Context, track_index: int, device_index: int, chain_index: int, volume: float) -> str:
    """
    Set the volume of a chain in a rack device.

    Parameters:
    - track_index: The index of the track containing the rack
    - device_index: The index of the rack device on the track
    - chain_index: The index of the chain
    - volume: Volume level from 0.0 (silence) to 1.0 (0dB)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_chain_volume", {
            "track_index": track_index,
            "device_index": device_index,
            "chain_index": chain_index,
            "volume": volume
        })
        return f"Set volume of chain '{result.get('chain_name')}' to {result.get('volume')} in {result.get('device_name')}"
    except Exception as e:
        logger.error(f"Error setting chain volume: {str(e)}")
        return f"Error setting chain volume: {str(e)}"


@mcp.tool()
def set_chain_mute(ctx: Context, track_index: int, device_index: int, chain_index: int, muted: bool) -> str:
    """
    Set the mute state of a chain in a rack device.

    Parameters:
    - track_index: The index of the track containing the rack
    - device_index: The index of the rack device on the track
    - chain_index: The index of the chain
    - muted: True to mute, False to unmute
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_chain_mute", {
            "track_index": track_index,
            "device_index": device_index,
            "chain_index": chain_index,
            "muted": muted
        })
        state = "muted" if result.get('muted') else "unmuted"
        return f"Chain '{result.get('chain_name')}' is now {state} in {result.get('device_name')}"
    except Exception as e:
        logger.error(f"Error setting chain mute: {str(e)}")
        return f"Error setting chain mute: {str(e)}"


@mcp.tool()
def insert_device_to_chain(ctx: Context, track_index: int, device_index: int, chain_index: int, device_name: str, position: int = None) -> str:
    """
    Insert a native Live device into a chain. Requires Live 12+.

    Only native Ableton devices can be inserted (e.g., "Saturator", "EQ Eight", "Compressor").
    Max for Live devices and third-party plugins are not supported.

    Parameters:
    - track_index: The index of the track containing the rack
    - device_index: The index of the rack device on the track
    - chain_index: The index of the chain to add the device to
    - device_name: The name of the device as it appears in Ableton's browser (e.g., "Saturator", "EQ Eight")
    - position: Optional position in the chain's device list (default: end)
    """
    try:
        ableton = get_ableton_connection()
        params = {
            "track_index": track_index,
            "device_index": device_index,
            "chain_index": chain_index,
            "device_name": device_name
        }
        if position is not None:
            params["position"] = position
        result = ableton.send_command("insert_device_to_chain", params)
        return f"Inserted '{result.get('device_name')}' into chain '{result.get('chain_name')}' in {result.get('rack_name')} (devices: {result.get('device_count')})"
    except Exception as e:
        logger.error(f"Error inserting device to chain: {str(e)}")
        return f"Error inserting device to chain: {str(e)}"


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


@mcp.tool()
def clear_arrangement_clip_notes(ctx: Context, track_index: int, clip_index: int) -> str:
    """
    Clear all MIDI notes from an arrangement clip.

    Parameters:
    - track_index: The index of the track containing the clip
    - clip_index: The index of the arrangement clip
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("clear_arrangement_clip_notes", {
            "track_index": track_index,
            "clip_index": clip_index
        })
        return f"Cleared all notes from arrangement clip '{result.get('clip_name', 'clip')}'"
    except Exception as e:
        logger.error(f"Error clearing arrangement clip notes: {str(e)}")
        return f"Error clearing arrangement clip notes: {str(e)}"


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
    Ask questions about an audio file using AI (Music Flamingo via Replicate).

    Music Flamingo is a state-of-the-art Large Audio-Language Model for music
    understanding with theory-aware Q&A (harmony, structure, timbre, lyrics,
    cultural context), chain-of-thought reasoning, and long-form song reasoning.

    Examples: "What instruments are playing?", "Describe the mood of this track",
    "What genre would you classify this as?", "Are there any issues with the mix?"

    Parameters:
    - file_path: Absolute path to the audio file (WAV, MP3, AIFF, AAC, OGG, FLAC, M4A)
    - prompt: Your question or instruction about the audio

    Note: Requires REPLICATE_API_TOKEN environment variable to be set.
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
        return f"Missing dependency: {str(e)}. Run: pip install replicate"
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
def analyze_energy(ctx: Context, file_path: str, bpm: float = None, target_bpm: float = None) -> str:
    """
    Analyze energy features of an audio file per sixteenth note.

    Returns 8 energy metrics per time slice:
    - rms: Overall loudness (0-1)
    - centroid: Spectral brightness (0-1)
    - flux: Rate of spectral change (0-1)
    - bands[0-4]: Energy in frequency bands (Sub/Bass/LowMid/HighMid/High)

    Band frequency ranges:
    - bands[0]: Sub 20-60 Hz
    - bands[1]: Bass 60-250 Hz
    - bands[2]: LowMid 250-500 Hz
    - bands[3]: HighMid 500-2000 Hz
    - bands[4]: High 2000-20000 Hz

    Parameters:
    - file_path: Absolute path to the audio file
    - bpm: Tempo in BPM (if not provided, detects via song structure analysis)
    - target_bpm: Lock BPM detection to this value (±1 BPM) when auto-detecting

    Returns JSON with struct-of-arrays format for compact output:
    - times: array of timestamps (seconds)
    - rms, centroid, flux: arrays of values
    - bands: 5 arrays of band energy values
    - global_stats: median and std for classification
    """
    try:
        from MCP_Server.audio_analysis import extract_energy_features

        # If BPM not provided, detect it
        effective_bpm = bpm
        if effective_bpm is None:
            from MCP_Server.audio_analysis import analyze_song_structure as do_structure
            structure = do_structure(file_path, include_beats=False, target_bpm=target_bpm)
            effective_bpm = structure.get('bpm', 120.0)
            logger.info(f"Auto-detected BPM: {effective_bpm}")

        result = extract_energy_features(file_path, effective_bpm)
        return json.dumps(result)  # No indent to save space for large arrays
    except ValueError as e:
        logger.error(f"Energy analysis error: {str(e)}")
        return f"Error: {str(e)}"
    except Exception as e:
        logger.error(f"Error analyzing energy: {str(e)}")
        return f"Error analyzing energy: {str(e)}"


@mcp.tool()
def analyze_vocal_onsets(ctx: Context, file_path: str, bpm: float = None) -> str:
    """
    Detect vocal onsets and return positions.

    Uses librosa onset detection to find transient moments in vocal audio.
    Useful for analyzing vocal timing and rhythm patterns.

    Parameters:
    - file_path: Path to vocal audio file
    - bpm: BPM for beat conversion (auto-detects if not provided)

    Returns JSON with onset times in seconds and beats.
    """
    try:
        from MCP_Server.audio_analysis import analyze_vocal_onsets as do_analysis
        result = do_analysis(file_path, bpm)
        return json.dumps(result, indent=2)
    except ValueError as e:
        logger.error(f"Vocal onset analysis error: {str(e)}")
        return f"Error: {str(e)}"
    except Exception as e:
        logger.error(f"Error analyzing vocal onsets: {str(e)}")
        return f"Error analyzing vocal onsets: {str(e)}"


@mcp.tool()
def analyze_groove_timing(ctx: Context, vocal_onsets: str, drum_hits: str, bpm: float = 170.0) -> str:
    """
    Compare timing feel between vocal onsets and drum groove.

    Analyzes how far each source is from the beat grid and calculates
    the recommended shift to align vocals with the drum groove.

    Parameters:
    - vocal_onsets: JSON array of onset beat positions (from analyze_vocal_onsets)
    - drum_hits: JSON array of drum hit beat positions (kick/snare from MIDI)
    - bpm: Session tempo for ms calculations (default: 170)

    Returns analysis with:
    - vocal_grid_offset_ms: How far vocals are from grid
    - drum_grid_offset_ms: How far drums are from grid
    - recommended_shift_ms: How much to shift vocals to match drums
    - recommended_shift_beats: Same in beats
    """
    try:
        from MCP_Server.audio_analysis import analyze_groove_timing as do_analysis

        # Parse JSON inputs
        vocal_list = json.loads(vocal_onsets) if isinstance(vocal_onsets, str) else vocal_onsets
        drum_list = json.loads(drum_hits) if isinstance(drum_hits, str) else drum_hits

        result = do_analysis(vocal_list, drum_list, bpm)
        return json.dumps(result, indent=2)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON input: {str(e)}")
        return f"Error: Invalid JSON input - {str(e)}"
    except Exception as e:
        logger.error(f"Error analyzing groove timing: {str(e)}")
        return f"Error analyzing groove timing: {str(e)}"


@mcp.tool()
def analyze_mashup_timing(
    ctx: Context,
    vocal_file: str,
    vocal_track_index: int,
    drum_track_index: int,
    drum_clip_index: int = 0,
    bpm: float = None
) -> str:
    """
    Analyze timing alignment between vocals and drums for a mashup.

    This is a high-level tool that orchestrates the full timing analysis workflow:
    1. Detects vocal onsets from source file
    2. Gets vocal clip positions from arrangement (with loop_start/loop_end)
    3. Maps onsets to arrangement positions using clip offsets
    4. Extracts drum hits from MIDI clip
    5. Compares timing feel and recommends shift

    Parameters:
    - vocal_file: Path to source vocal audio file
    - vocal_track_index: Track containing vocal clips in arrangement
    - drum_track_index: Track containing drum MIDI
    - drum_clip_index: Which arrangement clip has the drums (default: 0)
    - bpm: Session BPM (auto-detects from session if not provided)

    Returns analysis with recommended timing correction.
    """
    try:
        from MCP_Server.audio_analysis import analyze_vocal_onsets, analyze_groove_timing

        ableton = get_ableton_connection()

        # 1. Get session BPM if not provided
        if bpm is None:
            session = ableton.send_command("get_session_info", {})
            bpm = session.get("tempo", 170.0)
            logger.info(f"Using session BPM: {bpm}")

        # 2. Detect vocal onsets
        logger.info(f"Analyzing vocal onsets from: {vocal_file}")
        onset_result = analyze_vocal_onsets(vocal_file, bpm)
        onset_beats = onset_result["onset_beats"]
        logger.info(f"Detected {len(onset_beats)} vocal onsets")

        # 3. Get vocal clip positions with loop_start
        vocal_clips = ableton.send_command("get_arrangement_clips", {
            "track_index": vocal_track_index
        })
        clips = vocal_clips.get("clips", [])
        logger.info(f"Found {len(clips)} vocal clips on track {vocal_track_index}")

        # 4. Map onsets to arrangement positions
        def map_onset_to_arrangement(src_beat, clip_list):
            for clip in clip_list:
                src_start = clip.get("loop_start", 0)
                src_end = clip.get("loop_end", clip.get("length", 0) + src_start)
                if src_start <= src_beat < src_end:
                    offset = src_beat - src_start
                    return clip["start_time"] + offset
            return None

        mapped_onsets = []
        for beat in onset_beats:
            arr_pos = map_onset_to_arrangement(beat, clips)
            if arr_pos is not None:
                mapped_onsets.append(arr_pos)

        logger.info(f"Mapped {len(mapped_onsets)} onsets to arrangement")

        # 5. Get drum MIDI notes
        drum_notes = ableton.send_command("get_arrangement_clip_notes", {
            "track_index": drum_track_index,
            "clip_index": drum_clip_index
        })
        notes = drum_notes.get("notes", [])

        # Filter to kick (36) and snare (38)
        drum_hits = [n["start_time"] for n in notes if n.get("pitch") in [36, 38]]
        logger.info(f"Found {len(drum_hits)} kick/snare hits")

        # 6. Analyze groove timing
        timing_result = analyze_groove_timing(mapped_onsets, drum_hits, bpm)

        # 7. Return combined analysis
        result = {
            "bpm": bpm,
            "vocal_onsets_total": len(onset_beats),
            "vocal_onsets_mapped": len(mapped_onsets),
            "vocal_clips": len(clips),
            "drum_hits": len(drum_hits),
            "timing_analysis": timing_result,
            "recommendation": f"Shift vocal clips by {timing_result['recommended_shift_beats']:.4f} beats ({timing_result['recommended_shift_ms']:.1f}ms)"
        }

        return json.dumps(result, indent=2)

    except Exception as e:
        logger.error(f"Error analyzing mashup timing: {str(e)}")
        return f"Error analyzing mashup timing: {str(e)}"


@mcp.tool()
def annotate_arrangement(
    ctx: Context,
    file_path: str,
    annotation_track_name: str = "Structure",
    create_cue_points: bool = True,
    target_bpm: float = None
) -> str:
    """
    Analyze audio and create annotation track in Ableton's arrangement view.

    Creates a "ghost MIDI" track with clips for each song section, using:
    - Clip names to encode metadata: "[CHORUS] Hi (up) | bars 33-64"
    - MIDI note pitches for section type (intro=C1, verse=D1, chorus=F1, etc.)
    - MIDI note velocity for energy level (hi=127, lo=50)
    - MIDI note duration for energy direction (up=full, down=half, same=quarter)

    Energy classification:
    - Level: "hi" if segment energy > track median, "lo" otherwise
    - Direction: "up"/"down"/"same" relative to previous segment

    Parameters:
    - file_path: Absolute path to the audio file to analyze
    - annotation_track_name: Name for the annotation track (default: "Structure")
    - create_cue_points: Create locators at section boundaries (default: True)
    - target_bpm: Lock BPM detection to this value (±1 BPM)

    Returns JSON summary with created track, segments, and energy classifications.
    """
    try:
        from MCP_Server.audio_analysis import (
            analyze_song_structure as do_structure,
            extract_energy_features,
            classify_segment_energy
        )

        ableton = get_ableton_connection()

        # Step 1: Analyze song structure
        logger.info(f"Analyzing song structure for {file_path}...")
        structure = do_structure(file_path, include_beats=True, target_bpm=target_bpm)
        bpm = structure.get('bpm', 120.0)
        segments = structure.get('segments', [])

        if not segments:
            return json.dumps({"error": "No segments detected in audio"})

        # Step 2: Extract energy features
        logger.info(f"Extracting energy features at {bpm} BPM...")
        energy_data = extract_energy_features(file_path, bpm)

        # Step 3: Classify segment energy
        annotated_segments = classify_segment_energy(segments, energy_data, bpm)

        # Step 4: Create annotation MIDI track
        logger.info(f"Creating annotation track '{annotation_track_name}'...")
        track_result = ableton.send_command("create_midi_track", {"index": -1})
        track_index = track_result.get("index")

        ableton.send_command("set_track_name", {
            "track_index": track_index,
            "name": annotation_track_name
        })

        # Section type to MIDI pitch mapping
        section_pitches = {
            "intro": 24,    # C1
            "verse": 26,    # D1
            "pre-chorus": 27,  # D#1
            "chorus": 29,   # F1
            "bridge": 31,   # G1
            "outro": 33,    # A1
            "instrumental": 35,  # B1
            "solo": 28,     # E1
            "breakdown": 30,  # F#1
            "buildup": 32,  # G#1
        }
        default_pitch = 24  # C1 for unknown sections

        # Energy level to velocity
        energy_velocities = {"hi": 127, "lo": 50}

        # Create clips for each segment
        created_clips = []
        for i, seg in enumerate(annotated_segments):
            start_beat = seg.get('start_beat', 0)
            end_beat = seg.get('end_beat', start_beat + 16)
            label = seg.get('label', 'unknown').lower()
            energy_level = seg.get('energy_level', 'lo')
            energy_direction = seg.get('energy_direction', 'same')

            clip_length = end_beat - start_beat
            if clip_length <= 0:
                continue

            # Create clip
            clip_result = ableton.send_command("create_clip_in_arrangement", {
                "track_index": track_index,
                "start_time": start_beat,
                "length": clip_length
            })
            clip_index = clip_result.get("clip_index", i)

            # Determine note properties
            pitch = section_pitches.get(label, default_pitch)
            velocity = energy_velocities.get(energy_level, 50)

            # Duration based on direction
            if energy_direction == "up":
                note_duration = clip_length
            elif energy_direction == "down":
                note_duration = clip_length / 2
            else:
                note_duration = clip_length / 4

            # Add MIDI note
            ableton.send_command("add_notes_to_arrangement_clip", {
                "track_index": track_index,
                "clip_index": clip_index,
                "notes": [{
                    "pitch": pitch,
                    "start_time": 0,
                    "duration": note_duration,
                    "velocity": velocity,
                    "mute": False
                }]
            })

            # Set clip name with metadata
            start_bar = int(start_beat / 4) + 1
            end_bar = int(end_beat / 4)
            clip_name = f"[{label.upper()}] {energy_level.capitalize()} ({energy_direction}) | bars {start_bar}-{end_bar}"

            ableton.send_command("set_arrangement_clip_name", {
                "track_index": track_index,
                "clip_index": clip_index,
                "name": clip_name
            })

            created_clips.append({
                "label": label,
                "start_beat": start_beat,
                "end_beat": end_beat,
                "energy_level": energy_level,
                "energy_direction": energy_direction,
                "clip_name": clip_name
            })

        # Step 5: Create cue points at segment boundaries
        cue_points_created = 0
        if create_cue_points:
            for seg in annotated_segments:
                start_beat = seg.get('start_beat', 0)
                try:
                    ableton.send_command("create_cue_point", {"time": start_beat})
                    cue_points_created += 1
                except Exception as e:
                    logger.warning(f"Failed to create cue point at {start_beat}: {e}")

        return json.dumps({
            "success": True,
            "bpm": bpm,
            "annotation_track_index": track_index,
            "segments": created_clips,
            "cue_points_created": cue_points_created,
            "energy_data_available": True  # Can call analyze_energy for raw data
        }, indent=2)

    except Exception as e:
        logger.error(f"Error annotating arrangement: {str(e)}")
        return json.dumps({"error": str(e)})


@mcp.tool()
def set_arrangement_clip_name(ctx: Context, track_index: int, clip_index: int, name: str) -> str:
    """
    Set the name of an arrangement clip.

    Parameters:
    - track_index: The index of the track containing the clip
    - clip_index: The index of the arrangement clip
    - name: The new name for the clip
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_arrangement_clip_name", {
            "track_index": track_index,
            "clip_index": clip_index,
            "name": name
        })
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error setting arrangement clip name: {str(e)}")
        return f"Error setting arrangement clip name: {str(e)}"


@mcp.tool()
def vocal_to_midi(ctx: Context, audio_path: str, output_midi_path: str, bpm: float = 120.0,
                  create_track: bool = False, track_name: str = "Vocal Rhythm") -> str:
    """
    Convert vocal audio to MIDI based on phoneme categorization.

    Analyzes vocal onsets and categorizes them by phoneme type, mapping to
    standard drum rack MIDI notes (like Ableton's "Convert Drums to MIDI Track"):
    - Plosives (P/B/T/K) → Snare (D1/38) - Percussive attacks
    - Fricatives (S/Sh/F) → HiHat (F#1/42) - High frequency content
    - Vowels/Nasals (A/E/M/N) → Kick (C1/36) - Tonal body

    Parameters:
    - audio_path: Path to the vocal audio file
    - output_midi_path: Path to save the output MIDI file
    - bpm: Tempo in BPM (default: 120)
    - create_track: If True, creates a MIDI track in Ableton with Drum Rack (default: False)
    - track_name: Name for the new track if create_track is True

    Returns summary with onset count and phoneme categories.
    """
    try:
        from MCP_Server.audio_analysis import vocal_to_midi as do_vocal_to_midi
        result = do_vocal_to_midi(audio_path, output_midi_path, bpm)

        output = (
            f"Converted vocals to MIDI: {result['output_path']}\n"
            f"Duration: {result['duration']:.1f}s, BPM: {result['bpm']}\n"
            f"Onsets: {result['onset_count']} total\n"
            f"  - Plosives (Snare/D1): {result['categories']['plosive']}\n"
            f"  - Fricatives (HiHat/F#1): {result['categories']['fricative']}\n"
            f"  - Vowels (Kick/C1): {result['categories']['vowel']}"
        )

        # Optionally create MIDI track with Drum Rack in Ableton and add notes directly
        if create_track:
            try:
                ableton = get_ableton_connection()

                # Create a new MIDI track
                track_result = ableton.send_command("create_midi_track", {"index": -1})
                track_index = track_result.get("track_index")

                # Set track name
                ableton.send_command("set_track_name", {
                    "track_index": track_index,
                    "name": track_name
                })

                # Load a basic Drum Rack
                try:
                    ableton.send_command("load_browser_item", {
                        "track_index": track_index,
                        "item_uri": "query:Drums#Drum%20Rack"
                    })
                except:
                    logger.warning("Could not load Drum Rack - you may need to load one manually")

                # Create an arrangement clip with the right length
                clip_length = result['duration'] * result['bpm'] / 60.0  # Duration in beats
                clip_result = ableton.send_command("create_clip_in_arrangement", {
                    "track_index": track_index,
                    "start_time": 0,
                    "length": clip_length
                })
                clip_index = clip_result.get("clip_index", 0)

                # Add the notes directly to the clip
                notes = result.get('notes', [])
                if notes:
                    ableton.send_command("add_notes_to_arrangement_clip", {
                        "track_index": track_index,
                        "clip_index": clip_index,
                        "notes": notes
                    })

                output += f"\n\nCreated MIDI track '{track_name}' at index {track_index}"
                output += f"\nAdded {len(notes)} notes to arrangement clip"

            except Exception as track_err:
                output += f"\n\nNote: Could not create Ableton track: {str(track_err)}"
                output += f"\nMIDI file saved to {result['output_path']} - drag it into Ableton manually"

        return output

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
def create_structure_track(
    ctx: Context,
    file_path: str,
    track_name: str = "Structure",
    target_bpm: float = None,
    audio_track_index: int = None,
    audio_start_beat: float = None,
    create_cue_points: bool = True
) -> str:
    """
    Create a structure MIDI track with energy visualization for mashup alignment.

    Analyzes the audio file and creates a MIDI track with arrangement clips where:
    - Each clip represents a song section (intro, verse, chorus, etc.)
    - Energy meter notes visualize RMS and flux per 16th note:
      - Pitch 36-59: RMS energy level (36=low, 59=high)
      - Velocity 1-80: Spectral flux (1=static, 80=dynamic)
    - Downbeat markers at pitch 72 (C5) every 4 beats for alignment

    This is the streamlined tool for creating structure tracks - call it once with
    an audio file path and it handles all analysis and MIDI creation automatically.

    IMPORTANT: For accurate alignment, either:
    - Provide audio_track_index to auto-detect the audio clip's position, OR
    - Provide audio_start_beat if you know where the audio's bar 1 starts

    The tool uses downbeat detection to snap segment boundaries to actual bar lines,
    accounting for any intro/silence before bar 1 in the audio file.

    Parameters:
    - file_path: Absolute path to the audio file (WAV, MP3, AIFF, etc.)
    - track_name: Name for the MIDI track (default: "Structure")
    - target_bpm: Lock BPM detection to this value (±1 BPM). Use when tempo is
                  misdetected (e.g., 140 BPM detected as 81 BPM).
    - audio_track_index: Track index containing the audio clip (to auto-detect position)
    - audio_start_beat: Manual override for where audio's bar 1 starts in arrangement.
                        If not provided and audio_track_index is given, auto-detects
                        from the first arrangement clip on that track.
    - create_cue_points: Create locators at section boundaries (default: True)

    Returns JSON with track_index, clips created, and analysis summary.
    """
    import time as time_module

    try:
        from MCP_Server.audio_analysis import (
            analyze_song_structure as do_structure,
            extract_energy_features,
        )

        ableton = get_ableton_connection()

        # Step 1: Get project tempo from Ableton
        session_info = ableton.send_command("get_session_info", {})
        project_bpm = session_info.get('tempo', 120.0)
        logger.info(f"Project tempo: {project_bpm} BPM")

        # Step 2: Analyze song structure
        logger.info(f"Analyzing song structure for {file_path}...")
        structure = do_structure(file_path, include_beats=True, target_bpm=target_bpm)
        audio_bpm = structure.get('bpm', 120.0)
        segments = structure.get('segments', [])

        if not segments:
            return json.dumps({"error": "No segments detected in audio"})

        # Get downbeats for proper bar alignment
        downbeats = structure.get('downbeats', [])
        logger.info(f"Detected audio BPM: {audio_bpm}, Segments: {len(segments)}, Downbeats: {len(downbeats)}")

        # Step 3: Determine where bar 1 of the audio starts in the arrangement
        # This is critical for alignment accuracy
        #
        # Key insight: When Ableton warps audio, it typically sets the clip's 1.1.1 marker
        # to align with the first detected beat. So the clip_start position usually
        # already accounts for any intro/silence before bar 1.
        #
        # The first_downbeat from our analysis tells us where WE think bar 1 is,
        # which may differ from what Ableton detected. For accuracy, we use our
        # downbeat positions for segment boundaries, but trust the clip position
        # for the overall alignment.

        bar1_offset_beat = 0.0  # Default: bar 1 starts at beat 0
        first_downbeat_sec = downbeats[0] if downbeats else 0
        first_downbeat_beats = first_downbeat_sec * audio_bpm / 60.0

        if audio_start_beat is not None:
            # User explicitly specified where bar 1 starts - trust them completely
            bar1_offset_beat = audio_start_beat
            logger.info(f"Using user-specified audio_start_beat: {bar1_offset_beat}")
        elif audio_track_index is not None:
            # Auto-detect from the audio clip's position
            logger.info(f"Auto-detecting audio position from track {audio_track_index}...")
            clips_result = ableton.send_command("get_arrangement_clips", {
                "track_index": audio_track_index
            })
            audio_clips = clips_result.get('clips', [])
            if audio_clips:
                # Use the first clip's start position
                # For warped clips, Ableton's clip start usually = bar 1 of the audio
                # (because Ableton aligns the 1.1.1 marker during warping)
                clip_start = audio_clips[0].get('start_time', 0)

                # If the first downbeat is very close to 0 (< 0.5 beats), assume
                # Ableton has already aligned things and use clip_start directly.
                # Otherwise, there's significant intro before bar 1 that we need to account for.
                if first_downbeat_beats < 0.5:
                    bar1_offset_beat = clip_start
                    logger.info(f"Audio clip starts at beat {clip_start}, first downbeat near start ({first_downbeat_beats:.2f} beats)")
                else:
                    # Significant offset - add it to the clip start
                    bar1_offset_beat = clip_start + first_downbeat_beats
                    logger.info(f"Audio clip starts at beat {clip_start}, first downbeat at {first_downbeat_sec:.2f}s = {first_downbeat_beats:.2f} beats")

                logger.info(f"Bar 1 of audio is at arrangement beat {bar1_offset_beat}")
            else:
                logger.warning(f"No clips found on track {audio_track_index}, using beat 0 + first downbeat offset")
                bar1_offset_beat = first_downbeat_beats
        else:
            # No position info provided - assume clip starts at beat 0
            # Add first downbeat offset if there's intro before bar 1
            bar1_offset_beat = first_downbeat_beats
            logger.info(f"No audio position specified. First downbeat at {first_downbeat_sec:.2f}s = bar 1 at beat {bar1_offset_beat:.2f}")

        # Step 4: Extract energy features
        logger.info(f"Extracting energy features at {audio_bpm} BPM...")
        energy_data = extract_energy_features(file_path, audio_bpm)

        # Step 5: Create MIDI track
        logger.info(f"Creating MIDI track '{track_name}'...")
        track_result = ableton.send_command("create_midi_track", {"index": -1})
        track_index = track_result.get("index")

        ableton.send_command("set_track_name", {
            "track_index": track_index,
            "name": track_name
        })

        # Step 6: Convert segments to beat positions, snapping to downbeats
        # Segments have 'start' and 'end' in seconds
        # Downbeats are timestamps in seconds where each bar's beat 1 occurs

        # Helper function to find the nearest downbeat and return its bar number
        def snap_to_nearest_bar(time_sec: float) -> int:
            """Snap a time in seconds to the nearest bar number (1-indexed)."""
            if not downbeats:
                # Fallback: calculate bar from raw time
                beat = time_sec * audio_bpm / 60.0
                return max(1, round(beat / 4) + 1)

            # Find closest downbeat
            best_bar = 1
            best_dist = float('inf')
            for i, db_time in enumerate(downbeats):
                dist = abs(db_time - time_sec)
                if dist < best_dist:
                    best_dist = dist
                    best_bar = i + 1  # 1-indexed bars
            return best_bar

        clips_data = []
        for i, seg in enumerate(segments):
            start_sec = seg.get('start', 0)
            end_sec = seg.get('end', start_sec + 4)
            label = seg.get('label', 'unknown').upper()

            # Snap to nearest bar boundaries
            start_bar = snap_to_nearest_bar(start_sec)
            end_bar = snap_to_nearest_bar(end_sec)

            # Convert bar numbers to arrangement beats
            # bar 1 = bar1_offset_beat, bar 2 = bar1_offset_beat + 4, etc.
            start_beat = bar1_offset_beat + (start_bar - 1) * 4
            end_beat = bar1_offset_beat + (end_bar - 1) * 4

            # Ensure we have at least one bar of content
            if end_beat <= start_beat:
                end_beat = start_beat + 4

            clips_data.append({
                'label': label,
                'start_beat': start_beat,
                'end_beat': end_beat,
                'start_bar': start_bar,
                'end_bar': end_bar,
            })

        # Ensure continuous boundaries (no gaps or overlaps between clips)
        for i in range(1, len(clips_data)):
            if clips_data[i]['start_beat'] != clips_data[i-1]['end_beat']:
                clips_data[i]['start_beat'] = clips_data[i-1]['end_beat']

        # Step 5: Create clips and add notes
        created_clips = []
        energy_times = energy_data['times']
        energy_rms = energy_data['rms']
        energy_flux = energy_data['flux']

        for i, clip_data in enumerate(clips_data):
            start_beat = clip_data['start_beat']
            end_beat = clip_data['end_beat']
            start_bar = clip_data['start_bar']
            end_bar = clip_data['end_bar']
            label = clip_data['label']
            length = end_beat - start_beat

            if length <= 0:
                continue

            # Create the clip
            logger.info(f"Creating clip {i}: {label} (bars {start_bar}-{end_bar}) at arrangement beat {start_beat}, length {length}")
            clip_result = ableton.send_command("create_clip_in_arrangement", {
                "track_index": track_index,
                "start_time": start_beat,
                "length": length
            })
            clip_index = clip_result.get("clip_index", i)

            # Small delay to ensure clip is created
            time_module.sleep(0.1)

            # Generate energy meter notes
            notes = []

            # Downbeat markers at pitch 72 every 4 beats
            beat = 0
            while beat < length:
                notes.append({
                    "pitch": 72,  # C5
                    "start_time": beat,
                    "duration": 0.25,
                    "velocity": 100,
                    "mute": False
                })
                beat += 4

            # Energy meter notes per 16th note
            # Convert audio bar range to seconds for energy data lookup
            # Energy data is in original audio time, so use audio bar positions
            audio_start_sec = (start_bar - 1) * 4 * 60.0 / audio_bpm
            audio_end_sec = (end_bar - 1) * 4 * 60.0 / audio_bpm

            for j, t in enumerate(energy_times):
                if t < audio_start_sec or t >= audio_end_sec:
                    continue

                # Convert time to beat position within clip
                # t is in seconds from audio start, convert to beats relative to this clip
                beat_pos = (t - audio_start_sec) * audio_bpm / 60.0

                # Get energy values
                rms_val = energy_rms[j] if j < len(energy_rms) else 0
                flux_val = energy_flux[j] if j < len(energy_flux) else 0

                # Map RMS to pitch 36-59 (24 semitones range)
                pitch = 36 + int(rms_val * 23)
                pitch = max(36, min(59, pitch))

                # Map flux to velocity 1-80
                velocity = 1 + int(flux_val * 79)
                velocity = max(1, min(80, velocity))

                notes.append({
                    "pitch": pitch,
                    "start_time": round(beat_pos, 4),
                    "duration": 0.25,
                    "velocity": velocity,
                    "mute": False
                })

            # Add notes to clip in batches
            if notes:
                batch_size = 100
                for batch_start in range(0, len(notes), batch_size):
                    batch = notes[batch_start:batch_start + batch_size]
                    ableton.send_command("add_notes_to_arrangement_clip", {
                        "track_index": track_index,
                        "clip_index": clip_index,
                        "notes": batch
                    })
                    time_module.sleep(0.05)

            # Set clip name using audio bar numbers
            clip_name = f"{label} | bars {start_bar}-{end_bar}"

            ableton.send_command("set_arrangement_clip_name", {
                "track_index": track_index,
                "clip_index": clip_index,
                "name": clip_name
            })

            created_clips.append({
                "clip_index": clip_index,
                "label": label,
                "start_beat": start_beat,
                "end_beat": end_beat,
                "clip_name": clip_name,
                "note_count": len(notes)
            })

        # Step 6: Create cue points at section boundaries
        cue_points_created = 0
        if create_cue_points:
            for clip_data in clips_data:
                start_beat = clip_data['start_beat']
                try:
                    ableton.send_command("create_cue_point", {"time": start_beat})
                    cue_points_created += 1
                except Exception as e:
                    logger.warning(f"Failed to create cue point at {start_beat}: {e}")

        return json.dumps({
            "success": True,
            "audio_bpm": audio_bpm,
            "project_bpm": project_bpm,
            "bar1_offset_beat": bar1_offset_beat,
            "track_index": track_index,
            "track_name": track_name,
            "clips": created_clips,
            "total_clips": len(created_clips),
            "cue_points_created": cue_points_created,
        }, indent=2)

    except Exception as e:
        logger.error(f"Error creating structure track: {str(e)}")
        import traceback
        traceback.print_exc()
        return json.dumps({"error": str(e)})


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