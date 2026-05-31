# AbletonMCP/init.py
# -*- coding: utf-8 -*-
from __future__ import absolute_import, print_function, unicode_literals

from _Framework.ControlSurface import ControlSurface
import socket
import select
import json
import traceback

DEFAULT_PORT = 9877
HOST = "localhost"

def create_instance(c_instance):
    return AbletonMCP(c_instance)

class AbletonMCP(ControlSurface):

    def __init__(self, c_instance):
        ControlSurface.__init__(self, c_instance)
        self.log_message("AbletonMCP initializing...")
        self._song = self.song()
        self._session_cache = {}
        self._server = None
        self._client = None
        self._buffer = ""
        self._start_server()

    def _start_server(self):
        try:
            self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._server.setblocking(False)
            self._server.bind((HOST, DEFAULT_PORT))
            self._server.listen(5)
            self.log_message("AbletonMCP listening on port " + str(DEFAULT_PORT))
            self.show_message("AbletonMCP ready on port " + str(DEFAULT_PORT))
        except Exception as e:
            self.log_message("Error starting server: " + str(e))

    def disconnect(self):
        self.log_message("AbletonMCP disconnecting...")
        if self._client:
            try: self._client.close()
            except: pass
            self._client = None
        if self._server:
            try: self._server.close()
            except: pass
            self._server = None
        ControlSurface.disconnect(self)
        self.log_message("AbletonMCP disconnected")

    def update_display(self):
        # Build cache on first tick (main thread — safe)
        if not self._session_cache:
            try:
                self._session_cache = {
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
                self.log_message("Session cache ready")
            except Exception as e:
                self.log_message("Cache error: " + str(e))

        if not self._server:
            return

        # Accept new connection if no client
        if self._client is None:
            try:
                r, _, _ = select.select([self._server], [], [], 0)
                if r:
                    self._client, addr = self._server.accept()
                    self._client.setblocking(False)
                    self._buffer = ""
                    self.log_message("Client connected from " + str(addr))
                    self.show_message("AbletonMCP: client connected")
            except Exception as e:
                self.log_message("Accept error: " + str(e))
            return

        # Read from existing client
        try:
            r, _, _ = select.select([self._client], [], [], 0)
            if not r:
                return
            data = self._client.recv(8192)
            if not data:
                self.log_message("Client disconnected")
                self._client.close()
                self._client = None
                return
            try:
                self._buffer += data.decode("utf-8")
            except AttributeError:
                self._buffer += data

            try:
                command = json.loads(self._buffer)
                self._buffer = ""
                self.log_message("Received command: " + str(command.get("type", "?")))
                response = self._process_command(command)
                resp_bytes = json.dumps(response).encode("utf-8")
                self._client.sendall(resp_bytes)
            except ValueError:
                pass  # incomplete JSON, wait for more
        except Exception as e:
            self.log_message("Client error: " + str(e))
            try: self._client.close()
            except: pass
            self._client = None

    def _process_command(self, command):
        command_type = command.get("type", "")
        params = command.get("params", {}) or {}
        response = {"status": "success", "result": {}}
        try:
            if command_type == "get_session_info":
                response["result"] = self._get_session_info()
            elif command_type == "get_track_info":
                response["result"] = self._get_track_info(params.get("track_index", 0))
            elif command_type == "create_midi_track":
                response["result"] = self._create_midi_track(params.get("index", -1))
            elif command_type == "set_track_name":
                response["result"] = self._set_track_name(params.get("track_index", 0), params.get("name", ""))
            elif command_type == "create_clip":
                response["result"] = self._create_clip(params.get("track_index", 0), params.get("clip_index", 0), params.get("length", 4.0))
            elif command_type == "add_notes_to_clip":
                response["result"] = self._add_notes_to_clip(params.get("track_index", 0), params.get("clip_index", 0), params.get("notes", []))
            elif command_type == "set_clip_name":
                response["result"] = self._set_clip_name(params.get("track_index", 0), params.get("clip_index", 0), params.get("name", ""))
            elif command_type == "set_tempo":
                response["result"] = self._set_tempo(params.get("tempo", 120.0))
            elif command_type == "fire_clip":
                response["result"] = self._fire_clip(params.get("track_index", 0), params.get("clip_index", 0))
            elif command_type == "stop_clip":
                response["result"] = self._stop_clip(params.get("track_index", 0), params.get("clip_index", 0))
            elif command_type == "start_playback":
                response["result"] = self._start_playback()
            elif command_type == "stop_playback":
                response["result"] = self._stop_playback()
            elif command_type == "load_browser_item":
                response["result"] = self._load_browser_item(params.get("track_index", 0), params.get("item_uri", ""))
            elif command_type == "get_browser_tree":
                response["result"] = self.get_browser_tree(params.get("category_type", "all"))
            elif command_type == "get_browser_items_at_path":
                response["result"] = self.get_browser_items_at_path(params.get("path", ""))
            else:
                response["status"] = "error"
                response["message"] = "Unknown command: " + command_type
            # Update cache after any state change
            if command_type not in ("get_session_info", "get_track_info", "get_browser_tree", "get_browser_items_at_path"):
                self._session_cache = {}
        except Exception as e:
            self.log_message("Command error: " + str(e))
            response["status"] = "error"
            response["message"] = str(e)
        return response

    def _get_session_info(self):
        if self._session_cache:
            return dict(self._session_cache)
        raise Exception("Session not ready")

    def _get_track_info(self, track_index):
        if track_index < 0 or track_index >= len(self._song.tracks):
            raise IndexError("Track index out of range")
        track = self._song.tracks[track_index]
        clip_slots = []
        for i, slot in enumerate(track.clip_slots):
            clip_info = None
            if slot.has_clip:
                clip = slot.clip
                clip_info = {"name": clip.name, "length": clip.length, "is_playing": clip.is_playing, "is_recording": clip.is_recording}
            clip_slots.append({"index": i, "has_clip": slot.has_clip, "clip": clip_info})
        devices = []
        for i, device in enumerate(track.devices):
            devices.append({"index": i, "name": device.name, "class_name": device.class_name, "type": self._get_device_type(device)})
        return {"index": track_index, "name": track.name, "is_audio_track": track.has_audio_input, "is_midi_track": track.has_midi_input,
                "mute": track.mute, "solo": track.solo, "arm": track.arm,
                "volume": track.mixer_device.volume.value, "panning": track.mixer_device.panning.value,
                "clip_slots": clip_slots, "devices": devices}

    def _create_midi_track(self, index):
        self._song.create_midi_track(index)
        new_idx = len(self._song.tracks) - 1 if index == -1 else index
        new_track = self._song.tracks[new_idx]
        return {"index": new_idx, "name": new_track.name}

    def _set_track_name(self, track_index, name):
        if track_index < 0 or track_index >= len(self._song.tracks):
            raise IndexError("Track index out of range")
        self._song.tracks[track_index].name = name
        return {"name": self._song.tracks[track_index].name}

    def _create_clip(self, track_index, clip_index, length):
        if track_index < 0 or track_index >= len(self._song.tracks):
            raise IndexError("Track index out of range")
        track = self._song.tracks[track_index]
        if clip_index < 0 or clip_index >= len(track.clip_slots):
            raise IndexError("Clip index out of range")
        slot = track.clip_slots[clip_index]
        if slot.has_clip:
            raise Exception("Clip slot already has a clip")
        slot.create_clip(length)
        return {"name": slot.clip.name, "length": slot.clip.length}

    def _add_notes_to_clip(self, track_index, clip_index, notes):
        if track_index < 0 or track_index >= len(self._song.tracks):
            raise IndexError("Track index out of range")
        track = self._song.tracks[track_index]
        if clip_index < 0 or clip_index >= len(track.clip_slots):
            raise IndexError("Clip index out of range")
        slot = track.clip_slots[clip_index]
        if not slot.has_clip:
            raise Exception("No clip in slot")
        live_notes = []
        for note in notes:
            live_notes.append((note.get("pitch", 60), note.get("start_time", 0.0), note.get("duration", 0.25), note.get("velocity", 100), note.get("mute", False)))
        slot.clip.set_notes(tuple(live_notes))
        return {"note_count": len(notes)}

    def _set_clip_name(self, track_index, clip_index, name):
        track = self._song.tracks[track_index]
        slot = track.clip_slots[clip_index]
        if not slot.has_clip:
            raise Exception("No clip in slot")
        slot.clip.name = name
        return {"name": slot.clip.name}

    def _set_tempo(self, tempo):
        self._song.tempo = tempo
        return {"tempo": self._song.tempo}

    def _fire_clip(self, track_index, clip_index):
        slot = self._song.tracks[track_index].clip_slots[clip_index]
        if not slot.has_clip:
            raise Exception("No clip in slot")
        slot.fire()
        return {"fired": True}

    def _stop_clip(self, track_index, clip_index):
        self._song.tracks[track_index].clip_slots[clip_index].stop()
        return {"stopped": True}

    def _start_playback(self):
        self._song.start_playing()
        return {"playing": self._song.is_playing}

    def _stop_playback(self):
        self._song.stop_playing()
        return {"playing": self._song.is_playing}

    def _load_browser_item(self, track_index, item_uri):
        if track_index < 0 or track_index >= len(self._song.tracks):
            raise IndexError("Track index out of range")
        track = self._song.tracks[track_index]
        app = self.application()
        item = self._find_browser_item_by_uri(app.browser, item_uri)
        if not item:
            raise ValueError("Browser item not found: " + item_uri)
        self._song.view.selected_track = track
        app.browser.load_item(item)
        return {"loaded": True, "item_name": item.name, "track_name": track.name, "uri": item_uri}

    def _find_browser_item_by_uri(self, browser_or_item, uri, max_depth=10, current_depth=0):
        try:
            if hasattr(browser_or_item, "uri") and browser_or_item.uri == uri:
                return browser_or_item
            if current_depth >= max_depth:
                return None
            if hasattr(browser_or_item, "instruments"):
                for cat in [browser_or_item.instruments, browser_or_item.sounds, browser_or_item.drums, browser_or_item.audio_effects, browser_or_item.midi_effects]:
                    item = self._find_browser_item_by_uri(cat, uri, max_depth, current_depth + 1)
                    if item:
                        return item
                return None
            if hasattr(browser_or_item, "children") and browser_or_item.children:
                for child in browser_or_item.children:
                    item = self._find_browser_item_by_uri(child, uri, max_depth, current_depth + 1)
                    if item:
                        return item
            return None
        except:
            return None

    def _get_device_type(self, device):
        try:
            if device.can_have_drum_pads: return "drum_machine"
            if device.can_have_chains: return "rack"
            if "instrument" in device.class_display_name.lower(): return "instrument"
            if "audio_effect" in device.class_name.lower(): return "audio_effect"
            if "midi_effect" in device.class_name.lower(): return "midi_effect"
            return "unknown"
        except:
            return "unknown"

    def get_browser_tree(self, category_type="all"):
        try:
            app = self.application()
            if not app:
                raise RuntimeError("No application")
            browser = app.browser
            result = {"type": category_type, "categories": []}
            for attr, label in [("instruments", "Instruments"), ("sounds", "Sounds"), ("drums", "Drums"), ("audio_effects", "Audio Effects"), ("midi_effects", "MIDI Effects")]:
                if (category_type == "all" or category_type == attr) and hasattr(browser, attr):
                    try:
                        item = getattr(browser, attr)
                        result["categories"].append({"name": label, "uri": getattr(item, "uri", None), "is_folder": True})
                    except:
                        pass
            return result
        except Exception as e:
            self.log_message("Browser tree error: " + str(e))
            raise

    def get_browser_items_at_path(self, path):
        try:
            app = self.application()
            browser = app.browser
            parts = path.split("/")
            root = parts[0].lower()
            current = None
            for attr in ["instruments", "sounds", "drums", "audio_effects", "midi_effects"]:
                if attr == root and hasattr(browser, attr):
                    current = getattr(browser, attr)
                    break
            if current is None:
                return {"path": path, "error": "Unknown category: " + root, "items": []}
            for part in parts[1:]:
                if not part:
                    continue
                found = False
                if hasattr(current, "children"):
                    for child in current.children:
                        if hasattr(child, "name") and child.name.lower() == part.lower():
                            current = child
                            found = True
                            break
                if not found:
                    return {"path": path, "error": "Not found: " + part, "items": []}
            items = []
            if hasattr(current, "children"):
                for child in current.children:
                    items.append({"name": getattr(child, "name", "?"), "is_folder": hasattr(child, "children") and bool(child.children),
                                  "is_loadable": getattr(child, "is_loadable", False), "uri": getattr(child, "uri", None)})
            return {"path": path, "name": getattr(current, "name", "?"), "items": items}
        except Exception as e:
            self.log_message("Browser path error: " + str(e))
            raise
