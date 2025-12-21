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
            elif command_type == "get_all_track_info":
                response["result"] = self._get_all_track_info()
            # Read-only commands for new features
            elif command_type == "get_arrangement_clips":
                track_index = params.get("track_index", 0)
                response["result"] = self._get_arrangement_clips(track_index)
            elif command_type == "get_device_parameters":
                track_index = params.get("track_index", 0)
                device_index = params.get("device_index", 0)
                response["result"] = self._get_device_parameters(track_index, device_index)
            elif command_type == "get_track_devices":
                track_index = params.get("track_index", 0)
                response["result"] = self._get_track_devices(track_index)
            elif command_type == "get_scenes":
                response["result"] = self._get_scenes()
            elif command_type == "get_clip_notes":
                track_index = params.get("track_index", 0)
                clip_index = params.get("clip_index", 0)
                response["result"] = self._get_clip_notes(track_index, clip_index)
            elif command_type == "get_arrangement_clip_notes":
                track_index = params.get("track_index", 0)
                clip_index = params.get("clip_index", 0)
                response["result"] = self._get_arrangement_clip_notes(track_index, clip_index)
            elif command_type == "get_cue_points":
                response["result"] = self._get_cue_points()
            elif command_type == "get_playhead_position":
                response["result"] = {"position": self._song.current_song_time}
            # Commands that modify Live's state should be scheduled on the main thread
            elif command_type in ["create_midi_track", "create_audio_track", "delete_track", "set_track_name",
                                 "create_clip", "add_notes_to_clip", "set_clip_name",
                                 "set_tempo", "fire_clip", "stop_clip",
                                 "start_playback", "stop_playback", "load_browser_item",
                                 "create_clip_in_arrangement", "add_notes_to_arrangement_clip",
                                 "duplicate_clip_to_arrangement", "delete_arrangement_clip",
                                 "set_device_parameter", "create_scene", "set_scene_name",
                                 "fire_scene", "set_track_volume", "set_track_pan",
                                 "set_track_mute", "set_track_solo", "set_track_arm",
                                 "set_send_level", "duplicate_clip", "set_clip_loop",
                                 "set_clip_start_end", "clear_clip_notes",
                                 "create_cue_point", "delete_cue_point",
                                 "set_playhead_position",
                                 "split_arrangement_clip", "move_arrangement_clip",
                                 "set_arrangement_clip_file_position", "duplicate_arrangement_clip_to_time"]:
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
                        # Arrangement view operations
                        elif command_type == "create_clip_in_arrangement":
                            track_index = params.get("track_index", 0)
                            start_time = params.get("start_time", 0.0)
                            length = params.get("length", 4.0)
                            result = self._create_clip_in_arrangement(track_index, start_time, length)
                        elif command_type == "add_notes_to_arrangement_clip":
                            track_index = params.get("track_index", 0)
                            clip_index = params.get("clip_index", 0)
                            notes = params.get("notes", [])
                            result = self._add_notes_to_arrangement_clip(track_index, clip_index, notes)
                        elif command_type == "duplicate_clip_to_arrangement":
                            track_index = params.get("track_index", 0)
                            clip_slot_index = params.get("clip_slot_index", 0)
                            destination_time = params.get("destination_time", 0.0)
                            result = self._duplicate_clip_to_arrangement(track_index, clip_slot_index, destination_time)
                        elif command_type == "delete_arrangement_clip":
                            track_index = params.get("track_index", 0)
                            clip_index = params.get("clip_index", 0)
                            result = self._delete_arrangement_clip(track_index, clip_index)
                        # Device parameter operations
                        elif command_type == "set_device_parameter":
                            track_index = params.get("track_index", 0)
                            device_index = params.get("device_index", 0)
                            parameter_index = params.get("parameter_index", 0)
                            value = params.get("value", 0.0)
                            result = self._set_device_parameter(track_index, device_index, parameter_index, value)
                        # Scene operations
                        elif command_type == "create_scene":
                            index = params.get("index", -1)
                            result = self._create_scene(index)
                        elif command_type == "set_scene_name":
                            scene_index = params.get("scene_index", 0)
                            name = params.get("name", "")
                            result = self._set_scene_name(scene_index, name)
                        elif command_type == "fire_scene":
                            scene_index = params.get("scene_index", 0)
                            result = self._fire_scene(scene_index)
                        # Mixer operations
                        elif command_type == "set_track_volume":
                            track_index = params.get("track_index", 0)
                            value = params.get("value", 0.85)
                            result = self._set_track_volume(track_index, value)
                        elif command_type == "set_track_pan":
                            track_index = params.get("track_index", 0)
                            value = params.get("value", 0.0)
                            result = self._set_track_pan(track_index, value)
                        elif command_type == "set_track_mute":
                            track_index = params.get("track_index", 0)
                            muted = params.get("muted", False)
                            result = self._set_track_mute(track_index, muted)
                        elif command_type == "set_track_solo":
                            track_index = params.get("track_index", 0)
                            soloed = params.get("soloed", False)
                            result = self._set_track_solo(track_index, soloed)
                        elif command_type == "set_track_arm":
                            track_index = params.get("track_index", 0)
                            armed = params.get("armed", False)
                            result = self._set_track_arm(track_index, armed)
                        elif command_type == "set_send_level":
                            track_index = params.get("track_index", 0)
                            send_index = params.get("send_index", 0)
                            value = params.get("value", 0.0)
                            result = self._set_send_level(track_index, send_index, value)
                        # Clip operations
                        elif command_type == "duplicate_clip":
                            track_index = params.get("track_index", 0)
                            source_slot = params.get("source_slot", 0)
                            dest_slot = params.get("dest_slot", 1)
                            result = self._duplicate_clip(track_index, source_slot, dest_slot)
                        elif command_type == "set_clip_loop":
                            track_index = params.get("track_index", 0)
                            clip_index = params.get("clip_index", 0)
                            loop_start = params.get("loop_start", 0.0)
                            loop_end = params.get("loop_end", 4.0)
                            result = self._set_clip_loop(track_index, clip_index, loop_start, loop_end)
                        elif command_type == "set_clip_start_end":
                            track_index = params.get("track_index", 0)
                            clip_index = params.get("clip_index", 0)
                            start = params.get("start", 0.0)
                            end = params.get("end", 4.0)
                            result = self._set_clip_start_end(track_index, clip_index, start, end)
                        elif command_type == "clear_clip_notes":
                            track_index = params.get("track_index", 0)
                            clip_index = params.get("clip_index", 0)
                            result = self._clear_clip_notes(track_index, clip_index)
                        elif command_type == "create_audio_track":
                            index = params.get("index", -1)
                            result = self._create_audio_track(index)
                        elif command_type == "delete_track":
                            track_index = params.get("track_index", 0)
                            track_name = params.get("track_name", "")
                            result = self._delete_track(track_index, track_name)
                        elif command_type == "create_cue_point":
                            time = params.get("time", 0)
                            result = self._create_cue_point(time)
                        elif command_type == "delete_cue_point":
                            time = params.get("time", 0)
                            result = self._delete_cue_point(time)
                        elif command_type == "set_playhead_position":
                            position = params.get("position", 0)
                            self._song.current_song_time = position
                            result = {"position": self._song.current_song_time}
                        # Arrangement clip manipulation
                        elif command_type == "split_arrangement_clip":
                            track_index = params.get("track_index", 0)
                            clip_index = params.get("clip_index", 0)
                            split_time = params.get("split_time", 0.0)
                            result = self._split_arrangement_clip(track_index, clip_index, split_time)
                        elif command_type == "move_arrangement_clip":
                            track_index = params.get("track_index", 0)
                            clip_index = params.get("clip_index", 0)
                            new_start_time = params.get("new_start_time", 0.0)
                            result = self._move_arrangement_clip(track_index, clip_index, new_start_time)
                        elif command_type == "set_arrangement_clip_file_position":
                            track_index = params.get("track_index", 0)
                            clip_index = params.get("clip_index", 0)
                            start_marker = params.get("start_marker", None)
                            end_marker = params.get("end_marker", None)
                            loop_start = params.get("loop_start", None)
                            loop_end = params.get("loop_end", None)
                            result = self._set_arrangement_clip_file_position(track_index, clip_index, start_marker, end_marker, loop_start, loop_end)
                        elif command_type == "duplicate_arrangement_clip_to_time":
                            track_index = params.get("track_index", 0)
                            clip_index = params.get("clip_index", 0)
                            destination_time = params.get("destination_time", 0.0)
                            result = self._duplicate_arrangement_clip_to_time(track_index, clip_index, destination_time)

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

    def _get_all_track_info(self):
        """Get information about all tracks in the session"""
        try:
            tracks = []
            for track_index in range(len(self._song.tracks)):
                track = self._song.tracks[track_index]

                # Get clip slots (basic info only to keep response size manageable)
                clip_slots = []
                for slot_index, slot in enumerate(track.clip_slots):
                    clip_info = None
                    if slot.has_clip:
                        clip = slot.clip
                        clip_info = {
                            "name": clip.name,
                            "length": clip.length,
                            "is_playing": clip.is_playing
                        }

                    clip_slots.append({
                        "index": slot_index,
                        "has_clip": slot.has_clip,
                        "clip": clip_info
                    })

                # Get devices (basic info only)
                devices = []
                for device_index, device in enumerate(track.devices):
                    devices.append({
                        "index": device_index,
                        "name": device.name,
                        "class_name": device.class_name
                    })

                tracks.append({
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
                })

            return {"tracks": tracks, "count": len(tracks)}
        except Exception as e:
            self.log_message("Error getting all track info: " + str(e))
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

    # ============================================
    # ARRANGEMENT VIEW OPERATIONS
    # ============================================

    def _get_arrangement_clips(self, track_index):
        """Get all clips in the arrangement view for a track"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]
            clips = []

            # Check if arrangement_clips is available (Live 11+)
            if hasattr(track, 'arrangement_clips'):
                for i, clip in enumerate(track.arrangement_clips):
                    clips.append({
                        "index": i,
                        "name": clip.name,
                        "start_time": clip.start_time,
                        "end_time": clip.end_time,
                        "length": clip.length,
                        "is_midi_clip": clip.is_midi_clip,
                        "color": clip.color
                    })

            return {
                "track_index": track_index,
                "track_name": track.name,
                "clips": clips
            }
        except Exception as e:
            self.log_message("Error getting arrangement clips: " + str(e))
            raise

    def _create_clip_in_arrangement(self, track_index, start_time, length):
        """Create a MIDI clip in the arrangement view"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]

            # Check if this is a MIDI track
            if not track.has_midi_input:
                raise ValueError("Track is not a MIDI track")

            # Live 12+: Use direct arrangement clip creation
            if hasattr(track, 'create_midi_clip_in_arrangement'):
                clip = track.create_midi_clip_in_arrangement(start_time, length)
                return {
                    "name": clip.name,
                    "start_time": start_time,
                    "length": length,
                    "track_index": track_index,
                    "method": "direct"
                }

            # Live 11 fallback: Create in session, duplicate to arrangement, delete session clip
            # Find an empty clip slot to use as temporary storage
            temp_slot_index = None
            for i, slot in enumerate(track.clip_slots):
                if not slot.has_clip:
                    temp_slot_index = i
                    break

            if temp_slot_index is None:
                raise RuntimeError("No empty clip slot available for arrangement clip creation")

            clip_slot = track.clip_slots[temp_slot_index]

            # Step 1: Create clip in session view
            clip_slot.create_clip(length)
            clip = clip_slot.clip
            clip_name = clip.name

            # Step 2: Duplicate to arrangement at the specified time
            if hasattr(track, 'duplicate_clip_to_arrangement'):
                track.duplicate_clip_to_arrangement(clip, start_time)
            else:
                # Clean up and raise error if even this isn't available
                clip_slot.delete_clip()
                raise RuntimeError("Neither create_midi_clip_in_arrangement nor duplicate_clip_to_arrangement available")

            # Step 3: Delete the temporary session clip
            clip_slot.delete_clip()

            return {
                "name": clip_name,
                "start_time": start_time,
                "length": length,
                "track_index": track_index,
                "method": "fallback"
            }
        except Exception as e:
            self.log_message("Error creating arrangement clip: " + str(e))
            raise

    def _add_notes_to_arrangement_clip(self, track_index, clip_index, notes):
        """Add MIDI notes to an arrangement clip"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]

            if not hasattr(track, 'arrangement_clips'):
                raise RuntimeError("arrangement_clips not available (requires Live 11+)")

            if clip_index < 0 or clip_index >= len(track.arrangement_clips):
                raise IndexError("Clip index out of range")

            clip = track.arrangement_clips[clip_index]

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

            return {
                "note_count": len(notes),
                "clip_index": clip_index
            }
        except Exception as e:
            self.log_message("Error adding notes to arrangement clip: " + str(e))
            raise

    def _duplicate_clip_to_arrangement(self, track_index, clip_slot_index, destination_time):
        """Duplicate a session clip to the arrangement view"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]

            if clip_slot_index < 0 or clip_slot_index >= len(track.clip_slots):
                raise IndexError("Clip slot index out of range")

            clip_slot = track.clip_slots[clip_slot_index]

            if not clip_slot.has_clip:
                raise ValueError("No clip in the specified slot")

            clip = clip_slot.clip

            # Duplicate to arrangement
            if hasattr(track, 'duplicate_clip_to_arrangement'):
                track.duplicate_clip_to_arrangement(clip, destination_time)

                return {
                    "source_clip": clip.name,
                    "destination_time": destination_time,
                    "track_index": track_index
                }
            else:
                raise RuntimeError("duplicate_clip_to_arrangement not available (requires Live 11+)")
        except Exception as e:
            self.log_message("Error duplicating clip to arrangement: " + str(e))
            raise

    def _delete_arrangement_clip(self, track_index, clip_index):
        """Delete a clip from the arrangement view"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]

            if not hasattr(track, 'arrangement_clips'):
                raise RuntimeError("arrangement_clips not available (requires Live 11+)")

            if clip_index < 0 or clip_index >= len(track.arrangement_clips):
                raise IndexError("Clip index out of range")

            clip = track.arrangement_clips[clip_index]
            clip_name = clip.name

            # Delete the clip using the delete_clip method if available
            if hasattr(track, 'delete_clip'):
                track.delete_clip(clip)
            else:
                # Alternative: clear the clip's time selection
                clip.clear_all_envelopes()
                # Note: Full deletion may not be possible without delete_clip
                raise RuntimeError("delete_clip not available - clip cleared but not deleted")

            return {
                "deleted": True,
                "clip_name": clip_name,
                "track_index": track_index
            }
        except Exception as e:
            self.log_message("Error deleting arrangement clip: " + str(e))
            raise

    def _split_arrangement_clip(self, track_index, clip_index, split_time):
        """
        Split an arrangement clip at a specific time.
        Creates two clips: one ending at split_time, one starting at split_time.

        Note: Live doesn't have a direct split API, so we:
        1. Duplicate the clip
        2. Trim the original to end at split_time
        3. Trim the duplicate to start at split_time
        """
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]

            if not hasattr(track, 'arrangement_clips'):
                raise RuntimeError("arrangement_clips not available (requires Live 11+)")

            if clip_index < 0 or clip_index >= len(track.arrangement_clips):
                raise IndexError("Clip index out of range")

            clip = track.arrangement_clips[clip_index]
            clip_name = clip.name
            original_start = clip.start_time
            original_end = clip.end_time

            # Validate split_time is within clip bounds
            if split_time <= original_start or split_time >= original_end:
                raise ValueError("split_time must be within clip bounds ({0} to {1})".format(original_start, original_end))

            # For audio clips, we need to calculate the file position offset
            is_audio = not clip.is_midi_clip

            if is_audio:
                # Get the current loop/warp settings
                original_loop_start = clip.loop_start if hasattr(clip, 'loop_start') else 0

                # Calculate the offset in the audio file for the split point
                # The split point in the file = loop_start + (split_time - clip_start)
                split_file_position = original_loop_start + (split_time - original_start)

            # Duplicate the clip first
            if hasattr(track, 'duplicate_clip_to_arrangement'):
                track.duplicate_clip_to_arrangement(clip, split_time)
            else:
                raise RuntimeError("duplicate_clip_to_arrangement not available")

            # Find the new clip (should be at the split position)
            new_clip = None
            new_clip_index = None
            for i, c in enumerate(track.arrangement_clips):
                if abs(c.start_time - split_time) < 0.001 and i != clip_index:
                    new_clip = c
                    new_clip_index = i
                    break

            if not new_clip:
                raise RuntimeError("Could not find duplicated clip")

            # For audio clips, adjust the loop_start of the new clip
            if is_audio and hasattr(new_clip, 'loop_start'):
                new_clip.loop_start = split_file_position

            # Note: We can't easily trim the original clip's end in arrangement view
            # The user may need to manually adjust or we need to delete and recreate

            return {
                "success": True,
                "original_clip": {
                    "index": clip_index,
                    "name": clip_name,
                    "start": original_start,
                    "end": original_end
                },
                "new_clip": {
                    "index": new_clip_index,
                    "name": new_clip.name,
                    "start": new_clip.start_time,
                    "end": new_clip.end_time
                },
                "split_time": split_time,
                "note": "Original clip end may need manual adjustment"
            }
        except Exception as e:
            self.log_message("Error splitting arrangement clip: " + str(e))
            raise

    def _move_arrangement_clip(self, track_index, clip_index, new_start_time):
        """
        Move an arrangement clip to a new start time.

        Note: Live's arrangement clips don't have a direct 'move' API.
        We duplicate to the new position and delete the original.
        """
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]

            if not hasattr(track, 'arrangement_clips'):
                raise RuntimeError("arrangement_clips not available (requires Live 11+)")

            if clip_index < 0 or clip_index >= len(track.arrangement_clips):
                raise IndexError("Clip index out of range")

            clip = track.arrangement_clips[clip_index]
            clip_name = clip.name
            original_start = clip.start_time
            original_end = clip.end_time
            clip_length = original_end - original_start

            if abs(new_start_time - original_start) < 0.001:
                return {
                    "success": True,
                    "message": "Clip already at target position",
                    "start_time": original_start
                }

            # Duplicate the clip to the new position
            if hasattr(track, 'duplicate_clip_to_arrangement'):
                track.duplicate_clip_to_arrangement(clip, new_start_time)
            else:
                raise RuntimeError("duplicate_clip_to_arrangement not available")

            # Delete the original clip
            if hasattr(track, 'delete_clip'):
                track.delete_clip(clip)
            else:
                raise RuntimeError("delete_clip not available - clip duplicated but original not deleted")

            # Find the new clip
            new_clip = None
            new_clip_index = None
            for i, c in enumerate(track.arrangement_clips):
                if abs(c.start_time - new_start_time) < 0.001:
                    new_clip = c
                    new_clip_index = i
                    break

            return {
                "success": True,
                "clip_name": clip_name,
                "original_start": original_start,
                "new_start": new_start_time,
                "new_clip_index": new_clip_index
            }
        except Exception as e:
            self.log_message("Error moving arrangement clip: " + str(e))
            raise

    def _set_arrangement_clip_file_position(self, track_index, clip_index, start_marker=None, end_marker=None, loop_start=None, loop_end=None):
        """
        Set the file position markers for an arrangement clip.
        This controls which part of the source audio/MIDI file is played.

        For audio clips:
        - start_marker/end_marker: Control the visible region in the clip
        - loop_start/loop_end: Control which part of the file plays (in beats, relative to file start)
        """
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]

            if not hasattr(track, 'arrangement_clips'):
                raise RuntimeError("arrangement_clips not available (requires Live 11+)")

            if clip_index < 0 or clip_index >= len(track.arrangement_clips):
                raise IndexError("Clip index out of range")

            clip = track.arrangement_clips[clip_index]
            result = {
                "clip_name": clip.name,
                "clip_index": clip_index,
                "changes": []
            }

            # Set start marker if provided
            if start_marker is not None and hasattr(clip, 'start_marker'):
                clip.start_marker = start_marker
                result["changes"].append("start_marker")
                result["start_marker"] = clip.start_marker

            # Set end marker if provided
            if end_marker is not None and hasattr(clip, 'end_marker'):
                clip.end_marker = end_marker
                result["changes"].append("end_marker")
                result["end_marker"] = clip.end_marker

            # Set loop start if provided (this is key for audio file position)
            if loop_start is not None and hasattr(clip, 'loop_start'):
                clip.loop_start = loop_start
                result["changes"].append("loop_start")
                result["loop_start"] = clip.loop_start

            # Set loop end if provided
            if loop_end is not None and hasattr(clip, 'loop_end'):
                clip.loop_end = loop_end
                result["changes"].append("loop_end")
                result["loop_end"] = clip.loop_end

            return result
        except Exception as e:
            self.log_message("Error setting arrangement clip file position: " + str(e))
            raise

    def _duplicate_arrangement_clip_to_time(self, track_index, clip_index, destination_time):
        """
        Duplicate an arrangement clip to a new time position.
        """
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]

            if not hasattr(track, 'arrangement_clips'):
                raise RuntimeError("arrangement_clips not available (requires Live 11+)")

            if clip_index < 0 or clip_index >= len(track.arrangement_clips):
                raise IndexError("Clip index out of range")

            clip = track.arrangement_clips[clip_index]
            clip_name = clip.name

            # Duplicate to arrangement
            if hasattr(track, 'duplicate_clip_to_arrangement'):
                track.duplicate_clip_to_arrangement(clip, destination_time)
            else:
                raise RuntimeError("duplicate_clip_to_arrangement not available")

            # Find the new clip
            new_clip = None
            new_clip_index = None
            for i, c in enumerate(track.arrangement_clips):
                if abs(c.start_time - destination_time) < 0.001:
                    new_clip = c
                    new_clip_index = i
                    break

            return {
                "success": True,
                "source_clip": clip_name,
                "source_index": clip_index,
                "destination_time": destination_time,
                "new_clip_index": new_clip_index,
                "new_clip_name": new_clip.name if new_clip else "Unknown"
            }
        except Exception as e:
            self.log_message("Error duplicating arrangement clip: " + str(e))
            raise

    # ============================================
    # DEVICE PARAMETER OPERATIONS
    # ============================================

    def _get_track_devices(self, track_index):
        """Get all devices on a track. Use track_index=-1 for master track."""
        try:
            if track_index == -1:
                track = self._song.master_track
            elif track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            else:
                track = self._song.tracks[track_index]
            devices = []

            for i, device in enumerate(track.devices):
                devices.append({
                    "index": i,
                    "name": device.name,
                    "class_name": device.class_name,
                    "type": self._get_device_type(device),
                    "is_active": device.is_active,
                    "parameter_count": len(device.parameters) if hasattr(device, 'parameters') else 0
                })

            return {
                "track_index": track_index,
                "track_name": track.name,
                "devices": devices
            }
        except Exception as e:
            self.log_message("Error getting track devices: " + str(e))
            raise

    def _get_device_parameters(self, track_index, device_index):
        """Get all parameters of a device. Use track_index=-1 for master track."""
        try:
            if track_index == -1:
                track = self._song.master_track
            elif track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            else:
                track = self._song.tracks[track_index]

            if device_index < 0 or device_index >= len(track.devices):
                raise IndexError("Device index out of range")

            device = track.devices[device_index]
            params = []

            for i, param in enumerate(device.parameters):
                params.append({
                    "index": i,
                    "name": param.name,
                    "value": param.value,
                    "min": param.min,
                    "max": param.max,
                    "default_value": param.default_value,
                    "is_quantized": param.is_quantized
                })

            return {
                "track_index": track_index,
                "device_index": device_index,
                "device_name": device.name,
                "parameters": params
            }
        except Exception as e:
            self.log_message("Error getting device parameters: " + str(e))
            raise

    def _set_device_parameter(self, track_index, device_index, parameter_index, value):
        """Set a device parameter value. Use track_index=-1 for master track."""
        try:
            if track_index == -1:
                track = self._song.master_track
            elif track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            else:
                track = self._song.tracks[track_index]

            if device_index < 0 or device_index >= len(track.devices):
                raise IndexError("Device index out of range")

            device = track.devices[device_index]

            if parameter_index < 0 or parameter_index >= len(device.parameters):
                raise IndexError("Parameter index out of range")

            param = device.parameters[parameter_index]

            # Clamp value to valid range
            clamped_value = max(param.min, min(param.max, value))
            param.value = clamped_value

            return {
                "parameter_name": param.name,
                "new_value": param.value,
                "device_name": device.name
            }
        except Exception as e:
            self.log_message("Error setting device parameter: " + str(e))
            raise

    # ============================================
    # SCENE OPERATIONS
    # ============================================

    def _get_scenes(self):
        """Get all scenes in the session"""
        try:
            scenes = []

            for i, scene in enumerate(self._song.scenes):
                scenes.append({
                    "index": i,
                    "name": scene.name,
                    "tempo": scene.tempo if hasattr(scene, 'tempo') else None,
                    "is_triggered": scene.is_triggered,
                    "color": scene.color
                })

            return {
                "scene_count": len(scenes),
                "scenes": scenes
            }
        except Exception as e:
            self.log_message("Error getting scenes: " + str(e))
            raise

    def _create_scene(self, index):
        """Create a new scene at the specified index"""
        try:
            if index == -1:
                index = len(self._song.scenes)

            self._song.create_scene(index)
            new_scene = self._song.scenes[index]

            return {
                "index": index,
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
                "index": scene_index,
                "name": scene.name
            }
        except Exception as e:
            self.log_message("Error setting scene name: " + str(e))
            raise

    def _fire_scene(self, scene_index):
        """Fire (trigger) a scene"""
        try:
            if scene_index < 0 or scene_index >= len(self._song.scenes):
                raise IndexError("Scene index out of range")

            scene = self._song.scenes[scene_index]
            scene.fire()

            return {
                "fired": True,
                "index": scene_index,
                "name": scene.name
            }
        except Exception as e:
            self.log_message("Error firing scene: " + str(e))
            raise

    # ============================================
    # MIXER OPERATIONS
    # ============================================

    def _set_track_volume(self, track_index, value):
        """Set the volume of a track (0.0 to 1.0)"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]
            track.mixer_device.volume.value = max(0.0, min(1.0, value))

            return {
                "track_index": track_index,
                "volume": track.mixer_device.volume.value
            }
        except Exception as e:
            self.log_message("Error setting track volume: " + str(e))
            raise

    def _set_track_pan(self, track_index, value):
        """Set the pan of a track (-1.0 to 1.0)"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]
            track.mixer_device.panning.value = max(-1.0, min(1.0, value))

            return {
                "track_index": track_index,
                "pan": track.mixer_device.panning.value
            }
        except Exception as e:
            self.log_message("Error setting track pan: " + str(e))
            raise

    def _set_track_mute(self, track_index, muted):
        """Set the mute state of a track"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]
            track.mute = muted

            return {
                "track_index": track_index,
                "muted": track.mute
            }
        except Exception as e:
            self.log_message("Error setting track mute: " + str(e))
            raise

    def _set_track_solo(self, track_index, soloed):
        """Set the solo state of a track"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]
            track.solo = soloed

            return {
                "track_index": track_index,
                "soloed": track.solo
            }
        except Exception as e:
            self.log_message("Error setting track solo: " + str(e))
            raise

    def _set_track_arm(self, track_index, armed):
        """Set the arm state of a track for recording"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]

            # Only MIDI/audio tracks can be armed
            if track.can_be_armed:
                track.arm = armed
            else:
                raise ValueError("Track cannot be armed")

            return {
                "track_index": track_index,
                "armed": track.arm
            }
        except Exception as e:
            self.log_message("Error setting track arm: " + str(e))
            raise

    def _set_send_level(self, track_index, send_index, value):
        """Set a send level for a track"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]
            sends = track.mixer_device.sends

            if send_index < 0 or send_index >= len(sends):
                raise IndexError("Send index out of range")

            sends[send_index].value = max(0.0, min(1.0, value))

            return {
                "track_index": track_index,
                "send_index": send_index,
                "value": sends[send_index].value
            }
        except Exception as e:
            self.log_message("Error setting send level: " + str(e))
            raise

    # ============================================
    # CLIP OPERATIONS
    # ============================================

    def _get_clip_notes(self, track_index, clip_index):
        """Get all MIDI notes from a clip"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]

            if clip_index < 0 or clip_index >= len(track.clip_slots):
                raise IndexError("Clip index out of range")

            clip_slot = track.clip_slots[clip_index]

            if not clip_slot.has_clip:
                raise ValueError("No clip in slot")

            clip = clip_slot.clip

            if not clip.is_midi_clip:
                raise ValueError("Clip is not a MIDI clip")

            # Get notes using get_notes_extended if available, otherwise get_notes
            notes = []
            if hasattr(clip, 'get_notes_extended'):
                # get_notes_extended(from_pitch, pitch_span, from_time, time_span)
                raw_notes = clip.get_notes_extended(0, 128, 0.0, clip.length)
                for note in raw_notes:
                    notes.append({
                        "pitch": note.pitch,
                        "start_time": note.start_time,
                        "duration": note.duration,
                        "velocity": note.velocity,
                        "mute": note.mute
                    })
            else:
                # Fallback for older versions
                raw_notes = clip.get_notes(0.0, 0, clip.length, 128)
                for note in raw_notes:
                    notes.append({
                        "pitch": note[0],
                        "start_time": note[1],
                        "duration": note[2],
                        "velocity": note[3],
                        "mute": note[4] if len(note) > 4 else False
                    })

            return {
                "track_index": track_index,
                "clip_index": clip_index,
                "clip_name": clip.name,
                "length": clip.length,
                "note_count": len(notes),
                "notes": notes
            }
        except Exception as e:
            self.log_message("Error getting clip notes: " + str(e))
            raise

    def _get_arrangement_clip_notes(self, track_index, clip_index):
        """Get all MIDI notes from an arrangement clip"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]

            if not hasattr(track, 'arrangement_clips'):
                raise RuntimeError("arrangement_clips not available (requires Live 11+)")

            if clip_index < 0 or clip_index >= len(track.arrangement_clips):
                raise IndexError("Clip index out of range")

            clip = track.arrangement_clips[clip_index]

            if not clip.is_midi_clip:
                raise ValueError("Clip is not a MIDI clip")

            # Get notes using get_notes_extended if available, otherwise get_notes
            notes = []
            if hasattr(clip, 'get_notes_extended'):
                # get_notes_extended(from_pitch, pitch_span, from_time, time_span)
                raw_notes = clip.get_notes_extended(0, 128, 0.0, clip.length)
                for note in raw_notes:
                    notes.append({
                        "pitch": note.pitch,
                        "start_time": note.start_time,
                        "duration": note.duration,
                        "velocity": note.velocity,
                        "mute": note.mute
                    })
            else:
                # Fallback for older versions
                raw_notes = clip.get_notes(0.0, 0, clip.length, 128)
                for note in raw_notes:
                    notes.append({
                        "pitch": note[0],
                        "start_time": note[1],
                        "duration": note[2],
                        "velocity": note[3],
                        "mute": note[4] if len(note) > 4 else False
                    })

            return {
                "track_index": track_index,
                "clip_index": clip_index,
                "clip_name": clip.name,
                "start_time": clip.start_time,
                "length": clip.length,
                "note_count": len(notes),
                "notes": notes
            }
        except Exception as e:
            self.log_message("Error getting arrangement clip notes: " + str(e))
            raise

    def _duplicate_clip(self, track_index, source_slot, dest_slot):
        """Duplicate a clip to another slot"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]

            if source_slot < 0 or source_slot >= len(track.clip_slots):
                raise IndexError("Source slot index out of range")

            if dest_slot < 0 or dest_slot >= len(track.clip_slots):
                raise IndexError("Destination slot index out of range")

            source_clip_slot = track.clip_slots[source_slot]
            dest_clip_slot = track.clip_slots[dest_slot]

            if not source_clip_slot.has_clip:
                raise ValueError("No clip in source slot")

            if dest_clip_slot.has_clip:
                raise ValueError("Destination slot already has a clip")

            # Use duplicate_clip_to if available
            if hasattr(source_clip_slot, 'duplicate_clip_to'):
                source_clip_slot.duplicate_clip_to(dest_clip_slot)
            else:
                raise RuntimeError("duplicate_clip_to not available")

            return {
                "source_slot": source_slot,
                "dest_slot": dest_slot,
                "clip_name": dest_clip_slot.clip.name if dest_clip_slot.has_clip else "Unknown"
            }
        except Exception as e:
            self.log_message("Error duplicating clip: " + str(e))
            raise

    def _set_clip_loop(self, track_index, clip_index, loop_start, loop_end):
        """Set the loop points of a clip"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]

            if clip_index < 0 or clip_index >= len(track.clip_slots):
                raise IndexError("Clip index out of range")

            clip_slot = track.clip_slots[clip_index]

            if not clip_slot.has_clip:
                raise ValueError("No clip in slot")

            clip = clip_slot.clip
            clip.looping = True
            clip.loop_start = loop_start
            clip.loop_end = loop_end

            return {
                "clip_name": clip.name,
                "loop_start": clip.loop_start,
                "loop_end": clip.loop_end,
                "looping": clip.looping
            }
        except Exception as e:
            self.log_message("Error setting clip loop: " + str(e))
            raise

    def _set_clip_start_end(self, track_index, clip_index, start, end):
        """Set the start and end markers of a clip"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]

            if clip_index < 0 or clip_index >= len(track.clip_slots):
                raise IndexError("Clip index out of range")

            clip_slot = track.clip_slots[clip_index]

            if not clip_slot.has_clip:
                raise ValueError("No clip in slot")

            clip = clip_slot.clip
            clip.start_marker = start
            clip.end_marker = end

            return {
                "clip_name": clip.name,
                "start_marker": clip.start_marker,
                "end_marker": clip.end_marker
            }
        except Exception as e:
            self.log_message("Error setting clip start/end: " + str(e))
            raise

    def _clear_clip_notes(self, track_index, clip_index):
        """Clear all notes from a MIDI clip"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]

            if clip_index < 0 or clip_index >= len(track.clip_slots):
                raise IndexError("Clip index out of range")

            clip_slot = track.clip_slots[clip_index]

            if not clip_slot.has_clip:
                raise ValueError("No clip in slot")

            clip = clip_slot.clip

            if not clip.is_midi_clip:
                raise ValueError("Clip is not a MIDI clip")

            # Remove all notes using remove_notes_extended if available
            if hasattr(clip, 'remove_notes_extended'):
                clip.remove_notes_extended(0, 128, 0.0, clip.length)
            else:
                # Fallback: use remove_notes
                clip.remove_notes(0.0, 0, clip.length, 128)

            return {
                "clip_name": clip.name,
                "cleared": True
            }
        except Exception as e:
            self.log_message("Error clearing clip notes: " + str(e))
            raise

    # ============================================
    # AUDIO TRACK SUPPORT
    # ============================================

    def _create_audio_track(self, index):
        """Create a new audio track at the specified index"""
        try:
            self._song.create_audio_track(index)

            new_track_index = len(self._song.tracks) - 1 if index == -1 else index
            new_track = self._song.tracks[new_track_index]

            return {
                "index": new_track_index,
                "name": new_track.name
            }
        except Exception as e:
            self.log_message("Error creating audio track: " + str(e))
            raise

    def _delete_track(self, track_index, track_name):
        """Delete a track at the specified index, with name verification for safety"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]
            actual_name = track.name

            # Safety check: verify track name matches
            if actual_name != track_name:
                raise ValueError(
                    "Track name mismatch: expected '{0}' at index {1}, but found '{2}'. "
                    "Track indices may have shifted.".format(track_name, track_index, actual_name)
                )

            self._song.delete_track(track_index)

            return {
                "success": True,
                "deleted_track": actual_name,
                "deleted_index": track_index
            }
        except Exception as e:
            self.log_message("Error deleting track: " + str(e))
            raise

    def _get_cue_points(self):
        """Get all cue points (locators) in the arrangement"""
        try:
            cue_points = []
            for cue in self._song.cue_points:
                cue_points.append({
                    "time": cue.time,
                    "name": cue.name
                })
            # Sort by time
            cue_points.sort(key=lambda x: x["time"])
            return {
                "cue_points": cue_points,
                "count": len(cue_points)
            }
        except Exception as e:
            self.log_message("Error getting cue points: " + str(e))
            raise

    def _create_cue_point(self, time):
        """Create a cue point (locator) at the specified time"""
        try:
            # First check if a cue point already exists at this time
            existing_cue = None
            for cue in self._song.cue_points:
                if abs(cue.time - time) < 0.001:  # Float comparison tolerance
                    existing_cue = cue
                    break

            if existing_cue is None:
                # Save current song time, move to target, create cue, restore
                original_time = self._song.current_song_time
                self._song.current_song_time = time
                self._song.set_or_delete_cue()
                self._song.current_song_time = original_time

            return {
                "success": True,
                "time": time
            }
        except Exception as e:
            self.log_message("Error creating cue point: " + str(e))
            raise

    def _delete_cue_point(self, time):
        """Delete a cue point at the specified time"""
        try:
            # Check if cue point exists at this time
            cue_exists = False
            for cue in self._song.cue_points:
                if abs(cue.time - time) < 0.001:
                    cue_exists = True
                    break

            if not cue_exists:
                raise ValueError("No cue point found at time {0}".format(time))

            # Save current song time, move to target, delete cue, restore
            original_time = self._song.current_song_time
            self._song.current_song_time = time
            self._song.set_or_delete_cue()
            self._song.current_song_time = original_time

            return {
                "success": True,
                "deleted_time": time
            }
        except Exception as e:
            self.log_message("Error deleting cue point: " + str(e))
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
