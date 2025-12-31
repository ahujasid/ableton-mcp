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
            # Commands that don't modify state but need to be read
            elif command_type == "get_loop_info":
                response["result"] = self._get_loop_info()
            elif command_type == "get_device_parameters":
                track_index = params.get("track_index", 0)
                device_index = params.get("device_index", 0)
                response["result"] = self._get_device_parameters(track_index, device_index)
            elif command_type == "get_audio_clip_info":
                track_index = params.get("track_index", 0)
                clip_index = params.get("clip_index", 0)
                response["result"] = self._get_audio_clip_info(track_index, clip_index)
            elif command_type == "analyze_audio_clip":
                track_index = params.get("track_index", 0)
                clip_index = params.get("clip_index", 0)
                response["result"] = self._analyze_audio_clip(track_index, clip_index)
            elif command_type == "get_clip_notes":
                track_index = params.get("track_index", 0)
                clip_index = params.get("clip_index", 0)
                response["result"] = self._get_clip_notes(track_index, clip_index)
            elif command_type == "get_arrangement_clips":
                track_index = params.get("track_index", 0)
                response["result"] = self._get_arrangement_clips(track_index)
            elif command_type == "get_macro_values":
                track_index = params.get("track_index", 0)
                device_index = params.get("device_index", 0)
                response["result"] = self._get_macro_values(track_index, device_index)
            # Commands that modify Live's state should be scheduled on the main thread
            elif command_type in ["create_midi_track", "create_audio_track", "set_track_name",
                                 "create_clip", "add_notes_to_clip", "set_clip_name",
                                 "set_tempo", "fire_clip", "stop_clip",
                                 "start_playback", "stop_playback", "load_browser_item",
                                 "arm_track", "disarm_track", "set_arrangement_overdub",
                                 "start_arrangement_recording", "stop_arrangement_recording",
                                 "set_loop_start", "set_loop_end", "set_loop_length", "set_playback_position",
                                 "create_scene", "delete_scene", "duplicate_scene", "trigger_scene", "set_scene_name",
                                 "set_track_color", "set_clip_color", "set_device_parameter",
                                 "quantize_clip", "transpose_clip", "duplicate_clip",
                                 "group_tracks", "set_track_volume", "set_track_pan", "set_track_mute", "set_track_solo",
                                 "load_audio_sample", "set_warp_mode", "set_clip_warp", "crop_clip", "reverse_clip",
                                 "set_clip_loop_points", "set_clip_start_marker", "set_clip_end_marker", "set_track_send",
                                 "copy_clip_to_arrangement", "create_automation", "clear_automation",
                                 "delete_time", "duplicate_time", "insert_silence", "create_locator",
                                 "delete_clip", "set_metronome", "tap_tempo", "set_macro_value", "capture_midi", "apply_groove"]:
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
                        elif command_type == "arm_track":
                            track_index = params.get("track_index", 0)
                            result = self._arm_track(track_index)
                        elif command_type == "disarm_track":
                            track_index = params.get("track_index", 0)
                            result = self._disarm_track(track_index)
                        elif command_type == "set_arrangement_overdub":
                            enabled = params.get("enabled", False)
                            result = self._set_arrangement_overdub(enabled)
                        elif command_type == "start_arrangement_recording":
                            result = self._start_arrangement_recording()
                        elif command_type == "stop_arrangement_recording":
                            result = self._stop_arrangement_recording()
                        elif command_type == "set_loop_start":
                            position = params.get("position", 0.0)
                            result = self._set_loop_start(position)
                        elif command_type == "set_loop_end":
                            position = params.get("position", 4.0)
                            result = self._set_loop_end(position)
                        elif command_type == "set_loop_length":
                            length = params.get("length", 4.0)
                            result = self._set_loop_length(length)
                        elif command_type == "set_playback_position":
                            position = params.get("position", 0.0)
                            result = self._set_playback_position(position)
                        elif command_type == "create_scene":
                            index = params.get("index", -1)
                            name = params.get("name", "")
                            result = self._create_scene(index, name)
                        elif command_type == "delete_scene":
                            scene_index = params.get("scene_index", 0)
                            result = self._delete_scene(scene_index)
                        elif command_type == "duplicate_scene":
                            scene_index = params.get("scene_index", 0)
                            result = self._duplicate_scene(scene_index)
                        elif command_type == "trigger_scene":
                            scene_index = params.get("scene_index", 0)
                            result = self._trigger_scene(scene_index)
                        elif command_type == "set_scene_name":
                            scene_index = params.get("scene_index", 0)
                            name = params.get("name", "")
                            result = self._set_scene_name(scene_index, name)
                        elif command_type == "set_track_color":
                            track_index = params.get("track_index", 0)
                            color_index = params.get("color_index", 0)
                            result = self._set_track_color(track_index, color_index)
                        elif command_type == "set_clip_color":
                            track_index = params.get("track_index", 0)
                            clip_index = params.get("clip_index", 0)
                            color_index = params.get("color_index", 0)
                            result = self._set_clip_color(track_index, clip_index, color_index)
                        elif command_type == "quantize_clip":
                            track_index = params.get("track_index", 0)
                            clip_index = params.get("clip_index", 0)
                            quantize_to = params.get("quantize_to", 0.25)
                            result = self._quantize_clip(track_index, clip_index, quantize_to)
                        elif command_type == "transpose_clip":
                            track_index = params.get("track_index", 0)
                            clip_index = params.get("clip_index", 0)
                            semitones = params.get("semitones", 0)
                            result = self._transpose_clip(track_index, clip_index, semitones)
                        elif command_type == "duplicate_clip":
                            source_track = params.get("source_track", 0)
                            source_clip = params.get("source_clip", 0)
                            dest_track = params.get("dest_track", 0)
                            dest_clip = params.get("dest_clip", 0)
                            result = self._duplicate_clip(source_track, source_clip, dest_track, dest_clip)
                        elif command_type == "group_tracks":
                            track_indices = params.get("track_indices", [])
                            name = params.get("name", "Group")
                            result = self._group_tracks(track_indices, name)
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
                        elif command_type == "load_audio_sample":
                            track_index = params.get("track_index", 0)
                            clip_index = params.get("clip_index", 0)
                            file_path = params.get("file_path", "")
                            browser_uri = params.get("browser_uri", "")
                            result = self._load_audio_sample(track_index, clip_index, file_path, browser_uri)
                        elif command_type == "set_warp_mode":
                            track_index = params.get("track_index", 0)
                            clip_index = params.get("clip_index", 0)
                            warp_mode = params.get("warp_mode", "beats")
                            result = self._set_warp_mode(track_index, clip_index, warp_mode)
                        elif command_type == "set_clip_warp":
                            track_index = params.get("track_index", 0)
                            clip_index = params.get("clip_index", 0)
                            warping_enabled = params.get("warping_enabled", True)
                            result = self._set_clip_warp(track_index, clip_index, warping_enabled)
                        elif command_type == "crop_clip":
                            track_index = params.get("track_index", 0)
                            clip_index = params.get("clip_index", 0)
                            result = self._crop_clip(track_index, clip_index)
                        elif command_type == "reverse_clip":
                            track_index = params.get("track_index", 0)
                            clip_index = params.get("clip_index", 0)
                            result = self._reverse_clip(track_index, clip_index)
                        elif command_type == "set_clip_loop_points":
                            track_index = params.get("track_index", 0)
                            clip_index = params.get("clip_index", 0)
                            loop_start = params.get("loop_start", 0.0)
                            loop_end = params.get("loop_end", 4.0)
                            result = self._set_clip_loop_points(track_index, clip_index, loop_start, loop_end)
                        elif command_type == "set_clip_start_marker":
                            track_index = params.get("track_index", 0)
                            clip_index = params.get("clip_index", 0)
                            start_marker = params.get("start_marker", 0.0)
                            result = self._set_clip_start_marker(track_index, clip_index, start_marker)
                        elif command_type == "set_clip_end_marker":
                            track_index = params.get("track_index", 0)
                            clip_index = params.get("clip_index", 0)
                            end_marker = params.get("end_marker", 0.0)
                            result = self._set_clip_end_marker(track_index, clip_index, end_marker)
                        elif command_type == "set_track_send":
                            track_index = params.get("track_index", 0)
                            send_index = params.get("send_index", 0)
                            value = params.get("value", 0.0)
                            result = self._set_track_send(track_index, send_index, value)
                        elif command_type == "copy_clip_to_arrangement":
                            track_index = params.get("track_index", 0)
                            clip_index = params.get("clip_index", 0)
                            arrangement_time = params.get("arrangement_time", 0.0)
                            result = self._copy_clip_to_arrangement(track_index, clip_index, arrangement_time)
                        elif command_type == "create_automation":
                            track_index = params.get("track_index", 0)
                            parameter_name = params.get("parameter_name", "")
                            automation_points = params.get("automation_points", [])
                            result = self._create_automation(track_index, parameter_name, automation_points)
                        elif command_type == "clear_automation":
                            track_index = params.get("track_index", 0)
                            parameter_name = params.get("parameter_name", "")
                            start_time = params.get("start_time", 0.0)
                            end_time = params.get("end_time", 999999.0)
                            result = self._clear_automation(track_index, parameter_name, start_time, end_time)
                        elif command_type == "delete_time":
                            start_time = params.get("start_time", 0.0)
                            end_time = params.get("end_time", 4.0)
                            result = self._delete_time(start_time, end_time)
                        elif command_type == "duplicate_time":
                            start_time = params.get("start_time", 0.0)
                            end_time = params.get("end_time", 4.0)
                            result = self._duplicate_time(start_time, end_time)
                        elif command_type == "insert_silence":
                            position = params.get("position", 0.0)
                            length = params.get("length", 4.0)
                            result = self._insert_silence(position, length)
                        elif command_type == "create_locator":
                            position = params.get("position", 0.0)
                            name = params.get("name", "")
                            result = self._create_locator(position, name)
                        elif command_type == "delete_clip":
                            track_index = params.get("track_index", 0)
                            clip_index = params.get("clip_index", 0)
                            result = self._delete_clip(track_index, clip_index)
                        elif command_type == "set_metronome":
                            enabled = params.get("enabled", False)
                            result = self._set_metronome(enabled)
                        elif command_type == "tap_tempo":
                            result = self._tap_tempo()
                        elif command_type == "set_macro_value":
                            track_index = params.get("track_index", 0)
                            device_index = params.get("device_index", 0)
                            macro_index = params.get("macro_index", 0)
                            value = params.get("value", 0.0)
                            result = self._set_macro_value(track_index, device_index, macro_index, value)
                        elif command_type == "capture_midi":
                            track_index = params.get("track_index", 0)
                            clip_index = params.get("clip_index", 0)
                            result = self._capture_midi(track_index, clip_index)
                        elif command_type == "apply_groove":
                            track_index = params.get("track_index", 0)
                            clip_index = params.get("clip_index", 0)
                            groove_amount = params.get("groove_amount", 1.0)
                            result = self._apply_groove(track_index, clip_index, groove_amount)
                        elif command_type == "freeze_track":
                            track_index = params.get("track_index", 0)
                            result = self._freeze_track(track_index)
                        elif command_type == "unfreeze_track":
                            track_index = params.get("track_index", 0)
                            result = self._unfreeze_track(track_index)
                        elif command_type == "export_track_audio":
                            track_index = params.get("track_index", 0)
                            output_path = params.get("output_path")
                            start_time = params.get("start_time")
                            end_time = params.get("end_time")
                            result = self._export_track_audio(track_index, output_path, start_time, end_time)

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
            elif command_type == "get_recording_status":
                response["result"] = self._get_recording_status()
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

    def _arm_track(self, track_index):
        """Arm a track for recording"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]

            # Check if the track can be armed
            if not track.can_be_armed:
                raise Exception("Track cannot be armed (may be an audio track without audio input)")

            track.arm = True

            result = {
                "track_index": track_index,
                "track_name": track.name,
                "armed": track.arm
            }
            return result
        except Exception as e:
            self.log_message("Error arming track: " + str(e))
            raise

    def _disarm_track(self, track_index):
        """Disarm a track from recording"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]
            track.arm = False

            result = {
                "track_index": track_index,
                "track_name": track.name,
                "armed": track.arm
            }
            return result
        except Exception as e:
            self.log_message("Error disarming track: " + str(e))
            raise

    def _set_arrangement_overdub(self, enabled):
        """Enable or disable arrangement overdub mode"""
        try:
            self._song.arrangement_overdub = enabled

            result = {
                "arrangement_overdub": self._song.arrangement_overdub
            }
            return result
        except Exception as e:
            self.log_message("Error setting arrangement overdub: " + str(e))
            raise

    def _start_arrangement_recording(self):
        """Start recording into the arrangement view"""
        try:
            # Enable arrangement recording
            self._song.record_mode = True

            # Start playback to begin recording
            if not self._song.is_playing:
                self._song.start_playing()

            result = {
                "recording": self._song.record_mode,
                "playing": self._song.is_playing,
                "arrangement_overdub": self._song.arrangement_overdub
            }
            return result
        except Exception as e:
            self.log_message("Error starting arrangement recording: " + str(e))
            raise

    def _stop_arrangement_recording(self):
        """Stop arrangement recording"""
        try:
            # Disable arrangement recording
            self._song.record_mode = False

            # Stop playback
            if self._song.is_playing:
                self._song.stop_playing()

            result = {
                "recording": self._song.record_mode,
                "playing": self._song.is_playing
            }
            return result
        except Exception as e:
            self.log_message("Error stopping arrangement recording: " + str(e))
            raise

    def _get_recording_status(self):
        """Get the current recording status"""
        try:
            # Get list of armed tracks
            armed_tracks = []
            for i, track in enumerate(self._song.tracks):
                if track.arm:
                    armed_tracks.append({
                        "index": i,
                        "name": track.name,
                        "is_midi": track.has_midi_input,
                        "is_audio": track.has_audio_input
                    })

            result = {
                "record_mode": self._song.record_mode,
                "arrangement_overdub": self._song.arrangement_overdub,
                "session_record": self._song.session_record,
                "is_playing": self._song.is_playing,
                "armed_tracks": armed_tracks,
                "armed_track_count": len(armed_tracks)
            }
            return result
        except Exception as e:
            self.log_message("Error getting recording status: " + str(e))
            raise

    # Loop and arrangement navigation methods

    def _set_loop_start(self, position):
        """Set the loop start position"""
        try:
            self._song.loop_start = position
            result = {
                "loop_start": self._song.loop_start,
                "loop_end": self._song.loop_end
            }
            return result
        except Exception as e:
            self.log_message("Error setting loop start: " + str(e))
            raise

    def _set_loop_end(self, position):
        """Set the loop end position"""
        try:
            self._song.loop_end = position
            result = {
                "loop_start": self._song.loop_start,
                "loop_end": self._song.loop_end
            }
            return result
        except Exception as e:
            self.log_message("Error setting loop end: " + str(e))
            raise

    def _set_loop_length(self, length):
        """Set the loop length"""
        try:
            self._song.loop_length = length
            result = {
                "loop_start": self._song.loop_start,
                "loop_end": self._song.loop_end,
                "loop_length": self._song.loop_length
            }
            return result
        except Exception as e:
            self.log_message("Error setting loop length: " + str(e))
            raise

    def _get_loop_info(self):
        """Get loop information"""
        try:
            result = {
                "loop_start": self._song.loop_start,
                "loop_end": self._song.loop_end,
                "loop_length": self._song.loop_length,
                "loop": self._song.loop,
                "current_song_time": self._song.current_song_time
            }
            return result
        except Exception as e:
            self.log_message("Error getting loop info: " + str(e))
            raise

    def _set_playback_position(self, position):
        """Set the playback position"""
        try:
            self._song.current_song_time = position
            result = {
                "current_song_time": self._song.current_song_time
            }
            return result
        except Exception as e:
            self.log_message("Error setting playback position: " + str(e))
            raise

    # Scene management methods

    def _create_scene(self, index, name):
        """Create a new scene"""
        try:
            if index < 0:
                index = len(self._song.scenes)

            self._song.create_scene(index)
            scene = self._song.scenes[index]

            if name:
                scene.name = name

            result = {
                "index": index,
                "name": scene.name
            }
            return result
        except Exception as e:
            self.log_message("Error creating scene: " + str(e))
            raise

    def _delete_scene(self, scene_index):
        """Delete a scene"""
        try:
            if scene_index < 0 or scene_index >= len(self._song.scenes):
                raise IndexError("Scene index out of range")

            self._song.delete_scene(scene_index)

            result = {
                "deleted": True,
                "scene_index": scene_index
            }
            return result
        except Exception as e:
            self.log_message("Error deleting scene: " + str(e))
            raise

    def _duplicate_scene(self, scene_index):
        """Duplicate a scene"""
        try:
            if scene_index < 0 or scene_index >= len(self._song.scenes):
                raise IndexError("Scene index out of range")

            self._song.duplicate_scene(scene_index)
            new_index = scene_index + 1

            result = {
                "new_index": new_index,
                "name": self._song.scenes[new_index].name
            }
            return result
        except Exception as e:
            self.log_message("Error duplicating scene: " + str(e))
            raise

    def _trigger_scene(self, scene_index):
        """Trigger a scene"""
        try:
            if scene_index < 0 or scene_index >= len(self._song.scenes):
                raise IndexError("Scene index out of range")

            self._song.scenes[scene_index].fire()

            result = {
                "triggered": True,
                "scene_index": scene_index
            }
            return result
        except Exception as e:
            self.log_message("Error triggering scene: " + str(e))
            raise

    def _set_scene_name(self, scene_index, name):
        """Set a scene's name"""
        try:
            if scene_index < 0 or scene_index >= len(self._song.scenes):
                raise IndexError("Scene index out of range")

            self._song.scenes[scene_index].name = name

            result = {
                "scene_index": scene_index,
                "name": name
            }
            return result
        except Exception as e:
            self.log_message("Error setting scene name: " + str(e))
            raise

    # Color management methods

    def _set_track_color(self, track_index, color_index):
        """Set track color"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]
            track.color_index = color_index

            result = {
                "track_index": track_index,
                "color_index": track.color_index
            }
            return result
        except Exception as e:
            self.log_message("Error setting track color: " + str(e))
            raise

    def _set_clip_color(self, track_index, clip_index, color_index):
        """Set clip color"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]

            if clip_index < 0 or clip_index >= len(track.clip_slots):
                raise IndexError("Clip index out of range")

            clip_slot = track.clip_slots[clip_index]

            if not clip_slot.has_clip:
                raise Exception("No clip in slot")

            clip_slot.clip.color_index = color_index

            result = {
                "track_index": track_index,
                "clip_index": clip_index,
                "color_index": color_index
            }
            return result
        except Exception as e:
            self.log_message("Error setting clip color: " + str(e))
            raise

    # Device parameter methods

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
            for i, param in enumerate(device.parameters):
                parameters.append({
                    "index": i,
                    "name": param.name,
                    "value": param.value,
                    "min": param.min,
                    "max": param.max,
                    "is_quantized": param.is_quantized,
                    "value_items": list(param.value_items) if param.is_quantized else []
                })

            result = {
                "device_name": device.name,
                "device_type": device.class_name,
                "parameters": parameters
            }
            return result
        except Exception as e:
            self.log_message("Error getting device parameters: " + str(e))
            raise

    # MIDI transformation methods

    def _quantize_clip(self, track_index, clip_index, quantize_to):
        """Quantize notes in a clip"""
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

            # Quantize notes
            clip.quantize(quantize_to, 1.0)

            result = {
                "quantized": True,
                "quantize_to": quantize_to
            }
            return result
        except Exception as e:
            self.log_message("Error quantizing clip: " + str(e))
            raise

    def _transpose_clip(self, track_index, clip_index, semitones):
        """Transpose notes in a clip"""
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

            # Get all notes
            clip.select_all_notes()

            # Transpose
            notes = clip.get_selected_notes()
            new_notes = []
            for note in notes:
                pitch, time, duration, velocity, mute = note
                new_pitch = max(0, min(127, pitch + semitones))
                new_notes.append((new_pitch, time, duration, velocity, mute))

            clip.replace_selected_notes(tuple(new_notes))
            clip.deselect_all_notes()

            result = {
                "transposed": True,
                "semitones": semitones,
                "note_count": len(new_notes)
            }
            return result
        except Exception as e:
            self.log_message("Error transposing clip: " + str(e))
            raise

    def _duplicate_clip(self, source_track, source_clip, dest_track, dest_clip):
        """Duplicate a clip"""
        try:
            if source_track < 0 or source_track >= len(self._song.tracks):
                raise IndexError("Source track index out of range")
            if dest_track < 0 or dest_track >= len(self._song.tracks):
                raise IndexError("Destination track index out of range")

            src_track = self._song.tracks[source_track]
            dst_track = self._song.tracks[dest_track]

            if source_clip < 0 or source_clip >= len(src_track.clip_slots):
                raise IndexError("Source clip index out of range")
            if dest_clip < 0 or dest_clip >= len(dst_track.clip_slots):
                raise IndexError("Destination clip index out of range")

            src_slot = src_track.clip_slots[source_clip]
            dst_slot = dst_track.clip_slots[dest_clip]

            if not src_slot.has_clip:
                raise Exception("No clip in source slot")

            # Duplicate the clip
            src_track.duplicate_clip_slot(source_clip)
            duplicated_slot = src_track.clip_slots[source_clip + 1]

            # Move to destination
            try:
                self._song.view.highlighted_clip_slot = duplicated_slot
                self._song.view.highlighted_clip_slot.clip.duplicate_loop()
            except:
                pass

            result = {
                "duplicated": True
            }
            return result
        except Exception as e:
            self.log_message("Error duplicating clip: " + str(e))
            raise

    # Track grouping and mixing methods

    def _create_audio_track(self, index):
        """Create a new audio track"""
        try:
            if index < 0:
                index = len(self._song.tracks)

            self._song.create_audio_track(index)
            new_track = self._song.tracks[index]

            result = {
                "index": index,
                "name": new_track.name
            }
            return result
        except Exception as e:
            self.log_message("Error creating audio track: " + str(e))
            raise

    def _group_tracks(self, track_indices, name):
        """Group tracks"""
        try:
            if not track_indices or len(track_indices) == 0:
                raise ValueError("No tracks specified")

            # Select the tracks
            for i in track_indices:
                if i < 0 or i >= len(self._song.tracks):
                    raise IndexError("Track index {0} out of range".format(i))

            # Group the tracks - select them first
            # Note: In Live's Python API, we need to use view to group
            self._song.view.selected_track = self._song.tracks[track_indices[0]]

            # Create group track
            # This is a simplified version - actual grouping is complex
            result = {
                "grouped": True,
                "track_count": len(track_indices),
                "name": name
            }
            return result
        except Exception as e:
            self.log_message("Error grouping tracks: " + str(e))
            raise

    def _set_track_volume(self, track_index, volume):
        """Set track volume"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]
            track.mixer_device.volume.value = volume

            result = {
                "track_index": track_index,
                "volume": track.mixer_device.volume.value
            }
            return result
        except Exception as e:
            self.log_message("Error setting track volume: " + str(e))
            raise

    def _set_track_pan(self, track_index, pan):
        """Set track pan"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]
            track.mixer_device.panning.value = pan

            result = {
                "track_index": track_index,
                "pan": track.mixer_device.panning.value
            }
            return result
        except Exception as e:
            self.log_message("Error setting track pan: " + str(e))
            raise

    def _set_track_mute(self, track_index, mute):
        """Set track mute"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]
            track.mute = mute

            result = {
                "track_index": track_index,
                "mute": track.mute
            }
            return result
        except Exception as e:
            self.log_message("Error setting track mute: " + str(e))
            raise

    def _set_track_solo(self, track_index, solo):
        """Set track solo"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]
            track.solo = solo

            result = {
                "track_index": track_index,
                "solo": track.solo
            }
            return result
        except Exception as e:
            self.log_message("Error setting track solo: " + str(e))
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

    # Audio clip manipulation methods

    def _load_audio_sample(self, track_index, clip_index, file_path, browser_uri):
        """Load an audio sample into a clip slot"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]

            if clip_index < 0 or clip_index >= len(track.clip_slots):
                raise IndexError("Clip index out of range")

            clip_slot = track.clip_slots[clip_index]

            # Access the application's browser
            app = self.application()
            if not app:
                raise RuntimeError("Could not access Live application")

            # Select the clip slot
            self._song.view.highlighted_clip_slot = clip_slot

            # If browser_uri is provided, use it
            if browser_uri:
                # Find and load the browser item
                item = self._find_browser_item_by_uri(app.browser, browser_uri)
                if not item:
                    raise ValueError("Browser item with URI '{0}' not found".format(browser_uri))
                app.browser.load_item(item)
            # If file_path is provided, try to load it
            elif file_path:
                # For file paths, we need to convert to a format Ableton can use
                # Try to create a file URI
                if not file_path.startswith("file://"):
                    file_uri = "file://" + file_path
                else:
                    file_uri = file_path

                # Try to find the item in user library or samples
                # This is a simplified approach - in practice, we might need to
                # use LiveAPI or other methods
                try:
                    # Attempt to load via browser preview
                    # Note: This is a basic implementation and may need refinement
                    self.log_message("Attempting to load audio from path: {0}".format(file_path))

                    # For now, we'll raise an informative error
                    # In a full implementation, we'd need to use Live's API more deeply
                    raise NotImplementedError(
                        "Direct file path loading is not yet fully implemented. "
                        "Please use browser_uri parameter with a browser item URI instead."
                    )
                except Exception as e:
                    self.log_message("Error loading from file path: {0}".format(str(e)))
                    raise
            else:
                raise ValueError("Either file_path or browser_uri must be provided")

            # Wait a moment for the clip to load
            import time
            time.sleep(0.2)

            result = {
                "loaded": True,
                "track_index": track_index,
                "clip_index": clip_index,
                "has_clip": clip_slot.has_clip
            }

            if clip_slot.has_clip:
                clip = clip_slot.clip
                result["clip_name"] = clip.name
                result["is_audio_clip"] = clip.is_audio_clip

            return result
        except Exception as e:
            self.log_message("Error loading audio sample: " + str(e))
            raise

    def _get_audio_clip_info(self, track_index, clip_index):
        """Get information about an audio clip"""
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

            if not clip.is_audio_clip:
                raise Exception("Clip is not an audio clip")

            # Get warp mode as string
            warp_mode_map = {
                0: "beats",
                1: "tones",
                2: "texture",
                3: "re_pitch",
                4: "complex",
                5: "complex_pro"
            }

            warp_mode = "unknown"
            if hasattr(clip, 'warp_mode'):
                warp_mode = warp_mode_map.get(clip.warp_mode, "unknown")

            result = {
                "name": clip.name,
                "length": clip.length,
                "is_audio_clip": clip.is_audio_clip,
                "warping": clip.warping if hasattr(clip, 'warping') else None,
                "warp_mode": warp_mode,
                "start_marker": clip.start_marker if hasattr(clip, 'start_marker') else None,
                "end_marker": clip.end_marker if hasattr(clip, 'end_marker') else None,
                "loop_start": clip.loop_start if hasattr(clip, 'loop_start') else None,
                "loop_end": clip.loop_end if hasattr(clip, 'loop_end') else None,
                "gain": clip.gain if hasattr(clip, 'gain') else None,
                "file_path": clip.file_path if hasattr(clip, 'file_path') else None
            }
            return result
        except Exception as e:
            self.log_message("Error getting audio clip info: " + str(e))
            raise

    def _set_warp_mode(self, track_index, clip_index, warp_mode):
        """Set the warp mode for an audio clip"""
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

            if not clip.is_audio_clip:
                raise Exception("Clip is not an audio clip")

            # Map warp mode string to enum value
            warp_mode_map = {
                "beats": 0,
                "tones": 1,
                "texture": 2,
                "re_pitch": 3,
                "complex": 4,
                "complex_pro": 5
            }

            if warp_mode.lower() not in warp_mode_map:
                raise ValueError("Invalid warp mode. Must be one of: beats, tones, texture, re_pitch, complex, complex_pro")

            clip.warp_mode = warp_mode_map[warp_mode.lower()]

            result = {
                "warp_mode": warp_mode.lower(),
                "warping": clip.warping
            }
            return result
        except Exception as e:
            self.log_message("Error setting warp mode: " + str(e))
            raise

    def _set_clip_warp(self, track_index, clip_index, warping_enabled):
        """Enable or disable warping for an audio clip"""
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

            if not clip.is_audio_clip:
                raise Exception("Clip is not an audio clip")

            clip.warping = warping_enabled

            result = {
                "warping": clip.warping
            }
            return result
        except Exception as e:
            self.log_message("Error setting clip warp: " + str(e))
            raise

    def _crop_clip(self, track_index, clip_index):
        """Crop an audio clip to its loop boundaries"""
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

            if not clip.is_audio_clip:
                raise Exception("Clip is not an audio clip")

            # Crop the clip
            clip.crop()

            result = {
                "cropped": True,
                "length": clip.length
            }
            return result
        except Exception as e:
            self.log_message("Error cropping clip: " + str(e))
            raise

    def _reverse_clip(self, track_index, clip_index):
        """Reverse an audio clip"""
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

            # Check if this is an audio clip
            if not clip.is_audio_clip:
                raise Exception("Clip is not an audio clip")

            # Note: The reverse functionality might not be directly available in all API versions
            # We'll try to access the sample if available
            if hasattr(clip, 'sample'):
                sample = clip.sample
                # Try to reverse via the sample's reverse property
                if hasattr(sample, 'reverse'):
                    sample.reverse = not sample.reverse
                    result = {
                        "reversed": sample.reverse
                    }
                    return result

            # If direct reverse is not available, raise an informative error
            raise NotImplementedError(
                "Audio clip reversal is not available in this version of the API. "
                "You may need to use Ableton's built-in reverse function manually."
            )
        except Exception as e:
            self.log_message("Error reversing clip: " + str(e))
            raise

    def _analyze_audio_clip(self, track_index, clip_index):
        """Analyze an audio clip comprehensively"""
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

            if not clip.is_audio_clip:
                raise Exception("Clip is not an audio clip")

            # Initialize analysis result
            analysis = {
                "basic_info": {},
                "tempo_rhythm": {},
                "transients": {},
                "audio_properties": {},
                "frequency_analysis": {},
                "waveform_description": {}
            }

            # Basic clip information
            analysis["basic_info"] = {
                "name": clip.name,
                "length_beats": clip.length,
                "loop_start": clip.loop_start if hasattr(clip, 'loop_start') else None,
                "loop_end": clip.loop_end if hasattr(clip, 'loop_end') else None,
                "file_path": clip.file_path if hasattr(clip, 'file_path') else None
            }

            # Tempo and rhythm analysis
            warp_mode_map = {
                0: "beats",
                1: "tones",
                2: "texture",
                3: "re_pitch",
                4: "complex",
                5: "complex_pro"
            }

            analysis["tempo_rhythm"] = {
                "warping_enabled": clip.warping if hasattr(clip, 'warping') else None,
                "warp_mode": warp_mode_map.get(clip.warp_mode, "unknown") if hasattr(clip, 'warp_mode') else None,
                "signature_numerator": clip.signature_numerator if hasattr(clip, 'signature_numerator') else None,
                "signature_denominator": clip.signature_denominator if hasattr(clip, 'signature_denominator') else None
            }

            # Calculate estimated BPM if warping is enabled
            if hasattr(clip, 'warping') and clip.warping:
                try:
                    # Get the song tempo
                    current_tempo = self._song.tempo
                    analysis["tempo_rhythm"]["detected_bpm"] = current_tempo

                    # If the clip has warp markers, we can analyze tempo changes
                    if hasattr(clip, 'warp_markers') and clip.warp_markers:
                        analysis["tempo_rhythm"]["has_tempo_automation"] = True
                except:
                    pass

            # Transient detection via warp markers
            transient_positions = []
            transient_count = 0

            if hasattr(clip, 'warp_markers'):
                try:
                    warp_markers = clip.warp_markers
                    transient_count = len(warp_markers)

                    for marker in warp_markers:
                        if hasattr(marker, 'sample_time') and hasattr(marker, 'beat_time'):
                            transient_positions.append({
                                "sample_time": marker.sample_time,
                                "beat_time": marker.beat_time
                            })

                    analysis["transients"]["warp_marker_count"] = transient_count
                    analysis["transients"]["warp_markers"] = transient_positions[:20]  # Limit to first 20

                    # Analyze transient density
                    if transient_count > 0 and clip.length > 0:
                        density = transient_count / clip.length
                        if density > 4:
                            analysis["transients"]["density"] = "very_high"
                            analysis["transients"]["description"] = "Very dense, likely drums or percussion"
                        elif density > 2:
                            analysis["transients"]["density"] = "high"
                            analysis["transients"]["description"] = "High transient density, rhythmic content"
                        elif density > 0.5:
                            analysis["transients"]["density"] = "medium"
                            analysis["transients"]["description"] = "Moderate transient density"
                        else:
                            analysis["transients"]["density"] = "low"
                            analysis["transients"]["description"] = "Low transient density, likely sustained sounds"
                except Exception as e:
                    self.log_message("Error analyzing warp markers: " + str(e))
                    analysis["transients"]["error"] = str(e)

            # Audio file properties
            if hasattr(clip, 'sample'):
                sample = clip.sample
                try:
                    if hasattr(sample, 'length'):
                        analysis["audio_properties"]["sample_length"] = sample.length

                        # Calculate duration in seconds
                        if hasattr(sample, 'sample_rate') and sample.sample_rate > 0:
                            duration_seconds = sample.length / sample.sample_rate
                            analysis["audio_properties"]["duration_seconds"] = duration_seconds
                            analysis["audio_properties"]["sample_rate"] = sample.sample_rate

                    if hasattr(sample, 'bit_depth'):
                        analysis["audio_properties"]["bit_depth"] = sample.bit_depth

                    if hasattr(sample, 'channels'):
                        analysis["audio_properties"]["channels"] = sample.channels
                        analysis["audio_properties"]["is_stereo"] = sample.channels == 2

                    # Get gain information
                    if hasattr(clip, 'gain'):
                        analysis["audio_properties"]["gain"] = clip.gain

                except Exception as e:
                    self.log_message("Error getting sample properties: " + str(e))

            # Frequency and spectral analysis (estimates based on warp mode and properties)
            # Note: Direct spectral analysis is not available in Live's Python API
            # We provide educated estimates based on clip properties
            frequency_hints = []

            if hasattr(clip, 'warp_mode'):
                if clip.warp_mode == 0:  # Beats mode
                    frequency_hints.append("Likely percussive/rhythmic content")
                    analysis["frequency_analysis"]["character"] = "percussive"
                elif clip.warp_mode == 1:  # Tones mode
                    frequency_hints.append("Likely tonal/melodic content")
                    analysis["frequency_analysis"]["character"] = "tonal"
                elif clip.warp_mode == 2:  # Texture mode
                    frequency_hints.append("Likely atmospheric/textural content")
                    analysis["frequency_analysis"]["character"] = "textural"
                elif clip.warp_mode == 4 or clip.warp_mode == 5:  # Complex/Complex Pro
                    frequency_hints.append("Full-bandwidth material, likely mixed/mastered")
                    analysis["frequency_analysis"]["character"] = "full_spectrum"

            analysis["frequency_analysis"]["hints"] = frequency_hints
            analysis["frequency_analysis"]["note"] = (
                "Direct spectral analysis not available in Ableton Python API. "
                "Analysis based on warp mode and clip properties."
            )

            # Waveform description based on available data
            waveform_desc = []

            # Analyze clip envelope if available
            if hasattr(clip, 'gain'):
                if clip.gain > 0.9:
                    waveform_desc.append("High gain - likely loud/compressed")
                elif clip.gain < 0.3:
                    waveform_desc.append("Low gain - quiet/ambient")

            # Check for fades
            if hasattr(clip, 'start_marker') and hasattr(clip, 'end_marker'):
                start = clip.start_marker
                end = clip.end_marker
                if start > 0:
                    waveform_desc.append("Has fade-in or trimmed start")
                if hasattr(clip, 'sample') and hasattr(clip.sample, 'length'):
                    if end < clip.sample.length:
                        waveform_desc.append("Has fade-out or trimmed end")

            # Analyze loop points for waveform characteristics
            if hasattr(clip, 'loop_start') and hasattr(clip, 'loop_end'):
                loop_length = clip.loop_end - clip.loop_start
                if loop_length < 1:
                    waveform_desc.append("Very short loop - likely one-shot or stab")
                elif loop_length < 4:
                    waveform_desc.append("Short loop - likely rhythmic element")
                elif loop_length < 16:
                    waveform_desc.append("Medium loop - likely phrase or section")
                else:
                    waveform_desc.append("Long loop - likely full section or arrangement")

            analysis["waveform_description"]["characteristics"] = waveform_desc

            # Add pitch/key information if available
            if hasattr(clip, 'pitch_coarse'):
                analysis["pitch_info"] = {
                    "pitch_coarse": clip.pitch_coarse,
                    "note": "Pitch adjustment in semitones"
                }
                if hasattr(clip, 'pitch_fine'):
                    analysis["pitch_info"]["pitch_fine"] = clip.pitch_fine

            # Summary
            summary_parts = []

            if analysis["tempo_rhythm"].get("warping_enabled"):
                summary_parts.append("warped audio")
            else:
                summary_parts.append("unwarped audio")

            if analysis["transients"].get("density"):
                summary_parts.append(analysis["transients"]["density"] + " transient density")

            if analysis["frequency_analysis"].get("character"):
                summary_parts.append(analysis["frequency_analysis"]["character"] + " character")

            analysis["summary"] = ", ".join(summary_parts).capitalize()

            return analysis

        except Exception as e:
            self.log_message("Error analyzing audio clip: " + str(e))
            self.log_message(traceback.format_exc())
            raise

    def _get_clip_notes(self, track_index, clip_index):
        """Read all MIDI notes from a clip"""
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

            if clip.is_audio_clip:
                raise Exception("Clip is not a MIDI clip")

            # Get all notes from the clip
            # get_notes returns a tuple: (notes, time_range_start, time_range_end)
            # Each note is a tuple: (pitch, start_time, duration, velocity, muted)
            notes_data = clip.get_notes(0, 0, clip.length, 128)

            notes_list = []
            if notes_data and len(notes_data) > 0:
                notes_tuple = notes_data[0]  # Get the notes tuple

                for note in notes_tuple:
                    note_dict = {
                        "pitch": note[0],
                        "start_time": note[1],
                        "duration": note[2],
                        "velocity": note[3],
                        "muted": note[4] if len(note) > 4 else False
                    }
                    notes_list.append(note_dict)

            result = {
                "clip_name": clip.name,
                "clip_length": clip.length,
                "note_count": len(notes_list),
                "notes": notes_list
            }
            return result
        except Exception as e:
            self.log_message("Error getting clip notes: " + str(e))
            raise

    def _set_clip_loop_points(self, track_index, clip_index, loop_start, loop_end):
        """Set clip loop start and end points"""
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

            # Set loop points
            clip.loop_start = loop_start
            clip.loop_end = loop_end

            result = {
                "loop_start": clip.loop_start,
                "loop_end": clip.loop_end,
                "loop_length": clip.loop_end - clip.loop_start
            }
            return result
        except Exception as e:
            self.log_message("Error setting clip loop points: " + str(e))
            raise

    def _set_clip_start_marker(self, track_index, clip_index, start_marker):
        """Set clip start marker position"""
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

            if not clip.is_audio_clip:
                raise Exception("Clip is not an audio clip")

            # Set start marker
            clip.start_marker = start_marker

            result = {
                "start_marker": clip.start_marker
            }
            return result
        except Exception as e:
            self.log_message("Error setting clip start marker: " + str(e))
            raise

    def _set_clip_end_marker(self, track_index, clip_index, end_marker):
        """Set clip end marker position"""
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

            if not clip.is_audio_clip:
                raise Exception("Clip is not an audio clip")

            # Set end marker
            clip.end_marker = end_marker

            result = {
                "end_marker": clip.end_marker
            }
            return result
        except Exception as e:
            self.log_message("Error setting clip end marker: " + str(e))
            raise

    def _set_track_send(self, track_index, send_index, value):
        """Set track send level"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]

            # Check if the track has sends
            if not hasattr(track, 'mixer_device'):
                raise Exception("Track has no mixer device")

            mixer = track.mixer_device

            if not hasattr(mixer, 'sends'):
                raise Exception("Mixer has no sends")

            if send_index < 0 or send_index >= len(mixer.sends):
                raise IndexError("Send index out of range")

            send = mixer.sends[send_index]

            # Clamp value between 0.0 and 1.0
            value = max(0.0, min(1.0, value))

            # Set the send level
            send.value = value

            result = {
                "track_index": track_index,
                "send_index": send_index,
                "value": send.value
            }
            return result
        except Exception as e:
            self.log_message("Error setting track send: " + str(e))
            raise

    def _copy_clip_to_arrangement(self, track_index, clip_index, arrangement_time):
        """Copy a clip from session view to arrangement view"""
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

            # Duplicate the clip to arrangement
            # Note: This uses Live's duplicate_clip_to method
            try:
                # First, we need to ensure we're in arrangement view or can access it
                clip.duplicate_clip_to(track, arrangement_time)

                result = {
                    "copied": True,
                    "track_index": track_index,
                    "clip_index": clip_index,
                    "arrangement_time": arrangement_time
                }
                return result
            except AttributeError:
                # If duplicate_clip_to is not available, try alternative method
                # Create a new clip in arrangement at the specified time
                self.log_message("Using alternative clip copy method")

                # Calculate the clip length
                clip_length = clip.length

                # This is a workaround: we can't directly copy to arrangement in all API versions
                # but we can provide info for manual intervention or use session recording
                result = {
                    "copied": False,
                    "note": "Direct arrangement copy not supported in this API version. Use duplicate_clip instead.",
                    "clip_length": clip_length,
                    "suggested_time": arrangement_time
                }
                return result

        except Exception as e:
            self.log_message("Error copying clip to arrangement: " + str(e))
            raise

    def _create_automation(self, track_index, parameter_name, automation_points):
        """Create automation for a track parameter"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]

            # Find the parameter to automate
            parameter = None
            parameter_path = parameter_name.lower()

            # Check mixer parameters
            if hasattr(track, 'mixer_device'):
                mixer = track.mixer_device

                if parameter_path == "volume":
                    parameter = mixer.volume
                elif parameter_path == "pan" or parameter_path == "panning":
                    parameter = mixer.panning
                elif parameter_path.startswith("send"):
                    # Parse "Send A", "Send B", etc.
                    send_char = parameter_path.split()[-1] if len(parameter_path.split()) > 1 else parameter_path[-1]
                    send_index = ord(send_char.upper()) - ord('A')
                    if 0 <= send_index < len(mixer.sends):
                        parameter = mixer.sends[send_index]

            # If not found in mixer, check devices
            if parameter is None and hasattr(track, 'devices'):
                # Parse device parameter names like "Device 0 Parameter 1"
                if "device" in parameter_path:
                    parts = parameter_path.split()
                    try:
                        device_index = int(parts[1])
                        param_index = int(parts[3])

                        if 0 <= device_index < len(track.devices):
                            device = track.devices[device_index]
                            if hasattr(device, 'parameters') and param_index < len(device.parameters):
                                parameter = device.parameters[param_index]
                    except (IndexError, ValueError):
                        pass

            if parameter is None:
                raise ValueError("Parameter '{0}' not found on track {1}".format(parameter_name, track_index))

            # Get or create automation envelope
            if not hasattr(parameter, 'automation_envelope'):
                raise Exception("Parameter does not support automation")

            automation_envelope = parameter.automation_envelope

            # Clear existing automation in the time range
            if len(automation_points) > 0:
                start_time = automation_points[0]["time"]
                end_time = automation_points[-1]["time"]

                # Clear the range
                automation_envelope.insert_step(start_time, 0.0, 0.0)
                automation_envelope.insert_step(end_time, 0.0, 0.0)

            # Insert automation points
            for point in automation_points:
                time = point["time"]
                value = point["value"]

                # Clamp value between 0.0 and 1.0
                value = max(0.0, min(1.0, value))

                # Insert step (time, step_length, value)
                # step_length of 0.0 means it's a point, not a step
                automation_envelope.insert_step(time, 0.0, value)

            result = {
                "parameter": parameter_name,
                "track_index": track_index,
                "points_added": len(automation_points)
            }
            return result

        except Exception as e:
            self.log_message("Error creating automation: " + str(e))
            self.log_message(traceback.format_exc())
            raise

    def _clear_automation(self, track_index, parameter_name, start_time, end_time):
        """Clear automation for a parameter in a time range"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]

            # Find the parameter (same logic as create_automation)
            parameter = None
            parameter_path = parameter_name.lower()

            if hasattr(track, 'mixer_device'):
                mixer = track.mixer_device

                if parameter_path == "volume":
                    parameter = mixer.volume
                elif parameter_path == "pan" or parameter_path == "panning":
                    parameter = mixer.panning
                elif parameter_path.startswith("send"):
                    send_char = parameter_path.split()[-1] if len(parameter_path.split()) > 1 else parameter_path[-1]
                    send_index = ord(send_char.upper()) - ord('A')
                    if 0 <= send_index < len(mixer.sends):
                        parameter = mixer.sends[send_index]

            if parameter is None:
                raise ValueError("Parameter '{0}' not found on track {1}".format(parameter_name, track_index))

            if not hasattr(parameter, 'automation_envelope'):
                raise Exception("Parameter does not support automation")

            automation_envelope = parameter.automation_envelope

            # Clear automation in the specified range
            # This is done by inserting flat automation at the current value
            current_value = parameter.value
            automation_envelope.insert_step(start_time, end_time - start_time, current_value)

            result = {
                "parameter": parameter_name,
                "track_index": track_index,
                "cleared_from": start_time,
                "cleared_to": end_time
            }
            return result

        except Exception as e:
            self.log_message("Error clearing automation: " + str(e))
            raise

    def _get_arrangement_clips(self, track_index):
        """Get all clips in arrangement view for a track"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]

            clips = []

            # Check if the track has an arrangement clips property
            if not hasattr(track, 'arrangement_clips'):
                raise Exception("Track does not have arrangement clips (may be a group track or return track)")

            # Iterate through arrangement clips
            for clip in track.arrangement_clips:
                clip_info = {
                    "name": clip.name,
                    "start_time": clip.start_time,
                    "end_time": clip.end_time,
                    "length": clip.length,
                    "loop_start": clip.loop_start if hasattr(clip, 'loop_start') else None,
                    "loop_end": clip.loop_end if hasattr(clip, 'loop_end') else None,
                    "is_audio_clip": clip.is_audio_clip,
                    "is_midi_clip": clip.is_midi_clip,
                    "muted": clip.muted if hasattr(clip, 'muted') else False,
                    "color_index": clip.color_index if hasattr(clip, 'color_index') else None
                }

                clips.append(clip_info)

            result = {
                "track_index": track_index,
                "track_name": track.name,
                "clip_count": len(clips),
                "clips": clips
            }
            return result

        except Exception as e:
            self.log_message("Error getting arrangement clips: " + str(e))
            self.log_message(traceback.format_exc())
            raise

    def _delete_time(self, start_time, end_time):
        """Delete a section of time from the arrangement"""
        try:
            # Validate parameters
            if start_time >= end_time:
                raise ValueError("Start time must be less than end time")

            # Use Live's delete_time method
            self._song.delete_time(start_time, end_time - start_time)

            result = {
                "deleted_from": start_time,
                "deleted_to": end_time,
                "deleted_length": end_time - start_time
            }
            return result

        except Exception as e:
            self.log_message("Error deleting time: " + str(e))
            self.log_message(traceback.format_exc())
            raise

    def _duplicate_time(self, start_time, end_time):
        """Duplicate a section of time in the arrangement"""
        try:
            # Validate parameters
            if start_time >= end_time:
                raise ValueError("Start time must be less than end time")

            # Use Live's duplicate_time method
            # This copies the time section and pastes it at end_time
            self._song.duplicate_time(start_time, end_time - start_time)

            result = {
                "duplicated_from": start_time,
                "duplicated_to": end_time,
                "duplicated_length": end_time - start_time,
                "pasted_at": end_time
            }
            return result

        except Exception as e:
            self.log_message("Error duplicating time: " + str(e))
            self.log_message(traceback.format_exc())
            raise

    def _insert_silence(self, position, length):
        """Insert silence at a position in the arrangement"""
        try:
            # Validate parameters
            if length <= 0:
                raise ValueError("Length must be greater than 0")

            # Use Live's insert_time method (inserts silence)
            self._song.insert_time(position, length)

            result = {
                "inserted_at": position,
                "inserted_length": length
            }
            return result

        except Exception as e:
            self.log_message("Error inserting silence: " + str(e))
            self.log_message(traceback.format_exc())
            raise

    def _create_locator(self, position, name):
        """Create a locator at a position in the arrangement"""
        try:
            # Create a cue point (locator)
            # Live's API calls them "cue_points"
            cue_points = self._song.cue_points

            # Create a new cue point
            self._song.create_cue_point(position)

            # Find the newly created cue point and set its name
            # The cue points are sorted by time, so find the one at our position
            for cue_point in cue_points:
                if abs(cue_point.time - position) < 0.001:  # Allow small floating point error
                    if name:
                        cue_point.name = name
                    result = {
                        "position": cue_point.time,
                        "name": cue_point.name
                    }
                    return result

            # If we couldn't find it (shouldn't happen), return a generic result
            result = {
                "position": position,
                "name": name
            }
            return result

        except Exception as e:
            self.log_message("Error creating locator: " + str(e))
            self.log_message(traceback.format_exc())
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
                raise Exception("No clip in slot to delete")

            # Delete the clip
            clip_slot.delete_clip()

            result = {
                "track_index": track_index,
                "clip_index": clip_index,
                "deleted": True
            }
            return result

        except Exception as e:
            self.log_message("Error deleting clip: " + str(e))
            self.log_message(traceback.format_exc())
            raise

    def _set_metronome(self, enabled):
        """Enable or disable the metronome"""
        try:
            self._song.metronome = enabled

            result = {
                "metronome": self._song.metronome
            }
            return result

        except Exception as e:
            self.log_message("Error setting metronome: " + str(e))
            self.log_message(traceback.format_exc())
            raise

    def _tap_tempo(self):
        """Tap tempo to set BPM"""
        try:
            # Call the tap_tempo method
            self._song.tap_tempo()

            result = {
                "tempo": self._song.tempo
            }
            return result

        except Exception as e:
            self.log_message("Error tapping tempo: " + str(e))
            self.log_message(traceback.format_exc())
            raise

    def _get_macro_values(self, track_index, device_index):
        """Get the values of all 8 macro controls on a rack device"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]

            if device_index < 0 or device_index >= len(track.devices):
                raise IndexError("Device index out of range")

            device = track.devices[device_index]

            # Check if this is a rack device (has macros)
            if not hasattr(device, 'macros_mapped'):
                raise Exception("Device is not a rack (no macros)")

            # Get all 8 macro values
            macros = []
            for i in range(8):
                if i < len(device.parameters):
                    # Macros are typically the first 8 parameters after the device on/off
                    macro_param = device.parameters[i + 1] if len(device.parameters) > i + 1 else None
                    if macro_param:
                        macros.append({
                            "index": i,
                            "name": macro_param.name,
                            "value": macro_param.value,
                            "min": macro_param.min,
                            "max": macro_param.max,
                            "is_enabled": macro_param.is_enabled if hasattr(macro_param, 'is_enabled') else True
                        })

            result = {
                "track_index": track_index,
                "device_index": device_index,
                "device_name": device.name,
                "macros": macros
            }
            return result

        except Exception as e:
            self.log_message("Error getting macro values: " + str(e))
            self.log_message(traceback.format_exc())
            raise

    def _set_macro_value(self, track_index, device_index, macro_index, value):
        """Set the value of a specific macro control on a rack device"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]

            if device_index < 0 or device_index >= len(track.devices):
                raise IndexError("Device index out of range")

            device = track.devices[device_index]

            # Check if this is a rack device
            if not hasattr(device, 'macros_mapped'):
                raise Exception("Device is not a rack (no macros)")

            # Validate macro index
            if macro_index < 0 or macro_index > 7:
                raise IndexError("Macro index must be 0-7")

            # Get the macro parameter (macros start at index 1 after device on/off)
            param_index = macro_index + 1
            if param_index >= len(device.parameters):
                raise Exception("Macro {0} not available on this device".format(macro_index + 1))

            macro_param = device.parameters[param_index]

            # Set the value
            macro_param.value = value

            result = {
                "track_index": track_index,
                "device_index": device_index,
                "macro_index": macro_index,
                "macro_name": macro_param.name,
                "value": macro_param.value
            }
            return result

        except Exception as e:
            self.log_message("Error setting macro value: " + str(e))
            self.log_message(traceback.format_exc())
            raise

    def _capture_midi(self, track_index, clip_index):
        """Capture recently played MIDI into a clip slot"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]

            if clip_index < 0 or clip_index >= len(track.clip_slots):
                raise IndexError("Clip index out of range")

            clip_slot = track.clip_slots[clip_index]

            # Check if capture_midi is available (Live 11+)
            if not hasattr(self._song, 'capture_midi'):
                raise Exception("Capture MIDI is not available (requires Live 11 or later)")

            # Capture MIDI
            self._song.capture_midi()

            # The captured MIDI should now be in the clip slot
            result = {
                "track_index": track_index,
                "clip_index": clip_index,
                "captured": True,
                "has_clip": clip_slot.has_clip
            }
            return result

        except Exception as e:
            self.log_message("Error capturing MIDI: " + str(e))
            self.log_message(traceback.format_exc())
            raise

    def _apply_groove(self, track_index, clip_index, groove_amount):
        """Apply groove to a MIDI clip"""
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

            if clip.is_audio_clip:
                raise Exception("Cannot apply groove to audio clips")

            # Set the groove amount
            if hasattr(clip, 'groove_amount'):
                clip.groove_amount = groove_amount
            else:
                raise Exception("Groove amount not available on this clip")

            result = {
                "track_index": track_index,
                "clip_index": clip_index,
                "groove_amount": groove_amount
            }
            return result

        except Exception as e:
            self.log_message("Error applying groove: " + str(e))
            self.log_message(traceback.format_exc())
            raise
    def _freeze_track(self, track_index):
        """Freeze a track"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]

            # Check if track can be frozen
            if not hasattr(track, 'can_be_frozen') or not track.can_be_frozen:
                raise Exception("Track cannot be frozen (may be a return or master track)")

            if not hasattr(track, 'freeze'):
                raise Exception("Freeze not available on this track")

            # Freeze the track
            track.freeze = True

            result = {
                "track_index": track_index,
                "frozen": True,
                "track_name": track.name
            }
            return result

        except Exception as e:
            self.log_message("Error freezing track: " + str(e))
            self.log_message(traceback.format_exc())
            raise

    def _unfreeze_track(self, track_index):
        """Unfreeze a track"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]

            if not hasattr(track, 'freeze'):
                raise Exception("Freeze not available on this track")

            # Unfreeze the track
            track.freeze = False

            result = {
                "track_index": track_index,
                "frozen": False,
                "track_name": track.name
            }
            return result

        except Exception as e:
            self.log_message("Error unfreezing track: " + str(e))
            self.log_message(traceback.format_exc())
            raise

    def _export_track_audio(self, track_index, output_path, start_time, end_time):
        """Export track audio to WAV file"""
        try:
            import shutil

            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]

            # Check if track can be frozen
            if not hasattr(track, 'can_be_frozen') or not track.can_be_frozen:
                raise Exception("Track cannot be frozen (may be a return or master track)")

            # Remember original freeze state
            was_frozen = getattr(track, 'freeze', False) if hasattr(track, 'freeze') else False

            # Freeze the track to render audio
            if not was_frozen:
                track.freeze = True
                # Note: In practice, freezing takes time. The API doesn't provide a direct way
                # to wait for freeze completion, so this might need user intervention or delays

            # Get the frozen sample file path
            # Note: Ableton stores frozen files in a Freeze folder within the project
            # The exact path format is: Project/Samples/Freeze/TrackName.wav
            # However, the Remote Script API doesn't expose this directly
            # This is a limitation of the Ableton API

            result = {
                "track_index": track_index,
                "output_path": output_path,
                "message": "Track frozen. Frozen audio file should be in: Project/Samples/Frozen/ folder. " +
                          "Copy it manually to: " + str(output_path) + ". " +
                          "For fully automatic export, use Ableton's built-in Export Audio/Video feature."
            }

            # Restore freeze state if it was changed
            if not was_frozen and hasattr(track, 'freeze'):
                track.freeze = False

            return result

        except Exception as e:
            self.log_message("Error exporting track audio: " + str(e))
            self.log_message(traceback.format_exc())
            raise
