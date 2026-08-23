"""all AbletonMCP commands. reloadable at runtime via the `reload` command,
so iterating does not require restarting Live.

each command is a `cmd_<name>(self, params)` method. every command runs on
Live's main thread (the shell in __init__.py schedules it via schedule_message):
the Live Object Model is not thread-safe, and touching it from the socket
thread has crashed Live.
"""
from __future__ import absolute_import, print_function, unicode_literals

import os
import re
import time
import traceback

VERSION = 13



class Handlers(object):
    def __init__(self, script):
        self._script = script
        self._song = script.song()
        self.log_message = script.log_message
        self.show_message = script.show_message
        self.application = script.application

    def resolve(self, command_type):
        fn = getattr(self, "cmd_" + command_type, None)
        if fn is None:
            raise KeyError("Unknown command: " + command_type)
        return fn, True

    # ── command table (params dict → result) ─────────────────────────

    def cmd_create_midi_track(self, params):
        index = params.get("index", -1)
        return self._create_midi_track(index)

    def cmd_set_track_name(self, params):
        track_index = params.get("track_index", 0)
        name = params.get("name", "")
        return self._set_track_name(track_index, name)

    def cmd_create_clip(self, params):
        track_index = params.get("track_index", 0)
        clip_index = params.get("clip_index", 0)
        length = params.get("length", 4.0)
        return self._create_clip(track_index, clip_index, length)

    def cmd_create_audio_clip(self, params):
        track_index = params.get("track_index", 0)
        clip_index = params.get("clip_index", 0)
        path = params.get("path", "")
        return self._create_audio_clip(track_index, clip_index, path)

    def cmd_add_notes_to_clip(self, params):
        track_index = params.get("track_index", 0)
        clip_index = params.get("clip_index", 0)
        notes = params.get("notes", [])
        return self._add_notes_to_clip(track_index, clip_index, notes)

    def cmd_set_clip_name(self, params):
        track_index = params.get("track_index", 0)
        clip_index = params.get("clip_index", 0)
        name = params.get("name", "")
        return self._set_clip_name(track_index, clip_index, name)

    def cmd_set_arrangement_clip_name(self, params):
        track_index = params.get("track_index", 0)
        clip_index = params.get("clip_index", 0)
        name = params.get("name", "")
        return self._set_arrangement_clip_name(track_index, clip_index, name)

    def cmd_set_tempo(self, params):
        tempo = params.get("tempo", 120.0)
        return self._set_tempo(tempo)

    def cmd_fire_clip(self, params):
        track_index = params.get("track_index", 0)
        clip_index = params.get("clip_index", 0)
        return self._fire_clip(track_index, clip_index)

    def cmd_stop_clip(self, params):
        track_index = params.get("track_index", 0)
        clip_index = params.get("clip_index", 0)
        return self._stop_clip(track_index, clip_index)

    def cmd_start_playback(self, params):
        return self._start_playback()

    def cmd_stop_playback(self, params):
        return self._stop_playback()

    def cmd_delete_clip(self, params):
        track_index = params.get("track_index", 0)
        clip_index = params.get("clip_index", 0)
        return self._delete_clip(track_index, clip_index)

    def cmd_delete_track(self, params):
        track_index = params.get("track_index", 0)
        return self._delete_track(track_index)

    def cmd_delete_device(self, params):
        track_index = params.get("track_index", 0)
        device_index = params.get("device_index", 0)
        return self._delete_device(track_index, device_index)

    def cmd_get_device_params(self, params):
        track_index = params.get("track_index", 0)
        device_index = params.get("device_index", 0)
        return self._get_device_params(track_index, device_index)

    def cmd_set_device_param(self, params):
        track_index = params.get("track_index", 0)
        device_index = params.get("device_index", 0)
        param = params.get("param", "")
        value = params.get("value", 0.0)
        return self._set_device_param(track_index, device_index, param, value)

    def cmd_set_track_volume(self, params):
        track_index = params.get("track_index", 0)
        value = params.get("value", 0.85)
        return self._set_track_volume(track_index, value)

    def cmd_get_clip_envelope(self, params):
        return self._get_clip_envelope(
            params.get("track_index", 0),
            params.get("clip_index", 0),
            params.get("device_index", 0),
            params.get("param", ""),
            params.get("resolution", 0.25),
        )

    def cmd_set_clip_envelope(self, params):
        return self._set_clip_envelope(
            params.get("track_index", 0),
            params.get("clip_index", 0),
            params.get("device_index", 0),
            params.get("param", ""),
            params.get("steps", []),
            params.get("clear", True),
        )

    def cmd_get_clip_notes(self, params):
        track_index = params.get("track_index", 0)
        clip_index = params.get("clip_index", 0)
        return self._get_clip_notes(track_index, clip_index)

    def cmd_get_device_chains(self, params):
        track_index = params.get("track_index", 0)
        device_index = params.get("device_index", 0)
        return self._get_device_chains(track_index, device_index)

    def cmd_set_chain_volume(self, params):
        track_index = params.get("track_index", 0)
        device_index = params.get("device_index", 0)
        chain_index = params.get("chain_index", 0)
        value = params.get("value", 0.85)
        return self._set_chain_volume(track_index, device_index, chain_index, value)

    def cmd_set_master_volume(self, params):
        value = params.get("value", 0.85)
        return self._set_master_volume(value)

    def cmd_set_send_level(self, params):
        track_index = params.get("track_index", 0)
        send_index = params.get("send_index", 0)
        value = params.get("value", 0.0)
        return self._set_send_level(track_index, send_index, value)

    def cmd_load_instrument_or_effect(self, params):
        track_index = params.get("track_index", 0)
        uri = params.get("uri", "")
        return self._load_instrument_or_effect(track_index, uri)

    def cmd_load_browser_item(self, params):
        track_index = params.get("track_index", 0)
        item_uri = params.get("item_uri", "")
        return self._load_browser_item(track_index, item_uri)

    def cmd_switch_to_arrangement_view(self, params):
        return self._switch_to_arrangement_view()

    def cmd_set_current_song_time(self, params):
        time_val = params.get("time", 0.0)
        return self._set_current_song_time(time_val)

    def cmd_duplicate_session_clip_to_arrangement(self, params):
        track_index = params.get("track_index", 0)
        clip_index = params.get("clip_index", 0)
        destination_time = params.get("destination_time", 0.0)
        return self._duplicate_session_clip_to_arrangement(
            track_index, clip_index, destination_time)

    def cmd_map_rack_magnitude(self, params):
        track_index = params.get("track_index", 0)
        device_index = params.get("device_index", 0)
        macro_name = params.get("macro_name", "Magnitude")
        return self._map_rack_magnitude(
            track_index, device_index, macro_name)

    def cmd_inspect_rack(self, params):
        track_index = params.get("track_index", 0)
        device_index = params.get("device_index", 0)
        return self._inspect_rack(track_index, device_index)

    def cmd_introspect(self, params):
        return self._introspect(
            params.get("path", ""),
            params.get("include_methods", False))

    def cmd_get_set_overview(self, params):
        return self._get_set_overview(
            params.get("include_params", False))

    def cmd_get_routing(self, params):
        return self._get_routing(
            params.get("track_index", 0),
            params.get("device_index", None))

    def cmd_get_params(self, params):
        return self._get_params(params.get("path", ""))

    def cmd_set_param(self, params):
        return self._set_param(
            params.get("path", ""),
            params.get("param", ""),
            params.get("value", 0.0))

    def cmd_set_routing(self, params):
        return self._set_routing(
            params.get("path", ""),
            params.get("routing_type", None),
            params.get("routing_channel", None))

    def cmd_record_automation(self, params):
        return self._record_automation(params.get("param_path", ""), params.get("points", []),
                                       params.get("pre_roll", 1.0), params.get("post_roll", 0.5))

    def cmd_get_record_automation(self, params):
        return self._record_status()

    def cmd_play_from(self, params):
        """start, then seek: start_playing begins at the start marker regardless of
        a prior seek, but setting current_song_time while playing jumps playback."""
        t = float(params.get("time", 0.0))
        if not self._song.is_playing:
            self._song.start_playing()
        self._song.current_song_time = t
        return {"is_playing": True, "requested_time": t}

    def cmd_call(self, params):
        return self._call(params.get("path", ""), params.get("method", ""), params.get("args", []))

    def cmd_set_attr(self, params):
        return self._set_attr(params.get("path", ""), params.get("attr", ""), params.get("value"))

    def cmd_get_song_file(self, params):
        return {"file_path": self._song.file_path, "name": self._song.name}

    def cmd_get_automated_params(self, params):
        return self._get_automated_params()

    def cmd_get_arrangement_envelope(self, params):
        return self._get_arrangement_envelope(params.get("param_path", ""), params.get("resolution", 1.0))

    def cmd_start_capture(self, params):
        return self._start_capture(params.get("meters", True), params.get("automation", True))

    def cmd_get_capture(self, params):
        return self._capture_report(params.get("resolution", 1.0))

    def cmd_stop_capture(self, params):
        return self._stop_capture(params.get("resolution", 1.0))

    def cmd_get_session_info(self, params):
        return self._get_session_info()

    def cmd_get_track_info(self, params):
        track_index = params.get("track_index", 0)
        return self._get_track_info(track_index)

    def cmd_get_browser_item(self, params):
        uri = params.get("uri", None)
        path = params.get("path", None)
        return self._get_browser_item(uri, path)

    def cmd_get_browser_tree(self, params):
        category_type = params.get("category_type", "all")
        return self.get_browser_tree(category_type)

    def cmd_get_browser_items_at_path(self, params):
        path = params.get("path", "")
        return self.get_browser_items_at_path(path)

    def cmd_get_arrangement_clips(self, params):
        track_index = params.get("track_index", 0)
        return self._get_arrangement_clips(track_index)

    # ── implementations ──────────────────────────────────────────────

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
    
    def _get_device_params(self, track_index, device_index):
        """List a device's parameters: name, value, range, display value"""
        try:
            track = self._song.tracks[track_index]
            device = track.devices[device_index]
            out = []
            for i, p in enumerate(device.parameters):
                out.append({
                    "index": i,
                    "name": p.name,
                    "value": p.value,
                    "min": p.min,
                    "max": p.max,
                    "display": str(p.str_for_value(p.value)),
                    "is_quantized": p.is_quantized,
                })
            return {"device": device.name, "params": out}
        except Exception as e:
            self.log_message("Error getting device params: " + str(e))
            raise

    def _set_device_param(self, track_index, device_index, param, value):
        """Set a device parameter by name or index. value is in the param's native range."""
        try:
            track = self._song.tracks[track_index]
            device = track.devices[device_index]
            target = None
            if isinstance(param, int):
                target = device.parameters[param]
            else:
                for p in device.parameters:
                    if p.name == param:
                        target = p
                        break
            if target is None:
                raise Exception("Parameter not found: " + str(param))
            value = max(target.min, min(target.max, float(value)))
            target.value = value
            return {
                "device": device.name,
                "param": target.name,
                "value": target.value,
                "display": str(target.str_for_value(target.value)),
            }
        except Exception as e:
            self.log_message("Error setting device param: " + str(e))
            raise

    def _set_track_volume(self, track_index, value):
        """Set track mixer volume (0.0-1.0, 0.85 = 0dB)"""
        try:
            track = self._song.tracks[track_index]
            track.mixer_device.volume.value = max(0.0, min(1.0, float(value)))
            return {"track": track.name, "volume": track.mixer_device.volume.value}
        except Exception as e:
            self.log_message("Error setting track volume: " + str(e))
            raise

    def _resolve_clip_and_param(self, track_index, clip_index, device_index, param):
        """Resolve a session clip plus a device parameter by name or index"""
        clip_slot = self._song.tracks[track_index].clip_slots[clip_index]
        if not clip_slot.has_clip:
            raise Exception("No clip in slot")
        device = self._song.tracks[track_index].devices[device_index]
        target = None
        if isinstance(param, int):
            target = device.parameters[param]
        else:
            for p in device.parameters:
                if p.name == param:
                    target = p
                    break
        if target is None:
            raise Exception("Parameter not found: " + str(param))
        return clip_slot.clip, target

    def _get_clip_envelope(self, track_index, clip_index, device_index, param, resolution=0.25):
        """Sample a clip's automation envelope for a device parameter"""
        try:
            clip, target = self._resolve_clip_and_param(track_index, clip_index, device_index, param)
            env = clip.automation_envelope(target)
            if env is None:
                return {"has_envelope": False, "param": target.name}
            samples = []
            t = 0.0
            step = max(0.05, float(resolution))
            while t < clip.length:
                v = env.value_at_time(t)
                samples.append({
                    "time": round(t, 4),
                    "value": v,
                    "display": str(target.str_for_value(v)),
                })
                t += step
            return {"has_envelope": True, "param": target.name,
                    "clip_length": clip.length, "samples": samples}
        except Exception as e:
            self.log_message("Error reading clip envelope: " + str(e))
            raise

    def _set_clip_envelope(self, track_index, clip_index, device_index, param, steps, clear=True):
        """Write step automation into a clip envelope. steps: [{time, length, value}]"""
        try:
            clip, target = self._resolve_clip_and_param(track_index, clip_index, device_index, param)
            if clear:
                try:
                    clip.clear_envelope(target)
                except Exception:
                    pass
            env = clip.automation_envelope(target)
            if env is None:
                env = clip.create_automation_envelope(target)
            for s in steps:
                start = float(s.get("time", 0.0))
                length = float(s.get("length", 0.0))
                value = max(target.min, min(target.max, float(s.get("value", 0.0))))
                env.insert_step(start, length, value)
            return {"param": target.name, "steps_written": len(steps)}
        except Exception as e:
            self.log_message("Error writing clip envelope: " + str(e))
            raise

    def _get_clip_notes(self, track_index, clip_index):
        """Read all notes from a session MIDI clip"""
        try:
            clip_slot = self._song.tracks[track_index].clip_slots[clip_index]
            if not clip_slot.has_clip:
                raise Exception("No clip in slot")
            clip = clip_slot.clip
            notes = clip.get_notes_extended(0, 128, 0.0, clip.length)
            out = []
            for n in notes:
                out.append({
                    "pitch": n.pitch,
                    "start_time": n.start_time,
                    "duration": n.duration,
                    "velocity": n.velocity,
                    "mute": n.mute,
                })
            return {"clip_name": clip.name, "length": clip.length, "notes": out}
        except Exception as e:
            self.log_message("Error reading clip notes: " + str(e))
            raise

    def _get_device_chains(self, track_index, device_index):
        """List chains (e.g. drum rack pads) of a rack device with volumes"""
        try:
            device = self._song.tracks[track_index].devices[device_index]
            if not device.can_have_chains:
                raise Exception("Device has no chains")
            out = []
            for i, ch in enumerate(device.chains):
                out.append({
                    "index": i,
                    "name": ch.name,
                    "volume": ch.mixer_device.volume.value,
                })
            return {"device": device.name, "chains": out}
        except Exception as e:
            self.log_message("Error listing device chains: " + str(e))
            raise

    def _set_chain_volume(self, track_index, device_index, chain_index, value):
        """Set the mixer volume of a rack chain (drum pad)"""
        try:
            device = self._song.tracks[track_index].devices[device_index]
            ch = device.chains[chain_index]
            ch.mixer_device.volume.value = max(0.0, min(1.0, float(value)))
            return {"chain": ch.name, "volume": ch.mixer_device.volume.value}
        except Exception as e:
            self.log_message("Error setting chain volume: " + str(e))
            raise

    def _set_master_volume(self, value):
        """Set master output volume (0.0-1.0, 0.85 = 0dB)"""
        try:
            mv = self._song.master_track.mixer_device.volume
            mv.value = max(0.0, min(1.0, float(value)))
            return {"master_volume": mv.value}
        except Exception as e:
            self.log_message("Error setting master volume: " + str(e))
            raise

    def _set_send_level(self, track_index, send_index, value):
        """Set a track's send level (0.0-1.0)"""
        try:
            track = self._song.tracks[track_index]
            send = track.mixer_device.sends[send_index]
            send.value = max(0.0, min(1.0, float(value)))
            return {"track": track.name, "send": send_index, "level": send.value}
        except Exception as e:
            self.log_message("Error setting send level: " + str(e))
            raise

    def _delete_clip(self, track_index, clip_index):
        """Delete the clip in the given session slot"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            track = self._song.tracks[track_index]
            if clip_index < 0 or clip_index >= len(track.clip_slots):
                raise IndexError("Clip index out of range")
            clip_slot = track.clip_slots[clip_index]
            if not clip_slot.has_clip:
                raise Exception("No clip in slot")
            name = clip_slot.clip.name
            clip_slot.delete_clip()
            return {"deleted": True, "clip_name": name}
        except Exception as e:
            self.log_message("Error deleting clip: " + str(e))
            raise

    def _delete_track(self, track_index):
        """Delete a track by index"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            name = self._song.tracks[track_index].name
            self._song.delete_track(track_index)
            return {"deleted": True, "track_name": name}
        except Exception as e:
            self.log_message("Error deleting track: " + str(e))
            raise

    def _delete_device(self, track_index, device_index):
        """Delete a device from a track's chain"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            track = self._song.tracks[track_index]
            if device_index < 0 or device_index >= len(track.devices):
                raise IndexError("Device index out of range")
            name = track.devices[device_index].name
            track.delete_device(device_index)
            return {"deleted": True, "device_name": name}
        except Exception as e:
            self.log_message("Error deleting device: " + str(e))
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
    

    # ── generic LOM introspection ─────────────────────────────────────
    _PATH_TOKEN = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)|\[(-?\d+)\]")

    def _resolve_lom_path(self, path):
        """Resolve a path like 'tracks[0].devices[1].parameters[3]' relative to the song.
        'master_track', 'return_tracks[0]', 'view', '' (song itself) all work."""
        obj = self._song
        for name, idx in self._PATH_TOKEN.findall(path or ""):
            if name:
                obj = getattr(obj, name)
            else:
                obj = obj[int(idx)]
        return obj

    def _safe_repr(self, v, depth=0):
        if isinstance(v, (bool, int, float)) or v is None:
            return v
        if isinstance(v, str):
            return v
        try:
            seq = list(v)
            if depth > 0:
                return "<%d items>" % len(seq)
            return [self._safe_repr(x, depth + 1) for x in seq[:64]] + (["..."] if len(seq) > 64 else [])
        except Exception:
            pass
        name = None
        for key in ("display_name", "name"):
            name = self._try(lambda: getattr(v, key))
            if name is not None:
                break
        cls = type(v).__name__
        if name is not None:
            try:
                return "<%s %r>" % (cls, str(name))
            except Exception:
                pass
        return "<%s>" % cls

    def _introspect(self, path, include_methods=False):
        """dir() an arbitrary LOM object and read every non-callable attribute.
        the tool for discovering what live actually exposes (sidechain routing, etc.)."""
        obj = self._resolve_lom_path(path)
        attrs, methods, errors = {}, [], {}
        for a in dir(obj):
            if a.startswith("_"):
                continue
            try:
                v = getattr(obj, a)
            except Exception as e:
                errors[a] = str(e)
                continue
            if callable(v):
                methods.append(a)
            else:
                try:
                    attrs[a] = self._safe_repr(v)
                except Exception as e:
                    errors[a] = str(e)
        out = {"path": path, "type": type(obj).__name__, "attrs": attrs, "errors": errors}
        if include_methods:
            out["methods"] = methods
        return out

    def _resolve_arg(self, a):
        """args may be plain json values or {"path": "..."} references to LOM objects."""
        if isinstance(a, dict) and "path" in a and len(a) == 1:
            return self._resolve_lom_path(a["path"])
        return a

    def _call(self, path, method, args):
        """call a method on any LOM object: e.g. call('', 'begin_undo_step'),
        call('tracks[3].arrangement_clips[0]', 'create_automation_envelope',
             [{"path": "tracks[3].devices[1].parameters[9]"}])."""
        obj = self._resolve_lom_path(path)
        fn = getattr(obj, method)
        result = fn(*[self._resolve_arg(a) for a in (args or [])])
        return {"path": path, "method": method, "result": self._safe_repr(result)}

    def _set_attr(self, path, attr, value):
        obj = self._resolve_lom_path(path)
        before = self._safe_repr(getattr(obj, attr))
        setattr(obj, attr, self._resolve_arg(value))
        return {"path": path, "attr": attr, "before": before, "after": self._safe_repr(getattr(obj, attr))}

    def _routing_summary(self, obj):
        """read the standard LOM routing attrs if the object has them."""
        out = {}
        for key in ("input_routing_type", "input_routing_channel",
                    "output_routing_type", "output_routing_channel"):
            if hasattr(obj, key):
                try:
                    r = getattr(obj, key)
                    out[key] = getattr(r, "display_name", None)
                except Exception as e:
                    out[key] = "error: " + str(e)
        for key in ("available_input_routing_types", "available_input_routing_channels",
                    "available_output_routing_types", "available_output_routing_channels"):
            if hasattr(obj, key):
                try:
                    out[key] = [getattr(r, "display_name", str(r)) for r in getattr(obj, key)]
                except Exception as e:
                    out[key] = "error: " + str(e)
        return out

    def _get_routing(self, track_index, device_index=None):
        """routing for a track, or for one of its devices (e.g. a compressor's sidechain input)."""
        track = self._all_tracks()[track_index]
        if device_index is None:
            return {"track": track.name, "routing": self._routing_summary(track)}
        device = track.devices[device_index]
        return {"track": track.name, "device": device.name,
                "class_name": device.class_name, "routing": self._routing_summary(device)}

    def _all_tracks(self):
        """tracks + return tracks + master, in one index space (tracks first)."""
        return list(self._song.tracks) + list(self._song.return_tracks) + [self._song.master_track]

    def _device_summary(self, device, include_params, path=""):
        d = {
            "path": path,
            "name": device.name,
            "class_name": device.class_name,
            "is_active": self._try(lambda: device.is_active),
            "type": self._get_device_type(device),
        }
        routing = self._routing_summary(device)
        if routing:
            d["routing"] = routing
        if include_params:
            d["params"] = [
                {"index": i, "name": p.name, "value": p.value,
                 "display": str(p.str_for_value(p.value)),
                 "min": p.min, "max": p.max}
                for i, p in enumerate(device.parameters)
            ]
        else:
            d["param_count"] = len(device.parameters)
        if self._try(lambda: device.can_have_chains, False):
            d["chains"] = [
                {"index": ci, "name": ch.name, "path": "%s.chains[%d]" % (path, ci),
                 "mute": self._try(lambda: ch.mute), "solo": self._try(lambda: ch.solo),
                 "devices": [self._device_summary(cd, include_params, "%s.chains[%d].devices[%d]" % (path, ci, di))
                             for di, cd in enumerate(ch.devices)]}
                for ci, ch in enumerate(device.chains)
            ]
        return d

    def _try(self, fn, default=None):
        try:
            return fn()
        except Exception:
            return default

    def _track_summary(self, track, index, kind, include_params, path):
        mixer = track.mixer_device
        t = {
            "index": index,
            "path": path,
            "kind": kind,
            "name": track.name,
            "mute": self._try(lambda: track.mute),
            "solo": self._try(lambda: track.solo),
            "volume": mixer.volume.value,
            "volume_display": str(mixer.volume.str_for_value(mixer.volume.value)),
            "panning": mixer.panning.value,
            "sends": [{"index": i, "value": s.value, "display": str(s.str_for_value(s.value))}
                      for i, s in enumerate(mixer.sends)],
            "routing": self._routing_summary(track),
            "devices": [self._device_summary(d, include_params, "%s.devices[%d]" % (path, i))
                        for i, d in enumerate(track.devices)],
        }
        return t

    def _get_set_overview(self, include_params=False):
        """the whole set in one read: tracks, returns, master — mixer, routing, devices."""
        tracks = [self._track_summary(t, i, "track", include_params, "tracks[%d]" % i)
                  for i, t in enumerate(self._song.tracks)]
        returns = [self._track_summary(t, i, "return", include_params, "return_tracks[%d]" % i)
                   for i, t in enumerate(self._song.return_tracks)]
        master = self._track_summary(self._song.master_track, 0, "master", include_params, "master_track")
        return {
            "tempo": self._song.tempo,
            "note": "every track/device carries a 'path' usable with get_params / set_param / "
                    "set_routing / introspect.",
            "tracks": tracks,
            "return_tracks": returns,
            "master_track": master,
        }


    # ── path-addressed params / routing (reach master, returns, rack chains) ──
    def _param_info(self, i, p):
        return {"index": i, "name": p.name, "value": p.value,
                "display": str(p.str_for_value(p.value)),
                "min": p.min, "max": p.max,
                "is_quantized": p.is_quantized,
                "is_enabled": self._try(lambda: p.is_enabled, True)}

    def _get_params(self, path):
        """parameters of any device addressed by LOM path,
        e.g. 'master_track.devices[1].chains[0].devices[1]'."""
        device = self._resolve_lom_path(path)
        out = {"path": path, "device": device.name, "class_name": device.class_name,
               "is_active": self._try(lambda: device.is_active),
               "params": [self._param_info(i, p) for i, p in enumerate(device.parameters)]}
        routing = self._routing_summary(device)
        if routing:
            out["routing"] = routing
        return out

    def _set_param(self, path, param, value):
        device = self._resolve_lom_path(path)
        target = None
        if isinstance(param, int):
            target = device.parameters[param]
        else:
            for p in device.parameters:
                if p.name == param:
                    target = p
                    break
        if target is None:
            raise Exception("Parameter not found: " + str(param))
        before = target.value
        target.value = max(target.min, min(target.max, float(value)))
        return {"path": path, "device": device.name, "param": target.name,
                "before": before, "before_display": str(target.str_for_value(before)),
                "value": target.value, "display": str(target.str_for_value(target.value))}

    def _set_routing(self, path, routing_type=None, routing_channel=None):
        """set input routing on a device (compressor sidechain) or track by display_name.
        type first, then channel — changing the type changes the available channels."""
        obj = self._resolve_lom_path(path)
        if routing_type is not None:
            match = [r for r in obj.available_input_routing_types if r.display_name == routing_type]
            if not match:
                raise Exception("routing type %r not in %r" % (
                    routing_type, [r.display_name for r in obj.available_input_routing_types]))
            obj.input_routing_type = match[0]
        if routing_channel is not None:
            match = [c for c in obj.available_input_routing_channels if c.display_name == routing_channel]
            if not match:
                raise Exception("routing channel %r not in %r" % (
                    routing_channel, [c.display_name for c in obj.available_input_routing_channels]))
            obj.input_routing_channel = match[0]
        return {"path": path, "routing": self._routing_summary(obj)}

    # ── automation ───────────────────────────────────────────────────
    AUTOMATION_STATES = {0: "none", 1: "playing", 2: "overridden"}

    def _walk_params(self):
        """yield (track_path, track_name, owner_path, owner_name, param_index, param)
        for every device parameter (recursing racks) and mixer parameter in the set."""
        def walk_devices(devices, base, track_path, track_name):
            for di, d in enumerate(devices):
                dpath = "%s.devices[%d]" % (base, di)
                for pi, p in enumerate(d.parameters):
                    yield (track_path, track_name, dpath, d.name, pi, p)
                if self._try(lambda: d.can_have_chains, False):
                    for ci, ch in enumerate(d.chains):
                        for item in walk_devices(ch.devices, "%s.chains[%d]" % (dpath, ci), track_path, track_name):
                            yield item
        for track_path, track_name, tr in self._meter_targets():
            m = tr.mixer_device
            mixer = [("volume", m.volume), ("panning", m.panning)]
            mixer += [("sends[%d]" % i, snd) for i, snd in enumerate(m.sends)]
            for name, p in mixer:
                yield (track_path, track_name, track_path + ".mixer_device", "mixer", name, p)
            for item in walk_devices(tr.devices, track_path, track_path, track_name):
                yield item

    def _get_automated_params(self):
        """every parameter in the set whose automation_state is not 'none'."""
        out = []
        for track_path, track_name, owner_path, owner_name, pi, p in self._walk_params():
            state = self._try(lambda: p.automation_state, 0)
            if state:
                out.append({"track": track_name, "track_path": track_path,
                            "device": owner_name, "device_path": owner_path,
                            "param": p.name, "param_index": pi,
                            "param_path": "%s.parameters[%d]" % (owner_path, pi) if isinstance(pi, int) else "%s.%s" % (owner_path, pi),
                            "automation_state": self.AUTOMATION_STATES.get(state, state),
                            "value": p.value, "display": str(p.str_for_value(p.value))})
        return {"count": len(out), "params": out}

    def _track_of_path(self, path):
        m = re.match(r"(tracks\[\d+\]|return_tracks\[\d+\]|master_track)", path or "")
        if not m:
            raise Exception("path must start with tracks[i], return_tracks[i] or master_track")
        return m.group(1), self._resolve_lom_path(m.group(1))

    def _get_arrangement_envelope(self, param_path, resolution=1.0):
        """sample a parameter's arrangement automation, clip by clip, in beats."""
        param = self._resolve_lom_path(param_path)
        track_path, track = self._track_of_path(param_path)
        step = max(0.0625, float(resolution))
        clips = []
        for clip in track.arrangement_clips:
            env = self._try(lambda: clip.automation_envelope(param))
            if env is None:
                clips.append({"clip": clip.name, "start_time": clip.start_time, "end_time": clip.end_time, "has_envelope": False})
                continue
            samples = []
            t = 0.0
            while t < clip.length:
                v = env.value_at_time(t)
                samples.append([round(clip.start_time + t, 4), v])
                t += step
            clips.append({"clip": clip.name, "start_time": clip.start_time, "end_time": clip.end_time,
                          "has_envelope": True, "samples": samples})
        return {"param_path": param_path, "param": param.name, "min": param.min, "max": param.max,
                "automation_state": self.AUTOMATION_STATES.get(self._try(lambda: param.automation_state, 0)),
                "track": track.name, "clips": clips}

    # ── automation recording ─────────────────────────────────────────
    # the LOM cannot write arrangement lanes directly, but Live records a lane
    # when a parameter moves during playback with record_mode on. so: seek just
    # before the first point, enable record, play, and apply the (linearly
    # interpolated) values each main-thread tick until past the last point.
    # wrapped in one undo step; all tracks are disarmed for the pass and restored.

    _rec = None

    def _record_automation(self, param_path, points, pre_roll=1.0, post_roll=0.5):
        if Handlers._rec and Handlers._rec["state"] == "recording":
            raise Exception("a recording pass is already running")
        pts = sorted((float(t), float(v)) for t, v in points)
        if not pts:
            raise Exception("points required: [[beat, value], ...]")
        param = self._resolve_lom_path(param_path)
        song = self._song
        script = self._script
        t_first, t_last = pts[0][0], pts[-1][0]
        arms = [(tr, tr.arm) for tr in song.tracks if self._try(lambda: tr.can_be_armed, False)]
        rec = {"state": "recording", "param_path": param_path, "param": param.name,
               "points": pts, "applied": 0, "t_start": max(0.0, t_first - float(pre_roll)),
               "t_end": t_last + float(post_roll), "arms": arms,
               "prev": {"record_mode": song.record_mode, "song_time": song.current_song_time,
                        "session_automation_record": song.session_automation_record},
               "log": []}
        Handlers._rec = rec

        def value_at(t):
            if t <= pts[0][0]:
                return pts[0][1]
            for (ta, va), (tb, vb) in zip(pts, pts[1:]):
                if ta <= t <= tb:
                    return vb if tb == ta else va + (t - ta) / (tb - ta) * (vb - va)
            return pts[-1][1]

        def finish():
            try:
                song.stop_playing()
            finally:
                song.record_mode = rec["prev"]["record_mode"]
                song.session_automation_record = rec["prev"]["session_automation_record"]
                for tr, a in arms:
                    self._try(lambda: setattr(tr, "arm", a))
                song.current_song_time = rec["prev"]["song_time"]
                song.end_undo_step()
                rec["state"] = "done"

        def tick():
            if rec["state"] != "recording":
                return
            try:
                t = song.current_song_time
                if t >= rec["t_end"] or not song.is_playing:
                    finish()
                    return
                if t >= pts[0][0]:
                    v = max(param.min, min(param.max, value_at(t)))
                    if param.value != v:
                        param.value = v
                        rec["applied"] += 1
                        if len(rec["log"]) < 400:
                            rec["log"].append([round(t, 3), v])
            except Exception as e:
                self.log_message("record_automation tick error: " + str(e))
                rec["state"] = "error"
                rec["error"] = str(e)
                self._try(finish)
                return
            script.schedule_message(1, tick)

        song.begin_undo_step()
        for tr, _ in arms:
            self._try(lambda: setattr(tr, "arm", False))
        song.session_automation_record = True
        song.record_mode = True
        song.start_playing()
        song.current_song_time = rec["t_start"]
        script.schedule_message(1, tick)
        return self._record_status()

    def _record_status(self):
        rec = Handlers._rec
        if rec is None:
            return {"state": "none"}
        return {"state": rec["state"], "param": rec["param"], "param_path": rec["param_path"],
                "t_start": rec["t_start"], "t_end": rec["t_end"], "applied": rec["applied"],
                "error": rec.get("error"), "log": rec["log"][-20:]}

    # ── metering ─────────────────────────────────────────────────────
    # values are Live's raw 0.0-1.0 output meter readings (peak, smoothed by Live).
    # no dB mapping is documented, so compare them relatively. every meter read runs
    # on Live's main thread: the capture re-arms itself with schedule_message
    # (one tick per Live timer tick, ~100ms) so nothing touches the LOM off-thread.

    def _meter_targets(self):
        t = [("tracks[%d]" % i, tr.name, tr) for i, tr in enumerate(self._song.tracks)]
        t += [("return_tracks[%d]" % i, tr.name, tr) for i, tr in enumerate(self._song.return_tracks)]
        t += [("master_track", "Main", self._song.master_track)]
        return t

    def _new_meter_stats(self):
        return dict((path, {"name": name, "peak": 0.0, "sum": 0.0, "n": 0, "clip_frames": 0})
                    for path, name, _ in self._meter_targets())

    def _meter_tick(self, stats):
        for path, name, tr in self._meter_targets():
            st = stats.get(path)
            if st is None:
                continue
            l, r = tr.output_meter_left, tr.output_meter_right
            st["peak"] = max(st["peak"], l, r)
            st["sum"] += (l + r) / 2.0
            st["n"] += 1
            if l >= 1.0 or r >= 1.0:
                st["clip_frames"] += 1

    def _meter_report(self, stats, seconds, state):
        rows = [{"path": path, "name": st["name"], "peak": st["peak"],
                 "mean": (st["sum"] / st["n"]) if st["n"] else 0.0,
                 "clip_frames": st["clip_frames"]} for path, st in stats.items()]
        rows.sort(key=lambda x: -x["peak"])
        return {"state": state, "seconds": seconds,
                "samples": stats["master_track"]["n"] if "master_track" in stats else 0,
                "tracks": rows}

    _capture = None

    def _start_capture(self, meters=True, automation=True):
        """record, once per Live timer tick on the main thread, the song position plus
        (optionally) every track's output meter and the value of every automated
        parameter. runs until stop_capture; the caller drives playback separately."""
        if Handlers._capture and Handlers._capture["running"]:
            return self._capture_report()
        params = []
        if automation:
            for row in self._get_automated_params()["params"]:
                params.append((row, self._resolve_lom_path(row["param_path"])))
        cap = {"running": True, "t0": time.time(), "t1": None, "ticks": 0,
               "meters": self._new_meter_stats() if meters else None,
               "params": params, "series": [[] for _ in params],
               "times": []}
        script = self._script
        song = self._song

        def tick():
            if not cap["running"]:
                return
            try:
                cap["ticks"] += 1
                if cap["meters"] is not None and song.is_playing:
                    self._meter_tick(cap["meters"])
                if cap["params"]:
                    t = song.current_song_time
                    cap["times"].append(t)
                    for i, (_, p) in enumerate(cap["params"]):
                        cap["series"][i].append(p.value)
            except Exception as e:
                self.log_message("capture tick error: " + str(e))
            script.schedule_message(1, tick)

        Handlers._capture = cap
        script.schedule_message(1, tick)
        return {"state": "running", "meters": meters, "automated_params": len(params)}

    def _capture_report(self, resolution=1.0):
        """meters: peak/mean per track. automation: per param, values bucketed by song
        position at `resolution` beats (mean of samples in the bucket), so a 4-bar
        sweep reads as a short list rather than hundreds of ticks."""
        cap = Handlers._capture
        if cap is None:
            return {"state": "none"}
        end = cap["t1"] or time.time()
        out = {"state": "running" if cap["running"] else "stopped",
               "seconds": end - cap["t0"], "ticks": cap["ticks"]}
        if cap["meters"] is not None:
            out["meters"] = self._meter_report(cap["meters"], end - cap["t0"], out["state"])["tracks"]
        if cap["params"]:
            step = max(0.0625, float(resolution))
            times = cap["times"]
            rows = []
            for (row, p), series in zip(cap["params"], cap["series"]):
                buckets = {}
                for t, v in zip(times, series):
                    b = int(t // step)
                    acc = buckets.setdefault(b, [0.0, 0])
                    acc[0] += v
                    acc[1] += 1
                pts = [[round(b * step, 4), buckets[b][0] / buckets[b][1]] for b in sorted(buckets)]
                vals = [v for _, v in pts]
                rows.append({"track": row["track"], "device": row["device"], "param": row["param"],
                             "param_path": row["param_path"], "min": p.min, "max": p.max,
                             "observed_min": min(vals) if vals else None,
                             "observed_max": max(vals) if vals else None,
                             "display_min": str(p.str_for_value(min(vals))) if vals else None,
                             "display_max": str(p.str_for_value(max(vals))) if vals else None,
                             "points": pts})
            out["automation"] = {"resolution_beats": step,
                                 "song_time_range": [min(times), max(times)] if times else None,
                                 "params": rows}
        return out

    def _stop_capture(self, resolution=1.0):
        cap = Handlers._capture
        if cap is None:
            return {"state": "none"}
        cap["running"] = False
        cap["t1"] = time.time()
        return self._capture_report(resolution)

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

