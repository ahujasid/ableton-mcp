# AbletonMCP/init.py
from __future__ import absolute_import, print_function, unicode_literals

from _Framework.ControlSurface import ControlSurface
import os
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
HOST = "0.0.0.0"
SUPPORTED_COMMANDS = [
    "get_session_info",
    "get_track_info",
    "get_device_info",
    "get_device_parameters",
    "get_browser_tree",
    "get_browser_items_at_path",
    "get_browser_item",
    "get_browser_categories",
    "get_browser_items",
    "search_browser_items",
    "list_supported_commands",
    "create_midi_track",
    "create_audio_track",
    "create_scene",
    "append_scene",
    "set_track_name",
    "create_clip",
    "create_audio_clip",
    "add_notes_to_clip",
    "set_clip_name",
    "set_tempo",
    "fire_clip",
    "stop_clip",
    "start_playback",
    "stop_playback",
    "load_instrument_or_effect",
    "load_browser_item",
    "set_device_parameter",
    "set_device_parameter_by_name",
    "execute_batch",
    "switch_to_arrangement_view",
    "set_current_song_time",
    "get_arrangement_clips",
    "duplicate_session_clip_to_arrangement",
    "duplicate_clip_to_arrangement",
    "duplicate_scene_to_arrangement",
    "back_to_arrangement",
    "stop_all_clips",
    "export_audio"
]

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
            except Exception:
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
                    except Exception:
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
            except Exception:
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
            elif command_type == "get_device_info":
                track_index = params.get("track_index", 0)
                device_index = params.get("device_index", 0)
                response["result"] = self._get_device_info(track_index, device_index)
            elif command_type == "get_device_parameters":
                track_index = params.get("track_index", 0)
                device_index = params.get("device_index", 0)
                response["result"] = self._get_device_parameters(track_index, device_index)
            elif command_type == "list_supported_commands":
                response["result"] = {"commands": SUPPORTED_COMMANDS}
            # Commands that modify Live's state should be scheduled on the main thread
            elif command_type in ["create_midi_track", "create_audio_track",
                                 "create_scene", "append_scene", "set_track_name",
                                 "create_clip", "create_audio_clip", "add_notes_to_clip", "set_clip_name",
                                 "set_tempo", "fire_clip", "stop_clip",
                                 "start_playback", "stop_playback",
                                 "load_instrument_or_effect", "load_browser_item",
                                 "set_device_parameter", "set_device_parameter_by_name",
                                 "execute_batch",
                                 "switch_to_arrangement_view", "set_current_song_time",
                                 "duplicate_session_clip_to_arrangement",
                                 "duplicate_clip_to_arrangement",
                                 "duplicate_scene_to_arrangement",
                                 "back_to_arrangement", "stop_all_clips",
                                 "export_audio"]:
                # Use a thread-safe approach with a response queue
                response_queue = queue.Queue()
                
                # Define a function to execute on the main thread
                def main_thread_task():
                    try:
                        result = None
                        deferred_response = False
                        if command_type == "create_midi_track":
                            index = params.get("index", -1)
                            result = self._create_midi_track(index)
                        elif command_type == "create_audio_track":
                            index = params.get("index", -1)
                            result = self._create_audio_track(index)
                        elif command_type == "create_scene":
                            result = self._create_scene(
                                params.get("index", -1),
                                params.get("name", None)
                            )
                        elif command_type == "append_scene":
                            result = self._create_scene(-1, params.get("name", None))
                        elif command_type == "set_track_name":
                            track_index = params.get("track_index", 0)
                            name = params.get("name", "")
                            result = self._set_track_name(track_index, name)
                        elif command_type == "create_clip":
                            track_index = params.get("track_index", 0)
                            clip_index = params.get("clip_index", 0)
                            length = params.get("length", 4.0)
                            result = self._create_clip(track_index, clip_index, length)
                        elif command_type == "create_audio_clip":
                            track_index = params.get("track_index", 0)
                            clip_index = params.get("clip_index", 0)
                            path = params.get("path", "")
                            result = self._create_audio_clip(track_index, clip_index, path)
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
                        elif command_type == "set_device_parameter":
                            result = self._set_device_parameter(
                                params.get("track_index", 0),
                                params.get("device_index", 0),
                                params.get("parameter_index", 0),
                                params.get("value", 0.0)
                            )
                        elif command_type == "set_device_parameter_by_name":
                            result = self._set_device_parameter_by_name(
                                params.get("track_index", 0),
                                params.get("device_index", 0),
                                params.get("parameter_name", ""),
                                params.get("value", 0.0)
                            )
                        elif command_type == "execute_batch":
                            result = self._execute_batch(
                                params.get("commands", []),
                                params.get("stop_on_error", True)
                            )
                        elif command_type == "duplicate_clip_to_arrangement":
                            track_index = params.get("track_index", 0)
                            scene_index = params.get("scene_index", 0)
                            start_time = params.get("start_time", 0.0)
                            result = self._duplicate_clip_to_arrangement(
                                track_index, scene_index, start_time
                            )
                        elif command_type == "duplicate_scene_to_arrangement":
                            scene_index = params.get("scene_index", 0)
                            start_time = params.get("start_time", 0.0)
                            track_indices = params.get("track_indices", None)
                            result = self._duplicate_scene_to_arrangement(
                                scene_index, start_time, track_indices
                            )
                        elif command_type == "back_to_arrangement":
                            result = self._back_to_arrangement()
                            deferred_response = True

                            def verify_back_to_arrangement(result=result):
                                result = self._verify_back_to_arrangement(result)
                                response_queue.put({"status": "success", "result": result})

                            self.schedule_message(2, verify_back_to_arrangement)
                        elif command_type == "stop_all_clips":
                            result = self._stop_all_clips()
                            deferred_response = True

                            def verify_stop_all_clips(result=result):
                                result = self._verify_stop_all_clips(result)
                                response_queue.put({"status": "success", "result": result})

                            self.schedule_message(2, verify_stop_all_clips)
                        elif command_type == "export_audio":
                            result = self._export_audio(
                                params.get("output_path", ""),
                                params.get("render_start_bar", 1),
                                params.get("render_start_beat", 1),
                                params.get("render_start_sixteenth", 1),
                                params.get("render_length_bars", 0),
                                params.get("render_length_beats", 0),
                                params.get("render_length_sixteenths", 0),
                                params.get("rendered_track", "Main"),
                                params.get("file_type", "AIFF"),
                                params.get("encode_mp3", False),
                                params.get("normalize", False),
                                params.get("create_analysis_file", False)
                            )
                        elif command_type == "start_playback":
                            result = self._start_playback()
                        elif command_type == "stop_playback":
                            result = self._stop_playback()
                        elif command_type == "load_instrument_or_effect":
                            track_index = params.get("track_index", 0)
                            uri = params.get("uri", "")
                            result = self._load_browser_item(track_index, uri)
                            deferred_response = True

                            def verify_load_instrument_or_effect(result=result):
                                result = self._verify_load_browser_item(result)
                                response_queue.put({"status": "success", "result": result})

                            self.schedule_message(4, verify_load_instrument_or_effect)
                        elif command_type == "load_browser_item":
                            track_index = params.get("track_index", 0)
                            item_uri = params.get("item_uri", "")
                            result = self._load_browser_item(track_index, item_uri)
                            deferred_response = True

                            def verify_load_browser_item(result=result):
                                result = self._verify_load_browser_item(result)
                                response_queue.put({"status": "success", "result": result})

                            self.schedule_message(4, verify_load_browser_item)
                        # ── Arrangement view commands ──────────────────────────────
                        elif command_type == "switch_to_arrangement_view":
                            result = self._switch_to_arrangement_view()
                        elif command_type == "set_current_song_time":
                            time_val = params.get("time", 0.0)
                            result = self._set_current_song_time(time_val)
                        elif command_type == "duplicate_session_clip_to_arrangement":
                            track_index = params.get("track_index", 0)
                            clip_index = params.get("clip_index", 0)
                            destination_time = params.get("destination_time", 0.0)
                            result = self._duplicate_session_clip_to_arrangement(
                                track_index, clip_index, destination_time)
                        # Put the result in the queue
                        if not deferred_response:
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
                
                # Wait for the response with a timeout. Some commands (notably
                # create_audio_clip, which decodes/imports the audio file on
                # the main thread) can take longer than the default 10s on
                # larger files — give them more headroom.
                long_running_commands = {"create_audio_clip": 60.0}
                queue_timeout = long_running_commands.get(command_type, 10.0)
                try:
                    task_response = response_queue.get(timeout=queue_timeout)
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
            elif command_type == "search_browser_items":
                query = params.get("query", "")
                category = params.get("category", None)
                max_results = params.get("max_results", 20)
                response["result"] = self.search_browser_items(query, category, max_results)
            # Read-only arrangement command – no main-thread scheduling required
            elif command_type == "get_arrangement_clips":
                track_index = params.get("track_index", 0)
                response["result"] = self._get_arrangement_clips(track_index)
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
    
    def _safe_song_property(self, attr, cast, default):
        """Read self._song.<attr> with cast, returning default on common failures.
        Catches only narrow exceptions so genuine bugs still surface."""
        try:
            return cast(getattr(self._song, attr))
        except (AttributeError, TypeError, ValueError):
            return default

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
                },
                # Transport / playback state — lets clients render a live
                # playhead without polling separately. Each property is read
                # via _safe_song_property so an attribute missing on a given
                # Live version falls back to its default rather than breaking
                # the response shape.
                "is_playing":        self._safe_song_property("is_playing",        bool,  False),
                "current_song_time": self._safe_song_property("current_song_time", float, 0.0),
                "song_length":       self._safe_song_property("song_length",       float, 0.0),
                "loop":              self._safe_song_property("loop",              bool,  False),
                "loop_start":        self._safe_song_property("loop_start",        float, 0.0),
                "loop_length":       self._safe_song_property("loop_length",       float, 0.0),
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
                "devices": self._get_track_devices(track)
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
            self._song.create_audio_track(index)

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

    def _create_scene(self, index=-1, name=None):
        """Create a new Session scene."""
        try:
            scene_count_before = len(self._song.scenes)
            self._song.create_scene(index)
            scene_index = len(self._song.scenes) - 1 if index == -1 else index
            scene = self._song.scenes[scene_index]
            if name is not None:
                scene.name = name

            return {
                "index": scene_index,
                "name": scene.name,
                "scene_count_before": scene_count_before,
                "scene_count_after": len(self._song.scenes)
            }
        except Exception as e:
            self.log_message("Error creating scene: " + str(e))
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
            auto_created_scene = None

            if clip_index < 0:
                raise IndexError("Clip index out of range; valid range is 0-{0}".format(len(track.clip_slots) - 1))
            if clip_index == len(track.clip_slots):
                auto_created_scene = self._create_scene(-1)
                track = self._song.tracks[track_index]
            elif clip_index > len(track.clip_slots):
                raise IndexError("Clip index out of range; valid range is 0-{0}, or {1} to append a scene".format(
                    len(track.clip_slots) - 1,
                    len(track.clip_slots)
                ))
            
            clip_slot = track.clip_slots[clip_index]
            
            # Check if the clip slot already has a clip
            if clip_slot.has_clip:
                raise Exception("Clip slot already has a clip")
            
            # Create the clip
            clip_slot.create_clip(length)
            
            result = {
                "name": clip_slot.clip.name,
                "length": clip_slot.clip.length,
                "track_index": track_index,
                "clip_index": clip_index,
                "scene_count": len(self._song.scenes),
                "auto_created_scene": auto_created_scene
            }
            return result
        except Exception as e:
            self.log_message("Error creating clip: " + str(e))
            raise

    def _create_audio_clip(self, track_index, clip_index, path):
        """Create an audio clip in the specified audio track clip slot by importing a file.

        Requires Ableton Live 12.0.5 or newer (the underlying
        ClipSlot.create_audio_clip Live API was introduced in 12.0.5 — it is
        not available in earlier 12.0.x releases).
        """
        try:
            if not path:
                raise ValueError("Audio file path is required")

            if not os.path.isabs(path):
                raise ValueError("Audio file path must be absolute (got: %s)" % path)

            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]

            # Must be an audio track. Audio tracks expose audio input; MIDI
            # tracks don't. Reject MIDI / return tracks up front so the caller
            # gets a clear error instead of a Live API exception.
            if getattr(track, "has_midi_input", False) or not getattr(track, "has_audio_input", True):
                raise ValueError("Track %d is not an audio track" % track_index)

            if clip_index < 0 or clip_index >= len(track.clip_slots):
                raise IndexError("Clip index out of range")

            clip_slot = track.clip_slots[clip_index]

            if clip_slot.has_clip:
                raise Exception("Clip slot already has a clip")

            if not hasattr(clip_slot, "create_audio_clip"):
                raise Exception(
                    "ClipSlot.create_audio_clip is unavailable in this Ableton Live "
                    "version. Requires Live 12.0.5 or newer."
                )

            clip_slot.create_audio_clip(path)

            result = {
                "name": clip_slot.clip.name,
                "length": clip_slot.clip.length,
                "is_audio_clip": clip_slot.clip.is_audio_clip
            }
            return result
        except Exception as e:
            self.log_message("Error creating audio clip: " + str(e))
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

    def _duplicate_clip_to_arrangement(self, track_index, scene_index, start_time):
        """Duplicate one Session clip into Arrangement."""
        result = {
            "success": False,
            "scene_index": scene_index,
            "start_time": start_time,
            "duplicated": [],
            "skipped": [],
            "arrangement_clip_count_before": None,
            "arrangement_clip_count_after": None
        }
        
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            
            track = self._song.tracks[track_index]
            if scene_index < 0 or scene_index >= len(track.clip_slots):
                raise IndexError("Scene index out of range")
            
            slot = track.clip_slots[scene_index]
            if not slot.has_clip:
                result["skipped"].append({
                    "track_index": track_index,
                    "track_name": track.name,
                    "reason": "empty_slot"
                })
                result["success"] = True
                return result
            
            clip = slot.clip
            result["arrangement_clip_count_before"] = len(track.arrangement_clips)
            track.duplicate_clip_to_arrangement(clip, float(start_time))
            result["arrangement_clip_count_after"] = len(track.arrangement_clips)
            result["duplicated"].append({
                "track_index": track_index,
                "track_name": track.name,
                "clip_name": clip.name,
                "arrangement_clip_count_before": result["arrangement_clip_count_before"],
                "arrangement_clip_count_after": result["arrangement_clip_count_after"]
            })
            result["success"] = result["arrangement_clip_count_after"] > result["arrangement_clip_count_before"]
            return result
        except Exception as e:
            result["error"] = str(e)
            self.log_message("Error duplicating clip to arrangement: " + str(e))
            self.log_message(traceback.format_exc())
            return result

    def _duplicate_scene_to_arrangement(self, scene_index, start_time, track_indices=None):
        """Duplicate all clips in a Session scene into Arrangement at start_time."""
        result = {
            "success": False,
            "scene_index": scene_index,
            "start_time": start_time,
            "duplicated": [],
            "skipped": []
        }
        
        try:
            tracks = self._song.tracks
            
            if track_indices is None:
                selected_track_indices = range(len(tracks))
            else:
                if not isinstance(track_indices, list):
                    raise TypeError("track_indices must be a list of zero-based track indices")
                selected_track_indices = track_indices
            
            for track_index in selected_track_indices:
                if track_index < 0 or track_index >= len(tracks):
                    result["skipped"].append({
                        "track_index": track_index,
                        "track_name": "",
                        "reason": "track_index_out_of_range"
                    })
                    continue
                
                track = tracks[track_index]
                if scene_index < 0 or scene_index >= len(track.clip_slots):
                    result["skipped"].append({
                        "track_index": track_index,
                        "track_name": track.name,
                        "reason": "scene_index_out_of_range"
                    })
                    continue
                
                slot = track.clip_slots[scene_index]
                if not slot.has_clip:
                    result["skipped"].append({
                        "track_index": track_index,
                        "track_name": track.name,
                        "reason": "empty_slot"
                    })
                    continue
                
                clip = slot.clip
                arrangement_clip_count_before = len(track.arrangement_clips)
                track.duplicate_clip_to_arrangement(clip, float(start_time))
                arrangement_clip_count_after = len(track.arrangement_clips)
                result["duplicated"].append({
                    "track_index": track_index,
                    "track_name": track.name,
                    "clip_name": clip.name,
                    "arrangement_clip_count_before": arrangement_clip_count_before,
                    "arrangement_clip_count_after": arrangement_clip_count_after
                })
            
            result["success"] = len(result["duplicated"]) > 0 and all(
                item["arrangement_clip_count_after"] > item["arrangement_clip_count_before"]
                for item in result["duplicated"]
            )
            return result
        except Exception as e:
            result["error"] = str(e)
            self.log_message("Error duplicating scene to arrangement: " + str(e))
            self.log_message(traceback.format_exc())
            return result

    def _get_playing_session_clips(self):
        """Return currently playing or triggered Session clips for verification."""
        playing = []
        for track_index, track in enumerate(self._song.tracks):
            for slot_index, slot in enumerate(track.clip_slots):
                clip_info = None
                if slot.has_clip:
                    clip = slot.clip
                    if clip.is_playing or clip.is_triggered:
                        clip_info = {
                            "track_index": track_index,
                            "track_name": track.name,
                            "slot_index": slot_index,
                            "clip_name": clip.name,
                            "is_playing": bool(clip.is_playing),
                            "is_triggered": bool(clip.is_triggered)
                        }
                if clip_info:
                    playing.append(clip_info)
        return playing

    def _back_to_arrangement(self):
        """Re-enable Arrangement playback when Session clips have taken over."""
        result = {
            "success": False,
            "back_to_arranger_before": None,
            "back_to_arranger_after": None,
            "playing_before": [],
            "playing_after": []
        }
        
        try:
            result["back_to_arranger_before"] = bool(self._song.back_to_arranger)
            result["playing_before"] = self._get_playing_session_clips()
            self._song.stop_all_clips(False)
            self._song.back_to_arranger = False
            return result
        except Exception as e:
            result["error"] = str(e)
            self.log_message("Error returning to arrangement: " + str(e))
            self.log_message(traceback.format_exc())
            return result

    def _verify_back_to_arrangement(self, result):
        """Verify Arrangement playback was re-enabled after Live updates state."""
        try:
            result["back_to_arranger_after"] = bool(self._song.back_to_arranger)
            result["playing_after"] = self._get_playing_session_clips()
            result["success"] = (
                not result["back_to_arranger_after"] and
                len(result["playing_after"]) == 0
            )
            return result
        except Exception as e:
            result["error"] = str(e)
            self.log_message("Error verifying return to arrangement: " + str(e))
            self.log_message(traceback.format_exc())
            return result

    def _stop_all_clips(self):
        """Stop all Session clips."""
        result = {
            "success": False,
            "playing_before": [],
            "playing_after": []
        }
        
        try:
            result["playing_before"] = self._get_playing_session_clips()
            self._song.stop_all_clips(False)
            return result
        except Exception as e:
            result["error"] = str(e)
            self.log_message("Error stopping all clips: " + str(e))
            self.log_message(traceback.format_exc())
            return result

    def _verify_stop_all_clips(self, result):
        """Verify Session clips stopped after Live updates state."""
        try:
            result["playing_after"] = self._get_playing_session_clips()
            result["success"] = len(result["playing_after"]) == 0
            return result
        except Exception as e:
            result["error"] = str(e)
            self.log_message("Error verifying stopped clips: " + str(e))
            self.log_message(traceback.format_exc())
            return result

    def _export_audio(self, output_path, render_start_bar, render_start_beat,
                      render_start_sixteenth, render_length_bars,
                      render_length_beats, render_length_sixteenths,
                      rendered_track="Main", file_type="AIFF",
                      encode_mp3=False, normalize=False,
                      create_analysis_file=False):
        """Audio export is not implemented by the documented Live API."""
        raise NotImplementedError("export_audio is not implemented by AbletonMCP")
    
    
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
    
    # ── Arrangement view implementations ──────────────────────────────────────

    def _switch_to_arrangement_view(self):
        """Switch Ableton's main window to the Arrangement view"""
        try:
            self.application().view.show_view("Arranger")
            return {"view": "Arranger"}
        except Exception as e:
            self.log_message("Error switching to arrangement view: " + str(e))
            raise

    def _set_current_song_time(self, time_val):
        """Move the arrangement playhead to a position in beats"""
        try:
            self._song.current_song_time = float(time_val)
            return {"current_song_time": self._song.current_song_time}
        except Exception as e:
            self.log_message("Error setting current song time: " + str(e))
            raise

    def _get_arrangement_clips(self, track_index):
        """Return all clips placed in the Arrangement timeline for a track.

        Each clip dict contains:
          name, start_time, end_time, length, color,
          is_midi_clip, is_audio_clip, is_playing
        """
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]
            clips = []

            # track.arrangement_clips is available in Live 11 / 12
            for clip in track.arrangement_clips:
                clips.append({
                    "name": clip.name,
                    "start_time": clip.start_time,
                    "end_time": clip.end_time,
                    "length": clip.length,
                    "color": clip.color,
                    "is_midi_clip": clip.is_midi_clip,
                    "is_audio_clip": clip.is_audio_clip,
                    "is_playing": clip.is_playing
                })

            return {
                "track_index": track_index,
                "track_name": track.name,
                "clip_count": len(clips),
                "clips": clips
            }
        except Exception as e:
            self.log_message("Error getting arrangement clips: " + str(e))
            raise

    def _duplicate_session_clip_to_arrangement(self, track_index, clip_index, destination_time):
        """Copy a Session-view clip into the Arrangement timeline.

        Uses the real Live API:
          track.duplicate_clip_to_arrangement(clip, destination_time)

        Available in Live 11 / 12.  destination_time is in beats from the
        start of the arrangement.
        """
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]

            if clip_index < 0 or clip_index >= len(track.clip_slots):
                raise IndexError("Clip slot index out of range")

            clip_slot = track.clip_slots[clip_index]

            if not clip_slot.has_clip:
                raise Exception(
                    "No clip in slot " + str(clip_index) +
                    " on track " + str(track_index)
                )

            clip = clip_slot.clip

            # Duplicate to arrangement at the requested beat position
            track.duplicate_clip_to_arrangement(clip, float(destination_time))

            return {
                "success": True,
                "track_index": track_index,
                "track_name": track.name,
                "clip_name": clip.name,
                "destination_time": destination_time
            }
        except Exception as e:
            self.log_message("Error duplicating clip to arrangement: " + str(e))
            raise

    # ── Browser implementations ───────────────────────────────────────────────

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
                if path_parts[0].lower() == "instruments":
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
            if hasattr(item, "is_loadable") and not item.is_loadable:
                raise ValueError("Browser item with URI '{0}' is not loadable".format(item_uri))
            
            # Select the track
            self._song.view.selected_track = track
            devices_before = self._get_track_devices(track)
            clip_slots_before = self._get_clip_slot_summary(track)
            
            # Load the item
            app.browser.load_item(item)
            
            result = {
                "loaded": False,
                "item_name": item.name,
                "track_name": track.name,
                "track_index": track_index,
                "uri": item_uri,
                "is_loadable": item.is_loadable if hasattr(item, "is_loadable") else None,
                "devices_before": devices_before,
                "devices_after": [],
                "new_devices": [],
                "inserted_device_name": None,
                "inserted_device_index": None,
                "device_count_before": len(devices_before),
                "device_count_after": None,
                "clip_slots_before": clip_slots_before,
                "clip_slots_after": [],
                "new_clips": [],
                "clip_count_before": len([slot for slot in clip_slots_before if slot.get("has_clip")]),
                "clip_count_after": None
            }
            return result
        except Exception as e:
            self.log_message("Error loading browser item: {0}".format(str(e)))
            self.log_message(traceback.format_exc())
            raise

    def _verify_load_browser_item(self, result):
        """Verify a browser item load changed the target track's devices."""
        try:
            track_index = result.get("track_index", 0)
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]
            devices_after = self._get_track_devices(track)
            devices_before = result.get("devices_before", [])
            clip_slots_after = self._get_clip_slot_summary(track)
            clip_slots_before = result.get("clip_slots_before", [])
            inserted_devices = self._find_inserted_devices(devices_before, devices_after)
            new_clips = self._find_new_clips(clip_slots_before, clip_slots_after)
            result["devices_after"] = devices_after
            result["new_devices"] = [device.get("name") for device in inserted_devices]
            if inserted_devices:
                result["inserted_device_name"] = inserted_devices[0].get("name")
                result["inserted_device_index"] = inserted_devices[0].get("index")
            result["clip_slots_after"] = clip_slots_after
            result["new_clips"] = new_clips
            result["device_count_after"] = len(devices_after)
            result["clip_count_after"] = len([slot for slot in clip_slots_after if slot.get("has_clip")])
            result["loaded"] = bool(inserted_devices or new_clips)
            if not result["loaded"]:
                result["error"] = "Browser item load did not change the target track's devices or clips"
            return result
        except Exception as e:
            result["error"] = str(e)
            self.log_message("Error verifying browser item load: {0}".format(str(e)))
            self.log_message(traceback.format_exc())
            return result
    
    # Substring markers that point a URI at a likely root. If no marker
    # matches we fall back to the default order, so this is purely an
    # optimisation — never a correctness change.
    _URI_ROOT_HINTS = (
        ('plugins',       ('vst:', 'vst3:', 'au:', 'query:plugins', 'plugin#')),
        ('max_for_live',  ('max for live', 'maxforlive', 'm4l', 'query:max')),
        ('user_library',  ('user library', 'userlibrary', 'query:user library', 'query:user-library')),
        ('packs',         ('query:packs', '/packs/')),
        ('samples',       ('query:samples', 'sample:', '/samples/')),
        ('drums',         ('query:drums', '/drums/')),
        ('instruments',   ('query:instruments', '/instruments/')),
        ('sounds',        ('query:sounds', '/sounds/')),
        ('audio_effects', ('query:audio effects', 'audioeffects', '/audio_effects/')),
        ('midi_effects',  ('query:midi effects', 'midieffects', '/midi_effects/')),
    )

    def _order_roots_by_uri(self, roots, uri):
        """Reorder ``roots`` so the URI's likely root is walked first."""
        if not isinstance(uri, (bytes, str)) or not uri:
            return roots
        lowered = uri.lower()
        for attr, markers in self._URI_ROOT_HINTS:
            if any(m in lowered for m in markers):
                head = [(a, r) for (a, r) in roots if a == attr]
                tail = [(a, r) for (a, r) in roots if a != attr]
                return head + tail
        return roots

    def _find_browser_item_by_uri(self, browser_or_item, uri, max_depth=10, current_depth=0):
        """Find a browser item by its URI.

        Top-level lookups are memoised on ``self._uri_cache`` so repeated
        loads of the same URI don't re-walk the entire browser tree.
        """
        if current_depth == 0:
            cache = getattr(self, '_uri_cache', None)
            if cache is None:
                self._uri_cache = cache = {}
            if uri in cache:
                return cache[uri]
            result = self._walk_browser_for_uri(browser_or_item, uri, max_depth, 0)
            if result is not None:
                cache[uri] = result
            return result
        return self._walk_browser_for_uri(browser_or_item, uri, max_depth, current_depth)

    def _walk_browser_for_uri(self, browser_or_item, uri, max_depth, current_depth):
        """Recursive walk used by :py:meth:`_find_browser_item_by_uri`."""
        try:
            # Check if this is the item we're looking for
            if hasattr(browser_or_item, 'uri') and browser_or_item.uri == uri:
                return browser_or_item

            # Stop recursion if we've reached max depth
            if current_depth >= max_depth:
                return None

            # Check if this is a browser with root categories
            if hasattr(browser_or_item, 'instruments'):
                roots = [
                    ('instruments', browser_or_item.instruments),
                    ('sounds', browser_or_item.sounds),
                    ('drums', browser_or_item.drums),
                    ('audio_effects', browser_or_item.audio_effects),
                    ('midi_effects', browser_or_item.midi_effects),
                ]
                for extra_attr in ('plugins', 'max_for_live', 'user_library', 'packs', 'samples'):
                    if hasattr(browser_or_item, extra_attr):
                        try:
                            roots.append((extra_attr, getattr(browser_or_item, extra_attr)))
                        except (AttributeError, RuntimeError) as e:
                            self.log_message("Could not access browser.{0}: {1}".format(extra_attr, str(e)))

                for _attr, category in self._order_roots_by_uri(roots, uri):
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

    def _safe_getattr(self, obj, attr, default=None):
        """Read a Live API attribute that may raise when unavailable."""
        try:
            if hasattr(obj, attr):
                return getattr(obj, attr)
        except Exception:
            return default
        return default

    def _get_track_devices(self, track):
        """Return device details for a track."""
        devices = []
        for device_index, device in enumerate(track.devices):
            devices.append({
                "index": device_index,
                "name": device.name,
                "class_name": device.class_name,
                "type": self._get_device_type(device)
            })
        return devices

    def _device_key(self, device_info):
        """Return a stable comparison key for serialized device info."""
        return (
            device_info.get("name"),
            device_info.get("class_name"),
            device_info.get("type")
        )

    def _find_inserted_devices(self, devices_before, devices_after):
        """Find inserted devices without assuming Live appends them."""
        remaining_before = {}
        for device in devices_before:
            key = self._device_key(device)
            remaining_before[key] = remaining_before.get(key, 0) + 1

        inserted = []
        for device in devices_after:
            key = self._device_key(device)
            if remaining_before.get(key, 0):
                remaining_before[key] -= 1
            else:
                inserted.append(device)
        return inserted

    def _get_clip_slot_summary(self, track):
        """Return lightweight clip-slot state for load verification."""
        slots = []
        for slot_index, slot in enumerate(track.clip_slots):
            has_clip = bool(slot.has_clip)
            slots.append({
                "index": slot_index,
                "has_clip": has_clip,
                "clip_name": slot.clip.name if has_clip else None
            })
        return slots

    def _find_new_clips(self, slots_before, slots_after):
        """Find clip slots that gained a clip."""
        had_clip = {}
        for slot in slots_before:
            had_clip[slot.get("index")] = bool(slot.get("has_clip"))

        new_clips = []
        for slot in slots_after:
            if slot.get("has_clip") and not had_clip.get(slot.get("index"), False):
                new_clips.append({
                    "slot_index": slot.get("index"),
                    "clip_name": slot.get("clip_name")
                })
        return new_clips

    def _get_track(self, track_index):
        """Return a track by zero-based index."""
        if track_index < 0 or track_index >= len(self._song.tracks):
            raise IndexError("Track index out of range")
        return self._song.tracks[track_index]

    def _get_device(self, track_index, device_index):
        """Return a device by track and device index."""
        track = self._get_track(track_index)
        if device_index < 0 or device_index >= len(track.devices):
            raise IndexError("Device index out of range")
        return track.devices[device_index]

    def _get_parameter_info(self, parameter, parameter_index):
        """Return serializable parameter info."""
        return {
            "index": parameter_index,
            "name": self._safe_getattr(parameter, "name", ""),
            "original_name": self._safe_getattr(parameter, "original_name", None),
            "value": self._safe_getattr(parameter, "value", None),
            "default_value": self._safe_getattr(parameter, "default_value", None),
            "min": self._safe_getattr(parameter, "min", None),
            "max": self._safe_getattr(parameter, "max", None),
            "is_enabled": self._safe_getattr(parameter, "is_enabled", None),
            "is_quantized": self._safe_getattr(parameter, "is_quantized", None)
        }

    def _get_device_info(self, track_index, device_index):
        """Return device details and parameters."""
        device = self._get_device(track_index, device_index)
        return {
            "track_index": track_index,
            "device_index": device_index,
            "name": device.name,
            "class_name": device.class_name,
            "class_display_name": device.class_display_name if hasattr(device, "class_display_name") else None,
            "type": self._get_device_type(device),
            "can_have_chains": device.can_have_chains if hasattr(device, "can_have_chains") else None,
            "can_have_drum_pads": device.can_have_drum_pads if hasattr(device, "can_have_drum_pads") else None,
            "parameters": [
                self._get_parameter_info(parameter, parameter_index)
                for parameter_index, parameter in enumerate(device.parameters)
            ] if hasattr(device, "parameters") else []
        }

    def _get_device_parameters(self, track_index, device_index):
        """Return parameters for a device."""
        device = self._get_device(track_index, device_index)
        return {
            "track_index": track_index,
            "device_index": device_index,
            "device_name": device.name,
            "class_name": device.class_name,
            "parameters": [
                self._get_parameter_info(parameter, parameter_index)
                for parameter_index, parameter in enumerate(device.parameters)
            ] if hasattr(device, "parameters") else []
        }

    def _set_device_parameter(self, track_index, device_index, parameter_index, value):
        """Set a device parameter by index and verify readback."""
        device = self._get_device(track_index, device_index)
        if not hasattr(device, "parameters"):
            raise RuntimeError("Device has no parameters")
        if parameter_index < 0 or parameter_index >= len(device.parameters):
            raise IndexError("Parameter index out of range")

        parameter = device.parameters[parameter_index]
        value_before = parameter.value
        requested_value = float(value)
        parameter.value = requested_value
        value_after = parameter.value
        value_matches_requested = abs(float(value_after) - requested_value) <= 0.000001
        value_changed = abs(float(value_after) - float(value_before)) > 0.000001
        return {
            "track_index": track_index,
            "device_index": device_index,
            "device_name": device.name,
            "parameter_index": parameter_index,
            "parameter_name": parameter.name,
            "value_before": value_before,
            "requested_value": requested_value,
            "value_after": value_after,
            "value_changed": value_changed,
            "value_matches_requested": value_matches_requested,
            "success": value_matches_requested
        }

    def _set_device_parameter_by_name(self, track_index, device_index, parameter_name, value):
        """Set a device parameter by exact or case-insensitive name."""
        device = self._get_device(track_index, device_index)
        if not hasattr(device, "parameters"):
            raise RuntimeError("Device has no parameters")

        target_name = parameter_name.strip().lower()
        if not target_name:
            raise ValueError("parameter_name is required")

        for parameter_index, parameter in enumerate(device.parameters):
            names = [parameter.name]
            if hasattr(parameter, "original_name") and parameter.original_name:
                names.append(parameter.original_name)
            if target_name in [name.lower() for name in names if name]:
                result = self._set_device_parameter(track_index, device_index, parameter_index, value)
                result["matched_name"] = parameter_name
                return result

        raise ValueError("Parameter '{0}' not found".format(parameter_name))

    def _execute_batch(self, commands, stop_on_error=True):
        """Execute a simple list of commands without result references."""
        if not isinstance(commands, list):
            raise TypeError("commands must be a list")
        if len(commands) > 50:
            raise ValueError("execute_batch supports at most 50 commands")

        results = []
        for command_index, command in enumerate(commands):
            command_type = command.get("type", "")
            params = command.get("params", {})
            entry = {
                "index": command_index,
                "type": command_type,
                "status": "success",
                "result": {}
            }
            try:
                if command_type == "execute_batch":
                    raise ValueError("execute_batch cannot be nested")
                if command_type == "export_audio":
                    raise ValueError("export_audio cannot run inside execute_batch")
                entry["result"] = self._execute_batch_command(command_type, params)
            except Exception as e:
                entry["status"] = "error"
                entry["error"] = str(e)
                results.append(entry)
                if stop_on_error:
                    return {
                        "success": False,
                        "stop_on_error": bool(stop_on_error),
                        "failed_index": command_index,
                        "results": results
                    }
                continue
            results.append(entry)

        return {
            "success": all(entry["status"] == "success" for entry in results),
            "stop_on_error": bool(stop_on_error),
            "failed_index": None,
            "results": results
        }

    def _execute_batch_command(self, command_type, params):
        """Execute one batch-safe command."""
        if command_type == "get_session_info":
            return self._get_session_info()
        if command_type == "get_track_info":
            return self._get_track_info(params.get("track_index", 0))
        if command_type == "get_device_info":
            return self._get_device_info(params.get("track_index", 0), params.get("device_index", 0))
        if command_type == "get_device_parameters":
            return self._get_device_parameters(params.get("track_index", 0), params.get("device_index", 0))
        if command_type == "list_supported_commands":
            return {"commands": SUPPORTED_COMMANDS}
        if command_type == "search_browser_items":
            return self.search_browser_items(
                params.get("query", ""),
                params.get("category", None),
                params.get("max_results", 20)
            )
        if command_type == "get_browser_items_at_path":
            return self.get_browser_items_at_path(params.get("path", ""))
        if command_type == "get_browser_tree":
            return self.get_browser_tree(params.get("category_type", "all"))
        if command_type == "create_midi_track":
            return self._create_midi_track(params.get("index", -1))
        if command_type == "create_audio_track":
            return self._create_audio_track(params.get("index", -1))
        if command_type == "create_scene":
            return self._create_scene(params.get("index", -1), params.get("name", None))
        if command_type == "append_scene":
            return self._create_scene(-1, params.get("name", None))
        if command_type == "set_track_name":
            return self._set_track_name(params.get("track_index", 0), params.get("name", ""))
        if command_type == "create_clip":
            return self._create_clip(
                params.get("track_index", 0),
                params.get("clip_index", 0),
                params.get("length", 4.0)
            )
        if command_type == "add_notes_to_clip":
            return self._add_notes_to_clip(
                params.get("track_index", 0),
                params.get("clip_index", 0),
                params.get("notes", [])
            )
        if command_type == "set_clip_name":
            return self._set_clip_name(
                params.get("track_index", 0),
                params.get("clip_index", 0),
                params.get("name", "")
            )
        if command_type == "set_tempo":
            return self._set_tempo(params.get("tempo", 120.0))
        if command_type == "fire_clip":
            return self._fire_clip(params.get("track_index", 0), params.get("clip_index", 0))
        if command_type == "stop_clip":
            return self._stop_clip(params.get("track_index", 0), params.get("clip_index", 0))
        if command_type in ["load_browser_item", "load_instrument_or_effect"]:
            item_uri = params.get("item_uri", params.get("uri", ""))
            result = self._load_browser_item(params.get("track_index", 0), item_uri)
            result["verification_deferred"] = True
            result["verification_note"] = (
                "Batch browser loads are not readback-verified in the same Live callback; "
                "call get_track_info or get_device_parameters after the batch to verify the load."
            )
            return result
        if command_type == "set_device_parameter":
            return self._set_device_parameter(
                params.get("track_index", 0),
                params.get("device_index", 0),
                params.get("parameter_index", 0),
                params.get("value", 0.0)
            )
        if command_type == "set_device_parameter_by_name":
            return self._set_device_parameter_by_name(
                params.get("track_index", 0),
                params.get("device_index", 0),
                params.get("parameter_name", ""),
                params.get("value", 0.0)
            )
        if command_type == "duplicate_clip_to_arrangement":
            return self._duplicate_clip_to_arrangement(
                params.get("track_index", 0),
                params.get("scene_index", 0),
                params.get("start_time", 0.0)
            )
        if command_type == "duplicate_scene_to_arrangement":
            return self._duplicate_scene_to_arrangement(
                params.get("scene_index", 0),
                params.get("start_time", 0.0),
                params.get("track_indices", None)
            )
        if command_type == "start_playback":
            return self._start_playback()
        if command_type == "stop_playback":
            return self._stop_playback()
        raise ValueError("Command '{0}' is not supported in execute_batch".format(command_type))

    def _browser_item_info(self, item, path):
        """Return serializable browser item info."""
        children = self._safe_getattr(item, "children", None)
        try:
            is_folder = bool(children)
        except Exception:
            is_folder = False
        return {
            "name": self._safe_getattr(item, "name", "Unknown"),
            "path": path,
            "is_folder": is_folder,
            "is_device": bool(self._safe_getattr(item, "is_device", False)),
            "is_loadable": bool(self._safe_getattr(item, "is_loadable", False)),
            "uri": self._safe_getattr(item, "uri", None)
        }

    def _get_browser_roots(self, browser, category=None):
        """Return browser root categories by stable external names."""
        root_names = [
            "instruments", "sounds", "drums", "audio_effects", "midi_effects",
            "plugins", "max_for_live", "packs", "user_library"
        ]
        roots = []
        for name in root_names:
            if category is None or category == "all" or category == name:
                root = self._safe_getattr(browser, name, None)
                if root is not None:
                    roots.append((name, root))
        return roots

    def _search_browser_item(self, item, path, query, max_results, results,
                             depth=0, max_depth=12, budget=None, max_nodes=1500):
        """Search browser items by name/path."""
        if budget is None:
            budget = {"visited": 0, "skipped": 0}
        if len(results) >= max_results or depth > max_depth or item is None:
            return
        if budget["visited"] >= max_nodes:
            return

        budget["visited"] += 1

        name = self._safe_getattr(item, "name", "")
        searchable = (name + " " + path).lower()
        if query in searchable:
            results.append(self._browser_item_info(item, path))
            if len(results) >= max_results:
                return

        children = self._safe_getattr(item, "children", None)
        if children:
            try:
                child_iter = list(children)
            except Exception as e:
                budget["skipped"] += 1
                self.log_message("Skipping browser children at {0}: {1}".format(path, str(e)))
                return

            for child in child_iter:
                try:
                    child_name = self._safe_getattr(child, "name", "Unknown")
                    child_path = path + "/" + child_name
                    self._search_browser_item(
                        child, child_path, query, max_results, results,
                        depth + 1, max_depth, budget, max_nodes
                    )
                except Exception as e:
                    budget["skipped"] += 1
                    self.log_message("Skipping browser item under {0}: {1}".format(path, str(e)))
                if len(results) >= max_results:
                    return
                if budget["visited"] >= max_nodes:
                    return
    
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
        except Exception:
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

    def search_browser_items(self, query, category=None, max_results=20):
        """
        Search Ableton browser items by name or path.

        Args:
            query: Case-insensitive text to search for
            category: Optional root category such as instruments, sounds, drums,
                      audio_effects, or midi_effects
            max_results: Maximum number of results to return

        Returns:
            Dictionary with matching browser items and their URIs
        """
        try:
            app = self.application()
            if not app:
                raise RuntimeError("Could not access Live application")
            if not hasattr(app, "browser") or app.browser is None:
                raise RuntimeError("Browser is not available in the Live application")

            query = (query or "").strip().lower()
            if not query:
                raise ValueError("query is required")

            try:
                max_results = int(max_results)
            except (TypeError, ValueError):
                max_results = 20
            if max_results <= 0:
                max_results = 20

            normalized_category = category.lower() if category else None
            roots = self._get_browser_roots(app.browser, normalized_category)
            if normalized_category and normalized_category != "all" and not roots:
                return {
                    "query": query,
                    "category": category,
                    "error": "Unknown or unavailable category: {0}".format(category),
                    "available_categories": [
                        name for name, item in self._get_browser_roots(app.browser, "all")
                    ],
                    "results": []
                }

            results = []
            budget = {"visited": 0, "skipped": 0}
            for root_name, root_item in roots:
                self._search_browser_item(root_item, root_name, query, max_results, results, budget=budget)
                if len(results) >= max_results:
                    break
                if budget["visited"] >= 1500:
                    break

            return {
                "query": query,
                "category": category,
                "results": results,
                "count": len(results),
                "visited": budget["visited"],
                "skipped": budget["skipped"],
                "truncated": budget["visited"] >= 1500
            }
        except Exception as e:
            self.log_message("Error searching browser items: {0}".format(str(e)))
            self.log_message(traceback.format_exc())
            raise
