# AbletonMCP/init.py
from __future__ import absolute_import, print_function, unicode_literals

from _Framework.ControlSurface import ControlSurface
import Live
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
            elif command_type == "get_scenes":
                response["result"] = self._get_scenes()
            elif command_type == "get_return_tracks":
                response["result"] = self._get_return_tracks()
            elif command_type == "get_device_parameters":
                track_index = params.get("track_index", 0)
                device_index = params.get("device_index", 0)
                response["result"] = self._get_device_parameters(track_index, device_index)
            elif command_type == "get_notes_from_clip":
                track_index = params.get("track_index", 0)
                clip_index = params.get("clip_index", 0)
                response["result"] = self._get_notes_from_clip(track_index, clip_index)
            elif command_type == "get_current_song_time":
                response["result"] = self._get_current_song_time()
            elif command_type == "get_clip_info":
                track_index = params.get("track_index", 0)
                clip_index = params.get("clip_index", 0)
                response["result"] = self._get_clip_info(track_index, clip_index)
            elif command_type == "get_clip_slot_info":
                track_index = params.get("track_index", 0)
                clip_index = params.get("clip_index", 0)
                response["result"] = self._get_clip_slot_info(track_index, clip_index)
            elif command_type == "get_track_routing":
                track_index = params.get("track_index", 0)
                response["result"] = self._get_track_routing(track_index)
            elif command_type == "get_available_routings":
                track_index = params.get("track_index", 0)
                response["result"] = self._get_available_routings(track_index)
            elif command_type == "get_arrangement_clips":
                track_index = params.get("track_index", 0)
                response["result"] = self._get_arrangement_clips(track_index)
            elif command_type == "get_cue_points":
                response["result"] = self._get_cue_points()
            elif command_type == "get_arrangement_loop":
                response["result"] = self._get_arrangement_loop()
            # Commands that modify Live's state should be scheduled on the main thread
            elif command_type in ["create_midi_track", "set_track_name",
                                 "create_clip", "add_notes_to_clip", "set_clip_name",
                                 "set_tempo", "fire_clip", "stop_clip",
                                 "start_playback", "stop_playback", "load_browser_item",
                                 "create_return_track", "set_send", "set_return_track_name",
                                 "load_device_on_return",
                                 "set_track_volume", "set_track_panning",
                                 "set_track_mute", "set_track_solo", "set_track_arm",
                                 "set_track_color",
                                 "set_return_track_volume", "set_return_track_panning",
                                 "set_return_track_mute", "set_return_track_color",
                                 "set_master_volume", "set_master_panning",
                                 "create_scene", "delete_scene", "fire_scene",
                                 "set_scene_name", "set_scene_color", "set_scene_tempo",
                                 "duplicate_scene", "stop_all_clips",
                                 "set_device_parameter",
                                 "set_clip_loop", "set_clip_color",
                                 "duplicate_clip", "quantize_clip",
                                 "set_current_song_time", "set_arrangement_record",
                                 "set_session_record", "set_overdub", "set_metronome",
                                 "tap_tempo", "set_nudge_up", "set_nudge_down",
                                 "undo", "redo",
                                 "set_time_signature",
                                 "set_input_routing", "set_output_routing",
                                 "set_audio_clip_gain", "set_audio_clip_pitch",
                                 "set_audio_clip_warp",
                                 "remove_notes_from_clip", "apply_note_modifications",
                                 "set_or_delete_cue", "set_arrangement_loop",
                                 "set_punch_points", "jump_to_cue"]:
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
                        elif command_type == "create_return_track":
                            result = self._create_return_track()
                        elif command_type == "set_send":
                            source_track_index = params.get("source_track_index", 0)
                            return_track_index = params.get("return_track_index", 0)
                            send_amount = params.get("send_amount", 0.0)
                            result = self._set_send(source_track_index, return_track_index, send_amount)
                        elif command_type == "set_return_track_name":
                            return_track_index = params.get("return_track_index", 0)
                            name = params.get("name", "")
                            result = self._set_return_track_name(return_track_index, name)
                        elif command_type == "load_device_on_return":
                            return_track_index = params.get("return_track_index", 0)
                            item_uri = params.get("item_uri", "")
                            result = self._load_device_on_return(return_track_index, item_uri)
                        elif command_type == "set_track_volume":
                            result = self._set_track_volume(params.get("track_index", 0), params.get("volume", 0.85))
                        elif command_type == "set_track_panning":
                            result = self._set_track_panning(params.get("track_index", 0), params.get("panning", 0.0))
                        elif command_type == "set_track_mute":
                            result = self._set_track_mute(params.get("track_index", 0), params.get("mute", False))
                        elif command_type == "set_track_solo":
                            result = self._set_track_solo(params.get("track_index", 0), params.get("solo", False))
                        elif command_type == "set_track_arm":
                            result = self._set_track_arm(params.get("track_index", 0), params.get("arm", False))
                        elif command_type == "set_track_color":
                            result = self._set_track_color(params.get("track_index", 0), params.get("color", 0))
                        elif command_type == "set_return_track_volume":
                            result = self._set_return_track_volume(params.get("return_track_index", 0), params.get("volume", 0.85))
                        elif command_type == "set_return_track_panning":
                            result = self._set_return_track_panning(params.get("return_track_index", 0), params.get("panning", 0.0))
                        elif command_type == "set_return_track_mute":
                            result = self._set_return_track_mute(params.get("return_track_index", 0), params.get("mute", False))
                        elif command_type == "set_return_track_color":
                            result = self._set_return_track_color(params.get("return_track_index", 0), params.get("color", 0))
                        elif command_type == "set_master_volume":
                            result = self._set_master_volume(params.get("volume", 0.85))
                        elif command_type == "set_master_panning":
                            result = self._set_master_panning(params.get("panning", 0.0))
                        elif command_type == "create_scene":
                            result = self._create_scene(params.get("index", -1))
                        elif command_type == "delete_scene":
                            result = self._delete_scene(params.get("scene_index", 0))
                        elif command_type == "fire_scene":
                            result = self._fire_scene(params.get("scene_index", 0))
                        elif command_type == "set_scene_name":
                            result = self._set_scene_name(params.get("scene_index", 0), params.get("name", ""))
                        elif command_type == "set_scene_color":
                            result = self._set_scene_color(params.get("scene_index", 0), params.get("color", 0))
                        elif command_type == "set_scene_tempo":
                            result = self._set_scene_tempo(params.get("scene_index", 0), params.get("tempo", 0.0))
                        elif command_type == "duplicate_scene":
                            result = self._duplicate_scene(params.get("scene_index", 0))
                        elif command_type == "stop_all_clips":
                            result = self._stop_all_clips()
                        elif command_type == "set_device_parameter":
                            result = self._set_device_parameter(
                                params.get("track_index", 0),
                                params.get("device_index", 0),
                                params.get("param_index", 0),
                                params.get("value", 0.0)
                            )
                        elif command_type == "set_clip_loop":
                            result = self._set_clip_loop(
                                params.get("track_index", 0),
                                params.get("clip_index", 0),
                                params.get("loop_start", 0.0),
                                params.get("loop_end", 4.0),
                                params.get("loop_on", True)
                            )
                        elif command_type == "set_clip_color":
                            result = self._set_clip_color(
                                params.get("track_index", 0),
                                params.get("clip_index", 0),
                                params.get("color", 0)
                            )
                        elif command_type == "duplicate_clip":
                            result = self._duplicate_clip(
                                params.get("track_index", 0),
                                params.get("clip_index", 0),
                                params.get("target_clip_index", 1)
                            )
                        elif command_type == "quantize_clip":
                            result = self._quantize_clip(
                                params.get("track_index", 0),
                                params.get("clip_index", 0),
                                params.get("quantize_to", 0.25),
                                params.get("amount", 1.0)
                            )
                        elif command_type == "set_current_song_time":
                            result = self._set_current_song_time(params.get("time", 0.0))
                        elif command_type == "set_arrangement_record":
                            result = self._set_arrangement_record(params.get("record", False))
                        elif command_type == "set_session_record":
                            result = self._set_session_record(params.get("record", False))
                        elif command_type == "set_overdub":
                            result = self._set_overdub(params.get("overdub", False))
                        elif command_type == "set_metronome":
                            result = self._set_metronome(params.get("metronome", False))
                        elif command_type == "tap_tempo":
                            result = self._tap_tempo()
                        elif command_type == "set_nudge_up":
                            result = self._set_nudge_up(params.get("nudge", False))
                        elif command_type == "set_nudge_down":
                            result = self._set_nudge_down(params.get("nudge", False))
                        elif command_type == "undo":
                            result = self._undo()
                        elif command_type == "redo":
                            result = self._redo()
                        elif command_type == "set_time_signature":
                            result = self._set_time_signature(
                                params.get("numerator"), params.get("denominator"))
                        elif command_type == "set_input_routing":
                            result = self._set_input_routing(
                                params.get("track_index", 0),
                                params.get("routing_type_name", ""))
                        elif command_type == "set_output_routing":
                            result = self._set_output_routing(
                                params.get("track_index", 0),
                                params.get("routing_type_name", ""))
                        elif command_type == "set_audio_clip_gain":
                            result = self._set_audio_clip_gain(
                                params.get("track_index", 0),
                                params.get("clip_index", 0),
                                params.get("gain"))
                        elif command_type == "set_audio_clip_pitch":
                            result = self._set_audio_clip_pitch(
                                params.get("track_index", 0),
                                params.get("clip_index", 0),
                                params.get("pitch_coarse"),
                                params.get("pitch_fine"))
                        elif command_type == "set_audio_clip_warp":
                            result = self._set_audio_clip_warp(
                                params.get("track_index", 0),
                                params.get("clip_index", 0),
                                params.get("warping"),
                                params.get("warp_mode"))
                        elif command_type == "remove_notes_from_clip":
                            result = self._remove_notes_from_clip(
                                params.get("track_index", 0),
                                params.get("clip_index", 0),
                                params.get("from_pitch", 0),
                                params.get("pitch_span", 128),
                                params.get("from_time", 0.0),
                                params.get("time_span", 1e9))
                        elif command_type == "apply_note_modifications":
                            result = self._apply_note_modifications(
                                params.get("track_index", 0),
                                params.get("clip_index", 0),
                                params.get("notes", []))
                        elif command_type == "set_or_delete_cue":
                            result = self._set_or_delete_cue()
                        elif command_type == "set_arrangement_loop":
                            result = self._set_arrangement_loop(
                                params.get("loop_start"),
                                params.get("loop_length"),
                                params.get("loop_on"))
                        elif command_type == "set_punch_points":
                            result = self._set_punch_points(
                                params.get("punch_in"),
                                params.get("punch_out"))
                        elif command_type == "jump_to_cue":
                            result = self._jump_to_cue(params.get("direction", "next"))

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
            elif command_type == "get_return_tracks":
                response["result"] = self._get_return_tracks()
            # Add the new browser commands
            elif command_type == "get_browser_tree":
                category_type = params.get("category_type", "all")
                response["result"] = self.get_browser_tree(category_type)
            elif command_type == "get_browser_items_at_path":
                path = params.get("path", "")
                response["result"] = self.get_browser_items_at_path(path)
            elif command_type == "get_audio_clip_info":
                response["result"] = self._get_audio_clip_info(
                    params.get("track_index", 0),
                    params.get("clip_index", 0))
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
            
            sends = []
            for send in track.mixer_device.sends:
                sends.append(send.value)

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
                "color": track.color,
                "sends": sends,
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

            specs = []
            for note in notes:
                spec = Live.Clip.MidiNoteSpecification(
                    pitch=note.get("pitch", 60),
                    start_time=note.get("start_time", 0.0),
                    duration=note.get("duration", 0.25),
                    velocity=note.get("velocity", 100),
                    mute=note.get("mute", False)
                )
                specs.append(spec)

            clip.add_new_notes(tuple(specs))

            return {"note_count": len(specs)}
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
    
    def _get_current_song_time(self):
        """Return current playback position in beats."""
        try:
            return {"current_song_time": self._song.current_song_time}
        except Exception as e:
            self.log_message("Error getting song time: " + str(e))
            raise

    def _set_current_song_time(self, time):
        """Jump playback position to a beat position."""
        try:
            if time < 0:
                raise Exception("Song time must be >= 0")
            self._song.current_song_time = time
            return {"current_song_time": self._song.current_song_time}
        except Exception as e:
            self.log_message("Error setting song time: " + str(e))
            raise

    def _set_arrangement_record(self, record):
        """Enable or disable arrangement recording."""
        try:
            self._song.record_mode = record
            return {"arrangement_record": self._song.record_mode}
        except Exception as e:
            self.log_message("Error setting arrangement record: " + str(e))
            raise

    def _set_session_record(self, record):
        """Enable or disable session recording."""
        try:
            self._song.session_record = record
            return {"session_record": self._song.session_record}
        except Exception as e:
            self.log_message("Error setting session record: " + str(e))
            raise

    def _set_overdub(self, overdub):
        """Enable or disable overdub."""
        try:
            self._song.overdub = overdub
            return {"overdub": self._song.overdub}
        except Exception as e:
            self.log_message("Error setting overdub: " + str(e))
            raise

    def _set_metronome(self, metronome):
        """Enable or disable the metronome."""
        try:
            self._song.metronome = metronome
            return {"metronome": self._song.metronome}
        except Exception as e:
            self.log_message("Error setting metronome: " + str(e))
            raise

    def _tap_tempo(self):
        """Send a tap tempo pulse."""
        try:
            self._song.tap_tempo()
            return {"tempo": self._song.tempo}
        except Exception as e:
            self.log_message("Error tapping tempo: " + str(e))
            raise

    def _set_nudge_up(self, nudge):
        """Set nudge-up state (hold True to nudge tempo up)."""
        try:
            self._song.nudge_up = nudge
            return {"nudge_up": nudge}
        except Exception as e:
            self.log_message("Error setting nudge up: " + str(e))
            raise

    def _set_nudge_down(self, nudge):
        """Set nudge-down state (hold True to nudge tempo down)."""
        try:
            self._song.nudge_down = nudge
            return {"nudge_down": nudge}
        except Exception as e:
            self.log_message("Error setting nudge down: " + str(e))
            raise

    def _undo(self):
        """Undo the last action."""
        try:
            self._song.undo()
            return {"undone": True}
        except Exception as e:
            self.log_message("Error undoing: " + str(e))
            raise

    def _redo(self):
        """Redo the last undone action."""
        try:
            self._song.redo()
            return {"redone": True}
        except Exception as e:
            self.log_message("Error redoing: " + str(e))
            raise

    def _get_clip_info(self, track_index, clip_index):
        """Get detailed info about a clip."""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            track = self._song.tracks[track_index]
            if clip_index < 0 or clip_index >= len(track.clip_slots):
                raise IndexError("Clip index out of range")
            slot = track.clip_slots[clip_index]
            if not slot.has_clip:
                raise Exception("No clip in slot")
            clip = slot.clip
            return {
                "track_index": track_index,
                "clip_index": clip_index,
                "name": clip.name,
                "length": clip.length,
                "color": clip.color,
                "is_audio_clip": clip.is_audio_clip,
                "is_midi_clip": clip.is_midi_clip,
                "is_playing": clip.is_playing,
                "is_recording": clip.is_recording,
                "loop_on": clip.looping,
                "loop_start": clip.loop_start,
                "loop_end": clip.loop_end,
                "start_marker": clip.start_marker,
                "end_marker": clip.end_marker,
            }
        except Exception as e:
            self.log_message("Error getting clip info: " + str(e))
            raise

    def _get_clip_slot_info(self, track_index, clip_index):
        """Get state of a clip slot."""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            track = self._song.tracks[track_index]
            if clip_index < 0 or clip_index >= len(track.clip_slots):
                raise IndexError("Clip index out of range")
            slot = track.clip_slots[clip_index]
            clip_info = None
            if slot.has_clip:
                clip = slot.clip
                clip_info = {
                    "name": clip.name,
                    "length": clip.length,
                    "color": clip.color,
                    "is_playing": clip.is_playing,
                    "is_recording": clip.is_recording,
                }
            return {
                "track_index": track_index,
                "clip_index": clip_index,
                "has_clip": slot.has_clip,
                "has_stop_button": slot.has_stop_button,
                "is_triggered": slot.is_triggered,
                "clip": clip_info,
            }
        except Exception as e:
            self.log_message("Error getting clip slot info: " + str(e))
            raise

    def _set_time_signature(self, numerator, denominator):
        """Set the song time signature."""
        try:
            valid_denominators = [1, 2, 4, 8, 16, 32]
            if numerator is None or denominator is None:
                raise Exception("numerator and denominator are required")
            if numerator < 1 or numerator > 99:
                raise Exception("Numerator must be between 1 and 99")
            if denominator not in valid_denominators:
                raise Exception("Denominator must be one of: 1, 2, 4, 8, 16, 32")
            self._song.signature_numerator = numerator
            self._song.signature_denominator = denominator
            return {
                "numerator": numerator,
                "denominator": denominator,
            }
        except Exception as e:
            self.log_message("Error setting time signature: " + str(e))
            raise

    def _get_track_routing(self, track_index):
        """Get the current input and output routing for a track."""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            track = self._song.tracks[track_index]
            input_type = track.input_routing_type
            output_type = track.output_routing_type
            input_channel = track.input_routing_channel
            output_channel = track.output_routing_channel
            return {
                "track_index": track_index,
                "input_routing_type": input_type.display_name,
                "input_routing_channel": input_channel.display_name,
                "output_routing_type": output_type.display_name,
                "output_routing_channel": output_channel.display_name,
            }
        except Exception as e:
            self.log_message("Error getting track routing: " + str(e))
            raise

    def _get_available_routings(self, track_index):
        """Get all available input and output routing types for a track."""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            track = self._song.tracks[track_index]
            available_inputs = [r.display_name for r in track.available_input_routing_types]
            available_outputs = [r.display_name for r in track.available_output_routing_types]
            return {
                "track_index": track_index,
                "available_input_routing_types": available_inputs,
                "available_output_routing_types": available_outputs,
            }
        except Exception as e:
            self.log_message("Error getting available routings: " + str(e))
            raise

    def _set_input_routing(self, track_index, routing_type_name):
        """Set the input routing type for a track by display name."""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            track = self._song.tracks[track_index]
            for routing_type in track.available_input_routing_types:
                if routing_type.display_name == routing_type_name:
                    track.input_routing_type = routing_type
                    return {"track_index": track_index, "input_routing_type": routing_type_name}
            available = [r.display_name for r in track.available_input_routing_types]
            raise Exception("Input routing type not found: '{}'. Available: {}".format(
                routing_type_name, available))
        except Exception as e:
            self.log_message("Error setting input routing: " + str(e))
            raise

    def _set_output_routing(self, track_index, routing_type_name):
        """Set the output routing type for a track by display name."""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            track = self._song.tracks[track_index]
            for routing_type in track.available_output_routing_types:
                if routing_type.display_name == routing_type_name:
                    track.output_routing_type = routing_type
                    return {"track_index": track_index, "output_routing_type": routing_type_name}
            available = [r.display_name for r in track.available_output_routing_types]
            raise Exception("Output routing type not found: '{}'. Available: {}".format(
                routing_type_name, available))
        except Exception as e:
            self.log_message("Error setting output routing: " + str(e))
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
    
    def _get_device_parameters(self, track_index, device_index):
        """Get all parameters for a device on a track"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            track = self._song.tracks[track_index]
            if device_index < 0 or device_index >= len(track.devices):
                raise IndexError("Device index out of range")
            device = track.devices[device_index]
            parameters = []
            for param_index, param in enumerate(device.parameters):
                parameters.append({
                    "index": param_index,
                    "name": param.name,
                    "value": param.value,
                    "min": param.min,
                    "max": param.max,
                    "is_quantized": param.is_quantized,
                    "value_string": param.str_for_value(param.value)
                })
            return {
                "track_index": track_index,
                "device_index": device_index,
                "device_name": device.name,
                "parameters": parameters
            }
        except Exception as e:
            self.log_message("Error getting device parameters: " + str(e))
            raise

    def _set_device_parameter(self, track_index, device_index, param_index, value):
        """Set a parameter value on a device"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            track = self._song.tracks[track_index]
            if device_index < 0 or device_index >= len(track.devices):
                raise IndexError("Device index out of range")
            device = track.devices[device_index]
            if param_index < 0 or param_index >= len(device.parameters):
                raise IndexError("Parameter index out of range")
            param = device.parameters[param_index]
            clamped = max(param.min, min(param.max, value))
            param.value = clamped
            return {
                "track_index": track_index,
                "device_index": device_index,
                "device_name": device.name,
                "param_index": param_index,
                "param_name": param.name,
                "value": param.value,
                "value_string": param.str_for_value(param.value)
            }
        except Exception as e:
            self.log_message("Error setting device parameter: " + str(e))
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
    
    def _get_return_tracks(self):
        """Get information about all return tracks"""
        try:
            return_tracks = []
            for index, track in enumerate(self._song.return_tracks):
                devices = []
                for device_index, device in enumerate(track.devices):
                    devices.append({
                        "index": device_index,
                        "name": device.name,
                        "class_name": device.class_name,
                        "type": self._get_device_type(device)
                    })
                return_tracks.append({
                    "index": index,
                    "name": track.name,
                    "mute": track.mute,
                    "volume": track.mixer_device.volume.value,
                    "panning": track.mixer_device.panning.value,
                    "devices": devices
                })
            return {
                "return_track_count": len(return_tracks),
                "return_tracks": return_tracks
            }
        except Exception as e:
            self.log_message("Error getting return tracks: " + str(e))
            raise

    def _create_return_track(self):
        """Create a new return track"""
        try:
            self._song.create_return_track()
            new_track = self._song.return_tracks[-1]
            return {
                "index": len(self._song.return_tracks) - 1,
                "name": new_track.name
            }
        except Exception as e:
            self.log_message("Error creating return track: " + str(e))
            raise

    def _set_return_track_name(self, return_track_index, name):
        """Set the name of a return track"""
        try:
            if return_track_index < 0 or return_track_index >= len(self._song.return_tracks):
                raise IndexError("Return track index out of range")
            track = self._song.return_tracks[return_track_index]
            # Live auto-prepends the letter prefix (A-, B-, …); strip it if caller included it
            if len(name) > 2 and name[1] == '-' and name[0].isupper():
                name = name[2:]
            track.name = name
            return {"name": track.name}
        except Exception as e:
            self.log_message("Error setting return track name: " + str(e))
            raise

    def _set_send(self, source_track_index, return_track_index, send_amount):
        """Set the send amount from a source track to a return track"""
        try:
            if source_track_index < 0 or source_track_index >= len(self._song.tracks):
                raise IndexError("Source track index out of range")
            if return_track_index < 0 or return_track_index >= len(self._song.return_tracks):
                raise IndexError("Return track index out of range")
            send_amount = max(0.0, min(1.0, float(send_amount)))
            source_track = self._song.tracks[source_track_index]
            source_track.mixer_device.sends[return_track_index].value = send_amount
            return {
                "source_track": source_track.name,
                "return_track_index": return_track_index,
                "send_amount": source_track.mixer_device.sends[return_track_index].value
            }
        except Exception as e:
            self.log_message("Error setting send: " + str(e))
            raise

    def _load_device_on_return(self, return_track_index, item_uri):
        """Load an instrument or effect onto a return track by its URI"""
        try:
            if return_track_index < 0 or return_track_index >= len(self._song.return_tracks):
                raise IndexError("Return track index out of range")
            return_track = self._song.return_tracks[return_track_index]
            app = self.application()
            item = self._find_browser_item_by_uri(app.browser, item_uri)
            if not item:
                raise ValueError("Browser item with URI '{0}' not found".format(item_uri))
            self._song.view.selected_track = return_track
            app.browser.load_item(item)
            return {
                "loaded": True,
                "device_name": item.name,
                "return_track_name": return_track.name,
                "return_track_index": return_track_index,
                "uri": item_uri
            }
        except Exception as e:
            self.log_message("Error loading device on return track: " + str(e))
            raise

    def _set_track_volume(self, track_index, volume):
        if track_index < 0 or track_index >= len(self._song.tracks):
            raise IndexError("Track index out of range")
        track = self._song.tracks[track_index]
        track.mixer_device.volume.value = max(0.0, min(1.0, float(volume)))
        return {"track": track.name, "volume": track.mixer_device.volume.value}

    def _set_track_panning(self, track_index, panning):
        if track_index < 0 or track_index >= len(self._song.tracks):
            raise IndexError("Track index out of range")
        track = self._song.tracks[track_index]
        track.mixer_device.panning.value = max(-1.0, min(1.0, float(panning)))
        return {"track": track.name, "panning": track.mixer_device.panning.value}

    def _set_track_mute(self, track_index, mute):
        if track_index < 0 or track_index >= len(self._song.tracks):
            raise IndexError("Track index out of range")
        track = self._song.tracks[track_index]
        track.mute = bool(mute)
        return {"track": track.name, "mute": track.mute}

    def _set_track_solo(self, track_index, solo):
        if track_index < 0 or track_index >= len(self._song.tracks):
            raise IndexError("Track index out of range")
        track = self._song.tracks[track_index]
        track.solo = bool(solo)
        return {"track": track.name, "solo": track.solo}

    def _set_track_arm(self, track_index, arm):
        if track_index < 0 or track_index >= len(self._song.tracks):
            raise IndexError("Track index out of range")
        track = self._song.tracks[track_index]
        track.arm = bool(arm)
        return {"track": track.name, "arm": track.arm}

    def _set_track_color(self, track_index, color):
        if track_index < 0 or track_index >= len(self._song.tracks):
            raise IndexError("Track index out of range")
        track = self._song.tracks[track_index]
        track.color = int(color)
        return {"track": track.name, "color": track.color}

    def _set_return_track_volume(self, return_track_index, volume):
        if return_track_index < 0 or return_track_index >= len(self._song.return_tracks):
            raise IndexError("Return track index out of range")
        track = self._song.return_tracks[return_track_index]
        track.mixer_device.volume.value = max(0.0, min(1.0, float(volume)))
        return {"track": track.name, "volume": track.mixer_device.volume.value}

    def _set_return_track_panning(self, return_track_index, panning):
        if return_track_index < 0 or return_track_index >= len(self._song.return_tracks):
            raise IndexError("Return track index out of range")
        track = self._song.return_tracks[return_track_index]
        track.mixer_device.panning.value = max(-1.0, min(1.0, float(panning)))
        return {"track": track.name, "panning": track.mixer_device.panning.value}

    def _set_return_track_mute(self, return_track_index, mute):
        if return_track_index < 0 or return_track_index >= len(self._song.return_tracks):
            raise IndexError("Return track index out of range")
        track = self._song.return_tracks[return_track_index]
        track.mute = bool(mute)
        return {"track": track.name, "mute": track.mute}

    def _set_return_track_color(self, return_track_index, color):
        if return_track_index < 0 or return_track_index >= len(self._song.return_tracks):
            raise IndexError("Return track index out of range")
        track = self._song.return_tracks[return_track_index]
        track.color = int(color)
        return {"track": track.name, "color": track.color}

    def _set_master_volume(self, volume):
        self._song.master_track.mixer_device.volume.value = max(0.0, min(1.0, float(volume)))
        return {"volume": self._song.master_track.mixer_device.volume.value}

    def _set_master_panning(self, panning):
        self._song.master_track.mixer_device.panning.value = max(-1.0, min(1.0, float(panning)))
        return {"panning": self._song.master_track.mixer_device.panning.value}

    # -------------------------------------------------------------------------
    # Phase 2 — Scene Management
    # -------------------------------------------------------------------------

    def _get_scenes(self):
        scenes = []
        for i, scene in enumerate(self._song.scenes):
            scenes.append({
                "index": i,
                "name": scene.name,
                "color": scene.color,
                "tempo": scene.tempo,
                "is_triggered": scene.is_triggered,
            })
        return {"scene_count": len(scenes), "scenes": scenes}

    def _create_scene(self, index=-1):
        self._song.create_scene(index)
        # Resolve the actual index inserted
        actual_index = index if index >= 0 else len(self._song.scenes) - 1
        scene = self._song.scenes[actual_index]
        return {"index": actual_index, "name": scene.name}

    def _delete_scene(self, scene_index):
        if scene_index < 0 or scene_index >= len(self._song.scenes):
            raise IndexError("Scene index out of range")
        name = self._song.scenes[scene_index].name
        self._song.delete_scene(scene_index)
        return {"deleted_index": scene_index, "name": name}

    def _fire_scene(self, scene_index):
        if scene_index < 0 or scene_index >= len(self._song.scenes):
            raise IndexError("Scene index out of range")
        scene = self._song.scenes[scene_index]
        scene.fire()
        return {"index": scene_index, "name": scene.name}

    def _set_scene_name(self, scene_index, name):
        if scene_index < 0 or scene_index >= len(self._song.scenes):
            raise IndexError("Scene index out of range")
        self._song.scenes[scene_index].name = name
        return {"index": scene_index, "name": self._song.scenes[scene_index].name}

    def _set_scene_color(self, scene_index, color):
        if scene_index < 0 or scene_index >= len(self._song.scenes):
            raise IndexError("Scene index out of range")
        scene = self._song.scenes[scene_index]
        scene.color = int(color)
        return {"index": scene_index, "name": scene.name, "color": scene.color}

    def _set_scene_tempo(self, scene_index, tempo):
        if scene_index < 0 or scene_index >= len(self._song.scenes):
            raise IndexError("Scene index out of range")
        scene = self._song.scenes[scene_index]
        # tempo=0.0 means "no override" in Live's LOM
        scene.tempo = float(tempo)
        return {"index": scene_index, "name": scene.name, "tempo": scene.tempo}

    def _duplicate_scene(self, scene_index):
        if scene_index < 0 or scene_index >= len(self._song.scenes):
            raise IndexError("Scene index out of range")
        self._song.duplicate_scene(scene_index)
        new_index = scene_index + 1
        scene = self._song.scenes[new_index]
        return {"source_index": scene_index, "new_index": new_index, "name": scene.name}

    def _stop_all_clips(self):
        self._song.stop_all_clips()
        return {"stopped": True}

    def _get_clip(self, track_index, clip_index):
        """Helper: return clip or raise."""
        if track_index < 0 or track_index >= len(self._song.tracks):
            raise IndexError("Track index out of range")
        track = self._song.tracks[track_index]
        if clip_index < 0 or clip_index >= len(track.clip_slots):
            raise IndexError("Clip index out of range")
        clip_slot = track.clip_slots[clip_index]
        if not clip_slot.has_clip:
            raise Exception("No clip in slot")
        return clip_slot.clip

    def _get_notes_from_clip(self, track_index, clip_index):
        """Get all MIDI notes from a clip."""
        try:
            clip = self._get_clip(track_index, clip_index)
            if not clip.is_midi_clip:
                raise Exception("Clip is not a MIDI clip")
            notes = clip.get_notes_extended(from_pitch=0, pitch_span=128, from_time=0, time_span=clip.length)
            return {
                "track_index": track_index,
                "clip_index": clip_index,
                "clip_name": clip.name,
                "clip_length": clip.length,
                "notes": [
                    {
                        "pitch": n.pitch,
                        "start_time": n.start_time,
                        "duration": n.duration,
                        "velocity": n.velocity,
                        "mute": n.mute,
                    }
                    for n in notes
                ],
            }
        except Exception as e:
            self.log_message("Error getting notes: " + str(e))
            raise

    def _remove_notes_from_clip(self, track_index, clip_index, from_pitch, pitch_span, from_time, time_span):
        """Remove notes from a clip in a pitch/time range."""
        try:
            clip = self._get_clip(track_index, clip_index)
            if not clip.is_midi_clip:
                raise Exception("Clip is not a MIDI clip")
            clip.remove_notes_extended(
                from_pitch=from_pitch,
                pitch_span=pitch_span,
                from_time=from_time,
                time_span=time_span
            )
            return {"success": True}
        except Exception as e:
            self.log_message("Error removing notes: " + str(e))
            raise

    def _apply_note_modifications(self, track_index, clip_index, notes):
        """Apply in-place modifications to existing notes via get_notes_extended + apply_note_modifications."""
        try:
            clip = self._get_clip(track_index, clip_index)
            if not clip.is_midi_clip:
                raise Exception("Clip is not a MIDI clip")
            all_notes = clip.get_notes_extended(from_pitch=0, pitch_span=128, from_time=0, time_span=clip.length)
            # Build lookup: (pitch, start_time) -> MidiNote
            note_map = {(n.pitch, round(n.start_time, 6)): n for n in all_notes}
            updated = 0
            for mod in notes:
                key = (mod["pitch"], round(mod["start_time"], 6))
                if key in note_map:
                    n = note_map[key]
                    if "new_pitch" in mod:
                        n.pitch = mod["new_pitch"]
                    if "new_start_time" in mod:
                        n.start_time = mod["new_start_time"]
                    if "new_duration" in mod:
                        n.duration = mod["new_duration"]
                    if "new_velocity" in mod:
                        n.velocity = mod["new_velocity"]
                    if "new_mute" in mod:
                        n.mute = mod["new_mute"]
                    updated += 1
            clip.apply_note_modifications(all_notes)
            return {"updated": updated}
        except Exception as e:
            self.log_message("Error applying note modifications: " + str(e))
            raise

    def _get_arrangement_clips(self, track_index):
        """Get all clips in the arrangement view for a track."""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            track = self._song.tracks[track_index]
            clips = []
            for clip in track.arrangement_clips:
                clips.append({
                    "name": clip.name,
                    "start_time": clip.start_time,
                    "end_time": clip.end_time,
                    "length": clip.length,
                    "color": clip.color,
                    "is_audio_clip": clip.is_audio_clip,
                    "is_midi_clip": clip.is_midi_clip,
                    "muted": clip.muted,
                })
            return {"track_index": track_index, "clips": clips}
        except Exception as e:
            self.log_message("Error getting arrangement clips: " + str(e))
            raise

    def _get_cue_points(self):
        """Get all cue points (locators) in the arrangement."""
        try:
            cue_points = []
            for cp in self._song.cue_points:
                cue_points.append({"name": cp.name, "time": cp.time})
            return {"cue_points": cue_points}
        except Exception as e:
            self.log_message("Error getting cue points: " + str(e))
            raise

    def _set_or_delete_cue(self):
        """Create or delete a cue point at the current song time."""
        try:
            time_before = [cp.time for cp in self._song.cue_points]
            self._song.set_or_delete_cue()
            time_after = [cp.time for cp in self._song.cue_points]
            if len(time_after) > len(time_before):
                action = "created"
            else:
                action = "deleted"
            return {"action": action, "cue_points": [{"name": cp.name, "time": cp.time} for cp in self._song.cue_points]}
        except Exception as e:
            self.log_message("Error setting/deleting cue: " + str(e))
            raise

    def _get_arrangement_loop(self):
        """Get the current arrangement loop state."""
        try:
            return {
                "loop": self._song.loop,
                "loop_start": self._song.loop_start,
                "loop_length": self._song.loop_length,
                "punch_in": self._song.punch_in,
                "punch_out": self._song.punch_out,
            }
        except Exception as e:
            self.log_message("Error getting arrangement loop: " + str(e))
            raise

    def _set_arrangement_loop(self, loop_start, loop_length, loop_on):
        """Set the arrangement loop region and on/off state."""
        try:
            if loop_start is not None:
                self._song.loop_start = loop_start
            if loop_length is not None:
                self._song.loop_length = loop_length
            if loop_on is not None:
                self._song.loop = loop_on
            # Live applies boolean property changes asynchronously, so reading
            # self._song.loop back immediately returns the pre-change value.
            # Numeric properties (loop_start, loop_length) read back correctly.
            # Return the requested boolean rather than the stale read-back.
            return {
                "loop": loop_on if loop_on is not None else self._song.loop,
                "loop_start": self._song.loop_start,
                "loop_length": self._song.loop_length,
            }
        except Exception as e:
            self.log_message("Error setting arrangement loop: " + str(e))
            raise

    def _set_punch_points(self, punch_in, punch_out):
        """Set punch in/out state."""
        try:
            if punch_in is not None:
                self._song.punch_in = punch_in
            if punch_out is not None:
                self._song.punch_out = punch_out
            # Same async read-back issue as _set_arrangement_loop — return
            # the requested values for any arg that was explicitly set.
            return {
                "punch_in": punch_in if punch_in is not None else self._song.punch_in,
                "punch_out": punch_out if punch_out is not None else self._song.punch_out,
            }
        except Exception as e:
            self.log_message("Error setting punch points: " + str(e))
            raise

    def _jump_to_cue(self, direction):
        """Jump to next or previous cue point."""
        try:
            if direction == "next":
                self._song.jump_to_next_cue()
            else:
                self._song.jump_to_prev_cue()
            # jump_to_next/prev_cue() is fire-and-forget; current_song_time
            # read immediately after still reflects the pre-jump position.
            return {"direction": direction}
        except Exception as e:
            self.log_message("Error jumping to cue: " + str(e))
            raise

    def _set_clip_loop(self, track_index, clip_index, loop_start, loop_end, loop_on):
        """Set loop start, end, and on/off for a clip."""
        try:
            clip = self._get_clip(track_index, clip_index)
            clip.loop_start = loop_start
            clip.loop_end = loop_end
            clip.looping = loop_on
            return {
                "loop_start": clip.loop_start,
                "loop_end": clip.loop_end,
                "looping": clip.looping,
            }
        except Exception as e:
            self.log_message("Error setting clip loop: " + str(e))
            raise

    def _set_clip_color(self, track_index, clip_index, color):
        """Set the color of a clip (integer RGB)."""
        try:
            clip = self._get_clip(track_index, clip_index)
            clip.color = color
            return {"color": clip.color}
        except Exception as e:
            self.log_message("Error setting clip color: " + str(e))
            raise

    def _duplicate_clip(self, track_index, clip_index, target_clip_index):
        """Duplicate a clip into another slot on the same track."""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            track = self._song.tracks[track_index]
            if clip_index < 0 or clip_index >= len(track.clip_slots):
                raise IndexError("Source clip index out of range")
            if target_clip_index < 0 or target_clip_index >= len(track.clip_slots):
                raise IndexError("Target clip index out of range")
            src_slot = track.clip_slots[clip_index]
            if not src_slot.has_clip:
                raise Exception("No clip in source slot")
            dst_slot = track.clip_slots[target_clip_index]
            if dst_slot.has_clip:
                raise Exception("Target slot already has a clip")
            src_slot.duplicate_clip_to(dst_slot)
            return {
                "source_clip_index": clip_index,
                "target_clip_index": target_clip_index,
                "clip_name": dst_slot.clip.name if dst_slot.has_clip else "",
            }
        except Exception as e:
            self.log_message("Error duplicating clip: " + str(e))
            raise

    def _quantize_clip(self, track_index, clip_index, quantize_to, amount):
        """Quantize notes in a MIDI clip. quantize_to is note division (1=quarter, 0.5=8th, 0.25=16th, 0.125=32nd). amount 0–1."""
        # Ableton's Clip.quantize() takes a RecordingQuantization integer enum, not a beat division float.
        QUANTIZE_MAP = {1.0: 1, 0.5: 2, 0.25: 5, 0.125: 8}
        quantize_enum = QUANTIZE_MAP.get(float(quantize_to))
        if quantize_enum is None:
            raise Exception("Invalid quantize_to value: {}. Use 1.0, 0.5, 0.25, or 0.125".format(quantize_to))
        try:
            clip = self._get_clip(track_index, clip_index)
            if not clip.is_midi_clip:
                raise Exception("Clip is not a MIDI clip")
            clip.quantize(quantize_enum, amount)
            return {
                "track_index": track_index,
                "clip_index": clip_index,
                "quantize_to": quantize_to,
                "amount": amount,
            }
        except Exception as e:
            self.log_message("Error quantizing clip: " + str(e))
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
            root_category = path_parts[0].lower().replace(" ", "_")
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

    # Warp mode integer constants (Live.Clip.WarpMode enum)
    WARP_MODES = {
        0: "Beats",
        1: "Tones",
        2: "Texture",
        3: "Re-Pitch",
        4: "Complex",
        6: "Complex Pro",
    }
    WARP_MODE_NAMES = {v: k for k, v in WARP_MODES.items()}

    def _get_audio_clip_info(self, track_index, clip_index):
        """Read audio-specific properties of an audio clip."""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            track = self._song.tracks[track_index]
            if clip_index < 0 or clip_index >= len(track.clip_slots):
                raise IndexError("Clip index out of range")
            slot = track.clip_slots[clip_index]
            if not slot.has_clip:
                raise Exception("No clip in slot")
            clip = slot.clip
            if not clip.is_audio_clip:
                raise Exception("Clip is not an audio clip")
            sample_name = ""
            try:
                if hasattr(clip, 'sample') and clip.sample is not None:
                    sample_name = clip.sample.file_path if hasattr(clip.sample, 'file_path') else ""
            except Exception:
                pass
            warp_mode_int = int(clip.warp_mode) if hasattr(clip, 'warp_mode') else 0
            return {
                "track_index": track_index,
                "clip_index": clip_index,
                "name": clip.name,
                "sample_name": sample_name,
                "gain": clip.gain if hasattr(clip, 'gain') else None,
                "gain_display_string": clip.gain_display_string if hasattr(clip, 'gain_display_string') else "",
                "warping": clip.warping if hasattr(clip, 'warping') else None,
                "warp_mode": warp_mode_int,
                "warp_mode_name": self.WARP_MODES.get(warp_mode_int, "Unknown"),
                "pitch_coarse": clip.pitch_coarse if hasattr(clip, 'pitch_coarse') else 0,
                "pitch_fine": clip.pitch_fine if hasattr(clip, 'pitch_fine') else 0.0,
            }
        except Exception as e:
            self.log_message("Error getting audio clip info: " + str(e))
            raise

    def _set_audio_clip_gain(self, track_index, clip_index, gain):
        """Set the gain of an audio clip (0.0 to 1.0 linear)."""
        try:
            if gain is None:
                raise ValueError("gain is required")
            gain = float(gain)
            if gain < 0.0 or gain > 1.0:
                raise ValueError("gain must be between 0.0 and 1.0")
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            track = self._song.tracks[track_index]
            if clip_index < 0 or clip_index >= len(track.clip_slots):
                raise IndexError("Clip index out of range")
            slot = track.clip_slots[clip_index]
            if not slot.has_clip:
                raise Exception("No clip in slot")
            clip = slot.clip
            if not clip.is_audio_clip:
                raise Exception("Clip is not an audio clip")
            clip.gain = gain
            return "Gain set to {0} on clip {1}/{2}".format(gain, track_index, clip_index)
        except Exception as e:
            self.log_message("Error setting audio clip gain: " + str(e))
            raise

    def _set_audio_clip_pitch(self, track_index, clip_index, pitch_coarse, pitch_fine):
        """Set pitch_coarse (semitones, -48..48) and/or pitch_fine (cents, -50..50)."""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            track = self._song.tracks[track_index]
            if clip_index < 0 or clip_index >= len(track.clip_slots):
                raise IndexError("Clip index out of range")
            slot = track.clip_slots[clip_index]
            if not slot.has_clip:
                raise Exception("No clip in slot")
            clip = slot.clip
            if not clip.is_audio_clip:
                raise Exception("Clip is not an audio clip")
            if pitch_coarse is not None:
                coarse = int(pitch_coarse)
                if coarse < -48 or coarse > 48:
                    raise ValueError("pitch_coarse must be between -48 and 48")
                clip.pitch_coarse = coarse
            if pitch_fine is not None:
                fine = float(pitch_fine)
                if fine < -50.0 or fine > 50.0:
                    raise ValueError("pitch_fine must be between -50.0 and 50.0")
                clip.pitch_fine = fine
            return "Pitch set on clip {0}/{1}".format(track_index, clip_index)
        except Exception as e:
            self.log_message("Error setting audio clip pitch: " + str(e))
            raise

    def _set_audio_clip_warp(self, track_index, clip_index, warping, warp_mode):
        """Set warping on/off and/or warp mode on an audio clip."""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            track = self._song.tracks[track_index]
            if clip_index < 0 or clip_index >= len(track.clip_slots):
                raise IndexError("Clip index out of range")
            slot = track.clip_slots[clip_index]
            if not slot.has_clip:
                raise Exception("No clip in slot")
            clip = slot.clip
            if not clip.is_audio_clip:
                raise Exception("Clip is not an audio clip")
            if warping is not None:
                clip.warping = bool(warping)
            if warp_mode is not None:
                if isinstance(warp_mode, str):
                    mode_int = self.WARP_MODE_NAMES.get(warp_mode)
                    if mode_int is None:
                        raise ValueError("Unknown warp mode: {0}. Valid: {1}".format(
                            warp_mode, list(self.WARP_MODE_NAMES.keys())))
                else:
                    mode_int = int(warp_mode)
                    if mode_int not in self.WARP_MODES:
                        raise ValueError("Unknown warp mode int: {0}. Valid: {1}".format(
                            mode_int, list(self.WARP_MODES.keys())))
                clip.warp_mode = mode_int
            return "Warp settings updated on clip {0}/{1}".format(track_index, clip_index)
        except Exception as e:
            self.log_message("Error setting audio clip warp: " + str(e))
            raise
