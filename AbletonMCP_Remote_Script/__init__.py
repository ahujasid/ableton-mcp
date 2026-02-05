# AbletonMCP/init.py
from __future__ import absolute_import, print_function, unicode_literals

from _Framework.ControlSurface import ControlSurface
import socket
import json
import threading
import time
import traceback

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
            elif command_type in ["create_midi_track", "create_audio_track", "set_track_name",
                                 "create_clip", "add_notes_to_clip", "set_clip_name", "delete_clip",
                                 "set_tempo", "fire_clip", "stop_clip",
                                 "start_playback", "stop_playback", "load_browser_item",
                                 "set_device_parameter", "load_sample", "create_clip_automation",
                                 "delete_device", "set_track_volume", "set_track_pan",
                                 "set_track_mute", "set_track_solo", "set_track_arm",
                                 "fire_scene", "create_scene", "set_scene_name",
                                 "set_return_track_volume", "set_track_send",
                                 "delete_track", "delete_scene", "duplicate_clip", "duplicate_track",
                                 "clear_clip_notes", "quantize_clip_notes", "transpose_clip_notes",
                                 "set_clip_looping", "set_clip_loop_points", "set_clip_color",
                                 "set_return_track_pan", "set_return_track_mute", "set_return_track_solo",
                                 "set_master_volume"]:
                # Use a thread-safe approach with a response queue
                response_queue = queue.Queue()
                
                # Define a function to execute on the main thread
                def main_thread_task():
                    try:
                        result = None
                        if command_type == "create_midi_track":
                            index = params.get("index", -1)
                            result = self._create_midi_track(index)
                        elif command_type == "create_audio_track":
                            index = params.get("index", -1)
                            result = self._create_audio_track(index)
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
                        elif command_type == "delete_clip":
                            track_index = params.get("track_index", 0)
                            clip_index = params.get("clip_index", 0)
                            result = self._delete_clip(track_index, clip_index)
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
                        elif command_type == "set_device_parameter":
                            track_index = params.get("track_index", 0)
                            device_index = params.get("device_index", 0)
                            parameter_name = params.get("parameter_name", "")
                            value = params.get("value", 0.0)
                            result = self._set_device_parameter(track_index, device_index, parameter_name, value)
                        elif command_type == "load_sample":
                            track_index = params.get("track_index", 0)
                            sample_uri = params.get("sample_uri", "")
                            result = self._load_sample(track_index, sample_uri)
                        elif command_type == "create_clip_automation":
                            track_index = params.get("track_index", 0)
                            clip_index = params.get("clip_index", 0)
                            parameter_name = params.get("parameter_name", "")
                            automation_points = params.get("automation_points", [])
                            result = self._create_clip_automation(track_index, clip_index, parameter_name, automation_points)
                        elif command_type == "delete_device":
                            track_index = params.get("track_index", 0)
                            device_index = params.get("device_index", 0)
                            result = self._delete_device(track_index, device_index)
                        elif command_type == "set_track_volume":
                            track_index = params.get("track_index", 0)
                            volume = params.get("volume", 0.85)
                            result = self._set_track_volume(track_index, volume)
                        elif command_type == "set_track_pan":
                            track_index = params.get("track_index", 0)
                            pan = params.get("pan", 0.0)
                            result = self._set_track_pan(track_index, pan)
                        elif command_type == "set_track_mute":
                            track_index = params.get("track_index", 0)
                            mute = params.get("mute", False)
                            result = self._set_track_mute(track_index, mute)
                        elif command_type == "set_track_solo":
                            track_index = params.get("track_index", 0)
                            solo = params.get("solo", False)
                            result = self._set_track_solo(track_index, solo)
                        elif command_type == "set_track_arm":
                            track_index = params.get("track_index", 0)
                            arm = params.get("arm", False)
                            result = self._set_track_arm(track_index, arm)
                        elif command_type == "fire_scene":
                            scene_index = params.get("scene_index", 0)
                            result = self._fire_scene(scene_index)
                        elif command_type == "create_scene":
                            index = params.get("index", -1)
                            result = self._create_scene(index)
                        elif command_type == "set_scene_name":
                            scene_index = params.get("scene_index", 0)
                            name = params.get("name", "")
                            result = self._set_scene_name(scene_index, name)
                        elif command_type == "set_return_track_volume":
                            return_track_index = params.get("return_track_index", 0)
                            volume = params.get("volume", 0.85)
                            result = self._set_return_track_volume(return_track_index, volume)
                        elif command_type == "set_track_send":
                            track_index = params.get("track_index", 0)
                            send_index = params.get("send_index", 0)
                            value = params.get("value", 0.0)
                            result = self._set_track_send(track_index, send_index, value)
                        elif command_type == "delete_track":
                            track_index = params.get("track_index", 0)
                            result = self._delete_track(track_index)
                        elif command_type == "delete_scene":
                            scene_index = params.get("scene_index", 0)
                            result = self._delete_scene(scene_index)
                        elif command_type == "duplicate_clip":
                            track_index = params.get("track_index", 0)
                            clip_index = params.get("clip_index", 0)
                            target_clip_index = params.get("target_clip_index", 0)
                            result = self._duplicate_clip(track_index, clip_index, target_clip_index)
                        elif command_type == "duplicate_track":
                            track_index = params.get("track_index", 0)
                            result = self._duplicate_track(track_index)
                        elif command_type == "clear_clip_notes":
                            track_index = params.get("track_index", 0)
                            clip_index = params.get("clip_index", 0)
                            result = self._clear_clip_notes(track_index, clip_index)
                        elif command_type == "quantize_clip_notes":
                            track_index = params.get("track_index", 0)
                            clip_index = params.get("clip_index", 0)
                            grid_size = params.get("grid_size", 0.25)
                            result = self._quantize_clip_notes(track_index, clip_index, grid_size)
                        elif command_type == "transpose_clip_notes":
                            track_index = params.get("track_index", 0)
                            clip_index = params.get("clip_index", 0)
                            semitones = params.get("semitones", 0)
                            result = self._transpose_clip_notes(track_index, clip_index, semitones)
                        elif command_type == "set_clip_looping":
                            track_index = params.get("track_index", 0)
                            clip_index = params.get("clip_index", 0)
                            looping = params.get("looping", True)
                            result = self._set_clip_looping(track_index, clip_index, looping)
                        elif command_type == "set_clip_loop_points":
                            track_index = params.get("track_index", 0)
                            clip_index = params.get("clip_index", 0)
                            loop_start = params.get("loop_start", 0.0)
                            loop_end = params.get("loop_end", 4.0)
                            result = self._set_clip_loop_points(track_index, clip_index, loop_start, loop_end)
                        elif command_type == "set_clip_color":
                            track_index = params.get("track_index", 0)
                            clip_index = params.get("clip_index", 0)
                            color_index = params.get("color_index", 0)
                            result = self._set_clip_color(track_index, clip_index, color_index)
                        elif command_type == "set_return_track_pan":
                            return_track_index = params.get("return_track_index", 0)
                            pan = params.get("pan", 0.0)
                            result = self._set_return_track_pan(return_track_index, pan)
                        elif command_type == "set_return_track_mute":
                            return_track_index = params.get("return_track_index", 0)
                            mute = params.get("mute", False)
                            result = self._set_return_track_mute(return_track_index, mute)
                        elif command_type == "set_return_track_solo":
                            return_track_index = params.get("return_track_index", 0)
                            solo = params.get("solo", False)
                            result = self._set_return_track_solo(return_track_index, solo)
                        elif command_type == "set_master_volume":
                            volume = params.get("volume", 0.85)
                            result = self._set_master_volume(volume)

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
            # New read-only commands
            elif command_type == "get_device_parameters":
                track_index = params.get("track_index", 0)
                device_index = params.get("device_index", 0)
                response["result"] = self._get_device_parameters(track_index, device_index)
            elif command_type == "get_user_library":
                response["result"] = self._get_user_library()
            elif command_type == "get_user_folders":
                response["result"] = self._get_user_folders()
            elif command_type == "search_browser":
                query = params.get("query", "")
                category = params.get("category", "all")
                response["result"] = self._search_browser(query, category)
            elif command_type == "get_scenes":
                response["result"] = self._get_scenes()
            elif command_type == "get_return_tracks":
                response["result"] = self._get_return_tracks()
            elif command_type == "get_return_track_info":
                return_track_index = params.get("return_track_index", 0)
                response["result"] = self._get_return_track_info(return_track_index)
            elif command_type == "get_clip_notes":
                track_index = params.get("track_index", 0)
                clip_index = params.get("clip_index", 0)
                start_time = params.get("start_time", 0.0)
                time_span = params.get("time_span", 0.0)
                start_pitch = params.get("start_pitch", 0)
                pitch_span = params.get("pitch_span", 128)
                response["result"] = self._get_clip_notes(track_index, clip_index, start_time, time_span, start_pitch, pitch_span)
            elif command_type == "get_clip_info":
                track_index = params.get("track_index", 0)
                clip_index = params.get("clip_index", 0)
                response["result"] = self._get_clip_info(track_index, clip_index)
            elif command_type == "get_master_track_info":
                response["result"] = self._get_master_track_info()
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

    def _create_audio_track(self, index):
        """Create a new audio track at the specified index"""
        try:
            # Create the track
            self._song.create_audio_track(index)

            # Get the new track
            new_track_index = len(self._song.tracks) - 1 if index == -1 else index
            new_track = self._song.tracks[new_track_index]

            result = {
                "index": new_track_index,
                "name": new_track.name
            }
            return result
        except Exception as e:
            self.log_message("Error creating audio track: " + str(e))
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

    def _delete_clip(self, track_index, clip_index):
        """Delete a clip from a clip slot"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]

            if clip_index < 0 or clip_index >= len(track.clip_slots):
                raise IndexError("Clip index out of range")

            clip_slot = track.clip_slots[clip_index]

            if not clip_slot.has_clip:
                raise Exception("No clip in slot")

            clip_name = clip_slot.clip.name
            clip_slot.delete_clip()

            return {
                "deleted": True,
                "clip_name": clip_name,
                "track_index": track_index,
                "clip_index": clip_index
            }
        except Exception as e:
            self.log_message("Error deleting clip: " + str(e))
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
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            
            track = self._song.tracks[track_index]
            
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
    
    # New handler methods for device parameters, user library, samples, and automation

    def _get_device_parameters(self, track_index, device_index):
        """Get all parameters for a device"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]

            if device_index < 0 or device_index >= len(track.devices):
                raise IndexError("Device index out of range")

            device = track.devices[device_index]

            parameters = []
            for param in device.parameters:
                param_info = {
                    "name": param.name,
                    "value": param.value,
                    "min": param.min,
                    "max": param.max,
                    "is_quantized": param.is_quantized
                }
                # Try to get default_value, but catch exceptions for parameters that don't support it
                try:
                    if hasattr(param, 'default_value'):
                        param_info["default_value"] = param.default_value
                except:
                    param_info["default_value"] = None
                # Try to get value_items for quantized parameters
                try:
                    if param.is_quantized and hasattr(param, 'value_items'):
                        param_info["value_items"] = list(param.value_items)
                except:
                    pass
                parameters.append(param_info)

            return {
                "device_name": device.name,
                "device_class": device.class_name,
                "parameter_count": len(parameters),
                "parameters": parameters
            }
        except Exception as e:
            self.log_message("Error getting device parameters: " + str(e))
            raise

    def _set_device_parameter(self, track_index, device_index, parameter_name, value):
        """Set a device parameter value"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]

            if device_index < 0 or device_index >= len(track.devices):
                raise IndexError("Device index out of range")

            device = track.devices[device_index]

            for param in device.parameters:
                if param.name.lower() == parameter_name.lower():
                    # Clamp value to valid range
                    clamped_value = max(param.min, min(param.max, value))
                    param.value = clamped_value
                    return {
                        "parameter": param.name,
                        "value": param.value,
                        "clamped": clamped_value != value
                    }

            raise ValueError("Parameter '{0}' not found on device".format(parameter_name))
        except Exception as e:
            self.log_message("Error setting device parameter: " + str(e))
            raise

    def _get_user_library(self):
        """Get user library contents"""
        try:
            app = self.application()
            if not app:
                raise RuntimeError("Could not access Live application")

            if not hasattr(app, 'browser') or app.browser is None:
                raise RuntimeError("Browser is not available")

            items = []

            # Try to access user_library
            if hasattr(app.browser, 'user_library'):
                user_lib = app.browser.user_library
                if hasattr(user_lib, 'children'):
                    for child in user_lib.children:
                        items.append({
                            "name": child.name if hasattr(child, 'name') else "Unknown",
                            "uri": child.uri if hasattr(child, 'uri') else None,
                            "is_folder": hasattr(child, 'children') and bool(child.children),
                            "is_loadable": hasattr(child, 'is_loadable') and child.is_loadable
                        })

            return {
                "item_count": len(items),
                "items": items
            }
        except Exception as e:
            self.log_message("Error getting user library: " + str(e))
            raise

    def _get_user_folders(self):
        """Get user folders"""
        try:
            app = self.application()
            if not app:
                raise RuntimeError("Could not access Live application")

            if not hasattr(app, 'browser') or app.browser is None:
                raise RuntimeError("Browser is not available")

            folders = []

            # Try to access user_folders
            if hasattr(app.browser, 'user_folders'):
                for folder in app.browser.user_folders:
                    folder_info = {
                        "name": folder.name if hasattr(folder, 'name') else "Unknown",
                        "uri": folder.uri if hasattr(folder, 'uri') else None,
                        "is_folder": True
                    }

                    # Try to get children count
                    if hasattr(folder, 'children'):
                        folder_info["child_count"] = len(list(folder.children))

                    folders.append(folder_info)

            return {
                "folder_count": len(folders),
                "folders": folders
            }
        except Exception as e:
            self.log_message("Error getting user folders: " + str(e))
            raise

    def _load_sample(self, track_index, sample_uri):
        """Load a sample onto a track"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]

            app = self.application()
            if not app:
                raise RuntimeError("Could not access Live application")

            # Find the browser item by URI
            item = self._find_browser_item_by_uri(app.browser, sample_uri)

            if not item:
                raise ValueError("Sample with URI '{0}' not found".format(sample_uri))

            # Select the track
            self._song.view.selected_track = track

            # Load the item
            app.browser.load_item(item)

            return {
                "loaded": True,
                "sample_name": item.name if hasattr(item, 'name') else "Unknown",
                "track_index": track_index
            }
        except Exception as e:
            self.log_message("Error loading sample: " + str(e))
            raise

    def _create_clip_automation(self, track_index, clip_index, parameter_name, automation_points):
        """Create automation envelope in a clip"""
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

            # Find the parameter
            param = None

            # Check mixer parameters first
            if parameter_name.lower() == "volume":
                param = track.mixer_device.volume
            elif parameter_name.lower() == "pan" or parameter_name.lower() == "panning":
                param = track.mixer_device.panning
            else:
                # Find in devices
                for device in track.devices:
                    for p in device.parameters:
                        if p.name.lower() == parameter_name.lower():
                            param = p
                            break
                    if param:
                        break

            if not param:
                raise ValueError("Parameter '{0}' not found".format(parameter_name))

            # Check if clip supports automation
            if not hasattr(clip, 'automation_envelope'):
                raise Exception("Clip does not support automation envelopes")

            # Get or create envelope for the parameter
            envelope = clip.automation_envelope(param)

            if envelope is None:
                raise Exception("Could not create automation envelope for parameter")

            # Clear existing automation if the method exists
            if hasattr(envelope, 'clear'):
                envelope.clear()

            # Insert automation points
            point_count = 0
            for point in automation_points:
                time_val = point.get("time", 0.0)
                value_val = point.get("value", 0.0)
                duration = point.get("duration", 0.0)

                # Clamp value to parameter range
                clamped_value = max(param.min, min(param.max, value_val))

                if hasattr(envelope, 'insert_step'):
                    envelope.insert_step(time_val, duration, clamped_value)
                    point_count += 1

            return {
                "created": True,
                "point_count": point_count,
                "parameter": parameter_name
            }
        except Exception as e:
            self.log_message("Error creating clip automation: " + str(e))
            self.log_message(traceback.format_exc())
            raise

    def _search_browser(self, query, category):
        """Search browser for items matching query"""
        try:
            app = self.application()
            if not app:
                raise RuntimeError("Could not access Live application")

            if not hasattr(app, 'browser') or app.browser is None:
                raise RuntimeError("Browser is not available")

            results = []
            query_lower = query.lower()

            def search_item(item, depth=0, max_depth=5):
                if depth > max_depth or len(results) >= 50:
                    return

                if hasattr(item, 'name') and query_lower in item.name.lower():
                    results.append({
                        "name": item.name,
                        "uri": item.uri if hasattr(item, 'uri') else None,
                        "is_loadable": hasattr(item, 'is_loadable') and item.is_loadable,
                        "is_folder": hasattr(item, 'children') and bool(item.children)
                    })

                if hasattr(item, 'children') and len(results) < 50:
                    for child in item.children:
                        search_item(child, depth + 1, max_depth)
                        if len(results) >= 50:
                            break

            # Determine which categories to search
            categories_to_search = []

            if category == "all" or category == "instruments":
                if hasattr(app.browser, 'instruments'):
                    categories_to_search.append(app.browser.instruments)

            if category == "all" or category == "sounds":
                if hasattr(app.browser, 'sounds'):
                    categories_to_search.append(app.browser.sounds)

            if category == "all" or category == "drums":
                if hasattr(app.browser, 'drums'):
                    categories_to_search.append(app.browser.drums)

            if category == "all" or category == "audio_effects":
                if hasattr(app.browser, 'audio_effects'):
                    categories_to_search.append(app.browser.audio_effects)

            if category == "all" or category == "midi_effects":
                if hasattr(app.browser, 'midi_effects'):
                    categories_to_search.append(app.browser.midi_effects)

            # Also search user library if searching all
            if category == "all":
                if hasattr(app.browser, 'user_library'):
                    categories_to_search.append(app.browser.user_library)
                if hasattr(app.browser, 'user_folders'):
                    for folder in app.browser.user_folders:
                        categories_to_search.append(folder)

            # Perform the search
            for cat in categories_to_search:
                search_item(cat)
                if len(results) >= 50:
                    break

            return {
                "query": query,
                "category": category,
                "result_count": len(results),
                "results": results
            }
        except Exception as e:
            self.log_message("Error searching browser: " + str(e))
            raise

    def _delete_device(self, track_index, device_index):
        """Delete a device from a track"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]

            if device_index < 0 or device_index >= len(track.devices):
                raise IndexError("Device index out of range")

            device_name = track.devices[device_index].name
            track.delete_device(device_index)

            return {
                "deleted": True,
                "device_name": device_name,
                "track_index": track_index
            }
        except Exception as e:
            self.log_message("Error deleting device: " + str(e))
            raise

    def _set_track_volume(self, track_index, volume):
        """Set the volume of a track"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]
            volume_param = track.mixer_device.volume

            # Clamp value to valid range
            clamped_value = max(volume_param.min, min(volume_param.max, volume))
            volume_param.value = clamped_value

            return {
                "track_index": track_index,
                "volume": volume_param.value,
                "clamped": clamped_value != volume
            }
        except Exception as e:
            self.log_message("Error setting track volume: " + str(e))
            raise

    def _set_track_pan(self, track_index, pan):
        """Set the panning of a track"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]
            pan_param = track.mixer_device.panning

            # Clamp value to valid range
            clamped_value = max(pan_param.min, min(pan_param.max, pan))
            pan_param.value = clamped_value

            return {
                "track_index": track_index,
                "pan": pan_param.value,
                "clamped": clamped_value != pan
            }
        except Exception as e:
            self.log_message("Error setting track pan: " + str(e))
            raise

    def _set_track_mute(self, track_index, mute):
        """Set the mute state of a track"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]
            track.mute = mute

            return {
                "track_index": track_index,
                "mute": track.mute
            }
        except Exception as e:
            self.log_message("Error setting track mute: " + str(e))
            raise

    def _set_track_solo(self, track_index, solo):
        """Set the solo state of a track"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]
            track.solo = solo

            return {
                "track_index": track_index,
                "solo": track.solo
            }
        except Exception as e:
            self.log_message("Error setting track solo: " + str(e))
            raise

    def _set_track_arm(self, track_index, arm):
        """Set the arm state of a track"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]

            # Check if track can be armed
            if not track.can_be_armed:
                raise Exception("This track cannot be armed")

            track.arm = arm

            return {
                "track_index": track_index,
                "arm": track.arm
            }
        except Exception as e:
            self.log_message("Error setting track arm: " + str(e))
            raise

    def _get_scenes(self):
        """Get information about all scenes"""
        try:
            scenes = []
            for scene_index, scene in enumerate(self._song.scenes):
                scene_info = {
                    "index": scene_index,
                    "name": scene.name,
                    "is_triggered": scene.is_triggered if hasattr(scene, 'is_triggered') else False
                }
                # Try to get tempo if available
                try:
                    if hasattr(scene, 'tempo'):
                        scene_info["tempo"] = scene.tempo
                except:
                    pass
                scenes.append(scene_info)

            return {
                "scene_count": len(scenes),
                "scenes": scenes
            }
        except Exception as e:
            self.log_message("Error getting scenes: " + str(e))
            raise

    def _fire_scene(self, scene_index):
        """Fire a scene"""
        try:
            if scene_index < 0 or scene_index >= len(self._song.scenes):
                raise IndexError("Scene index out of range")

            scene = self._song.scenes[scene_index]
            scene.fire()

            return {
                "fired": True,
                "scene_index": scene_index,
                "scene_name": scene.name
            }
        except Exception as e:
            self.log_message("Error firing scene: " + str(e))
            raise

    def _create_scene(self, index):
        """Create a new scene at the specified index"""
        try:
            self._song.create_scene(index)

            new_scene_index = len(self._song.scenes) - 1 if index == -1 else index
            new_scene = self._song.scenes[new_scene_index]

            return {
                "index": new_scene_index,
                "name": new_scene.name
            }
        except Exception as e:
            self.log_message("Error creating scene: " + str(e))
            raise

    def _set_scene_name(self, scene_index, name):
        """Set the name of a scene"""
        try:
            if scene_index < 0 or scene_index >= len(self._song.scenes):
                raise IndexError("Scene index out of range")

            scene = self._song.scenes[scene_index]
            scene.name = name

            return {
                "name": scene.name
            }
        except Exception as e:
            self.log_message("Error setting scene name: " + str(e))
            raise

    def _get_return_tracks(self):
        """Get information about all return tracks"""
        try:
            return_tracks = []
            for rt_index, return_track in enumerate(self._song.return_tracks):
                rt_info = {
                    "index": rt_index,
                    "name": return_track.name,
                    "volume": return_track.mixer_device.volume.value,
                    "panning": return_track.mixer_device.panning.value,
                    "mute": return_track.mute,
                    "solo": return_track.solo,
                    "devices": []
                }

                for device_index, device in enumerate(return_track.devices):
                    rt_info["devices"].append({
                        "index": device_index,
                        "name": device.name,
                        "class_name": device.class_name
                    })

                return_tracks.append(rt_info)

            return {
                "return_track_count": len(return_tracks),
                "return_tracks": return_tracks
            }
        except Exception as e:
            self.log_message("Error getting return tracks: " + str(e))
            raise

    def _get_return_track_info(self, return_track_index):
        """Get detailed information about a return track"""
        try:
            if return_track_index < 0 or return_track_index >= len(self._song.return_tracks):
                raise IndexError("Return track index out of range")

            return_track = self._song.return_tracks[return_track_index]

            devices = []
            for device_index, device in enumerate(return_track.devices):
                devices.append({
                    "index": device_index,
                    "name": device.name,
                    "class_name": device.class_name,
                    "type": self._get_device_type(device)
                })

            return {
                "index": return_track_index,
                "name": return_track.name,
                "volume": return_track.mixer_device.volume.value,
                "panning": return_track.mixer_device.panning.value,
                "mute": return_track.mute,
                "solo": return_track.solo,
                "devices": devices
            }
        except Exception as e:
            self.log_message("Error getting return track info: " + str(e))
            raise

    def _set_return_track_volume(self, return_track_index, volume):
        """Set the volume of a return track"""
        try:
            if return_track_index < 0 or return_track_index >= len(self._song.return_tracks):
                raise IndexError("Return track index out of range")

            return_track = self._song.return_tracks[return_track_index]
            volume_param = return_track.mixer_device.volume

            clamped_value = max(volume_param.min, min(volume_param.max, volume))
            volume_param.value = clamped_value

            return {
                "return_track_index": return_track_index,
                "volume": volume_param.value,
                "clamped": clamped_value != volume
            }
        except Exception as e:
            self.log_message("Error setting return track volume: " + str(e))
            raise

    def _set_return_track_pan(self, return_track_index, pan):
        """Set the panning of a return track"""
        try:
            if return_track_index < 0 or return_track_index >= len(self._song.return_tracks):
                raise IndexError("Return track index out of range")

            return_track = self._song.return_tracks[return_track_index]
            pan_param = return_track.mixer_device.panning

            clamped_value = max(pan_param.min, min(pan_param.max, pan))
            pan_param.value = clamped_value

            return {
                "return_track_index": return_track_index,
                "pan": pan_param.value,
                "clamped": clamped_value != pan
            }
        except Exception as e:
            self.log_message("Error setting return track pan: " + str(e))
            raise

    def _set_return_track_mute(self, return_track_index, mute):
        """Set the mute state of a return track"""
        try:
            if return_track_index < 0 or return_track_index >= len(self._song.return_tracks):
                raise IndexError("Return track index out of range")

            return_track = self._song.return_tracks[return_track_index]
            return_track.mute = mute

            return {
                "return_track_index": return_track_index,
                "mute": return_track.mute
            }
        except Exception as e:
            self.log_message("Error setting return track mute: " + str(e))
            raise

    def _set_return_track_solo(self, return_track_index, solo):
        """Set the solo state of a return track"""
        try:
            if return_track_index < 0 or return_track_index >= len(self._song.return_tracks):
                raise IndexError("Return track index out of range")

            return_track = self._song.return_tracks[return_track_index]
            return_track.solo = solo

            return {
                "return_track_index": return_track_index,
                "solo": return_track.solo
            }
        except Exception as e:
            self.log_message("Error setting return track solo: " + str(e))
            raise

    def _get_master_track_info(self):
        """Get detailed information about the master track"""
        try:
            master = self._song.master_track

            devices = []
            for device_index, device in enumerate(master.devices):
                devices.append({
                    "index": device_index,
                    "name": device.name,
                    "class_name": device.class_name,
                    "type": self._get_device_type(device)
                })

            result = {
                "name": "Master",
                "volume": master.mixer_device.volume.value,
                "panning": master.mixer_device.panning.value,
                "devices": devices
            }

            return result
        except Exception as e:
            self.log_message("Error getting master track info: " + str(e))
            raise

    def _set_master_volume(self, volume):
        """Set the volume of the master track"""
        try:
            master = self._song.master_track
            volume_param = master.mixer_device.volume

            clamped_value = max(volume_param.min, min(volume_param.max, volume))
            volume_param.value = clamped_value

            return {
                "volume": volume_param.value,
                "clamped": clamped_value != volume
            }
        except Exception as e:
            self.log_message("Error setting master volume: " + str(e))
            raise

    def _set_track_send(self, track_index, send_index, value):
        """Set the send level from a track to a return track"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]
            sends = track.mixer_device.sends

            if send_index < 0 or send_index >= len(sends):
                raise IndexError("Send index out of range")

            send_param = sends[send_index]
            clamped_value = max(send_param.min, min(send_param.max, value))
            send_param.value = clamped_value

            return {
                "track_index": track_index,
                "send_index": send_index,
                "value": send_param.value,
                "clamped": clamped_value != value
            }
        except Exception as e:
            self.log_message("Error setting track send: " + str(e))
            raise

    def _get_clip_notes(self, track_index, clip_index, start_time, time_span, start_pitch, pitch_span):
        """Get MIDI notes from a clip"""
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

            # Check if this is a MIDI clip
            if not hasattr(clip, 'get_notes'):
                raise Exception("Clip is not a MIDI clip")

            # If time_span is 0, use the entire clip length
            if time_span == 0.0:
                time_span = clip.length

            # Get notes from the clip
            # API: get_notes(start_time, start_pitch, time_span, pitch_span)
            notes_tuple = clip.get_notes(start_time, start_pitch, time_span, pitch_span)

            # Convert tuple format to list of dictionaries
            # Notes are returned as tuple of tuples: ((pitch, time, duration, velocity, mute), ...)
            notes = []
            for note in notes_tuple:
                notes.append({
                    "pitch": note[0],
                    "start_time": note[1],
                    "duration": note[2],
                    "velocity": note[3],
                    "mute": note[4] if len(note) > 4 else False
                })

            return {
                "clip_name": clip.name,
                "clip_length": clip.length,
                "note_count": len(notes),
                "notes": notes
            }
        except Exception as e:
            self.log_message("Error getting clip notes: " + str(e))
            raise

    def _delete_track(self, track_index):
        """Delete a track from the session"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]
            track_name = track.name

            self._song.delete_track(track_index)

            return {
                "deleted": True,
                "track_name": track_name,
                "track_index": track_index
            }
        except Exception as e:
            self.log_message("Error deleting track: " + str(e))
            raise

    def _delete_scene(self, scene_index):
        """Delete a scene from the session"""
        try:
            if scene_index < 0 or scene_index >= len(self._song.scenes):
                raise IndexError("Scene index out of range")

            scene = self._song.scenes[scene_index]
            scene_name = scene.name

            self._song.delete_scene(scene_index)

            return {
                "deleted": True,
                "scene_name": scene_name,
                "scene_index": scene_index
            }
        except Exception as e:
            self.log_message("Error deleting scene: " + str(e))
            raise

    def _get_clip_info(self, track_index, clip_index):
        """Get detailed information about a clip"""
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

            result = {
                "name": clip.name,
                "length": clip.length,
                "is_playing": clip.is_playing,
                "is_recording": clip.is_recording,
                "is_midi_clip": hasattr(clip, 'get_notes')
            }

            # Try to get additional properties if available
            try:
                if hasattr(clip, 'start_marker'):
                    result["start_marker"] = clip.start_marker
                if hasattr(clip, 'end_marker'):
                    result["end_marker"] = clip.end_marker
                if hasattr(clip, 'loop_start'):
                    result["loop_start"] = clip.loop_start
                if hasattr(clip, 'loop_end'):
                    result["loop_end"] = clip.loop_end
                if hasattr(clip, 'looping'):
                    result["looping"] = clip.looping
                if hasattr(clip, 'warping'):
                    result["warping"] = clip.warping
                if hasattr(clip, 'color_index'):
                    result["color_index"] = clip.color_index
            except:
                pass

            return result
        except Exception as e:
            self.log_message("Error getting clip info: " + str(e))
            raise

    def _clear_clip_notes(self, track_index, clip_index):
        """Remove all MIDI notes from a clip"""
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

            if not hasattr(clip, 'remove_notes'):
                raise Exception("Clip is not a MIDI clip")

            # Count notes before removing
            notes_before = clip.get_notes(0, 0, clip.length, 128)
            notes_count = len(notes_before)

            # Remove all notes
            clip.remove_notes(0, 0, clip.length, 128)

            return {
                "cleared": True,
                "notes_removed": notes_count,
                "clip_name": clip.name
            }
        except Exception as e:
            self.log_message("Error clearing clip notes: " + str(e))
            raise

    def _duplicate_clip(self, track_index, clip_index, target_clip_index):
        """Duplicate a clip to another slot on the same track"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]

            if clip_index < 0 or clip_index >= len(track.clip_slots):
                raise IndexError("Source clip index out of range")

            if target_clip_index < 0 or target_clip_index >= len(track.clip_slots):
                raise IndexError("Target clip index out of range")

            source_slot = track.clip_slots[clip_index]
            target_slot = track.clip_slots[target_clip_index]

            if not source_slot.has_clip:
                raise Exception("No clip in source slot")

            if target_slot.has_clip:
                raise Exception("Target slot already has a clip")

            # Duplicate the clip
            source_slot.duplicate_clip_to(target_slot)

            return {
                "duplicated": True,
                "source_index": clip_index,
                "target_index": target_clip_index,
                "clip_name": source_slot.clip.name
            }
        except Exception as e:
            self.log_message("Error duplicating clip: " + str(e))
            raise

    def _duplicate_track(self, track_index):
        """Duplicate a track with all its devices and clips"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]
            source_name = track.name

            # Duplicate the track
            self._song.duplicate_track(track_index)

            # The new track is inserted right after the source
            new_track_index = track_index + 1
            new_track = self._song.tracks[new_track_index]

            return {
                "duplicated": True,
                "source_index": track_index,
                "source_name": source_name,
                "new_index": new_track_index,
                "new_name": new_track.name
            }
        except Exception as e:
            self.log_message("Error duplicating track: " + str(e))
            raise

    def _quantize_clip_notes(self, track_index, clip_index, grid_size):
        """Quantize MIDI notes in a clip to a grid"""
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

            if not hasattr(clip, 'get_notes'):
                raise Exception("Clip is not a MIDI clip")

            # Get all notes
            notes_tuple = clip.get_notes(0, 0, clip.length, 128)

            if len(notes_tuple) == 0:
                return {
                    "quantized": True,
                    "notes_quantized": 0,
                    "grid_size": grid_size
                }

            # Quantize each note's start time
            quantized_notes = []
            for note in notes_tuple:
                pitch = note[0]
                start_time = note[1]
                duration = note[2]
                velocity = note[3]
                mute = note[4] if len(note) > 4 else False

                # Quantize start time to grid
                quantized_time = round(start_time / grid_size) * grid_size

                quantized_notes.append((pitch, quantized_time, duration, velocity, mute))

            # Remove old notes and add quantized notes
            clip.remove_notes(0, 0, clip.length, 128)
            clip.set_notes(tuple(quantized_notes))

            return {
                "quantized": True,
                "notes_quantized": len(quantized_notes),
                "grid_size": grid_size
            }
        except Exception as e:
            self.log_message("Error quantizing clip notes: " + str(e))
            raise

    def _transpose_clip_notes(self, track_index, clip_index, semitones):
        """Transpose MIDI notes in a clip by a number of semitones"""
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

            if not hasattr(clip, 'get_notes'):
                raise Exception("Clip is not a MIDI clip")

            # Get all notes
            notes_tuple = clip.get_notes(0, 0, clip.length, 128)

            if len(notes_tuple) == 0:
                return {
                    "transposed": True,
                    "notes_transposed": 0,
                    "semitones": semitones
                }

            # Transpose each note's pitch
            transposed_notes = []
            for note in notes_tuple:
                pitch = note[0]
                start_time = note[1]
                duration = note[2]
                velocity = note[3]
                mute = note[4] if len(note) > 4 else False

                # Transpose pitch and clamp to valid MIDI range (0-127)
                new_pitch = max(0, min(127, pitch + semitones))

                transposed_notes.append((new_pitch, start_time, duration, velocity, mute))

            # Remove old notes and add transposed notes
            clip.remove_notes(0, 0, clip.length, 128)
            clip.set_notes(tuple(transposed_notes))

            return {
                "transposed": True,
                "notes_transposed": len(transposed_notes),
                "semitones": semitones
            }
        except Exception as e:
            self.log_message("Error transposing clip notes: " + str(e))
            raise

    def _set_clip_looping(self, track_index, clip_index, looping):
        """Set the looping state of a clip"""
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
            clip.looping = looping

            return {
                "track_index": track_index,
                "clip_index": clip_index,
                "looping": clip.looping
            }
        except Exception as e:
            self.log_message("Error setting clip looping: " + str(e))
            raise

    def _set_clip_loop_points(self, track_index, clip_index, loop_start, loop_end):
        """Set the loop start and end points of a clip"""
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

            # Set in safe order to avoid loop_start >= loop_end errors
            if loop_end > clip.loop_start:
                clip.loop_end = loop_end
                clip.loop_start = loop_start
            else:
                clip.loop_start = loop_start
                clip.loop_end = loop_end

            return {
                "track_index": track_index,
                "clip_index": clip_index,
                "loop_start": clip.loop_start,
                "loop_end": clip.loop_end
            }
        except Exception as e:
            self.log_message("Error setting clip loop points: " + str(e))
            raise

    def _set_clip_color(self, track_index, clip_index, color_index):
        """Set the color of a clip"""
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
            clip.color_index = color_index

            return {
                "track_index": track_index,
                "clip_index": clip_index,
                "color_index": clip.color_index
            }
        except Exception as e:
            self.log_message("Error setting clip color: " + str(e))
            raise

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
