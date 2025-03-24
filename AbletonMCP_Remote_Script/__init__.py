# AbletonMCP/init.py
from __future__ import absolute_import, print_function, unicode_literals

from _Framework.ControlSurface import ControlSurface
import socket
import json
import threading
import time
import traceback
import queue

# Constants for socket communication
DEFAULT_PORT = 9877
HOST = "localhost"

def create_instance(c_instance):
    """Create and return the AbletonMCP script instance"""
    return AbletonMCP(c_instance)

class AbletonMCP(ControlSurface):
    """AbletonMCP Remote Script for Ableton Live"""
    
    def __init__(self, c_instance):
        """Initialize the control surface"""
        ControlSurface.__init__(self, c_instance)
        self.log_message("AbletonMCP Remote Script initializing...")
        
        # Socket server for communication
        self.server = None
        self.client_threads = []
        self.server_thread = None
        self.running = False
        
        # Cache the song reference for easier access
        self._song = self.song()
        
        # Start the socket server
        self.start_server()
        
        self.log_message("AbletonMCP initialized")
        
        # Show a message in Ableton
        self.show_message("AbletonMCP: Listening for commands on port " + str(DEFAULT_PORT))
    
    def disconnect(self):
        """Called when Ableton closes or the control surface is removed"""
        self.log_message("AbletonMCP disconnecting...")
        self.running = False
        
        # Stop the server
        if self.server:
            try:
                self.server.close()
            except:
                pass
        
        # Wait for the server thread to exit
        if self.server_thread and self.server_thread.is_alive():
            self.server_thread.join(1.0)
            
        # Clean up any client threads
        for client_thread in self.client_threads[:]:
            if client_thread.is_alive():
                # We don't join them as they might be stuck
                self.log_message(f"Client thread still alive during disconnect")
        
        ControlSurface.disconnect(self)
        self.log_message("AbletonMCP disconnected")
    
    def start_server(self):
        """Start the socket server in a separate thread"""
        try:
            self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server.bind((HOST, DEFAULT_PORT))
            self.server.listen(5)  # Allow up to 5 pending connections
            
            self.running = True
            self.server_thread = threading.Thread(target=self._server_thread)
            self.server_thread.daemon = True
            self.server_thread.start()
            
            self.log_message("Server started on port " + str(DEFAULT_PORT))
        except Exception as e:
            self.log_message("Error starting server: " + str(e))
            self.show_message("AbletonMCP: Error starting server - " + str(e))
    
    def _server_thread(self):
        """Server thread implementation - handles client connections"""
        try:
            self.log_message("Server thread started")
            # Set a timeout to allow regular checking of running flag
            self.server.settimeout(1.0)
            
            while self.running:
                try:
                    # Accept connections with timeout
                    client, address = self.server.accept()
                    self.log_message("Connection accepted from " + str(address))
                    self.show_message("AbletonMCP: Client connected")
                    
                    # Handle client in a separate thread
                    client_thread = threading.Thread(
                        target=self._handle_client,
                        args=(client,)
                    )
                    client_thread.daemon = True
                    client_thread.start()
                    
                    # Keep track of client threads
                    self.client_threads.append(client_thread)
                    
                    # Clean up finished client threads
                    self.client_threads = [t for t in self.client_threads if t.is_alive()]
                    
                except socket.timeout:
                    # No connection yet, just continue
                    continue
                except Exception as e:
                    if self.running:  # Only log if still running
                        self.log_message("Server accept error: " + str(e))
                    time.sleep(0.5)
            
            self.log_message("Server thread stopped")
        except Exception as e:
            self.log_message("Server thread error: " + str(e))
    
    def _handle_client(self, client):
        """Handle communication with a connected client"""
        self.log_message("Client handler started")
        client.settimeout(None)  # No timeout for client socket
        buffer = b''
        
        try:
            while self.running:
                try:
                    # Receive data
                    data = client.recv(8192)
                    
                    if not data:
                        # Client disconnected
                        self.log_message("Client disconnected")
                        break
                    
                    # Accumulate data in buffer
                    buffer += data
                    
                    try:
                        # Try to parse command from buffer
                        command = json.loads(buffer.decode('utf-8'))
                        buffer = b''  # Clear buffer after successful parse
                        
                        self.log_message("Received command: " + str(command.get("type", "unknown")))
                        
                        # Process the command and get response
                        response = self._process_command(command)
                        
                        # Send the response
                        client.sendall(json.dumps(response).encode('utf-8'))
                    except json.JSONDecodeError:
                        # Incomplete data, wait for more
                        continue
                        
                except Exception as e:
                    self.log_message("Error handling client data: " + str(e))
                    self.log_message(traceback.format_exc())
                    
                    # Send error response if possible
                    error_response = {
                        "status": "error",
                        "message": str(e)
                    }
                    try:
                        client.sendall(json.dumps(error_response).encode('utf-8'))
                    except:
                        # If we can't send the error, the connection is probably dead
                        break
                    
                    # For serious errors, break the loop
                    if not isinstance(e, json.JSONDecodeError):
                        break
        except Exception as e:
            self.log_message("Error in client handler: " + str(e))
        finally:
            try:
                client.close()
            except:
                pass
            self.log_message("Client handler stopped")
    
    def _process_command(self, command):
        """Process a command from the client and return a response"""
        command_type = command.get("type", "")
        params = command.get("params", {})
        
        # Initialize response
        response = {
            "status": "success",
            "result": {}
        }
        
        try:
            # Route the command to the appropriate handler
            if command_type == "set_clip_properties":
                track_index = params.get("track_index", 0)
                clip_index = params.get("clip_index", 0)
                properties = params.get("properties", {})
                response["result"] = self.set_clip_properties(track_index, clip_index, properties)
            elif command_type == "set_device_parameters":
                track_index = params.get("track_index", 0)
                device_index = params.get("device_index", 0)
                parameters = params.get("parameters", {})
                response["result"] = self.set_device_parameters(track_index, device_index, parameters)
            elif command_type == "search_browser_items":
                query = params.get("query", "")
                category_type = params.get("category_type", "all")
                max_results = params.get("max_results", 50)
                response["result"] = self.search_browser_items(query, category_type, max_results)
            elif command_type == "get_session_info":
                response["result"] = self._get_session_info()
            elif command_type == "get_track_info":
                track_index = params.get("track_index", 0)
                response["result"] = self._get_track_info(track_index)
            elif command_type == "get_master_track_info":
                response["result"] = self._get_master_track_info()
            elif command_type in ["create_midi_track", "set_track_name", 
                                 "create_clip", "add_notes_to_clip", "set_clip_name", 
                                 "set_tempo", "fire_clip", "stop_clip",
                                 "start_playback", "stop_playback", "load_browser_item"]:
                # Use a thread-safe approach with a response queue
                response_queue = queue.Queue()
                
                # Define a function to execute on the main thread
                def main_thread_task():
                    try:
                        result = None
                        if command_type == "create_midi_track":
                            index = params.get("index", -1)
                            result = self._create_midi_track(index)
                        elif command_type == "set_track_name":
                            track_index = params.get("track_index", 0)
                            name = params.get("name", "")
                            result = self._set_track_name(track_index, name)
                        elif command_type == "create_clip":
                            track_index = params.get("track_index", 0)
                            clip_index = params.get("clip_index", 0)
                            length = params.get("length", 4.0)
                            result = self._create_clip(track_index, clip_index, length)
                        elif command_type == "add_notes_to_clip":
                            track_index = params.get("track_index", 0)
                            clip_index = params.get("clip_index", 0)
                            notes = params.get("notes", [])
                            result = self._add_notes_to_clip(track_index, clip_index, notes)
                        elif command_type == "set_clip_name":
                            track_index = params.get("track_index", 0)
                            clip_index = params.get("clip_index", 0)
                            name = params.get("name", "")
                            result = self._set_clip_name(track_index, clip_index, name)
                        elif command_type == "set_tempo":
                            tempo = params.get("tempo", 120.0)
                            result = self._set_tempo(tempo)
                        elif command_type == "fire_clip":
                            track_index = params.get("track_index", 0)
                            clip_index = params.get("clip_index", 0)
                            result = self._fire_clip(track_index, clip_index)
                        elif command_type == "stop_clip":
                            track_index = params.get("track_index", 0)
                            clip_index = params.get("clip_index", 0)
                            result = self._stop_clip(track_index, clip_index)
                        elif command_type == "start_playback":
                            result = self._start_playback()
                        elif command_type == "stop_playback":
                            result = self._stop_playback()
                        elif command_type == "load_instrument_or_effect":
                            track_index = params.get("track_index", 0)
                            uri = params.get("uri", "")
                            result = self._load_instrument_or_effect(track_index, uri)
                        elif command_type == "load_browser_item":
                            track_index = params.get("track_index", 0)
                            item_uri = params.get("item_uri", "")
                            result = self._load_browser_item(track_index, item_uri)
                        
                        # Put the result in the queue
                        response_queue.put({"status": "success", "result": result})
                    except Exception as e:
                        self.log_message("Error in main thread task: " + str(e))
                        self.log_message(traceback.format_exc())
                        response_queue.put({"status": "error", "message": str(e)})
                
                # Schedule the task to run on the main thread
                self.schedule_message(0, main_thread_task)
                
                # Wait for the response with a timeout
                try:
                    task_response = response_queue.get(timeout=10.0)
                    if task_response.get("status") == "error":
                        response["status"] = "error"
                        response["message"] = task_response.get("message", "Unknown error")
                    else:
                        response["result"] = task_response.get("result", {})
                except queue.Empty:
                    response["status"] = "error"
                    response["message"] = "Timeout waiting for operation to complete"
            elif command_type == "get_browser_item":
                uri = params.get("uri", None)
                path = params.get("path", None)
                response["result"] = self._get_browser_item(uri, path)
            elif command_type == "get_browser_categories":
                category_type = params.get("category_type", "all")
                response["result"] = self._get_browser_categories(category_type)
            elif command_type == "get_browser_items":
                path = params.get("path", "")
                item_type = params.get("item_type", "all")
                response["result"] = self._get_browser_items(path, item_type)
            # Add the new browser commands
            elif command_type == "get_browser_tree":
                category_type = params.get("category_type", "all")
                response["result"] = self.get_browser_tree(category_type)
            elif command_type == "get_browser_items_at_path":
                path = params.get("path", "")
                response["result"] = self.get_browser_items_at_path(path)
            elif command_type == "get_device_parameters":
                track_index = params.get("track_index", 0)
                device_index = params.get("device_index", 0)
                try:
                    result = self._get_device_parameters(track_index, device_index)
                    self.log_message(f"[GET_DEVICE_PARAMS] Got result from _get_device_parameters: {result}")
                    # Make sure we return a properly structured response
                    response = {
                        "status": "success",
                        "result": result
                    }
                    self.log_message(f"[GET_DEVICE_PARAMS] Returning response: {response}")
                    return response
                except Exception as e:
                    self.log_message(f"[GET_DEVICE_PARAMS] Error in get_device_parameters: {str(e)}")
                    self.log_message(traceback.format_exc())
                    response["status"] = "error"
                    response["message"] = str(e)
                    response["result"] = {
                        "device_name": "Error",
                        "parameters": []
                    }
            elif command_type == "set_device_parameter":
                track_index = params.get("track_index", 0)
                device_index = params.get("device_index", 0)
                parameter_name = params.get("parameter_name")
                value = params.get("value")
                if parameter_name is None or value is None:
                    response["status"] = "error"
                    response["message"] = "Missing parameter_name or value"
                else:
                    response["result"] = self._set_device_parameter(track_index, device_index, parameter_name, value)
            else:
                response["status"] = "error"
                response["message"] = "Unknown command: " + command_type
        except Exception as e:
            self.log_message("Error processing command: " + str(e))
            self.log_message(traceback.format_exc())
            response["status"] = "error"
            response["message"] = str(e)
        
        return response
    
    # Command implementations
    
    def _get_session_info(self):
        """Get information about the current session"""
        try:
            result = {
                "tempo": self._song.tempo,
                "signature_numerator": self._song.signature_numerator,
                "signature_denominator": self._song.signature_denominator,
                "track_count": len(self._song.tracks),
                "return_track_count": len(self._song.return_tracks),
                "master_track": {
                    "name": "Master",
                    "volume": self._song.master_track.mixer_device.volume.value,
                    "panning": self._song.master_track.mixer_device.panning.value
                }
            }
            return result
        except Exception as e:
            self.log_message("Error getting session info: " + str(e))
            raise
    
    def _get_track_info(self, track_index):
        """Get information about a track"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            
            track = self._song.tracks[track_index]
            
            # Get clip slots
            clip_slots = []
            for slot_index, slot in enumerate(track.clip_slots):
                clip_info = None
                if slot.has_clip:
                    clip = slot.clip
                    clip_info = {
                        "name": clip.name,
                        "length": clip.length,
                        "is_playing": clip.is_playing,
                        "is_recording": clip.is_recording
                    }
                
                clip_slots.append({
                    "index": slot_index,
                    "has_clip": slot.has_clip,
                    "clip": clip_info
                })
            
            # Get devices
            devices = []
            for device_index, device in enumerate(track.devices):
                devices.append({
                    "index": device_index,
                    "name": device.name,
                    "class_name": device.class_name,
                    "type": self._get_device_type(device)
                })
            
            result = {
                "index": track_index,
                "name": track.name,
                "is_audio_track": track.has_audio_input,
                "is_midi_track": track.has_midi_input,
                "mute": track.mute,
                "solo": track.solo,
                "arm": track.arm,
                "volume": track.mixer_device.volume.value,
                "panning": track.mixer_device.panning.value,
                "clip_slots": clip_slots,
                "devices": devices
            }
            return result
        except Exception as e:
            self.log_message("Error getting track info: " + str(e))
            raise
    
    def _get_master_track_info(self):
        """Get detailed information about the master track"""
        try:
            master = self._song.master_track
            
            # Get devices on master track
            devices = []
            for device_index, device in enumerate(master.devices):
                devices.append({
                    "index": device_index,
                    "name": device.name,
                    "class_name": device.class_name,
                    "type": self._get_device_type(device)
                })
            
            # Get clip slots if they exist
            clip_slots = []
            if hasattr(master, 'clip_slots'):
                for slot_index, slot in enumerate(master.clip_slots):
                    clip_info = None
                    if slot.has_clip:
                        clip = slot.clip
                        clip_info = {
                            "name": clip.name,
                            "length": clip.length,
                            "is_playing": clip.is_playing,
                            "is_recording": clip.is_recording
                        }
                    
                    clip_slots.append({
                        "index": slot_index,
                        "has_clip": slot.has_clip,
                        "clip": clip_info
                    })
            
            result = {
                "name": "Master",
                "volume": master.mixer_device.volume.value,
                "panning": master.mixer_device.panning.value,
                "devices": devices,
                "clip_slots": clip_slots,
                "is_master_track": True
            }
            return result
        except Exception as e:
            self.log_message("Error getting master track info: " + str(e))
            raise
    
    def _create_midi_track(self, index):
        """Create a new MIDI track at the specified index"""
        try:
            # Create the track
            self._song.create_midi_track(index)
            
            # Get the new track
            new_track_index = len(self._song.tracks) - 1 if index == -1 else index
            new_track = self._song.tracks[new_track_index]
            
            result = {
                "index": new_track_index,
                "name": new_track.name
            }
            return result
        except Exception as e:
            self.log_message("Error creating MIDI track: " + str(e))
            raise
    
    
    def _set_track_name(self, track_index, name):
        """Set the name of a track"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            
            # Set the name
            track = self._song.tracks[track_index]
            track.name = name
            
            result = {
                "name": track.name
            }
            return result
        except Exception as e:
            self.log_message("Error setting track name: " + str(e))
            raise
    
    def _create_clip(self, track_index, clip_index, length):
        """Create a new MIDI clip in the specified track and clip slot"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            
            track = self._song.tracks[track_index]
            
            if clip_index < 0 or clip_index >= len(track.clip_slots):
                raise IndexError("Clip index out of range")
            
            clip_slot = track.clip_slots[clip_index]
            
            # Check if the clip slot already has a clip
            if clip_slot.has_clip:
                raise Exception("Clip slot already has a clip")
            
            # Create the clip
            clip_slot.create_clip(length)
            
            result = {
                "name": clip_slot.clip.name,
                "length": clip_slot.clip.length
            }
            return result
        except Exception as e:
            self.log_message("Error creating clip: " + str(e))
            raise
    
    def _add_notes_to_clip(self, track_index, clip_index, notes):
        """Add MIDI notes to a clip"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            
            track = self._song.tracks[track_index]
            
            if clip_index < 0 or clip_index >= len(track.clip_slots):
                raise IndexError("Clip index out of range")
            
            clip_slot = track.clip_slots[clip_index]
            
            if not clip_slot.has_clip:
                raise Exception("No clip in slot")
            
            clip = clip_slot.clip
            
            # Convert note data to Live's format
            live_notes = []
            for note in notes:
                pitch = note.get("pitch", 60)
                start_time = note.get("start_time", 0.0)
                duration = note.get("duration", 0.25)
                velocity = note.get("velocity", 100)
                mute = note.get("mute", False)
                
                live_notes.append((pitch, start_time, duration, velocity, mute))
            
            # Add the notes
            clip.set_notes(tuple(live_notes))
            
            result = {
                "note_count": len(notes)
            }
            return result
        except Exception as e:
            self.log_message("Error adding notes to clip: " + str(e))
            raise
    
    def _set_clip_name(self, track_index, clip_index, name):
        """Set the name of a clip"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            
            track = self._song.tracks[track_index]
            
            if clip_index < 0 or clip_index >= len(track.clip_slots):
                raise IndexError("Clip index out of range")
            
            clip_slot = track.clip_slots[clip_index]
            
            if not clip_slot.has_clip:
                raise Exception("No clip in slot")
            
            clip = clip_slot.clip
            clip.name = name
            
            result = {
                "name": clip.name
            }
            return result
        except Exception as e:
            self.log_message("Error setting clip name: " + str(e))
            raise
    
    def _set_tempo(self, tempo):
        """Set the tempo of the session"""
        try:
            self._song.tempo = tempo
            
            result = {
                "tempo": self._song.tempo
            }
            return result
        except Exception as e:
            self.log_message("Error setting tempo: " + str(e))
            raise
    
    def _fire_clip(self, track_index, clip_index):
        """Fire a clip"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            
            track = self._song.tracks[track_index]
            
            if clip_index < 0 or clip_index >= len(track.clip_slots):
                raise IndexError("Clip index out of range")
            
            clip_slot = track.clip_slots[clip_index]
            
            if not clip_slot.has_clip:
                raise Exception("No clip in slot")
            
            clip_slot.fire()
            
            result = {
                "fired": True
            }
            return result
        except Exception as e:
            self.log_message("Error firing clip: " + str(e))
            raise
    
    def _stop_clip(self, track_index, clip_index):
        """Stop a clip"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            
            track = self._song.tracks[track_index]
            
            if clip_index < 0 or clip_index >= len(track.clip_slots):
                raise IndexError("Clip index out of range")
            
            clip_slot = track.clip_slots[clip_index]
            
            clip_slot.stop()
            
            result = {
                "stopped": True
            }
            return result
        except Exception as e:
            self.log_message("Error stopping clip: " + str(e))
            raise
    
    
    def _start_playback(self):
        """Start playing the session"""
        try:
            self._song.start_playing()
            
            result = {
                "playing": self._song.is_playing
            }
            return result
        except Exception as e:
            self.log_message("Error starting playback: " + str(e))
            raise
    
    def _stop_playback(self):
        """Stop playing the session"""
        try:
            self._song.stop_playing()
            
            result = {
                "playing": self._song.is_playing
            }
            return result
        except Exception as e:
            self.log_message("Error stopping playback: " + str(e))
            raise
    
    def _get_browser_item(self, uri, path):
        """Get a browser item by URI or path"""
        try:
            # Access the application's browser instance instead of creating a new one
            app = self.application()
            if not app:
                raise RuntimeError("Could not access Live application")
                
            result = {
                "uri": uri,
                "path": path,
                "found": False
            }
            
            # Try to find by URI first if provided
            if uri:
                item = self._find_browser_item_by_uri(app.browser, uri)
                if item:
                    result["found"] = True
                    result["item"] = {
                        "name": item.name,
                        "is_folder": item.is_folder,
                        "is_device": item.is_device,
                        "is_loadable": item.is_loadable,
                        "uri": item.uri
                    }
                    return result
            
            # If URI not provided or not found, try by path
            if path:
                # Parse the path and navigate to the specified item
                path_parts = path.split("/")
                
                # Determine the root based on the first part
                current_item = None
                if path_parts[0].lower() == "nstruments":
                    current_item = app.browser.instruments
                elif path_parts[0].lower() == "sounds":
                    current_item = app.browser.sounds
                elif path_parts[0].lower() == "drums":
                    current_item = app.browser.drums
                elif path_parts[0].lower() == "audio_effects":
                    current_item = app.browser.audio_effects
                elif path_parts[0].lower() == "midi_effects":
                    current_item = app.browser.midi_effects
                else:
                    # Default to instruments if not specified
                    current_item = app.browser.instruments
                    # Don't skip the first part in this case
                    path_parts = ["instruments"] + path_parts
                
                # Navigate through the path
                for i in range(1, len(path_parts)):
                    part = path_parts[i]
                    if not part:  # Skip empty parts
                        continue
                    
                    found = False
                    for child in current_item.children:
                        if child.name.lower() == part.lower():
                            current_item = child
                            found = True
                            break
                    
                    if not found:
                        result["error"] = f"Path part '{part}' not found"
                        return result
                
                # Found the item
                result["found"] = True
                result["item"] = {
                    "name": current_item.name,
                    "is_folder": current_item.is_folder,
                    "is_device": current_item.is_device,
                    "is_loadable": current_item.is_loadable,
                    "uri": current_item.uri
                }
            
            return result
        except Exception as e:
            self.log_message("Error getting browser item: " + str(e))
            self.log_message(traceback.format_exc())
            raise   
    
    
    
    def _load_browser_item(self, track_index, item_uri):
        """Load a browser item onto a track by its URI"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            
            track = self._song.tracks[track_index]
            
            # Access the application's browser instance instead of creating a new one
            app = self.application()
            
            # Find the browser item by URI
            item = self._find_browser_item_by_uri(app.browser, item_uri)
            
            if not item:
                raise ValueError(f"Browser item with URI '{item_uri}' not found")
            
            # Select the track
            self._song.view.selected_track = track
            
            # Load the item
            app.browser.load_item(item)
            
            result = {
                "loaded": True,
                "item_name": item.name,
                "track_name": track.name,
                "uri": item_uri
            }
            return result
        except Exception as e:
            self.log_message(f"Error loading browser item: {str(e)}")
            self.log_message(traceback.format_exc())
            raise
    
    def _find_browser_item_by_uri(self, browser_or_item, uri, max_depth=10, current_depth=0):
        """Find a browser item by its URI"""
        try:
            # Check if this is the item we're looking for
            if hasattr(browser_or_item, 'uri') and browser_or_item.uri == uri:
                return browser_or_item
            
            # Stop recursion if we've reached max depth
            if current_depth >= max_depth:
                return None
            
            # Check if this is a browser with root categories
            if hasattr(browser_or_item, 'instruments'):
                # Check all main categories
                categories = [
                    browser_or_item.instruments,
                    browser_or_item.sounds,
                    browser_or_item.drums,
                    browser_or_item.audio_effects,
                    browser_or_item.midi_effects
                ]
                
                for category in categories:
                    item = self._find_browser_item_by_uri(category, uri, max_depth, current_depth + 1)
                    if item:
                        return item
                
                return None
            
            # Check if this item has children
            if hasattr(browser_or_item, 'children') and browser_or_item.children:
                for child in browser_or_item.children:
                    item = self._find_browser_item_by_uri(child, uri, max_depth, current_depth + 1)
                    if item:
                        return item
            
            return None
        except Exception as e:
            self.log_message(f"Error finding browser item by URI: {str(e)}")
            return None
    
    # Helper methods
    
    def _get_device_type(self, device):
        """Get the type of a device"""
        try:
            # Simple heuristic - in a real implementation you'd look at the device class
            if device.can_have_drum_pads:
                return "drum_machine"
            elif device.can_have_chains:
                return "rack"
            elif "instrument" in device.class_display_name.lower():
                return "instrument"
            elif "audio_effect" in device.class_name.lower():
                return "audio_effect"
            elif "midi_effect" in device.class_name.lower():
                return "midi_effect"
            else:
                return "unknown"
        except:
            return "unknown"
    
    def get_browser_tree(self, category_type="all"):
        """
        Get a simplified tree of browser categories.
        
        Args:
            category_type: Type of categories to get ('all', 'instruments', 'sounds', etc.)
            
        Returns:
            Dictionary with the browser tree structure
        """
        try:
            # Access the application's browser instance instead of creating a new one
            app = self.application()
            if not app:
                raise RuntimeError("Could not access Live application")
                
            # Check if browser is available
            if not hasattr(app, 'browser') or app.browser is None:
                raise RuntimeError("Browser is not available in the Live application")
            
            # Log available browser attributes to help diagnose issues
            browser_attrs = [attr for attr in dir(app.browser) if not attr.startswith('_')]
            self.log_message(f"Available browser attributes: {browser_attrs}")
            
            result = {
                "type": category_type,
                "categories": [],
                "available_categories": browser_attrs
            }
            
            # Helper function to process a browser item and its children
            def process_item(item, depth=0):
                if not item:
                    return None
                
                result = {
                    "name": item.name if hasattr(item, 'name') else "Unknown",
                    "is_folder": hasattr(item, 'children') and bool(item.children),
                    "is_device": hasattr(item, 'is_device') and item.is_device,
                    "is_loadable": hasattr(item, 'is_loadable') and item.is_loadable,
                    "uri": item.uri if hasattr(item, 'uri') else None,
                    "children": []
                }
                
                
                return result
            
            # Process based on category type and available attributes
            if (category_type == "all" or category_type == "instruments") and hasattr(app.browser, 'instruments'):
                try:
                    instruments = process_item(app.browser.instruments)
                    if instruments:
                        instruments["name"] = "Instruments"  # Ensure consistent naming
                        result["categories"].append(instruments)
                except Exception as e:
                    self.log_message(f"Error processing instruments: {str(e)}")
            
            if (category_type == "all" or category_type == "sounds") and hasattr(app.browser, 'sounds'):
                try:
                    sounds = process_item(app.browser.sounds)
                    if sounds:
                        sounds["name"] = "Sounds"  # Ensure consistent naming
                        result["categories"].append(sounds)
                except Exception as e:
                    self.log_message(f"Error processing sounds: {str(e)}")
            
            if (category_type == "all" or category_type == "drums") and hasattr(app.browser, 'drums'):
                try:
                    drums = process_item(app.browser.drums)
                    if drums:
                        drums["name"] = "Drums"  # Ensure consistent naming
                        result["categories"].append(drums)
                except Exception as e:
                    self.log_message(f"Error processing drums: {str(e)}")
            
            if (category_type == "all" or category_type == "audio_effects") and hasattr(app.browser, 'audio_effects'):
                try:
                    audio_effects = process_item(app.browser.audio_effects)
                    if audio_effects:
                        audio_effects["name"] = "Audio Effects"  # Ensure consistent naming
                        result["categories"].append(audio_effects)
                except Exception as e:
                    self.log_message(f"Error processing audio_effects: {str(e)}")
            
            if (category_type == "all" or category_type == "midi_effects") and hasattr(app.browser, 'midi_effects'):
                try:
                    midi_effects = process_item(app.browser.midi_effects)
                    if midi_effects:
                        midi_effects["name"] = "MIDI Effects"  # Ensure consistent naming
                        result["categories"].append(midi_effects)
                except Exception as e:
                    self.log_message(f"Error processing midi_effects: {str(e)}")
            
            # Try to process other potentially available categories
            for attr in browser_attrs:
                if attr not in ['instruments', 'sounds', 'drums', 'audio_effects', 'midi_effects'] and \
                   (category_type == "all" or category_type == attr):
                    try:
                        item = getattr(app.browser, attr)
                        if hasattr(item, 'children') or hasattr(item, 'name'):
                            category = process_item(item)
                            if category:
                                category["name"] = attr.capitalize()  # Use attribute name as category name
                                result["categories"].append(category)
                    except Exception as e:
                        self.log_message(f"Error processing {attr}: {str(e)}")
            
            self.log_message(f"Browser tree generated for {category_type} with {len(result['categories'])} root categories")
            return result
            
        except Exception as e:
            self.log_message(f"Error getting browser tree: {str(e)}")
            self.log_message(traceback.format_exc())
            raise
    
    def get_browser_items_at_path(self, path):
        """
        Get browser items at a specific path.
        
        Args:
            path: Path in the format "category/folder/subfolder"
                 where category is one of: instruments, sounds, drums, audio_effects, midi_effects
                 or any other available browser category
                 
        Returns:
            Dictionary with items at the specified path
        """
        try:
            # Access the application's browser instance instead of creating a new one
            app = self.application()
            if not app:
                raise RuntimeError("Could not access Live application")
                
            # Check if browser is available
            if not hasattr(app, 'browser') or app.browser is None:
                raise RuntimeError("Browser is not available in the Live application")
            
            # Log available browser attributes to help diagnose issues
            browser_attrs = [attr for attr in dir(app.browser) if not attr.startswith('_')]
            self.log_message(f"Available browser attributes: {browser_attrs}")
                
            # Parse the path
            path_parts = path.split("/")
            if not path_parts:
                raise ValueError("Invalid path")
            
            # Determine the root category
            root_category = path_parts[0].lower()
            current_item = None
            
            # Check standard categories first
            if root_category == "instruments" and hasattr(app.browser, 'instruments'):
                current_item = app.browser.instruments
            elif root_category == "sounds" and hasattr(app.browser, 'sounds'):
                current_item = app.browser.sounds
            elif root_category == "drums" and hasattr(app.browser, 'drums'):
                current_item = app.browser.drums
            elif root_category == "audio_effects" and hasattr(app.browser, 'audio_effects'):
                current_item = app.browser.audio_effects
            elif root_category == "midi_effects" and hasattr(app.browser, 'midi_effects'):
                current_item = app.browser.midi_effects
            else:
                # Try to find the category in other browser attributes
                found = False
                for attr in browser_attrs:
                    if attr.lower() == root_category:
                        try:
                            current_item = getattr(app.browser, attr)
                            found = True
                            break
                        except Exception as e:
                            self.log_message(f"Error accessing browser attribute {attr}: {str(e)}")
                
                if not found:
                    # If we still haven't found the category, return available categories
                    return {
                        "path": path,
                        "error": f"Unknown or unavailable category: {root_category}",
                        "available_categories": browser_attrs,
                        "items": []
                    }
            
            # Navigate through the path
            for i in range(1, len(path_parts)):
                part = path_parts[i]
                if not part:  # Skip empty parts
                    continue
                
                if not hasattr(current_item, 'children'):
                    return {
                        "path": path,
                        "error": f"Item at '{'/'.join(path_parts[:i])}' has no children",
                        "items": []
                    }
                
                found = False
                for child in current_item.children:
                    if hasattr(child, 'name') and child.name.lower() == part.lower():
                        current_item = child
                        found = True
                        break
                
                if not found:
                    return {
                        "path": path,
                        "error": f"Path part '{part}' not found",
                        "items": []
                    }
            
            # Get items at the current path
            items = []
            if hasattr(current_item, 'children'):
                for child in current_item.children:
                    item_info = {
                        "name": child.name if hasattr(child, 'name') else "Unknown",
                        "is_folder": hasattr(child, 'children') and bool(child.children),
                        "is_device": hasattr(child, 'is_device') and child.is_device,
                        "is_loadable": hasattr(child, 'is_loadable') and child.is_loadable,
                        "uri": child.uri if hasattr(child, 'uri') else None
                    }
                    items.append(item_info)
            
            result = {
                "path": path,
                "name": current_item.name if hasattr(current_item, 'name') else "Unknown",
                "uri": current_item.uri if hasattr(current_item, 'uri') else None,
                "is_folder": hasattr(current_item, 'children') and bool(current_item.children),
                "is_device": hasattr(current_item, 'is_device') and current_item.is_device,
                "is_loadable": hasattr(current_item, 'is_loadable') and current_item.is_loadable,
                "items": items
            }
            
            self.log_message(f"Retrieved {len(items)} items at path: {path}")
            return result
            
        except Exception as e:
            self.log_message(f"Error getting browser items at path: {str(e)}")
            self.log_message(traceback.format_exc())
            raise

    def _get_device_parameters(self, track_index, device_index):
        """Get all parameters for a device on a track"""
        try:
            self.log_message(f"[GET_DEVICE_PARAMS] Starting for device {device_index} on track {track_index}")
            
            # Special handling for master track
            if track_index == -1:
                track = self._song.master_track
                self.log_message(f"[GET_DEVICE_PARAMS] Using master track")
            else:
                if track_index < 0 or track_index >= len(self._song.tracks):
                    error_msg = f"Track index {track_index} out of range"
                    self.log_message(f"[GET_DEVICE_PARAMS] Error: {error_msg}")
                    raise IndexError(error_msg)
                track = self._song.tracks[track_index]
            
            self.log_message(f"[GET_DEVICE_PARAMS] Found track: {track.name}")
            
            if device_index < 0 or device_index >= len(track.devices):
                error_msg = f"Device index {device_index} out of range. Track has {len(track.devices)} devices"
                self.log_message(f"[GET_DEVICE_PARAMS] Error: {error_msg}")
                raise IndexError(error_msg)
            
            device = track.devices[device_index]
            self.log_message(f"[GET_DEVICE_PARAMS] Found device: {device.name} (class: {device.class_name})")
            
            parameters = []
            self.log_message(f"[GET_DEVICE_PARAMS] Getting parameters for device {device.name}")
            
            for param in device.parameters:
                self.log_message(f"[GET_DEVICE_PARAMS] Processing parameter: {param.name}")
                param_info = {
                    "name": param.name,
                    "value": param.value,
                    "min": param.min,
                    "max": param.max,
                    "is_enabled": param.is_enabled,
                    "is_automated": param.automation_state > 0
                }
                parameters.append(param_info)
                self.log_message(f"[GET_DEVICE_PARAMS] Parameter info: {param_info}")
            
            result = {
                "device_name": device.name,
                "parameters": parameters
            }
            
            # Log the complete result before returning
            self.log_message(f"[GET_DEVICE_PARAMS] Complete result: {result}")
            return result
        except Exception as e:
            self.log_message(f"[GET_DEVICE_PARAMS] Error: {str(e)}")
            self.log_message(f"[GET_DEVICE_PARAMS] Traceback: {traceback.format_exc()}")
            raise

    def _set_device_parameter(self, track_index, device_index, parameter_name, value):
        """Set a device parameter value"""
        try:
            self.log_message(f"Setting parameter {parameter_name} to {value} for device {device_index} on track {track_index}")
            
            # Special handling for master track
            if track_index == -1:
                track = self._song.master_track
                self.log_message(f"Using master track")
            else:
                if track_index < 0 or track_index >= len(self._song.tracks):
                    self.log_message(f"Track index {track_index} out of range")
                    raise IndexError("Track index out of range")
                track = self._song.tracks[track_index]
            
            if device_index < 0 or device_index >= len(track.devices):
                self.log_message(f"Device index {device_index} out of range. Track has {len(track.devices)} devices")
                raise IndexError("Device index out of range")
            
            device = track.devices[device_index]
            self.log_message(f"Found device: {device.name} (class: {device.class_name})")
            
            # Find parameter by name
            target_param = None
            self.log_message(f"Searching for parameter: {parameter_name}")
            for param in device.parameters:
                self.log_message(f"Checking parameter: {param.name}")
                if param.name == parameter_name:
                    target_param = param
                    self.log_message(f"Found matching parameter: {param.name}")
                    break
            
            if not target_param:
                self.log_message(f"Parameter {parameter_name} not found in device {device.name}")
                raise ValueError(f"Parameter {parameter_name} not found")
            
            # Ensure value is within bounds
            value = float(value)
            original_value = value
            value = max(min(value, target_param.max), target_param.min)
            if value != original_value:
                self.log_message(f"Value {original_value} clamped to {value} (min: {target_param.min}, max: {target_param.max})")
            
            # Set the parameter value
            target_param.value = value
            self.log_message(f"Parameter value set successfully")
            
            result = {
                "device_name": device.name,
                "parameter_name": parameter_name,
                "value": value
            }
            self.log_message(f"Returning result: {result}")
            return result
        except Exception as e:
            self.log_message(f"Error setting device parameter: {str(e)}")
            self.log_message(traceback.format_exc())
            raise

    def set_clip_properties(self, track_index, clip_index, properties):
        """Set multiple properties of a clip at once.
        
        Args:
            track_index: Index of the track
            clip_index: Index of the clip slot
            properties: Dictionary of properties to set
        """
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            
            track = self._song.tracks[track_index]
            
            if clip_index < 0 or clip_index >= len(track.clip_slots):
                raise IndexError("Clip index out of range")
            
            clip_slot = track.clip_slots[clip_index]
            
            if not clip_slot.has_clip:
                raise Exception("No clip in slot")
            
            clip = clip_slot.clip
            result = {"name": clip.name}
            
            # Handle each property
            for prop, value in properties.items():
                if prop == "name":
                    clip.name = str(value)
                    result["name"] = clip.name
                elif prop == "color":
                    clip.color = int(value)
                    result["color"] = clip.color
                elif prop == "warping":
                    clip.warping = bool(value)
                    result["warping"] = clip.warping
                elif prop == "gain":
                    clip.gain = float(value)
                    result["gain"] = clip.gain
                elif prop == "pitch_coarse":
                    clip.pitch_coarse = int(value)
                    result["pitch_coarse"] = clip.pitch_coarse
                elif prop == "pitch_fine":
                    clip.pitch_fine = float(value)
                    result["pitch_fine"] = clip.pitch_fine
                elif prop == "looping":
                    clip.looping = bool(value)
                    result["looping"] = clip.looping
                elif prop == "loop_start":
                    clip.loop_start = float(value)
                    result["loop_start"] = clip.loop_start
                elif prop == "loop_end":
                    clip.loop_end = float(value)
                    result["loop_end"] = clip.loop_end
                elif prop == "start_marker":
                    clip.start_marker = float(value)
                    result["start_marker"] = clip.start_marker
                elif prop == "end_marker":
                    clip.end_marker = float(value)
                    result["end_marker"] = clip.end_marker
                elif prop == "signature_numerator":
                    clip.signature_numerator = int(value)
                    result["signature_numerator"] = clip.signature_numerator
                elif prop == "signature_denominator":
                    clip.signature_denominator = int(value)
                    result["signature_denominator"] = clip.signature_denominator
            
            return result
            
        except Exception as e:
            self.log_message(f"Error setting clip properties: {str(e)}")
            raise

    def set_device_parameters(self, track_index, device_index, parameters):
        """Set multiple parameters of a device at once.
        
        Args:
            track_index: Index of the track (-1 for master track)
            device_index: Index of the device
            parameters: Dictionary of parameter names and values
        """
        try:
            # Special handling for master track
            if track_index == -1:
                track = self._song.master_track
                self.log_message(f"Using master track")
            else:
                if track_index < 0 or track_index >= len(self._song.tracks):
                    self.log_message(f"Track index {track_index} out of range")
                    raise IndexError("Track index out of range")
                track = self._song.tracks[track_index]
            
            if device_index < 0 or device_index >= len(track.devices):
                self.log_message(f"Device index {device_index} out of range")
                raise IndexError("Device index out of range")
            
            device = track.devices[device_index]
            self.log_message(f"Found device: {device.name}")
            
            result = {
                "device_name": device.name,
                "parameters": {}
            }
            
            # Create parameter name lookup for faster access
            param_lookup = {param.name: param for param in device.parameters}
            
            # Set each parameter
            for param_name, value in parameters.items():
                if param_name not in param_lookup:
                    self.log_message(f"Parameter {param_name} not found")
                    continue
                    
                param = param_lookup[param_name]
                
                # Ensure value is within bounds
                value = float(value)
                original_value = value
                value = max(min(value, param.max), param.min)
                
                if value != original_value:
                    self.log_message(f"Value {original_value} clamped to {value} for {param_name}")
                
                # Set the parameter value
                param.value = value
                
                # Store the result
                result["parameters"][param_name] = {
                    "value": value,
                    "min": param.min,
                    "max": param.max
                }
            
            return result
            
        except Exception as e:
            self.log_message(f"Error setting device parameters: {str(e)}")
            self.log_message(traceback.format_exc())
            raise

    def search_browser_items(self, query, category_type="all", max_results=50):
        """Search for browser items matching a query string.
        
        Args:
            query: Search string to match against item names
            category_type: Type of categories to search ("all", "instruments", "sounds", "drums", "audio_effects", "midi_effects")
            max_results: Maximum number of results to return
        """
        try:
            self.log_message(f"Searching for '{query}' in {category_type} (max: {max_results})")
            
            # Access the application's browser instance
            app = self.application()
            if not app:
                raise RuntimeError("Could not access Live application")
                
            # Check if browser is available
            if not hasattr(app, 'browser') or app.browser is None:
                raise RuntimeError("Browser is not available in the Live application")
            
            # Get all items to search through based on category_type
            items_to_search = []
            
            def collect_items(item, depth=0, max_depth=5):
                if depth >= max_depth:
                    return
                    
                if hasattr(item, 'children'):
                    for child in item.children:
                        items_to_search.append(child)
                        collect_items(child, depth + 1, max_depth)
            
            # Determine which categories to search
            categories = []
            if category_type == "all" or category_type == "instruments":
                if hasattr(app.browser, 'instruments'):
                    categories.append(app.browser.instruments)
            if category_type == "all" or category_type == "sounds":
                if hasattr(app.browser, 'sounds'):
                    categories.append(app.browser.sounds)
            if category_type == "all" or category_type == "drums":
                if hasattr(app.browser, 'drums'):
                    categories.append(app.browser.drums)
            if category_type == "all" or category_type == "audio_effects":
                if hasattr(app.browser, 'audio_effects'):
                    categories.append(app.browser.audio_effects)
            if category_type == "all" or category_type == "midi_effects":
                if hasattr(app.browser, 'midi_effects'):
                    categories.append(app.browser.midi_effects)
            
            # Collect all items from selected categories
            for category in categories:
                collect_items(category)
            
            # Search through collected items
            query = query.lower()
            matching_items = []
            
            for item in items_to_search:
                if len(matching_items) >= max_results:
                    break
                    
                try:
                    if hasattr(item, 'name') and query in item.name.lower():
                        item_info = {
                            "name": item.name,
                            "path": self._get_item_path(item),
                            "is_loadable": hasattr(item, 'is_loadable') and item.is_loadable,
                            "is_device": hasattr(item, 'is_device') and item.is_device,
                            "uri": item.uri if hasattr(item, 'uri') else None
                        }
                        matching_items.append(item_info)
                except Exception as e:
                    self.log_message(f"Error processing item: {str(e)}")
                    continue
            
            result = {
                "total_results": len(matching_items),
                "results": matching_items[:max_results]
            }
            
            self.log_message(f"Found {len(matching_items)} matches for '{query}'")
            return result
            
        except Exception as e:
            self.log_message(f"Error searching browser items: {str(e)}")
            self.log_message(traceback.format_exc())
            raise

    def _get_item_path(self, item):
        """Get the full path of a browser item"""
        try:
            path_parts = []
            current = item
            
            # Walk up the parent chain
            while hasattr(current, 'name') and hasattr(current, 'parent') and current.parent:
                path_parts.insert(0, current.name)
                current = current.parent
            
            # Add root category name
            if hasattr(current, 'name'):
                path_parts.insert(0, current.name)
            
            return '/'.join(path_parts)
        except Exception as e:
            self.log_message(f"Error getting item path: {str(e)}")
            return "Unknown Path"