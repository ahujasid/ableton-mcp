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


class _RemoteScriptError(Exception):
    """Structured, fail-closed error raised by the production-control owner."""

    def __init__(self, code, message, details=None):
        Exception.__init__(self, message)
        self.code = code
        self.details = details or {}

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
                response["result"] = self._get_track_info(
                    track_index,
                    params.get("expected_track_name"),
                    params.get("track_type", params.get("track_kind", "normal"))
                )
            elif command_type == "get_capabilities":
                response["result"] = self._get_capabilities()
            elif command_type == "get_mixer_parameters":
                response["result"] = self._get_mixer_parameters(params)
            elif command_type == "get_device_parameters":
                response["result"] = self._get_device_parameters(params)
            elif command_type == "get_clip_notes":
                response["result"] = self._get_clip_notes(params)
            elif command_type == "get_clip_properties":
                response["result"] = self._get_clip_properties(params)
            elif command_type == "get_output_meter_levels":
                response["result"] = self._get_output_meter_levels(params)
            # Commands that modify Live's state should be scheduled on the main thread
            elif command_type in ["create_midi_track", "set_track_name",
                                 "create_clip", "create_audio_clip", "add_notes_to_clip", "set_clip_name",
                                 "set_tempo", "fire_clip", "stop_clip",
                                 "start_playback", "stop_playback", "load_browser_item",
                                 # Arrangement view – must run on the main thread
                                 "switch_to_arrangement_view", "set_current_song_time",
                                 "duplicate_session_clip_to_arrangement",
                                 # Production-control MVP mutations
                                 "set_mixer_parameter", "set_mixer_parameters",
                                 "set_device_parameter", "set_device_parameters",
                                 "replace_clip_notes", "clear_clip_notes", "set_clip_loop",
                                 "delete_session_clip", "duplicate_session_clip",
                                 "duplicate_session_scene_clips", "fire_scene",
                                 "stop_all_clips", "back_to_arrangement",
                                 "delete_arrangement_clip"]:
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
                                params
                            )
                        elif command_type == "set_mixer_parameter":
                            result = self._set_mixer_parameter(params)
                        elif command_type == "set_mixer_parameters":
                            result = self._set_mixer_parameters(params)
                        elif command_type == "set_device_parameter":
                            result = self._set_device_parameter(params)
                        elif command_type == "set_device_parameters":
                            result = self._set_device_parameters(params)
                        elif command_type == "replace_clip_notes":
                            result = self._replace_clip_notes(params)
                        elif command_type == "clear_clip_notes":
                            result = self._clear_clip_notes(params)
                        elif command_type == "set_clip_loop":
                            result = self._set_clip_loop(params)
                        elif command_type == "delete_session_clip":
                            result = self._delete_session_clip(params)
                        elif command_type == "duplicate_session_clip":
                            result = self._duplicate_session_clip(params)
                        elif command_type == "duplicate_session_scene_clips":
                            result = self._duplicate_session_scene_clips(params)
                        elif command_type == "fire_scene":
                            result = self._fire_scene(params)
                        elif command_type == "stop_all_clips":
                            result = self._stop_all_clips(params)
                        elif command_type == "back_to_arrangement":
                            result = self._back_to_arrangement(params)
                        elif command_type == "delete_arrangement_clip":
                            result = self._delete_arrangement_clip(params)

                        # Put the result in the queue
                        response_queue.put({"status": "success", "result": result})
                    except Exception as e:
                        self.log_message("Error in main thread task: " + str(e))
                        self.log_message(traceback.format_exc())
                        task_error = {"status": "error", "message": str(e)}
                        if hasattr(e, "code"):
                            task_error["error"] = {
                                "code": e.code,
                                "details": getattr(e, "details", {})
                            }
                        response_queue.put(task_error)
                
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
                        if task_response.get("error"):
                            response["error"] = task_response["error"]
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
            # Read-only arrangement command – no main-thread scheduling required
            elif command_type == "get_arrangement_clips":
                track_index = params.get("track_index", 0)
                response["result"] = self._get_arrangement_clips(
                    track_index,
                    params.get("expected_track_name"),
                    params.get("track_type", params.get("track_kind", "normal"))
                )
            else:
                response["status"] = "error"
                response["message"] = "Unknown command: " + command_type
        except Exception as e:
            self.log_message("Error processing command: " + str(e))
            self.log_message(traceback.format_exc())
            response["status"] = "error"
            response["message"] = str(e)
            if hasattr(e, "code"):
                response["error"] = {
                    "code": e.code,
                    "details": getattr(e, "details", {})
                }
        
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
    
    def _get_track_info(self, track_index, expected_track_name=None, track_type="normal"):
        """Get information about a track"""
        try:
            track, resolved_target = self._resolve_track(
                track_index, expected_track_name, track_type
            )
            
            # Get clip slots
            clip_slots = []
            for slot_index, slot in enumerate(getattr(track, "clip_slots", ())):
                clip_info = None
                if slot.has_clip:
                    clip = slot.clip
                    clip_info = {
                        "name": self._safe_getattr(clip, "name", None),
                        "length": self._safe_getattr(clip, "length", None),
                        "is_playing": self._safe_getattr(clip, "is_playing", False),
                        "is_recording": self._safe_getattr(clip, "is_recording", False)
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
                    "name": self._safe_getattr(device, "name", None),
                    "class_name": self._safe_getattr(device, "class_name", None),
                    "type": self._get_device_type(device)
                })
            
            result = {
                "index": resolved_target["track_index"],
                "name": track.name,
                "track_type": resolved_target["track_type"],
                "is_audio_track": self._safe_getattr(track, "has_audio_input", False),
                "is_midi_track": self._safe_getattr(track, "has_midi_input", False),
                "mute": self._safe_getattr(track, "mute", None),
                "solo": self._safe_getattr(track, "solo", None),
                "arm": self._safe_getattr(track, "arm", None),
                "volume": self._safe_getattr(
                    self._safe_getattr(self._safe_getattr(track, "mixer_device", None), "volume", None),
                    "value", None
                ),
                "panning": self._safe_getattr(
                    self._safe_getattr(self._safe_getattr(track, "mixer_device", None), "panning", None),
                    "value", None
                ),
                "clip_slots": clip_slots,
                "devices": devices
            }
            return result
        except Exception as e:
            self.log_message("Error getting track info: " + str(e))
            raise
    
    # ------------------------------------------------------------------
    # Production-control MVP: safe resolution and value helpers
    # ------------------------------------------------------------------

    def _copy_params(self, params):
        """Return a shallow dict copy without requiring modern Python syntax."""
        if params is None:
            return {}
        if not isinstance(params, dict):
            raise _RemoteScriptError("invalid_params", "params must be an object")
        return dict(params)

    def _safe_getattr(self, obj, name, default=None):
        try:
            return getattr(obj, name)
        except Exception:
            return default

    def _safe_hasattr(self, obj, name):
        try:
            getattr(obj, name)
            return True
        except Exception:
            return False

    def _safe_callable(self, obj, name):
        value = self._safe_getattr(obj, name, None)
        return callable(value)

    def _coerce_index(self, value, label):
        if isinstance(value, bool):
            raise _RemoteScriptError("invalid_index", "%s must be an integer" % label)
        try:
            index = int(value)
        except (TypeError, ValueError):
            raise _RemoteScriptError("invalid_index", "%s must be an integer" % label)
        try:
            if index != value:
                raise _RemoteScriptError("invalid_index", "%s must be an integer" % label)
        except TypeError:
            raise _RemoteScriptError("invalid_index", "%s must be an integer" % label)
        return index

    def _normalise_track_type(self, track_type):
        value = (track_type or "normal").lower()
        aliases = {
            "track": "normal",
            "tracks": "normal",
            "regular": "normal",
            "return_track": "return",
            "returns": "return",
            "master": "main",
            "main_track": "main",
        }
        return aliases.get(value, value)

    def _resolve_track(self, track_index=0, expected_track_name=None, track_type="normal"):
        """Resolve a normal, return, or main track and verify its identity."""
        if isinstance(track_index, dict):
            params = track_index
            track_index = params.get("track_index", 0)
            expected_track_name = params.get("expected_track_name", expected_track_name)
            track_type = params.get(
                "track_type", params.get("track_scope", params.get("track_kind", track_type))
            )

        kind = self._normalise_track_type(track_type)
        if kind == "normal":
            collection = self._safe_getattr(self._song, "tracks", ()) or ()
        elif kind == "return":
            collection = self._safe_getattr(self._song, "return_tracks", ()) or ()
        elif kind == "main":
            master = self._safe_getattr(self._song, "master_track", None)
            if master is None:
                raise _RemoteScriptError("unsupported_target", "Main track is unavailable")
            collection = (master,)
        else:
            raise _RemoteScriptError("invalid_track_type", "Unknown track_type: %s" % kind)

        index = self._coerce_index(track_index, "track_index")
        if index < 0 or index >= len(collection):
            raise _RemoteScriptError("track_not_found", "Track index out of range")
        track = collection[index]
        actual_name = self._safe_getattr(track, "name", None)
        if expected_track_name is not None and actual_name != expected_track_name:
            raise _RemoteScriptError(
                "track_identity_mismatch",
                "Track identity mismatch at index %d" % index,
                {"expected_track_name": expected_track_name, "actual_track_name": actual_name}
            )
        target = {
            "track_type": kind,
            "track_kind": kind,
            "track_index": index,
            "name": actual_name,
        }
        return track, target

    def _resolve_session_clip(self, params=None, track_index=0, clip_index=0,
                              expected_clip_name=None, expected_track_name=None,
                              track_type="normal", require_expected_name=False):
        """Resolve one Session clip with an optional strict name guard."""
        if isinstance(params, dict):
            values = params
            track_index = values.get("track_index", track_index)
            clip_index = values.get("clip_index", clip_index)
            expected_clip_name = values.get(
                "expected_clip_name", values.get("expected_name", expected_clip_name)
            )
            expected_track_name = values.get("expected_track_name", expected_track_name)
            track_type = values.get(
                "track_type", values.get("track_scope", values.get("track_kind", track_type))
            )

        if require_expected_name and not expected_clip_name:
            raise _RemoteScriptError(
                "expected_clip_name_required",
                "expected_clip_name is required for this mutation"
            )

        track, track_target = self._resolve_track(
            track_index, expected_track_name, track_type
        )
        index = self._coerce_index(clip_index, "clip_index")
        slots = getattr(track, "clip_slots", ())
        if index < 0 or index >= len(slots):
            raise _RemoteScriptError("clip_not_found", "Clip slot index out of range")
        slot = slots[index]
        if not bool(self._safe_getattr(slot, "has_clip", False)):
            raise _RemoteScriptError("clip_not_found", "No clip in session slot %d" % index)
        clip = self._safe_getattr(slot, "clip", None)
        if clip is None:
            raise _RemoteScriptError("clip_not_found", "Session slot has no readable clip")
        actual_name = self._safe_getattr(clip, "name", None)
        if expected_clip_name is not None and actual_name != expected_clip_name:
            raise _RemoteScriptError(
                "clip_identity_mismatch",
                "Clip identity mismatch at slot %d" % index,
                {"expected_clip_name": expected_clip_name, "actual_clip_name": actual_name}
            )
        target = dict(track_target)
        target.update({
            "clip_index": index,
            "clip_name": actual_name,
            "length": self._safe_getattr(clip, "length", None),
        })
        return track, slot, clip, target

    def _selector_parts(self, selector, kind):
        """Extract index/name/class guards from a device or chain path item."""
        if isinstance(selector, dict):
            index = selector.get("index")
            if kind == "device":
                index = selector.get("device_index", index)
            elif kind == "chain":
                index = selector.get("chain_index", index)
            expected_name = selector.get("expected_name")
            if kind == "device":
                expected_name = selector.get(
                    "expected_device_name", selector.get("name", expected_name)
                )
            else:
                expected_name = selector.get(
                    "expected_chain_name", selector.get("name", expected_name)
                )
            expected_class = selector.get("expected_class_name")
            if kind == "device":
                expected_class = selector.get(
                    "expected_device_class_name", selector.get("class_name", expected_class)
                )
            else:
                expected_class = selector.get(
                    "expected_chain_class_name", selector.get("class_name", expected_class)
                )
            explicit_kind = selector.get("type", selector.get("kind"))
            if explicit_kind:
                explicit_kind = str(explicit_kind).lower()
                if explicit_kind in ("rack_chain", "chain"):
                    kind = "chain"
                elif explicit_kind in ("device", "plugin"):
                    kind = "device"
            return index, expected_name, expected_class, kind
        if isinstance(selector, (bytes, str)):
            return None, selector, None, kind
        return selector, None, None, kind

    def _select_path_item(self, collection, selector, kind, expected_name=None,
                          expected_class=None):
        index, local_name, local_class, effective_kind = self._selector_parts(selector, kind)
        if effective_kind != kind:
            kind = effective_kind
        expected_name = local_name if local_name is not None else expected_name
        expected_class = local_class if local_class is not None else expected_class
        if index is not None:
            index = self._coerce_index(index, "%s_index" % kind)
            if index < 0 or index >= len(collection):
                raise _RemoteScriptError(
                    "%s_not_found" % kind, "%s index out of range" % kind
                )
            item = collection[index]
        elif expected_name is not None:
            matches = []
            for candidate_index, candidate in enumerate(collection):
                if self._safe_getattr(candidate, "name", None) == expected_name:
                    matches.append((candidate_index, candidate))
            if len(matches) != 1:
                raise _RemoteScriptError(
                    "%s_identity_ambiguous" % kind,
                    "Expected exactly one %s named %s" % (kind, expected_name),
                    {"match_count": len(matches)}
                )
            index, item = matches[0]
        else:
            raise _RemoteScriptError(
                "%s_selector_required" % kind,
                "%s path item needs an index or expected name" % kind
            )

        actual_name = self._safe_getattr(item, "name", None)
        actual_class = self._safe_getattr(item, "class_name", None)
        if expected_name is not None and actual_name != expected_name:
            raise _RemoteScriptError(
                "%s_identity_mismatch" % kind,
                "%s name mismatch" % kind,
                {"expected_name": expected_name, "actual_name": actual_name}
            )
        if expected_class is not None and actual_class != expected_class:
            raise _RemoteScriptError(
                "%s_class_mismatch" % kind,
                "%s class_name mismatch" % kind,
                {"expected_class_name": expected_class, "actual_class_name": actual_class}
            )
        return item, {
            "kind": kind,
            "index": index,
            "name": actual_name,
            "class_name": actual_class,
        }

    def _as_path_list(self, device_path):
        if device_path is None:
            return []
        if isinstance(device_path, (list, tuple)):
            return list(device_path)
        return [device_path]

    def _as_expected_list(self, value):
        if value is None:
            return []
        if isinstance(value, (list, tuple)):
            return list(value)
        return [value]

    def _resolve_device_path(self, params=None, track=None, device_path=None,
                             expected_device_names=None, expected_device_class_names=None,
                             expected_chain_names=None, expected_chain_class_names=None):
        """Resolve a nested device path, checking every named/classed hop."""
        if isinstance(params, dict):
            values = params
            if track is None:
                track, _ = self._resolve_track(values)
            device_path = values.get("device_path", values.get("path", device_path))
            if device_path is None and values.get("device_index") is not None:
                device_path = [values.get("device_index")]
            expected_device_names = values.get(
                "expected_device_names", expected_device_names
            )
            if expected_device_names is None and values.get("expected_device_name") is not None:
                expected_device_names = [values.get("expected_device_name")]
            expected_device_class_names = values.get(
                "expected_device_class_names", expected_device_class_names
            )
            if expected_device_class_names is None and values.get("expected_device_class_name") is not None:
                expected_device_class_names = [values.get("expected_device_class_name")]
            expected_chain_names = values.get("expected_chain_names", expected_chain_names)
            if expected_chain_names is None and values.get("expected_chain_name") is not None:
                expected_chain_names = [values.get("expected_chain_name")]
            expected_chain_class_names = values.get(
                "expected_chain_class_names", expected_chain_class_names
            )
            if expected_chain_class_names is None and values.get("expected_chain_class_name") is not None:
                expected_chain_class_names = [values.get("expected_chain_class_name")]
        if track is None:
            raise _RemoteScriptError("track_required", "A track is required for device resolution")

        path = self._as_path_list(device_path)
        if not path:
            raise _RemoteScriptError("device_path_required", "device_path is required")
        device_names = self._as_expected_list(expected_device_names)
        device_classes = self._as_expected_list(expected_device_class_names)
        chain_names = self._as_expected_list(expected_chain_names)
        chain_classes = self._as_expected_list(expected_chain_class_names)

        collection = self._safe_getattr(track, "devices", ()) or ()
        kind = "device"
        resolved_path = []
        device_position = 0
        chain_position = 0
        current_device = None
        current_chain = None

        for path_position, selector in enumerate(path):
            # A dict can explicitly identify a chain. Otherwise a rack with
            # chains makes the next numeric hop a chain by default.
            requested_kind = kind
            if isinstance(selector, dict):
                explicit_kind = selector.get("type", selector.get("kind"))
                if explicit_kind:
                    explicit_kind = str(explicit_kind).lower()
                    if explicit_kind in ("chain", "rack_chain"):
                        requested_kind = "chain"
                    elif explicit_kind in ("device", "plugin"):
                        requested_kind = "device"
                elif selector.get("chain_index") is not None or \
                        selector.get("expected_chain_name") is not None or \
                        selector.get("expected_chain_class_name") is not None:
                    requested_kind = "chain"

            if requested_kind == "device":
                if collection is None:
                    raise _RemoteScriptError("device_not_found", "Device collection is unavailable")
                expected_name = device_names[device_position] if device_position < len(device_names) else None
                expected_class = device_classes[device_position] if device_position < len(device_classes) else None
                current_device, item_target = self._select_path_item(
                    collection, selector, "device", expected_name, expected_class
                )
                device_position += 1
                resolved_path.append(item_target)
                if path_position + 1 < len(path):
                    chains = self._safe_getattr(current_device, "chains", None)
                    if chains is not None and len(chains) > 0:
                        collection = chains
                        kind = "chain"
                    else:
                        nested_devices = self._safe_getattr(current_device, "devices", None)
                        if nested_devices is not None:
                            collection = nested_devices
                            kind = "device"
                        elif chains is not None:
                            # Preserve a useful chain_not_found error for an
                            # empty rack instead of guessing another owner.
                            collection = chains
                            kind = "chain"
                        else:
                            raise _RemoteScriptError(
                                "device_path_invalid", "Device has no nested chains/devices"
                            )
            else:
                if collection is None:
                    raise _RemoteScriptError("chain_not_found", "Chain collection is unavailable")
                expected_name = chain_names[chain_position] if chain_position < len(chain_names) else None
                expected_class = chain_classes[chain_position] if chain_position < len(chain_classes) else None
                current_chain, item_target = self._select_path_item(
                    collection, selector, "chain", expected_name, expected_class
                )
                chain_position += 1
                resolved_path.append(item_target)
                if path_position + 1 < len(path):
                    nested_devices = self._safe_getattr(current_chain, "devices", None)
                    if nested_devices is None:
                        raise _RemoteScriptError("device_path_invalid", "Chain has no devices")
                    collection = nested_devices
                    kind = "device"

        if current_device is None:
            raise _RemoteScriptError("device_path_invalid", "device_path must end at a device")
        return current_device, resolved_path

    def _parameter_state(self, parameter, index=None):
        value = self._safe_getattr(parameter, "value", None)
        minimum = self._safe_getattr(parameter, "min", None)
        maximum = self._safe_getattr(parameter, "max", None)
        is_quantized = self._safe_getattr(parameter, "is_quantized", None)
        value_items = self._safe_getattr(parameter, "value_items", None)
        if value_items is not None and not isinstance(value_items, (list, tuple)):
            try:
                value_items = list(value_items)
            except (TypeError, ValueError):
                value_items = [value_items]
        elif isinstance(value_items, tuple):
            value_items = list(value_items)
        display_value = self._safe_getattr(parameter, "display_value", None)
        if display_value is None:
            formatter = self._safe_getattr(parameter, "str_for_value", None)
            if callable(formatter):
                try:
                    display_value = formatter(value)
                except Exception:
                    display_value = value
        if display_value is None:
            display_value = value
        state = {
            "value": value,
            "min": minimum,
            "max": maximum,
            "display_value": display_value,
            "is_quantized": is_quantized,
            "value_items": value_items,
            "name": self._safe_getattr(parameter, "name", None),
        }
        if index is not None:
            state["index"] = index
        return state

    def _property_state(self, owner, attr, name=None):
        value = self._safe_getattr(owner, attr, None)
        return {
            "value": value,
            "min": None,
            "max": None,
            "display_value": value,
            "is_quantized": True,
            "value_items": [False, True] if isinstance(value, bool) else None,
            "name": name or attr,
        }

    def _state_value_equal(self, left, right, tolerance=0.0):
        if isinstance(left, bool) or isinstance(right, bool):
            return left == right
        try:
            left_float = float(left)
            right_float = float(right)
            return abs(left_float - right_float) <= float(tolerance or 0.0)
        except (TypeError, ValueError):
            return left == right

    def _check_expected_current(self, state, params):
        if "expected_current_value" not in params:
            if not params.get("dry_run", False) and not params.get("overwrite", False):
                raise _RemoteScriptError(
                    "expected_current_value_required",
                    "expected_current_value is required unless overwrite=true"
                )
            return
        expected = params.get("expected_current_value")
        tolerance = params.get("tolerance", 0.0)
        if not self._state_value_equal(state.get("value"), expected, tolerance):
            raise _RemoteScriptError(
                "current_value_mismatch",
                "Current value does not match expected_current_value",
                {"expected_current_value": expected, "actual_current_value": state.get("value"),
                 "tolerance": tolerance}
            )

    def _validate_requested_value(self, state, value):
        minimum = state.get("min")
        maximum = state.get("max")
        try:
            if minimum is not None and float(value) < float(minimum):
                raise _RemoteScriptError("value_out_of_range", "Requested value is below min")
            if maximum is not None and float(value) > float(maximum):
                raise _RemoteScriptError("value_out_of_range", "Requested value is above max")
        except (TypeError, ValueError):
            # Boolean and enumerated parameters do not necessarily have
            # numeric values; Live remains the final type validator.
            pass
        value_items = state.get("value_items")
        if value_items and state.get("is_quantized"):
            if value not in value_items:
                # Some LOM stubs expose labels while the value is numeric.
                # Reject only when neither representation matches.
                matched = False
                for item in value_items:
                    if str(item) == str(value):
                        matched = True
                        break
                if not matched:
                    try:
                        numeric_value = float(value)
                        if minimum is not None and maximum is not None:
                            matched = float(minimum) <= numeric_value <= float(maximum)
                        elif int(numeric_value) == numeric_value:
                            matched = 0 <= int(numeric_value) < len(value_items)
                    except (TypeError, ValueError):
                        matched = False
                if not matched:
                    raise _RemoteScriptError(
                        "invalid_quantized_value",
                        "Requested value is not in value_items",
                        {"value": value, "value_items": value_items}
                    )

    def _mutation_result(self, target, before, requested, after, state=None):
        state = state or {}
        return {
            "target": target,
            "before": before,
            "requested": requested,
            "applied": after,
            "after": after,
            "min": state.get("min"),
            "max": state.get("max"),
            "display_value": state.get("display_value", after),
            "is_quantized": state.get("is_quantized"),
            "value_items": state.get("value_items"),
        }

    def _set_entry_value(self, entry, value):
        if entry["kind"] == "parameter":
            entry["parameter"].value = value
        else:
            setattr(entry["owner"], entry["attr"], value)

    def _read_entry_state(self, entry):
        if entry["kind"] == "parameter":
            return self._parameter_state(entry["parameter"], entry.get("parameter_index"))
        return self._property_state(entry["owner"], entry["attr"], entry.get("name"))

    def _resolve_mixer_entry(self, params):
        values = self._copy_params(params)
        track, track_target = self._resolve_track(values)
        parameter_name = values.get(
            "parameter", values.get("parameter_name", values.get("mixer_parameter"))
        )
        if parameter_name is None:
            raise _RemoteScriptError("parameter_required", "Mixer parameter is required")
        normalized = str(parameter_name).lower()
        normalized = {"pan": "panning", "send": "sends"}.get(normalized, normalized)
        target = dict(track_target)
        target["parameter"] = normalized
        mixer = self._safe_getattr(track, "mixer_device", None)
        if normalized in ("volume", "panning"):
            parameter = self._safe_getattr(mixer, normalized, None)
            if parameter is None:
                raise _RemoteScriptError("unsupported_parameter", "Mixer parameter is unavailable")
            expected_name = values.get("expected_parameter_name")
            actual_name = self._safe_getattr(parameter, "name", None)
            if expected_name is not None and actual_name != expected_name:
                raise _RemoteScriptError(
                    "parameter_identity_mismatch", "Mixer parameter name mismatch",
                    {"expected_parameter_name": expected_name, "actual_parameter_name": actual_name}
                )
            target.update({"parameter_index": None, "parameter_name": actual_name or normalized})
            return {"kind": "parameter", "parameter": parameter, "target": target,
                    "parameter_index": None}
        if normalized == "sends":
            sends = self._safe_getattr(mixer, "sends", None)
            send_index = values.get("send_index", values.get("parameter_index"))
            if sends is None or send_index is None:
                raise _RemoteScriptError("send_index_required", "send_index is required for sends")
            send_index = self._coerce_index(send_index, "send_index")
            if send_index < 0 or send_index >= len(sends):
                raise _RemoteScriptError("parameter_not_found", "Send index out of range")
            parameter = sends[send_index]
            expected_name = values.get("expected_parameter_name")
            actual_name = self._safe_getattr(parameter, "name", None)
            if expected_name is not None and actual_name != expected_name:
                raise _RemoteScriptError(
                    "parameter_identity_mismatch", "Send parameter name mismatch",
                    {"expected_parameter_name": expected_name, "actual_parameter_name": actual_name}
                )
            target.update({"parameter_index": send_index, "parameter_name": actual_name or "send"})
            return {"kind": "parameter", "parameter": parameter, "target": target,
                    "parameter_index": send_index}
        if normalized in ("mute", "solo", "arm"):
            if not self._safe_hasattr(track, normalized):
                raise _RemoteScriptError("unsupported_parameter", "Track property is unavailable")
            expected_name = values.get("expected_parameter_name")
            if expected_name is not None and expected_name != normalized:
                raise _RemoteScriptError(
                    "parameter_identity_mismatch", "Track property name mismatch",
                    {"expected_parameter_name": expected_name, "actual_parameter_name": normalized}
                )
            target.update({"parameter_index": None, "parameter_name": normalized})
            return {"kind": "property", "owner": track, "attr": normalized,
                    "name": normalized, "target": target, "parameter_index": None}
        raise _RemoteScriptError("unsupported_parameter", "Unsupported mixer parameter: %s" % normalized)

    def _resolve_device_entry(self, params):
        values = self._copy_params(params)
        track, track_target = self._resolve_track(values)
        device, path_target = self._resolve_device_path(values, track=track)
        parameter_index = values.get("parameter_index")
        if parameter_index is None:
            raise _RemoteScriptError("parameter_required", "parameter_index is required")
        parameter_index = self._coerce_index(parameter_index, "parameter_index")
        parameters = self._safe_getattr(device, "parameters", None)
        if parameters is None or parameter_index < 0 or parameter_index >= len(parameters):
            raise _RemoteScriptError("parameter_not_found", "Device parameter index out of range")
        parameter = parameters[parameter_index]
        expected_name = values.get("expected_parameter_name")
        actual_name = self._safe_getattr(parameter, "name", None)
        if expected_name is not None and actual_name != expected_name:
            raise _RemoteScriptError(
                "parameter_identity_mismatch", "Device parameter name mismatch",
                {"expected_parameter_name": expected_name, "actual_parameter_name": actual_name}
            )
        target = dict(track_target)
        target.update({
            "device_path": path_target,
            "device_name": self._safe_getattr(device, "name", None),
            "device_class_name": self._safe_getattr(device, "class_name", None),
            "parameter_index": parameter_index,
            "parameter_name": actual_name,
        })
        return {"kind": "parameter", "parameter": parameter, "target": target,
                "parameter_index": parameter_index, "device": device}

    def _entry_description(self, entry):
        return {
            "target": entry["target"],
            "state": self._read_entry_state(entry),
        }

    def _get_mixer_parameters(self, params=None):
        values = self._copy_params(params)
        specs = values.get("parameters")
        explicit_specs = specs is not None
        if specs is None:
            specs = ["volume", "panning", "mute", "solo", "arm"]
            sends = self._safe_getattr(
                self._safe_getattr(
                    self._resolve_track(values)[0], "mixer_device", None
                ), "sends", ()
            )
            specs.extend([{"parameter": "sends", "send_index": index}
                          for index in range(len(sends))])
        elif isinstance(specs, dict):
            specs = [specs]
        elif not isinstance(specs, (list, tuple)):
            raise _RemoteScriptError("invalid_parameters", "parameters must be a list")
        results = []
        for spec in specs:
            if isinstance(spec, dict):
                expanded_specs = [spec]
            else:
                expanded_specs = [
                    {"parameter": "sends", "send_index": index}
                    for index in range(
                        len(self._safe_getattr(
                            self._safe_getattr(
                                self._resolve_track(values)[0], "mixer_device", None
                            ), "sends", ()
                        ))
                    )
                ] if str(spec).lower() == "sends" else [{"parameter": spec}]
            for expanded_spec in expanded_specs:
                merged = dict(values)
                merged.update(expanded_spec)
                merged.pop("parameters", None)
                try:
                    entry = self._resolve_mixer_entry(merged)
                except _RemoteScriptError as error:
                    skippable = (
                        "unsupported_parameter", "send_index_required", "parameter_not_found"
                    )
                    if explicit_specs or error.code not in skippable:
                        raise
                    continue
                state = self._read_entry_state(entry)
                item = dict(state)
                item["target"] = entry["target"]
                results.append(item)
        return {
            "target": results[0]["target"] if len(results) == 1 else None,
            "parameters": results,
        }

    def _get_device_parameters(self, params=None):
        values = self._copy_params(params)
        track, track_target = self._resolve_track(values)
        device, path_target = self._resolve_device_path(values, track=track)
        requested = values.get("parameter_index")
        if requested is None and values.get("parameters") is None:
            indexes = list(range(len(self._safe_getattr(device, "parameters", ()))))
        elif requested is not None:
            indexes = [requested]
        else:
            indexes = values.get("parameters")
        if not isinstance(indexes, (list, tuple)):
            indexes = [indexes]
        results = []
        for index in indexes:
            merged = dict(values)
            merged["parameter_index"] = index
            entry = self._resolve_device_entry(merged)
            state = self._read_entry_state(entry)
            item = dict(state)
            item["target"] = entry["target"]
            results.append(item)
        return {
            "target": {
                "track": track_target,
                "device_path": path_target,
                "device_name": self._safe_getattr(device, "name", None),
            },
            "parameters": results,
        }

    def _preflight_entries(self, entries, values):
        for entry in entries:
            state = self._read_entry_state(entry)
            spec = entry.get("params", values)
            self._check_expected_current(state, spec)
            if "value" not in spec:
                raise _RemoteScriptError("value_required", "value is required for mutation")
            self._validate_requested_value(state, spec.get("value"))
            entry["before_state"] = state
            entry["requested"] = spec.get("value")

    def _rollback_entries(self, entries):
        rollback_errors = []
        for entry in reversed(entries):
            try:
                self._set_entry_value(entry, entry["before_state"].get("value"))
                restored = self._read_entry_state(entry)
                if not self._state_value_equal(
                        restored.get("value"), entry["before_state"].get("value"), 0.0):
                    rollback_errors.append({
                        "target": entry["target"],
                        "error": "rollback readback mismatch",
                    })
            except Exception as error:
                rollback_errors.append({"target": entry.get("target"), "error": str(error)})
        return rollback_errors

    def _apply_entries(self, entries, dry_run=False):
        if dry_run:
            return {
                "dry_run": True,
                "changes": [
                    self._mutation_result(
                        entry["target"], entry["before_state"].get("value"),
                        entry["requested"], entry["before_state"].get("value"),
                        entry["before_state"]
                    ) for entry in entries
                ],
            }
        attempted = []
        changes = []
        try:
            for entry in entries:
                attempted.append(entry)
                self._set_entry_value(entry, entry["requested"])
                after_state = self._read_entry_state(entry)
                tolerance = entry.get("params", {}).get("tolerance", 0.0)
                if not self._state_value_equal(
                        after_state.get("value"), entry["requested"], tolerance):
                    raise _RemoteScriptError(
                        "readback_mismatch", "Applied value did not read back",
                        {"target": entry["target"], "requested": entry["requested"],
                         "actual": after_state.get("value")}
                    )
                changes.append(self._mutation_result(
                    entry["target"], entry["before_state"].get("value"),
                    entry["requested"], after_state.get("value"), after_state
                ))
        except Exception as error:
            rollback_errors = self._rollback_entries(attempted)
            details = {"rollback_errors": rollback_errors, "changes_before_failure": changes}
            if isinstance(error, _RemoteScriptError):
                details["cause_code"] = error.code
            raise _RemoteScriptError("batch_rolled_back", str(error), details)
        return {"dry_run": False, "changes": changes}

    def _set_mixer_parameter(self, params=None):
        values = self._copy_params(params)
        entry = self._resolve_mixer_entry(values)
        entry["params"] = values
        self._preflight_entries([entry], values)
        result = self._apply_entries([entry], bool(values.get("dry_run", False)))
        if len(result["changes"]) == 1:
            return result["changes"][0]
        return result

    def _set_mixer_parameters(self, params=None):
        values = self._copy_params(params)
        specs = values.get("parameters")
        if not isinstance(specs, (list, tuple)) or not specs:
            raise _RemoteScriptError("invalid_parameters", "parameters must be a non-empty list")
        entries = []
        for spec in specs:
            merged = dict(values)
            if isinstance(spec, dict):
                merged.update(spec)
            else:
                raise _RemoteScriptError("invalid_parameters", "each parameter change must be an object")
            merged.pop("parameters", None)
            entry = self._resolve_mixer_entry(merged)
            entry["params"] = merged
            entries.append(entry)
        self._preflight_entries(entries, values)
        return self._apply_entries(entries, bool(values.get("dry_run", False)))

    def _set_device_parameter(self, params=None):
        values = self._copy_params(params)
        entry = self._resolve_device_entry(values)
        entry["params"] = values
        self._preflight_entries([entry], values)
        result = self._apply_entries([entry], bool(values.get("dry_run", False)))
        return result["changes"][0]

    def _set_device_parameters(self, params=None):
        values = self._copy_params(params)
        specs = values.get("parameters")
        if not isinstance(specs, (list, tuple)) or not specs:
            raise _RemoteScriptError("invalid_parameters", "parameters must be a non-empty list")
        entries = []
        for spec in specs:
            if not isinstance(spec, dict):
                raise _RemoteScriptError("invalid_parameters", "each parameter change must be an object")
            merged = dict(values)
            merged.update(spec)
            merged.pop("parameters", None)
            entry = self._resolve_device_entry(merged)
            entry["params"] = merged
            entries.append(entry)
        self._preflight_entries(entries, values)
        return self._apply_entries(entries, bool(values.get("dry_run", False)))

    # ------------------------------------------------------------------
    # Capability probes
    # ------------------------------------------------------------------

    def _get_capabilities(self):
        app = None
        try:
            app = self.application()
        except Exception:
            app = None
        version = None
        get_version_string = self._safe_getattr(app, "get_version_string", None)
        if callable(get_version_string):
            try:
                version = get_version_string()
            except Exception:
                version = None
        if version is None:
            version = self._safe_getattr(app, "version", None)
        if version is None:
            version = self._safe_getattr(self._song, "version", None)
        tracks = self._safe_getattr(self._song, "tracks", ()) or ()
        returns = self._safe_getattr(self._song, "return_tracks", ()) or ()
        scenes = self._safe_getattr(self._song, "scenes", ()) or ()
        sample_track = tracks[0] if len(tracks) else (returns[0] if len(returns) else None)
        sample_clip = None
        sample_slot = None
        if sample_track is not None:
            for candidate in self._safe_getattr(sample_track, "clip_slots", ()) or ():
                if self._safe_getattr(candidate, "has_clip", False):
                    sample_slot = candidate
                    sample_clip = self._safe_getattr(candidate, "clip", None)
                    break
        sample_device = None
        if sample_track is not None:
            devices = self._safe_getattr(sample_track, "devices", ())
            if devices:
                sample_device = devices[0]
        probes = {
            "song.back_to_arranger": self._safe_hasattr(self._song, "back_to_arranger"),
            "song.stop_all_clips": self._safe_callable(self._song, "stop_all_clips"),
            "song.scenes": self._safe_hasattr(self._song, "scenes"),
            "track.delete_clip": self._safe_callable(sample_track, "delete_clip") if sample_track else False,
            "track.stop_all_clips": self._safe_callable(sample_track, "stop_all_clips") if sample_track else False,
            "track.duplicate_clip_slot": self._safe_callable(sample_track, "duplicate_clip_slot") if sample_track else False,
            "track.duplicate_clip_to_arrangement": self._safe_callable(sample_track, "duplicate_clip_to_arrangement") if sample_track else False,
            "clip_slot.delete_clip": self._safe_callable(sample_slot, "delete_clip") if sample_slot else False,
            "clip_slot.duplicate_clip_to": self._safe_callable(sample_slot, "duplicate_clip_to") if sample_slot else False,
            "clip.get_all_notes_extended": self._safe_callable(sample_clip, "get_all_notes_extended") if sample_clip else False,
            "clip.get_notes_extended": self._safe_callable(sample_clip, "get_notes_extended") if sample_clip else False,
            "clip.add_new_notes": self._safe_callable(sample_clip, "add_new_notes") if sample_clip else False,
            "clip.apply_note_modifications": self._safe_callable(sample_clip, "apply_note_modifications") if sample_clip else False,
            "clip.remove_notes_extended": self._safe_callable(sample_clip, "remove_notes_extended") if sample_clip else False,
            "clip.remove_notes_by_id": self._safe_callable(sample_clip, "remove_notes_by_id") if sample_clip else False,
            "clip.set_notes": self._safe_callable(sample_clip, "set_notes") if sample_clip else False,
            "clip.loop": self._safe_hasattr(sample_clip, "loop") if sample_clip else False,
            "clip_slot.fire": self._safe_callable(sample_slot, "fire") if sample_slot else False,
            "scene.fire": self._safe_callable(scenes[0], "fire") if scenes else False,
            "track.output_meter_left": self._safe_hasattr(sample_track, "output_meter_left") if sample_track else False,
            "track.output_meter_right": self._safe_hasattr(sample_track, "output_meter_right") if sample_track else False,
            "device.parameters": self._safe_hasattr(sample_device, "parameters") if sample_device else False,
            "device.chains": self._safe_hasattr(sample_device, "chains") if sample_device else False,
            "mixer_device": self._safe_hasattr(sample_track, "mixer_device") if sample_track else False,
        }
        return {
            "live_version": version,
            "version": version,
            "operations": probes,
            "capabilities": probes,
        }

    # ------------------------------------------------------------------
    # MIDI notes and clip properties
    # ------------------------------------------------------------------

    def _note_attr(self, note, name, default=None):
        if isinstance(note, dict):
            return note.get(name, default)
        return self._safe_getattr(note, name, default)

    def _note_to_dict(self, note):
        if isinstance(note, (list, tuple)):
            if len(note) < 5:
                raise _RemoteScriptError("invalid_note", "Legacy note needs five fields")
            result = {
                "pitch": note[0],
                "start_time": note[1],
                "duration": note[2],
                "velocity": note[3],
                "mute": note[4],
            }
            optional_names = ("probability", "velocity_deviation", "release_velocity")
            for position, name in enumerate(optional_names, 5):
                if len(note) > position:
                    result[name] = note[position]
            return result
        result = {}
        for name in ("note_id", "pitch", "start_time", "duration", "velocity", "mute",
                     "probability", "velocity_deviation", "release_velocity"):
            value = self._note_attr(note, name, None)
            if value is not None:
                result[name] = value
        required = ("pitch", "start_time", "duration", "velocity", "mute")
        for name in required:
            if name not in result:
                raise _RemoteScriptError("invalid_note", "Extended note is missing %s" % name)
        return result

    def _validate_note(self, note):
        if not isinstance(note, (dict, list, tuple)):
            raise _RemoteScriptError("invalid_note", "Each note must be an object or legacy tuple")
        result = self._note_to_dict(note)
        try:
            pitch = int(result["pitch"])
            start_time = float(result["start_time"])
            duration = float(result["duration"])
            velocity = int(result["velocity"])
        except (KeyError, TypeError, ValueError):
            raise _RemoteScriptError("invalid_note", "Note fields have invalid types")
        if pitch < 0 or pitch > 127:
            raise _RemoteScriptError("invalid_note", "pitch must be between 0 and 127")
        if start_time < 0.0 or duration <= 0.0:
            raise _RemoteScriptError("invalid_note", "start_time/duration must be positive")
        if velocity < 0 or velocity > 127:
            raise _RemoteScriptError("invalid_note", "velocity must be between 0 and 127")
        if not isinstance(result.get("mute"), bool):
            raise _RemoteScriptError("invalid_note", "mute must be boolean")
        result["pitch"] = pitch
        result["start_time"] = start_time
        result["duration"] = duration
        result["velocity"] = velocity
        for name in ("probability", "velocity_deviation", "release_velocity"):
            if name in result:
                try:
                    result[name] = float(result[name]) if name != "release_velocity" else int(result[name])
                except (TypeError, ValueError):
                    raise _RemoteScriptError("invalid_note", "%s has invalid type" % name)
        if "probability" in result and not 0.0 <= result["probability"] <= 1.0:
            raise _RemoteScriptError("invalid_note", "probability must be between 0 and 1")
        if "velocity_deviation" in result and not -127.0 <= result["velocity_deviation"] <= 127.0:
            raise _RemoteScriptError("invalid_note", "velocity_deviation must be between -127 and 127")
        if "release_velocity" in result and not 0 <= result["release_velocity"] <= 127:
            raise _RemoteScriptError("invalid_note", "release_velocity must be between 0 and 127")
        return result

    def _validate_notes(self, notes):
        if notes is None:
            notes = []
        if not isinstance(notes, (list, tuple)):
            raise _RemoteScriptError("invalid_notes", "notes must be a list")
        return [self._validate_note(note) for note in notes]

    def _read_clip_notes(self, clip, from_time=None, from_pitch=0,
                         time_span=None, pitch_span=128):
        explicit_time_span = time_span is not None
        length = self._safe_getattr(clip, "length", None)
        if from_time is None:
            from_time = 0.0
        if time_span is None:
            try:
                time_span = max(float(length), 0.0)
            except (TypeError, ValueError):
                time_span = 1048576.0

        get_all = self._safe_getattr(clip, "get_all_notes_extended", None)
        if callable(get_all) and not explicit_time_span and from_time == 0.0 and \
                from_pitch == 0 and pitch_span == 128:
            try:
                raw = get_all()
                if isinstance(raw, dict):
                    raw = raw.get("notes", [])
                return [self._note_to_dict(note) for note in (raw or [])], "extended_all"
            except (AttributeError, RuntimeError, TypeError, ValueError):
                pass

        get_extended = self._safe_getattr(clip, "get_notes_extended", None)
        if callable(get_extended):
            # Live's documented Python order is from_pitch, pitch_span,
            # from_time, time_span. A small compatibility fallback covers
            # older stubs/Live builds without assuming the newer API exists.
            signatures = [
                (from_pitch, pitch_span, from_time, time_span),
                (from_time, from_pitch, time_span, pitch_span),
            ]
            for signature in signatures:
                try:
                    raw = get_extended(*signature)
                    if isinstance(raw, dict):
                        raw = raw.get("notes", [])
                    return [self._note_to_dict(note) for note in (raw or [])], "extended"
                except TypeError:
                    continue

        get_legacy = self._safe_getattr(clip, "get_notes", None)
        if callable(get_legacy):
            try:
                raw = get_legacy(from_time, from_pitch, time_span, pitch_span)
            except TypeError:
                raw = get_legacy()
            return [self._note_to_dict(note) for note in (raw or [])], "legacy"
        notes_attr = self._safe_getattr(clip, "notes", None)
        if notes_attr is not None:
            return [self._note_to_dict(note) for note in notes_attr], "stub"
        raise _RemoteScriptError("unsupported_operation", "Clip note read API is unavailable")

    def _note_payload(self, note):
        payload = {}
        for name in ("pitch", "start_time", "duration", "velocity", "mute",
                     "probability", "velocity_deviation", "release_velocity"):
            if name in note:
                payload[name] = note[name]
        return payload

    def _legacy_note_tuple(self, note):
        optional = ("probability", "velocity_deviation", "release_velocity")
        if any(name in note for name in optional):
            raise _RemoteScriptError(
                "extended_notes_required",
                "Live note API does not expose reliable extended-note writes"
            )
        return (
            note["pitch"], note["start_time"], note["duration"],
            note["velocity"], note["mute"]
        )

    def _notes_projection(self, notes, expected=None):
        expected = expected or []
        optional = set()
        for note in expected:
            optional.update([name for name in note if name in (
                "probability", "velocity_deviation", "release_velocity"
            )])
        projection = []
        for note in notes:
            values = (
                note.get("pitch"), note.get("start_time"), note.get("duration"),
                note.get("velocity"), note.get("mute")
            )
            optional_values = tuple(note.get(name) for name in sorted(optional))
            projection.append(values + optional_values)
        return sorted(projection, key=lambda value: repr(value))

    def _notes_equal(self, actual, expected, tolerance=0.000001):
        if len(actual) != len(expected):
            return False
        # Compare note identities by a stable base ordering, with float
        # tolerance. This avoids requiring Live to preserve insertion order.
        def key(note):
            return (note.get("pitch"), note.get("start_time"), note.get("duration"),
                    note.get("velocity"), note.get("mute"))
        actual_sorted = sorted(actual, key=key)
        expected_sorted = sorted(expected, key=key)
        optional = set()
        for note in expected_sorted:
            optional.update([name for name in note if name in (
                "probability", "velocity_deviation", "release_velocity"
            )])
        for actual_note, expected_note in zip(actual_sorted, expected_sorted):
            for name in ("pitch", "velocity", "mute"):
                if actual_note.get(name) != expected_note.get(name):
                    return False
            for name in ("start_time", "duration"):
                if not self._state_value_equal(actual_note.get(name), expected_note.get(name), tolerance):
                    return False
            for name in optional:
                if not self._state_value_equal(actual_note.get(name), expected_note.get(name), tolerance):
                    return False
        return True

    def _remove_all_clip_notes(self, clip, snapshot):
        remove_extended = self._safe_getattr(clip, "remove_notes_extended", None)
        if callable(remove_extended):
            length = self._safe_getattr(clip, "length", None)
            try:
                span = max(float(length), 1048576.0)
            except (TypeError, ValueError):
                span = 1048576.0
            signatures = [
                (0, 128, 0.0, span),
                (0.0, 0, span, 128),
            ]
            for signature in signatures:
                try:
                    remove_extended(*signature)
                    return "remove_notes_extended"
                except TypeError:
                    continue

        remove_by_id = self._safe_getattr(clip, "remove_notes_by_id", None)
        if callable(remove_by_id):
            ids = [note.get("note_id") for note in snapshot if note.get("note_id") is not None]
            if ids:
                try:
                    remove_by_id(ids)
                    return "remove_notes_by_id"
                except TypeError:
                    remove_by_id(tuple(ids))
                    return "remove_notes_by_id"
            if snapshot:
                raise _RemoteScriptError(
                    "extended_notes_required",
                    "Cannot remove existing notes without note_id values"
                )
            return "remove_notes_by_id"

        set_notes = self._safe_getattr(clip, "set_notes", None)
        if callable(set_notes):
            set_notes(tuple())
            return "set_notes"
        raise _RemoteScriptError("unsupported_operation", "Clip note delete API is unavailable")

    def _add_clip_notes(self, clip, notes, method_hint=None):
        if not notes:
            return
        add_new = self._safe_getattr(clip, "add_new_notes", None)
        if callable(add_new):
            payload = [self._note_payload(note) for note in notes]
            # Max documentation shows {"notes": [...]}; Python Remote
            # Script builds have also accepted the list/tuple directly.
            try:
                add_new({"notes": payload})
                return
            except (TypeError, KeyError):
                try:
                    add_new(payload)
                    return
                except (TypeError, KeyError):
                    add_new(tuple(payload))
                    return
        set_notes = self._safe_getattr(clip, "set_notes", None)
        if callable(set_notes):
            set_notes(tuple(self._legacy_note_tuple(note) for note in notes))
            return
        raise _RemoteScriptError("unsupported_operation", "Clip note write API is unavailable")

    def _write_all_clip_notes(self, clip, notes, previous_notes):
        # Prefer a native extended replace, while preserving a legacy fallback
        # only when no extended delete API is present.
        add_new = self._safe_getattr(clip, "add_new_notes", None)
        remove_extended = self._safe_getattr(clip, "remove_notes_extended", None)
        remove_by_id = self._safe_getattr(clip, "remove_notes_by_id", None)
        set_notes = self._safe_getattr(clip, "set_notes", None)
        if not callable(set_notes) and not callable(remove_extended) and not callable(remove_by_id):
            raise _RemoteScriptError("unsupported_operation", "Clip note replacement API is unavailable")
        if not callable(add_new) and not callable(set_notes):
            raise _RemoteScriptError("unsupported_operation", "Clip note add API is unavailable")

        if callable(set_notes) and not callable(add_new) and not callable(remove_extended) and not callable(remove_by_id):
            set_notes(tuple(self._legacy_note_tuple(note) for note in notes))
            return

        self._remove_all_clip_notes(clip, previous_notes)
        self._add_clip_notes(clip, notes)

    def _get_clip_notes(self, params=None):
        values = self._copy_params(params)
        track, slot, clip, target = self._resolve_session_clip(values)
        from_time = values.get("from_time")
        from_pitch = values.get("from_pitch", 0)
        time_span = values.get("time_span")
        pitch_span = values.get("pitch_span", 128)
        notes, api = self._read_clip_notes(clip, from_time, from_pitch, time_span, pitch_span)
        return {
            "target": target,
            "notes": notes,
            "note_count": len(notes),
            "api": api,
            "from_time": 0.0 if from_time is None else from_time,
            "from_pitch": from_pitch,
            "time_span": time_span,
            "pitch_span": pitch_span,
        }

    def _replace_clip_notes(self, params=None):
        values = self._copy_params(params)
        track, slot, clip, target = self._resolve_session_clip(values)
        requested = self._validate_notes(values.get("notes", []))
        before, _api = self._read_clip_notes(clip)

        has_range = any(name in values for name in ("from_time", "from_pitch", "time_span", "pitch_span"))
        if has_range:
            from_time = float(values.get("from_time", 0.0))
            from_pitch = int(values.get("from_pitch", 0))
            time_span = values.get("time_span")
            if time_span is None:
                length = self._safe_getattr(clip, "length", 0.0)
                time_span = max(float(length) - from_time, 0.0)
            time_span = float(time_span)
            pitch_span = int(values.get("pitch_span", 128))
            if from_time < 0 or time_span < 0 or from_pitch < 0 or pitch_span <= 0:
                raise _RemoteScriptError("invalid_note_range", "Invalid note replacement range")
            for note in requested:
                in_time = from_time <= note["start_time"] < from_time + time_span
                in_pitch = from_pitch <= note["pitch"] < from_pitch + pitch_span
                if not (in_time and in_pitch):
                    raise _RemoteScriptError(
                        "note_outside_replacement_range",
                        "Every requested note must start inside the replacement range"
                    )
            outside = []
            for note in before:
                in_time = from_time <= float(note.get("start_time", 0.0)) < from_time + time_span
                in_pitch = from_pitch <= int(note.get("pitch", 0)) < from_pitch + pitch_span
                if not (in_time and in_pitch):
                    outside.append(note)
            desired = outside + requested
        else:
            desired = requested

        if values.get("dry_run", False):
            return {
                "dry_run": True,
                "target": target,
                "before": before,
                "requested": requested,
                "applied": None,
                "after": before,
            }

        try:
            self._write_all_clip_notes(clip, desired, before)
            after, _after_api = self._read_clip_notes(clip)
            if not self._notes_equal(after, desired, values.get("tolerance", 0.000001)):
                raise _RemoteScriptError(
                    "readback_mismatch", "Clip notes did not read back as requested",
                    {"expected_count": len(desired), "actual_count": len(after)}
                )
        except Exception as error:
            rollback_error = None
            try:
                self._write_all_clip_notes(clip, before, desired)
                restored, _restore_api = self._read_clip_notes(clip)
                if not self._notes_equal(restored, before):
                    rollback_error = "note snapshot readback mismatch"
            except Exception as restore_exception:
                rollback_error = str(restore_exception)
            details = {"rollback_error": rollback_error, "target": target}
            if isinstance(error, _RemoteScriptError):
                details["cause_code"] = error.code
            raise _RemoteScriptError("notes_rolled_back", str(error), details)

        return {
            "dry_run": False,
            "target": target,
            "before": before,
            "requested": requested,
            "applied": after,
            "after": after,
            "note_count": len(after),
        }

    def _clear_clip_notes(self, params=None):
        values = self._copy_params(params)
        values["notes"] = []
        return self._replace_clip_notes(values)

    def _clip_property_snapshot(self, clip):
        properties = {}
        for name in ("name", "length", "loop", "loop_start", "loop_end",
                     "start_marker", "end_marker", "warping", "warp_mode",
                     "gain", "pitch_coarse", "pitch_fine", "is_audio_clip", "is_midi_clip"):
            if self._safe_hasattr(clip, name):
                properties[name] = self._safe_getattr(clip, name)
        return properties

    def _get_clip_properties(self, params=None):
        values = self._copy_params(params)
        track, slot, clip, target = self._resolve_session_clip(values)
        properties = self._clip_property_snapshot(clip)
        return {"target": target, "properties": properties}

    def _get_output_meter_levels(self, params=None):
        values = self._copy_params(params)
        track, target = self._resolve_track(values)
        left = self._safe_getattr(track, "output_meter_left", None)
        right = self._safe_getattr(track, "output_meter_right", None)
        if left is None and right is None:
            raise _RemoteScriptError(
                "unsupported_operation",
                "Track output meter levels are unavailable"
            )
        return {
            "target": target,
            "left": left,
            "right": right,
        }

    def _set_clip_loop(self, params=None):
        values = self._copy_params(params)
        track, slot, clip, target = self._resolve_session_clip(values)
        updates = {}
        for name in ("loop", "loop_start", "loop_end", "start_marker", "end_marker"):
            if name in values:
                if not self._safe_hasattr(clip, name):
                    raise _RemoteScriptError("unsupported_parameter", "Clip property is unavailable: %s" % name)
                updates[name] = values[name]
        if not updates:
            raise _RemoteScriptError("value_required", "At least one loop property is required")
        before = {}
        for name in updates:
            before[name] = self._safe_getattr(clip, name)
        loop_start = updates.get("loop_start", before.get("loop_start"))
        loop_end = updates.get("loop_end", before.get("loop_end"))
        if loop_start is not None and loop_end is not None:
            try:
                if float(loop_start) < 0 or float(loop_end) <= float(loop_start):
                    raise _RemoteScriptError("invalid_loop", "loop_end must be greater than loop_start")
            except (TypeError, ValueError):
                raise _RemoteScriptError("invalid_loop", "Loop markers must be numeric")
        if values.get("dry_run", False):
            return {
                "dry_run": True, "target": target, "before": before,
                "requested": updates, "applied": None, "after": before,
            }
        applied_names = []
        try:
            for name in updates:
                setattr(clip, name, updates[name])
                applied_names.append(name)
            after = {name: self._safe_getattr(clip, name) for name in updates}
            for name in updates:
                if not self._state_value_equal(after[name], updates[name], values.get("tolerance", 0.000001)):
                    raise _RemoteScriptError("readback_mismatch", "Clip loop property did not read back")
        except Exception as error:
            rollback_error = None
            try:
                for name in reversed(applied_names):
                    setattr(clip, name, before[name])
            except Exception as restore_exception:
                rollback_error = str(restore_exception)
            raise _RemoteScriptError(
                "clip_loop_rolled_back", str(error),
                {"target": target, "rollback_error": rollback_error}
            )
        return {
            "dry_run": False, "target": target, "before": before,
            "requested": updates, "applied": after, "after": after,
        }

    def _delete_session_clip(self, params=None):
        values = self._copy_params(params)
        track, slot, clip, target = self._resolve_session_clip(values, require_expected_name=True)
        delete_clip = self._safe_getattr(slot, "delete_clip", None)
        if not callable(delete_clip):
            raise _RemoteScriptError("unsupported_operation", "ClipSlot.delete_clip is unavailable")
        before = {"exists": True, "name": target.get("clip_name")}
        if values.get("dry_run", False):
            return {
                "dry_run": True, "target": target, "before": before,
                "requested": "delete", "applied": None, "after": before,
            }
        delete_clip()
        after_exists = bool(self._safe_getattr(slot, "has_clip", False))
        if after_exists:
            raise _RemoteScriptError("readback_mismatch", "Session clip still exists after delete")
        return {
            "dry_run": False, "target": target, "before": before,
            "requested": "delete", "applied": True,
            "after": {"exists": False},
        }

    # ------------------------------------------------------------------
    # Session variants and auditioning
    # ------------------------------------------------------------------

    def _slot_snapshot(self, slot):
        if not bool(self._safe_getattr(slot, "has_clip", False)):
            return {"exists": False}
        clip = self._safe_getattr(slot, "clip", None)
        snapshot = {
            "exists": True,
            "name": self._safe_getattr(clip, "name", None),
            "length": self._safe_getattr(clip, "length", None),
        }
        try:
            snapshot["notes"], _api = self._read_clip_notes(clip)
        except Exception:
            snapshot["notes"] = None
        return snapshot

    def _restore_slot_snapshot(self, slot, snapshot):
        delete_clip = self._safe_getattr(slot, "delete_clip", None)
        if callable(delete_clip) and bool(self._safe_getattr(slot, "has_clip", False)):
            delete_clip()
        if not snapshot.get("exists"):
            return
        create_clip = self._safe_getattr(slot, "create_clip", None)
        if not callable(create_clip):
            raise _RemoteScriptError("rollback_unavailable", "Cannot recreate overwritten clip")
        create_clip(snapshot.get("length", 4.0))
        restored = self._safe_getattr(slot, "clip", None)
        if restored is None:
            raise _RemoteScriptError("rollback_unavailable", "Recreated clip is unreadable")
        if snapshot.get("name") is not None:
            restored.name = snapshot.get("name")
        if snapshot.get("notes") is not None:
            self._write_all_clip_notes(restored, snapshot.get("notes"), [])

    def _resolve_duplicate_pair(self, values):
        source_values = dict(values)
        source_track_index = source_values.get(
            "source_track_index", source_values.get("track_index", 0)
        )
        source_clip_index = source_values.get(
            "source_clip_index", source_values.get("clip_index", 0)
        )
        source_expected_track = source_values.get(
            "expected_source_track_name", source_values.get("expected_track_name")
        )
        source_track_type = source_values.get(
            "source_track_kind", source_values.get("track_type", source_values.get("track_kind", "normal"))
        )
        source_expected_clip = source_values.get(
            "expected_source_clip_name", source_values.get("expected_clip_name")
        )
        source_track, source_slot, source_clip, source_target = self._resolve_session_clip({
            "track_index": source_track_index,
            "clip_index": source_clip_index,
            "expected_track_name": source_expected_track,
            "expected_clip_name": source_expected_clip,
            "track_type": source_track_type,
        })

        destination_track_index = values.get(
            "destination_track_index", values.get("dest_track_index", source_track_index)
        )
        destination_clip_index = values.get(
            "destination_clip_index", values.get("dest_clip_index")
        )
        if destination_clip_index is None:
            raise _RemoteScriptError("destination_required", "destination_clip_index is required")
        destination_track_type = values.get(
            "destination_track_type", values.get("destination_track_kind", source_track_type)
        )
        destination_expected_track = values.get(
            "expected_destination_track_name", values.get("destination_expected_track_name")
        )
        destination_track, destination_target = self._resolve_track(
            destination_track_index, destination_expected_track, destination_track_type
        )
        destination_index = self._coerce_index(destination_clip_index, "destination_clip_index")
        destination_slots = getattr(destination_track, "clip_slots", ())
        if destination_index < 0 or destination_index >= len(destination_slots):
            raise _RemoteScriptError("destination_not_found", "Destination clip slot index out of range")
        destination_slot = destination_slots[destination_index]
        destination_clip = self._safe_getattr(destination_slot, "clip", None)
        destination_expected_clip = values.get(
            "expected_destination_clip_name", values.get("destination_expected_clip_name")
        )
        if destination_clip is not None and destination_expected_clip is not None:
            actual_destination_name = self._safe_getattr(destination_clip, "name", None)
            if actual_destination_name != destination_expected_clip:
                raise _RemoteScriptError(
                    "destination_clip_identity_mismatch",
                    "Destination clip name mismatch",
                    {"expected_clip_name": destination_expected_clip,
                     "actual_clip_name": actual_destination_name}
                )
        if source_track is destination_track and source_slot is destination_slot:
            raise _RemoteScriptError("invalid_destination", "Source and destination clips are identical")
        duplicate_to = self._safe_getattr(source_slot, "duplicate_clip_to", None)
        if not callable(duplicate_to):
            raise _RemoteScriptError(
                "unsupported_operation",
                "ClipSlot.duplicate_clip_to is unavailable"
            )
        occupied = bool(self._safe_getattr(destination_slot, "has_clip", False))
        overwrite = bool(values.get("overwrite", False))
        if occupied and not overwrite:
            raise _RemoteScriptError(
                "destination_occupied", "Destination session slot is occupied",
                {"destination_track_index": destination_track_index,
                 "destination_clip_index": destination_index}
            )
        return {
            "source_track": source_track,
            "source_slot": source_slot,
            "source_clip": source_clip,
            "source_target": source_target,
            "destination_track": destination_track,
            "destination_slot": destination_slot,
            "destination_target": dict(destination_target, clip_index=destination_index),
            "destination_index": destination_index,
            "destination_snapshot": self._slot_snapshot(destination_slot),
            "occupied": occupied,
            "overwrite": overwrite,
        }

    def _duplicate_pairs(self, pairs, values):
        if values.get("dry_run", False):
            return {
                "dry_run": True,
                "targets": [
                    {"source": pair["source_target"], "destination": pair["destination_target"]}
                    for pair in pairs
                ],
                "copied": [],
            }
        changed = []
        copied = []
        try:
            for pair in pairs:
                changed.append(pair)
                duplicate_to = self._safe_getattr(pair["source_slot"], "duplicate_clip_to", None)
                duplicate_to(pair["destination_slot"])
                destination_clip = self._safe_getattr(pair["destination_slot"], "clip", None)
                if not bool(self._safe_getattr(pair["destination_slot"], "has_clip", False)) or destination_clip is None:
                    raise _RemoteScriptError("readback_mismatch", "Duplicated clip is not readable")
                expected_name = self._safe_getattr(pair["source_clip"], "name", None)
                actual_name = self._safe_getattr(destination_clip, "name", None)
                if expected_name != actual_name:
                    raise _RemoteScriptError(
                        "readback_mismatch", "Duplicated clip name did not read back",
                        {"expected_name": expected_name, "actual_name": actual_name}
                    )
                copied.append({
                    "source": pair["source_target"],
                    "destination": pair["destination_target"],
                    "clip_name": actual_name,
                    "length": self._safe_getattr(destination_clip, "length", None),
                })
        except Exception as error:
            rollback_errors = []
            for pair in reversed(changed):
                try:
                    self._restore_slot_snapshot(pair["destination_slot"], pair["destination_snapshot"])
                except Exception as restore_exception:
                    rollback_errors.append({"target": pair["destination_target"], "error": str(restore_exception)})
            raise _RemoteScriptError(
                "duplicate_rolled_back", str(error),
                {"rollback_errors": rollback_errors, "copied_before_failure": copied}
            )
        return {"dry_run": False, "targets": copied, "copied": copied}

    def _duplicate_session_clip(self, params=None):
        values = self._copy_params(params)
        pair = self._resolve_duplicate_pair(values)
        result = self._duplicate_pairs([pair], values)
        if result.get("copied"):
            copied = result["copied"][0]
            return {
                "dry_run": result.get("dry_run", False),
                "target": copied.get("destination"),
                "source": copied.get("source"),
                "before": pair["destination_snapshot"],
                "requested": "duplicate",
                "applied": copied,
                "after": self._slot_snapshot(pair["destination_slot"]),
            }
        return result

    def _scene_at(self, index, expected_name=None):
        scenes = self._safe_getattr(self._song, "scenes", ()) or ()
        index = self._coerce_index(index, "scene_index")
        if index < 0 or index >= len(scenes):
            raise _RemoteScriptError("scene_not_found", "Scene index out of range")
        scene = scenes[index]
        actual_name = self._safe_getattr(scene, "name", None)
        if expected_name is not None and actual_name != expected_name:
            raise _RemoteScriptError(
                "scene_identity_mismatch", "Scene name mismatch",
                {"expected_scene_name": expected_name, "actual_scene_name": actual_name}
            )
        return scene, {"scene_index": index, "scene_name": actual_name}

    def _duplicate_session_scene_clips(self, params=None):
        values = self._copy_params(params)
        source_scene_index = values.get("source_scene_index", values.get("scene_index"))
        destination_scene_index = values.get("destination_scene_index")
        if source_scene_index is None or destination_scene_index is None:
            raise _RemoteScriptError("scene_required", "source and destination scene indexes are required")
        _source_scene, source_scene_target = self._scene_at(
            source_scene_index,
            values.get("expected_source_scene_name", values.get("expected_scene_name"))
        )
        _destination_scene, destination_scene_target = self._scene_at(
            destination_scene_index, values.get("expected_destination_scene_name")
        )
        track_indexes = values.get("track_indices", values.get("track_subset"))
        if track_indexes is None:
            track_indexes = list(range(len(getattr(self._song, "tracks", ()))))
        if not isinstance(track_indexes, (list, tuple)) or not track_indexes:
            raise _RemoteScriptError("track_subset_required", "track_indices must be a non-empty list")
        expected_source_tracks = values.get("expected_source_track_names", {})
        expected_destination_tracks = values.get("expected_destination_track_names", {})
        expected_source_clips = values.get("expected_source_clip_names", {})
        pairs = []
        for position, track_item in enumerate(track_indexes):
            if isinstance(track_item, dict):
                track_index = track_item.get("track_index")
                if track_index is None:
                    raise _RemoteScriptError("invalid_track_subset", "track_subset item needs track_index")
                item_expected_track = track_item.get("expected_track_name")
                item_track_kind = track_item.get("track_kind", track_item.get("track_type", "normal"))
            else:
                track_index = track_item
                item_expected_track = None
                item_track_kind = "normal"
            if isinstance(expected_source_tracks, (list, tuple)):
                source_expected_track = expected_source_tracks[position] if position < len(expected_source_tracks) else None
            else:
                source_expected_track = expected_source_tracks.get(str(track_index), expected_source_tracks.get(track_index)) if isinstance(expected_source_tracks, dict) else None
            if source_expected_track is None:
                source_expected_track = item_expected_track
            if isinstance(expected_destination_tracks, (list, tuple)):
                destination_expected_track = expected_destination_tracks[position] if position < len(expected_destination_tracks) else None
            else:
                destination_expected_track = expected_destination_tracks.get(str(track_index), expected_destination_tracks.get(track_index)) if isinstance(expected_destination_tracks, dict) else None
            if destination_expected_track is None:
                destination_expected_track = item_expected_track
            if isinstance(expected_source_clips, (list, tuple)):
                source_expected_clip = expected_source_clips[position] if position < len(expected_source_clips) else None
            else:
                source_expected_clip = expected_source_clips.get(str(track_index), expected_source_clips.get(track_index)) if isinstance(expected_source_clips, dict) else None
            pair_values = dict(values)
            pair_values.update({
                "track_index": track_index,
                "clip_index": source_scene_index,
                "expected_track_name": source_expected_track,
                "expected_clip_name": source_expected_clip,
                "destination_track_index": track_index,
                "destination_clip_index": destination_scene_index,
                "expected_destination_track_name": destination_expected_track,
                "track_type": item_track_kind,
                "destination_track_type": item_track_kind,
            })
            pairs.append(self._resolve_duplicate_pair(pair_values))
        result = self._duplicate_pairs(pairs, values)
        result["source_scene"] = source_scene_target
        result["destination_scene"] = destination_scene_target
        result["track_indices"] = list(track_indexes)
        return result

    def _fire_scene(self, params=None):
        values = self._copy_params(params)
        scene, target = self._scene_at(
            values.get("scene_index", 0), values.get("expected_scene_name")
        )
        before = {"is_playing": self._safe_getattr(self._song, "is_playing", None)}
        if values.get("dry_run", False):
            return {"dry_run": True, "target": target, "before": before,
                    "requested": "fire", "applied": None, "after": before}
        fire = self._safe_getattr(scene, "fire", None)
        if not callable(fire):
            raise _RemoteScriptError("unsupported_operation", "Scene.fire is unavailable")
        expected_quantization = values.get("expected_global_quantization")
        actual_quantization = self._safe_getattr(
            self._song, "clip_trigger_quantization", None
        )
        if expected_quantization is not None and actual_quantization != expected_quantization:
            raise _RemoteScriptError(
                "quantization_mismatch",
                "Global clip trigger quantization does not match the expected value",
                {"expected_global_quantization": expected_quantization,
                 "actual_global_quantization": actual_quantization}
            )
        force_legato = values.get("force_legato", False)
        can_select = values.get("can_select_scene_on_launch", True)
        try:
            fire(force_legato, can_select)
        except TypeError:
            fire()
        after = {"is_playing": self._safe_getattr(self._song, "is_playing", None)}
        return {"dry_run": False, "target": target, "before": before,
                "requested": {"force_legato": force_legato,
                              "can_select_scene_on_launch": can_select,
                              "expected_global_quantization": expected_quantization},
                "applied": {"fired": True,
                            "global_quantization": actual_quantization}, "after": after}

    def _stop_all_clips(self, params=None):
        values = self._copy_params(params)
        subset = values.get("track_subset")
        subset_targets = []
        subset_tracks = []
        if subset is not None:
            if not isinstance(subset, (list, tuple)) or not subset:
                raise _RemoteScriptError("invalid_track_subset", "track_subset must be a non-empty list")
            for item in subset:
                item_values = item if isinstance(item, dict) else {"track_index": item}
                track, target = self._resolve_track(item_values)
                stop_track = self._safe_getattr(track, "stop_all_clips", None)
                if not callable(stop_track):
                    raise _RemoteScriptError("unsupported_operation", "Track.stop_all_clips is unavailable")
                subset_tracks.append((track, stop_track))
                subset_targets.append(target)
            stop = None
        else:
            stop = self._safe_getattr(self._song, "stop_all_clips", None)
            if not callable(stop):
                raise _RemoteScriptError("unsupported_operation", "Song.stop_all_clips is unavailable")
        before = {"is_playing": self._safe_getattr(self._song, "is_playing", None)}
        if values.get("dry_run", False):
            return {"dry_run": True, "target": {"scope": "tracks" if subset is not None else "song",
                                                   "tracks": subset_targets}, "before": before,
                    "requested": {"quantized": values.get("quantized")},
                    "applied": None, "after": before}
        if subset_tracks:
            for _track, stop_track in subset_tracks:
                stop_track()
        else:
            if "quantized" in values:
                try:
                    stop(values.get("quantized"))
                except TypeError:
                    stop()
            else:
                stop()
        after = {"is_playing": self._safe_getattr(self._song, "is_playing", None)}
        return {"dry_run": False, "target": {"scope": "tracks" if subset is not None else "song",
                                                "tracks": subset_targets}, "before": before,
                "requested": {"quantized": values.get("quantized")},
                "applied": True, "after": after}

    def _back_to_arrangement(self, params=None):
        values = self._copy_params(params)
        if not self._safe_hasattr(self._song, "back_to_arranger"):
            raise _RemoteScriptError("unsupported_operation", "Song.back_to_arranger is unavailable")
        before = self._safe_getattr(self._song, "back_to_arranger", None)
        if values.get("dry_run", False):
            return {"dry_run": True, "target": {"scope": "song"}, "before": before,
                    "requested": 0, "applied": None, "after": before}
        self._song.back_to_arranger = 0
        after = self._safe_getattr(self._song, "back_to_arranger", None)
        return {"dry_run": False, "target": {"scope": "song"}, "before": before,
                "requested": 0, "applied": after, "after": after}

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

    def _arrangement_clip_record(self, clip):
        start_time = self._safe_getattr(clip, "start_time", None)
        end_time = self._safe_getattr(clip, "end_time", None)
        length = self._safe_getattr(clip, "length", None)
        if end_time is None and start_time is not None and length is not None:
            try:
                end_time = float(start_time) + float(length)
            except (TypeError, ValueError):
                end_time = None
        return {
            "name": self._safe_getattr(clip, "name", None),
            "start_time": start_time,
            "end_time": end_time,
            "length": length,
            "duration": length,
            "color": self._safe_getattr(clip, "color", None),
            "is_midi_clip": self._safe_getattr(clip, "is_midi_clip", None),
            "is_audio_clip": self._safe_getattr(clip, "is_audio_clip", None),
            "is_playing": self._safe_getattr(clip, "is_playing", None),
        }

    def _resolve_arrangement_clip(self, params=None, require_exact=False):
        """Resolve exactly one Arrangement clip by name, start, and duration."""
        values = self._copy_params(params)
        track, track_target = self._resolve_track(values)
        expected_name = values.get(
            "expected_arrangement_clip_name",
            values.get("expected_clip_name", values.get("clip_name"))
        )
        expected_start = values.get(
            "expected_start_time", values.get("start_time")
        )
        expected_duration = values.get(
            "expected_duration", values.get("duration")
        )
        if require_exact and (expected_name is None or expected_start is None or expected_duration is None):
            raise _RemoteScriptError(
                "arrangement_target_required",
                "Arrangement target requires name, start_time, and duration"
            )
        clips = list(self._safe_getattr(track, "arrangement_clips", ()) or ())
        tolerance = values.get("tolerance", 0.000001)
        matches = []
        for clip in clips:
            if expected_name is not None and self._safe_getattr(clip, "name", None) != expected_name:
                continue
            if expected_start is not None and not self._state_value_equal(
                    self._safe_getattr(clip, "start_time", None), expected_start, tolerance):
                continue
            actual_length = self._safe_getattr(clip, "length", None)
            if expected_duration is not None and not self._state_value_equal(
                    actual_length, expected_duration, tolerance):
                continue
            matches.append(clip)
        if len(matches) != 1:
            raise _RemoteScriptError(
                "arrangement_target_ambiguous",
                "Expected exactly one Arrangement clip",
                {"match_count": len(matches), "expected_name": expected_name,
                 "expected_start_time": expected_start, "expected_duration": expected_duration}
            )
        clip = matches[0]
        target = dict(track_target)
        target.update({
            "clip_name": self._safe_getattr(clip, "name", None),
            "start_time": self._safe_getattr(clip, "start_time", None),
            "duration": self._safe_getattr(clip, "length", None),
        })
        return track, clip, target

    def _get_arrangement_clips(self, track_index, expected_track_name=None, track_type="normal"):
        """Return all clips placed in the Arrangement timeline for a track.

        Each clip dict contains:
          name, start_time, end_time, length, color,
          is_midi_clip, is_audio_clip, is_playing
        """
        try:
            track, target = self._resolve_track(track_index, expected_track_name, track_type)
            clips = []

            # track.arrangement_clips is available in Live 11 / 12
            for clip in getattr(track, "arrangement_clips", ()):
                clips.append(self._arrangement_clip_record(clip))

            return {
                "track_index": target["track_index"],
                "track_name": track.name,
                "track_type": target["track_type"],
                "clip_count": len(clips),
                "clips": clips
            }
        except Exception as e:
            self.log_message("Error getting arrangement clips: " + str(e))
            raise

    def _duplicate_session_clip_to_arrangement(self, params=None, clip_index=None, destination_time=None):
        """Copy a Session-view clip into the Arrangement timeline.

        Uses the real Live API:
          track.duplicate_clip_to_arrangement(clip, destination_time)

        Available in Live 11 / 12.  destination_time is in beats from the
        start of the arrangement.
        """
        values = self._copy_params(params) if isinstance(params, dict) else {
            "track_index": params, "clip_index": clip_index,
            "destination_time": destination_time,
        }
        track, slot, clip, source_target = self._resolve_session_clip(values)
        duplicate = self._safe_getattr(track, "duplicate_clip_to_arrangement", None)
        if not callable(duplicate):
            raise _RemoteScriptError(
                "unsupported_operation",
                "Track.duplicate_clip_to_arrangement is unavailable"
            )
        if values.get("destination_time") is None:
            raise _RemoteScriptError("destination_required", "destination_time is required")
        try:
            destination_time = float(values.get("destination_time"))
        except (TypeError, ValueError):
            raise _RemoteScriptError("invalid_destination", "destination_time must be numeric")
        if destination_time < 0:
            raise _RemoteScriptError("invalid_destination", "destination_time cannot be negative")
        length = self._safe_getattr(clip, "length", None)
        try:
            destination_end = destination_time + float(length)
        except (TypeError, ValueError):
            destination_end = None
        existing_arrangement_clips = list(
            self._safe_getattr(track, "arrangement_clips", ()) or ()
        )
        overlaps = []
        for arrangement_clip in existing_arrangement_clips:
            start = self._safe_getattr(arrangement_clip, "start_time", None)
            end = self._safe_getattr(arrangement_clip, "end_time", None)
            if end is None and start is not None:
                try:
                    end = float(start) + float(self._safe_getattr(arrangement_clip, "length", 0.0))
                except (TypeError, ValueError):
                    end = None
            try:
                if destination_end is not None and start is not None and end is not None and \
                        float(start) < destination_end and float(end) > destination_time:
                    overlaps.append(arrangement_clip)
            except (TypeError, ValueError):
                continue
        if overlaps and not bool(values.get("overwrite", False)):
            raise _RemoteScriptError(
                "destination_occupied", "Arrangement destination overlaps an existing clip",
                {"overlap_count": len(overlaps), "destination_time": destination_time}
            )
        if overlaps and bool(values.get("overwrite", False)):
            # Live has no generally recoverable Arrangement replacement API
            # across supported versions. Refuse a destructive overwrite even
            # when the caller opts in; the default remains fail-closed.
            raise _RemoteScriptError(
                "overwrite_unsupported",
                "Arrangement overwrite is unavailable without a recovery API"
            )
        before = {"destination_time": destination_time, "overlap_count": 0}
        if values.get("dry_run", False):
            return {"success": False, "dry_run": True, "target": source_target,
                    "track_index": source_target.get("track_index"),
                    "track_name": source_target.get("name"),
                    "clip_name": source_target.get("clip_name"),
                    "destination_time": destination_time,
                    "before": before, "requested": destination_time,
                    "applied": None, "after": before}
        try:
            duplicate(clip, destination_time)
            matches = []
            for arrangement_clip in list(self._safe_getattr(track, "arrangement_clips", ()) or ()):
                if self._safe_getattr(arrangement_clip, "name", None) == self._safe_getattr(clip, "name", None) and \
                        self._state_value_equal(self._safe_getattr(arrangement_clip, "start_time", None), destination_time, values.get("tolerance", 0.000001)) and \
                        self._state_value_equal(self._safe_getattr(arrangement_clip, "length", None), length, values.get("tolerance", 0.000001)):
                    matches.append(arrangement_clip)
            if len(matches) != 1:
                raise _RemoteScriptError(
                    "readback_mismatch", "Arrangement duplicate did not produce one exact target",
                    {"match_count": len(matches)}
                )
        except Exception as error:
            rollback_errors = []
            delete_clip = self._safe_getattr(track, "delete_clip", None)
            current_clips = list(self._safe_getattr(track, "arrangement_clips", ()) or ())
            inserted = [candidate for candidate in current_clips
                        if candidate not in existing_arrangement_clips]
            if inserted and callable(delete_clip):
                for candidate in inserted:
                    try:
                        delete_clip(candidate)
                    except Exception as rollback_exception:
                        rollback_errors.append(str(rollback_exception))
            elif inserted:
                rollback_errors.append("Track.delete_clip is unavailable")
            raise _RemoteScriptError(
                "arrangement_duplicate_rolled_back", str(error),
                {"target": source_target, "rollback_errors": rollback_errors,
                 "inserted_count": len(inserted)}
            )
        after = self._arrangement_clip_record(matches[0])
        return {"success": True, "dry_run": False, "target": source_target,
                "track_index": source_target.get("track_index"),
                "track_name": source_target.get("name"),
                "clip_name": source_target.get("clip_name"),
                "destination_time": destination_time,
                "before": before, "requested": destination_time,
                "applied": after, "after": after}

    def _delete_arrangement_clip(self, params=None):
        values = self._copy_params(params)
        track, clip, target = self._resolve_arrangement_clip(values, require_exact=True)
        delete_clip = self._safe_getattr(track, "delete_clip", None)
        if not callable(delete_clip):
            raise _RemoteScriptError(
                "unsupported_operation",
                "Track.delete_clip is unavailable in this Live runtime"
            )
        before = self._arrangement_clip_record(clip)
        if values.get("dry_run", False):
            return {"dry_run": True, "target": target, "before": before,
                    "requested": "delete", "applied": None, "after": before}
        delete_clip(clip)
        remaining = []
        for candidate in list(self._safe_getattr(track, "arrangement_clips", ()) or ()):
            if candidate is clip:
                remaining.append(candidate)
        if remaining:
            raise _RemoteScriptError("readback_mismatch", "Arrangement clip still exists after delete")
        return {"dry_run": False, "target": target, "before": before,
                "requested": "delete", "applied": True, "after": {"exists": False}}

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
