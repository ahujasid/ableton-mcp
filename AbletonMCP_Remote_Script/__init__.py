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
            elif command_type == "get_device_parameters":
                track_index = params.get("track_index", 0)
                device_path = params.get("device_path", [])
                response["result"] = self._get_device_parameters(track_index, device_path)
            elif command_type == "get_device_chains":
                track_index = params.get("track_index", 0)
                device_path = params.get("device_path", [])
                response["result"] = self._get_device_chains(track_index, device_path)
            # Commands that modify Live's state should be scheduled on the main thread
            elif command_type in ["create_midi_track", "set_track_name",
                                 "create_clip", "create_audio_clip", "add_notes_to_clip", "set_clip_name",
                                 "set_tempo", "fire_clip", "stop_clip",
                                 "start_playback", "stop_playback", "load_browser_item",
                                 # Arrangement view – must run on the main thread
                                 "switch_to_arrangement_view", "set_current_song_time",
                                 "duplicate_session_clip_to_arrangement",
                                 # Device/chain graph editing – must run on the main thread
                                 "insert_device_in_chain", "insert_chain_in_rack",
                                 "set_chain_properties", "set_device_parameter",
                                 "set_track_midi_channel", "set_macro_count",
                                 "load_sample_into_device", "delete_device", "delete_track"]:
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
                                track_index, clip_index, destination_time)
                        # ── Device/chain graph editing ──────────────────────
                        elif command_type == "insert_device_in_chain":
                            track_index = params.get("track_index", 0)
                            device_path = params.get("device_path", [])
                            device_name = params.get("device_name", "")
                            target_index = params.get("target_index", None)
                            result = self._insert_device_in_chain(
                                track_index, device_path, device_name, target_index)
                        elif command_type == "insert_chain_in_rack":
                            track_index = params.get("track_index", 0)
                            device_path = params.get("device_path", [])
                            target_index = params.get("target_index", None)
                            result = self._insert_chain_in_rack(
                                track_index, device_path, target_index)
                        elif command_type == "set_chain_properties":
                            track_index = params.get("track_index", 0)
                            device_path = params.get("device_path", [])
                            result = self._set_chain_properties(
                                track_index, device_path,
                                params.get("name", None),
                                params.get("in_note", None),
                                params.get("choke_group", None))
                        elif command_type == "set_device_parameter":
                            track_index = params.get("track_index", 0)
                            device_path = params.get("device_path", [])
                            parameter_name = params.get("parameter_name", "")
                            value = params.get("value", 0.0)
                            result = self._set_device_parameter(
                                track_index, device_path, parameter_name, value)
                        elif command_type == "set_track_midi_channel":
                            track_index = params.get("track_index", 0)
                            channel = params.get("channel", None)
                            result = self._set_track_midi_channel(track_index, channel)
                        elif command_type == "set_macro_count":
                            track_index = params.get("track_index", 0)
                            device_path = params.get("device_path", [])
                            count = params.get("count", 4)
                            result = self._set_macro_count(track_index, device_path, count)
                        elif command_type == "load_sample_into_device":
                            track_index = params.get("track_index", 0)
                            device_path = params.get("device_path", [])
                            item_uri = params.get("item_uri", "")
                            result = self._load_sample_into_device(track_index, device_path, item_uri)
                        elif command_type == "delete_device":
                            track_index = params.get("track_index", 0)
                            device_path = params.get("device_path", [])
                            result = self._delete_device(track_index, device_path)
                        elif command_type == "delete_track":
                            track_index = params.get("track_index", 0)
                            result = self._delete_track(track_index)

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
    
    # ── Device / chain graph addressing ─────────────────────────────────────
    #
    # A "device_path" is a list of ints that alternately index into a
    # container's .devices list and a rack device's .chains list, starting
    # from the track's top-level .devices list. This lets any device or
    # chain, at any nesting depth (e.g. a device inside a Drum Rack pad,
    # inside an Instrument Rack, on a track) be addressed uniformly:
    #
    #   []        -> the track itself (a device can be appended here)
    #   [0]        -> track.devices[0]                        (a Device)
    #   [0, 2]     -> track.devices[0].chains[2]               (a Chain)
    #   [0, 2, 1]  -> track.devices[0].chains[2].devices[1]    (a Device)

    def _resolve_device_path(self, track, device_path):
        """Resolve a device_path against a track. Returns (obj, kind) where
        kind is 'track', 'device', or 'chain'."""
        obj = track
        kind = "track"
        for i, idx in enumerate(device_path):
            if kind in ("track", "chain"):
                devices = obj.devices
                if idx < 0 or idx >= len(devices):
                    raise IndexError(
                        "Device index {0} out of range at path position {1} (path {2})".format(
                            idx, i, device_path))
                obj = devices[idx]
                kind = "device"
            elif kind == "device":
                if not obj.can_have_chains:
                    raise ValueError(
                        "Device '{0}' at path position {1} has no chains (path {2})".format(
                            obj.name, i, device_path))
                chains = obj.chains
                if idx < 0 or idx >= len(chains):
                    raise IndexError(
                        "Chain index {0} out of range at path position {1} (path {2})".format(
                            idx, i, device_path))
                obj = chains[idx]
                kind = "chain"
            else:
                raise ValueError("Unreachable path state")
        return obj, kind

    def _find_parameter_by_name(self, device, parameter_name):
        """Find a DeviceParameter on a device by name, with a fallback to
        case-insensitive and substring matching."""
        for p in device.parameters:
            if p.name == parameter_name:
                return p
        lowered = parameter_name.lower()
        for p in device.parameters:
            if p.name.lower() == lowered:
                return p
        for p in device.parameters:
            if lowered in p.name.lower():
                return p
        available = [p.name for p in device.parameters]
        raise ValueError(
            "Parameter '{0}' not found on device '{1}'. Available: {2}".format(
                parameter_name, device.name, available))

    def _get_track_for_index(self, track_index):
        if track_index < 0 or track_index >= len(self._song.tracks):
            raise IndexError("Track index out of range")
        return self._song.tracks[track_index]

    def _insert_device_in_chain(self, track_index, device_path, device_name, target_index):
        """Insert a native Live device (by its UI name, e.g. 'Saturator') at
        the end of a chain (or the track's root chain), or at target_index if
        given. Live 12.3+ only (Track.insert_device / Chain.insert_device)."""
        try:
            if not device_name:
                raise ValueError("device_name is required")
            track = self._get_track_for_index(track_index)
            obj, kind = self._resolve_device_path(track, device_path)
            if kind not in ("track", "chain"):
                raise ValueError(
                    "device_path must resolve to a track or a chain to insert a device "
                    "(got a device — did you mean to address one level up?)")
            if not hasattr(obj, "insert_device"):
                raise RuntimeError(
                    "insert_device is not available — requires Ableton Live 12.3 or newer")

            if target_index is None:
                obj.insert_device(device_name)
            else:
                obj.insert_device(device_name, int(target_index))

            devices = obj.devices
            new_index = int(target_index) if target_index is not None else len(devices) - 1
            new_device = devices[new_index]
            return {
                "device_path": list(device_path) + [new_index],
                "index": new_index,
                "name": new_device.name,
                "class_name": new_device.class_name
            }
        except Exception as e:
            self.log_message("Error inserting device in chain: " + str(e))
            self.log_message(traceback.format_exc())
            raise

    def _insert_chain_in_rack(self, track_index, device_path, target_index):
        """Insert a new chain into a rack device (Instrument/Audio Effect/
        Drum Rack). For Drum Racks this creates a DrumChain with in_note
        defaulted to -1 ('All Notes') — set it with set_chain_properties.
        Live 12.3+ only (RackDevice.insert_chain)."""
        try:
            track = self._get_track_for_index(track_index)
            obj, kind = self._resolve_device_path(track, device_path)
            if kind != "device":
                raise ValueError("device_path must resolve to a rack device")
            if not obj.can_have_chains:
                raise ValueError("Device '{0}' is not a rack (has no chains)".format(obj.name))
            if not hasattr(obj, "insert_chain"):
                raise RuntimeError(
                    "insert_chain is not available — requires Ableton Live 12.3 or newer")

            if target_index is None:
                obj.insert_chain()
            else:
                obj.insert_chain(int(target_index))

            chains = obj.chains
            new_index = int(target_index) if target_index is not None else len(chains) - 1
            new_chain = chains[new_index]
            return {
                "device_path": list(device_path) + [new_index],
                "chain_index": new_index,
                "name": new_chain.name,
                "is_drum_chain": hasattr(new_chain, "in_note")
            }
        except Exception as e:
            self.log_message("Error inserting chain in rack: " + str(e))
            self.log_message(traceback.format_exc())
            raise

    def _set_chain_properties(self, track_index, device_path, name, in_note, choke_group):
        """Set a chain's name and, for Drum Rack pad chains (DrumChain),
        its triggering note (in_note) and/or choke_group."""
        try:
            track = self._get_track_for_index(track_index)
            obj, kind = self._resolve_device_path(track, device_path)
            if kind != "chain":
                raise ValueError("device_path must resolve to a chain")

            if name is not None:
                obj.name = name
            if in_note is not None:
                if not hasattr(obj, "in_note"):
                    raise ValueError("Chain '{0}' is not a Drum Rack pad chain (no in_note)".format(obj.name))
                obj.in_note = int(in_note)
            if choke_group is not None:
                if not hasattr(obj, "choke_group"):
                    raise ValueError("Chain '{0}' is not a Drum Rack pad chain (no choke_group)".format(obj.name))
                obj.choke_group = int(choke_group)

            return {
                "name": obj.name,
                "in_note": getattr(obj, "in_note", None),
                "choke_group": getattr(obj, "choke_group", None)
            }
        except Exception as e:
            self.log_message("Error setting chain properties: " + str(e))
            self.log_message(traceback.format_exc())
            raise

    def _set_device_parameter(self, track_index, device_path, parameter_name, value):
        """Set a device parameter's value by name (e.g. 'Drive', 'Dry/Wet',
        'Decay Time'). Matches exact name first, then case-insensitive,
        then substring."""
        try:
            track = self._get_track_for_index(track_index)
            obj, kind = self._resolve_device_path(track, device_path)
            if kind != "device":
                raise ValueError("device_path must resolve to a device")

            param = self._find_parameter_by_name(obj, parameter_name)
            param.value = float(value)

            display_value = None
            try:
                display_value = param.str_for_value(param.value)
            except Exception:
                pass

            return {
                "device_name": obj.name,
                "parameter_name": param.name,
                "value": param.value,
                "display_value": display_value,
                "min": param.min,
                "max": param.max
            }
        except Exception as e:
            self.log_message("Error setting device parameter: " + str(e))
            self.log_message(traceback.format_exc())
            raise

    def _get_device_parameters(self, track_index, device_path):
        """List all automatable parameters on a device with their current
        value, min, max, and human-readable display_value (e.g. "2.50 s",
        "1.00 kHz") — many Live parameters use non-linear curves, so
        display_value is the reliable way to see/target a real-world value
        rather than guessing from the raw 0-1 'value'. Use this to discover
        exact parameter names and current values before calling
        set_device_parameter."""
        try:
            track = self._get_track_for_index(track_index)
            obj, kind = self._resolve_device_path(track, device_path)
            if kind != "device":
                raise ValueError("device_path must resolve to a device")

            parameters = []
            for i, p in enumerate(obj.parameters):
                display_value = None
                try:
                    display_value = p.str_for_value(p.value)
                except Exception:
                    pass
                parameters.append({
                    "index": i,
                    "name": p.name,
                    "value": p.value,
                    "display_value": display_value,
                    "min": p.min,
                    "max": p.max,
                    "is_quantized": p.is_quantized
                })

            return {
                "device_name": obj.name,
                "class_name": obj.class_name,
                "parameters": parameters
            }
        except Exception as e:
            self.log_message("Error getting device parameters: " + str(e))
            self.log_message(traceback.format_exc())
            raise

    def _get_device_chains(self, track_index, device_path):
        """List the chains inside a rack device (Instrument/Audio Effect/
        Drum Rack), including each chain's devices, in_note, and
        choke_group (for Drum Rack pad chains)."""
        try:
            track = self._get_track_for_index(track_index)
            obj, kind = self._resolve_device_path(track, device_path)
            if kind != "device":
                raise ValueError("device_path must resolve to a device")
            if not obj.can_have_chains:
                return {"device_name": obj.name, "can_have_chains": False, "chains": []}

            chains = []
            for i, c in enumerate(obj.chains):
                chains.append({
                    "index": i,
                    "name": c.name,
                    "is_drum_chain": hasattr(c, "in_note"),
                    "in_note": getattr(c, "in_note", None),
                    "choke_group": getattr(c, "choke_group", None),
                    "devices": [
                        {"index": j, "name": d.name, "class_name": d.class_name}
                        for j, d in enumerate(c.devices)
                    ]
                })

            return {
                "device_name": obj.name,
                "can_have_chains": True,
                "chains": chains
            }
        except Exception as e:
            self.log_message("Error getting device chains: " + str(e))
            self.log_message(traceback.format_exc())
            raise

    def _set_track_midi_channel(self, track_index, channel):
        """Filter a MIDI track's input to a single MIDI channel (1-16), or
        pass channel=None/0 to reset to 'All Channels'."""
        try:
            track = self._get_track_for_index(track_index)
            if not hasattr(track, "available_input_routing_channels"):
                raise ValueError(
                    "Track '{0}' does not support MIDI channel routing (not a MIDI track?)".format(track.name))

            available = track.available_input_routing_channels
            target = None

            if channel is None or int(channel) == 0:
                for ch in available:
                    dn = ch.get("display_name", "") if isinstance(ch, dict) else getattr(ch, "display_name", "")
                    if "all" in dn.lower():
                        target = ch
                        break
            else:
                wanted = str(int(channel))
                for ch in available:
                    dn = ch.get("display_name", "") if isinstance(ch, dict) else getattr(ch, "display_name", "")
                    dn_clean = dn.strip().lower()
                    if dn_clean in ("ch. " + wanted, "ch " + wanted, "channel " + wanted) or \
                       dn_clean.endswith(" " + wanted):
                        target = ch
                        break

            if target is None:
                available_names = [
                    (ch.get("display_name", "") if isinstance(ch, dict) else getattr(ch, "display_name", ""))
                    for ch in available
                ]
                raise ValueError(
                    "Could not find MIDI channel {0} among available routing channels: {1}".format(
                        channel, available_names))

            track.input_routing_channel = target
            result_channel = track.input_routing_channel
            result_dn = result_channel.get("display_name", "") if isinstance(result_channel, dict) \
                else getattr(result_channel, "display_name", "")
            return {"input_routing_channel": result_dn}
        except Exception as e:
            self.log_message("Error setting track MIDI channel: " + str(e))
            self.log_message(traceback.format_exc())
            raise

    def _set_macro_count(self, track_index, device_path, count):
        """Set how many Macro knobs are visible on a rack device (Instrument
        Rack, Audio Effect Rack, or Drum Rack) by repeatedly calling
        add_macro()/remove_macro() (Live 11.0+ — visible_macro_count itself
        is read-only)."""
        try:
            track = self._get_track_for_index(track_index)
            obj, kind = self._resolve_device_path(track, device_path)
            if kind != "device":
                raise ValueError("device_path must resolve to a rack device")
            if not obj.can_have_chains:
                raise ValueError("Device '{0}' is not a rack (has no macros)".format(obj.name))
            if not hasattr(obj, "add_macro") or not hasattr(obj, "remove_macro"):
                raise RuntimeError(
                    "add_macro/remove_macro are not available — requires Ableton Live 11.0 or newer")

            target = int(count)
            # Guard against runaway loops if the rack refuses to change count
            # (e.g. hitting Live's max) — cap iterations to the requested delta plus slack.
            max_iterations = abs(target - obj.visible_macro_count) + 4
            iterations = 0
            while obj.visible_macro_count < target and iterations < max_iterations:
                obj.add_macro()
                iterations += 1
            while obj.visible_macro_count > target and iterations < max_iterations:
                obj.remove_macro()
                iterations += 1

            return {"device_name": obj.name, "visible_macro_count": obj.visible_macro_count}
        except Exception as e:
            self.log_message("Error setting macro count: " + str(e))
            self.log_message(traceback.format_exc())
            raise

    def _load_sample_into_device(self, track_index, device_path, item_uri):
        """Load a browser sample (or preset). device_path may resolve to:
          - a chain or the track root ([]) — the item is loaded into an
            EMPTY slot there, e.g. Live auto-creates a Simpler for a raw
            sample, exactly like dragging a sample onto an empty track.
            This is the reliable path — use it.
          - an existing device — attempts an in-place hot-swap. On this
            Live build, hot-swapping a sample directly onto an existing
            SimplerDevice raises a boost.python argument-type error
            ("SimplerDevice did not match C++ signature: ADevice") — a
            genuine Ableton bug, not something callable-side can avoid.
            Prefer deleting the device and loading into the empty chain
            instead (see delete_device).

        Reports device_count_before/after and the newly-appeared device
        (if any) so the caller can verify what actually happened."""
        try:
            if not item_uri:
                raise ValueError("item_uri is required")
            track = self._get_track_for_index(track_index)
            obj, kind = self._resolve_device_path(track, device_path)
            if kind not in ("device", "chain", "track"):
                raise ValueError("device_path must resolve to a device, chain, or track")

            app = self.application()
            item = self._find_browser_item_by_uri(app.browser, item_uri)
            if not item:
                raise ValueError("Browser item with URI '{0}' not found".format(item_uri))

            # Select the top-level track first.
            self._song.view.selected_track = track

            # Walk the path, selecting each intermediate chain so the
            # browser's implicit load target cascades down through nested racks.
            cursor = track
            cursor_kind = "track"
            chain_selection_log = []
            for idx in device_path:
                if cursor_kind in ("track", "chain"):
                    cursor = cursor.devices[idx]
                    cursor_kind = "device"
                elif cursor_kind == "device":
                    chain = cursor.chains[idx]
                    if hasattr(cursor, "view") and hasattr(cursor.view, "selected_chain"):
                        try:
                            cursor.view.selected_chain = chain
                            chain_selection_log.append("{0}:ok".format(cursor.name))
                        except Exception as e:
                            chain_selection_log.append("{0}:failed({1})".format(cursor.name, str(e)))
                    cursor = chain
                    cursor_kind = "chain"

            # Container whose device list we diff to see what the load did.
            if kind == "device":
                container, container_kind = self._resolve_device_path(track, device_path[:-1])
            else:
                container = obj
                container_kind = kind
            before_count = len(container.devices)

            try:
                app.browser.load_item(item)
                load_error = None
            except Exception as e:
                load_error = str(e)
                self.log_message("browser.load_item failed: " + load_error)
                self.log_message(traceback.format_exc())

            after_devices = list(container.devices)
            new_device_name = None
            new_device_index = None
            if load_error is None:
                if len(after_devices) > before_count:
                    new_device_index = len(after_devices) - 1
                    new_device_name = after_devices[new_device_index].name
                elif kind == "device":
                    idx = device_path[-1]
                    if 0 <= idx < len(after_devices):
                        new_device_index = idx
                        new_device_name = after_devices[idx].name

            return {
                "loaded": load_error is None,
                "load_error": load_error,
                "item_name": item.name,
                "target_kind": kind,
                "chain_selection_log": chain_selection_log,
                "device_count_before": before_count,
                "device_count_after": len(after_devices),
                "new_device_name": new_device_name,
                "new_device_index": new_device_index
            }
        except Exception as e:
            self.log_message("Error loading sample into device: " + str(e))
            self.log_message(traceback.format_exc())
            raise

    def _delete_device(self, track_index, device_path):
        """Delete the device at device_path (its parent — a chain or the
        track root — must support delete_device; Live 12.3+)."""
        try:
            if not device_path:
                raise ValueError("device_path must address a device (non-empty list)")
            track = self._get_track_for_index(track_index)
            parent, parent_kind = self._resolve_device_path(track, device_path[:-1])
            if parent_kind not in ("track", "chain"):
                raise ValueError("device_path's parent must be a track or chain")
            if not hasattr(parent, "delete_device"):
                raise RuntimeError(
                    "delete_device is not available — requires Ableton Live 12.3 or newer")

            idx = device_path[-1]
            devices = parent.devices
            if idx < 0 or idx >= len(devices):
                raise IndexError("Device index out of range")
            deleted_name = devices[idx].name
            parent.delete_device(idx)

            return {"deleted": True, "name": deleted_name, "remaining_count": len(parent.devices)}
        except Exception as e:
            self.log_message("Error deleting device: " + str(e))
            self.log_message(traceback.format_exc())
            raise

    def _delete_track(self, track_index):
        """Delete a top-level track (e.g. to clean up scratch/test tracks)."""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            name = self._song.tracks[track_index].name
            self._song.delete_track(track_index)
            return {"deleted": True, "name": name, "remaining_track_count": len(self._song.tracks)}
        except Exception as e:
            self.log_message("Error deleting track: " + str(e))
            self.log_message(traceback.format_exc())
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
