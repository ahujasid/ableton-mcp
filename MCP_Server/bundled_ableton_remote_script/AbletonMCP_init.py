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
# Loopback, not 0.0.0.0. This socket takes unauthenticated commands that import
# arbitrary absolute paths, load browser items and drive the transport, so
# anything that can reach the port controls the DAW. Binding every interface
# exposed that to the whole local network — and to any network the machine is
# routable from.
#
# Running Live and the MCP server on different machines is the one legitimate
# reason to widen this; set ABLETON_MCP_HOST to do so deliberately, and put it
# behind a trusted network or an explicit relay.
HOST = os.environ.get("ABLETON_MCP_HOST", "127.0.0.1")

# A command that never completes must not grow the buffer without bound.
# Generous enough for a large add_notes_to_clip payload.
MAX_REQUEST_BYTES = 16 * 1024 * 1024

# Bumped whenever the TCP command surface changes; the MCP server compares
# this to EXPECTED_REMOTE_SCRIPT_VERSION.
SCRIPT_VERSION = "1.9.1+studio"
PROTOCOL_VERSION = 1

SCRIPT_CAPABILITIES = [
    "get_session_info",
    "get_track_info",
    "get_script_info",
    "get_clip_notes",
    "get_device_parameters",
    "get_session_snapshot",
    "set_device_parameter",
    "drain_passive_events",
    "create_midi_track",
    "create_audio_track",
    "create_clip",
    "create_audio_clip",
    "add_notes_to_clip",
    "load_instrument_or_effect",
    "get_arrangement_clips",
    "duplicate_session_clip_to_arrangement",
    "create_locator",
    "delete_clip",
    "clear_notes_from_clip",
    # studio-upgrades fork
    "set_track_mixer",
    "get_drum_pads",
    "copy_clip",
    "fill_arrangement",
    "delete_arrangement_clips",
    "back_to_arrangement",
    "set_arrangement_loop",
    # studio-upgrades 1.9
    "add_device",
    "delete_device",
    "set_device_parameters",
    "set_sidechain",
    "write_clip_automation",
    "clear_clip_automation",
    "get_clip_automation",
    "get_groove_pool",
    "set_groove",
    "assign_groove",
    "set_groove_amount",
    "load_groove",
    "set_clip_properties",
    "get_song_scale",
    "set_song_scale",
    "create_return_track",
    "delete_track",
    "duplicate_track",
    "get_mixer_overview",
    "start_render",
    "get_render_status",
    "cancel_render",
    "track_type_addressing",
]

def create_instance(c_instance):
    """Create and return the AbletonMCP script instance"""
    return AbletonMCP(c_instance)

class AbletonMCP(ControlSurface):
    """AbletonMCP Remote Script for Ableton Live"""

    @property
    def _song(self):
        """The Song of the Set that is open now. Live swaps the Song object
        when a new Set is created or opened, so a reference cached at start-up
        goes stale ("did not match C++ signature"). Tests may pin a fake."""
        pinned = self.__dict__.get("_pinned_song")
        return pinned if pinned is not None else self.song()

    @_song.setter
    def _song(self, value):
        self.__dict__["_pinned_song"] = value
    
    def __init__(self, c_instance):
        """Initialize the control surface"""
        ControlSurface.__init__(self, c_instance)
        self.log_message(
            "AbletonMCP Remote Script initializing... (script v%s)"
            % SCRIPT_VERSION
        )
        
        # Socket server for communication
        self.server = None
        self.client_threads = []
        self.server_thread = None
        self.running = False
        
        # self._song is a property (below) so it always points at the open Set

        # Passive human-UI event queue (drained by MCP → Supabase)
        self._passive_events = []
        self._passive_lock = threading.Lock()
        self._passive_max = 500
        self._passive_track_count = None
        self._passive_track_bindings = []  # (track, [(add_name, callback), ...]) for cleanup
        self._song_passive_callbacks = []
        
        # Start the socket server
        self.start_server()

        # Register LOM listeners for passive capture (after song is ready)
        try:
            self._setup_passive_listeners()
        except Exception as e:
            self.log_message("Passive listener setup failed: " + str(e))
            self.log_message(traceback.format_exc())
        
        self.log_message("AbletonMCP initialized")
        
        # Show a message in Ableton
        self.show_message("AbletonMCP: Listening for commands on port " + str(DEFAULT_PORT))
    
    def disconnect(self):
        """Called when Ableton closes or the control surface is removed"""
        self.log_message("AbletonMCP disconnecting...")
        self.running = False

        try:
            self._teardown_passive_listeners()
        except Exception as e:
            self.log_message("Passive listener teardown error: " + str(e))
        
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
        # Accumulate raw bytes, never per-chunk text. A multi-byte UTF-8
        # character (an accented clip name, an emoji) can straddle two recv()
        # boundaries; decoding each chunk on its own raises there, and the old
        # code answered that with an error frame pushed into a stream the
        # client was still reading a real response from — desynchronising the
        # connection for good.
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

                    buffer += data

                    if len(buffer) > MAX_REQUEST_BYTES:
                        buffer = b''
                        raise ValueError(
                            "Request exceeded %d bytes without a complete JSON command"
                            % MAX_REQUEST_BYTES)

                    try:
                        # Only a fully received command decodes and parses.
                        # Either error means "not all here yet", so wait.
                        command = json.loads(buffer.decode('utf-8'))
                    except (ValueError, UnicodeDecodeError):
                        continue

                    buffer = b''  # Clear buffer after successful parse

                    self.log_message("Received command: " + str(command.get("type", "unknown")))

                    # Process the command and get response
                    response = self._process_command(command)

                    # Send the response with explicit encoding
                    client.sendall(json.dumps(response).encode('utf-8'))

                except Exception as e:
                    self.log_message("Error handling client data: " + str(e))
                    self.log_message(traceback.format_exc())

                    # Every error that reaches here leaves the request/response
                    # stream in an unknown state, so report it and close rather
                    # than carry on out of step with the client.
                    error_response = {
                        "status": "error",
                        "message": str(e)
                    }
                    try:
                        client.sendall(json.dumps(error_response).encode('utf-8'))
                    except Exception:
                        pass
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
            if command_type == "get_script_info":
                response["result"] = self._get_script_info()
            elif command_type == "get_session_info":
                response["result"] = self._get_session_info()
            elif command_type == "get_track_info":
                track_index = params.get("track_index", 0)
                response["result"] = self._get_track_info(track_index)
            # Commands that modify Live's state should be scheduled on the main thread
            elif command_type in ["create_midi_track", "create_audio_track", "set_track_name",
                                 "create_clip", "create_audio_clip", "add_notes_to_clip", "set_clip_name",
                                 "set_arrangement_clip_name",
                                 "delete_clip",
                                 "clear_notes_from_clip",
                                 "set_tempo", "fire_clip", "stop_clip",
                                 "start_playback", "stop_playback",
                                 "load_browser_item", "load_instrument_or_effect",
                                 # Arrangement view – must run on the main thread
                                 "switch_to_arrangement_view", "set_current_song_time",
                                 "duplicate_session_clip_to_arrangement",
                                 "map_rack_magnitude", "inspect_rack",
                                 # studio-upgrades fork
                                 "set_track_mixer", "copy_clip", "fill_arrangement",
                                 "delete_arrangement_clips", "back_to_arrangement",
                                 "set_arrangement_loop"]:
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
                        elif command_type == "clear_notes_from_clip":
                            track_index = params.get("track_index", 0)
                            clip_index = params.get("clip_index", 0)
                            result = self._clear_notes_from_clip(track_index, clip_index)
                        elif command_type == "set_clip_name":
                            track_index = params.get("track_index", 0)
                            clip_index = params.get("clip_index", 0)
                            name = params.get("name", "")
                            result = self._set_clip_name(track_index, clip_index, name)
                        elif command_type == "set_arrangement_clip_name":
                            track_index = params.get("track_index", 0)
                            clip_index = params.get("clip_index", 0)
                            name = params.get("name", "")
                            result = self._set_arrangement_clip_name(track_index, clip_index, name)
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
                        elif command_type == "delete_clip":
                            track_index = params.get("track_index", 0)
                            clip_index = params.get("clip_index", 0)
                            result = self._delete_clip(track_index, clip_index)
                        elif command_type == "start_playback":
                            result = self._start_playback()
                        elif command_type == "stop_playback":
                            result = self._stop_playback()
                        elif command_type == "load_instrument_or_effect":
                            track_index = params.get("track_index", 0)
                            uri = params.get("uri", "")
                            result = self._load_browser_item(
                                track_index, uri, params.get("track_type", "track"))
                        elif command_type == "load_browser_item":
                            track_index = params.get("track_index", 0)
                            item_uri = params.get("item_uri", "")
                            result = self._load_browser_item(
                                track_index, item_uri, params.get("track_type", "track"))
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
                        elif command_type == "map_rack_magnitude":
                            track_index = params.get("track_index", 0)
                            device_index = params.get("device_index", 0)
                            macro_name = params.get("macro_name", "Magnitude")
                            result = self._map_rack_magnitude(
                                track_index, device_index, macro_name)
                        elif command_type == "inspect_rack":
                            track_index = params.get("track_index", 0)
                            device_index = params.get("device_index", 0)
                            result = self._inspect_rack(track_index, device_index)
                        # ── studio-upgrades fork ───────────────────────────────────
                        elif command_type == "set_track_mixer":
                            result = self._set_track_mixer(
                                params.get("track_index", 0),
                                track_type=params.get("track_type", "track"),
                                volume=params.get("volume"),
                                volume_db=params.get("volume_db"),
                                panning=params.get("panning"),
                                mute=params.get("mute"),
                                solo=params.get("solo"),
                                sends=params.get("sends"),
                            )
                        elif command_type == "copy_clip":
                            result = self._copy_clip(
                                params.get("track_index", 0),
                                params.get("clip_index", 0),
                                params.get("target_track_index", params.get("track_index", 0)),
                                params.get("target_clip_index", 0),
                                overwrite=bool(params.get("overwrite", False)),
                                new_name=params.get("new_name"),
                            )
                        elif command_type == "fill_arrangement":
                            result = self._fill_arrangement(
                                params.get("track_index", 0),
                                params.get("clip_index", 0),
                                params.get("start_time", 0.0),
                                params.get("end_time", 0.0),
                                step=params.get("step"),
                            )
                        elif command_type == "delete_arrangement_clips":
                            result = self._delete_arrangement_clips(
                                params.get("track_index", 0),
                                params.get("start_time", 0.0),
                                params.get("end_time"),
                            )
                        elif command_type == "back_to_arrangement":
                            result = self._back_to_arrangement()
                        elif command_type == "set_arrangement_loop":
                            result = self._set_arrangement_loop(
                                params.get("start_time", 0.0),
                                params.get("length", 16.0),
                                params.get("enabled", True),
                            )

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
                
                # create_audio_clip decodes/imports the file on the main
                # thread and needs more than the default headroom.
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
            elif command_type == "create_locator":
                # Live only applies set_or_delete_cue() at the playhead, and
                # both the playhead move and the new cue become visible on a
                # later tick -- so this runs as a short scheduled chain rather
                # than one synchronous main-thread task.
                response_queue = queue.Queue()

                def start_locator():
                    try:
                        self._create_locator_async(
                            params.get("name", ""), params.get("time", 0.0),
                            response_queue)
                    except Exception as e:
                        self.log_message("Error creating locator: " + str(e))
                        response_queue.put({"status": "error", "message": str(e)})

                try:
                    self.schedule_message(0, start_locator)
                except AssertionError:
                    start_locator()
                self._await_main_thread(response, response_queue, 10.0)
            elif command_type == "get_drum_pads":
                response["result"] = self._get_drum_pads(
                    params.get("track_index", 0), params.get("device_index"))
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
                response["result"] = self._get_arrangement_clips(track_index)
            # Dataset / state-snapshot reads
            elif command_type == "get_clip_notes":
                track_index = params.get("track_index", 0)
                clip_index = params.get("clip_index", 0)
                response["result"] = self._get_clip_notes(track_index, clip_index)
            elif command_type == "get_device_parameters":
                track_index = params.get("track_index", 0)
                device_index = params.get("device_index", 0)
                response["result"] = self._get_device_parameters(
                    track_index, device_index, params.get("track_type", "track"))
            elif command_type == "get_session_snapshot":
                include_notes = params.get("include_notes", True)
                include_params = params.get("include_params", True)
                response["result"] = self._get_session_snapshot(
                    include_notes=include_notes,
                    include_params=include_params,
                )
            elif command_type == "drain_passive_events":
                response["result"] = self._drain_passive_events()
            elif command_type == "set_device_parameter":
                response_queue = queue.Queue()

                def main_thread_task():
                    try:
                        result = self._set_device_parameter(
                            params.get("track_index", 0),
                            params.get("device_index", 0),
                            params.get("parameter_index", 0),
                            params.get("value", 0.0),
                            params.get("track_type", "track"),
                            params.get("display"),
                        )
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
            elif command_type in self._STUDIO_MAIN_COMMANDS:
                handler = getattr(self, self._STUDIO_MAIN_COMMANDS[command_type])
                self._run_on_main_thread(handler, params, response, timeout=20.0)
            elif command_type in self._STUDIO_READ_COMMANDS:
                handler = getattr(self, self._STUDIO_READ_COMMANDS[command_type])
                response["result"] = handler(params)
            else:
                response["status"] = "error"
                response["message"] = "Unknown command: " + command_type
        except Exception as e:
            self.log_message("Error processing command: " + str(e))
            self.log_message(traceback.format_exc())
            response["status"] = "error"
            response["message"] = str(e)
        
        return response
    
    def _await_main_thread(self, response, response_queue, timeout):
        """Fill ``response`` from a main-thread task's queue (or a timeout)."""
        try:
            task_response = response_queue.get(timeout=timeout)
            if task_response.get("status") == "error":
                response["status"] = "error"
                response["message"] = task_response.get("message", "Unknown error")
            else:
                response["result"] = task_response.get("result", {})
        except queue.Empty:
            response["status"] = "error"
            response["message"] = "Timeout waiting for operation to complete"

    # Command implementations

    def _get_script_info(self):
        """Handshake payload for MCP server version / capability checks."""
        return {
            "name": "AbletonMCP",
            "script_version": SCRIPT_VERSION,
            "protocol_version": PROTOCOL_VERSION,
            "port": DEFAULT_PORT,
            "capabilities": list(SCRIPT_CAPABILITIES),
            "snapshot_schema": "ableton_mcp_snapshot_v2",
            "passive_listeners": True,
        }
    
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
                    "panning": self._song.master_track.mixer_device.panning.value,
                    "devices": [d.name for d in self._song.master_track.devices],
                },
                "return_tracks": [
                    {"index": i, "name": t.name, "devices": [d.name for d in t.devices]}
                    for i, t in enumerate(self._song.return_tracks)
                ],
                "tracks": [
                    {"index": i, "name": t.name,
                     "type": "midi" if getattr(t, "has_midi_input", False) else "audio",
                     "devices": [d.name for d in t.devices]}
                    for i, t in enumerate(self._song.tracks)
                ],
                # Read via _safe_song_property so an attribute missing on a
                # given Live version falls back to its default.
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
                "arm": self._safe_arm(track),
                "volume": track.mixer_device.volume.value,
                "panning": track.mixer_device.panning.value,
                "clip_slots": clip_slots,
                "devices": devices
            }
            return result
        except Exception as e:
            self.log_message("Error getting track info: " + str(e))
            raise
    
    def _safe_arm(self, track):
        """Read track.arm, returning False for tracks that have no arm state.

        Live raises RuntimeError("Master and Return Tracks have no 'Arm'
        state!") for group tracks as well as return and main tracks. A
        `getattr(track, "arm", False)` does not guard this: the attribute
        exists, so getattr's default never applies -- reading it is what
        throws, and the error is a RuntimeError rather than an AttributeError.

        Check can_be_armed first so the common path does not rely on raising,
        and keep a narrow catch for Live versions that do not expose that
        property on every track type.
        """
        try:
            if not getattr(track, "can_be_armed", False):
                return False
            return bool(track.arm)
        except (AttributeError, RuntimeError):
            return False

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

    def _set_arrangement_clip_name(self, track_index, clip_index, name):
        """Set the name of a clip placed in the Arrangement timeline.

        clip_index indexes into track.arrangement_clips, in the same order
        as returned by _get_arrangement_clips (i.e. ordered by start_time).
        """
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]
            arrangement_clips = list(track.arrangement_clips)

            if clip_index < 0 or clip_index >= len(arrangement_clips):
                raise IndexError("Clip index out of range")

            clip = arrangement_clips[clip_index]
            clip.name = name

            result = {
                "name": clip.name
            }
            return result
        except Exception as e:
            self.log_message("Error setting arrangement clip name: " + str(e))
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

    def _delete_clip(self, track_index, clip_index):
        """Delete the clip in the given clip slot, freeing the slot for reuse."""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]

            if clip_index < 0 or clip_index >= len(track.clip_slots):
                raise IndexError("Clip index out of range")

            clip_slot = track.clip_slots[clip_index]

            if not clip_slot.has_clip:
                return {"deleted": False, "reason": "Clip slot was already empty"}

            clip_slot.delete_clip()

            return {"deleted": True}
        except Exception as e:
            self.log_message("Error deleting clip: " + str(e))
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

    def _clear_notes_from_clip(self, track_index, clip_index):
        """Remove all MIDI notes from a Session clip.

        Pairs with _add_notes_to_clip to make a real replace (clear, then add),
        which the write-only API otherwise can't do. Counts notes first so the
        result can report how many were removed.
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

            if not clip.is_midi_clip:
                raise Exception("Clip is not a MIDI clip; no notes to clear")

            length = clip.length

            # Count existing notes for the report (best-effort; never fatal).
            cleared = 0
            try:
                getter = getattr(clip, "get_notes_extended", None)
                if getter is not None:
                    cleared = len(list(getter(0, 128, 0.0, length)))
                else:
                    cleared = len(list(clip.get_notes(0.0, 0, length, 128)))
            except Exception:
                cleared = 0

            # Remove every note across the full pitch/time range. Prefer the
            # modern API (Live 11+); fall back to the legacy signature. Argument
            # order mirrors the get/remove _extended family:
            #   remove_notes_extended(from_pitch, pitch_span, from_time, time_span)
            # vs the legacy remove_notes(from_time, from_pitch, time_span, pitch_span).
            remover = getattr(clip, "remove_notes_extended", None)
            if remover is not None:
                remover(0, 128, 0.0, length)
            else:
                clip.remove_notes(0.0, 0, length, 128)

            return {
                "track_index": track_index,
                "clip_index": clip_index,
                "clip_name": clip.name,
                "cleared_count": cleared,
            }
        except Exception as e:
            self.log_message("Error clearing notes from clip: " + str(e))
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

    # ── studio-upgrades fork ──────────────────────────────────────────────────

    def _create_locator_async(self, name, time_val, response_queue):
        """Create (or rename) a locator at a beat position.

        Song.set_or_delete_cue() toggles a cue at the playhead. The upstream
        version moved the playhead, toggled and searched for the cue in the
        same callback, before Live had applied either change, so it never
        found the cue (and a second call could toggle it back off). Here each
        step runs on its own tick.
        """
        song = self._song
        target = float(time_val)
        tolerance = 0.01

        def find():
            for cue in song.cue_points:
                if abs(cue.time - target) < tolerance:
                    return cue
            return None

        def finish(cue):
            if cue is None:
                times = sorted(round(c.time, 3) for c in song.cue_points)
                response_queue.put({
                    "status": "error",
                    "message": "Locator was not created at beat %s (locators now at: %s)"
                               % (target, times),
                })
                return
            if name:
                try:
                    cue.name = str(name)
                except Exception as e:
                    self.log_message("Could not rename locator: " + str(e))
            response_queue.put({
                "status": "success",
                "result": {"success": True, "time": cue.time, "name": cue.name},
            })

        existing = find()
        if existing is not None:
            finish(existing)
            return
        times_before = [c.time for c in song.cue_points]

        if self._safe_song_property("is_playing", bool, False):
            raise Exception(
                "Stop playback before adding locators: Live places them at the "
                "moving playhead.")

        original_time = song.current_song_time
        song.current_song_time = target

        def step_find():
            try:
                cue = find()
                if cue is None:
                    # Live may place the cue slightly off the requested
                    # beat; accept exactly one new cue and report its time.
                    new = [c for c in song.cue_points
                           if all(abs(c.time - t) > tolerance for t in times_before)]
                    if len(new) == 1:
                        cue = new[0]
                try:
                    song.current_song_time = original_time
                except Exception:
                    pass
                finish(cue)
            except Exception as e:
                response_queue.put({"status": "error", "message": str(e)})

        def step_toggle():
            try:
                if find() is None:
                    song.set_or_delete_cue()
                self.schedule_message(1, step_find)
            except Exception as e:
                response_queue.put({"status": "error", "message": str(e)})

        self.schedule_message(1, step_toggle)

    def _mixer_target(self, track_index, track_type="track"):
        """Resolve a regular, return or master track for mixer edits."""
        track_type = (track_type or "track").lower()
        if track_type == "master":
            return self._song.master_track
        tracks = self._song.return_tracks if track_type == "return" else self._song.tracks
        if track_index < 0 or track_index >= len(tracks):
            raise IndexError("%s index out of range" % track_type.capitalize())
        return tracks[track_index]

    @staticmethod
    def _parse_db(text):
        cleaned = str(text).replace("dB", "").strip()
        if "inf" in cleaned:
            return float("-inf")
        return float(cleaned)

    def _value_for_db(self, param, db):
        """Find the raw fader value Live displays as ``db`` (bisection on
        str_for_value, which is monotonic for volume and send faders)."""
        to_db = lambda v: self._parse_db(param.str_for_value(v))
        lo, hi = float(param.min), float(param.max)
        db = float(db)
        if db <= to_db(lo):
            return lo
        if db >= to_db(hi):
            return hi
        for _ in range(40):
            mid = (lo + hi) / 2.0
            if to_db(mid) < db:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2.0

    @staticmethod
    def _param_display(param):
        try:
            return param.str_for_value(param.value)
        except Exception:
            return str(param.value)

    def _set_track_mixer(self, track_index, track_type="track", volume=None,
                         volume_db=None, panning=None, mute=None, solo=None,
                         sends=None):
        """Set volume (raw or dB), pan, mute, solo and sends on one track."""
        track = self._mixer_target(track_index, track_type)
        mixer = track.mixer_device
        changed = []

        if volume_db is not None:
            mixer.volume.value = self._value_for_db(mixer.volume, volume_db)
            changed.append("volume")
        elif volume is not None:
            v = float(volume)
            mixer.volume.value = max(mixer.volume.min, min(mixer.volume.max, v))
            changed.append("volume")

        if panning is not None:
            p = float(panning)
            mixer.panning.value = max(mixer.panning.min, min(mixer.panning.max, p))
            changed.append("panning")

        is_master = (track_type or "track").lower() == "master"
        if mute is not None:
            if is_master:
                raise Exception("The master track cannot be muted")
            track.mute = bool(mute)
            changed.append("mute")
        if solo is not None:
            if is_master:
                raise Exception("The master track cannot be soloed")
            track.solo = bool(solo)
            changed.append("solo")

        if sends:
            items = sends.items() if isinstance(sends, dict) else [
                (s.get("index"), s.get("value")) for s in sends]
            send_params = list(mixer.sends)
            for key, val in items:
                i = int(key)
                if i < 0 or i >= len(send_params):
                    raise IndexError("Send index %d out of range" % i)
                sp = send_params[i]
                sp.value = max(sp.min, min(sp.max, float(val)))
            changed.append("sends")

        result = {
            "track_name": track.name,
            "changed": changed,
            "volume": mixer.volume.value,
            "volume_display": self._param_display(mixer.volume),
            "panning": mixer.panning.value,
            "panning_display": self._param_display(mixer.panning),
            "sends": [{"index": i, "value": sp.value, "display": self._param_display(sp)}
                      for i, sp in enumerate(mixer.sends)],
        }
        if not is_master:
            result["mute"] = bool(track.mute)
            result["solo"] = bool(track.solo)
        return result

    @staticmethod
    def _note_name(note):
        names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
        # Ableton's octave numbering: MIDI 60 = C3.
        return "%s%d" % (names[int(note) % 12], int(note) // 12 - 2)

    def _find_drum_rack(self, devices, depth=0):
        for device in devices:
            if getattr(device, "can_have_drum_pads", False):
                return device
            if getattr(device, "can_have_chains", False) and depth < 2:
                for chain in getattr(device, "chains", []):
                    found = self._find_drum_rack(chain.devices, depth + 1)
                    if found is not None:
                        return found
        return None

    def _get_drum_pads(self, track_index, device_index=None):
        """List the loaded pads of a Drum Rack: MIDI note, note name, pad name."""
        if track_index < 0 or track_index >= len(self._song.tracks):
            raise IndexError("Track index out of range")
        track = self._song.tracks[track_index]
        if device_index is not None:
            devices = list(track.devices)
            if device_index < 0 or device_index >= len(devices):
                raise IndexError("Device index out of range")
            rack = devices[device_index]
            if not getattr(rack, "can_have_drum_pads", False):
                raise Exception("Device %d on this track is not a Drum Rack" % device_index)
        else:
            rack = self._find_drum_rack(track.devices)
            if rack is None:
                raise Exception("No Drum Rack found on track '%s'" % track.name)

        pads = []
        for pad in rack.drum_pads:
            chains = list(getattr(pad, "chains", []))
            if not chains:
                continue
            pads.append({
                "note": int(pad.note),
                "note_name": self._note_name(pad.note),
                "name": pad.name,
                "mute": bool(getattr(pad, "mute", False)),
                "solo": bool(getattr(pad, "solo", False)),
                "chains": [c.name for c in chains],
            })
        return {
            "track_index": track_index,
            "track_name": track.name,
            "rack_name": rack.name,
            "pad_count": len(pads),
            "pads": pads,
        }

    def _copy_clip(self, track_index, clip_index, target_track_index,
                   target_clip_index, overwrite=False, new_name=None):
        """Copy a Session clip into another slot (same or different track)."""
        tracks = self._song.tracks
        for ti in (track_index, target_track_index):
            if ti < 0 or ti >= len(tracks):
                raise IndexError("Track index out of range")
        src_track, dst_track = tracks[track_index], tracks[target_track_index]
        if clip_index < 0 or clip_index >= len(src_track.clip_slots):
            raise IndexError("Source clip index out of range")
        if target_clip_index < 0 or target_clip_index >= len(dst_track.clip_slots):
            raise IndexError("Target clip index out of range")
        src_slot = src_track.clip_slots[clip_index]
        dst_slot = dst_track.clip_slots[target_clip_index]
        if not src_slot.has_clip:
            raise Exception("No clip in source slot")
        if src_slot is dst_slot or (track_index == target_track_index
                                    and clip_index == target_clip_index):
            raise Exception("Source and target are the same slot")
        if dst_slot.has_clip:
            if not overwrite:
                raise Exception("Target slot already has a clip (pass overwrite=true to replace it)")
            dst_slot.delete_clip()

        src = src_slot.clip
        duplicate = getattr(src_slot, "duplicate_clip_to", None)
        method = "duplicate_clip_to"
        if duplicate is not None:
            duplicate(dst_slot)
        else:
            if not getattr(src, "is_midi_clip", False):
                raise Exception("This Live version can only copy MIDI clips")
            method = "note_copy"
            dst_slot.create_clip(src.length)
            notes = self._notes_from_clip(src)
            dst_slot.clip.set_notes(tuple(
                (n["pitch"], n["start_time"], n["duration"], n["velocity"], n["mute"])
                for n in notes))
            dst_slot.clip.name = src.name
        if new_name:
            dst_slot.clip.name = str(new_name)
        return {
            "source": {"track_index": track_index, "clip_index": clip_index, "name": src.name},
            "target": {"track_index": target_track_index, "clip_index": target_clip_index,
                       "name": dst_slot.clip.name},
            "length": dst_slot.clip.length,
            "method": method,
        }

    def _fill_arrangement(self, track_index, clip_index, start_time, end_time, step=None):
        """Place a Session clip back-to-back across [start_time, end_time)."""
        if track_index < 0 or track_index >= len(self._song.tracks):
            raise IndexError("Track index out of range")
        track = self._song.tracks[track_index]
        if clip_index < 0 or clip_index >= len(track.clip_slots):
            raise IndexError("Clip slot index out of range")
        slot = track.clip_slots[clip_index]
        if not slot.has_clip:
            raise Exception("No clip in slot %d on track %d" % (clip_index, track_index))
        clip = slot.clip
        start, end = float(start_time), float(end_time)
        length = float(step) if step else float(clip.length)
        if length <= 0:
            raise ValueError("Step / clip length must be positive")
        if end <= start:
            raise ValueError("end_time must be after start_time")
        positions = []
        t = start
        while t < end - 1e-6:
            if len(positions) >= 512:
                raise Exception("Refusing to place more than 512 copies in one call")
            track.duplicate_clip_to_arrangement(clip, t)
            positions.append(t)
            t += length
        return {
            "track_name": track.name,
            "clip_name": clip.name,
            "copies": len(positions),
            "positions": positions,
            "ends_at": positions[-1] + float(clip.length) if positions else start,
        }

    def _delete_arrangement_clips(self, track_index, start_time=0.0, end_time=None):
        """Delete arrangement clips whose start falls in [start_time, end_time)."""
        if track_index < 0 or track_index >= len(self._song.tracks):
            raise IndexError("Track index out of range")
        track = self._song.tracks[track_index]
        deleter = getattr(track, "delete_clip", None)
        if deleter is None:
            raise Exception("Track.delete_clip is unavailable in this Live version (needs Live 11+)")
        start = float(start_time)
        end = float(end_time) if end_time is not None else None
        eps = 1e-6
        targets = [c for c in list(track.arrangement_clips)
                   if c.start_time >= start - eps and (end is None or c.start_time < end - eps)]
        removed = []
        for clip in targets:
            removed.append({"name": clip.name, "start_time": clip.start_time})
            deleter(clip)
        return {"track_name": track.name, "deleted": len(removed), "clips": removed}

    def _back_to_arrangement(self):
        """Press Live's Back to Arrangement button."""
        self._song.back_to_arranger = False
        return {"back_to_arranger_lit": bool(self._song.back_to_arranger)}

    def _set_arrangement_loop(self, start_time, length, enabled=True):
        song = self._song
        if float(length) <= 0:
            raise ValueError("Loop length must be positive")
        song.loop_start = float(start_time)
        song.loop_length = float(length)
        song.loop = bool(enabled)
        return {"loop": bool(song.loop), "loop_start": song.loop_start,
                "loop_length": song.loop_length}

    # ── studio-upgrades 1.9: dispatch tables ─────────────────────────────────
    #
    # New commands register here instead of growing the if/elif chain above.
    # MAIN: run on Live's main thread (anything that writes to the set).
    # READ: run directly on the socket thread (pure reads / job status).

    _STUDIO_MAIN_COMMANDS = {
        "add_device": "_cmd_add_device",
        "delete_device": "_cmd_delete_device",
        "set_device_parameters": "_cmd_set_device_parameters",
        "set_sidechain": "_cmd_set_sidechain",
        "write_clip_automation": "_cmd_write_clip_automation",
        "clear_clip_automation": "_cmd_clear_clip_automation",
        "set_groove": "_cmd_set_groove",
        "assign_groove": "_cmd_assign_groove",
        "set_groove_amount": "_cmd_set_groove_amount",
        "load_groove": "_cmd_load_groove",
        "set_clip_properties": "_cmd_set_clip_properties",
        "set_song_scale": "_cmd_set_song_scale",
        "create_return_track": "_cmd_create_return_track",
        "delete_track": "_cmd_delete_track",
        "duplicate_track": "_cmd_duplicate_track",
        "start_render": "_cmd_start_render",
        "cancel_render": "_cmd_cancel_render",
    }
    _STUDIO_READ_COMMANDS = {
        "get_clip_automation": "_cmd_get_clip_automation",
        "get_groove_pool": "_cmd_get_groove_pool",
        "get_song_scale": "_cmd_get_song_scale",
        "get_render_status": "_cmd_get_render_status",
        "get_mixer_overview": "_cmd_get_mixer_overview",
    }

    RENDER_TRACK_NAME = "MCP Render"

    def _run_on_main_thread(self, fn, params, response, timeout=10.0):
        response_queue = queue.Queue()

        def task():
            try:
                response_queue.put({"status": "success", "result": fn(params)})
            except Exception as e:
                self.log_message("Error in main thread task: " + str(e))
                self.log_message(traceback.format_exc())
                response_queue.put({"status": "error", "message": str(e)})

        try:
            self.schedule_message(0, task)
        except AssertionError:
            task()
        self._await_main_thread(response, response_queue, timeout)

    # ── shared helpers ────────────────────────────────────────────────────────

    def _track_from(self, params, key="track_index", type_key="track_type"):
        return self._mixer_target(int(params.get(key, 0) or 0), params.get(type_key, "track"))

    def _device_from(self, track, device_index):
        devices = list(track.devices)
        if device_index is None or int(device_index) < 0 or int(device_index) >= len(devices):
            raise IndexError("Device index out of range (track has %d devices)" % len(devices))
        return devices[int(device_index)]

    @staticmethod
    def _device_summary(track):
        return [{"index": i, "name": d.name, "class_name": getattr(d, "class_name", "")}
                for i, d in enumerate(track.devices)]

    def _find_parameter(self, device, index=None, name=None):
        params = list(device.parameters)
        if name is not None:
            wanted = str(name).strip().lower()
            for p in params:
                if p.name.strip().lower() == wanted:
                    return p
            for p in params:
                if wanted in p.name.strip().lower():
                    return p
            raise Exception("Parameter '%s' not found on %s. Available: %s" % (
                name, device.name, ", ".join(p.name for p in params[:40])))
        if index is None or int(index) < 0 or int(index) >= len(params):
            raise IndexError("Parameter index out of range")
        return params[int(index)]

    _UNIT_FACTORS = (
        ("khz", 1000.0, "hz"), ("hz", 1.0, "hz"),
        ("ms", 0.001, "s"), ("s", 1.0, "s"),
        ("db", 1.0, "db"), ("%", 1.0, "%"),
    )

    @classmethod
    def _parse_quantity(cls, text):
        """Parse '1.20 kHz' -> (1200.0, 'hz'), '-6.0 dB' -> (-6.0, 'db'),
        '350 ms' -> (0.35, 's'), '-inf dB' -> (-inf, 'db'). None if no number."""
        import re
        s = str(text).strip().lower().replace(",", ".")
        pan = re.match(r"^\s*(\d+(?:\.\d+)?)\s*([lr])\s*$", s)
        if pan:
            amount = float(pan.group(1))
            return (-amount if pan.group(2) == "l" else amount), "pan"
        if s in ("c", "center", "centre"):
            return 0.0, "pan"
        if "inf" in s:
            unit = "db" if "db" in s else ""
            return (float("-inf") if "-" in s else float("inf")), unit
        m = re.search(r"[-+]?\d*\.?\d+(?:e[-+]?\d+)?", s)
        if not m:
            return None
        value = float(m.group(0))
        rest = s[m.end():].strip()
        for suffix, factor, unit in cls._UNIT_FACTORS:
            if rest.startswith(suffix):
                return value * factor, unit
        if rest.startswith("k"):
            return value * 1000.0, ""
        return value, ""

    def _value_for_display(self, param, display):
        """Raw parameter value whose display text matches ``display``.

        Quantised parameters match their value_items by name; continuous ones
        are solved by bisection on str_for_value (monotonic for Live's
        native parameters)."""
        text = str(display).strip()
        lowered = text.lower()
        if getattr(param, "is_quantized", False):
            items = [str(v) for v in getattr(param, "value_items", [])]
            for i, item in enumerate(items):
                if item.strip().lower() == lowered:
                    return float(param.min) + i
            if lowered in ("on", "true", "yes"):
                return float(param.max)
            if lowered in ("off", "false", "no"):
                return float(param.min)
            if items:
                raise Exception("'%s' is not one of %s for %s" % (display, items, param.name))
        target = self._parse_quantity(text)
        if target is None:
            raise Exception("Could not read a number from '%s'" % display)
        tval, tunit = target
        lo, hi = float(param.min), float(param.max)

        def measure(v):
            q = self._parse_quantity(param.str_for_value(v))
            if q is None:
                raise Exception("%s has non-numeric display values; pass a raw value" % param.name)
            return q[0]

        f_lo, f_hi = measure(lo), measure(hi)
        increasing = f_hi >= f_lo
        if (increasing and tval <= f_lo) or (not increasing and tval >= f_lo):
            return lo
        if (increasing and tval >= f_hi) or (not increasing and tval <= f_hi):
            return hi
        sign = 1.0 if increasing else -1.0
        goal = sign * tval

        def edge(strict):
            # first raw value whose display reaches the goal (>=), or passes it (>)
            a, b = float(param.min), float(param.max)
            for _ in range(48):
                mid = (a + b) / 2.0
                m = sign * measure(mid)
                if (m > goal) if strict else (m >= goal):
                    b = mid
                else:
                    a = mid
            return b

        lower = edge(False)
        upper = edge(True)
        # Displays are rounded, so a range of raw values shows the target;
        # aim for the middle of that plateau rather than its rounding edge.
        if upper > lower and abs(measure((lower + upper) / 2.0) - tval) <= abs(measure(lower) - tval):
            return (lower + upper) / 2.0
        return lower

    def _apply_param_value(self, param, value=None, display=None, normalized=None):
        if display is not None:
            raw = self._value_for_display(param, display)
        elif normalized is not None:
            raw = float(param.min) + float(normalized) * (float(param.max) - float(param.min))
        elif value is not None:
            raw = float(value)
        else:
            raise Exception("Give value, display or normalized for %s" % param.name)
        raw = max(float(param.min), min(float(param.max), raw))
        if getattr(param, "is_quantized", False):
            raw = float(int(round(raw)))
        param.value = raw
        return {"name": param.name, "value": float(param.value),
                "display": self._param_display(param)}

    # ── devices ───────────────────────────────────────────────────────────────

    def _browser_find_by_name(self, name, root_names=("audio_effects", "instruments",
                                                      "midi_effects", "drums",
                                                      "max_for_live"), max_depth=3):
        app = self.application()
        browser = app.browser
        wanted = str(name).strip().lower()

        def strip_ext(n):
            n = n.strip().lower()
            for ext in (".adv", ".adg", ".amxd", ".agr", ".alc", ".aupreset"):
                if n.endswith(ext):
                    return n[: -len(ext)]
            return n

        def walk(item, depth):
            if depth > max_depth:
                return None
            for child in getattr(item, "children", []):
                try:
                    if strip_ext(child.name) == wanted and getattr(child, "is_loadable", True):
                        return child
                except Exception:
                    continue
            for child in getattr(item, "children", []):
                if getattr(child, "is_folder", False) or getattr(child, "children", None):
                    found = walk(child, depth + 1)
                    if found is not None:
                        return found
            return None

        for root_name in root_names:
            root = getattr(browser, root_name, None)
            if root is None:
                continue
            found = walk(root, 0)
            if found is not None:
                return found
        return None

    def _cmd_add_device(self, params):
        """Add a native device by name ("EQ Eight", "Compressor", "Reverb")
        to a track, return track or the master."""
        track = self._track_from(params)
        name = str(params.get("name", "")).strip()
        if not name:
            raise Exception("Device name required")
        position = params.get("position")
        before = len(track.devices)
        method = None
        notes = []
        inserter = getattr(track, "insert_device", None)
        if inserter is not None:
            try:
                if position is None:
                    inserter(name)
                else:
                    inserter(name, int(position))
                method = "insert_device"
            except Exception as e:
                notes.append("insert_device failed (%s); used the browser" % e)
        if method is None:
            item = self._browser_find_by_name(name)
            if item is None:
                raise Exception("No device or preset named '%s' in the browser" % name)
            self._song.view.selected_track = track
            self.application().browser.load_item(item)
            method = "browser"
            if position is not None:
                notes.append("browser loading appends at the end; position ignored")
        return {"track_name": track.name, "method": method, "notes": notes,
                "added": len(track.devices) - before,
                "devices": self._device_summary(track)}

    def _cmd_delete_device(self, params):
        track = self._track_from(params)
        index = int(params.get("device_index", -1))
        device = self._device_from(track, index)
        name = device.name
        track.delete_device(index)
        return {"track_name": track.name, "deleted": name,
                "devices": self._device_summary(track)}

    def _cmd_set_device_parameters(self, params):
        """Set several parameters on one device, by name or index, using raw
        values, normalised 0-1 values, or display text ("1.2 kHz", "-6 dB")."""
        track = self._track_from(params)
        device = self._device_from(track, params.get("device_index"))
        changes = params.get("changes") or []
        if isinstance(changes, dict):
            changes = [dict({"name": k}, **(v if isinstance(v, dict) else {"value": v}))
                       for k, v in changes.items()]
        results = []
        for change in changes:
            param = self._find_parameter(device, index=change.get("index"),
                                         name=change.get("name"))
            results.append(self._apply_param_value(
                param, value=change.get("value"), display=change.get("display"),
                normalized=change.get("normalized")))
        return {"track_name": track.name, "device_name": device.name, "set": results}

    def _cmd_set_sidechain(self, params):
        """Route a device's sidechain input (Compressor and other devices that
        expose input routing) from another track and switch it on."""
        track = self._track_from(params)
        device = self._device_from(track, params.get("device_index"))
        types = list(getattr(device, "available_input_routing_types", []) or [])
        if not types:
            raise Exception("%s doesn't expose sidechain routing to scripts. "
                            "Use Live's Compressor, or route it by hand." % device.name)
        source = params.get("source_track_name")
        source_track = None
        if params.get("source_track_index") is not None:
            source_track = self._song.tracks[int(params["source_track_index"])]
            source = source or source_track.name
        if not source:
            raise Exception("source_track_index or source_track_name required")
        wanted = str(source).strip().lower()
        match = None
        if source_track is not None:
            for t in types:
                if self._same(getattr(t, "attached_object", None), source_track):
                    match = t
                    break
        for t in types if match is None else []:
            label = str(t.display_name).strip().lower()
            if label == wanted or label.endswith("-" + wanted) or label.split("-", 1)[-1] == wanted:
                match = t
                break
        if match is None:
            for t in types:
                if wanted in str(t.display_name).lower():
                    match = t
                    break
        if match is None:
            raise Exception("No sidechain source called '%s'. Options: %s" % (
                source, [str(t.display_name) for t in types]))
        device.input_routing_type = match
        tap = str(params.get("tap", "post fx")).lower()
        channels = list(getattr(device, "available_input_routing_channels", []) or [])
        chosen_channel = None
        for c in channels:
            if tap.replace("_", " ") in str(c.display_name).lower():
                device.input_routing_channel = c
                chosen_channel = str(c.display_name)
                break
        enabled = None
        if params.get("enable", True):
            for p in device.parameters:
                n = p.name.lower()
                if n in ("s/c on", "sidechain", "sidechain on", "s/c"):
                    p.value = p.max
                    enabled = p.name
                    break
        return {"track_name": track.name, "device_name": device.name,
                "source": str(match.display_name), "channel": chosen_channel,
                "enabled_parameter": enabled}

    # ── clip automation ───────────────────────────────────────────────────────

    def _automation_clip(self, params):
        if params.get("arrangement"):
            raise Exception("Live's API can't read or write envelopes on Arrangement clips; "
                            "automate the Session clip, then place it with fill_arrangement")
        return self._session_clip(params)

    def _session_clip(self, params):
        track = self._track_from(params)
        if params.get("arrangement"):
            clips = list(track.arrangement_clips)
            ci = int(params.get("clip_index", 0))
            if ci < 0 or ci >= len(clips):
                raise IndexError("Arrangement clip index out of range")
            return track, clips[ci]
        slots = list(getattr(track, "clip_slots", []))
        ci = int(params.get("clip_index", 0))
        if ci < 0 or ci >= len(slots):
            raise IndexError("Clip slot index out of range")
        if not slots[ci].has_clip:
            raise Exception("No clip in slot %d" % ci)
        return track, slots[ci].clip

    def _automation_target(self, track, target):
        target = target or {}
        mixer = target.get("mixer")
        if mixer:
            md = track.mixer_device
            mixer = str(mixer).lower()
            if mixer == "volume":
                return md.volume
            if mixer in ("pan", "panning"):
                return md.panning
            if mixer == "send":
                sends = list(md.sends)
                si = int(target.get("send_index", 0))
                if si < 0 or si >= len(sends):
                    raise IndexError("Send index out of range")
                return sends[si]
            if mixer in ("activator", "track_activator", "on"):
                return md.track_activator
            raise Exception("Unknown mixer target '%s'" % mixer)
        device = self._device_from(track, target.get("device_index"))
        return self._find_parameter(device, index=target.get("parameter_index"),
                                    name=target.get("parameter_name"))

    @staticmethod
    def _curve(shape, f):
        if shape == "ease_in":
            return f * f
        if shape == "ease_out":
            return 1.0 - (1.0 - f) * (1.0 - f)
        if shape in ("s_curve", "smooth"):
            return f * f * (3.0 - 2.0 * f)
        if shape == "exp":
            import math
            return (math.exp(3.0 * f) - 1.0) / (math.exp(3.0) - 1.0)
        return f

    def _cmd_write_clip_automation(self, params):
        """Draw a clip envelope from breakpoints. Ramps are written as short
        steps (``resolution`` beats) because insert_step is the only writer
        the Live API offers; holds and quantised parameters use one step per
        segment."""
        track, clip = self._automation_clip(params)
        param = self._automation_target(track, params.get("target"))
        points = params.get("points") or []
        if not points:
            raise Exception("At least one point is required")
        curve = str(params.get("curve", "linear")).lower()
        resolution = max(1.0 / 128.0, float(params.get("resolution", 0.0625)))
        clip_end = float(getattr(clip, "loop_end", 0.0) or 0.0) if getattr(clip, "looping", True) else 0.0
        clip_end = max(clip_end, float(getattr(clip, "length", 0.0) or 0.0))
        resolved = []
        for p in points:
            t = max(0.0, float(p.get("time", 0.0)))
            if "display" in p:
                v = self._value_for_display(param, p["display"])
            elif "normalized" in p:
                v = float(param.min) + float(p["normalized"]) * (float(param.max) - float(param.min))
            else:
                v = float(p.get("value", param.value))
            resolved.append((t, max(float(param.min), min(float(param.max), v))))
        resolved.sort(key=lambda x: x[0])

        envelope = clip.automation_envelope(param)
        if envelope is not None and params.get("clear_existing", True):
            clip.clear_envelope(param)
            envelope = None
        if envelope is None:
            try:
                envelope = clip.create_automation_envelope(param)
            except Exception as e:
                raise Exception("Live refused to create an envelope for %s: %s" % (param.name, e))
        if envelope is None:
            raise Exception("Live refused to create an envelope for %s" % param.name)

        quantized = bool(getattr(param, "is_quantized", False))
        steps = []
        if resolved[0][0] > 0:
            steps.append((0.0, resolved[0][0], resolved[0][1]))
        for (t0, v0), (t1, v1) in zip(resolved, resolved[1:]):
            span = t1 - t0
            if span <= 1e-9:
                continue
            if curve == "step" or quantized or v0 == v1:
                steps.append((t0, span, v0))
                continue
            t = t0
            while t < t1 - 1e-9:
                length = min(resolution, t1 - t)
                f = self._curve(curve, (t - t0) / span)
                steps.append((t, length, v0 + (v1 - v0) * f))
                t += length
        last_t, last_v = resolved[-1]
        tail = max(clip_end - last_t, resolution)
        steps.append((last_t, tail, last_v))
        if len(steps) > 4096:
            raise Exception("Too many automation steps (%d); raise resolution" % len(steps))
        for t, length, v in steps:
            if quantized:
                v = float(int(round(v)))
            envelope.insert_step(t, length, v)
        # A parameter the user moved by hand is "overridden" and ignores its
        # envelope until re-enabled.
        if hasattr(param, "re_enable_automation"):
            try:
                param.re_enable_automation()
            except Exception:
                pass
        return {"track_name": track.name, "clip_name": clip.name,
                "parameter": param.name, "points": len(resolved), "steps": len(steps),
                "start": resolved[0][0], "end": last_t,
                "first_display": param.str_for_value(resolved[0][1]),
                "last_display": param.str_for_value(last_v)}

    def _cmd_clear_clip_automation(self, params):
        track, clip = self._automation_clip(params)
        target = params.get("target")
        if target:
            param = self._automation_target(track, target)
            clip.clear_envelope(param)
            return {"cleared": param.name, "clip_name": clip.name}
        clip.clear_all_envelopes()
        return {"cleared": "all", "clip_name": clip.name}

    def _cmd_get_clip_automation(self, params):
        track, clip = self._automation_clip(params)
        param = self._automation_target(track, params.get("target"))
        envelope = clip.automation_envelope(param)
        if envelope is None:
            return {"parameter": param.name, "has_envelope": False}
        start = float(getattr(clip, "loop_start", 0.0) or 0.0)
        end = float(getattr(clip, "loop_end", 0.0) or 0.0) or float(getattr(clip, "length", 4.0) or 4.0)
        resolution = max((end - start) / 256.0, float(params.get("resolution", 0.25)))
        samples = []
        t = start
        while t < end - 1e-9:
            v = float(envelope.value_at_time(t))
            samples.append({"time": round(t, 4), "value": round(v, 5),
                            "display": param.str_for_value(v)})
            t += resolution
        return {"parameter": param.name, "has_envelope": True,
                "clip_name": clip.name, "samples": samples}

    # ── groove pool ───────────────────────────────────────────────────────────

    _GROOVE_BASES = ["1/4", "1/8", "1/8T", "1/16", "1/16T", "1/32"]

    def _grooves(self):
        pool = getattr(self._song, "groove_pool", None)
        if pool is None:
            raise Exception("This Live version doesn't expose the groove pool (needs Live 11+)")
        return list(pool.grooves)

    def _groove_info(self, index, g):
        base = int(getattr(g, "base", 0) or 0)
        return {"index": index, "name": g.name,
                "base": self._GROOVE_BASES[base] if 0 <= base < len(self._GROOVE_BASES) else base,
                "timing": round(float(g.timing_amount), 3),
                "random": round(float(g.random_amount), 3),
                "velocity": round(float(g.velocity_amount), 3),
                "quantize": round(float(g.quantization_amount), 3)}

    def _cmd_get_groove_pool(self, params):
        grooves = self._grooves()
        return {"global_amount": float(getattr(self._song, "groove_amount", 1.0)),
                "grooves": [self._groove_info(i, g) for i, g in enumerate(grooves)]}

    def _cmd_set_groove(self, params):
        grooves = self._grooves()
        i = int(params.get("groove_index", 0))
        if i < 0 or i >= len(grooves):
            raise IndexError("Groove index out of range")
        g = grooves[i]
        for key, attr in (("timing", "timing_amount"), ("random", "random_amount"),
                          ("velocity", "velocity_amount"), ("quantize", "quantization_amount")):
            if params.get(key) is not None:
                setattr(g, attr, float(params[key]))
        if params.get("base") is not None:
            base = params["base"]
            g.base = self._GROOVE_BASES.index(base) if base in self._GROOVE_BASES else int(base)
        return self._groove_info(i, g)

    def _cmd_assign_groove(self, params):
        track, clip = self._session_clip(params)
        gi = params.get("groove_index")
        if gi is None:
            try:
                clip.groove = None
            except Exception:
                raise Exception("Live's API can't remove a clip's groove; remove it in the "
                                "clip's Groove chooser, or assign a groove with timing 0")
            return {"clip_name": clip.name, "groove": None}
        grooves = self._grooves()
        gi = int(gi)
        if gi < 0 or gi >= len(grooves):
            raise IndexError("Groove index out of range")
        clip.groove = grooves[gi]
        return {"clip_name": clip.name, "groove": grooves[gi].name}

    def _cmd_set_groove_amount(self, params):
        amount = max(0.0, min(1.3, float(params.get("amount", 1.0))))
        try:
            self._song.groove_amount = amount
        except Exception:
            self._song.groove_amount = min(amount, 1.0)
        return {"global_amount": float(self._song.groove_amount)}

    def _groove_roots(self):
        """Where .agr grooves live: packs → Core Library → Grooves, then the
        User Library and the current project."""
        browser = self.application().browser
        roots = []
        for pack in getattr(getattr(browser, "packs", None), "children", []) or []:
            if "core library" in str(pack.name).lower():
                for child in getattr(pack, "children", []) or []:
                    if str(child.name).lower() == "grooves":
                        roots.append(child)
        for attr in ("user_library", "current_project"):
            root = getattr(browser, attr, None)
            if root is not None:
                for child in getattr(root, "children", []) or []:
                    if "groove" in str(child.name).lower():
                        roots.append(child)
        return roots

    def _find_groove_item(self, name):
        wanted = str(name).strip().lower()
        if wanted.endswith(".agr"):
            wanted = wanted[:-4]

        def walk(item, depth):
            for child in getattr(item, "children", []) or []:
                n = str(child.name).strip().lower()
                if n.endswith(".agr") and n[:-4] == wanted:
                    return child
            if depth >= 3:
                return None
            for child in getattr(item, "children", []) or []:
                if getattr(child, "is_folder", False):
                    found = walk(child, depth + 1)
                    if found is not None:
                        return found
            return None

        for root in self._groove_roots():
            found = walk(root, 0)
            if found is not None:
                return found
        return None

    def _cmd_load_groove(self, params):
        """Add a library groove (e.g. "MPC 16 Swing-58") to the Groove Pool,
        reusing it if it's already there, and optionally assign it to a clip."""
        name = str(params.get("name", "")).strip()
        if name.lower().endswith(".agr"):
            name = name[:-4]
        grooves = self._grooves()
        index = next((i for i, g in enumerate(grooves) if g.name.lower() == name.lower()), None)
        loaded = None
        if index is None:
            item = self._find_groove_item(name)
            if item is None:
                raise Exception("Groove '%s' not found under Core Library > Grooves "
                                "or the User Library" % name)
            before = len(grooves)
            self.application().browser.load_item(item)
            grooves = self._grooves()
            if len(grooves) > before:
                index = len(grooves) - 1
            else:
                index = next((i for i, g in enumerate(grooves)
                              if g.name.lower() == name.lower()), None)
            loaded = item.name
        applied = None
        if index is not None and params.get("clip_index") is not None:
            track, clip = self._session_clip(params)
            clip.groove = grooves[index]
            applied = clip.groove.name if clip.groove is not None else None
        return {"loaded": loaded or "(already in pool)", "groove_index": index,
                "applied_to_clip": applied, "pool": [g.name for g in grooves]}

    # ── clip properties, scale, tracks ────────────────────────────────────────

    _WARP_MODES = {"beats": 0, "tones": 1, "texture": 2, "re-pitch": 3, "repitch": 3,
                   "complex": 4, "rex": 5, "complex pro": 6, "complex_pro": 6}

    def _cmd_set_clip_properties(self, params):
        track, clip = self._session_clip(params)
        changed = {}
        props = params.get("properties") or {}
        is_audio = bool(getattr(clip, "is_audio_clip", False))
        # Moving a range later: set its end first, or Live rejects the start
        # ("cannot be set behind the end marker").
        order = ["pitch_coarse", "pitch_fine", "gain", "warping", "warp_mode", "looping"]
        for lo, hi in (("loop_start", "loop_end"), ("start_marker", "end_marker")):
            current_end = float(getattr(clip, hi, 0.0) or 0.0)
            if props.get(lo) is not None and float(props[lo]) >= current_end:
                order += [hi, lo]
            else:
                order += [lo, hi]
        order += ["muted", "name", "velocity_amount"]
        if props.get("warp_mode") is not None and isinstance(props["warp_mode"], str):
            props = dict(props)
            props["warp_mode"] = self._WARP_MODES[props["warp_mode"].strip().lower()]
        available = list(getattr(clip, "available_warp_modes", []) or [])
        if props.get("warp_mode") is not None and available and int(props["warp_mode"]) not in available:
            raise Exception("Warp mode %s isn't available for this clip (available: %s)"
                            % (props["warp_mode"], available))
        for key in order:
            if key not in props or props[key] is None:
                continue
            value = props[key]
            if key in ("pitch_coarse", "pitch_fine", "gain", "warping", "warp_mode") and not is_audio:
                raise Exception("%s only applies to audio clips; use transform_clip_notes "
                                "to transpose MIDI" % key)
            if key in ("pitch_coarse", "pitch_fine", "warp_mode"):
                value = int(value)
            elif key in ("warping", "looping", "muted"):
                value = bool(value)
            elif key != "name":
                value = float(value)
            setattr(clip, key, value)
            # warping is applied by Live on a later tick; report what was asked
            changed[key] = value if key in ("warping", "warp_mode") else getattr(clip, key)
        return {"clip_name": clip.name, "changed": changed,
                "gain_display": getattr(clip, "gain_display_string", None) if is_audio else None}

    def _cmd_get_song_scale(self, params):
        song = self._song
        names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
        root = getattr(song, "root_note", None)
        return {"root_note": root,
                "root_name": names[int(root) % 12] if root is not None else None,
                "scale_name": getattr(song, "scale_name", None),
                "scale_mode": getattr(song, "scale_mode", None),
                "scale_intervals": list(getattr(song, "scale_intervals", []) or [])}

    def _cmd_set_song_scale(self, params):
        song = self._song
        if not hasattr(song, "scale_name"):
            raise Exception("Song scale needs Live 12")
        names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
        root = params.get("root_note")
        if root is not None:
            if isinstance(root, str):
                root = names.index(root.strip().upper().replace("DB", "C#").replace("EB", "D#")
                                   .replace("GB", "F#").replace("AB", "G#").replace("BB", "A#"))
            song.root_note = int(root) % 12
        if params.get("scale_name"):
            song.scale_name = str(params["scale_name"])
        if params.get("scale_mode") is not None:
            song.scale_mode = bool(params["scale_mode"])
        return self._cmd_get_song_scale(params)

    def _cmd_create_return_track(self, params):
        self._song.create_return_track()
        returns = list(self._song.return_tracks)
        track = returns[-1]
        if params.get("name"):
            track.name = str(params["name"])
        return {"return_index": len(returns) - 1, "name": track.name}

    def _cmd_delete_track(self, params):
        track_type = params.get("track_type", "track")
        index = int(params.get("track_index", -1))
        track = self._mixer_target(index, track_type)
        name = track.name
        if track_type == "return":
            self._song.delete_return_track(index)
        elif track_type == "track":
            self._song.delete_track(index)
        else:
            raise Exception("The master track can't be deleted")
        return {"deleted": name, "track_type": track_type}

    def _cmd_duplicate_track(self, params):
        index = int(params.get("track_index", -1))
        track = self._mixer_target(index, "track")
        source_name = track.name
        self._song.duplicate_track(index)
        # Live selects the copy; for groups it lands after the children, so
        # index + 1 is not reliable.
        copy = getattr(self._song.view, "selected_track", None)
        tracks = list(self._song.tracks)
        new_index = next((i for i, t in enumerate(tracks) if self._same(t, copy)), index + 1)
        copy = tracks[new_index]
        if params.get("name"):
            copy.name = str(params["name"])
        return {"source": source_name, "new_index": new_index, "name": copy.name}

    def _cmd_get_mixer_overview(self, params):
        """Every track, return and the master: devices plus fader, pan,
        sends, mute, solo, in dB where Live shows dB."""
        def row(track, kind, index):
            md = track.mixer_device
            entry = {"kind": kind, "index": index, "name": track.name,
                     "volume": self._param_display(md.volume),
                     "pan": self._param_display(md.panning),
                     "devices": [d.name for d in track.devices]}
            if kind != "master":
                entry["mute"] = bool(track.mute)
                entry["solo"] = bool(track.solo)
                entry["sends"] = [self._param_display(s) for s in md.sends]
            return entry
        rows = [row(t, "track", i) for i, t in enumerate(self._song.tracks)]
        rows += [row(t, "return", i) for i, t in enumerate(self._song.return_tracks)]
        rows.append(row(self._song.master_track, "master", 0))
        return {"tracks": rows}

    # ── rendering by resampling ───────────────────────────────────────────────
    #
    # Live has no offline export in its API. A render is a real-time
    # arrangement recording of the Resampling input onto a helper audio track,
    # driven by a tick loop so the socket thread never blocks:
    #
    #   preparing   new tracks expose no input routings in the tick they are
    #               created, so routing is retried each tick (10 s cap)
    #   positioning start_time/current_song_time are set, then confirmed on the
    #               next tick before recording starts
    #   recording   until the playhead passes end_beat
    #   finalizing  until the recorded clip and its file_path appear
    #   done/error  user state (loop, metronome, punch, arms, solos, playhead,
    #               selection) is restored; the helper track is muted so the
    #               take never plays back in the song
    #
    # The helper track's monitoring is Off (no feedback) and every older take
    # on it is deleted before recording, so nothing on it reaches Resampling.

    _render_job = None

    def _render_track(self):
        for track in self._song.tracks:
            if track.name == self.RENDER_TRACK_NAME and getattr(track, "has_audio_input", False):
                return track
        self._song.create_audio_track(-1)
        track = self._song.tracks[-1]
        track.name = self.RENDER_TRACK_NAME
        return track

    def _cmd_start_render(self, params):
        job = self._render_job
        if job and job.get("state") in ("preparing", "positioning", "recording", "finalizing"):
            raise Exception("A render is already running (job %s)" % job["id"])
        song = self._song
        start = float(params.get("start_beat", 0.0))
        end = float(params.get("end_beat", start + 16.0))
        if end <= start:
            raise ValueError("end_beat must be after start_beat")
        preroll = max(0.0, float(params.get("preroll_beats", 4.0)))
        record_from = max(0.0, start - preroll)
        if song.is_playing:
            song.stop_playing()

        render = self._render_track()
        tracks = list(song.tracks)
        tempo = float(song.tempo)
        job = {
            "id": "r%d" % int(time.time() * 1000),
            "state": "preparing",
            "start_beat": start, "end_beat": end, "record_from": record_from,
            "tempo": tempo,
            "expected_seconds": round((end - record_from) * 60.0 / tempo, 2),
            "ticks": 0, "phase_ticks": 0,
            "file_path": None, "error": None,
            "solo_tracks": list(params.get("solo_tracks") or []),
            "_params": dict(params),
            "_render": render,
        }
        # recording budget plus room for up to 4 bars of count-in
        job["max_ticks"] = int((job["expected_seconds"] + 16 * 60.0 / tempo) * 10) + 100
        view = song.view
        job["_saved"] = {
            "loop": song.loop,
            "metronome": getattr(song, "metronome", False),
            "punch_in": getattr(song, "punch_in", False),
            "punch_out": getattr(song, "punch_out", False),
            "song_time": song.current_song_time,
            "start_time": getattr(song, "start_time", None),
            "selected_track": getattr(view, "selected_track", None),
            "arms": [(t, t.arm) for t in tracks
                     if getattr(t, "can_be_armed", False) and not self._same(t, render)],
            "solos": [(t, t.solo) for t in tracks if not self._same(t, render)],
        }
        self._render_job = job
        self.schedule_message(1, self._render_tick)
        return self._public_job(job)

    @staticmethod
    def _same(a, b):
        """Live hands out fresh Python proxies, so compare LOM objects by
        their underlying pointer rather than identity."""
        if a is b:
            return True
        if a is None or b is None:
            return False
        pa, pb = getattr(a, "_live_ptr", None), getattr(b, "_live_ptr", None)
        if pa is not None and pb is not None:
            return pa == pb
        try:
            return a == b
        except Exception:
            return False

    @staticmethod
    def _public_job(job):
        return {k: v for k, v in dict(job).items() if not k.startswith("_")}

    def _render_try_route(self, render):
        for rt in list(getattr(render, "available_input_routing_types", []) or []):
            if "resampl" in str(rt.display_name).lower():
                render.input_routing_type = rt
                return str(rt.display_name)
        return None

    def _render_configure(self, job):
        """Everything after routing succeeded: arms, solos, transport, position."""
        song = self._song
        render = job["_render"]
        params = job["_params"]
        tracks = list(song.tracks)
        for t in tracks:
            if self._same(t, render):
                continue
            try:
                if getattr(t, "can_be_armed", False) and t.arm:
                    t.arm = False
                if getattr(t, "implicit_arm", False):
                    t.implicit_arm = False
            except Exception:
                pass
        try:
            render.current_monitoring_state = 2  # Off: plays nothing live, no feedback
        except Exception:
            pass
        for clip in list(getattr(render, "arrangement_clips", [])):
            try:
                render.delete_clip(clip)
            except Exception:
                pass
        render.mute = False

        solo = job["solo_tracks"]
        if solo:
            for t in tracks:
                if not self._same(t, render):
                    t.solo = False
            for i in solo:
                tracks[int(i)].solo = True

        song.loop = False
        if hasattr(song, "metronome"):
            song.metronome = False
        for attr in ("punch_in", "punch_out"):
            if hasattr(song, attr):
                setattr(song, attr, False)
        if params.get("follow_arrangement", True):
            try:
                song.stop_all_clips(False)
            except Exception:
                pass
            song.back_to_arranger = False
        try:
            song.view.selected_track = render
        except Exception:
            pass
        render.arm = True
        if hasattr(song, "start_time"):
            song.start_time = job["record_from"]
        song.current_song_time = job["record_from"]

    def _render_window_offset(self, job, clip):
        """Seconds into the recorded file where start_beat sits. Recorded
        files carry pre-roll, so song time clip.start_time maps to the
        clip's start_marker, not to the start of the file."""
        rel = job["start_beat"] - float(clip.start_time)
        beat_s = 60.0 / job["tempo"]
        try:
            if getattr(clip, "warping", False):
                samples = clip.beat_to_sample_time(float(clip.start_marker) + rel)
                return float(samples) / float(clip.sample_rate)
            return float(clip.start_marker) + rel * beat_s
        except Exception:
            return rel * beat_s

    def _render_restore(self, job):
        song = self._song
        saved = job.get("_saved") or {}
        render = job.get("_render")
        try:
            song.record_mode = False
            if song.is_playing:
                song.stop_playing()
        except Exception:
            pass
        if render is not None:
            for attr, value in (("arm", False), ("mute", True)):
                try:
                    setattr(render, attr, value)
                except Exception:
                    pass
        for t, armed in saved.get("arms", []):
            try:
                t.arm = armed
            except Exception:
                pass
        for t, soloed in saved.get("solos", []):
            try:
                t.solo = soloed
            except Exception:
                pass
        for attr in ("loop", "metronome", "punch_in", "punch_out"):
            if attr in saved and hasattr(song, attr):
                try:
                    setattr(song, attr, saved[attr])
                except Exception:
                    pass
        try:
            if saved.get("start_time") is not None and hasattr(song, "start_time"):
                song.start_time = saved["start_time"]
            song.current_song_time = saved.get("song_time", 0.0)
        except Exception:
            pass
        if saved.get("selected_track") is not None:
            try:
                song.view.selected_track = saved["selected_track"]
            except Exception:
                pass

    def _render_fail(self, job, message):
        job["state"] = "error"
        job["error"] = message
        self.log_message("Render error: " + message)
        self._render_restore(job)

    def _render_tick(self):
        job = self._render_job
        if not job or job.get("state") not in ("preparing", "positioning", "recording", "finalizing"):
            return
        song = self._song
        try:
            job["ticks"] += 1
            job["phase_ticks"] += 1
            state = job["state"]

            if state == "preparing":
                if self._render_try_route(job["_render"]) is None:
                    if job["phase_ticks"] > 100:
                        raise Exception("Couldn't route the render track to Resampling")
                    self.schedule_message(1, self._render_tick)
                    return
                self._render_configure(job)
                job["state"], job["phase_ticks"] = "positioning", 0
                self.schedule_message(1, self._render_tick)
                return

            if state == "positioning":
                if abs(song.current_song_time - job["record_from"]) > 1e-3:
                    if job["phase_ticks"] > 20:
                        raise Exception("Couldn't move the playhead to beat %s" % job["record_from"])
                    song.current_song_time = job["record_from"]
                    self.schedule_message(1, self._render_tick)
                    return
                song.record_mode = True
                song.start_playing()
                job["state"], job["phase_ticks"] = "recording", 0
                self.schedule_message(1, self._render_tick)
                return

            if state == "recording":
                counting = bool(getattr(song, "is_counting_in", False))
                if song.current_song_time >= job["end_beat"]:
                    song.record_mode = False
                    song.stop_playing()
                    job["state"], job["phase_ticks"] = "finalizing", 0
                elif not song.is_playing and not counting and job["phase_ticks"] > 10:
                    raise Exception("Playback stopped before the render finished")
                elif job["phase_ticks"] > job["max_ticks"]:
                    raise Exception("Render timed out")
                self.schedule_message(1, self._render_tick)
                return

            # finalizing
            render = job["_render"]
            candidates = [c for c in getattr(render, "arrangement_clips", [])
                          if c.end_time > job["start_beat"]]
            clip = max(candidates, key=lambda c: c.start_time) if candidates else None
            path = getattr(clip, "file_path", None) if clip is not None else None
            if path and job["phase_ticks"] >= 3:
                job["file_path"] = str(path)
                job["clip_start_beat"] = float(clip.start_time)
                job["window_offset_s"] = round(self._render_window_offset(job, clip), 4)
                job["window_seconds"] = round(
                    (job["end_beat"] - job["start_beat"]) * 60.0 / job["tempo"], 4)
                job["state"] = "done"
                self._render_restore(job)
                return
            if job["phase_ticks"] > 50:
                raise Exception("Recording finished but no audio clip appeared on '%s'"
                                % self.RENDER_TRACK_NAME)
            self.schedule_message(1, self._render_tick)
        except Exception as e:
            self._render_fail(job, str(e))

    def _cmd_get_render_status(self, params):
        job = self._render_job
        if not job:
            return {"state": "idle"}
        if params.get("job_id") and params["job_id"] != job["id"]:
            return {"state": "unknown", "message": "Only the latest render is tracked",
                    "latest": job["id"]}
        return self._public_job(job)

    def _cmd_cancel_render(self, params):
        job = self._render_job
        if not job or job.get("state") not in ("preparing", "positioning", "recording", "finalizing"):
            return {"state": "idle"}
        self._render_fail(job, "cancelled")
        return self._public_job(job)

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
    
    
    
    def _load_instrument_or_effect(self, track_index, uri):
        """Load an instrument or effect onto a track by its browser URI.

        The command dispatcher above calls this method, but it was never
        defined — and "load_instrument_or_effect" was missing from the list of
        main-thread commands as well, so the command fell through to the final
        "Unknown command" branch. Loading a device is exactly what
        _load_browser_item does, so delegate to it; the only difference is the
        parameter name the MCP server uses ("uri" vs "item_uri").
        """
        return self._load_browser_item(track_index, uri)

    def _load_browser_item(self, track_index, item_uri, track_type="track"):
        """Load a browser item onto a track, return track or the master by URI"""
        try:
            track = self._mixer_target(track_index, track_type)
            
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
    
    # Substring markers that point a URI at a likely root. Unmatched URIs fall
    # back to the default search order.
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

    def _find_blend_parameter(self, device):
        """Find Dry/Wet, Mix, or Amount on a device for Magnitude mapping."""
        preferred = ("Dry/Wet", "Dry Wet", "Mix", "Amount")
        by_name = {}
        for param in device.parameters:
            try:
                by_name[param.name] = param
            except Exception:
                continue
        for name in preferred:
            if name in by_name:
                return by_name[name], name
        # Case-insensitive fallback
        lowered = dict((k.lower(), (v, k)) for k, v in by_name.items())
        for name in preferred:
            hit = lowered.get(name.lower())
            if hit:
                return hit[0], hit[1]
        return None, None

    def _inspect_rack(self, track_index, device_index=0):
        """Inspect a rack's nested devices and blend parameters."""
        if track_index < 0 or track_index >= len(self._song.tracks):
            raise IndexError("Track index out of range")
        track = self._song.tracks[track_index]
        if device_index < 0 or device_index >= len(track.devices):
            raise IndexError("Device index out of range")
        rack = track.devices[device_index]
        if not getattr(rack, "can_have_chains", False):
            raise ValueError("Device '{0}' is not a rack".format(rack.name))

        devices_info = []
        for chain_index, chain in enumerate(rack.chains):
            for nested in chain.devices:
                blend, blend_name = self._find_blend_parameter(nested)
                param_names = []
                try:
                    param_names = [p.name for p in nested.parameters]
                except Exception:
                    pass
                devices_info.append({
                    "chain_index": chain_index,
                    "name": nested.name,
                    "class_name": nested.class_name,
                    "blend_param": blend_name,
                    "parameters": param_names,
                })

        return {
            "track_index": track_index,
            "device_index": device_index,
            "rack_name": rack.name,
            "has_macro_map": hasattr(rack, "macro_map"),
            "has_rename_macro": hasattr(rack, "rename_macro"),
            "macros_mapped": list(getattr(rack, "macros_mapped", [])),
            "devices": devices_info,
        }

    def _map_rack_magnitude(self, track_index, device_index=0, macro_name="Magnitude"):
        """Rename Macro 1 and map nested Dry/Wet (or Mix/Amount) params to it."""
        if track_index < 0 or track_index >= len(self._song.tracks):
            raise IndexError("Track index out of range")
        track = self._song.tracks[track_index]
        if device_index < 0 or device_index >= len(track.devices):
            raise IndexError("Device index out of range")
        rack = track.devices[device_index]
        if not getattr(rack, "can_have_chains", False):
            raise ValueError("Device '{0}' is not a rack".format(rack.name))
        if not hasattr(rack, "macro_map"):
            raise RuntimeError(
                "RackDevice.macro_map is unavailable in this Live version")

        # Ensure at least one macro is visible
        try:
            visible = int(getattr(rack, "visible_macro_count", 1) or 1)
            while visible < 1 and hasattr(rack, "add_macro"):
                rack.add_macro()
                visible = int(rack.visible_macro_count)
        except Exception as e:
            self.log_message("Could not adjust visible macros: {0}".format(e))

        if hasattr(rack, "rename_macro"):
            rack.rename_macro(0, macro_name)
        else:
            # Fallback: Macro 1 is usually parameters[1] (0 = Device On)
            try:
                if len(rack.parameters) > 1:
                    rack.parameters[1].name = macro_name
            except Exception:
                pass

        mapped = []
        skipped = []
        for chain_index, chain in enumerate(rack.chains):
            for nested in chain.devices:
                blend, blend_name = self._find_blend_parameter(nested)
                if not blend:
                    skipped.append({
                        "device": nested.name,
                        "reason": "no Dry/Wet, Mix, or Amount parameter",
                    })
                    continue
                try:
                    rack.macro_map(0, blend)
                    mapped.append({
                        "device": nested.name,
                        "parameter": blend_name,
                        "chain_index": chain_index,
                    })
                except Exception as e:
                    skipped.append({
                        "device": nested.name,
                        "parameter": blend_name,
                        "reason": str(e),
                    })

        return {
            "rack_name": rack.name,
            "macro_name": macro_name,
            "macro_index": 0,
            "mapped": mapped,
            "skipped": skipped,
            "macros_mapped": list(getattr(rack, "macros_mapped", [])),
        }
    
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

    # ── Passive human-UI listeners ──────────────────────────────────────────────

    def _enqueue_passive(self, event_type, detail=None, track_index=None, clip_index=None):
        """Append a coarse human-UI event (capped FIFO)."""
        evt = {
            "type": event_type,
            "ts": time.time(),
            "track_index": track_index,
            "clip_index": clip_index,
            "detail": detail if detail is not None else {},
        }
        with self._passive_lock:
            self._passive_events.append(evt)
            if len(self._passive_events) > self._passive_max:
                self._passive_events = self._passive_events[-self._passive_max:]

    def _drain_passive_events(self):
        """Return and clear the passive event queue (called by MCP poller)."""
        with self._passive_lock:
            events = list(self._passive_events)
            self._passive_events = []
        return {"events": events, "count": len(events)}

    def _safe_add_listener(self, obj, add_name, callback):
        try:
            if obj is not None and hasattr(obj, add_name):
                getattr(obj, add_name)(callback)
                return True
        except Exception as e:
            self.log_message("add listener %s failed: %s" % (add_name, str(e)))
        return False

    def _safe_remove_listener(self, obj, remove_name, callback):
        try:
            if obj is not None and hasattr(obj, remove_name):
                getattr(obj, remove_name)(callback)
        except Exception:
            pass

    def _setup_passive_listeners(self):
        """Register high-signal LOM listeners for Mode C / assisted human edits."""
        song = self._song

        def on_tempo():
            try:
                self._enqueue_passive("tempo_changed", {"tempo": float(song.tempo)})
            except Exception:
                self._enqueue_passive("tempo_changed")

        def on_sig_num():
            try:
                self._enqueue_passive(
                    "time_signature_changed",
                    {
                        "signature_numerator": int(song.signature_numerator),
                        "signature_denominator": int(song.signature_denominator),
                    },
                )
            except Exception:
                self._enqueue_passive("time_signature_changed")

        def on_sig_den():
            on_sig_num()

        def on_is_playing():
            try:
                self._enqueue_passive(
                    "playback_changed",
                    {"is_playing": bool(song.is_playing)},
                )
            except Exception:
                self._enqueue_passive("playback_changed")

        def on_tracks():
            count = len(song.tracks)
            previous = getattr(self, "_passive_track_count", None)
            self._passive_track_count = count
            detail = {"track_count": count}
            if previous is not None:
                detail["previous_count"] = previous
                detail["removed"] = count < previous
                detail["added"] = count > previous
            self._enqueue_passive("tracks_changed", detail)
            try:
                self._rebind_track_listeners()
            except Exception as e:
                self.log_message("rebind track listeners failed: " + str(e))

        self._safe_add_listener(song, "add_tempo_listener", on_tempo)
        self._safe_add_listener(song, "add_signature_numerator_listener", on_sig_num)
        self._safe_add_listener(song, "add_signature_denominator_listener", on_sig_den)
        self._safe_add_listener(song, "add_is_playing_listener", on_is_playing)
        self._safe_add_listener(song, "add_tracks_listener", on_tracks)

        self._song_passive_callbacks = [
            ("tempo_listener", on_tempo),
            ("signature_numerator_listener", on_sig_num),
            ("signature_denominator_listener", on_sig_den),
            ("is_playing_listener", on_is_playing),
            ("tracks_listener", on_tracks),
        ]

        self._rebind_track_listeners()
        self.log_message("Passive LOM listeners registered")

    def _teardown_passive_listeners(self):
        song = getattr(self, "_song", None)
        for suffix, cb in getattr(self, "_song_passive_callbacks", []):
            self._safe_remove_listener(song, "remove_" + suffix, cb)
        self._clear_track_listeners()

    def _clear_track_listeners(self):
        for track, bindings in getattr(self, "_passive_track_bindings", []):
            for add_name, callback in bindings:
                remove_name = "remove_" + add_name[len("add_"):]
                target = getattr(callback, "_passive_target", None)
                if target is not None:
                    self._safe_remove_listener(target, remove_name, callback)
                else:
                    self._safe_remove_listener(track, remove_name, callback)
        self._passive_track_bindings = []

    def _rebind_track_listeners(self):
        self._clear_track_listeners()
        song = self._song
        for track_index, track in enumerate(song.tracks):
            bindings = []

            def make_track_cb(kind, t_index):
                def _cb():
                    detail = {}
                    try:
                        t = song.tracks[t_index]
                        if kind == "name_changed":
                            detail["name"] = t.name
                        elif kind == "mute_changed":
                            detail["mute"] = bool(t.mute)
                        elif kind == "solo_changed":
                            detail["solo"] = bool(t.solo)
                        elif kind == "arm_changed":
                            detail["arm"] = self._safe_arm(t)
                        elif kind == "devices_changed":
                            detail["device_count"] = len(t.devices)
                        elif kind == "volume_changed":
                            detail["volume"] = float(t.mixer_device.volume.value)
                        elif kind == "panning_changed":
                            detail["panning"] = float(t.mixer_device.panning.value)
                    except Exception:
                        pass
                    self._enqueue_passive(kind, detail, track_index=t_index)
                return _cb

            pairs = [
                ("add_name_listener", "name_changed"),
                ("add_mute_listener", "mute_changed"),
                ("add_solo_listener", "solo_changed"),
                ("add_arm_listener", "arm_changed"),
                ("add_devices_listener", "devices_changed"),
            ]
            for add_name, kind in pairs:
                cb = make_track_cb(kind, track_index)
                if self._safe_add_listener(track, add_name, cb):
                    bindings.append((add_name, cb))

            try:
                mixer = track.mixer_device
                vol_cb = make_track_cb("volume_changed", track_index)
                vol_cb._passive_target = mixer.volume
                if self._safe_add_listener(mixer.volume, "add_value_listener", vol_cb):
                    bindings.append(("add_value_listener", vol_cb))
                pan_cb = make_track_cb("panning_changed", track_index)
                pan_cb._passive_target = mixer.panning
                if self._safe_add_listener(mixer.panning, "add_value_listener", pan_cb):
                    bindings.append(("add_value_listener", pan_cb))
            except Exception as e:
                self.log_message("mixer listeners failed on track %d: %s" % (track_index, str(e)))

            try:
                for clip_index, slot in enumerate(track.clip_slots):
                    def make_slot_cb(t_index, c_index):
                        def _cb():
                            has = False
                            try:
                                has = bool(song.tracks[t_index].clip_slots[c_index].has_clip)
                            except Exception:
                                pass
                            self._enqueue_passive(
                                "clip_slot_changed",
                                {"has_clip": has},
                                track_index=t_index,
                                clip_index=c_index,
                            )
                            try:
                                self._bind_clip_listeners(t_index, c_index)
                            except Exception:
                                pass
                        return _cb

                    slot_cb = make_slot_cb(track_index, clip_index)
                    slot_cb._passive_target = slot
                    if self._safe_add_listener(slot, "add_has_clip_listener", slot_cb):
                        bindings.append(("add_has_clip_listener", slot_cb))
                    if slot.has_clip:
                        self._bind_clip_listeners(track_index, clip_index, bindings)
            except Exception as e:
                self.log_message("clip slot listeners failed on track %d: %s" % (track_index, str(e)))

            self._passive_track_bindings.append((track, bindings))

    def _bind_clip_listeners(self, track_index, clip_index, bindings=None):
        try:
            track = self._song.tracks[track_index]
            slot = track.clip_slots[clip_index]
            if not slot.has_clip:
                return
            clip = slot.clip

            def on_name():
                name = ""
                try:
                    name = clip.name
                except Exception:
                    pass
                self._enqueue_passive(
                    "clip_name_changed",
                    {"name": name},
                    track_index=track_index,
                    clip_index=clip_index,
                )

            def on_notes():
                self._enqueue_passive(
                    "clip_notes_changed",
                    {},
                    track_index=track_index,
                    clip_index=clip_index,
                )

            def on_playing():
                playing = False
                try:
                    playing = bool(clip.is_playing)
                except Exception:
                    pass
                self._enqueue_passive(
                    "clip_playing_changed",
                    {"is_playing": playing},
                    track_index=track_index,
                    clip_index=clip_index,
                )

            for add_name, cb in [
                ("add_name_listener", on_name),
                ("add_notes_listener", on_notes),
                ("add_playing_status_listener", on_playing),
            ]:
                cb._passive_target = clip
                if self._safe_add_listener(clip, add_name, cb):
                    if bindings is not None:
                        bindings.append((add_name, cb))
        except Exception as e:
            self.log_message(
                "bind clip listeners %d/%d failed: %s"
                % (track_index, clip_index, str(e))
            )

    # ── Dataset / state snapshot helpers ──────────────────────────────────────

    def _safe_attr(self, obj, attr, cast=None, default=None):
        try:
            val = getattr(obj, attr)
            if callable(val):
                return default
            if cast is not None:
                return cast(val)
            return val
        except Exception:
            return default

    def _notes_from_clip(self, clip):
        """Extract MIDI notes from a clip (incl. MPE/expression when available)."""
        notes = []
        if not clip or not getattr(clip, "is_midi_clip", False):
            return notes

        if hasattr(clip, "get_notes_extended"):
            try:
                raw = clip.get_notes_extended(0, 128, 0.0, float(clip.length) + 1.0)
                for n in raw:
                    entry = {
                        "pitch": int(getattr(n, "pitch", 0)),
                        "start_time": float(getattr(n, "start_time", 0.0)),
                        "duration": float(getattr(n, "duration", 0.0)),
                        "velocity": float(getattr(n, "velocity", 0)),
                        "mute": bool(getattr(n, "mute", False)),
                    }
                    for opt, caster in [
                        ("probability", float),
                        ("velocity_deviation", float),
                        ("release_velocity", float),
                        ("note_id", int),
                    ]:
                        if hasattr(n, opt):
                            try:
                                entry[opt] = caster(getattr(n, opt))
                            except Exception:
                                pass
                    for opt in ("pitch_bend_range", "pressure", "timbre", "slide"):
                        if hasattr(n, opt):
                            try:
                                entry[opt] = float(getattr(n, opt))
                            except Exception:
                                pass
                    notes.append(entry)
                return notes
            except Exception as e:
                self.log_message("get_notes_extended failed, falling back: " + str(e))

        if hasattr(clip, "get_notes"):
            try:
                raw = clip.get_notes(0.0, 0, float(clip.length) + 1.0, 128)
                for n in raw:
                    notes.append({
                        "pitch": int(n[0]),
                        "start_time": float(n[1]),
                        "duration": float(n[2]),
                        "velocity": float(n[3]),
                        "mute": bool(n[4]) if len(n) > 4 else False,
                    })
            except Exception as e:
                self.log_message("get_notes failed: " + str(e))
        return notes

    def _warp_markers_from_clip(self, clip):
        markers = []
        try:
            raw = getattr(clip, "warp_markers", None)
            if not raw:
                return markers
            for m in raw:
                markers.append({
                    "beat_time": float(getattr(m, "beat_time", getattr(m, "time", 0.0))),
                    "sample_time": float(
                        getattr(m, "sample_time", getattr(m, "time", 0.0))
                    ),
                })
        except Exception as e:
            self.log_message("warp_markers read failed: " + str(e))
        return markers

    def _automated_params_for_device(self, device):
        automated = []
        try:
            for param in device.parameters:
                is_auto = False
                try:
                    if hasattr(param, "automation_state"):
                        is_auto = int(param.automation_state) != 0
                    elif hasattr(param, "is_automated"):
                        is_auto = bool(param.is_automated)
                except Exception:
                    continue
                if is_auto:
                    automated.append(param.name)
        except Exception:
            pass
        return automated

    # Racks nest, and a pathological project could nest deeply. Cap the walk so
    # a snapshot can never blow the stack or the payload size.
    _MAX_CHAIN_DEPTH = 4

    def _serialize_device(self, device, device_index, include_params=True, depth=0):
        info = {
            "index": device_index,
            "name": device.name,
            "class_name": device.class_name,
            "type": self._get_device_type(device),
        }
        automated = self._automated_params_for_device(device)
        if automated:
            info["automated_parameters"] = automated
            info["automation_enabled"] = True
        else:
            info["automation_enabled"] = False

        if include_params:
            params = []
            try:
                for p_index, param in enumerate(device.parameters):
                    try:
                        entry = {
                            "index": p_index,
                            "name": param.name,
                            "value": float(param.value),
                            "min": float(param.min),
                            "max": float(param.max),
                            "is_enabled": bool(getattr(param, "is_enabled", True)),
                            "is_quantized": bool(getattr(param, "is_quantized", False)),
                        }
                        entry["display"] = self._param_display(param)
                        if entry["is_quantized"]:
                            try:
                                entry["value_items"] = [str(v) for v in param.value_items]
                            except Exception:
                                pass
                        if hasattr(param, "automation_state"):
                            try:
                                entry["automation_state"] = int(param.automation_state)
                            except Exception:
                                pass
                        params.append(entry)
                    except Exception:
                        continue
            except Exception as e:
                self.log_message("Error reading device parameters: " + str(e))
            info["parameters"] = params

        # Devices inside a rack carry the actual sound design — a drum rack's
        # nested Operator, an instrument rack's filter. Without this walk a rack
        # contributes only its 8 macros and the timbral state is invisible.
        if getattr(device, "can_have_chains", False):
            if depth >= self._MAX_CHAIN_DEPTH:
                info["chains_truncated"] = True
            else:
                info["chains"] = self._serialize_chains(
                    device, include_params=include_params, depth=depth
                )
        return info

    def _serialize_chains(self, rack, include_params=True, depth=0):
        chains = []
        try:
            chain_lists = [("chains", getattr(rack, "chains", []))]
            returns = getattr(rack, "return_chains", None)
            if returns:
                chain_lists.append(("return_chains", returns))

            for kind, chain_list in chain_lists:
                for chain_index, chain in enumerate(chain_list):
                    entry = {
                        "index": chain_index,
                        "kind": kind,
                        "chain_name": self._safe_attr(chain, "name", str, ""),
                        "mute": bool(self._safe_attr(chain, "mute", bool, False)),
                        "solo": bool(self._safe_attr(chain, "solo", bool, False)),
                    }
                    try:
                        mixer = chain.mixer_device
                        entry["volume"] = float(mixer.volume.value)
                        entry["panning"] = float(mixer.panning.value)
                    except Exception:
                        pass

                    # Drum racks expose the pad's note, which is what ties a
                    # nested device back to the kick/snare/hat it voices.
                    note = self._safe_attr(chain, "out_note", int, None)
                    if note is not None:
                        entry["out_note"] = note

                    nested = []
                    try:
                        for d_i, dev in enumerate(chain.devices):
                            nested.append(
                                self._serialize_device(
                                    dev,
                                    d_i,
                                    include_params=include_params,
                                    depth=depth + 1,
                                )
                            )
                    except Exception as e:
                        self.log_message("Error reading chain devices: " + str(e))
                    entry["devices"] = nested
                    chains.append(entry)
        except Exception as e:
            self.log_message("Error serializing rack chains: " + str(e))
        return chains

    def _serialize_clip_common(self, clip):
        info = {
            "looping": bool(self._safe_attr(clip, "looping", bool, False)),
            "loop_start": self._safe_attr(clip, "loop_start", float, None),
            "loop_end": self._safe_attr(clip, "loop_end", float, None),
            "warping": bool(self._safe_attr(clip, "warping", bool, False)),
            "warp_mode": self._safe_attr(clip, "warp_mode", int, None),
            "gain": self._safe_attr(clip, "gain", float, None),
            "pitch_coarse": self._safe_attr(clip, "pitch_coarse", int, None),
            "pitch_fine": self._safe_attr(clip, "pitch_fine", int, None),
            "launch_mode": self._safe_attr(clip, "launch_mode", int, None),
        }
        for attr in ("file_path", "file_path_relative"):
            path = self._safe_attr(clip, attr, str, None)
            if path:
                info["file_path"] = path
                break
        markers = self._warp_markers_from_clip(clip)
        if markers:
            info["warp_markers"] = markers
            info["warp_marker_count"] = len(markers)
        return dict((k, v) for k, v in info.items() if v is not None)

    def _serialize_session_clip(self, clip, include_notes=True):
        info = {
            "name": clip.name,
            "length": float(clip.length),
            "is_playing": bool(clip.is_playing),
            "is_recording": bool(getattr(clip, "is_recording", False)),
            "is_midi_clip": bool(getattr(clip, "is_midi_clip", False)),
            "is_audio_clip": bool(getattr(clip, "is_audio_clip", False)),
            "color": int(getattr(clip, "color", 0)),
        }
        info.update(self._serialize_clip_common(clip))
        if include_notes and info["is_midi_clip"]:
            info["notes"] = self._notes_from_clip(clip)
            info["note_count"] = len(info["notes"])
        return info

    def _serialize_arrangement_clip(self, clip, include_notes=True):
        info = {
            "name": clip.name,
            "start_time": float(clip.start_time),
            "end_time": float(clip.end_time),
            "length": float(clip.length),
            "color": int(getattr(clip, "color", 0)),
            "is_midi_clip": bool(getattr(clip, "is_midi_clip", False)),
            "is_audio_clip": bool(getattr(clip, "is_audio_clip", False)),
            "is_playing": bool(getattr(clip, "is_playing", False)),
        }
        info.update(self._serialize_clip_common(clip))
        if include_notes and info["is_midi_clip"]:
            info["notes"] = self._notes_from_clip(clip)
            info["note_count"] = len(info["notes"])
        return info

    def _serialize_sends(self, track):
        sends = []
        try:
            for i, send in enumerate(track.mixer_device.sends):
                sends.append({
                    "index": i,
                    "value": float(send.value),
                    "name": str(getattr(send, "name", "Send %d" % i)),
                })
        except Exception:
            pass
        return sends

    def _serialize_scenes(self):
        scenes = []
        try:
            for i, scene in enumerate(self._song.scenes):
                scenes.append({
                    "index": i,
                    "name": str(scene.name),
                    "tempo": self._safe_attr(scene, "tempo", float, None),
                    "is_triggered": bool(self._safe_attr(scene, "is_triggered", bool, False)),
                })
        except Exception as e:
            self.log_message("scenes serialize failed: " + str(e))
        return scenes

    def _serialize_cue_points(self):
        cues = []
        try:
            for cue in self._song.cue_points:
                cues.append({
                    "name": str(getattr(cue, "name", "")),
                    "time": float(getattr(cue, "time", 0.0)),
                })
        except Exception as e:
            self.log_message("cue_points serialize failed: " + str(e))
        return cues

    def _serialize_return_tracks(self, include_params=True):
        returns = []
        try:
            for i, track in enumerate(self._song.return_tracks):
                devices = []
                for d_i, device in enumerate(track.devices):
                    devices.append(
                        self._serialize_device(device, d_i, include_params=include_params)
                    )
                returns.append({
                    "index": i,
                    "name": track.name,
                    "mute": bool(track.mute),
                    "solo": bool(track.solo),
                    "volume": float(track.mixer_device.volume.value),
                    "panning": float(track.mixer_device.panning.value),
                    "devices": devices,
                })
        except Exception as e:
            self.log_message("return_tracks serialize failed: " + str(e))
        return returns

    def _serialize_master_track(self, include_params=True):
        """Master chain — the bus compressor/limiter that shapes the final sound."""
        try:
            track = self._song.master_track
            devices = []
            for d_i, device in enumerate(track.devices):
                devices.append(
                    self._serialize_device(device, d_i, include_params=include_params)
                )
            return {
                "volume": float(track.mixer_device.volume.value),
                "panning": float(track.mixer_device.panning.value),
                "devices": devices,
            }
        except Exception as e:
            self.log_message("master_track serialize failed: " + str(e))
            return None

    def _get_clip_notes(self, track_index, clip_index):
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
            if not getattr(clip, "is_midi_clip", False):
                raise Exception("Clip is not a MIDI clip")
            notes = self._notes_from_clip(clip)
            return {
                "track_index": track_index,
                "clip_index": clip_index,
                "clip_name": clip.name,
                "length": float(clip.length),
                "note_count": len(notes),
                "notes": notes,
            }
        except Exception as e:
            self.log_message("Error getting clip notes: " + str(e))
            raise

    def _get_device_parameters(self, track_index, device_index, track_type="track"):
        try:
            track = self._mixer_target(track_index, track_type)
            if device_index < 0 or device_index >= len(track.devices):
                raise IndexError("Device index out of range")
            device = track.devices[device_index]
            return {
                "track_index": track_index,
                "device": self._serialize_device(device, device_index, include_params=True),
            }
        except Exception as e:
            self.log_message("Error getting device parameters: " + str(e))
            raise

    def _get_session_snapshot(self, include_notes=True, include_params=True):
        """Full v2 project state dump for trajectory dataset recording."""
        try:
            session = self._get_session_info()
            tracks = []
            for track_index, track in enumerate(self._song.tracks):
                clip_slots = []
                for slot_index, slot in enumerate(track.clip_slots):
                    clip_info = None
                    if slot.has_clip:
                        clip_info = self._serialize_session_clip(
                            slot.clip, include_notes=include_notes
                        )
                    clip_slots.append({
                        "index": slot_index,
                        "has_clip": bool(slot.has_clip),
                        "clip": clip_info,
                    })

                devices = []
                for device_index, device in enumerate(track.devices):
                    devices.append(
                        self._serialize_device(
                            device, device_index, include_params=include_params
                        )
                    )

                arrangement_clips = []
                try:
                    for clip in track.arrangement_clips:
                        arrangement_clips.append(
                            self._serialize_arrangement_clip(
                                clip, include_notes=include_notes
                            )
                        )
                except Exception as e:
                    self.log_message(
                        "arrangement_clips unavailable on track %d: %s"
                        % (track_index, str(e))
                    )

                tracks.append({
                    "index": track_index,
                    "name": track.name,
                    "is_audio_track": bool(track.has_audio_input),
                    "is_midi_track": bool(track.has_midi_input),
                    "mute": bool(track.mute),
                    "solo": bool(track.solo),
                    "arm": self._safe_arm(track),
                    "volume": float(track.mixer_device.volume.value),
                    "panning": float(track.mixer_device.panning.value),
                    "sends": self._serialize_sends(track),
                    "clip_slots": clip_slots,
                    "devices": devices,
                    "arrangement_clips": arrangement_clips,
                })

            return {
                "schema": "ableton_mcp_snapshot_v2",
                "session": session,
                "tracks": tracks,
                "scenes": self._serialize_scenes(),
                "return_tracks": self._serialize_return_tracks(
                    include_params=include_params
                ),
                "master_track": self._serialize_master_track(
                    include_params=include_params
                ),
                "cue_points": self._serialize_cue_points(),
                "include_notes": bool(include_notes),
                "include_params": bool(include_params),
            }
        except Exception as e:
            self.log_message("Error getting session snapshot: " + str(e))
            raise

    def _set_device_parameter(self, track_index, device_index, parameter_index, value,
                              track_type="track", display=None):
        try:
            track = self._mixer_target(track_index, track_type)
            if device_index < 0 or device_index >= len(track.devices):
                raise IndexError("Device index out of range")
            device = track.devices[device_index]
            if parameter_index < 0 or parameter_index >= len(device.parameters):
                raise IndexError("Parameter index out of range")
            param = device.parameters[parameter_index]
            old = float(param.value)
            self._apply_param_value(param, value=None if display is not None else value,
                                    display=display)
            return {
                "track_index": track_index,
                "device_index": device_index,
                "parameter_index": parameter_index,
                "name": param.name,
                "old_value": old,
                "value": float(param.value),
                "min": float(param.min),
                "max": float(param.max),
                "display": self._param_display(param),
            }
        except Exception as e:
            self.log_message("Error setting device parameter: " + str(e))
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
            
            # The full browser is far too large to serialise, so descend one
            # level and mark anything deeper with has_more. The MCP server
            # renders that as "[...]" and get_browser_items_at_path walks on
            # from there.
            max_depth = 1
            max_children = 64
            folder_count = [0]

            def process_item(item, depth=0):
                if not item:
                    return None

                children = getattr(item, 'children', None) or []
                is_folder = bool(children)
                if is_folder:
                    folder_count[0] += 1

                node = {
                    "name": item.name if hasattr(item, 'name') else "Unknown",
                    "is_folder": is_folder,
                    "is_device": hasattr(item, 'is_device') and item.is_device,
                    "is_loadable": hasattr(item, 'is_loadable') and item.is_loadable,
                    "uri": item.uri if hasattr(item, 'uri') else None,
                    "children": []
                }

                if is_folder and depth >= max_depth:
                    node["has_more"] = True
                    return node

                for child in children[:max_children]:
                    try:
                        processed = process_item(child, depth + 1)
                    except Exception as e:
                        self.log_message("Error processing browser child: {0}".format(str(e)))
                        continue
                    if processed:
                        node["children"].append(processed)
                if len(children) > max_children:
                    node["has_more"] = True

                return node

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
            
            # The MCP server reports this back to the caller; without it the
            # header always claimed zero folders.
            result["total_folders"] = folder_count[0]

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
