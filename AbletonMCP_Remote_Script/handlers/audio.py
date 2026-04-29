"""Audio: load samples, warp, crop, reverse, analyze, freeze, export."""

from __future__ import absolute_import, print_function, unicode_literals

import time
import traceback


def load_audio_sample(
    song, track_index, clip_index, file_path, browser_uri, ctrl=None
):
    """Load an audio sample into a clip slot."""
    try:
        if track_index < 0 or track_index >= len(song.tracks):
            raise IndexError("Track index out of range")
        track = song.tracks[track_index]
        if clip_index < 0 or clip_index >= len(track.clip_slots):
            raise IndexError("Clip index out of range")
        clip_slot = track.clip_slots[clip_index]
        if ctrl is None:
            raise RuntimeError("load_audio_sample requires ctrl for application()")
        app = ctrl.application()
        if not app:
            raise RuntimeError("Could not access Live application")
        # Live's browser.load_item targets the focused location in the UI.
        # For an audio sample to land in the *clip slot* (rather than the
        # device chain or some hotswap target), we must set both the
        # selected_track AND highlighted_clip_slot. Setting only the
        # clip slot caused loads to silently drop.
        try:
            song.view.selected_track = track
        except Exception:
            pass
        # Selected scene drives "selected clip slot" together with selected_track
        try:
            if clip_index < len(song.scenes):
                song.view.selected_scene = song.scenes[clip_index]
        except Exception:
            pass
        song.view.highlighted_clip_slot = clip_slot
        if browser_uri:
            from . import browser as browser_mod
            item = browser_mod.find_browser_item_by_uri(
                app.browser, browser_uri, ctrl=ctrl
            )
            if not item:
                raise ValueError(
                    "Browser item with URI '{0}' not found".format(browser_uri)
                )
            # Live's Browser exposes a dedicated method for putting samples
            # into the *selected* clip slot — use it when available, fall
            # back to plain load_item otherwise (older Live versions).
            if hasattr(app.browser, "load_item_into_selected_clipslot"):
                app.browser.load_item_into_selected_clipslot(item)
            else:
                app.browser.load_item(item)
            # Sample import can take a moment for larger files / first-touch
            for _ in range(20):
                time.sleep(0.1)
                if clip_slot.has_clip:
                    break
            if not clip_slot.has_clip:
                raise RuntimeError(
                    "load_item ran but no clip materialized in slot {0} of track {1} "
                    "(uri={2}).".format(
                        clip_index, track_index, browser_uri
                    )
                )
        elif file_path:
            if ctrl:
                ctrl.log_message(
                    "Attempting to load audio from path: {0}".format(file_path)
                )
            raise NotImplementedError(
                "Direct file path loading is not yet fully implemented. "
                "Please use browser_uri parameter with a browser item URI instead."
            )
        else:
            raise ValueError("Either file_path or browser_uri must be provided")
        time.sleep(0.2)
        result = {
            "loaded": True,
            "track_index": track_index,
            "clip_index": clip_index,
            "has_clip": clip_slot.has_clip,
        }
        if clip_slot.has_clip:
            clip = clip_slot.clip
            result["clip_name"] = clip.name
            result["is_audio_clip"] = clip.is_audio_clip
        return result
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error loading audio sample: " + str(e))
        raise


def get_all_clip_gains(song, track_indices=None, ctrl=None):
    """Get clip gain for the first clip on each specified track."""
    try:
        if track_indices is None:
            track_indices = list(range(len(song.tracks)))
        results = []
        for i in track_indices:
            if i < 0 or i >= len(song.tracks):
                continue
            track = song.tracks[i]
            for slot_index, slot in enumerate(track.clip_slots):
                if slot.has_clip:
                    clip = slot.clip
                    if clip.is_audio_clip:
                        gain_val = getattr(clip, "gain", None)
                        gain_db = None
                        try:
                            gain_db = clip.gain_display_string
                        except Exception:
                            pass
                        results.append({
                            "track_index": i,
                            "track_name": track.name,
                            "clip_index": slot_index,
                            "clip_name": clip.name,
                            "gain": gain_val,
                            "gain_display": gain_db,
                        })
                    break  # only first clip per track
        return {"clips": results, "count": len(results)}
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error getting clip gains: " + str(e))
        raise


def set_clip_gain(song, track_index, clip_index, gain, ctrl=None):
    """Set clip gain. gain is the raw API value (0.0-1.0)."""
    try:
        if track_index < 0 or track_index >= len(song.tracks):
            raise IndexError("Track index out of range")
        track = song.tracks[track_index]
        if clip_index < 0 or clip_index >= len(track.clip_slots):
            raise IndexError("Clip index out of range")
        clip_slot = track.clip_slots[clip_index]
        if not clip_slot.has_clip:
            raise Exception("No clip in slot")
        clip = clip_slot.clip
        if not clip.is_audio_clip:
            raise Exception("Clip is not an audio clip")
        clip.gain = float(gain)
        gain_db = None
        try:
            gain_db = clip.gain_display_string
        except Exception:
            pass
        return {
            "track_index": track_index,
            "clip_index": clip_index,
            "gain": clip.gain,
            "gain_display": gain_db,
        }
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error setting clip gain: " + str(e))
        raise


def get_audio_clip_info(song, track_index, clip_index, ctrl=None):
    """Get information about an audio clip."""
    try:
        if track_index < 0 or track_index >= len(song.tracks):
            raise IndexError("Track index out of range")
        track = song.tracks[track_index]
        if clip_index < 0 or clip_index >= len(track.clip_slots):
            raise IndexError("Clip index out of range")
        clip_slot = track.clip_slots[clip_index]
        if not clip_slot.has_clip:
            raise Exception("No clip in slot")
        clip = clip_slot.clip
        if not clip.is_audio_clip:
            raise Exception("Clip is not an audio clip")
        warp_mode_map = {
            0: "beats",
            1: "tones",
            2: "texture",
            3: "re_pitch",
            4: "complex",
            5: "complex_pro",
        }
        warp_mode = "unknown"
        if hasattr(clip, "warp_mode"):
            warp_mode = warp_mode_map.get(clip.warp_mode, "unknown")
        return {
            "name": clip.name,
            "length": clip.length,
            "is_audio_clip": clip.is_audio_clip,
            "warping": getattr(clip, "warping", None),
            "warp_mode": warp_mode,
            "start_marker": getattr(clip, "start_marker", None),
            "end_marker": getattr(clip, "end_marker", None),
            "loop_start": getattr(clip, "loop_start", None),
            "loop_end": getattr(clip, "loop_end", None),
            "gain": getattr(clip, "gain", None),
            "file_path": getattr(clip, "file_path", None),
        }
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error getting audio clip info: " + str(e))
        raise


def set_warp_mode(song, track_index, clip_index, warp_mode, ctrl=None):
    """Set the warp mode for an audio clip."""
    try:
        if track_index < 0 or track_index >= len(song.tracks):
            raise IndexError("Track index out of range")
        track = song.tracks[track_index]
        if clip_index < 0 or clip_index >= len(track.clip_slots):
            raise IndexError("Clip index out of range")
        clip_slot = track.clip_slots[clip_index]
        if not clip_slot.has_clip:
            raise Exception("No clip in slot")
        clip = clip_slot.clip
        if not clip.is_audio_clip:
            raise Exception("Clip is not an audio clip")
        warp_mode_map = {
            "beats": 0,
            "tones": 1,
            "texture": 2,
            "re_pitch": 3,
            "complex": 4,
            "complex_pro": 5,
        }
        if warp_mode.lower() not in warp_mode_map:
            raise ValueError(
                "Invalid warp mode. Must be one of: beats, tones, texture, "
                "re_pitch, complex, complex_pro"
            )
        clip.warp_mode = warp_mode_map[warp_mode.lower()]
        return {"warp_mode": warp_mode.lower(), "warping": clip.warping}
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error setting warp mode: " + str(e))
        raise


def set_clip_warp(song, track_index, clip_index, warping_enabled, ctrl=None):
    """Enable or disable warping for an audio clip."""
    try:
        if track_index < 0 or track_index >= len(song.tracks):
            raise IndexError("Track index out of range")
        track = song.tracks[track_index]
        if clip_index < 0 or clip_index >= len(track.clip_slots):
            raise IndexError("Clip index out of range")
        clip_slot = track.clip_slots[clip_index]
        if not clip_slot.has_clip:
            raise Exception("No clip in slot")
        clip = clip_slot.clip
        if not clip.is_audio_clip:
            raise Exception("Clip is not an audio clip")
        clip.warping = warping_enabled
        return {"warping": clip.warping}
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error setting clip warp: " + str(e))
        raise


def crop_clip(song, track_index, clip_index, ctrl=None):
    """Crop an audio clip to its loop boundaries."""
    try:
        if track_index < 0 or track_index >= len(song.tracks):
            raise IndexError("Track index out of range")
        track = song.tracks[track_index]
        if clip_index < 0 or clip_index >= len(track.clip_slots):
            raise IndexError("Clip index out of range")
        clip_slot = track.clip_slots[clip_index]
        if not clip_slot.has_clip:
            raise Exception("No clip in slot")
        clip = clip_slot.clip
        if not clip.is_audio_clip:
            raise Exception("Clip is not an audio clip")
        clip.crop()
        return {"cropped": True, "length": clip.length}
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error cropping clip: " + str(e))
        raise


def reverse_clip(song, track_index, clip_index, ctrl=None):
    """Reverse an audio clip."""
    try:
        if track_index < 0 or track_index >= len(song.tracks):
            raise IndexError("Track index out of range")
        track = song.tracks[track_index]
        if clip_index < 0 or clip_index >= len(track.clip_slots):
            raise IndexError("Clip index out of range")
        clip_slot = track.clip_slots[clip_index]
        if not clip_slot.has_clip:
            raise Exception("No clip in slot")
        clip = clip_slot.clip
        if not clip.is_audio_clip:
            raise Exception("Clip is not an audio clip")
        if hasattr(clip, "sample"):
            sample = clip.sample
            if hasattr(sample, "reverse"):
                sample.reverse = not sample.reverse
                return {"reversed": sample.reverse}
        raise NotImplementedError(
            "Audio clip reversal is not available in this version of the API. "
            "You may need to use Ableton's built-in reverse function manually."
        )
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error reversing clip: " + str(e))
        raise


def analyze_audio_clip(song, track_index, clip_index, ctrl=None):
    """Analyze an audio clip comprehensively."""
    try:
        if track_index < 0 or track_index >= len(song.tracks):
            raise IndexError("Track index out of range")
        track = song.tracks[track_index]
        if clip_index < 0 or clip_index >= len(track.clip_slots):
            raise IndexError("Clip index out of range")
        clip_slot = track.clip_slots[clip_index]
        if not clip_slot.has_clip:
            raise Exception("No clip in slot")
        clip = clip_slot.clip
        if not clip.is_audio_clip:
            raise Exception("Clip is not an audio clip")
        warp_mode_map = {
            0: "beats",
            1: "tones",
            2: "texture",
            3: "re_pitch",
            4: "complex",
            5: "complex_pro",
        }
        analysis = {
            "basic_info": {},
            "tempo_rhythm": {},
            "transients": {},
            "audio_properties": {},
            "frequency_analysis": {},
            "waveform_description": {},
        }
        analysis["basic_info"] = {
            "name": clip.name,
            "length_beats": clip.length,
            "loop_start": getattr(clip, "loop_start", None),
            "loop_end": getattr(clip, "loop_end", None),
            "file_path": getattr(clip, "file_path", None),
        }
        analysis["tempo_rhythm"] = {
            "warping_enabled": getattr(clip, "warping", None),
            "warp_mode": (
                warp_mode_map.get(clip.warp_mode, "unknown")
                if hasattr(clip, "warp_mode")
                else None
            ),
            "signature_numerator": getattr(clip, "signature_numerator", None),
            "signature_denominator": getattr(clip, "signature_denominator", None),
        }
        if hasattr(clip, "warping") and clip.warping:
            try:
                analysis["tempo_rhythm"]["detected_bpm"] = song.tempo
                if hasattr(clip, "warp_markers") and clip.warp_markers:
                    analysis["tempo_rhythm"]["has_tempo_automation"] = True
            except Exception:
                pass
        transient_positions = []
        transient_count = 0
        if hasattr(clip, "warp_markers"):
            try:
                warp_markers = clip.warp_markers
                transient_count = len(warp_markers)
                for marker in warp_markers:
                    if hasattr(marker, "sample_time") and hasattr(
                        marker, "beat_time"
                    ):
                        transient_positions.append({
                            "sample_time": marker.sample_time,
                            "beat_time": marker.beat_time,
                        })
                analysis["transients"]["warp_marker_count"] = transient_count
                analysis["transients"]["warp_markers"] = transient_positions[:20]
                if transient_count > 0 and clip.length > 0:
                    density = transient_count / clip.length
                    if density > 4:
                        analysis["transients"]["density"] = "very_high"
                        analysis["transients"]["description"] = (
                            "Very dense, likely drums or percussion"
                        )
                    elif density > 2:
                        analysis["transients"]["density"] = "high"
                        analysis["transients"]["description"] = (
                            "High transient density, rhythmic content"
                        )
                    elif density > 0.5:
                        analysis["transients"]["density"] = "medium"
                        analysis["transients"]["description"] = (
                            "Moderate transient density"
                        )
                    else:
                        analysis["transients"]["density"] = "low"
                        analysis["transients"]["description"] = (
                            "Low transient density, likely sustained sounds"
                        )
            except Exception as e:
                if ctrl:
                    ctrl.log_message("Error analyzing warp markers: " + str(e))
                analysis["transients"]["error"] = str(e)
        if hasattr(clip, "sample"):
            sample = clip.sample
            try:
                if hasattr(sample, "length"):
                    analysis["audio_properties"]["sample_length"] = sample.length
                    if (
                        hasattr(sample, "sample_rate")
                        and sample.sample_rate > 0
                    ):
                        duration_seconds = (
                            sample.length / sample.sample_rate
                        )
                        analysis["audio_properties"][
                            "duration_seconds"
                        ] = duration_seconds
                        analysis["audio_properties"][
                            "sample_rate"
                        ] = sample.sample_rate
                if hasattr(sample, "bit_depth"):
                    analysis["audio_properties"]["bit_depth"] = sample.bit_depth
                if hasattr(sample, "channels"):
                    analysis["audio_properties"]["channels"] = sample.channels
                    analysis["audio_properties"]["is_stereo"] = (
                        sample.channels == 2
                    )
                if hasattr(clip, "gain"):
                    analysis["audio_properties"]["gain"] = clip.gain
            except Exception as e:
                if ctrl:
                    ctrl.log_message(
                        "Error getting sample properties: " + str(e)
                    )
        frequency_hints = []
        if hasattr(clip, "warp_mode"):
            if clip.warp_mode == 0:
                frequency_hints.append(
                    "Likely percussive/rhythmic content"
                )
                analysis["frequency_analysis"]["character"] = "percussive"
            elif clip.warp_mode == 1:
                frequency_hints.append("Likely tonal/melodic content")
                analysis["frequency_analysis"]["character"] = "tonal"
            elif clip.warp_mode == 2:
                frequency_hints.append(
                    "Likely atmospheric/textural content"
                )
                analysis["frequency_analysis"]["character"] = "textural"
            elif clip.warp_mode in (4, 5):
                frequency_hints.append(
                    "Full-bandwidth material, likely mixed/mastered"
                )
                analysis["frequency_analysis"]["character"] = "full_spectrum"
        analysis["frequency_analysis"]["hints"] = frequency_hints
        analysis["frequency_analysis"]["note"] = (
            "Direct spectral analysis not available in Ableton Python API. "
            "Analysis based on warp mode and clip properties."
        )
        waveform_desc = []
        if hasattr(clip, "gain"):
            if clip.gain > 0.9:
                waveform_desc.append("High gain - likely loud/compressed")
            elif clip.gain < 0.3:
                waveform_desc.append("Low gain - quiet/ambient")
        if hasattr(clip, "start_marker") and hasattr(clip, "end_marker"):
            start = clip.start_marker
            end = clip.end_marker
            if start > 0:
                waveform_desc.append("Has fade-in or trimmed start")
            if hasattr(clip, "sample") and hasattr(clip.sample, "length"):
                if end < clip.sample.length:
                    waveform_desc.append(
                        "Has fade-out or trimmed end"
                    )
        if hasattr(clip, "loop_start") and hasattr(clip, "loop_end"):
            loop_length = clip.loop_end - clip.loop_start
            if loop_length < 1:
                waveform_desc.append(
                    "Very short loop - likely one-shot or stab"
                )
            elif loop_length < 4:
                waveform_desc.append(
                    "Short loop - likely rhythmic element"
                )
            elif loop_length < 16:
                waveform_desc.append(
                    "Medium loop - likely phrase or section"
                )
            else:
                waveform_desc.append(
                    "Long loop - likely full section or arrangement"
                )
        analysis["waveform_description"]["characteristics"] = waveform_desc
        if hasattr(clip, "pitch_coarse"):
            analysis["pitch_info"] = {
                "pitch_coarse": clip.pitch_coarse,
                "note": "Pitch adjustment in semitones",
            }
            if hasattr(clip, "pitch_fine"):
                analysis["pitch_info"]["pitch_fine"] = clip.pitch_fine
        summary_parts = []
        if analysis["tempo_rhythm"].get("warping_enabled"):
            summary_parts.append("warped audio")
        else:
            summary_parts.append("unwarped audio")
        if analysis["transients"].get("density"):
            summary_parts.append(
                analysis["transients"]["density"] + " transient density"
            )
        if analysis["frequency_analysis"].get("character"):
            summary_parts.append(
                analysis["frequency_analysis"]["character"] + " character"
            )
        analysis["summary"] = ", ".join(summary_parts).capitalize()
        return analysis
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error analyzing audio clip: " + str(e))
            ctrl.log_message(traceback.format_exc())
        raise


def freeze_track(song, track_index, ctrl=None):
    """Freeze a track."""
    try:
        if track_index < 0 or track_index >= len(song.tracks):
            raise IndexError("Track index out of range")
        track = song.tracks[track_index]
        if not getattr(track, "can_be_frozen", False) or not track.can_be_frozen:
            raise Exception(
                "Track cannot be frozen (may be a return or master track)"
            )
        if not hasattr(track, "freeze"):
            raise Exception("Freeze not available on this track")
        track.freeze = True
        return {
            "track_index": track_index,
            "frozen": True,
            "track_name": track.name,
        }
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error freezing track: " + str(e))
        raise


def unfreeze_track(song, track_index, ctrl=None):
    """Unfreeze a track."""
    try:
        if track_index < 0 or track_index >= len(song.tracks):
            raise IndexError("Track index out of range")
        track = song.tracks[track_index]
        if not hasattr(track, "freeze"):
            raise Exception("Freeze not available on this track")
        track.freeze = False
        return {
            "track_index": track_index,
            "frozen": False,
            "track_name": track.name,
        }
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error unfreezing track: " + str(e))
        raise


def export_track_audio(
    song, track_index, output_path, start_time, end_time, ctrl=None
):
    """Export track audio to WAV file (freeze and report path)."""
    try:
        if track_index < 0 or track_index >= len(song.tracks):
            raise IndexError("Track index out of range")
        track = song.tracks[track_index]
        if not getattr(track, "can_be_frozen", False) or not track.can_be_frozen:
            raise Exception(
                "Track cannot be frozen (may be a return or master track)"
            )
        was_frozen = (
            getattr(track, "freeze", False)
            if hasattr(track, "freeze")
            else False
        )
        if not was_frozen:
            track.freeze = True
        result = {
            "track_index": track_index,
            "output_path": output_path,
            "message": (
                "Track frozen. Frozen audio file should be in: "
                "Project/Samples/Frozen/ folder. "
                "Copy it manually to: "
                + str(output_path)
                + ". "
                "For fully automatic export, use Ableton's built-in "
                "Export Audio/Video feature."
            ),
        }
        if not was_frozen and hasattr(track, "freeze"):
            track.freeze = False
        return result
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error exporting track audio: " + str(e))
            ctrl.log_message(traceback.format_exc())
        raise
