# AbletonMCP/init.py
from __future__ import absolute_import, print_function, unicode_literals

from _Framework.ControlSurface import ControlSurface
import os
import uuid
import re
import math
import select
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

EXPECTED_COMMAND_ERRORS = (ValueError, IndexError)

# Bumped whenever the TCP command surface changes; the MCP server compares
# this to EXPECTED_REMOTE_SCRIPT_VERSION.
SCRIPT_VERSION = "1.9.0"
PROTOCOL_VERSION = 1

SCRIPT_CAPABILITIES = [
    "get_locators",
    "get_target_identity",
    "get_script_info",
    "get_session_info",
    "get_track_info",
    "create_midi_track",
    "create_audio_track",
    "set_track_name",
    "create_clip",
    "create_audio_clip",
    "add_notes_to_clip",
    "clear_notes_from_clip",
    "set_clip_name",
    "set_arrangement_clip_name",
    "set_tempo",
    "fire_clip",
    "stop_clip",
    "delete_clip",
    "start_playback",
    "stop_playback",
    "load_instrument_or_effect",
    "load_browser_item",
    "switch_to_arrangement_view",
    "set_current_song_time",
    "duplicate_session_clip_to_arrangement",
    "map_rack_magnitude",
    "inspect_rack",
    "create_locator",
    "get_browser_item",
    "get_browser_categories",
    "get_browser_items",
    "get_browser_tree",
    "get_browser_items_at_path",
    "get_arrangement_clips",
    "get_clip_notes",
    "get_device_parameters",
    "get_session_snapshot",
    "drain_passive_events",
    "set_device_parameter",
]

ROUTING_FIELDS = (("input_type", "input_routing_type"), ("input_channel", "input_routing_channel"),
                  ("output_type", "output_routing_type"), ("output_channel", "output_routing_channel"))

INTEGRATION_COMMANDS = {
    "get_transport": ("_cmd_get_transport", False),
    "set_song_settings": ("_cmd_set_song_settings", True),
    "jump_to_cue": ("_cmd_jump_to_cue", True),
    "stop_all_clips": ("_cmd_stop_all_clips", True),

    "get_tracks_overview": ("_cmd_get_tracks_overview", False),
    "check_arrangement_sync": ("_cmd_check_arrangement_sync", False),
    "search_browser": ("_cmd_search_browser", False),
    "get_notes": ("_cmd_get_notes", False),
    "modify_notes": ("_cmd_modify_notes", True),
    "get_device_chain": ("_cmd_get_device_chain", False),
    "set_device_parameter_value": ("_cmd_set_device_parameter_value", True),
    "get_rack": ("_cmd_get_rack", False),
    "set_rack_chain": ("_cmd_set_rack_chain", True),
    "get_simpler": ("_cmd_get_simpler", False),
    "edit_simpler": ("_cmd_edit_simpler", True),

    "get_structure": ("_cmd_get_structure", False),
    "edit_structure": ("_cmd_edit_structure", True),
    "get_track_routing": ("_cmd_get_track_routing", False),
    "set_track_routing": ("_cmd_set_track_routing", True),
    "get_mixer_state": ("_cmd_get_mixer_state", False),
    "set_track_mixer": ("_cmd_set_track_mixer", True),
}
SCRIPT_CAPABILITIES += sorted(INTEGRATION_COMMANDS)

# Queue bounds limit the work accepted and executed during one Live callback.
MAX_PENDING_COMMANDS = 64
MAX_COMMANDS_PER_TICK = 8
COMMAND_TIMEOUT = 10.0
LONG_COMMAND_TIMEOUT = 60.0
_command_clock = getattr(time, "monotonic", time.time)


# Focused mutation primitives informed by PR #119; no generic setter command.
MAX_TARGET_IDENTITIES = 4096
MAX_MUTATION_FIELDS = 128


class CommandFailure(ValueError):
    def __init__(self, code, message, details=None):
        ValueError.__init__(self, message)
        self.code = code
        self.details = details or {}


def finite_number(value, label, minimum=None, maximum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(label + " must be a number")
    try:
        result = float(value)
    except OverflowError:
        raise ValueError(label + " must be finite")
    if math.isnan(result) or math.isinf(result):
        raise ValueError(label + " must be finite")
    if minimum is not None and result < minimum or maximum is not None and result > maximum:
        raise ValueError(label + " is outside the supported range")
    return result


def strict_index(value, label, count=None):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(label + " must be a nonnegative integer")
    if count is not None and value >= count:
        raise IndexError(label + " out of range")
    return value


def same_live_object(left, right):
    if left is right:
        return True
    try:
        return bool(left == right)
    except Exception:
        return False


def values_equal(left, right):
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        a, b = finite_number(left, "readback"), finite_number(right, "expected")
        return abs(a - b) <= max(1e-6, 1e-5 * max(abs(a), abs(b)))
    return same_live_object(left, right)


def preflight_changes(changes):
    if not isinstance(changes, (list, tuple)) or len(changes) > MAX_MUTATION_FIELDS:
        raise ValueError("Mutation has too many fields")
    snapshots = []
    seen = set()
    for owner, attr, value in changes:
        key = (id(owner), attr)
        if key in seen:
            raise ValueError("Duplicate mutation field")
        seen.add(key)
        old = getattr(owner, attr)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            finite_number(value, attr)
        snapshots.append((owner, attr, old, value))
    return snapshots


def apply_changes(changes):
    """Synchronous verified setter for properties with immediate host readback."""
    snapshots = preflight_changes(changes)
    attempted = []
    try:
        for owner, attr, old, value in snapshots:
            attempted.append((owner, attr, old))
            setattr(owner, attr, value)
            if not values_equal(getattr(owner, attr), value):
                raise ValueError("Readback mismatch for " + attr)
    except Exception as error:
        failures = []
        for owner, attr, old in reversed(attempted):
            try:
                setattr(owner, attr, old)
                if not values_equal(getattr(owner, attr), old):
                    raise ValueError("restore readback mismatch")
            except Exception as restore_error:
                failures.append({"field": attr, "message": str(restore_error)})
        raise CommandFailure("mutation_failed", str(error), {
            "rollback_complete": not failures, "rollback_failures": failures,
            "attempted_fields": len(attempted)})
    return {"changed_fields": len(snapshots), "verified": True}


# Safety categories adapted from PR #155; strict validation and host enforcement.
SAFETY_CATEGORIES = ("delete", "playback", "mixer", "routing", "structure", "edit", "undo")
SAFETY_COMMANDS = {
    "delete": set(("delete_track", "delete_clip", "clear_notes_from_clip", "delete_device", "delete_scene", "remove_notes", "delete_arrangement_clip", "clear_drum_pad")),
    "playback": set(("start_playback", "stop_playback", "fire_clip", "stop_clip", "fire_scene", "stop_all_clips", "jump_to_cue")),
    "mixer": set(("set_track_mixer", "set_rack_chain")),
    "routing": set(("set_track_routing", "set_track_monitoring", "set_device_routing")),
    "structure": set(("create_midi_track", "create_audio_track", "create_clip", "create_audio_clip", "duplicate_track", "create_return_track", "create_scene", "duplicate_scene", "move_device", "load_browser_item", "load_instrument_or_effect", "map_rack_magnitude", "duplicate_session_clip_to_arrangement", "insert_device", "insert_rack_chain", "copy_drum_pad")),
    "undo": set(("undo", "redo")),
}


def validate_safety_config(raw):
    if not isinstance(raw, dict):
        raise ValueError("Safety configuration must be an object")
    allowed = set(("read_only", "allow", "saved_set_allow", "deny_commands", "allow_commands"))
    if set(raw) - allowed:
        raise ValueError("Unknown safety configuration fields")
    cfg = {"read_only": False, "allow": dict((c, c != "delete") for c in SAFETY_CATEGORIES),
           "saved_set_allow": {"delete": False}, "deny_commands": [], "allow_commands": []}
    if "read_only" in raw:
        if type(raw["read_only"]) is not bool:
            raise ValueError("read_only must be a JSON boolean")
        cfg["read_only"] = raw["read_only"]
    for key in ("allow", "saved_set_allow"):
        if key not in raw:
            continue
        value = raw[key]
        if not isinstance(value, dict) or set(value) - set(SAFETY_CATEGORIES):
            raise ValueError(key + " must be an object with known categories")
        if any(type(on) is not bool for on in value.values()):
            raise ValueError(key + " values must be JSON booleans")
        cfg[key].update(value)
    for key in ("deny_commands", "allow_commands"):
        if key in raw:
            value = raw[key]
            if not isinstance(value, list) or any(not isinstance(c, str) or c not in SCRIPT_CAPABILITIES for c in value):
                raise ValueError(key + " must be a list of known command names")
            cfg[key] = list(value)
    return cfg


def load_safety_config():
    explicit = os.environ.get("ABLETON_MCP_SAFETY_CONFIG")
    path = explicit or os.path.join(os.path.expanduser("~"), ".config", "ableton-mcp", "safety.json")
    if not explicit and not os.path.exists(path):
        return validate_safety_config({})
    with open(path, "r") as source:
        text = source.read(65537)
    if len(text) > 65536:
        raise ValueError("Safety configuration exceeds 64 KiB")
    return validate_safety_config(json.loads(text))


_WAIT_FOR_TICK = object()


class DeferredOperation(object):
    """Owned by one request; advanced only from the bounded display callback."""
    def __init__(self, step, cleanup=None, max_ticks=50):
        self.step = step
        self.cleanup = cleanup
        self.max_ticks = max_ticks
        self.ticks = 0
        self.end_undo = None
        self.closed = False

    def poll(self):
        self.ticks += 1
        if self.ticks > self.max_ticks:
            raise CommandFailure("completion_timeout", "Host completion was not observed; outcome unknown; do not automatically retry")
        return self.step()

    def close(self, failed=False):
        if self.closed:
            return
        self.closed = True
        try:
            if self.cleanup:
                self.cleanup(failed)
        finally:
            if self.end_undo:
                self.end_undo()


class _CommandRequest(object):
    def __init__(self, command, deadline, client=None):
        self.client = client
        self.command = command
        self.deadline = deadline
        self.completed = threading.Event()
        self._lock = threading.Lock()
        self._state = "pending"
        self.response = None

    def begin(self):
        with self._lock:
            if self._state != "pending":
                return False
            if _command_clock() >= self.deadline:
                self._cancel("Timeout waiting for operation to complete")
                return False
            self._state = "running"
            return True

    def complete(self, response):
        with self._lock:
            if self._state == "running":
                self._state = "complete"
                self.response = response
                self.completed.set()

    def _cancel(self, message):
        if self._state in ("complete", "cancelled"):
            return
        if self._state == "running":
            message += "; operation started, outcome unknown; do not automatically retry"
        else:
            message += "; command not executed"
        self._state = "cancelled"
        self.response = {"status": "error", "message": message}
        self.completed.set()

    def cancel(self, message):
        with self._lock:
            self._cancel(message)


# ── Note validation (pure; no Live dependency so it can be unit-tested) ──────

# Defaults for fields a note dict may omit. release_velocity 64 is the MIDI
# standard "no release velocity" value and what Live itself writes.
NOTE_DEFAULTS = {
    "start_time": 0.0,
    "duration": 0.25,
    "velocity": 100.0,
    "mute": False,
    "probability": 1.0,
    "velocity_deviation": 0.0,
    "release_velocity": 64.0,
}

# Fields that only the modern add_new_notes API can store; the legacy
# set_notes tuple carries pitch/start/duration/velocity/mute only.
EXTENDED_NOTE_FIELDS = ("probability", "velocity_deviation", "release_velocity")


def _is_number(value):
    # bool is an int subclass; True as a velocity is a caller bug, not 1.
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_finite(value):
    """False for NaN, +/-inf, and ints too large to convert to float."""
    try:
        value = float(value)
    except OverflowError:
        return False
    return value == value and value not in (float("inf"), float("-inf"))


def _short_repr(value, limit=40):
    """repr() for error messages that cannot itself fail or flood the log.

    Python 3.11+ refuses to repr ints with more than ~4300 digits.
    """
    try:
        text = repr(value)
    except Exception:
        return "<%s too large to display>" % type(value).__name__
    return text if len(text) <= limit else text[:limit] + "..."


def normalize_note_specs(notes):
    """Validate note dicts and fill defaults.

    Returns a list of dicts with exactly the keys pitch, start_time, duration,
    velocity, mute, probability, velocity_deviation, release_velocity.
    Unknown keys (e.g. note_id from get_clip_notes) are ignored.

    Raises ValueError naming the first offending note and field. Out-of-range
    values are rejected, never clamped: a silently corrected note is exactly
    the kind of agent/UI mismatch this is meant to prevent.
    """
    if not isinstance(notes, (list, tuple)):
        raise ValueError("notes must be a list of note objects")

    def fail(i, msg):
        raise ValueError("Invalid note at index %d: %s" % (i, msg))

    def number(i, note, key, lo=None, hi=None, lo_open=False):
        value = note.get(key, NOTE_DEFAULTS.get(key))
        if not _is_number(value):
            fail(i, "%s must be a number, got %s" % (key, _short_repr(value)))
        if not _is_finite(value):
            fail(i, "%s must be a finite number, got %s" % (key, _short_repr(value)))
        value = float(value)
        if lo is not None and (value <= lo if lo_open else value < lo):
            fail(i, "%s must be %s %s, got %s"
                 % (key, ">" if lo_open else ">=", lo, _short_repr(note.get(key))))
        if hi is not None and value > hi:
            fail(i, "%s must be <= %s, got %s" % (key, hi, _short_repr(note.get(key))))
        return value

    if len(notes) > 10000:
        raise ValueError("At most 10000 notes may be written per command")
    result = []
    for i, note in enumerate(notes):
        if not isinstance(note, dict):
            fail(i, "expected an object, got %s" % _short_repr(note))
        if "pitch" not in note:
            fail(i, "pitch is required")
        pitch = note["pitch"]
        # Ints need no conversion (a huge one simply fails the range check).
        # Floats are checked for finiteness before int(): int() raises its own
        # ValueError/OverflowError on NaN/inf, losing the index and field name.
        if not _is_number(pitch) or (
                isinstance(pitch, float)
                and (not _is_finite(pitch) or pitch != int(pitch))):
            fail(i, "pitch must be an integer, got %s" % _short_repr(pitch))
        pitch = int(pitch)
        if pitch < 0 or pitch > 127:
            fail(i, "pitch must be in 0..127, got %s" % _short_repr(pitch))

        mute = note.get("mute", NOTE_DEFAULTS["mute"])
        if isinstance(mute, bool):
            pass
        elif _is_number(mute) and mute in (0, 1):
            mute = bool(mute)
        else:
            fail(i, "mute must be a boolean, got %s" % _short_repr(mute))

        result.append({
            "pitch": pitch,
            "start_time": number(i, note, "start_time"),
            "duration": number(i, note, "duration", lo=0.0, lo_open=True),
            "velocity": number(i, note, "velocity", lo=0, hi=127),
            "mute": mute,
            "probability": number(i, note, "probability", lo=0, hi=1),
            "velocity_deviation": number(i, note, "velocity_deviation", lo=-127, hi=127),
            "release_velocity": number(i, note, "release_velocity", lo=0, hi=127),
        })
    return result


def extended_fields_in(notes):
    """Extended field names the caller set explicitly on any note."""
    present = set()
    for note in notes:
        if isinstance(note, dict):
            for key in EXTENDED_NOTE_FIELDS:
                if key in note:
                    present.add(key)
    return sorted(present)


def step_sequencer_error(midi_clip_type):
    kind = ("a Step Sequencer clip" if midi_clip_type == 1
            else "not a standard MIDI clip")
    return ("Clip is %s (midi_clip_type=%s); notes written via the Live API "
            "are stored invisibly (not shown or played). Convert the clip to "
            "MIDI first." % (kind, midi_clip_type))


def create_instance(c_instance):
    """Create and return the AbletonMCP script instance"""
    return AbletonMCP(c_instance)

class AbletonMCP(ControlSurface):
    """AbletonMCP Remote Script for Ableton Live"""
    
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
        
        # Cache the song reference for easier access
        self._song = self.song()

        # Passive human-UI event queue (drained by MCP → Supabase)
        self._passive_events = []
        self._passive_lock = threading.Lock()
        self._passive_max = 500
        self._passive_track_count = None
        self._passive_track_bindings = []  # (track, [(add_name, callback), ...]) for cleanup
        self._song_passive_callbacks = []
        
        self._initialize_command_dispatch()

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
        self._shutdown_commands()

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
                    
                    with self._command_lock:
                        if self._command_stopped:
                            client.close()
                            break
                        self._clients.add(client)

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

                    self.log_message("Received command: " + str(command.get("type", "unknown") if isinstance(command, dict) else "invalid"))

                    # Process the command and get response
                    response = self._process_command(command, client=client)

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
            with self._command_lock:
                self._clients.discard(client)
            try:
                client.close()
            except:
                pass
            self.log_message("Client handler stopped")
    
    def _initialize_command_dispatch(self):
        """Called during Live's main-thread control-surface construction."""
        self._command_thread = threading.current_thread().ident
        self._command_queue = queue.Queue(maxsize=MAX_PENDING_COMMANDS)
        self._command_lock = threading.Lock()
        self._command_requests = set()
        self._command_stopped = False
        self._active_deferred = None
        self._background_deferred = []
        self._clients = set()

    def update_display(self):
        """Live calls this on its main thread; socket workers only enqueue."""
        ControlSurface.update_display(self)
        self._drain_commands()

    def _advance_operation(self, request, operation):
        if request.completed.is_set() or self._command_stopped or self._client_disconnected(request.client) or _command_clock() >= request.deadline:
            request.cancel("Deferred operation cancelled")
            try:
                operation.close(failed=True)
            except Exception as error:
                self._log_command_error("Deferred cancellation cleanup failed", error)
            return True
        try:
            result = operation.poll()
            if result is _WAIT_FOR_TICK:
                return False
            operation.close()
            request.complete({"status": "success", "result": result})
        except Exception as error:
            response = self._command_error_response(request.command.get("type"), error)
            try:
                operation.close(failed=True)
            except Exception as cleanup_error:
                response["error"]["details"]["cleanup_error"] = str(cleanup_error)
                response["error"]["details"]["rollback_complete"] = False
            request.complete(response)
        return True

    def _drain_commands(self):
        if threading.current_thread().ident != self._command_thread:
            raise RuntimeError("Command queue must be drained on Live's main thread")
        # Read-only background jobs yield to normal requests and rotate fairly.
        for _ in range(min(4, len(self._background_deferred))):
            pair = self._background_deferred.pop(0)
            if not self._advance_operation(*pair): self._background_deferred.append(pair)
        if self._active_deferred is not None:
            if self._advance_operation(*self._active_deferred): self._active_deferred = None
            return
        for _ in range(MAX_COMMANDS_PER_TICK):
            try:
                request = self._command_queue.get_nowait()
            except queue.Empty:
                break
            if self._client_disconnected(request.client):
                request.cancel("Client disconnected")
            elif request.begin():
                result = self._execute_command(request.command)
                if isinstance(result, DeferredOperation):
                    if result.exclusive:
                        self._active_deferred = (request, result)
                        break
                    self._background_deferred.append((request, result))
                else:
                    request.complete(result)


    def _shutdown_commands(self):
        with self._command_lock:
            self._command_stopped = True
            self._target_identities = []
            for request in self._command_requests:
                request.cancel("Remote Script disconnected")
            clients = list(self._clients)
        active = self._active_deferred
        self._active_deferred = None
        if active is not None:
            try:
                active[1].close(failed=True)
            except Exception as error:
                self._log_command_error("Shutdown cleanup failed", error)
        background = self._background_deferred
        self._background_deferred = []
        for request, operation in background:
            try: operation.close(failed=True)
            except Exception as error: self._log_command_error("Background cleanup failed", error)
        # Wake workers blocked in recv(), without joining them on Live's thread.
        for client in clients:
            try:
                client.shutdown(socket.SHUT_RDWR)
            except (OSError, AttributeError):
                pass
            try:
                client.close()
            except OSError:
                pass

    def _client_disconnected(self, client):
        if client is None:
            return False
        try:
            readable, _, _ = select.select([client], [], [], 0)
            return bool(readable) and not client.recv(1, socket.MSG_PEEK)
        except (OSError, ValueError):
            return True

    def _process_command(self, command, client=None):
        """Wait on a bounded main-thread handoff, never execute on a worker."""
        if threading.current_thread().ident == self._command_thread:
            return {"status": "error", "message": "Command handoff requires a socket worker"}
        if not isinstance(command, dict):
            return {"status": "error", "message": "Command must be an object"}
        timeout = LONG_COMMAND_TIMEOUT if command.get("type") == "create_audio_clip" else COMMAND_TIMEOUT
        request = _CommandRequest(command, _command_clock() + timeout, client)
        with self._command_lock:
            if self._command_stopped:
                return {"status": "error", "message": "Remote Script disconnected"}
            if len(self._command_requests) >= MAX_PENDING_COMMANDS:
                return {"status": "error", "message": "Main-thread command queue is full; command not executed"}
            try:
                self._command_queue.put_nowait(request)
            except queue.Full:
                return {"status": "error", "message": "Main-thread command queue is full; command not executed"}
            self._command_requests.add(request)
        try:
            while not request.completed.is_set():
                if self._client_disconnected(client):
                    request.cancel("Client disconnected")
                    break
                remaining = request.deadline - _command_clock()
                if remaining <= 0:
                    request.cancel("Timeout waiting for operation to complete")
                    break
                request.completed.wait(min(0.05, remaining))
            return request.response
        finally:
            with self._command_lock:
                self._command_requests.discard(request)

    def _log_command_error(self, context, error):
        self.log_message("{0}: {1}".format(context, error))
        if not isinstance(error, EXPECTED_COMMAND_ERRORS):
            self.log_message(traceback.format_exc())

    def _check_safety(self, command_type, category=None):
        mutating = self._is_mutating_command(command_type) or category is not None
        try:
            cfg = load_safety_config()
        except Exception as error:
            if mutating:
                raise CommandFailure("safety_refused", "Invalid safety configuration: " + str(error))
            return
        if command_type in cfg["deny_commands"]:
            raise CommandFailure("safety_refused", "Command is denied by safety configuration")
        if not mutating:
            return
        category = category or next((c for c, names in SAFETY_COMMANDS.items() if command_type in names), "edit")
        if cfg["read_only"] or not cfg["allow"][category]:
            raise CommandFailure("safety_refused", "Safety policy refuses " + category)
        if cfg["saved_set_allow"].get(category) is False:
            # Unknown saved state is treated as saved, never as permission.
            path = getattr(self._song, "file_path", None)
            if path is None or path != "":
                raise CommandFailure("safety_refused", "Safety policy refuses this operation in saved or unknown sets")


    def _command_error_response(self, command_type, error):
        self._log_command_error("Error processing " + str(command_type), error)
        code = getattr(error, "code", "invalid_request" if isinstance(error, (ValueError, IndexError)) else "execution_failed")
        return {"status": "error", "message": str(error), "error": {
            "code": code, "command": command_type, "details": getattr(error, "details", {})}}

    def _is_mutating_command(self, command_type):
        if isinstance(command_type, str) and command_type in INTEGRATION_COMMANDS:
            return INTEGRATION_COMMANDS[command_type][1]
        return command_type in SCRIPT_CAPABILITIES and not (
            command_type.startswith("get_") or command_type in ("inspect_rack", "drain_passive_events"))

    def _execute_command(self, command):
        command_type = command.get("type") if isinstance(command, dict) else None
        begin = end = None
        if self._is_mutating_command(command_type) and command_type not in ("undo", "redo"):
            song = getattr(self, "_song", None)
            begin = getattr(song, "begin_undo_step", None)
            end = getattr(song, "end_undo_step", None)
        opened = False
        deferred = False
        try:
            self._check_safety(command_type)
            if callable(begin) and callable(end):
                begin()
                opened = True
            response = self._execute_command_body(command)
            operation = response.get("result") if response.get("status") == "success" else None
            if isinstance(operation, DeferredOperation):
                operation.exclusive = self._is_mutating_command(command_type)
                operation.end_undo = end if opened else None
                deferred = True
                return operation
            return response
        except Exception as error:
            return self._command_error_response(command_type, error)
        finally:
            if opened and not deferred:
                try:
                    end()
                except Exception as error:
                    return self._command_error_response(command_type, error)



    def _execute_command_body(self, command):
        """Process a command from the client and return a response"""
        if not isinstance(command, dict) or not isinstance(command.get("type"), str) or not isinstance(command.get("params", {}), dict):
            return {"status": "error", "message": "Command requires a string type and object params"}
        command_type = command.get("type", "")
        params = command.get("params", {})
        
        # Initialize response
        response = {
            "status": "success",
            "result": {}
        }
        
        try:
            # Route the command to the appropriate handler
            if command_type in INTEGRATION_COMMANDS:
                response["result"] = getattr(self, INTEGRATION_COMMANDS[command_type][0])(params)
            elif command_type == "get_locators":
                response["result"] = self._get_locators(params)
            elif command_type == "get_target_identity":
                response["result"] = self._get_target_identity(params)
            elif command_type == "get_script_info":
                response["result"] = self._get_script_info()
            elif command_type == "get_session_info":
                response["result"] = self._get_session_info()
            elif command_type == "get_track_info":
                track_index = params.get("track_index", 0)
                response["result"] = self._get_track_info(track_index)
            elif command_type == "create_midi_track":
                index = params.get("index", -1)
                response["result"] = self._create_midi_track(index)
            elif command_type == "create_audio_track":
                index = params.get("index", -1)
                response["result"] = self._create_audio_track(index)
            elif command_type == "set_track_name":
                track_index = params.get("track_index", 0)
                name = params.get("name", "")
                response["result"] = self._set_track_name(track_index, name)
            elif command_type == "create_clip":
                track_index = params.get("track_index", 0)
                clip_index = params.get("clip_index", 0)
                length = params.get("length", 4.0)
                response["result"] = self._create_clip(track_index, clip_index, length)
            elif command_type == "create_audio_clip":
                track_index = params.get("track_index", 0)
                clip_index = params.get("clip_index", 0)
                path = params.get("path", "")
                response["result"] = self._create_audio_clip(track_index, clip_index, path)
            elif command_type == "add_notes_to_clip":
                track_index = params.get("track_index", 0)
                clip_index = params.get("clip_index", 0)
                notes = params.get("notes", [])
                response["result"] = self._add_notes_to_clip(track_index, clip_index, notes)
            elif command_type == "clear_notes_from_clip":
                track_index = params.get("track_index", 0)
                clip_index = params.get("clip_index", 0)
                response["result"] = self._clear_notes_from_clip(track_index, clip_index)
            elif command_type == "set_clip_name":
                track_index = params.get("track_index", 0)
                clip_index = params.get("clip_index", 0)
                name = params.get("name", "")
                response["result"] = self._set_clip_name(track_index, clip_index, name)
            elif command_type == "set_arrangement_clip_name":
                track_index = params.get("track_index", 0)
                clip_index = params.get("clip_index", 0)
                name = params.get("name", "")
                response["result"] = self._set_arrangement_clip_name(track_index, clip_index, name)
            elif command_type == "set_tempo":
                tempo = params.get("tempo", 120.0)
                response["result"] = self._set_tempo(tempo)
            elif command_type == "fire_clip":
                track_index = params.get("track_index", 0)
                clip_index = params.get("clip_index", 0)
                response["result"] = self._fire_clip(track_index, clip_index)
            elif command_type == "stop_clip":
                track_index = params.get("track_index", 0)
                clip_index = params.get("clip_index", 0)
                response["result"] = self._stop_clip(track_index, clip_index)
            elif command_type == "delete_clip":
                track_index = params.get("track_index", 0)
                clip_index = params.get("clip_index", 0)
                response["result"] = self._delete_clip(track_index, clip_index)
            elif command_type == "start_playback":
                response["result"] = self._start_playback()
            elif command_type == "stop_playback":
                response["result"] = self._stop_playback()
            elif command_type == "load_instrument_or_effect":
                track_index = params.get("track_index", 0)
                uri = params.get("uri", "")
                response["result"] = self._load_instrument_or_effect(track_index, uri)
            elif command_type == "load_browser_item":
                track_index = params.get("track_index", 0)
                item_uri = params.get("item_uri", "")
                response["result"] = self._load_browser_item(track_index, item_uri)
            # ── Arrangement view commands ──────────────────────────────
            elif command_type == "switch_to_arrangement_view":
                response["result"] = self._switch_to_arrangement_view()
            elif command_type == "set_current_song_time":
                time_val = params.get("time", 0.0)
                response["result"] = self._set_current_song_time(time_val)
            elif command_type == "duplicate_session_clip_to_arrangement":
                track_index = params.get("track_index", 0)
                clip_index = params.get("clip_index", 0)
                destination_time = params.get("destination_time", 0.0)
                response["result"] = self._duplicate_session_clip_to_arrangement(
                    track_index, clip_index, destination_time)
            elif command_type == "map_rack_magnitude":
                track_index = params.get("track_index", 0)
                device_index = params.get("device_index", 0)
                macro_name = params.get("macro_name", "Magnitude")
                response["result"] = self._map_rack_magnitude(
                    track_index, device_index, macro_name)
            elif command_type == "inspect_rack":
                track_index = params.get("track_index", 0)
                device_index = params.get("device_index", 0)
                response["result"] = self._inspect_rack(track_index, device_index)
            elif command_type == "create_locator":
                name = params.get("name", "")
                time_val = params.get("time", 0.0)
                response["result"] = self._create_locator(name, time_val)

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
            # Read-only arrangement command
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
                response["result"] = self._get_device_parameters(track_index, device_index)
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
                response["result"] = self._set_device_parameter(
                    params.get("track_index", 0),
                    params.get("device_index", 0),
                    params.get("parameter_index", 0),
                    params.get("value", 0.0),
                )
            else:
                response["status"] = "error"
                response["message"] = "Unknown command: " + command_type
        except Exception as e:
            return self._command_error_response(command_type, e)

        return response

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
        except (AttributeError, TypeError, ValueError, RuntimeError, OverflowError):
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
                # Read via _safe_song_property so an attribute missing on a
                # given Live version falls back to its default.
                "is_playing":        self._safe_song_property("is_playing",        bool,  False),
                "current_song_time": self._safe_song_property("current_song_time", float, 0.0),
                "song_length":       self._safe_song_property("song_length",       float, 0.0),
                "loop":              self._safe_song_property("loop",              bool,  False),
                "loop_start":        self._safe_song_property("loop_start",        float, 0.0),
                "loop_length":       self._safe_song_property("loop_length",       float, 0.0),
            }
            result.update({
                "root_note": self._safe_song_property("root_note", int, None),
                "scale_name": self._safe_song_property("scale_name", str, None),
                "name": self._safe_song_property("name", str, "Untitled"),
            })
            result["master_track"].update(self._output_meters(self._song.master_track))
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
                
                if clip_info is not None:
                    clip_info.update(self._clip_type_info(clip))

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
            result.update(self._output_meters(track))
            return result
        except Exception as e:
            self.log_message("Error getting track info: " + str(e))
            raise
    
    def _output_meters(self, track):
        """Read Live Track output meters; unsupported/invalid values are null."""
        result = {}
        for name in ("output_meter_left", "output_meter_right", "output_meter_level"):
            try:
                value = float(getattr(track, name))
                if math.isnan(value) or math.isinf(value) or not 0.0 <= value <= 1.0:
                    value = None
            except (AttributeError, RuntimeError, TypeError, ValueError, OverflowError):
                value = None
            result[name] = value
        return result

    def _cmd_get_transport(self, params):
        song = self._song
        result = {"supported_settings": []}
        keys = ("tempo", "signature_numerator", "signature_denominator", "metronome", "overdub", "arrangement_overdub", "groove_amount", "swing_amount", "root_note", "scale_mode")
        for key in keys + ("is_playing", "current_song_time", "loop", "loop_start", "loop_length"):
            try:
                value = getattr(song, key)
                if isinstance(value, (int, float)) and not isinstance(value, bool): finite_number(value, key)
                result[key] = value
                if key in keys: result["supported_settings"].append(key)
            except (AttributeError, RuntimeError, ValueError) as error:
                result[key] = None
                result.setdefault("unavailable", {})[key] = str(error)
        return result

    def _cmd_set_song_settings(self, params):
        bools = {"metronome", "overdub", "arrangement_overdub", "scale_mode"}
        numbers = {"tempo": (20,999), "groove_amount": (0,1.31), "swing_amount": (0,1)}
        integers = {"signature_numerator", "signature_denominator", "root_note"}
        if not params or set(params) - bools - set(numbers) - integers:
            raise ValueError("Unknown or empty song settings; loop/warp and recording writes are not supported here")
        changes = []
        for key, value in params.items():
            try: getattr(self._song, key)
            except (AttributeError, RuntimeError): raise ValueError(key + " is unsupported on this host")
            if key in bools:
                if type(value) is not bool: raise ValueError(key + " must be boolean")
            elif key in numbers:
                value = finite_number(value, key, *numbers[key])
            else:
                value = strict_index(value, key)
                if key == "signature_numerator" and not 1 <= value <= 99: raise ValueError("Numerator must be 1..99")
                if key == "signature_denominator" and value not in (1,2,4,8,16): raise ValueError("Denominator must be 1,2,4,8 or 16")
                if key == "root_note" and value > 11: raise ValueError("root_note must be 0..11")
            changes.append((self._song, key, value))
        return self._transaction(changes, lambda: self._cmd_get_transport({}))

    def _cmd_jump_to_cue(self, params):
        cues = self._song.cue_points
        index = strict_index(params.get("cue_index"), "cue_index", len(cues))
        cue = cues[index]
        self._check_identity(cue, params.get("cue_id"), True)
        return self._set_current_song_time(cue.time)

    def _cmd_stop_all_clips(self, params):
        self._song.stop_all_clips()
        return {"stop_requested": True}

    def _set_current_song_time(self, time_val):
        value = finite_number(time_val, "time", 0, 1e9)
        if self._song.is_playing: raise ValueError("Stop playback before a verified playhead seek")
        return self._transaction([(self._song, "current_song_time", value)],
                                 lambda: {"time": float(self._song.current_song_time)})

    def _set_tempo(self, tempo):
        value = finite_number(tempo, "tempo", 20, 999)
        return self._transaction([(self._song, "tempo", value)], lambda: {"tempo": float(self._song.tempo)})

    def _start_playback(self):
        self._song.start_playing()
        return DeferredOperation(lambda: {"is_playing": True} if self._song.is_playing else _WAIT_FOR_TICK, max_ticks=20)

    def _stop_playback(self):
        self._song.stop_playing()
        return DeferredOperation(lambda: {"is_playing": False} if not self._song.is_playing else _WAIT_FOR_TICK, max_ticks=20)


    def _cmd_get_tracks_overview(self, params):
        limit = strict_index(params.get("limit", 128), "limit")
        if not 1 <= limit <= 128: raise ValueError("limit must be 1..128")
        tracks = self._song.tracks
        result = []
        for i, track in enumerate(tracks[:limit]):
            slots = track.clip_slots
            result.append(self._target_record(track, track_index=i,
                type="audio" if track.has_audio_input else "midi" if track.has_midi_input else "other",
                clips=sum(1 for slot in slots[:128] if slot.has_clip), clips_truncated=len(slots)>128,
                devices=len(track.devices), mute=bool(track.mute), solo=bool(track.solo), arm=self._safe_arm(track)))
        return {"tempo": float(self._song.tempo), "track_count": len(tracks), "tracks": result, "truncated": len(tracks)>limit}

    def _cmd_check_arrangement_sync(self, params):
        bar = finite_number(params.get("bar_beats", 4.0), "bar_beats", .001, 128)
        tracks = self._song.tracks
        state = {"bar_beats": bar, "tracks_with_clips": 0, "total_clips": 0, "off_grid": 0, "overlaps": 0, "gaps": 0,
                 "problems": [], "truncated": len(tracks)>128, "unavailable_tracks": []}
        iterator = iter(enumerate(tracks[:128]))
        deadline = _command_clock() + 5.0
        def finish():
            state["in_sync"] = None if state["truncated"] or state["unavailable_tracks"] else state["off_grid"] == 0 and state["overlaps"] == 0
            return state
        def step():
            if _command_clock() >= deadline:
                state["truncated"] = True; return finish()
            try: index, track = next(iterator)
            except StopIteration: return finish()
            try: collection = track.arrangement_clips
            except (AttributeError, RuntimeError):
                state["unavailable_tracks"].append(index); return _WAIT_FOR_TICK
            remaining = 1024 - state["total_clips"]
            if remaining <= 0:
                state["truncated"] = True; return finish()
            limit = min(128, remaining)
            if len(collection)>limit: state["truncated"] = True
            clips = sorted(collection[:limit], key=lambda clip: clip.start_time)
            if clips: state["tracks_with_clips"] += 1
            previous_end = None
            for clip in clips:
                start = finite_number(clip.start_time, "clip start")
                end = finite_number(clip.end_time, "clip end", start)
                state["total_clips"] += 1
                if abs(start/bar - round(start/bar)) > 1e-4:
                    state["off_grid"] += 1
                    if len(state["problems"])<20: state["problems"].append({"track_index":index,"clip":str(clip.name)[:256],"issue":"off_grid","start":start})
                if previous_end is not None:
                    delta=start-previous_end
                    if delta>1e-4: state["gaps"]+=1
                    elif delta < -1e-4:
                        state["overlaps"]+=1
                        if len(state["problems"])<20: state["problems"].append({"track_index":index,"clip":str(clip.name)[:256],"issue":"overlap","start":start})
                previous_end = end if previous_end is None else max(previous_end,end)
            return _WAIT_FOR_TICK
        return DeferredOperation(step, max_ticks=130)


    def _cmd_search_browser(self, params):
        query = params.get("query")
        if not isinstance(query, str) or not query.strip() or len(query) > 256: raise ValueError("query must be 1..256 characters")
        max_results = strict_index(params.get("max_results", 20), "max_results")
        max_nodes = strict_index(params.get("max_nodes", 1500), "max_nodes")
        max_depth = strict_index(params.get("max_depth", 12), "max_depth")
        max_ms = finite_number(params.get("max_ms", 2000), "max_ms", 10, 5000)
        if not 1 <= max_results <= 100 or not 1 <= max_nodes <= 1500 or max_depth > 12: raise ValueError("Browser search limit out of range")
        categories = ("instruments", "sounds", "drums", "audio_effects", "midi_effects", "plugins", "packs", "samples", "max_for_live", "user_library")
        category = params.get("category")
        if category is not None and category not in categories: raise ValueError("Unknown browser category")
        browser = self.application().browser
        roots, unavailable = [], []
        for name in ((category,) if category else categories):
            try: roots.append((getattr(browser, name), name, 0))
            except (AttributeError, RuntimeError): unavailable.append(name)
        stack = [iter(roots)]
        state = {"visited": 0, "results": [], "truncated": False, "reason": None}
        deadline = _command_clock() + max_ms / 1000.0
        def result(reason=None):
            return {"results": state["results"], "visited": state["visited"], "truncated": state["truncated"] or reason is not None,
                    "reason": reason or state["reason"], "unavailable_categories": unavailable}
        def step():
            tick_deadline = _command_clock() + .005
            for _ in range(32):
                if _command_clock() >= deadline: return result("time_limit")
                if _command_clock() >= tick_deadline: return _WAIT_FOR_TICK
                if state["visited"] >= max_nodes: return result("node_limit")
                if len(state["results"]) >= max_results: return result("result_limit")
                if not stack: return result()
                try: item, path, depth = next(stack[-1])
                except StopIteration:
                    stack.pop(); continue
                state["visited"] += 1
                try:
                    name = str(item.name)
                    if query.lower() in name.lower():
                        state["results"].append({"name": name[:256], "path": path[:1024], "uri": str(getattr(item, "uri", ""))[:2048], "is_loadable": bool(getattr(item, "is_loadable", False))})
                    if depth >= max_depth:
                        state["truncated"] = True; state["reason"] = "depth_limit"
                    else:
                        # Capture parent path/depth now; do not close over mutable loop variables.
                        def children(source, parent_path, parent_depth):
                            for child in source:
                                yield child, parent_path + "/" + str(child.name)[:256], parent_depth + 1
                        stack.append(iter(children(getattr(item, "children", ()), path, depth)))
                except (AttributeError, RuntimeError):
                    state["truncated"] = True; state["reason"] = "unavailable_node"
            return _WAIT_FOR_TICK
        return DeferredOperation(step, max_ticks=100)


    def _addressed_clip(self, params, writing=False):
        track, kind, index = self._resolve_track(params, writing)
        if kind != "track": raise ValueError("Clips require a regular track")
        location = params.get("location")
        if location not in ("session", "arrangement"):
            raise ValueError("An explicit location (session or arrangement) is required")
        clip_index = strict_index(params.get("clip_index"), "clip_index")
        if location == "session":
            slots = track.clip_slots
            slot = slots[strict_index(clip_index, "clip_index", len(slots))]
            if not slot.has_clip: raise ValueError("Session slot is empty")
            clip = slot.clip
        else:
            try: clips = track.arrangement_clips
            except (AttributeError, RuntimeError): raise ValueError("Arrangement addressing is unsupported on this host")
            clip = clips[strict_index(clip_index, "clip_index", len(clips))]
        self._check_identity(clip, params.get("clip_id"), writing)
        if not getattr(clip, "is_midi_clip", False): raise ValueError("Clip is not MIDI")
        self._checked_midi_clip_type_for_write(clip)
        return clip

    def _bounded_native_notes(self, clip):
        method = getattr(clip, "get_all_notes_extended", None)
        if not callable(method): raise ValueError("Stable note IDs are unsupported on this host")
        notes = method()
        if len(notes) > 10000: raise ValueError("Clip exceeds 10000-note limit")
        return notes

    def _native_note_dict(self, note):
        result = {"note_id": int(note.note_id)}
        for field in ("pitch", "start_time", "duration", "velocity", "mute", "probability", "velocity_deviation", "release_velocity"):
            if hasattr(note, field): result[field] = getattr(note, field)
        return result

    def _cmd_get_notes(self, params):
        clip = self._addressed_clip(params)
        notes = self._bounded_native_notes(clip)
        return self._target_record(clip, location=params["location"], clip_index=params["clip_index"],
                                  notes=[self._native_note_dict(n) for n in notes], count=len(notes))

    def _cmd_modify_notes(self, params):
        edits = params.get("notes")
        if not isinstance(edits, list) or not 1 <= len(edits) <= 10000:
            raise ValueError("notes must contain 1..10000 ID-addressed edits")
        clip = self._addressed_clip(params, True)
        apply = getattr(clip, "apply_note_modifications", None)
        if not callable(apply): raise ValueError("ID-preserving note modifications are unsupported")
        native = self._bounded_native_notes(clip)
        by_id = {int(note.note_id): note for note in native}
        if len(by_id) != len(native): raise ValueError("Host returned duplicate note IDs")
        before, requested, seen = {}, {}, set()
        fields = set(NOTE_DEFAULTS) | {"pitch"}
        for edit in edits:
            if not isinstance(edit, dict): raise ValueError("Each note edit must be an object")
            nid = strict_index(edit.get("note_id"), "note_id")
            if nid in seen or nid not in by_id: raise ValueError("Duplicate or stale note_id")
            seen.add(nid)
            if set(edit) - fields - {"note_id"}: raise ValueError("Unknown note field")
            note = by_id[nid]
            original = self._native_note_dict(note)
            merged = dict(original); merged.update(edit)
            normalized = normalize_note_specs([merged])[0]
            updates = {key: normalized[key] for key in edit if key != "note_id"}
            if not updates: raise ValueError("Note edit has no changed fields")
            if any(not hasattr(note, key) for key in updates): raise ValueError("Requested note field is unsupported")
            before[nid] = {key: original[key] for key in updates}
            requested[nid] = updates
        def write_values(vector, values):
            mapping = {int(n.note_id): n for n in vector}
            if any(nid not in mapping for nid in values): raise ValueError("Note ID disappeared before restore")
            for nid, updates in values.items():
                for key, value in updates.items(): setattr(mapping[nid], key, value)
            apply(vector)
        state = {"error": None, "restoring": False}
        try: write_values(native, requested)
        except Exception as error: state["error"] = error
        def verify(values):
            current = {int(n.note_id): n for n in self._bounded_native_notes(clip)}
            for nid, updates in values.items():
                if nid not in current: raise ValueError("Note ID disappeared")
                for key, value in updates.items():
                    if not values_equal(getattr(current[nid], key), value): raise ValueError("Note readback mismatch")
        def cleanup(failed):
            if failed and not state["restoring"]:
                write_values(self._bounded_native_notes(clip), before)
        def step():
            if state["restoring"]:
                try:
                    verify(before)
                except Exception as error:
                    raise CommandFailure("note_mutation_failed", str(state["error"]), {"rollback_complete": False, "rollback_error": str(error)})
                raise CommandFailure("note_mutation_failed", str(state["error"]), {"rollback_complete": True})
            try:
                if state["error"]: raise state["error"]
                verify(requested)
                return {"modified_ids": sorted(requested), "location": params["location"], "clip_id": self._identity_for(clip)}
            except Exception as error:
                state["error"] = error; state["restoring"] = True
                try: write_values(self._bounded_native_notes(clip), before)
                except Exception as restore_error:
                    raise CommandFailure("note_mutation_failed", str(error), {"rollback_complete": False, "rollback_error": str(restore_error)})
                return _WAIT_FOR_TICK
        return DeferredOperation(step, cleanup, max_ticks=4)


    def _resolve_device(self, params, writing=False):
        track, kind, index = self._resolve_track(params, writing)
        path = params.get("device_path", [params.get("device_index", 0)])
        if not isinstance(path, list) or not path or len(path) > 9 or len(path) % 2 == 0:
            raise ValueError("device_path must be an odd-length list of device/chain indices, at most 9")
        parent = track
        device = None
        for offset, value in enumerate(path):
            if offset % 2 == 0:
                devices = parent.devices
                device = devices[strict_index(value, "device_index", len(devices))]
            else:
                if not getattr(device, "can_have_chains", False): raise ValueError("Device has no chains")
                chains = device.chains
                parent = chains[strict_index(value, "chain_index", len(chains))]
        self._check_identity(device, params.get("device_id"), writing)
        expected = params.get("expected_class")
        if expected is not None and device.class_name != expected:
            raise CommandFailure("stale_target", "Device class changed")
        return track, device, path

    def _device_record(self, device, path, budget, depth=0):
        if budget[0] <= 0: return {"truncated": True}
        budget[0] -= 1
        result = self._target_record(device, device_path=path, class_name=str(device.class_name))
        parameters = device.parameters
        result["parameters"] = [dict(self._parameter_report(p), parameter_index=i, name=str(p.name),
            parameter_id=self._identity_for(p), is_enabled=bool(getattr(p, "is_enabled", True))) for i, p in enumerate(parameters[:128])]
        result["parameters_truncated"] = len(parameters) > 128
        result["can_have_chains"] = bool(getattr(device, "can_have_chains", False))
        if result["can_have_chains"]:
            chains = device.chains
            result["chains"] = []
            if depth < 4:
                for ci, chain in enumerate(chains[:32]):
                    if budget[0] <= 0: break
                    children = []
                    for di, child in enumerate(chain.devices[:128]):
                        if budget[0] <= 0: break
                        children.append(self._device_record(child, path + [ci, di], budget, depth + 1))
                    result["chains"].append(self._target_record(chain, chain_index=ci, devices=children))
            result["chains_truncated"] = len(chains) > len(result["chains"]) or budget[0] <= 0
        return result

    def _cmd_get_device_chain(self, params):
        track, kind, index = self._resolve_track(params)
        budget = [128]
        devices = []
        for i, device in enumerate(track.devices[:128]):
            if budget[0] <= 0: break
            devices.append(self._device_record(device, [i], budget))
        return self._target_record(track, track_index=index, track_type=kind, devices=devices,
                                   truncated=budget[0] <= 0 or len(track.devices) > len(devices))

    def _parse_display(self, text):
        if not isinstance(text, str): raise ValueError("Display value must include explicit units")
        match = re.fullmatch(r"\s*([-+]?(?:\d+(?:\.\d+)?|\.\d+))\s*(Hz|kHz|ms|s|dB|%|)\s*", text, re.I)
        if not match: raise ValueError("Unsupported or ambiguous display unit")
        number = finite_number(float(match.group(1)), "display")
        unit = match.group(2).lower()
        scale, canonical = {"khz": (1000, "hz"), "ms": (.001, "s")}.get(unit, (1, unit))
        return number * scale, canonical

    def _value_for_display(self, param, wanted):
        if getattr(param, "is_quantized", False):
            items = list(param.value_items)
            matches = [i for i, item in enumerate(items) if str(item) == wanted]
            if len(matches) != 1: raise ValueError("Quantized display value is missing or ambiguous")
            return finite_number(param.min + matches[0], "parameter", param.min, param.max)
        target, unit = self._parse_display(wanted)
        def read(value):
            number, found_unit = self._parse_display(str(param.str_for_value(value)))
            if found_unit != unit: raise ValueError("Display units do not match")
            return number
        low, high = float(param.min), float(param.max)
        samples = [read(low + (high - low) * i / 32.0) for i in range(33)]
        increasing = samples[-1] > samples[0]
        if samples[-1] == samples[0] or any((b < a if increasing else b > a) for a, b in zip(samples, samples[1:])):
            raise ValueError("Nonmonotonic or ambiguous display mapping")
        if not min(samples) <= target <= max(samples): raise ValueError("Display value outside supported range")
        for _ in range(48):
            middle = (low + high) / 2
            if (read(middle) < target) == increasing: low = middle
            else: high = middle
        value = (low + high) / 2
        if abs(read(value) - target) > max(1e-6, abs(target) * .001):
            raise ValueError("Display value cannot be resolved without ambiguity")
        return value

    def _cmd_set_device_parameter_value(self, params):
        if set(params) - {"track_index", "track_type", "target_id", "expected_track_name", "device_path", "device_index", "device_id", "expected_class", "parameter_index", "parameter_id", "value", "display_value"}:
            raise ValueError("Unknown device edit field")
        track, device, path = self._resolve_device(params, True)
        parameters = device.parameters
        index = strict_index(params.get("parameter_index"), "parameter_index", len(parameters))
        parameter = parameters[index]
        self._check_identity(parameter, params.get("parameter_id"), True)
        if not getattr(parameter, "is_enabled", True): raise ValueError("Parameter is disabled")
        if ("value" in params) == ("display_value" in params): raise ValueError("Give exactly one of value or display_value")
        value = (finite_number(params["value"], "parameter", parameter.min, parameter.max) if "value" in params
                 else self._value_for_display(parameter, params["display_value"]))
        if getattr(parameter, "is_quantized", False) and value != int(value): raise ValueError("Quantized value must be an integer")
        return self._transaction([(parameter, "value", value)], lambda: self._parameter_report(parameter))

    def _cmd_get_rack(self, params):
        _, rack, path = self._resolve_device(params)
        if not getattr(rack, "can_have_chains", False): raise ValueError("Selected device is not a rack")
        return self._device_record(rack, path, [128])

    def _cmd_set_rack_chain(self, params):
        if set(params) - {"track_index", "track_type", "target_id", "expected_track_name", "device_path", "device_index", "device_id", "expected_class", "chain_index", "chain_id", "mute", "solo", "volume", "panning"}:
            raise ValueError("Unknown device edit field")
        _, rack, path = self._resolve_device(params, True)
        if not getattr(rack, "can_have_chains", False): raise ValueError("Selected device is not a rack")
        index = strict_index(params.get("chain_index"), "chain_index", len(rack.chains))
        chain = rack.chains[index]
        self._check_identity(chain, params.get("chain_id"), True)
        changes = []
        for key in ("mute", "solo"):
            if key in params:
                if type(params[key]) is not bool: raise ValueError(key + " must be boolean")
                changes.append((chain, key, params[key]))
        for key in ("volume", "panning"):
            if key in params:
                p = getattr(chain.mixer_device, key)
                changes.append((p, "value", finite_number(params[key], key, p.min, p.max)))
        if not changes: raise ValueError("No rack chain change requested")
        return self._transaction(changes, lambda: self._target_record(chain, chain_index=index))

    def _cmd_get_simpler(self, params):
        _, dev, path = self._resolve_device(params)
        if getattr(dev, "class_name", "") != "OriginalSimpler": raise ValueError("Selected device is not Simpler")
        out = self._target_record(dev, device_path=path)
        for key in ("voices", "retrigger", "playback_mode"):
            try: out[key] = getattr(dev, key)
            except (AttributeError, RuntimeError): out[key] = None
        sample = getattr(dev, "sample", None)
        out["sample"] = None if sample is None else {"length": int(sample.length), "sample_rate": int(sample.sample_rate)}
        return out

    def _cmd_edit_simpler(self, params):
        _, dev, path = self._resolve_device(params, True)
        if getattr(dev, "class_name", "") != "OriginalSimpler": raise ValueError("Selected device is not Simpler")
        selector_keys = {"track_index", "track_type", "target_id", "device_path", "device_index", "device_id", "expected_class"}
        if set(params) - selector_keys - {"voices", "retrigger", "playback_mode"}: raise ValueError("Unsupported Simpler edit; sample/warp editing is deferred")
        changes = []
        for key, low, high in (("voices", 1, 32), ("playback_mode", 0, 2)):
            if key in params:
                value = strict_index(params[key], key)
                if not low <= value <= high: raise ValueError(key + " out of range")
                getattr(dev, key)
                changes.append((dev, key, value))
        if "retrigger" in params:
            if type(params["retrigger"]) is not bool: raise ValueError("retrigger must be boolean")
            changes.append((dev, "retrigger", params["retrigger"]))
        if not changes: raise ValueError("No Simpler change requested")
        return self._transaction(changes, lambda: self._cmd_get_simpler(params))


    def _cmd_get_structure(self, params):
        limit = strict_index(params.get("limit", 128), "limit")
        if not 1 <= limit <= 128:
            raise ValueError("limit must be 1..128")
        tracks, scenes = list(self._song.tracks), list(self._song.scenes)
        return {"tracks": [self._target_record(t, track_index=i, track_type="track") for i, t in enumerate(tracks[:limit])],
                "scenes": [self._target_record(s, scene_index=i) for i, s in enumerate(scenes[:limit])],
                "truncated": len(tracks) > limit or len(scenes) > limit}

    def _resolve_scene(self, params):
        scenes = self._song.scenes
        index = strict_index(params.get("scene_index"), "scene_index", len(scenes))
        scene = scenes[index]
        self._check_identity(scene, params.get("scene_id"), True)
        return scene, index

    def _owned_track_cleanup(self, track):
        matches = [i for i, current in enumerate(self._song.tracks) if same_live_object(current, track)]
        if len(matches) == 1:
            self._song.delete_track(matches[0])
        elif matches:
            raise CommandFailure("cleanup_failed", "Owned track identity is ambiguous")

    def _create_owned(self, collection, create, remove):
        before = list(collection())
        try:
            create()
        except Exception as error:
            fresh = [obj for obj in collection() if not any(same_live_object(obj, old) for old in before)]
            details = {"rollback_requested": False, "rollback_complete": not fresh}
            if len(fresh) == 1:
                try:
                    remove(fresh[0])
                    details["rollback_requested"] = True
                    details["rollback_complete"] = not any(same_live_object(fresh[0], obj) for obj in collection())
                except Exception as cleanup_error:
                    details["cleanup_error"] = str(cleanup_error)
            raise CommandFailure("create_failed", str(error), details)
        fresh = [obj for obj in collection() if not any(same_live_object(obj, old) for old in before)]
        if len(fresh) != 1:
            raise CommandFailure("ownership_unknown", "Cannot identify created object; inspect the set before retrying")
        return fresh[0]

    def _cmd_edit_structure(self, params):
        action = params.get("action")
        actions = {"create_track", "create_scene", "duplicate_track", "duplicate_scene", "duplicate_clip", "delete_track", "delete_scene", "delete_clip", "rename_track", "rename_scene", "rename_clip"}
        if action not in actions:
            raise ValueError("Unsupported structural action")
        if set(params) - {"action", "track_index", "track_type", "target_id", "expected_track_name", "scene_index", "scene_id", "clip_index", "clip_id", "destination_index", "destination_slot_id", "kind", "name", "clip_length"}:
            raise ValueError("Unknown structural field")
        self._check_safety("edit_structure", category="delete" if action.startswith("delete_") else "structure" if action.startswith(("create_", "duplicate_")) else "edit")
        name = params.get("name")
        if name is not None and (not isinstance(name, str) or len(name) > 256):
            raise ValueError("name must be a string of at most 256 characters")
        if action.startswith("rename_") and name is None:
            raise ValueError("name is required")
        if action == "create_track":
            kind = params.get("kind", "midi")
            if kind not in ("midi", "audio"):
                raise ValueError("kind must be midi or audio")
            length = finite_number(params["clip_length"], "clip_length", .001, 65536) if "clip_length" in params else None
            if length is not None and (kind != "midi" or not self._song.scenes):
                raise ValueError("Compound clip creation needs a MIDI track and an existing scene")
            track = self._create_owned(lambda: self._song.tracks,
                lambda: getattr(self._song, "create_" + kind + "_track")(-1), self._owned_track_cleanup)
            try:
                if name is not None: track.name = name
                if length is not None:
                    if track.clip_slots[0].has_clip: raise ValueError("New track slot unexpectedly occupied")
                    track.clip_slots[0].create_clip(length)
            except Exception as error:
                try:
                    self._owned_track_cleanup(track)
                except Exception as cleanup_error:
                    raise CommandFailure("compound_create_failed", str(error), {"rollback_complete": False, "cleanup_error": str(cleanup_error)})
                raise CommandFailure("compound_create_failed", str(error), {"rollback_requested": True})
            def report():
                index = next((i for i, current in enumerate(self._song.tracks) if same_live_object(current, track)), None)
                if index is None: raise CommandFailure("stale_target", "Created track disappeared")
                return self._target_record(track, track_index=index, track_type="track")
            return DeferredOperation(report, lambda failed: self._owned_track_cleanup(track) if failed else None)
        if action in ("create_scene", "duplicate_scene", "delete_scene", "rename_scene"):
            if action != "create_scene": scene, index = self._resolve_scene(params)
            if action == "rename_scene":
                return self._transaction([(scene, "name", name)], lambda: self._target_record(scene, scene_index=index))
            if action == "delete_scene":
                self._song.delete_scene(index)
                def deleted():
                    if any(same_live_object(scene, current) for current in self._song.scenes):
                        raise CommandFailure("delete_unverified", "Scene deletion not observed; do not automatically retry")
                    return {"deleted": True}
                return DeferredOperation(deleted)
            def remove_scene(owned):
                matches = [i for i, scene in enumerate(self._song.scenes) if same_live_object(scene, owned)]
                if len(matches) == 1: self._song.delete_scene(matches[0])
            owned = self._create_owned(lambda: self._song.scenes,
                lambda: self._song.create_scene(-1) if action == "create_scene" else self._song.duplicate_scene(index), remove_scene)
            def cleanup(failed):
                if failed:
                    matches = [i for i, s in enumerate(self._song.scenes) if same_live_object(s, owned)]
                    if len(matches) == 1: self._song.delete_scene(matches[0])
            try:
                if name is not None: owned.name = name
            except Exception:
                cleanup(True)
                raise
            return DeferredOperation(lambda: self._target_record(owned, scene_index=next(i for i, s in enumerate(self._song.scenes) if same_live_object(s, owned))), cleanup)
        track, kind, index = self._resolve_track(params, True)
        if kind != "track": raise ValueError("Structural edits require a regular track")
        if action == "rename_track":
            return self._transaction([(track, "name", name)], lambda: self._target_record(track, track_index=index))
        if action == "delete_track":
            self._song.delete_track(index)
            def deleted():
                if any(same_live_object(track, current) for current in self._song.tracks):
                    raise CommandFailure("delete_unverified", "Track deletion not observed; do not automatically retry")
                return {"deleted": True}
            return DeferredOperation(deleted)
        if action == "duplicate_track":
            owned = self._create_owned(lambda: self._song.tracks,
                lambda: self._song.duplicate_track(index), self._owned_track_cleanup)
            return DeferredOperation(lambda: self._target_record(owned, track_index=next(i for i, t in enumerate(self._song.tracks) if same_live_object(t, owned))), lambda failed: self._owned_track_cleanup(owned) if failed else None)
        slots = track.clip_slots
        slot = slots[strict_index(params.get("clip_index"), "clip_index", len(slots))]
        if not slot.has_clip: raise ValueError("Source clip slot is empty")
        clip = slot.clip
        self._check_identity(clip, params.get("clip_id"), True)
        if action == "rename_clip":
            return self._transaction([(clip, "name", name)], lambda: self._target_record(clip))
        if action == "delete_clip":
            slot.delete_clip()
            def deleted():
                if slot.has_clip: raise CommandFailure("delete_unverified", "Clip slot is still occupied")
                return {"deleted": True}
            return DeferredOperation(deleted)
        dest = slots[strict_index(params.get("destination_index"), "destination_index", len(slots))]
        self._check_identity(dest, params.get("destination_slot_id"), True)
        if dest.has_clip: raise ValueError("Destination clip slot is occupied")
        owned = self._create_owned(lambda: [dest.clip] if dest.has_clip else [],
            lambda: slot.duplicate_clip_to(dest),
            lambda obj: dest.delete_clip() if dest.has_clip and same_live_object(dest.clip, obj) else None)
        def cleanup(failed):
            if failed and dest.has_clip and same_live_object(dest.clip, owned): dest.delete_clip()
        return DeferredOperation(lambda: self._target_record(owned), cleanup)


    def _routing_record(self, track, kind, index):
        result = self._target_record(track, track_type=kind, track_index=index)
        for key, attr in ROUTING_FIELDS:
            try:
                options = list(getattr(track, "available_" + attr + "s"))
                if len(options) > 256:
                    raise ValueError("Too many routing choices")
                current = getattr(track, attr)
                result[key] = str(current.display_name)
                result["available_" + key] = [str(option.display_name) for option in options]
            except (AttributeError, RuntimeError, ValueError) as error:
                result[key] = None
                result.setdefault("unavailable", {})[key] = str(error)
        return result

    def _cmd_get_track_routing(self, params):
        return self._routing_record(*self._resolve_track(params))

    def _routing_choice(self, wanted, options):
        if not isinstance(wanted, str):
            raise ValueError("Routing choices must be exact display-name strings")
        matches = [choice for choice in options if choice.display_name == wanted]
        if len(matches) != 1:
            raise ValueError("Routing choice is missing or ambiguous; use the current available list")
        return matches[0]

    def _cmd_set_track_routing(self, params):
        fields = dict(ROUTING_FIELDS)
        if set(params) - set(fields) - {"track_index", "track_type", "target_id", "expected_track_name"}:
            raise ValueError("Unknown routing field")
        track, kind, index = self._resolve_track(params, True)
        changes = []
        restore = []
        for direction in ("input", "output"):
            type_key, channel_key = direction + "_type", direction + "_channel"
            if type_key not in params and channel_key not in params:
                continue
            type_attr, channel_attr = fields[type_key], fields[channel_key]
            old_type, old_channel = getattr(track, type_attr), getattr(track, channel_attr)
            restore.extend([(track, type_attr, old_type), (track, channel_attr, old_channel)])
            new_type = old_type
            if type_key in params:
                options = list(getattr(track, "available_" + type_attr + "s"))
                if len(options) > 256: raise ValueError("Too many routing choices")
                new_type = self._routing_choice(params[type_key], options)
                changes.append((track, type_attr, new_type))
            if channel_key in params:
                if not same_live_object(new_type, old_type):
                    raise ValueError("Change routing type first, then read its channels before selecting a channel")
                options = list(getattr(track, "available_" + channel_attr + "s"))
                if len(options) > 256: raise ValueError("Too many routing choices")
                changes.append((track, channel_attr, self._routing_choice(params[channel_key], options)))
        if not changes:
            raise ValueError("No routing change requested")
        return self._transaction(changes, lambda: self._routing_record(track, kind, index), restore_changes=restore)


    def _parameter_report(self, param, unit=None):
        value = finite_number(param.value, "parameter value")
        display = str(param.str_for_value(value)) if callable(getattr(param, "str_for_value", None)) else str(param)
        out = {"value": value, "min": float(param.min), "max": float(param.max), "display": display}
        if unit == "dB":
            match = re.fullmatch(r"\s*(-?inf|[-+]?\d+(?:\.\d+)?)\s*dB\s*", display, re.I)
            if match:
                db = float(match.group(1))
                out.update({"db": db if math.isfinite(db) else None, "silence": db == float("-inf")})
        elif unit == "pan":
            match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([LR])\s*", display, re.I)
            if match:
                out["pan_percent"] = float(match.group(1)) * (-1 if match.group(2).upper() == "L" else 1)
        return out

    def _value_for_db(self, param, requested):
        lo, hi = float(param.min), float(param.max)
        if requested in ("-inf", "silence"):
            return lo
        wanted = finite_number(requested, "volume_db")
        def read(value):
            text = str(param.str_for_value(value))
            match = re.fullmatch(r"\s*(-?inf|[-+]?\d+(?:\.\d+)?)\s*dB\s*", text, re.I)
            if not match:
                raise ValueError("Parameter does not expose an unambiguous dB display")
            return float(match.group(1))
        samples = [read(lo + (hi - lo) * i / 16.0) for i in range(17)]
        if any(math.isnan(v) for v in samples) or any(a > b for a, b in zip(samples, samples[1:])):
            raise ValueError("Nonmonotonic dB display mapping")
        if wanted < samples[0] or wanted > samples[-1]:
            raise ValueError("Requested dB is outside parameter range")
        for _ in range(40):
            mid = (lo + hi) / 2.0
            if read(mid) < wanted:
                lo = mid
            else:
                hi = mid
        return hi

    def _mixer_record(self, track, kind, index):
        mixer = track.mixer_device
        out = self._target_record(track, track_type=kind, track_index=index,
            volume=self._parameter_report(mixer.volume, "dB"), panning=self._parameter_report(mixer.panning, "pan"))
        out["sends"] = [dict(self._parameter_report(p, "dB"), send_index=i) for i, p in enumerate(getattr(mixer, "sends", ()))] if kind != "master" else []
        if kind != "master":
            out.update({"mute": bool(track.mute), "solo": bool(track.solo), "arm": self._safe_arm(track)})
        return out

    def _cmd_get_mixer_state(self, params):
        track, kind, index = self._resolve_track(params)
        return self._mixer_record(track, kind, index)

    def _cmd_set_track_mixer(self, params):
        allowed = {"track_index", "track_type", "target_id", "expected_track_name", "volume", "volume_db", "panning", "sends", "mute", "solo", "arm", "exclusive_solo"}
        if set(params) - allowed:
            raise ValueError("Unknown mixer fields")
        track, kind, index = self._resolve_track(params, True)
        mixer = track.mixer_device
        changes = []
        if "volume" in params and "volume_db" in params:
            raise ValueError("Specify volume or volume_db, not both")
        for field in ("volume", "panning"):
            if field in params:
                parameter = getattr(mixer, field)
                value = finite_number(params[field], field, parameter.min, parameter.max)
                changes.append((parameter, "value", value))
        if "volume_db" in params:
            changes.append((mixer.volume, "value", self._value_for_db(mixer.volume, params["volume_db"])))
        sends = params.get("sends", {})
        if not isinstance(sends, dict) or len(sends) > 64:
            raise ValueError("sends must be an object with at most 64 indices")
        for key, value in sends.items():
            if kind == "master":
                raise ValueError("Master track has no sends")
            if not isinstance(key, str) or not key.isdigit():
                raise ValueError("Send keys must be decimal indices")
            send = mixer.sends[strict_index(int(key), "send_index", len(mixer.sends))]
            changes.append((send, "value", finite_number(value, "send", send.min, send.max)))
        for field in ("mute", "solo", "arm"):
            if field in params:
                if type(params[field]) is not bool:
                    raise ValueError(field + " must be boolean")
                if kind == "master" or field == "arm" and (kind != "track" or not track.can_be_armed):
                    raise ValueError(field + " is unsupported on this track")
                changes.append((track, field, params[field]))
        exclusive = params.get("exclusive_solo", False)
        if type(exclusive) is not bool:
            raise ValueError("exclusive_solo must be boolean")
        if exclusive and params.get("solo") is not True:
            raise ValueError("exclusive_solo requires solo=true")
        if exclusive:
            for other in list(self._song.tracks) + list(self._song.return_tracks):
                if not same_live_object(other, track) and other.solo:
                    changes.append((other, "solo", False))
        if not changes:
            raise ValueError("No mixer changes requested")
        return self._transaction(changes, lambda: self._mixer_record(track, kind, index))


    def _transaction(self, changes, report=None, restore_changes=None):
        """Verify async Live property writes after a tick; rollback is also verified later."""
        snapshots = preflight_changes(changes)
        if restore_changes is not None:
            preflight_changes(restore_changes)
        state = {"error": None, "phase": "verify", "attempted": [], "restoring": False}
        def restore():
            failures = []
            restore_entries = restore_changes if restore_changes is not None else [(o, a, old) for o, a, old, value in reversed(state["attempted"])]
            for owner, attr, old in restore_entries:
                try:
                    setattr(owner, attr, old)
                except Exception as error:
                    failures.append({"field": attr, "message": str(error)})
            return failures
        def cleanup(failed):
            if failed and not state["restoring"]:
                failures = restore()
                if failures:
                    raise CommandFailure("rollback_failed", "Restore failed", {"rollback_complete": False, "rollback_failures": failures})
        def step():
            if state["phase"] == "verify":
                try:
                    if state["error"]:
                        raise state["error"]
                    for owner, attr, old, value in snapshots:
                        if not values_equal(getattr(owner, attr), value):
                            raise ValueError("Readback mismatch for " + attr)
                    return report() if report else {"changed_fields": len(snapshots), "verified": True}
                except Exception as error:
                    state["error"] = error
                    state["restoring"] = True
                    state["failures"] = restore()
                    state["phase"] = "rollback"
                    return _WAIT_FOR_TICK
            failures = state["failures"]
            verify_entries = restore_changes if restore_changes is not None else [(o, a, old) for o, a, old, value in state["attempted"]]
            for owner, attr, old in verify_entries:
                try:
                    if not values_equal(getattr(owner, attr), old):
                        raise ValueError("restore readback mismatch")
                except Exception as error:
                    failures.append({"field": attr, "message": str(error)})
            raise CommandFailure("mutation_failed", str(state["error"]), {
                "rollback_complete": not failures, "rollback_failures": failures,
                "attempted_fields": len(state["attempted"])})
        for entry in snapshots:
            owner, attr, old, value = entry
            state["attempted"].append(entry)
            try:
                setattr(owner, attr, value)
            except Exception as error:
                state["error"] = error
                break
        return DeferredOperation(step, cleanup, max_ticks=4)


    def _identity_for(self, obj):
        # Equality matters: Live may return distinct Python wrappers for one LOM object.
        if not hasattr(self, "_target_identities"):
            self._target_identities = []
        for token, known in self._target_identities:
            if same_live_object(known, obj):
                return token
        token = uuid.uuid4().hex
        self._target_identities.append((token, obj))
        if len(self._target_identities) > MAX_TARGET_IDENTITIES:
            self._target_identities.pop(0)
        return token

    def _check_identity(self, obj, token, required=False):
        if token is None and not required:
            return
        if not isinstance(token, str) or not token:
            raise CommandFailure("identity_required", "Read the target identity before this operation")
        known = next((known for key, known in getattr(self, "_target_identities", []) if key == token), None)
        if known is None or not same_live_object(known, obj):
            raise CommandFailure("stale_target", "Target identity changed; read the target again")

    def _resolve_track(self, params, require_identity=False):
        kind = params.get("track_type", "track")
        if kind not in ("track", "return", "master"):
            raise ValueError("track_type must be track, return or master")
        tracks = ((self._song.master_track,) if kind == "master" else
                  self._song.return_tracks if kind == "return" else self._song.tracks)
        index = strict_index(params.get("track_index", 0), "track_index", len(tracks))
        track = tracks[index]
        expected = params.get("expected_track_name")
        if expected is not None and track.name != expected:
            raise CommandFailure("stale_target", "Track name changed")
        self._check_identity(track, params.get("target_id"), require_identity)
        return track, kind, index

    def _target_record(self, obj, **fields):
        fields.update({"target_id": self._identity_for(obj), "name": str(getattr(obj, "name", ""))})
        return fields

    def _get_target_identity(self, params):
        track, kind, index = self._resolve_track(params)
        record = self._target_record(track, track_type=kind, track_index=index)
        if "clip_index" in params:
            slots = getattr(track, "clip_slots", ())
            clip_index = strict_index(params["clip_index"], "clip_index", len(slots))
            slot = slots[clip_index]
            record["slot_id"] = self._identity_for(slot)
            record["clip"] = self._target_record(slot.clip, clip_index=clip_index) if slot.has_clip else None
        return record


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

            if not getattr(clip, "is_midi_clip", False):
                raise Exception("Clip is not a MIDI clip")

            # Refuse before touching the clip: notes written into a Step
            # Sequencer clip are accepted and read back but never shown/played.
            midi_clip_type = self._checked_midi_clip_type_for_write(clip)

            # Validate everything first so a bad note leaves the clip untouched.
            specs = normalize_note_specs(notes)

            try:
                import Live
                Spec = Live.Clip.MidiNoteSpecification
            except Exception:
                Spec = None

            ignored_fields = []
            if Spec is not None and hasattr(clip, "add_new_notes"):
                clip.add_new_notes(tuple(Spec(**s) for s in specs))
                api_used = "add_new_notes"
            else:
                # Pre-Live-11 fallback: the tuple format has no slot for the
                # extended fields, so report which ones were dropped.
                clip.set_notes(tuple(
                    (s["pitch"], s["start_time"], s["duration"],
                     s["velocity"], s["mute"]) for s in specs))
                api_used = "set_notes"
                ignored_fields = extended_fields_in(notes)

            result = {
                "note_count": len(specs),
                "api_used": api_used,
                "midi_clip_type": midi_clip_type,
            }
            if ignored_fields:
                result["ignored_fields"] = ignored_fields
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


    
    
    # ── Arrangement view implementations ──────────────────────────────────────

    def _switch_to_arrangement_view(self):
        """Switch Ableton's main window to the Arrangement view"""
        try:
            self.application().view.show_view("Arranger")
            return {"view": "Arranger"}
        except Exception as e:
            self.log_message("Error switching to arrangement view: " + str(e))
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

            self._checked_midi_clip_type_for_write(clip)

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

    def _create_locator(self, name, time_val):
        """Move, toggle and discover on separate ticks; never toggle an existing cue."""
        target = finite_number(time_val, "time", 0, 1e9)
        if not isinstance(name, str) or len(name) > 256:
            raise ValueError("Locator name must be a string of at most 256 characters")
        song = self._song
        if song.is_playing:
            raise ValueError("Stop playback before creating a locator")
        original = float(song.current_song_time)
        existing = [cue for cue in song.cue_points if abs(cue.time - target) < 1e-3]
        if len(existing) > 1:
            raise ValueError("Multiple locators at this time")
        if existing:
            apply_changes([(existing[0], "name", name)])
            return {"success": True, "time": existing[0].time, "name": existing[0].name, "created": False}
        state = {"phase": "position", "cue": None, "toggled": False}
        before = list(song.cue_points)
        def cleanup(failed):
            # A cue toggle has no object-specific delete API. Only undo our cue
            # while both its identity and the stopped playhead remain owned.
            try:
                if failed and state["toggled"]:
                    matches = [cue for cue in song.cue_points if abs(cue.time - target) < 1e-3]
                    owned = [cue for cue in matches if not any(same_live_object(cue, old) for old in before)]
                    if matches:
                        if (len(matches) != 1 or len(owned) != 1 or song.is_playing or
                                abs(song.current_song_time - target) >= 1e-3):
                            raise CommandFailure("rollback_incomplete", "Created locator could not be safely removed; inspect the set")
                        song.set_or_delete_cue()
            finally:
                if not song.is_playing and abs(song.current_song_time - target) < 1e-3:
                    song.current_song_time = original
        def step():
            if song.is_playing:
                raise CommandFailure("state_changed", "Playback started during locator creation")
            if state["phase"] == "position":
                if abs(song.current_song_time - target) >= 1e-3:
                    return _WAIT_FOR_TICK
                if any(abs(cue.time - target) < 1e-3 for cue in song.cue_points):
                    raise CommandFailure("state_changed", "A locator appeared before creation")
                state["toggled"] = True
                song.set_or_delete_cue()
                state["phase"] = "lookup"
                return _WAIT_FOR_TICK
            matches = [cue for cue in song.cue_points if abs(cue.time - target) < 1e-3 and
                       not any(same_live_object(cue, old) for old in before)]
            if not matches:
                return _WAIT_FOR_TICK
            if len(matches) != 1:
                raise CommandFailure("ambiguous_target", "Cannot identify created locator")
            cue = matches[0]
            apply_changes([(cue, "name", name)])
            return {"success": True, "time": cue.time, "name": cue.name, "created": True}
        try:
            song.current_song_time = target
        except Exception:
            cleanup(True)
            raise
        return DeferredOperation(step, cleanup, max_ticks=20)

    def _get_locators(self, params):
        return {"locators": [self._target_record(cue, cue_index=i, time=float(cue.time)) for i, cue in enumerate(self._song.cue_points[:1024])]}



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
            self._log_command_error("Error getting browser item", e)
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

    def _load_browser_item(self, track_index, item_uri):
        strict_index(track_index, "track_index", len(self._song.tracks))
        track = self._song.tracks[track_index]
        app = self.application()
        item = self._find_browser_item_by_uri(app.browser, item_uri)
        if item is None or not getattr(item, "is_loadable", False):
            raise ValueError("Browser item is unavailable or not loadable")
        before = list(track.devices)
        if len(before) > 128:
            raise ValueError("Device chain exceeds completion-check bound")
        def fingerprint(devices):
            return [tuple(float(p.value) for p in list(d.parameters)[:256]) for d in devices]
        old_values = fingerprint(before)
        view = self._song.view
        selected = view.selected_track
        def cleanup(failed):
            if same_live_object(view.selected_track, track):
                view.selected_track = selected
        def step():
            if not any(same_live_object(track, current) for current in self._song.tracks):
                raise CommandFailure("stale_target", "Load target disappeared")
            after = list(track.devices)
            changed = len(after) != len(before) or any(not same_live_object(a, b) for a, b in zip(after, before))
            if not changed and fingerprint(after) == old_values:
                return _WAIT_FOR_TICK
            return {"loaded": True, "settled": True, "item_name": item.name,
                    "track_name": track.name, "uri": item_uri,
                    "new_devices": [d.name for d in after if not any(same_live_object(d, old) for old in before)]}
        try:
            view.selected_track = track
            app.browser.load_item(item)
        except Exception:
            cleanup(True)
            raise
        # No change is not proof of completion (including identical preset reload).
        return DeferredOperation(step, cleanup, max_ticks=50)


    
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

    def _midi_clip_type(self, clip):
        """Live 13's Clip.midi_clip_type (0 = piano roll, 1 = Step Sequencer).

        None only when the clip is not a MIDI clip or the property does not
        exist (AttributeError: Live <= 12), so older Live behaves as before.

        Fails closed otherwise: if the property exists but cannot be read, or
        holds something that is not an integer, this raises rather than
        returning None. None means "normal MIDI clip" to the write guard, and
        Live silently accepts invisible notes in Step Sequencer clips, so an
        unreadable type must never be mistaken for a safe one.
        """
        if not getattr(clip, "is_midi_clip", False):
            return None
        try:
            value = clip.midi_clip_type
        except AttributeError:
            return None
        except Exception as e:
            raise Exception("Could not read midi_clip_type: %s" % e)
        if isinstance(value, bool):
            raise Exception("Unexpected midi_clip_type value: %s" % _short_repr(value))
        try:
            as_int = int(value)
        except Exception:
            raise Exception("Unexpected midi_clip_type value: %s" % _short_repr(value))
        # Only a float can be non-integral; an int-like enum (as Boost.Python
        # exposes Live enums) must pass even if it does not compare equal.
        if isinstance(value, float) and as_int != value:
            raise Exception("Unexpected midi_clip_type value: %s" % _short_repr(value))
        return as_int

    def _checked_midi_clip_type_for_write(self, clip):
        """Return the clip type, refusing anything but a plain MIDI clip."""
        try:
            midi_clip_type = self._midi_clip_type(clip)
        except Exception as e:
            raise Exception(
                "Refusing to modify notes: cannot determine whether this is a "
                "Step Sequencer clip (%s). Notes written to a Step Sequencer "
                "clip are stored invisibly." % e)
        if midi_clip_type:
            raise Exception(step_sequencer_error(midi_clip_type))
        return midi_clip_type

    def _is_non_standard_midi_clip(self, clip):
        """True for any MIDI clip that is not a plain piano-roll clip.

        Checked as != 0 rather than == 1: other values may exist and none of
        them is known to show API-written notes. Raises when the type cannot
        be determined (see _midi_clip_type).
        """
        return bool(self._midi_clip_type(clip))

    def _clip_type_info(self, clip):
        """Fields that tell a reader whether the returned notes are trustworthy.

        Readers must not fail a whole track or snapshot over one clip, so an
        unreadable type is reported instead of raised, and it counts as
        "may not match the UI".
        """
        try:
            midi_clip_type = self._midi_clip_type(clip)
        except Exception as e:
            return {
                "midi_clip_type": None,
                "midi_clip_type_error": str(e),
                "notes_may_not_match_ui": True,
            }
        return {
            "midi_clip_type": midi_clip_type,
            "notes_may_not_match_ui": bool(midi_clip_type),
        }


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
                        if hasattr(param, "value_string"):
                            entry["value_string"] = str(param.value_string)
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
        if info["is_midi_clip"]:
            info.update(self._clip_type_info(clip))
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
        if info["is_midi_clip"]:
            info.update(self._clip_type_info(clip))
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
                returns[-1].update(self._output_meters(track))
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
            result = {
                "volume": float(track.mixer_device.volume.value),
                "panning": float(track.mixer_device.panning.value),
                "devices": devices,
            }
            result.update(self._output_meters(track))
            return result
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
            result = {
                "track_index": track_index,
                "clip_index": clip_index,
                "clip_name": clip.name,
                "length": float(clip.length),
                "note_count": len(notes),
                "notes": notes,
            }
            result.update(self._clip_type_info(clip))
            return result
        except Exception as e:
            self.log_message("Error getting clip notes: " + str(e))
            raise


    def _get_device_parameters(self, track_index, device_index):
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            track = self._song.tracks[track_index]
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
                tracks[-1].update(self._output_meters(track))

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

    def _set_device_parameter(self, track_index, device_index, parameter_index, value):
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
            value = float(value)
            if not float(param.min) <= value <= float(param.max):
                raise ValueError("Value is outside the range of parameter '{0}'".format(param.name))
            old = float(param.value)
            param.value = value
            return {
                "track_index": track_index,
                "device_index": device_index,
                "parameter_index": parameter_index,
                "name": param.name,
                "old_value": old,
                "value": float(param.value),
                "min": float(param.min),
                "max": float(param.max),
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
            self._log_command_error("Error getting browser tree", e)
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
            self._log_command_error("Error getting browser items at path", e)
            raise
