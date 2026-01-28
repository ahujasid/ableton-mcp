# ableton_mcp_server.py
from mcp.server.fastmcp import FastMCP, Context
import socket
import json
import logging
from dataclasses import dataclass
from contextlib import asynccontextmanager
from typing import AsyncIterator, Dict, Any, List, Union, Optional

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
            "set_tempo", "fire_clip", "stop_clip", "start_playback", "stop_playback",
            "load_browser_item", "load_drum_kit", "set_device_parameter",
            "set_eq_band", "set_eq_global", "apply_eq_preset", "create_return_track",
            "set_send_level", "set_track_volume"
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
        result = ableton.send_command("get_session_info", {})
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
def create_return_track(ctx: Context) -> str:
    """
    Create a new return track in the Ableton session.
    
    Return tracks are used for send effects and are added to the end of the return track list.
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("create_return_track", {})
        return f"Created new return track: {result.get('name', 'unknown')}"
    except Exception as e:
        logger.error(f"Error creating return track: {str(e)}")
        return f"Error creating return track: {str(e)}"

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

@mcp.tool()
def get_device_parameters(ctx: Context, track_index: int, device_index: int) -> Dict[str, Any]:
    """
    Get all parameters for a device.
    
    Parameters:
    - track_index: The index of the track containing the device
    - device_index: The index of the device on the track
    
    Returns:
    - Dictionary with device information and parameters
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_device_parameters", {
            "track_index": track_index,
            "device_index": device_index
        })
        
        return result
    except Exception as e:
        logger.error(f"Error getting device parameters: {str(e)}")
        return {"error": f"Error getting device parameters: {str(e)}"}

@mcp.tool()
def set_device_parameter(ctx: Context, track_index: int, device_index: int, 
                         parameter_name: Optional[str] = None, 
                         parameter_index: Optional[int] = None, 
                         value: Optional[Union[float, int, str]] = None) -> str:
    """
    Set a device parameter by name or index.
    
    Parameters:
    - track_index: The index of the track containing the device
    - device_index: The index of the device on the track
    - parameter_name: The name of the parameter to set (alternative to parameter_index)
    - parameter_index: The index of the parameter to set (alternative to parameter_name)
    - value: The value to set the parameter to
    
    Returns:
    - String with the result of the operation
    """
    try:
        if parameter_name is None and parameter_index is None:
            return "Error: Either parameter_name or parameter_index must be provided"
        
        if value is None:
            return "Error: Value must be provided"
        
        ableton = get_ableton_connection()
        result = ableton.send_command("set_device_parameter", {
            "track_index": track_index,
            "device_index": device_index,
            "parameter_name": parameter_name,
            "parameter_index": parameter_index,
            "value": value
        })
        
        if "parameter_name" in result:
            return f"Set parameter '{result['parameter_name']}' of device '{result['device_name']}' to {result['value']}"
        else:
            return f"Failed to set parameter: {result.get('message', 'Unknown error')}"
    except Exception as e:
        logger.error(f"Error setting device parameter: {str(e)}")
        return f"Error setting device parameter: {str(e)}"

@mcp.tool()
def set_eq_band(ctx: Context, track_index: int, device_index: int, band_index: int,
                frequency: Optional[float] = None, gain: Optional[float] = None,
                q: Optional[float] = None, filter_type: Optional[Union[int, str]] = None) -> str:
    """
    Set parameters for a specific band in an EQ Eight device.
    
    Parameters:
    - track_index: The index of the track containing the EQ Eight
    - device_index: The index of the EQ Eight device on the track
    - band_index: The index of the band to modify (0-7)
    - frequency: The frequency value to set (Hz)
    - gain: The gain value to set (dB)
    - q: The Q factor to set
    - filter_type: The filter type to set (either index or name)
    
    Returns:
    - String with the result of the operation
    """
    try:
        ableton = get_ableton_connection()
        
        # First, verify that this is an EQ Eight device
        device_info = ableton.send_command("get_device_parameters", {
            "track_index": track_index,
            "device_index": device_index
        })
        
        if "device_name" not in device_info or "EQ Eight" not in device_info["device_name"]:
            return f"Error: Device at index {device_index} is not an EQ Eight device"
        
        # EQ Eight has 8 bands (0-7)
        if band_index < 0 or band_index > 7:
            return f"Error: Band index must be between 0 and 7"
        
        # Convert band_index (0-7) to the actual band number (1-8)
        band_number = band_index + 1
        
        # Set parameters as requested
        results = []
        
        # Set frequency if provided
        if frequency is not None:
            # Convert frequency to normalized value (0-1)
            if frequency < 20:
                frequency = 20  # Minimum frequency
            if frequency > 20000:
                frequency = 20000  # Maximum frequency
            
            # Convert to logarithmic scale (approximation)
            import math
            log_min = math.log10(20)  # 20 Hz
            log_max = math.log10(20000)  # 20 kHz
            log_freq = math.log10(frequency)
            normalized_value = (log_freq - log_min) / (log_max - log_min)
            
            freq_param_name = f"{band_number} Frequency A"
            freq_result = ableton.send_command("set_device_parameter", {
                "track_index": track_index,
                "device_index": device_index,
                "parameter_name": freq_param_name,
                "value": normalized_value
            })
            results.append(f"Set {freq_param_name} to {frequency} Hz")
        
        # Set gain if provided
        if gain is not None:
            gain_param_name = f"{band_number} Gain A"
            gain_result = ableton.send_command("set_device_parameter", {
                "track_index": track_index,
                "device_index": device_index,
                "parameter_name": gain_param_name,
                "value": gain
            })
            results.append(f"Set {gain_param_name} to {gain} dB")
        
        # Set Q if provided
        if q is not None:
            # Convert Q value to normalized value (0-1)
            normalized_q = q / 10.0  # Assuming max Q is around 10
            if normalized_q > 1.0:
                normalized_q = 1.0
                
            q_param_name = f"{band_number} Resonance A"
            q_result = ableton.send_command("set_device_parameter", {
                "track_index": track_index,
                "device_index": device_index,
                "parameter_name": q_param_name,
                "value": normalized_q
            })
            results.append(f"Set {q_param_name} to {q}")
        
        # Set filter type if provided
        if filter_type is not None:
            filter_param_name = f"{band_number} Filter Type A"
            filter_result = ableton.send_command("set_device_parameter", {
                "track_index": track_index,
                "device_index": device_index,
                "parameter_name": filter_param_name,
                "value": filter_type
            })
            results.append(f"Set {filter_param_name} to {filter_type}")
        
        if not results:
            return "No parameters were set"
        
        return "\n".join(results)
    except Exception as e:
        logger.error(f"Error setting EQ band parameters: {str(e)}")
        return f"Error setting EQ band parameters: {str(e)}"

@mcp.tool()
def set_eq_global(ctx: Context, track_index: int, device_index: int,
                 scale: Optional[float] = None, mode: Optional[Union[int, str]] = None,
                 oversampling: Optional[bool] = None) -> str:
    """
    Set global parameters for an EQ Eight device.
    
    Parameters:
    - track_index: The index of the track containing the EQ Eight
    - device_index: The index of the EQ Eight device on the track
    - scale: The scale value to set (0.5 = 50%, 1.0 = 100%, 2.0 = 200%, etc.)
    - mode: The mode to set (either index or name: "Stereo" or "L/R" or "M/S")
    - oversampling: Whether to enable oversampling (true/false)
    
    Returns:
    - String with the result of the operation
    """
    try:
        ableton = get_ableton_connection()
        
        # First, verify that this is an EQ Eight device
        device_info = ableton.send_command("get_device_parameters", {
            "track_index": track_index,
            "device_index": device_index
        })
        
        if "device_name" not in device_info or "EQ Eight" not in device_info["device_name"]:
            return f"Error: Device at index {device_index} is not an EQ Eight device"
        
        # Set parameters as requested
        results = []
        
        # Set scale if provided
        if scale is not None:
            scale_result = ableton.send_command("set_device_parameter", {
                "track_index": track_index,
                "device_index": device_index,
                "parameter_name": "Scale",
                "value": scale
            })
            results.append(f"Set Scale to {scale}")
        
        # Set mode if provided - Note: EQ Eight doesn't seem to have a "Mode" parameter
        # We'll check if there's a parameter with "Mode" in its name
        if mode is not None:
            # Get all parameters to find one that might be the mode
            all_params = device_info.get("parameters", [])
            mode_param = None
            
            for param in all_params:
                if "Mode" in param.get("name", ""):
                    mode_param = param
                    break
            
            if mode_param:
                mode_result = ableton.send_command("set_device_parameter", {
                    "track_index": track_index,
                    "device_index": device_index,
                    "parameter_name": mode_param["name"],
                    "value": mode
                })
                results.append(f"Set {mode_param['name']} to {mode}")
            else:
                results.append(f"Warning: Could not find a Mode parameter in EQ Eight")
        
        # Set oversampling if provided - Note: EQ Eight doesn't seem to have an "Oversampling" parameter
        # We'll check if there's a parameter with "Oversampling" or "Hi Quality" in its name
        if oversampling is not None:
            # Get all parameters to find one that might be oversampling
            all_params = device_info.get("parameters", [])
            oversampling_param = None
            
            for param in all_params:
                param_name = param.get("name", "")
                if "Oversampling" in param_name or "Hi Quality" in param_name:
                    oversampling_param = param
                    break
            
            if oversampling_param:
                # Convert boolean to 0 or 1
                oversampling_value = 1 if oversampling else 0
                oversampling_result = ableton.send_command("set_device_parameter", {
                    "track_index": track_index,
                    "device_index": device_index,
                    "parameter_name": oversampling_param["name"],
                    "value": oversampling_value
                })
                results.append(f"Set {oversampling_param['name']} to {'enabled' if oversampling else 'disabled'}")
            else:
                results.append(f"Warning: Could not find an Oversampling parameter in EQ Eight")
        
        if not results:
            return "No parameters were set"
        
        return "\n".join(results)
    except Exception as e:
        logger.error(f"Error setting EQ global parameters: {str(e)}")
        return f"Error setting EQ global parameters: {str(e)}"

@mcp.tool()
def apply_eq_preset(ctx: Context, track_index: int, device_index: int, preset_type: str) -> str:
    """
    Apply a preset to an EQ Eight device.
    
    Parameters:
    - track_index: The index of the track containing the EQ Eight
    - device_index: The index of the EQ Eight device on the track
    - preset_type: The type of preset to apply ("low_cut", "high_cut", "low_shelf", "high_shelf", "bell", "notch", "flat")
    
    Returns:
    - String with the result of the operation
    """
    try:
        ableton = get_ableton_connection()
        
        # First, verify that this is an EQ Eight device
        device_info = ableton.send_command("get_device_parameters", {
            "track_index": track_index,
            "device_index": device_index
        })
        
        if "device_name" not in device_info or "EQ Eight" not in device_info["device_name"]:
            return f"Error: Device at index {device_index} is not an EQ Eight device"
        
        # Define presets
        presets = {
            "low_cut": {
                0: {"enabled": True, "freq": 80, "gain": 0, "q": 0.7, "type": "High Pass 48dB"}
            },
            "high_cut": {
                7: {"enabled": True, "freq": 10000, "gain": 0, "q": 0.7, "type": "Low Pass 48dB"}
            },
            "low_shelf": {
                0: {"enabled": True, "freq": 100, "gain": -3, "q": 0.7, "type": "Low Shelf"}
            },
            "high_shelf": {
                7: {"enabled": True, "freq": 8000, "gain": -3, "q": 0.7, "type": "High Shelf"}
            },
            "bell": {
                3: {"enabled": True, "freq": 1000, "gain": 0, "q": 1.0, "type": "Bell"}
            },
            "notch": {
                3: {"enabled": True, "freq": 1000, "gain": -12, "q": 8.0, "type": "Notch"}
            },
            "flat": {
                # Reset all bands to default values
                0: {"enabled": False},
                1: {"enabled": False},
                2: {"enabled": False},
                3: {"enabled": False},
                4: {"enabled": False},
                5: {"enabled": False},
                6: {"enabled": False},
                7: {"enabled": False}
            }
        }
        
        if preset_type not in presets:
            return f"Error: Unknown preset type '{preset_type}'. Available presets: {', '.join(presets.keys())}"
        
        preset = presets[preset_type]
        results = []
        
        # Apply preset settings
        for band_index, settings in preset.items():
            # Convert band_index (0-7) to the actual band number (1-8)
            band_number = band_index + 1
            
            # Enable/disable the band
            if "enabled" in settings:
                enable_param_name = f"{band_number} Filter On A"
                enable_value = 1 if settings["enabled"] else 0
                enable_result = ableton.send_command("set_device_parameter", {
                    "track_index": track_index,
                    "device_index": device_index,
                    "parameter_name": enable_param_name,
                    "value": enable_value
                })
                results.append(f"Set {enable_param_name} to {'enabled' if settings['enabled'] else 'disabled'}")
            
            # Only set other parameters if the band is enabled
            if settings.get("enabled", False):
                # Set frequency if provided
                if "freq" in settings:
                    # Convert frequency to normalized value (0-1)
                    frequency = settings["freq"]
                    if frequency < 20:
                        frequency = 20  # Minimum frequency
                    if frequency > 20000:
                        frequency = 20000  # Maximum frequency
                    
                    # Convert to logarithmic scale (approximation)
                    import math
                    log_min = math.log10(20)  # 20 Hz
                    log_max = math.log10(20000)  # 20 kHz
                    log_freq = math.log10(frequency)
                    normalized_value = (log_freq - log_min) / (log_max - log_min)
                    
                    freq_param_name = f"{band_number} Frequency A"
                    freq_result = ableton.send_command("set_device_parameter", {
                        "track_index": track_index,
                        "device_index": device_index,
                        "parameter_name": freq_param_name,
                        "value": normalized_value
                    })
                    results.append(f"Set {freq_param_name} to {frequency} Hz")
                
                # Set gain if provided
                if "gain" in settings:
                    gain_param_name = f"{band_number} Gain A"
                    gain_result = ableton.send_command("set_device_parameter", {
                        "track_index": track_index,
                        "device_index": device_index,
                        "parameter_name": gain_param_name,
                        "value": settings["gain"]
                    })
                    results.append(f"Set {gain_param_name} to {settings['gain']} dB")
                
                # Set Q if provided
                if "q" in settings:
                    # Convert Q value to normalized value (0-1)
                    normalized_q = settings["q"] / 10.0  # Assuming max Q is around 10
                    if normalized_q > 1.0:
                        normalized_q = 1.0
                        
                    q_param_name = f"{band_number} Resonance A"
                    q_result = ableton.send_command("set_device_parameter", {
                        "track_index": track_index,
                        "device_index": device_index,
                        "parameter_name": q_param_name,
                        "value": normalized_q
                    })
                    results.append(f"Set {q_param_name} to {settings['q']}")
                
                # Set filter type if provided
                if "type" in settings:
                    filter_param_name = f"{band_number} Filter Type A"
                    filter_result = ableton.send_command("set_device_parameter", {
                        "track_index": track_index,
                        "device_index": device_index,
                        "parameter_name": filter_param_name,
                        "value": settings["type"]
                    })
                    results.append(f"Set {filter_param_name} to {settings['type']}")
        
        return f"Applied '{preset_type}' preset to EQ Eight"
    except Exception as e:
        logger.error(f"Error applying EQ preset: {str(e)}")
        return f"Error applying EQ preset: {str(e)}"

@mcp.tool()
def set_send_level(ctx: Context, track_index: int, send_index: int, value: float) -> str:
    """
    Set the level of a send from a track to a return track.
    
    Parameters:
    - track_index: The index of the track containing the send
    - send_index: The index of the send (corresponds to the return track index)
    - value: The value to set the send level to (0.0 to 1.0)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_send_level", {
            "track_index": track_index, 
            "send_index": send_index, 
            "value": value
        })
        return f"Set send level from track {result.get('track_name', 'unknown')} to {result.get('return_track_name', 'unknown')} to {result.get('value', value)}"
    except Exception as e:
        logger.error(f"Error setting send level: {str(e)}")
        return f"Error setting send level: {str(e)}"

@mcp.tool()
def set_track_volume(ctx: Context, track_index: int, value: float) -> str:
    """
    Set the volume of a track.
    
    Parameters:
    - track_index: The index of the track to set the volume for
    - value: The volume value (0.0 to 1.0)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_track_volume", {
            "track_index": track_index, 
            "value": value
        })
        
        volume_db = result.get('volume_db', 'unknown')
        if volume_db == float('-inf'):
            volume_db_str = "-∞ dB"
        else:
            volume_db_str = f"{volume_db:.1f} dB"
            
        return f"Set volume of track {result.get('track_name', 'unknown')} to {volume_db_str}"
    except Exception as e:
        logger.error(f"Error setting track volume: {str(e)}")
        return f"Error setting track volume: {str(e)}"

# Main execution
def main():
    """Run the MCP server"""
    import os
    
    # Get host and port from environment variables (set by CLI)
    host = os.environ.get("MCP_HOST", "127.0.0.1")
    port = int(os.environ.get("MCP_PORT", "8000"))
    
    # Start the server
    mcp.serve(host=host, port=port)

if __name__ == "__main__":
    main()