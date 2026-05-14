# AbletonMCP/init.py
from __future__ import absolute_import, print_function, unicode_literals

from _Framework.ControlSurface import ControlSurface
import socket
import json
import threading
import time
import traceback

try:
    import Queue as queue  # Python 2
except ImportError:
    import queue  # Python 3

from . import handlers

DEFAULT_PORT = 9877
HOST = "localhost"

# Commands that modify Live state and must run on the main thread
MODIFYING_COMMANDS = [
    "create_midi_track", "create_audio_track", "set_track_name",
    "create_clip", "add_notes_to_clip", "set_clip_name",
    "set_tempo", "fire_clip", "stop_clip",
    "start_playback", "stop_playback", "load_instrument_or_effect", "load_browser_item",
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
    "delete_time", "duplicate_time", "insert_silence",
    "delete_clip", "set_metronome", "tap_tempo", "set_macro_value", "capture_midi", "apply_groove",
    "freeze_track", "unfreeze_track", "export_track_audio",
    "create_return_track", "delete_track", "duplicate_track", "set_track_arm",
    "set_chain_device_parameter",
    "delete_device", "delete_chain_device",
    "set_return_track_name", "load_on_return_track",
]


def create_instance(c_instance):
    """Create and return the AbletonMCP script instance."""
    # Force-reload handler modules so toggling the control surface picks up code changes
    import importlib
    import traceback as _tb
    for submod_name in sorted(handlers.__dict__):
        submod = getattr(handlers, submod_name, None)
        if hasattr(submod, "__file__"):
            try:
                importlib.reload(submod)
            except Exception as _e:
                # Log reload errors instead of silently swallowing them
                try:
                    c_instance.log_message(
                        "Reload error for {0}: {1}\n{2}".format(
                            submod_name, _e, _tb.format_exc()
                        )
                    )
                except Exception:
                    pass
    return AbletonMCP(c_instance)


class AbletonMCP(ControlSurface):
    """AbletonMCP Remote Script for Ableton Live."""

    def __init__(self, c_instance):
        ControlSurface.__init__(self, c_instance)
        self.log_message("AbletonMCP Remote Script initializing...")
        self.server = None
        self.client_threads = []
        self.server_thread = None
        self.running = False
        self._song = self.song()
        self.start_server()
        self.log_message("AbletonMCP initialized")
        self.show_message("AbletonMCP: Listening for commands on port " + str(DEFAULT_PORT))

    def disconnect(self):
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

    def start_server(self):
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
        try:
            self.log_message("Server thread started")
            self.server.settimeout(1.0)
            while self.running:
                try:
                    client, address = self.server.accept()
                    self.log_message("Connection accepted from " + str(address))
                    self.show_message("AbletonMCP: Client connected")
                    client_thread = threading.Thread(
                        target=self._handle_client, args=(client,)
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
        self.log_message("Client handler started")
        client.settimeout(None)
        buffer = ""
        try:
            while self.running:
                try:
                    data = client.recv(8192)
                    if not data:
                        self.log_message("Client disconnected")
                        break
                    try:
                        buffer += data.decode("utf-8")
                    except AttributeError:
                        buffer += data
                    try:
                        command = json.loads(buffer)
                        buffer = ""
                        self.log_message("Received command: " + str(command.get("type", "unknown")))
                        response = self._process_command(command)
                        try:
                            client.sendall(json.dumps(response).encode("utf-8"))
                        except AttributeError:
                            client.sendall(json.dumps(response))
                    except ValueError:
                        continue
                except Exception as e:
                    self.log_message("Error handling client data: " + str(e))
                    self.log_message(traceback.format_exc())
                    error_response = {"status": "error", "message": str(e)}
                    try:
                        client.sendall(json.dumps(error_response).encode("utf-8"))
                    except AttributeError:
                        client.sendall(json.dumps(error_response))
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

    def _reload_handlers(self):
        """Hot-reload all handler modules without restarting."""
        import importlib
        reloaded = []
        errors = []
        for submod_name in sorted(handlers.__dict__):
            submod = getattr(handlers, submod_name, None)
            if hasattr(submod, "__file__"):
                try:
                    importlib.reload(submod)
                    reloaded.append(submod_name)
                except Exception as e:
                    errors.append({"module": submod_name, "error": str(e)})
                    self.log_message("Reload error for {0}: {1}".format(submod_name, e))
        self.log_message("Reloaded {0} handler modules".format(len(reloaded)))
        self.show_message("AbletonMCP: Reloaded {0} modules".format(len(reloaded)))
        return {"reloaded": reloaded, "errors": errors}

    def _process_command(self, command):
        command_type = command.get("type", "")
        params = command.get("params", {})
        response = {"status": "success", "result": {}}
        song = self._song
        ctrl = self

        try:
            # ---- Read-only (no main-thread scheduling) ----
            if command_type == "get_session_info":
                response["result"] = handlers.session.get_session_info(song, ctrl)
            elif command_type == "get_track_info":
                response["result"] = handlers.tracks.get_track_info(
                    song, params.get("track_index", 0), ctrl
                )
            elif command_type == "get_loop_info":
                response["result"] = handlers.session.get_loop_info(song, ctrl)
            elif command_type == "get_device_parameters":
                response["result"] = handlers.devices.get_device_parameters(
                    song,
                    params.get("track_index", 0),
                    params.get("device_index", 0),
                    params.get("track_type", "track"),
                    ctrl,
                )
            elif command_type == "get_audio_clip_info":
                response["result"] = handlers.audio.get_audio_clip_info(
                    song,
                    params.get("track_index", 0),
                    params.get("clip_index", 0),
                    ctrl,
                )
            elif command_type == "analyze_audio_clip":
                response["result"] = handlers.audio.analyze_audio_clip(
                    song,
                    params.get("track_index", 0),
                    params.get("clip_index", 0),
                    ctrl,
                )
            elif command_type == "get_clip_notes":
                response["result"] = handlers.midi.get_clip_notes(
                    song,
                    params.get("track_index", 0),
                    params.get("clip_index", 0),
                    ctrl,
                )
            elif command_type == "get_arrangement_clips":
                response["result"] = handlers.arrangement.get_arrangement_clips(
                    song, params.get("track_index", 0), ctrl
                )
            elif command_type == "get_chain_devices":
                response["result"] = handlers.devices.get_chain_devices(
                    song,
                    params.get("track_index", 0),
                    params.get("device_index", 0),
                    params.get("chain_index", 0),
                    params.get("track_type", "track"),
                    ctrl,
                )
            elif command_type == "get_chain_device_parameters":
                response["result"] = handlers.devices.get_chain_device_parameters(
                    song,
                    params.get("track_index", 0),
                    params.get("device_index", 0),
                    params.get("chain_index", 0),
                    params.get("chain_device_index", 0),
                    params.get("track_type", "track"),
                    ctrl,
                )
            elif command_type == "get_macro_values":
                response["result"] = handlers.devices.get_macro_values(
                    song,
                    params.get("track_index", 0),
                    params.get("device_index", 0),
                    ctrl,
                )
            elif command_type == "get_browser_item":
                response["result"] = handlers.browser.get_browser_item(
                    song,
                    params.get("uri"),
                    params.get("path"),
                    ctrl,
                )
            elif command_type == "get_browser_categories":
                response["result"] = handlers.browser.get_browser_categories(
                    song, params.get("category_type", "all"), ctrl
                )
            elif command_type == "get_browser_items":
                response["result"] = handlers.browser.get_browser_items(
                    song,
                    params.get("path", ""),
                    params.get("item_type", "all"),
                    ctrl,
                )
            elif command_type == "get_browser_tree":
                response["result"] = handlers.browser.get_browser_tree(
                    song, params.get("category_type", "all"), ctrl
                )
            elif command_type == "get_browser_items_at_path":
                response["result"] = handlers.browser.get_browser_items_at_path(
                    song, params.get("path", ""), ctrl
                )
            elif command_type == "debug_browser_introspect":
                response["result"] = handlers.browser.debug_browser_introspect(
                    song, ctrl
                )
            elif command_type == "get_recording_status":
                response["result"] = handlers.session.get_recording_status(song, ctrl)
            elif command_type == "get_all_tracks_info":
                response["result"] = handlers.tracks.get_all_tracks_info(song, ctrl)
            elif command_type == "get_return_tracks_info":
                response["result"] = handlers.tracks.get_return_tracks_info(song, ctrl)
            elif command_type == "get_notes_from_clip":
                response["result"] = handlers.midi.get_notes_from_clip(
                    song,
                    params.get("track_index", 0),
                    params.get("clip_index", 0),
                    ctrl,
                )

            # ---- create_locator (multi-tick) ----
            elif command_type == "create_locator":
                locator_result_queue = queue.Queue()
                loc_position = float(params.get("position", 0.0))
                loc_name = str(params.get("name", ""))

                def locator_step1():
                    try:
                        if song.is_playing:
                            song.stop_playing()
                        song.current_song_time = max(0.0, loc_position)
                        self.log_message(
                            "Locator step1: target=" + str(loc_position)
                            + " actual=" + str(song.current_song_time)
                        )
                        self.schedule_message(2, locator_step2)
                    except Exception as e:
                        self.log_message("Locator step1 error: " + str(e))
                        locator_result_queue.put({"status": "error", "message": str(e)})

                def locator_step2():
                    try:
                        actual_time = song.current_song_time
                        self.log_message(
                            "Locator step2: creating cue, song_time=" + str(actual_time)
                        )
                        song.set_or_delete_cue()
                        self.schedule_message(2, locator_step3)
                    except Exception as e:
                        self.log_message("Locator step2 error: " + str(e))
                        locator_result_queue.put({"status": "error", "message": str(e)})

                def locator_step3():
                    try:
                        best_cue = None
                        best_dist = 999999.0
                        for cp in song.cue_points:
                            dist = abs(cp.time - loc_position)
                            if dist < best_dist:
                                best_dist = dist
                                best_cue = cp
                        if best_cue:
                            self.log_message(
                                "Locator step3: found cue at " + str(best_cue.time)
                                + " dist=" + str(best_dist)
                            )
                            if loc_name:
                                try:
                                    best_cue.name = loc_name
                                    self.log_message("Locator step3: named '" + loc_name + "'")
                                except Exception as ne:
                                    self.log_message("Locator step3: naming failed: " + str(ne))
                            locator_result_queue.put({
                                "status": "success",
                                "result": {
                                    "position": best_cue.time,
                                    "name": getattr(best_cue, "name", loc_name),
                                },
                            })
                        else:
                            self.log_message(
                                "Locator step3: no cue found near " + str(loc_position)
                            )
                            locator_result_queue.put({
                                "status": "success",
                                "result": {
                                    "position": loc_position,
                                    "name": loc_name,
                                    "warning": "cue not found",
                                },
                            })
                    except Exception as e:
                        self.log_message("Locator step3 error: " + str(e))
                        locator_result_queue.put({"status": "error", "message": str(e)})

                self.schedule_message(1, locator_step1)
                try:
                    task_response = locator_result_queue.get(timeout=10.0)
                    if task_response.get("status") == "error":
                        response["status"] = "error"
                        response["message"] = task_response.get("message", "Unknown error")
                    else:
                        response["result"] = task_response.get("result", {})
                except queue.Empty:
                    response["status"] = "error"
                    response["message"] = "Timeout waiting for locator creation"

            # ---- Commands that need main-thread (response_queue + schedule_message) ----
            elif command_type in MODIFYING_COMMANDS:
                response_queue = queue.Queue()

                def main_thread_task():
                    try:
                        result = _dispatch_modifying(
                            command_type, params, song, ctrl
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

            # ---- Hot-reload command ----
            elif command_type == "reload_handlers":
                response["result"] = self._reload_handlers()

            # ---- Dynamic dispatch (hot-reloadable) ----
            elif handlers.dispatch.is_known(command_type):
                if handlers.dispatch.is_modifying(command_type):
                    response_queue = queue.Queue()

                    def dynamic_main_thread_task():
                        try:
                            result = handlers.dispatch.execute(
                                command_type, params, song, ctrl
                            )
                            response_queue.put({"status": "success", "result": result})
                        except Exception as e:
                            self.log_message("Error in dynamic dispatch: " + str(e))
                            self.log_message(traceback.format_exc())
                            response_queue.put({"status": "error", "message": str(e)})

                    try:
                        self.schedule_message(0, dynamic_main_thread_task)
                    except AssertionError:
                        dynamic_main_thread_task()
                    try:
                        task_response = response_queue.get(timeout=10.0)
                        if task_response.get("status") == "error":
                            response["status"] = "error"
                            response["message"] = task_response.get("message", "Unknown error")
                        else:
                            response["result"] = task_response.get("result", {})
                    except queue.Empty:
                        response["status"] = "error"
                        response["message"] = "Timeout waiting for dynamic operation"
                else:
                    response["result"] = handlers.dispatch.execute(
                        command_type, params, song, ctrl
                    )

            else:
                response["status"] = "error"
                response["message"] = "Unknown command: " + command_type
        except Exception as e:
            self.log_message("Error processing command: " + str(e))
            self.log_message(traceback.format_exc())
            response["status"] = "error"
            response["message"] = str(e)
        return response


def _dispatch_modifying(command_type, params, song, ctrl):
    """Run a state-modifying command (called on main thread)."""
    p = params
    if command_type == "create_midi_track":
        return handlers.tracks.create_midi_track(song, p.get("index", -1), ctrl)
    if command_type == "create_audio_track":
        return handlers.tracks.create_audio_track(song, p.get("index", -1), ctrl)
    if command_type == "set_track_name":
        return handlers.tracks.set_track_name(
            song, p.get("track_index", 0), p.get("name", ""), ctrl
        )
    if command_type == "create_clip":
        return handlers.clips.create_clip(
            song,
            p.get("track_index", 0),
            p.get("clip_index", 0),
            p.get("length", 4.0),
            ctrl,
        )
    if command_type == "add_notes_to_clip":
        return handlers.clips.add_notes_to_clip(
            song,
            p.get("track_index", 0),
            p.get("clip_index", 0),
            p.get("notes", []),
            ctrl,
        )
    if command_type == "set_clip_name":
        return handlers.clips.set_clip_name(
            song,
            p.get("track_index", 0),
            p.get("clip_index", 0),
            p.get("name", ""),
            ctrl,
        )
    if command_type == "set_tempo":
        return handlers.session.set_tempo(song, p.get("tempo", 120.0), ctrl)
    if command_type == "fire_clip":
        return handlers.clips.fire_clip(
            song, p.get("track_index", 0), p.get("clip_index", 0), ctrl
        )
    if command_type == "stop_clip":
        return handlers.clips.stop_clip(
            song, p.get("track_index", 0), p.get("clip_index", 0), ctrl
        )
    if command_type == "start_playback":
        return handlers.session.start_playback(song, ctrl)
    if command_type == "stop_playback":
        return handlers.session.stop_playback(song, ctrl)
    if command_type == "load_instrument_or_effect":
        return handlers.browser.load_instrument_or_effect(
            song, p.get("track_index", 0), p.get("uri", ""), ctrl
        )
    if command_type == "load_browser_item":
        return handlers.browser.load_browser_item(
            song,
            p.get("track_index", 0),
            p.get("uri", p.get("item_uri", "")),
            track_type=p.get("track_type", "track"),
            ctrl=ctrl,
        )
    if command_type == "arm_track":
        return handlers.tracks.arm_track(song, p.get("track_index", 0), ctrl)
    if command_type == "disarm_track":
        return handlers.tracks.disarm_track(song, p.get("track_index", 0), ctrl)
    if command_type == "set_arrangement_overdub":
        return handlers.session.set_arrangement_overdub(
            song, p.get("enabled", False), ctrl
        )
    if command_type == "start_arrangement_recording":
        return handlers.session.start_arrangement_recording(song, ctrl)
    if command_type == "stop_arrangement_recording":
        return handlers.session.stop_arrangement_recording(song, ctrl)
    if command_type == "set_loop_start":
        return handlers.session.set_loop_start(
            song, p.get("position", 0.0), ctrl
        )
    if command_type == "set_loop_end":
        return handlers.session.set_loop_end(
            song, p.get("position", 4.0), ctrl
        )
    if command_type == "set_loop_length":
        return handlers.session.set_loop_length(
            song, p.get("length", 4.0), ctrl
        )
    if command_type == "set_playback_position":
        return handlers.session.set_playback_position(
            song, p.get("position", 0.0), ctrl
        )
    if command_type == "create_scene":
        return handlers.scenes.create_scene(
            song, p.get("index", -1), p.get("name", ""), ctrl
        )
    if command_type == "delete_scene":
        return handlers.scenes.delete_scene(
            song, p.get("scene_index", 0), ctrl
        )
    if command_type == "duplicate_scene":
        return handlers.scenes.duplicate_scene(
            song, p.get("scene_index", 0), ctrl
        )
    if command_type == "trigger_scene":
        return handlers.scenes.trigger_scene(
            song, p.get("scene_index", 0), ctrl
        )
    if command_type == "set_scene_name":
        return handlers.scenes.set_scene_name(
            song,
            p.get("scene_index", 0),
            p.get("name", ""),
            ctrl,
        )
    if command_type == "set_track_color":
        return handlers.tracks.set_track_color(
            song,
            p.get("track_index", 0),
            p.get("color_index", 0),
            ctrl,
        )
    if command_type == "set_device_parameter":
        return handlers.devices.set_device_parameter(
            song,
            p.get("track_index", 0),
            p.get("device_index", 0),
            p.get("parameter_index", 0),
            p.get("value", 0.0),
            p.get("track_type", "track"),
            ctrl,
        )
    if command_type == "set_chain_device_parameter":
        return handlers.devices.set_chain_device_parameter(
            song,
            p.get("track_index", 0),
            p.get("device_index", 0),
            p.get("chain_index", 0),
            p.get("chain_device_index", 0),
            p.get("parameter_index", 0),
            p.get("value", 0.0),
            p.get("track_type", "track"),
            ctrl,
        )
    if command_type == "delete_device":
        return handlers.devices.delete_device(
            song,
            p.get("track_index", 0),
            p.get("device_index", 0),
            p.get("track_type", "track"),
            ctrl,
        )
    if command_type == "delete_chain_device":
        return handlers.devices.delete_chain_device(
            song,
            p.get("track_index", 0),
            p.get("device_index", 0),
            p.get("chain_index", 0),
            p.get("chain_device_index", 0),
            p.get("track_type", "track"),
            ctrl,
        )
    if command_type == "set_clip_color":
        return handlers.clips.set_clip_color(
            song,
            p.get("track_index", 0),
            p.get("clip_index", 0),
            p.get("color_index", 0),
            ctrl,
        )
    if command_type == "quantize_clip":
        return handlers.midi.quantize_clip(
            song,
            p.get("track_index", 0),
            p.get("clip_index", 0),
            p.get("quantize_to", 0.25),
            ctrl,
        )
    if command_type == "transpose_clip":
        return handlers.midi.transpose_clip(
            song,
            p.get("track_index", 0),
            p.get("clip_index", 0),
            p.get("semitones", 0),
            ctrl,
        )
    if command_type == "duplicate_clip":
        return handlers.midi.duplicate_clip(
            song,
            p.get("source_track", 0),
            p.get("source_clip", 0),
            p.get("dest_track", 0),
            p.get("dest_clip", 0),
            ctrl,
        )
    if command_type == "group_tracks":
        return handlers.tracks.group_tracks(
            song, p.get("track_indices", []), p.get("name", ""), ctrl
        )
    if command_type == "set_track_volume":
        return handlers.mixer.set_track_volume(
            song, p.get("track_index", 0), p.get("volume", 0.85), ctrl
        )
    if command_type == "set_track_pan":
        return handlers.mixer.set_track_pan(
            song, p.get("track_index", 0), p.get("pan", 0.0), ctrl
        )
    if command_type == "set_track_mute":
        return handlers.mixer.set_track_mute(
            song, p.get("track_index", 0), p.get("mute", False), ctrl
        )
    if command_type == "set_track_solo":
        return handlers.mixer.set_track_solo(
            song, p.get("track_index", 0), p.get("solo", False), ctrl
        )
    if command_type == "load_audio_sample":
        return handlers.audio.load_audio_sample(
            song,
            p.get("track_index", 0),
            p.get("clip_index", 0),
            p.get("file_path", ""),
            p.get("browser_uri", ""),
            ctrl,
        )
    if command_type == "set_warp_mode":
        return handlers.audio.set_warp_mode(
            song,
            p.get("track_index", 0),
            p.get("clip_index", 0),
            p.get("warp_mode", "beats"),
            ctrl,
        )
    if command_type == "set_clip_warp":
        return handlers.audio.set_clip_warp(
            song,
            p.get("track_index", 0),
            p.get("clip_index", 0),
            p.get("warping_enabled", True),
            ctrl,
        )
    if command_type == "crop_clip":
        return handlers.audio.crop_clip(
            song, p.get("track_index", 0), p.get("clip_index", 0), ctrl
        )
    if command_type == "reverse_clip":
        return handlers.audio.reverse_clip(
            song, p.get("track_index", 0), p.get("clip_index", 0), ctrl
        )
    if command_type == "set_clip_loop_points":
        return handlers.clips.set_clip_loop_points(
            song,
            p.get("track_index", 0),
            p.get("clip_index", 0),
            p.get("loop_start", 0.0),
            p.get("loop_end", 4.0),
            ctrl,
        )
    if command_type == "set_clip_start_marker":
        return handlers.clips.set_clip_start_marker(
            song,
            p.get("track_index", 0),
            p.get("clip_index", 0),
            p.get("start_marker", 0.0),
            ctrl,
        )
    if command_type == "set_clip_end_marker":
        return handlers.clips.set_clip_end_marker(
            song,
            p.get("track_index", 0),
            p.get("clip_index", 0),
            p.get("end_marker", 4.0),
            ctrl,
        )
    if command_type == "set_track_send":
        return handlers.mixer.set_track_send(
            song,
            p.get("track_index", 0),
            p.get("send_index", 0),
            p.get("value", 0.0),
            ctrl,
        )
    if command_type == "copy_clip_to_arrangement":
        return handlers.arrangement.copy_clip_to_arrangement(
            song,
            p.get("track_index", 0),
            p.get("clip_index", 0),
            p.get("arrangement_time", 0.0),
            ctrl,
        )
    if command_type == "create_automation":
        return handlers.automation.create_automation(
            song,
            p.get("track_index", 0),
            p.get("parameter_name", ""),
            p.get("automation_points", []),
            ctrl,
        )
    if command_type == "clear_automation":
        return handlers.automation.clear_automation(
            song,
            p.get("track_index", 0),
            p.get("parameter_name", ""),
            p.get("start_time", 0.0),
            p.get("end_time", 4.0),
            ctrl,
        )
    if command_type == "delete_time":
        return handlers.automation.delete_time(
            song,
            p.get("start_time", 0.0),
            p.get("end_time", 4.0),
            ctrl,
        )
    if command_type == "duplicate_time":
        return handlers.automation.duplicate_time(
            song,
            p.get("start_time", 0.0),
            p.get("end_time", 4.0),
            ctrl,
        )
    if command_type == "insert_silence":
        return handlers.automation.insert_silence(
            song,
            p.get("position", 0.0),
            p.get("length", 4.0),
            ctrl,
        )
    if command_type == "delete_clip":
        return handlers.clips.delete_clip(
            song, p.get("track_index", 0), p.get("clip_index", 0), ctrl
        )
    if command_type == "set_metronome":
        return handlers.session.set_metronome(
            song, p.get("enabled", False), ctrl
        )
    if command_type == "tap_tempo":
        return handlers.session.tap_tempo(song, ctrl)
    if command_type == "set_macro_value":
        return handlers.devices.set_macro_value(
            song,
            p.get("track_index", 0),
            p.get("device_index", 0),
            p.get("macro_index", 0),
            p.get("value", 0.0),
            ctrl,
        )
    if command_type == "capture_midi":
        return handlers.midi.capture_midi(
            song, p.get("track_index", 0), p.get("clip_index", 0), ctrl
        )
    if command_type == "apply_groove":
        return handlers.midi.apply_groove(
            song,
            p.get("track_index", 0),
            p.get("clip_index", 0),
            p.get("groove_amount", 0.5),
            ctrl,
        )
    if command_type == "freeze_track":
        return handlers.audio.freeze_track(
            song, p.get("track_index", 0), ctrl
        )
    if command_type == "unfreeze_track":
        return handlers.audio.unfreeze_track(
            song, p.get("track_index", 0), ctrl
        )
    if command_type == "export_track_audio":
        return handlers.audio.export_track_audio(
            song,
            p.get("track_index", 0),
            p.get("output_path", ""),
            p.get("start_time", 0.0),
            p.get("end_time", 0.0),
            ctrl,
        )
    if command_type == "create_return_track":
        return handlers.tracks.create_return_track(song, ctrl)
    if command_type == "delete_track":
        return handlers.tracks.delete_track(
            song, p.get("track_index", 0), ctrl
        )
    if command_type == "duplicate_track":
        return handlers.tracks.duplicate_track(
            song, p.get("track_index", 0), ctrl
        )
    if command_type == "set_track_arm":
        return handlers.tracks.set_track_arm(
            song,
            p.get("track_index", 0),
            p.get("arm", True),
            ctrl,
        )
    if command_type == "set_return_track_name":
        return handlers.tracks.set_return_track_name(
            song,
            p.get("return_index", 0),
            p.get("name", ""),
            ctrl,
        )
    if command_type == "load_on_return_track":
        return handlers.browser.load_on_return_track(
            song,
            p.get("return_index", 0),
            p.get("uri", ""),
            ctrl,
        )
    raise ValueError("Unknown modifying command: " + command_type)
