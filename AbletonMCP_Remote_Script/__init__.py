# AbletonMCP Remote Script
from __future__ import absolute_import, print_function, unicode_literals

from _Framework.ControlSurface import ControlSurface
import socket
import json
import threading
import time
import traceback

# Queue import compatible with Python 2 and 3
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
    """AbletonMCP Remote Script for Ableton Live.

    Receives TCP socket commands from the MCP server and executes them
    using Ableton's Python API.
    """

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

        # Build command registry
        self._build_command_registry()

        # Start the socket server
        self.start_server()

        self.log_message("AbletonMCP initialized")
        self.show_message("AbletonMCP: Listening for commands on port " + str(DEFAULT_PORT))

    # ------------------------------------------------------------------
    # Command registry
    # ------------------------------------------------------------------

    def _build_command_registry(self):
        """Build the command handler registry and read/write classification."""
        self._command_handlers = {
            # Session (read-only)
            "get_session_info": self._get_session_info_handler,
            "get_track_info": self._get_track_info_handler,
            "get_all_tracks_info": self._get_all_tracks_info_handler,
            "get_full_session_state": self._get_full_session_state_handler,
            "get_clip_notes": self._get_clip_notes_handler,
            "get_playing_position": self._get_playing_position_handler,
            # Scene read-only
            "get_scene_info": self._get_scene_info_handler,
            "get_all_scenes": self._get_all_scenes_handler,
            # Device read-only
            "get_device_parameters": self._get_device_parameters_handler,
            "get_device_info": self._get_device_info_handler,
            # Browser (read-only)
            "get_browser_item": self._get_browser_item_handler,
            "get_browser_categories": self._get_browser_categories_handler,
            "get_browser_items": self._get_browser_items_handler,
            "get_browser_tree": self._get_browser_tree_handler,
            "get_browser_items_at_path": self._get_browser_items_at_path_handler,
            "search_browser": self._search_browser_handler,
            # Track management (write)
            "create_midi_track": self._create_midi_track_handler,
            "create_audio_track": self._create_audio_track_handler,
            "delete_track": self._delete_track_handler,
            "duplicate_track": self._duplicate_track_handler,
            "set_track_name": self._set_track_name_handler,
            "set_track_volume": self._set_track_volume_handler,
            "set_track_pan": self._set_track_pan_handler,
            "set_track_mute": self._set_track_mute_handler,
            "set_track_solo": self._set_track_solo_handler,
            "set_track_arm": self._set_track_arm_handler,
            "set_track_send": self._set_track_send_handler,
            # Clip operations (write)
            "create_clip": self._create_clip_handler,
            "add_notes_to_clip": self._add_notes_to_clip_handler,
            "set_clip_name": self._set_clip_name_handler,
            "delete_clip": self._delete_clip_handler,
            "duplicate_clip_to_slot": self._duplicate_clip_to_slot_handler,
            "remove_notes_from_clip": self._remove_notes_from_clip_handler,
            "set_clip_loop": self._set_clip_loop_handler,
            "quantize_clip": self._quantize_clip_handler,
            "fire_clip": self._fire_clip_handler,
            "stop_clip": self._stop_clip_handler,
            # Scene management (write)
            "create_scene": self._create_scene_handler,
            "delete_scene": self._delete_scene_handler,
            "duplicate_scene": self._duplicate_scene_handler,
            "fire_scene": self._fire_scene_handler,
            "set_scene_name": self._set_scene_name_handler,
            "stop_all_clips": self._stop_all_clips_handler,
            # Device parameters (write)
            "set_device_parameter": self._set_device_parameter_handler,
            "set_device_parameter_by_name": self._set_device_parameter_by_name_handler,
            "toggle_device": self._toggle_device_handler,
            "delete_device": self._delete_device_handler,
            # Transport / global (write)
            "set_tempo": self._set_tempo_handler,
            "start_playback": self._start_playback_handler,
            "stop_playback": self._stop_playback_handler,
            "undo": self._undo_handler,
            "redo": self._redo_handler,
            "set_metronome": self._set_metronome_handler,
            "set_loop": self._set_loop_handler,
            "set_time_signature": self._set_time_signature_handler,
            "capture_midi": self._capture_midi_handler,
            "tap_tempo": self._tap_tempo_handler,
            "set_arrangement_position": self._set_arrangement_position_handler,
            "set_record": self._set_record_handler,
            # Browser load (write)
            "load_browser_item": self._load_browser_item_handler,
            "load_instrument_or_effect": self._load_instrument_or_effect_handler,
        }

        # Read-only commands execute directly on the socket thread
        self._read_commands = {
            "get_session_info",
            "get_track_info",
            "get_all_tracks_info",
            "get_full_session_state",
            "get_clip_notes",
            "get_playing_position",
            "get_scene_info",
            "get_all_scenes",
            "get_device_parameters",
            "get_device_info",
            "get_browser_item",
            "get_browser_categories",
            "get_browser_items",
            "get_browser_tree",
            "get_browser_items_at_path",
            "search_browser",
        }

        # Write commands must be scheduled on Ableton's main thread
        self._write_commands = {
            "create_midi_track",
            "create_audio_track",
            "delete_track",
            "duplicate_track",
            "set_track_name",
            "set_track_volume",
            "set_track_pan",
            "set_track_mute",
            "set_track_solo",
            "set_track_arm",
            "set_track_send",
            "create_clip",
            "add_notes_to_clip",
            "set_clip_name",
            "delete_clip",
            "duplicate_clip_to_slot",
            "remove_notes_from_clip",
            "set_clip_loop",
            "quantize_clip",
            "fire_clip",
            "stop_clip",
            "create_scene",
            "delete_scene",
            "duplicate_scene",
            "fire_scene",
            "set_scene_name",
            "stop_all_clips",
            "set_device_parameter",
            "set_device_parameter_by_name",
            "toggle_device",
            "delete_device",
            "set_tempo",
            "start_playback",
            "stop_playback",
            "undo",
            "redo",
            "set_metronome",
            "set_loop",
            "set_time_signature",
            "capture_midi",
            "tap_tempo",
            "set_arrangement_position",
            "set_record",
            "load_browser_item",
            "load_instrument_or_effect",
        }

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def disconnect(self):
        """Called when Ableton closes or the control surface is removed"""
        self.log_message("AbletonMCP disconnecting...")
        self.running = False

        if self.server:
            try:
                self.server.close()
            except Exception:
                pass

        if self.server_thread and self.server_thread.is_alive():
            self.server_thread.join(1.0)

        for client_thread in self.client_threads[:]:
            if client_thread.is_alive():
                self.log_message("Client thread still alive during disconnect")

        ControlSurface.disconnect(self)
        self.log_message("AbletonMCP disconnected")

    # ------------------------------------------------------------------
    # Socket server
    # ------------------------------------------------------------------

    def start_server(self):
        """Start the socket server in a separate thread"""
        try:
            self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server.bind((HOST, DEFAULT_PORT))
            self.server.listen(5)

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
            self.server.settimeout(1.0)

            while self.running:
                try:
                    client, address = self.server.accept()
                    self.log_message("Connection accepted from " + str(address))
                    self.show_message("AbletonMCP: Client connected")

                    client_thread = threading.Thread(
                        target=self._handle_client,
                        args=(client,)
                    )
                    client_thread.daemon = True
                    client_thread.start()

                    self.client_threads.append(client_thread)
                    self.client_threads = [t for t in self.client_threads if t.is_alive()]

                except socket.timeout:
                    continue
                except Exception as e:
                    if self.running:
                        self.log_message("Server accept error: " + str(e))
                    time.sleep(0.5)

            self.log_message("Server thread stopped")
        except Exception as e:
            self.log_message("Server thread error: " + str(e))

    def _handle_client(self, client):
        """Handle communication with a connected client"""
        self.log_message("Client handler started")
        client.settimeout(None)
        buffer = ''

        try:
            while self.running:
                try:
                    data = client.recv(8192)

                    if not data:
                        self.log_message("Client disconnected")
                        break

                    try:
                        buffer += data.decode('utf-8')
                    except AttributeError:
                        buffer += data

                    try:
                        command = json.loads(buffer)
                        buffer = ''

                        # Batch command support: if the payload is a list,
                        # process each command individually and return an array.
                        if isinstance(command, list):
                            responses = []
                            for cmd in command:
                                responses.append(self._process_command(cmd))
                            response_str = json.dumps(responses, ensure_ascii=False)
                        else:
                            self.log_message("Received command: " + str(command.get("type", "unknown")))
                            response = self._process_command(command)
                            response_str = json.dumps(response, ensure_ascii=False)

                        try:
                            client.sendall(response_str.encode('utf-8'))
                        except AttributeError:
                            client.sendall(response_str)
                    except ValueError:
                        # Incomplete JSON, wait for more data
                        continue

                except Exception as e:
                    self.log_message("Error handling client data: " + str(e))
                    self.log_message(traceback.format_exc())

                    error_response = {
                        "status": "error",
                        "message": str(e)
                    }
                    try:
                        client.sendall(json.dumps(error_response, ensure_ascii=False).encode('utf-8'))
                    except AttributeError:
                        client.sendall(json.dumps(error_response, ensure_ascii=False))
                    except Exception:
                        break

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

    # ------------------------------------------------------------------
    # Command dispatch
    # ------------------------------------------------------------------

    def _process_command(self, command):
        """Process a command from the client and return a response"""
        command_type = command.get("type", "")
        params = command.get("params", {})

        response = {
            "status": "success",
            "result": {}
        }

        try:
            handler = self._command_handlers.get(command_type)
            if handler is None:
                response["status"] = "error"
                response["message"] = "Unknown command: " + command_type
                return response

            if command_type in self._read_commands:
                # Read-only: execute directly
                response["result"] = handler(params)
            elif command_type in self._write_commands:
                # Write: schedule on main thread via queue
                response_queue = queue.Queue()

                def main_thread_task():
                    try:
                        result = handler(params)
                        response_queue.put({"status": "success", "result": result})
                    except Exception as e:
                        self.log_message("Error in main thread task: " + str(e))
                        self.log_message(traceback.format_exc())
                        response_queue.put({"status": "error", "message": str(e)})

                try:
                    self.schedule_message(0, main_thread_task)
                except AssertionError:
                    main_thread_task()

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
            else:
                # Fallback: execute directly
                response["result"] = handler(params)

        except Exception as e:
            self.log_message("Error processing command: " + str(e))
            self.log_message(traceback.format_exc())
            response["status"] = "error"
            response["message"] = str(e)

        return response

    # ------------------------------------------------------------------
    # Handler wrappers (extract params dict -> call implementation)
    # ------------------------------------------------------------------

    # -- Session / read-only -------------------------------------------

    def _get_session_info_handler(self, params):
        return self._get_session_info()

    def _get_track_info_handler(self, params):
        track_index = params.get("track_index", 0)
        return self._get_track_info(track_index)

    def _get_all_tracks_info_handler(self, params):
        return self._get_all_tracks_info()

    def _get_full_session_state_handler(self, params):
        return self._get_full_session_state()

    def _get_clip_notes_handler(self, params):
        track_index = params.get("track_index", 0)
        clip_index = params.get("clip_index", 0)
        return self._get_clip_notes(track_index, clip_index)

    def _get_playing_position_handler(self, params):
        return self._get_playing_position()

    def _get_scene_info_handler(self, params):
        scene_index = params.get("scene_index", 0)
        return self._get_scene_info(scene_index)

    def _get_all_scenes_handler(self, params):
        return self._get_all_scenes()

    def _get_device_parameters_handler(self, params):
        track_index = params.get("track_index", 0)
        device_index = params.get("device_index", 0)
        return self._get_device_parameters(track_index, device_index)

    def _get_device_info_handler(self, params):
        track_index = params.get("track_index", 0)
        device_index = params.get("device_index", 0)
        return self._get_device_info(track_index, device_index)

    # -- Browser read-only ---------------------------------------------

    def _get_browser_item_handler(self, params):
        uri = params.get("uri", None)
        path = params.get("path", None)
        return self._get_browser_item(uri, path)

    def _get_browser_categories_handler(self, params):
        category_type = params.get("category_type", "all")
        return self._get_browser_categories(category_type)

    def _get_browser_items_handler(self, params):
        path = params.get("path", "")
        item_type = params.get("item_type", "all")
        return self._get_browser_items(path, item_type)

    def _get_browser_tree_handler(self, params):
        category_type = params.get("category_type", "all")
        return self.get_browser_tree(category_type)

    def _get_browser_items_at_path_handler(self, params):
        path = params.get("path", "")
        return self.get_browser_items_at_path(path)

    def _search_browser_handler(self, params):
        query_str = params.get("query", "")
        category_type = params.get("category_type", "all")
        return self._search_browser(query_str, category_type)

    # -- Track management (write) --------------------------------------

    def _create_midi_track_handler(self, params):
        index = params.get("index", -1)
        return self._create_midi_track(index)

    def _create_audio_track_handler(self, params):
        index = params.get("index", -1)
        return self._create_audio_track(index)

    def _delete_track_handler(self, params):
        track_index = params.get("track_index", 0)
        return self._delete_track(track_index)

    def _duplicate_track_handler(self, params):
        track_index = params.get("track_index", 0)
        return self._duplicate_track(track_index)

    def _set_track_name_handler(self, params):
        track_index = params.get("track_index", 0)
        name = params.get("name", "")
        return self._set_track_name(track_index, name)

    def _set_track_volume_handler(self, params):
        track_index = params.get("track_index", 0)
        volume = params.get("volume", 0.85)
        return self._set_track_volume(track_index, volume)

    def _set_track_pan_handler(self, params):
        track_index = params.get("track_index", 0)
        pan = params.get("pan", 0.0)
        return self._set_track_pan(track_index, pan)

    def _set_track_mute_handler(self, params):
        track_index = params.get("track_index", 0)
        mute = params.get("mute", False)
        return self._set_track_mute(track_index, mute)

    def _set_track_solo_handler(self, params):
        track_index = params.get("track_index", 0)
        solo = params.get("solo", False)
        return self._set_track_solo(track_index, solo)

    def _set_track_arm_handler(self, params):
        track_index = params.get("track_index", 0)
        arm = params.get("arm", False)
        return self._set_track_arm(track_index, arm)

    def _set_track_send_handler(self, params):
        track_index = params.get("track_index", 0)
        send_index = params.get("send_index", 0)
        value = params.get("value", 0.0)
        return self._set_track_send(track_index, send_index, value)

    # -- Clip operations (write) ---------------------------------------

    def _create_clip_handler(self, params):
        track_index = params.get("track_index", 0)
        clip_index = params.get("clip_index", 0)
        length = params.get("length", 4.0)
        return self._create_clip(track_index, clip_index, length)

    def _add_notes_to_clip_handler(self, params):
        track_index = params.get("track_index", 0)
        clip_index = params.get("clip_index", 0)
        notes = params.get("notes", [])
        return self._add_notes_to_clip(track_index, clip_index, notes)

    def _set_clip_name_handler(self, params):
        track_index = params.get("track_index", 0)
        clip_index = params.get("clip_index", 0)
        name = params.get("name", "")
        return self._set_clip_name(track_index, clip_index, name)

    def _delete_clip_handler(self, params):
        track_index = params.get("track_index", 0)
        clip_index = params.get("clip_index", 0)
        return self._delete_clip(track_index, clip_index)

    def _duplicate_clip_to_slot_handler(self, params):
        track_index = params.get("track_index", 0)
        clip_index = params.get("clip_index", 0)
        target_track = params.get("target_track", 0)
        target_clip = params.get("target_clip", 0)
        return self._duplicate_clip_to_slot(track_index, clip_index, target_track, target_clip)

    def _remove_notes_from_clip_handler(self, params):
        track_index = params.get("track_index", 0)
        clip_index = params.get("clip_index", 0)
        from_time = params.get("from_time", 0.0)
        time_span = params.get("time_span", 4.0)
        from_pitch = params.get("from_pitch", 0)
        pitch_span = params.get("pitch_span", 128)
        return self._remove_notes_from_clip(track_index, clip_index, from_time, time_span, from_pitch, pitch_span)

    def _set_clip_loop_handler(self, params):
        track_index = params.get("track_index", 0)
        clip_index = params.get("clip_index", 0)
        looping = params.get("looping", True)
        loop_start = params.get("loop_start", None)
        loop_end = params.get("loop_end", None)
        return self._set_clip_loop(track_index, clip_index, looping, loop_start, loop_end)

    def _quantize_clip_handler(self, params):
        track_index = params.get("track_index", 0)
        clip_index = params.get("clip_index", 0)
        quantization = params.get("quantization", 4)
        amount = params.get("amount", 1.0)
        return self._quantize_clip(track_index, clip_index, quantization, amount)

    def _fire_clip_handler(self, params):
        track_index = params.get("track_index", 0)
        clip_index = params.get("clip_index", 0)
        return self._fire_clip(track_index, clip_index)

    def _stop_clip_handler(self, params):
        track_index = params.get("track_index", 0)
        clip_index = params.get("clip_index", 0)
        return self._stop_clip(track_index, clip_index)

    # -- Scene management (write) --------------------------------------

    def _create_scene_handler(self, params):
        index = params.get("index", -1)
        return self._create_scene(index)

    def _delete_scene_handler(self, params):
        scene_index = params.get("scene_index", 0)
        return self._delete_scene(scene_index)

    def _duplicate_scene_handler(self, params):
        scene_index = params.get("scene_index", 0)
        return self._duplicate_scene(scene_index)

    def _fire_scene_handler(self, params):
        scene_index = params.get("scene_index", 0)
        return self._fire_scene(scene_index)

    def _set_scene_name_handler(self, params):
        scene_index = params.get("scene_index", 0)
        name = params.get("name", "")
        return self._set_scene_name(scene_index, name)

    def _stop_all_clips_handler(self, params):
        return self._stop_all_clips()

    # -- Device parameters (write) -------------------------------------

    def _set_device_parameter_handler(self, params):
        track_index = params.get("track_index", 0)
        device_index = params.get("device_index", 0)
        parameter_index = params.get("parameter_index", 0)
        value = params.get("value", 0.0)
        return self._set_device_parameter(track_index, device_index, parameter_index, value)

    def _set_device_parameter_by_name_handler(self, params):
        track_index = params.get("track_index", 0)
        device_index = params.get("device_index", 0)
        parameter_name = params.get("parameter_name", "")
        value = params.get("value", 0.0)
        return self._set_device_parameter_by_name(track_index, device_index, parameter_name, value)

    def _toggle_device_handler(self, params):
        track_index = params.get("track_index", 0)
        device_index = params.get("device_index", 0)
        return self._toggle_device(track_index, device_index)

    def _delete_device_handler(self, params):
        track_index = params.get("track_index", 0)
        device_index = params.get("device_index", 0)
        return self._delete_device(track_index, device_index)

    # -- Transport / global (write) ------------------------------------

    def _set_tempo_handler(self, params):
        tempo = params.get("tempo", 120.0)
        return self._set_tempo(tempo)

    def _start_playback_handler(self, params):
        return self._start_playback()

    def _stop_playback_handler(self, params):
        return self._stop_playback()

    def _undo_handler(self, params):
        return self._undo()

    def _redo_handler(self, params):
        return self._redo()

    def _set_metronome_handler(self, params):
        enabled = params.get("enabled", False)
        return self._set_metronome(enabled)

    def _set_loop_handler(self, params):
        enabled = params.get("enabled", False)
        start = params.get("start", None)
        length = params.get("length", None)
        return self._set_loop(enabled, start, length)

    def _set_time_signature_handler(self, params):
        numerator = params.get("numerator", 4)
        denominator = params.get("denominator", 4)
        return self._set_time_signature(numerator, denominator)

    def _capture_midi_handler(self, params):
        return self._capture_midi()

    def _tap_tempo_handler(self, params):
        return self._tap_tempo()

    def _set_arrangement_position_handler(self, params):
        position = params.get("position", 0.0)
        return self._set_arrangement_position(position)

    def _set_record_handler(self, params):
        enabled = params.get("enabled", False)
        return self._set_record(enabled)

    # -- Browser load (write) ------------------------------------------

    def _load_browser_item_handler(self, params):
        track_index = params.get("track_index", 0)
        item_uri = params.get("item_uri", "")
        return self._load_browser_item(track_index, item_uri)

    def _load_instrument_or_effect_handler(self, params):
        track_index = params.get("track_index", 0)
        uri = params.get("uri", "")
        return self._load_instrument_or_effect(track_index, uri)

    # ==================================================================
    # Command implementations
    # ==================================================================

    # -- Session -------------------------------------------------------

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

    def _get_all_tracks_info(self):
        """Get summary information about all tracks in one call"""
        try:
            tracks = []
            for i, track in enumerate(self._song.tracks):
                try:
                    track_info = {
                        "index": i,
                        "name": track.name,
                        "is_midi": track.has_midi_input,
                        "is_audio": track.has_audio_input,
                        "mute": track.mute,
                        "solo": track.solo,
                        "arm": track.arm,
                        "volume": track.mixer_device.volume.value,
                        "panning": track.mixer_device.panning.value,
                        "clip_count": sum(1 for slot in track.clip_slots if slot.has_clip),
                        "device_count": len(track.devices)
                    }
                    tracks.append(track_info)
                except Exception as e:
                    self.log_message("Error getting track {0} info: {1}".format(i, str(e)))
                    tracks.append({"index": i, "error": str(e)})
            return {"tracks": tracks, "count": len(tracks)}
        except Exception as e:
            self.log_message("Error getting all tracks info: " + str(e))
            raise

    def _get_full_session_state(self):
        """Get the complete session state in one call.

        Returns tempo, time signature, all tracks with clips/devices,
        all scenes, return tracks, and master track info.
        """
        try:
            result = {
                "tempo": self._song.tempo,
                "signature_numerator": self._song.signature_numerator,
                "signature_denominator": self._song.signature_denominator,
                "is_playing": self._song.is_playing,
                "tracks": [],
                "return_tracks": [],
                "scenes": [],
                "master_track": {}
            }

            # Regular tracks
            for i, track in enumerate(self._song.tracks):
                try:
                    track_info = {
                        "index": i,
                        "name": track.name,
                        "is_midi": track.has_midi_input,
                        "is_audio": track.has_audio_input,
                        "mute": track.mute,
                        "solo": track.solo,
                        "arm": track.arm,
                        "volume": track.mixer_device.volume.value,
                        "panning": track.mixer_device.panning.value,
                        "devices": [],
                        "clips": []
                    }

                    # Devices
                    for d in track.devices:
                        try:
                            track_info["devices"].append({
                                "name": d.name,
                                "class": d.class_name
                            })
                        except Exception:
                            track_info["devices"].append({"name": "unknown", "class": "unknown"})

                    # Clips
                    for j, slot in enumerate(track.clip_slots):
                        try:
                            if slot.has_clip:
                                track_info["clips"].append({
                                    "index": j,
                                    "name": slot.clip.name,
                                    "length": slot.clip.length,
                                    "is_playing": slot.clip.is_playing
                                })
                        except Exception:
                            pass

                    result["tracks"].append(track_info)
                except Exception as e:
                    self.log_message("Error reading track {0}: {1}".format(i, str(e)))
                    result["tracks"].append({"index": i, "error": str(e)})

            # Scenes
            for i, scene in enumerate(self._song.scenes):
                try:
                    result["scenes"].append({
                        "index": i,
                        "name": scene.name
                    })
                except Exception:
                    result["scenes"].append({"index": i, "name": ""})

            # Return tracks
            for i, track in enumerate(self._song.return_tracks):
                try:
                    result["return_tracks"].append({
                        "index": i,
                        "name": track.name,
                        "volume": track.mixer_device.volume.value,
                        "panning": track.mixer_device.panning.value,
                        "devices": [{"name": d.name} for d in track.devices]
                    })
                except Exception as e:
                    self.log_message("Error reading return track {0}: {1}".format(i, str(e)))
                    result["return_tracks"].append({"index": i, "error": str(e)})

            # Master track
            try:
                result["master_track"] = {
                    "volume": self._song.master_track.mixer_device.volume.value,
                    "panning": self._song.master_track.mixer_device.panning.value
                }
            except Exception as e:
                self.log_message("Error reading master track: " + str(e))
                result["master_track"] = {"error": str(e)}

            return result
        except Exception as e:
            self.log_message("Error getting full session state: " + str(e))
            raise

    def _get_playing_position(self):
        """Get the current playing position with bar/beat calculation"""
        try:
            current_time = self._song.current_song_time
            tempo = self._song.tempo
            numerator = self._song.signature_numerator
            denominator = self._song.signature_denominator

            # Calculate bar and beat from current_song_time (in beats)
            beats_per_bar = numerator * (4.0 / denominator)
            bar = int(current_time / beats_per_bar) + 1
            beat = (current_time % beats_per_bar) + 1.0

            return {
                "current_song_time": current_time,
                "tempo": tempo,
                "signature_numerator": numerator,
                "signature_denominator": denominator,
                "bar": bar,
                "beat": beat,
                "is_playing": self._song.is_playing
            }
        except Exception as e:
            self.log_message("Error getting playing position: " + str(e))
            raise

    # -- Track info ----------------------------------------------------

    def _get_track_info(self, track_index):
        """Get information about a track"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]

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

    # -- Track management (write) --------------------------------------

    def _create_midi_track(self, index):
        """Create a new MIDI track at the specified index"""
        try:
            self._song.create_midi_track(index)
            new_track_index = len(self._song.tracks) - 1 if index == -1 else index
            new_track = self._song.tracks[new_track_index]
            return {
                "index": new_track_index,
                "name": new_track.name
            }
        except Exception as e:
            self.log_message("Error creating MIDI track: " + str(e))
            raise

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

    def _delete_track(self, track_index):
        """Delete a track"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            self._song.delete_track(track_index)
            return {"deleted": True, "track_index": track_index}
        except Exception as e:
            self.log_message("Error deleting track: " + str(e))
            raise

    def _duplicate_track(self, track_index):
        """Duplicate a track"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            self._song.duplicate_track(track_index)
            new_index = track_index + 1
            return {
                "duplicated": True,
                "source_index": track_index,
                "new_index": new_index,
                "name": self._song.tracks[new_index].name
            }
        except Exception as e:
            self.log_message("Error duplicating track: " + str(e))
            raise

    def _set_track_name(self, track_index, name):
        """Set the name of a track"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            track = self._song.tracks[track_index]
            track.name = name
            return {"name": track.name}
        except Exception as e:
            self.log_message("Error setting track name: " + str(e))
            raise

    def _set_track_volume(self, track_index, volume):
        """Set the volume of a track"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            track = self._song.tracks[track_index]
            track.mixer_device.volume.value = volume
            return {"volume": track.mixer_device.volume.value}
        except Exception as e:
            self.log_message("Error setting track volume: " + str(e))
            raise

    def _set_track_pan(self, track_index, pan):
        """Set the panning of a track"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            track = self._song.tracks[track_index]
            track.mixer_device.panning.value = pan
            return {"panning": track.mixer_device.panning.value}
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
            return {"mute": track.mute}
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
            return {"solo": track.solo}
        except Exception as e:
            self.log_message("Error setting track solo: " + str(e))
            raise

    def _set_track_arm(self, track_index, arm):
        """Set the arm state of a track"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            track = self._song.tracks[track_index]
            track.arm = arm
            return {"arm": track.arm}
        except Exception as e:
            self.log_message("Error setting track arm: " + str(e))
            raise

    def _set_track_send(self, track_index, send_index, value):
        """Set a send value on a track"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            track = self._song.tracks[track_index]
            sends = track.mixer_device.sends
            if send_index < 0 or send_index >= len(sends):
                raise IndexError("Send index out of range")
            sends[send_index].value = value
            return {"send_index": send_index, "value": sends[send_index].value}
        except Exception as e:
            self.log_message("Error setting track send: " + str(e))
            raise

    # -- Clip operations -----------------------------------------------

    def _create_clip(self, track_index, clip_index, length):
        """Create a new MIDI clip in the specified track and clip slot"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            track = self._song.tracks[track_index]
            if clip_index < 0 or clip_index >= len(track.clip_slots):
                raise IndexError("Clip index out of range")
            clip_slot = track.clip_slots[clip_index]
            if clip_slot.has_clip:
                raise Exception("Clip slot already has a clip")
            clip_slot.create_clip(length)
            return {
                "name": clip_slot.clip.name,
                "length": clip_slot.clip.length
            }
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

            live_notes = []
            for note in notes:
                pitch = note.get("pitch", 60)
                start_time = note.get("start_time", 0.0)
                duration = note.get("duration", 0.25)
                velocity = note.get("velocity", 100)
                mute = note.get("mute", False)
                live_notes.append((pitch, start_time, duration, velocity, mute))

            clip.set_notes(tuple(live_notes))
            return {"note_count": len(notes)}
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
            clip_slot.clip.name = name
            return {"name": clip_slot.clip.name}
        except Exception as e:
            self.log_message("Error setting clip name: " + str(e))
            raise

    def _delete_clip(self, track_index, clip_index):
        """Delete a clip from a slot"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            track = self._song.tracks[track_index]
            if clip_index < 0 or clip_index >= len(track.clip_slots):
                raise IndexError("Clip index out of range")
            clip_slot = track.clip_slots[clip_index]
            if not clip_slot.has_clip:
                raise Exception("No clip in slot")
            clip_slot.delete_clip()
            return {"deleted": True, "track_index": track_index, "clip_index": clip_index}
        except Exception as e:
            self.log_message("Error deleting clip: " + str(e))
            raise

    def _duplicate_clip_to_slot(self, track_index, clip_index, target_track, target_clip):
        """Duplicate a clip to a target slot by reading notes and recreating"""
        try:
            # Validate source
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Source track index out of range")
            src_track = self._song.tracks[track_index]
            if clip_index < 0 or clip_index >= len(src_track.clip_slots):
                raise IndexError("Source clip index out of range")
            src_slot = src_track.clip_slots[clip_index]
            if not src_slot.has_clip:
                raise Exception("No clip in source slot")
            src_clip = src_slot.clip

            # Validate target
            if target_track < 0 or target_track >= len(self._song.tracks):
                raise IndexError("Target track index out of range")
            tgt_track = self._song.tracks[target_track]
            if target_clip < 0 or target_clip >= len(tgt_track.clip_slots):
                raise IndexError("Target clip index out of range")
            tgt_slot = tgt_track.clip_slots[target_clip]
            if tgt_slot.has_clip:
                raise Exception("Target clip slot already has a clip")

            # Read source clip properties
            clip_length = src_clip.length
            clip_name = src_clip.name

            # Read notes from source clip
            # get_notes(from_time, from_pitch, time_span, pitch_span)
            notes_tuple = src_clip.get_notes(0, 0, clip_length, 128)

            # Create clip at target
            tgt_slot.create_clip(clip_length)
            tgt_clip = tgt_slot.clip
            tgt_clip.name = clip_name

            # Write notes to target clip
            if notes_tuple and len(notes_tuple) > 0:
                tgt_clip.set_notes(tuple(notes_tuple))

            return {
                "duplicated": True,
                "source": {"track": track_index, "clip": clip_index},
                "target": {"track": target_track, "clip": target_clip},
                "note_count": len(notes_tuple) if notes_tuple else 0,
                "name": tgt_clip.name
            }
        except Exception as e:
            self.log_message("Error duplicating clip to slot: " + str(e))
            raise

    def _get_clip_notes(self, track_index, clip_index):
        """Get notes from a clip"""
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

            # get_notes returns a tuple of tuples:
            # ((pitch, time, duration, velocity, mute), ...)
            # Signature: get_notes(from_time, from_pitch, time_span, pitch_span)
            notes_tuple = clip.get_notes(0, 0, clip.length, 128)

            notes = []
            for note in notes_tuple:
                notes.append({
                    "pitch": note[0],
                    "start_time": note[1],
                    "duration": note[2],
                    "velocity": note[3],
                    "mute": note[4]
                })

            return {
                "clip_name": clip.name,
                "clip_length": clip.length,
                "notes": notes,
                "note_count": len(notes)
            }
        except Exception as e:
            self.log_message("Error getting clip notes: " + str(e))
            raise

    def _remove_notes_from_clip(self, track_index, clip_index, from_time, time_span, from_pitch, pitch_span):
        """Remove notes from a clip within the specified range"""
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
            # remove_notes signature: (from_time, from_pitch, time_span, pitch_span)
            clip.remove_notes(from_time, from_pitch, time_span, pitch_span)
            return {
                "removed": True,
                "from_time": from_time,
                "time_span": time_span,
                "from_pitch": from_pitch,
                "pitch_span": pitch_span
            }
        except Exception as e:
            self.log_message("Error removing notes from clip: " + str(e))
            raise

    def _set_clip_loop(self, track_index, clip_index, looping, loop_start, loop_end):
        """Set clip loop properties"""
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
            if loop_start is not None:
                clip.loop_start = loop_start
            if loop_end is not None:
                clip.loop_end = loop_end
            return {
                "looping": clip.looping,
                "loop_start": clip.loop_start,
                "loop_end": clip.loop_end
            }
        except Exception as e:
            self.log_message("Error setting clip loop: " + str(e))
            raise

    def _quantize_clip(self, track_index, clip_index, quantization, amount):
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
            clip.quantize(quantization, amount)
            return {"quantized": True, "quantization": quantization, "amount": amount}
        except Exception as e:
            self.log_message("Error quantizing clip: " + str(e))
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
            return {"fired": True}
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
            return {"stopped": True}
        except Exception as e:
            self.log_message("Error stopping clip: " + str(e))
            raise

    # -- Scene management ----------------------------------------------

    def _get_scene_info(self, scene_index):
        """Get information about a specific scene"""
        try:
            scenes = self._song.scenes
            if scene_index < 0 or scene_index >= len(scenes):
                raise IndexError("Scene index out of range")
            scene = scenes[scene_index]
            clip_count = 0
            for track in self._song.tracks:
                try:
                    if scene_index < len(track.clip_slots) and track.clip_slots[scene_index].has_clip:
                        clip_count += 1
                except Exception:
                    pass
            result = {
                "index": scene_index,
                "name": scene.name,
                "clip_count": clip_count
            }
            try:
                result["tempo"] = scene.tempo
            except Exception:
                pass
            return result
        except Exception as e:
            self.log_message("Error getting scene info: " + str(e))
            raise

    def _get_all_scenes(self):
        """Get information about all scenes"""
        try:
            scenes_info = []
            for i, scene in enumerate(self._song.scenes):
                try:
                    clip_count = 0
                    for track in self._song.tracks:
                        try:
                            if i < len(track.clip_slots) and track.clip_slots[i].has_clip:
                                clip_count += 1
                        except Exception:
                            pass
                    scene_data = {
                        "index": i,
                        "name": scene.name,
                        "clip_count": clip_count
                    }
                    try:
                        scene_data["tempo"] = scene.tempo
                    except Exception:
                        pass
                    scenes_info.append(scene_data)
                except Exception as e:
                    self.log_message("Error reading scene {0}: {1}".format(i, str(e)))
                    scenes_info.append({"index": i, "error": str(e)})
            return {"scenes": scenes_info, "count": len(scenes_info)}
        except Exception as e:
            self.log_message("Error getting all scenes: " + str(e))
            raise

    def _create_scene(self, index):
        """Create a new scene at the specified index"""
        try:
            self._song.create_scene(index)
            new_index = len(self._song.scenes) - 1 if index == -1 else index
            return {
                "index": new_index,
                "name": self._song.scenes[new_index].name
            }
        except Exception as e:
            self.log_message("Error creating scene: " + str(e))
            raise

    def _delete_scene(self, scene_index):
        """Delete a scene"""
        try:
            if scene_index < 0 or scene_index >= len(self._song.scenes):
                raise IndexError("Scene index out of range")
            self._song.delete_scene(scene_index)
            return {"deleted": True, "scene_index": scene_index}
        except Exception as e:
            self.log_message("Error deleting scene: " + str(e))
            raise

    def _duplicate_scene(self, scene_index):
        """Duplicate a scene"""
        try:
            if scene_index < 0 or scene_index >= len(self._song.scenes):
                raise IndexError("Scene index out of range")
            self._song.duplicate_scene(scene_index)
            return {
                "duplicated": True,
                "source_index": scene_index,
                "new_index": scene_index + 1
            }
        except Exception as e:
            self.log_message("Error duplicating scene: " + str(e))
            raise

    def _fire_scene(self, scene_index):
        """Fire a scene"""
        try:
            if scene_index < 0 or scene_index >= len(self._song.scenes):
                raise IndexError("Scene index out of range")
            self._song.scenes[scene_index].fire()
            return {"fired": True, "scene_index": scene_index}
        except Exception as e:
            self.log_message("Error firing scene: " + str(e))
            raise

    def _set_scene_name(self, scene_index, name):
        """Set the name of a scene"""
        try:
            if scene_index < 0 or scene_index >= len(self._song.scenes):
                raise IndexError("Scene index out of range")
            self._song.scenes[scene_index].name = name
            return {"name": self._song.scenes[scene_index].name}
        except Exception as e:
            self.log_message("Error setting scene name: " + str(e))
            raise

    def _stop_all_clips(self):
        """Stop all clips"""
        try:
            self._song.stop_all_clips()
            return {"stopped": True}
        except Exception as e:
            self.log_message("Error stopping all clips: " + str(e))
            raise

    # -- Device parameters ---------------------------------------------

    def _get_device_parameters(self, track_index, device_index):
        """Get parameters of a device"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            track = self._song.tracks[track_index]
            if device_index < 0 or device_index >= len(track.devices):
                raise IndexError("Device index out of range")
            device = track.devices[device_index]

            parameters = []
            for param in device.parameters:
                try:
                    parameters.append({
                        "name": param.name,
                        "value": param.value,
                        "min": param.min,
                        "max": param.max,
                        "is_quantized": param.is_quantized
                    })
                except Exception as e:
                    self.log_message("Error reading parameter: " + str(e))
                    parameters.append({"name": "unknown", "error": str(e)})

            return {
                "device_name": device.name,
                "parameters": parameters,
                "parameter_count": len(parameters)
            }
        except Exception as e:
            self.log_message("Error getting device parameters: " + str(e))
            raise

    def _get_device_info(self, track_index, device_index):
        """Get information about a device"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            track = self._song.tracks[track_index]
            if device_index < 0 or device_index >= len(track.devices):
                raise IndexError("Device index out of range")
            device = track.devices[device_index]

            result = {
                "name": device.name,
                "class_name": device.class_name,
                "type": self._get_device_type(device),
                "parameter_count": len(device.parameters)
            }
            try:
                result["is_enabled"] = device.is_enabled
            except Exception:
                pass
            return result
        except Exception as e:
            self.log_message("Error getting device info: " + str(e))
            raise

    def _set_device_parameter(self, track_index, device_index, parameter_index, value):
        """Set a device parameter by index"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            track = self._song.tracks[track_index]
            if device_index < 0 or device_index >= len(track.devices):
                raise IndexError("Device index out of range")
            device = track.devices[device_index]
            if parameter_index < 0 or parameter_index >= len(device.parameters):
                raise IndexError("Parameter index out of range")
            param = device.parameters[parameter_index]
            param.value = value
            return {
                "name": param.name,
                "value": param.value
            }
        except Exception as e:
            self.log_message("Error setting device parameter: " + str(e))
            raise

    def _set_device_parameter_by_name(self, track_index, device_index, parameter_name, value):
        """Set a device parameter by name"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            track = self._song.tracks[track_index]
            if device_index < 0 or device_index >= len(track.devices):
                raise IndexError("Device index out of range")
            device = track.devices[device_index]

            target_param = None
            for param in device.parameters:
                if param.name == parameter_name:
                    target_param = param
                    break

            if target_param is None:
                raise ValueError("Parameter '{0}' not found on device '{1}'".format(parameter_name, device.name))

            target_param.value = value
            return {
                "name": target_param.name,
                "value": target_param.value
            }
        except Exception as e:
            self.log_message("Error setting device parameter by name: " + str(e))
            raise

    def _toggle_device(self, track_index, device_index):
        """Toggle a device on/off"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            track = self._song.tracks[track_index]
            if device_index < 0 or device_index >= len(track.devices):
                raise IndexError("Device index out of range")
            device = track.devices[device_index]

            if hasattr(device, 'is_enabled'):
                device.is_enabled = not device.is_enabled
                return {"is_enabled": device.is_enabled, "name": device.name}
            else:
                raise AttributeError("Device does not support enable/disable toggling")
        except Exception as e:
            self.log_message("Error toggling device: " + str(e))
            raise

    def _delete_device(self, track_index, device_index):
        """Delete a device from a track"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            track = self._song.tracks[track_index]
            if device_index < 0 or device_index >= len(track.devices):
                raise IndexError("Device index out of range")
            track.delete_device(device_index)
            return {"deleted": True, "track_index": track_index, "device_index": device_index}
        except Exception as e:
            self.log_message("Error deleting device: " + str(e))
            raise

    # -- Transport / global --------------------------------------------

    def _set_tempo(self, tempo):
        """Set the tempo of the session"""
        try:
            self._song.tempo = tempo
            return {"tempo": self._song.tempo}
        except Exception as e:
            self.log_message("Error setting tempo: " + str(e))
            raise

    def _start_playback(self):
        """Start playing the session"""
        try:
            self._song.start_playing()
            return {"playing": self._song.is_playing}
        except Exception as e:
            self.log_message("Error starting playback: " + str(e))
            raise

    def _stop_playback(self):
        """Stop playing the session"""
        try:
            self._song.stop_playing()
            return {"playing": self._song.is_playing}
        except Exception as e:
            self.log_message("Error stopping playback: " + str(e))
            raise

    def _undo(self):
        """Undo the last action"""
        try:
            self._song.undo()
            return {"undone": True}
        except Exception as e:
            self.log_message("Error performing undo: " + str(e))
            raise

    def _redo(self):
        """Redo the last undone action"""
        try:
            self._song.redo()
            return {"redone": True}
        except Exception as e:
            self.log_message("Error performing redo: " + str(e))
            raise

    def _set_metronome(self, enabled):
        """Set the metronome on or off"""
        try:
            self._song.metronome = enabled
            return {"metronome": self._song.metronome}
        except Exception as e:
            self.log_message("Error setting metronome: " + str(e))
            raise

    def _set_loop(self, enabled, start, length):
        """Set the loop state and optionally start/length"""
        try:
            self._song.loop = enabled
            if start is not None:
                self._song.loop_start = start
            if length is not None:
                self._song.loop_length = length
            return {
                "loop": self._song.loop,
                "loop_start": self._song.loop_start,
                "loop_length": self._song.loop_length
            }
        except Exception as e:
            self.log_message("Error setting loop: " + str(e))
            raise

    def _set_time_signature(self, numerator, denominator):
        """Set the time signature"""
        try:
            self._song.signature_numerator = numerator
            self._song.signature_denominator = denominator
            return {
                "signature_numerator": self._song.signature_numerator,
                "signature_denominator": self._song.signature_denominator
            }
        except Exception as e:
            self.log_message("Error setting time signature: " + str(e))
            raise

    def _capture_midi(self):
        """Capture MIDI (available in Live 10+)"""
        try:
            self._song.capture_midi()
            return {"captured": True}
        except AttributeError:
            return {"captured": False, "message": "capture_midi not available in this Live version"}
        except Exception as e:
            self.log_message("Error capturing MIDI: " + str(e))
            raise

    def _tap_tempo(self):
        """Tap tempo"""
        try:
            self._song.tap_tempo()
            return {"tempo": self._song.tempo}
        except Exception as e:
            self.log_message("Error tapping tempo: " + str(e))
            raise

    def _set_arrangement_position(self, position):
        """Set the arrangement playback position"""
        try:
            self._song.current_song_time = position
            return {"current_song_time": self._song.current_song_time}
        except Exception as e:
            self.log_message("Error setting arrangement position: " + str(e))
            raise

    def _set_record(self, enabled):
        """Set the record mode"""
        try:
            self._song.record_mode = enabled
            return {"record_mode": self._song.record_mode}
        except Exception as e:
            self.log_message("Error setting record mode: " + str(e))
            raise

    # -- Browser -------------------------------------------------------

    def _get_browser_item(self, uri, path):
        """Get a browser item by URI or path"""
        try:
            app = self.application()
            if not app:
                raise RuntimeError("Could not access Live application")

            result = {
                "uri": uri,
                "path": path,
                "found": False
            }

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

            if path:
                path_parts = path.split("/")

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
                    current_item = app.browser.instruments
                    path_parts = ["instruments"] + path_parts

                for i in range(1, len(path_parts)):
                    part = path_parts[i]
                    if not part:
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

    def _get_browser_categories(self, category_type):
        """Get browser categories"""
        try:
            app = self.application()
            if not app:
                raise RuntimeError("Could not access Live application")
            browser = app.browser

            categories = []
            category_map = {
                "instruments": ("Instruments", "instruments"),
                "sounds": ("Sounds", "sounds"),
                "drums": ("Drums", "drums"),
                "audio_effects": ("Audio Effects", "audio_effects"),
                "midi_effects": ("MIDI Effects", "midi_effects"),
            }

            for key, (display_name, attr_name) in category_map.items():
                if category_type == "all" or category_type == key:
                    if hasattr(browser, attr_name):
                        try:
                            item = getattr(browser, attr_name)
                            categories.append({
                                "name": display_name,
                                "key": key,
                                "has_children": hasattr(item, 'children') and bool(item.children)
                            })
                        except Exception:
                            pass

            return {"categories": categories}
        except Exception as e:
            self.log_message("Error getting browser categories: " + str(e))
            raise

    def _get_browser_items(self, path, item_type):
        """Get browser items at a given path"""
        try:
            return self.get_browser_items_at_path(path)
        except Exception as e:
            self.log_message("Error getting browser items: " + str(e))
            raise

    def _load_browser_item(self, track_index, item_uri):
        """Load a browser item onto a track by its URI"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            track = self._song.tracks[track_index]

            app = self.application()
            item = self._find_browser_item_by_uri(app.browser, item_uri)
            if not item:
                raise ValueError("Browser item with URI '{0}' not found".format(item_uri))

            self._song.view.selected_track = track
            app.browser.load_item(item)

            return {
                "loaded": True,
                "item_name": item.name,
                "track_name": track.name,
                "uri": item_uri
            }
        except Exception as e:
            self.log_message("Error loading browser item: {0}".format(str(e)))
            self.log_message(traceback.format_exc())
            raise

    def _load_instrument_or_effect(self, track_index, uri):
        """Load an instrument or effect onto a track by URI"""
        try:
            return self._load_browser_item(track_index, uri)
        except Exception as e:
            self.log_message("Error loading instrument or effect: {0}".format(str(e)))
            raise

    def _find_browser_item_by_uri(self, browser_or_item, uri, max_depth=10, current_depth=0):
        """Recursively find a browser item by its URI"""
        try:
            if hasattr(browser_or_item, 'uri') and browser_or_item.uri == uri:
                return browser_or_item

            if current_depth >= max_depth:
                return None

            if hasattr(browser_or_item, 'instruments'):
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

            if hasattr(browser_or_item, 'children') and browser_or_item.children:
                for child in browser_or_item.children:
                    item = self._find_browser_item_by_uri(child, uri, max_depth, current_depth + 1)
                    if item:
                        return item

            return None
        except Exception as e:
            self.log_message("Error finding browser item by URI: {0}".format(str(e)))
            return None

    def _search_browser(self, query, category_type="all"):
        """Search through browser items matching a query string.

        Walks the browser tree and collects items whose name contains the
        query (case-insensitive). Limits depth and result count for
        performance.
        """
        try:
            app = self.application()
            if not app:
                raise RuntimeError("Could not access Live application")
            browser = app.browser

            query_lower = query.lower()
            results = []
            max_results = 50
            max_depth = 6

            def walk(item, path, depth):
                if depth > max_depth or len(results) >= max_results:
                    return
                try:
                    name = item.name if hasattr(item, 'name') else ""
                    if query_lower in name.lower():
                        entry = {
                            "name": name,
                            "path": path,
                            "is_folder": hasattr(item, 'children') and bool(item.children),
                            "is_device": hasattr(item, 'is_device') and item.is_device,
                            "is_loadable": hasattr(item, 'is_loadable') and item.is_loadable,
                        }
                        if hasattr(item, 'uri'):
                            entry["uri"] = item.uri
                        results.append(entry)
                    if hasattr(item, 'children') and item.children:
                        child_path = path + "/" + name if path else name
                        for child in item.children:
                            if len(results) >= max_results:
                                break
                            walk(child, child_path, depth + 1)
                except Exception as e:
                    self.log_message("Error walking browser item: {0}".format(str(e)))

            category_map = {
                "instruments": "instruments",
                "sounds": "sounds",
                "drums": "drums",
                "audio_effects": "audio_effects",
                "midi_effects": "midi_effects",
            }

            if category_type == "all":
                categories_to_search = list(category_map.keys())
            else:
                categories_to_search = [category_type] if category_type in category_map else list(category_map.keys())

            for cat_key in categories_to_search:
                attr_name = category_map[cat_key]
                if hasattr(browser, attr_name):
                    try:
                        root = getattr(browser, attr_name)
                        walk(root, cat_key, 0)
                    except Exception as e:
                        self.log_message("Error searching category {0}: {1}".format(cat_key, str(e)))
                if len(results) >= max_results:
                    break

            return {
                "query": query,
                "category_type": category_type,
                "results": results,
                "result_count": len(results),
                "truncated": len(results) >= max_results
            }
        except Exception as e:
            self.log_message("Error searching browser: " + str(e))
            raise

    def get_browser_tree(self, category_type="all"):
        """Get a simplified tree of browser categories."""
        try:
            app = self.application()
            if not app:
                raise RuntimeError("Could not access Live application")

            if not hasattr(app, 'browser') or app.browser is None:
                raise RuntimeError("Browser is not available in the Live application")

            browser_attrs = [attr for attr in dir(app.browser) if not attr.startswith('_')]
            self.log_message("Available browser attributes: {0}".format(browser_attrs))

            result = {
                "type": category_type,
                "categories": [],
                "available_categories": browser_attrs
            }

            def process_item(item, depth=0):
                if not item:
                    return None
                return {
                    "name": item.name if hasattr(item, 'name') else "Unknown",
                    "is_folder": hasattr(item, 'children') and bool(item.children),
                    "is_device": hasattr(item, 'is_device') and item.is_device,
                    "is_loadable": hasattr(item, 'is_loadable') and item.is_loadable,
                    "uri": item.uri if hasattr(item, 'uri') else None,
                    "children": []
                }

            standard_categories = [
                ("instruments", "Instruments"),
                ("sounds", "Sounds"),
                ("drums", "Drums"),
                ("audio_effects", "Audio Effects"),
                ("midi_effects", "MIDI Effects"),
            ]

            for attr_name, display_name in standard_categories:
                if (category_type == "all" or category_type == attr_name) and hasattr(app.browser, attr_name):
                    try:
                        cat_item = process_item(getattr(app.browser, attr_name))
                        if cat_item:
                            cat_item["name"] = display_name
                            result["categories"].append(cat_item)
                    except Exception as e:
                        self.log_message("Error processing {0}: {1}".format(attr_name, str(e)))

            standard_names = {name for name, _ in standard_categories}
            for attr in browser_attrs:
                if attr not in standard_names and (category_type == "all" or category_type == attr):
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
        """Get browser items at a specific path.

        Path format: "category/folder/subfolder" where category is one of:
        instruments, sounds, drums, audio_effects, midi_effects, or any
        other available browser category.
        """
        try:
            app = self.application()
            if not app:
                raise RuntimeError("Could not access Live application")

            if not hasattr(app, 'browser') or app.browser is None:
                raise RuntimeError("Browser is not available in the Live application")

            browser_attrs = [attr for attr in dir(app.browser) if not attr.startswith('_')]
            self.log_message("Available browser attributes: {0}".format(browser_attrs))

            path_parts = path.split("/")
            if not path_parts:
                raise ValueError("Invalid path")

            root_category = path_parts[0].lower()
            current_item = None

            category_map = {
                "instruments": "instruments",
                "sounds": "sounds",
                "drums": "drums",
                "audio_effects": "audio_effects",
                "midi_effects": "midi_effects",
            }

            if root_category in category_map and hasattr(app.browser, category_map[root_category]):
                current_item = getattr(app.browser, category_map[root_category])
            else:
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
                    return {
                        "path": path,
                        "error": "Unknown or unavailable category: {0}".format(root_category),
                        "available_categories": browser_attrs,
                        "items": []
                    }

            for i in range(1, len(path_parts)):
                part = path_parts[i]
                if not part:
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

    # -- Helpers -------------------------------------------------------

    def _get_device_type(self, device):
        """Get the type of a device"""
        try:
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
