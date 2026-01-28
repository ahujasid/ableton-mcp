# AbletonMCP/init.py
from __future__ import absolute_import, print_function, unicode_literals

from _Framework.ControlSurface import ControlSurface
import socket
import json
import threading
import time
import traceback
import math

# Change queue import for Python 2
try:
    import Queue as queue  # Python 2
except ImportError:
    import queue  # Python 3

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
                self.log_message("Client thread still alive during disconnect")
        
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
        buffer = ''  # Changed from b'' to '' for Python 2
        
        try:
            while self.running:
                try:
                    # Receive data
                    data = client.recv(8192)
                    
                    if not data:
                        # Client disconnected
                        self.log_message("Client disconnected")
                        break
                    
                    # Accumulate data in buffer with explicit encoding/decoding
                    try:
                        # Python 3: data is bytes, decode to string
                        buffer += data.decode('utf-8')
                    except AttributeError:
                        # Python 2: data is already string
                        buffer += data
                    
                    try:
                        # Try to parse command from buffer
                        command = json.loads(buffer)  # Removed decode('utf-8')
                        buffer = ''  # Clear buffer after successful parse
                        
                        self.log_message("Received command: " + str(command.get("type", "unknown")))
                        
                        # Process the command and get response
                        response = self._process_command(command)
                        
                        # Send the response with explicit encoding
                        try:
                            # Python 3: encode string to bytes
                            client.sendall(json.dumps(response).encode('utf-8'))
                        except AttributeError:
                            # Python 2: string is already bytes
                            client.sendall(json.dumps(response))
                    except ValueError:
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
                        # Python 3: encode string to bytes
                        client.sendall(json.dumps(error_response).encode('utf-8'))
                    except AttributeError:
                        # Python 2: string is already bytes
                        client.sendall(json.dumps(error_response))
                    except:
                        # If we can't send the error, the connection is probably dead
                        break
                    
                    # For serious errors, break the loop
                    if not isinstance(e, ValueError):
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
            if command_type == "get_session_info":
                response["result"] = self._get_session_info()
            elif command_type == "get_track_info":
                track_index = params.get("track_index", 0)
                response["result"] = self._get_track_info(track_index)
            # Commands that modify Live's state should be scheduled on the main thread
            elif command_type in ["create_midi_track", "set_track_name", 
                                 "create_clip", "add_notes_to_clip", "set_clip_name", 
                                 "set_tempo", "fire_clip", "stop_clip",
                                 "start_playback", "stop_playback", "load_browser_item", "create_return_track", "set_send_level", "set_track_volume"]:
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
                        elif command_type == "load_browser_item":
                            track_index = params.get("track_index", 0)
                            item_uri = params.get("item_uri", "")
                            result = self._load_browser_item(track_index, item_uri)
                        elif command_type == "create_return_track":
                            result = self._create_return_track()
                        elif command_type == "set_send_level":
                            track_index = params.get("track_index", 0)
                            send_index = params.get("send_index", 0)
                            value = params.get("value", 0.0)
                            result = self._set_send_level(track_index, send_index, value)
                        elif command_type == "set_track_volume":
                            track_index = params.get("track_index", 0)
                            value = params.get("value", 0.0)
                            result = self._set_track_volume(track_index, value)
                        
                        # Put the result in the queue
                        response_queue.put({"status": "success", "result": result})
                    except Exception as e:
                        self.log_message("Error in main thread task: " + str(e))
                        self.log_message(traceback.format_exc())
                        response_queue.put({"status": "error", "message": str(e)})
                
                # Schedule the task to run on the main thread
                try:
                    self.schedule_message(0, main_thread_task)
                except AssertionError:
                    # If we're already on the main thread, execute directly
                    main_thread_task()
                
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
                response["result"] = self._get_device_parameters(track_index, device_index)
            elif command_type == "set_device_parameter":
                track_index = params.get("track_index", 0)
                device_index = params.get("device_index", 0)
                parameter_name = params.get("parameter_name", None)
                parameter_index = params.get("parameter_index", None)
                value = params.get("value", None)
                response["result"] = self._set_device_parameter(track_index, device_index, parameter_name, parameter_index, value)
            elif command_type == "set_eq_band":
                track_index = params.get("track_index", 0)
                device_index = params.get("device_index", 0)
                band_index = params.get("band_index", 0)
                frequency = params.get("frequency", None)
                gain = params.get("gain", None)
                q = params.get("q", None)
                filter_type = params.get("filter_type", None)
                response["result"] = self._set_eq_band(track_index, device_index, band_index, frequency, gain, q, filter_type)
            elif command_type == "set_eq_global":
                track_index = params.get("track_index", 0)
                device_index = params.get("device_index", 0)
                scale = params.get("scale", None)
                mode = params.get("mode", None)
                oversampling = params.get("oversampling", None)
                response["result"] = self._set_eq_global(track_index, device_index, scale, mode, oversampling)
            elif command_type == "apply_eq_preset":
                track_index = params.get("track_index", 0)
                device_index = params.get("device_index", 0)
                preset_type = params.get("preset_type", "")
                response["result"] = self._apply_eq_preset(track_index, device_index, preset_type)
            elif command_type == "set_track_volume":
                track_index = params.get("track_index", 0)
                value = params.get("value", 0.0)
                response["result"] = self._set_track_volume(track_index, value)
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
            track = self._get_track_by_index(track_index)
            
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
                        "is_recording": clip.is_recording,
                        "color": clip.color
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
            
            # Determine if this is a return track
            is_return_track = track_index >= len(self._song.tracks)
            
            # Create base track info
            track_info = {
                "index": track_index,
                "name": track.name,
                "is_audio_track": track.has_audio_input,
                "is_midi_track": track.has_midi_input,
                "mute": track.mute,
                "solo": track.solo,
                "volume": track.mixer_device.volume.value,
                "panning": track.mixer_device.panning.value,
                "clip_slots": clip_slots,
                "devices": devices,
                "is_return_track": is_return_track
            }
            
            # Add arm property only for regular tracks (not return tracks)
            if not is_return_track:
                track_info["arm"] = track.arm
                
            return track_info
        except Exception as e:
            self.log_message("Error getting track info: " + str(e))
            self.log_message(traceback.format_exc())
            raise
    
    def _get_track_by_index(self, track_index):
        """Get a track by its index"""
        if track_index < 0:
            raise IndexError("Track index out of range")
        
        # Check if this is a regular track
        if track_index < len(self._song.tracks):
            return self._song.tracks[track_index]
        
        # Check if this is a return track
        return_track_index = track_index - len(self._song.tracks)
        if return_track_index < len(self._song.return_tracks):
            return self._song.return_tracks[return_track_index]
        
        # If we get here, the index is out of range
        raise IndexError("Track index out of range")
    
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
    
    def _create_return_track(self):
        """Create a new return track"""
        try:
            # Create the return track
            self._song.create_return_track()
            
            # Get the new return track
            new_return_track_index = len(self._song.return_tracks) - 1
            new_return_track = self._song.return_tracks[new_return_track_index]
            
            result = {
                "index": new_return_track_index,
                "name": new_return_track.name
            }
            return result
        except Exception as e:
            self.log_message("Error creating return track: " + str(e))
            raise
    
    def _set_track_name(self, track_index, name):
        """Set the name of a track"""
        try:
            # Get the track using the helper function that handles return tracks
            track = self._get_track_by_index(track_index)
            
            # Set the name
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
            # Get the track using the helper function that handles return tracks
            track = self._get_track_by_index(track_index)
            
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
            # Get the track using the helper function that handles return tracks
            track = self._get_track_by_index(track_index)
            
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
            # Get the track using the helper function that handles return tracks
            track = self._get_track_by_index(track_index)
            
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
            # Get the track using the helper function that handles return tracks
            track = self._get_track_by_index(track_index)
            
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
            # Get the track using the helper function that handles return tracks
            track = self._get_track_by_index(track_index)
            
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
                        result["error"] = "Path part '{0}' not found".format(part)
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
            # Get the track using the helper function that handles return tracks
            track = self._get_track_by_index(track_index)
            
            # Access the application's browser instance instead of creating a new one
            app = self.application()
            
            # Find the browser item by URI
            item = self._find_browser_item_by_uri(app.browser, item_uri)
            
            if not item:
                raise ValueError("Browser item with URI '{0}' not found".format(item_uri))
            
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
            self.log_message("Error loading browser item: {0}".format(str(e)))
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
            self.log_message("Error finding browser item by URI: {0}".format(str(e)))
            return None
    
    # Helper methods
    
    def _get_device_type(self, device):
        """Get the type of a device"""
        if device.class_name == "PluginDevice":
            return "plugin"
        elif device.class_name == "InstrumentGroupDevice":
            return "instrument_rack"
        elif device.class_name == "DrumGroupDevice":
            return "drum_rack"
        elif device.can_have_drum_pads:
            return "drum_device"
        elif device.can_have_chains:
            return "rack"
        else:
            return "device"
    
    def _get_device_parameters(self, track_index, device_index):
        """Get all parameters for a device"""
        try:
            # Get the track using the helper function that handles return tracks
            track = self._get_track_by_index(track_index)
            
            if device_index < 0 or device_index >= len(track.devices):
                raise IndexError("Device index out of range")
            
            device = track.devices[device_index]
            
            # Get all parameters for the device
            parameters = []
            for param_index, param in enumerate(device.parameters):
                # Skip parameters that are not automatable or are just for display
                if not param.is_enabled or param.is_quantized and len(param.value_items) <= 1:
                    continue
                
                param_info = {
                    "index": param_index,
                    "name": param.name,
                    "value": param.value,
                    "min": param.min,
                    "max": param.max,
                }
                
                # Add value items for quantized parameters (e.g., filter types)
                if param.is_quantized and len(param.value_items) > 1:
                    param_info["value_items"] = [str(item) for item in param.value_items]
                    param_info["value_item_index"] = int(param.value)
                    param_info["value_item"] = str(param.value_items[int(param.value)])
                
                parameters.append(param_info)
            
            return {
                "device_name": device.name,
                "device_class": device.class_name,
                "device_type": self._get_device_type(device),
                "parameters": parameters
            }
        except Exception as e:
            self.log_message("Error getting device parameters: " + str(e))
            self.log_message(traceback.format_exc())
            raise
    
    def _set_device_parameter(self, track_index, device_index, parameter_name=None, parameter_index=None, value=None):
        """Set a device parameter by name or index"""
        try:
            # Get the track using the helper function that handles return tracks
            track = self._get_track_by_index(track_index)
            
            if device_index < 0 or device_index >= len(track.devices):
                raise IndexError("Device index out of range")
            
            device = track.devices[device_index]
            
            # Find the parameter by name or index
            parameter = None
            if parameter_name is not None:
                # Find parameter by name
                for param in device.parameters:
                    if param.name == parameter_name:
                        parameter = param
                        break
                
                if parameter is None:
                    raise ValueError(f"Parameter '{parameter_name}' not found in device '{device.name}'")
            
            elif parameter_index is not None:
                # Find parameter by index
                if parameter_index < 0 or parameter_index >= len(device.parameters):
                    raise IndexError("Parameter index out of range")
                
                parameter = device.parameters[parameter_index]
            
            else:
                raise ValueError("Either parameter_name or parameter_index must be provided")
            
            # Check if the parameter is enabled
            if not parameter.is_enabled:
                raise ValueError(f"Parameter '{parameter.name}' is not enabled")
            
            # Set the parameter value
            if value is None:
                raise ValueError("Value must be provided")
            
            # Handle quantized parameters (e.g., filter types)
            if parameter.is_quantized and len(parameter.value_items) > 1:
                # If value is a string, find the matching value item
                if isinstance(value, str):
                    value_index = None
                    for i, item in enumerate(parameter.value_items):
                        if str(item).lower() == value.lower():
                            value_index = i
                            break
                    
                    if value_index is None:
                        raise ValueError(f"Value '{value}' not found in parameter value items")
                    
                    value = value_index
                
                # Ensure value is an integer for quantized parameters
                value = int(value)
                
                # Check if value is in range
                if value < 0 or value >= len(parameter.value_items):
                    raise ValueError(f"Value index {value} out of range for parameter '{parameter.name}'")
            else:
                # For continuous parameters, ensure value is within range
                if value < parameter.min or value > parameter.max:
                    raise ValueError(f"Value {value} out of range for parameter '{parameter.name}' (min: {parameter.min}, max: {parameter.max})")
            
            # Set the parameter value
            parameter.value = value
            
            return {
                "device_name": device.name,
                "parameter_name": parameter.name,
                "parameter_index": list(device.parameters).index(parameter),
                "value": parameter.value,
                "min": parameter.min,
                "max": parameter.max
            }
        except Exception as e:
            self.log_message("Error setting device parameter: " + str(e))
            self.log_message(traceback.format_exc())
            raise
    
    def _set_eq_band(self, track_index, device_index, band_index, frequency=None, gain=None, q=None, filter_type=None):
        """Set parameters for a specific band in an EQ Eight device"""
        try:
            # Get the track and device
            track = self._get_track_by_index(track_index)
            
            if device_index < 0 or device_index >= len(track.devices):
                raise IndexError("Device index out of range")
            
            device = track.devices[device_index]
            
            # Verify this is an EQ Eight device
            if "EQ Eight" not in device.name:
                raise ValueError(f"Device at index {device_index} is not an EQ Eight device")
            
            # EQ Eight has 8 bands (0-7)
            if band_index < 0 or band_index > 7:
                raise ValueError("Band index must be between 0 and 7")
            
            # Convert band_index (0-7) to the actual band number (1-8)
            band_number = band_index + 1
            
            # Set parameters as requested
            results = {}
            
            # Set frequency if provided
            if frequency is not None:
                freq_param_name = f"{band_number} Frequency A"
                freq_param = None
                
                # Find the frequency parameter
                for param in device.parameters:
                    if param.name == freq_param_name:
                        freq_param = param
                        break
                
                if freq_param is None:
                    raise ValueError(f"Parameter '{freq_param_name}' not found")
                
                # Convert frequency value (Hz) to normalized value (0-1)
                # This is a rough approximation, as the actual mapping is logarithmic
                # For more precise control, we would need to implement the exact mapping function
                # that Ableton uses, but this should work for basic functionality
                if frequency < 20:
                    frequency = 20  # Minimum frequency
                if frequency > 20000:
                    frequency = 20000  # Maximum frequency
                
                # Convert to logarithmic scale (approximation)
                log_min = math.log10(20)  # 20 Hz
                log_max = math.log10(20000)  # 20 kHz
                log_freq = math.log10(frequency)
                normalized_value = (log_freq - log_min) / (log_max - log_min)
                
                freq_param.value = normalized_value
                results["frequency"] = frequency
            
            # Set gain if provided
            if gain is not None:
                gain_param_name = f"{band_number} Gain A"
                gain_param = None
                
                # Find the gain parameter
                for param in device.parameters:
                    if param.name == gain_param_name:
                        gain_param = param
                        break
                
                if gain_param is None:
                    raise ValueError(f"Parameter '{gain_param_name}' not found")
                
                gain_param.value = gain
                results["gain"] = gain
            
            # Set Q if provided
            if q is not None:
                q_param_name = f"{band_number} Resonance A"
                q_param = None
                
                # Find the Q parameter
                for param in device.parameters:
                    if param.name == q_param_name:
                        q_param = param
                        break
                
                if q_param is None:
                    raise ValueError(f"Parameter '{q_param_name}' not found")
                
                # Convert Q value to normalized value (0-1)
                # This is a rough approximation
                normalized_q = q / 10.0  # Assuming max Q is around 10
                if normalized_q > 1.0:
                    normalized_q = 1.0
                
                q_param.value = normalized_q
                results["q"] = q
            
            # Set filter type if provided
            if filter_type is not None:
                filter_param_name = f"{band_number} Filter Type A"
                filter_param = None
                
                # Find the filter type parameter
                for param in device.parameters:
                    if param.name == filter_param_name:
                        filter_param = param
                        break
                
                if filter_param is None:
                    raise ValueError(f"Parameter '{filter_param_name}' not found")
                
                # Handle filter type as string or index
                if isinstance(filter_type, str):
                    # Find the matching filter type
                    filter_index = None
                    for i, item in enumerate(filter_param.value_items):
                        if str(item).lower() == filter_type.lower():
                            filter_index = i
                            break
                    
                    if filter_index is None:
                        raise ValueError(f"Filter type '{filter_type}' not found")
                    
                    filter_param.value = filter_index
                    results["filter_type"] = str(filter_param.value_items[filter_index])
                else:
                    # Assume filter_type is an index
                    if filter_type < 0 or filter_type >= len(filter_param.value_items):
                        raise ValueError(f"Filter type index {filter_type} out of range")
                    
                    filter_param.value = filter_type
                    results["filter_type"] = str(filter_param.value_items[filter_type])
            
            return {
                "band_index": band_index,
                "parameters": results
            }
        except Exception as e:
            self.log_message("Error setting EQ band parameters: " + str(e))
            self.log_message(traceback.format_exc())
            raise
    
    def _set_eq_global(self, track_index, device_index, scale=None, mode=None, oversampling=None):
        """Set global parameters for an EQ Eight device"""
        try:
            # Get the track and device
            track = self._get_track_by_index(track_index)
            
            if device_index < 0 or device_index >= len(track.devices):
                raise IndexError("Device index out of range")
            
            device = track.devices[device_index]
            
            # Verify this is an EQ Eight device
            if "EQ Eight" not in device.name:
                raise ValueError(f"Device at index {device_index} is not an EQ Eight device")
            
            # Set parameters as requested
            results = {}
            
            # Set scale if provided
            if scale is not None:
                scale_param = None
                
                # Find the scale parameter
                for param in device.parameters:
                    if param.name == "Scale":
                        scale_param = param
                        break
                
                if scale_param is None:
                    raise ValueError("Scale parameter not found")
                
                scale_param.value = scale
                results["scale"] = scale
            
            # Set mode if provided - Note: EQ Eight doesn't seem to have a "Mode" parameter
            # We'll leave this in but it will likely fail
            if mode is not None:
                # Check if there's any parameter that might be the mode
                mode_param = None
                
                # Try to find a parameter that might be the mode
                for param in device.parameters:
                    if "Mode" in param.name:
                        mode_param = param
                        break
                
                if mode_param is None:
                    raise ValueError("Mode parameter not found")
                
                # Handle mode as string or index
                if isinstance(mode, str):
                    # Find the matching mode
                    mode_index = None
                    for i, item in enumerate(mode_param.value_items):
                        if str(item).lower() == mode.lower():
                            mode_index = i
                            break
                    
                    if mode_index is None:
                        raise ValueError(f"Mode '{mode}' not found")
                    
                    mode_param.value = mode_index
                    results["mode"] = str(mode_param.value_items[mode_index])
                else:
                    # Assume mode is an index
                    if mode < 0 or mode >= len(mode_param.value_items):
                        raise ValueError(f"Mode index {mode} out of range")
                    
                    mode_param.value = mode
                    results["mode"] = str(mode_param.value_items[mode])
            
            # Set oversampling if provided - Note: EQ Eight doesn't seem to have an "Oversampling" parameter
            # We'll leave this in but it will likely fail
            if oversampling is not None:
                # Try to find a parameter that might be oversampling
                oversampling_param = None
                
                for param in device.parameters:
                    if "Oversampling" in param.name or "Hi Quality" in param.name:
                        oversampling_param = param
                        break
                
                if oversampling_param is None:
                    raise ValueError("Oversampling parameter not found")
                
                # Convert boolean to 0 or 1
                oversampling_value = 1 if oversampling else 0
                oversampling_param.value = oversampling_value
                results["oversampling"] = bool(oversampling)
            
            return {
                "global_parameters": results
            }
        except Exception as e:
            self.log_message("Error setting EQ global parameters: " + str(e))
            self.log_message(traceback.format_exc())
            raise
    
    def _apply_eq_preset(self, track_index, device_index, preset_type):
        """Apply a preset to an EQ Eight device"""
        try:
            # Get the track and device
            track = self._get_track_by_index(track_index)
            
            if device_index < 0 or device_index >= len(track.devices):
                raise IndexError("Device index out of range")
            
            device = track.devices[device_index]
            
            # Verify this is an EQ Eight device
            if "EQ Eight" not in device.name:
                raise ValueError(f"Device at index {device_index} is not an EQ Eight device")
            
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
                raise ValueError(f"Unknown preset type '{preset_type}'. Available presets: {', '.join(presets.keys())}")
            
            preset = presets[preset_type]
            applied_settings = {}
            
            # Apply preset settings
            for band_index, settings in preset.items():
                band_settings = {}
                band_number = band_index + 1  # Convert to 1-based index for parameter names
                
                # Enable/disable the band
                if "enabled" in settings:
                    enable_param_name = f"{band_number} Filter On A"
                    enable_param = None
                    
                    # Find the enable parameter
                    for param in device.parameters:
                        if param.name == enable_param_name:
                            enable_param = param
                            break
                    
                    if enable_param is None:
                        raise ValueError(f"Parameter '{enable_param_name}' not found")
                    
                    enable_value = 1 if settings["enabled"] else 0
                    enable_param.value = enable_value
                    band_settings["enabled"] = settings["enabled"]
                
                # Only set other parameters if the band is enabled
                if settings.get("enabled", False):
                    # Set frequency if provided
                    if "freq" in settings:
                        freq_param_name = f"{band_number} Frequency A"
                        freq_param = None
                        
                        # Find the frequency parameter
                        for param in device.parameters:
                            if param.name == freq_param_name:
                                freq_param = param
                                break
                        
                        if freq_param is None:
                            raise ValueError(f"Parameter '{freq_param_name}' not found")
                        
                        # Convert frequency to normalized value (0-1)
                        frequency = settings["freq"]
                        if frequency < 20:
                            frequency = 20  # Minimum frequency
                        if frequency > 20000:
                            frequency = 20000  # Maximum frequency
                        
                        # Convert to logarithmic scale (approximation)
                        log_min = math.log10(20)  # 20 Hz
                        log_max = math.log10(20000)  # 20 kHz
                        log_freq = math.log10(frequency)
                        normalized_value = (log_freq - log_min) / (log_max - log_min)
                        
                        freq_param.value = normalized_value
                        band_settings["freq"] = frequency
                    
                    # Set gain if provided
                    if "gain" in settings:
                        gain_param_name = f"{band_number} Gain A"
                        gain_param = None
                        
                        # Find the gain parameter
                        for param in device.parameters:
                            if param.name == gain_param_name:
                                gain_param = param
                                break
                        
                        if gain_param is None:
                            raise ValueError(f"Parameter '{gain_param_name}' not found")
                        
                        gain_param.value = settings["gain"]
                        band_settings["gain"] = settings["gain"]
                    
                    # Set Q if provided
                    if "q" in settings:
                        q_param_name = f"{band_number} Resonance A"
                        q_param = None
                        
                        # Find the Q parameter
                        for param in device.parameters:
                            if param.name == q_param_name:
                                q_param = param
                                break
                        
                        if q_param is None:
                            raise ValueError(f"Parameter '{q_param_name}' not found")
                        
                        # Convert Q value to normalized value (0-1)
                        normalized_q = settings["q"] / 10.0  # Assuming max Q is around 10
                        if normalized_q > 1.0:
                            normalized_q = 1.0
                        
                        q_param.value = normalized_q
                        band_settings["q"] = settings["q"]
                    
                    # Set filter type if provided
                    if "type" in settings:
                        filter_param_name = f"{band_number} Filter Type A"
                        filter_param = None
                        
                        # Find the filter type parameter
                        for param in device.parameters:
                            if param.name == filter_param_name:
                                filter_param = param
                                break
                        
                        if filter_param is None:
                            raise ValueError(f"Parameter '{filter_param_name}' not found")
                        
                        # Handle filter type as string
                        filter_type = settings["type"]
                        filter_index = None
                        for i, item in enumerate(filter_param.value_items):
                            if str(item).lower() == filter_type.lower():
                                filter_index = i
                                break
                        
                        if filter_index is None:
                            raise ValueError(f"Filter type '{filter_type}' not found")
                        
                        filter_param.value = filter_index
                        band_settings["type"] = str(filter_param.value_items[filter_index])
                
                if band_settings:
                    applied_settings[f"band_{band_index}"] = band_settings
            
            return {
                "preset_type": preset_type,
                "applied_settings": applied_settings
            }
        except Exception as e:
            self.log_message("Error applying EQ preset: " + str(e))
            self.log_message(traceback.format_exc())
            raise
    
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
            self.log_message("Available browser attributes: {0}".format(browser_attrs))
            
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
                    self.log_message("Error processing instruments: {0}".format(str(e)))
            
            if (category_type == "all" or category_type == "sounds") and hasattr(app.browser, 'sounds'):
                try:
                    sounds = process_item(app.browser.sounds)
                    if sounds:
                        sounds["name"] = "Sounds"  # Ensure consistent naming
                        result["categories"].append(sounds)
                except Exception as e:
                    self.log_message("Error processing sounds: {0}".format(str(e)))
            
            if (category_type == "all" or category_type == "drums") and hasattr(app.browser, 'drums'):
                try:
                    drums = process_item(app.browser.drums)
                    if drums:
                        drums["name"] = "Drums"  # Ensure consistent naming
                        result["categories"].append(drums)
                except Exception as e:
                    self.log_message("Error processing drums: {0}".format(str(e)))
            
            if (category_type == "all" or category_type == "audio_effects") and hasattr(app.browser, 'audio_effects'):
                try:
                    audio_effects = process_item(app.browser.audio_effects)
                    if audio_effects:
                        audio_effects["name"] = "Audio Effects"  # Ensure consistent naming
                        result["categories"].append(audio_effects)
                except Exception as e:
                    self.log_message("Error processing audio_effects: {0}".format(str(e)))
            
            if (category_type == "all" or category_type == "midi_effects") and hasattr(app.browser, 'midi_effects'):
                try:
                    midi_effects = process_item(app.browser.midi_effects)
                    if midi_effects:
                        midi_effects["name"] = "MIDI Effects"
                        result["categories"].append(midi_effects)
                except Exception as e:
                    self.log_message("Error processing midi_effects: {0}".format(str(e)))
            
            # Try to process other potentially available categories
            for attr in browser_attrs:
                if attr not in ['instruments', 'sounds', 'drums', 'audio_effects', 'midi_effects'] and \
                   (category_type == "all" or category_type == attr):
                    try:
                        item = getattr(app.browser, attr)
                        if hasattr(item, 'children') or hasattr(item, 'name'):
                            category = process_item(item)
                            if category:
                                category["name"] = attr.capitalize()
                                result["categories"].append(category)
                    except Exception as e:
                        self.log_message("Error processing {0}: {1}".format(attr, str(e)))
            
            self.log_message("Browser tree generated for {0} with {1} root categories".format(
                category_type, len(result['categories'])))
            return result
            
        except Exception as e:
            self.log_message("Error getting browser tree: {0}".format(str(e)))
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
            self.log_message("Available browser attributes: {0}".format(browser_attrs))
                
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
                            self.log_message("Error accessing browser attribute {0}: {1}".format(attr, str(e)))
                
                if not found:
                    # If we still haven't found the category, return available categories
                    return {
                        "path": path,
                        "error": "Unknown or unavailable category: {0}".format(root_category),
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
                        "error": "Item at '{0}' has no children".format('/'.join(path_parts[:i])),
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
                        "error": "Path part '{0}' not found".format(part),
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
            
            self.log_message("Retrieved {0} items at path: {1}".format(len(items), path))
            return result
            
        except Exception as e:
            self.log_message("Error getting browser items at path: {0}".format(str(e)))
            self.log_message(traceback.format_exc())
            raise
    
    def _set_send_level(self, track_index, send_index, value):
        """Set the level of a send from a track to a return track"""
        try:
            # Get the track using the helper function that handles return tracks
            track = self._get_track_by_index(track_index)
            
            # Return tracks don't have sends, so make sure this is a regular track
            if track_index >= len(self._song.tracks):
                raise ValueError("Return tracks don't have sends")
            
            # Verify the send index is valid
            if send_index < 0 or send_index >= len(track.mixer_device.sends):
                raise IndexError("Send index out of range")
            
            # Get the send and set its value
            send = track.mixer_device.sends[send_index]
            send.value = value
            
            result = {
                "track_name": track.name,
                "send_index": send_index,
                "return_track_name": self._song.return_tracks[send_index].name,
                "value": send.value
            }
            return result
        except Exception as e:
            self.log_message("Error setting send level: " + str(e))
            self.log_message(traceback.format_exc())
            raise
    
    def _set_track_volume(self, track_index, value):
        """Set the volume of a track
        
        Args:
            track_index: Index of the track
            value: Volume value (0.0 to 1.0)
        
        Returns:
            Dictionary with track info and new volume value
        """
        try:
            # Get the track using the helper function that handles return tracks
            track = self._get_track_by_index(track_index)
            
            # Set the volume value (0.0 to 1.0)
            track.mixer_device.volume.value = value
            
            result = {
                "track_name": track.name,
                "volume": track.mixer_device.volume.value,
                "volume_db": self._linear_to_db(track.mixer_device.volume.value)
            }
            return result
        except Exception as e:
            self.log_message("Error setting track volume: " + str(e))
            self.log_message(traceback.format_exc())
            raise
    
    def _linear_to_db(self, value):
        """Convert a linear volume value (0.0 to 1.0) to dB
        
        Args:
            value: Linear volume value (0.0 to 1.0)
        
        Returns:
            Volume in dB
        """
        # Add a small epsilon to prevent extreme negative values
        # when value is very close to zero but not exactly zero
        epsilon = 1e-7
        
        if value <= epsilon:
            return float('-inf')  # -infinity dB for zero or near-zero volume
        
        # Ableton's volume mapping is approximately:
        # 0.85 -> 0dB
        # 0.0 -> -inf dB
        # 1.0 -> +6dB
        
        if value < 0.85:
            # Below 0dB
            return 20 * math.log10(value / 0.85)
        else:
            # Above 0dB (0.85 to 1.0 maps to 0dB to +6dB)
            return 6 * (value - 0.85) / 0.15