"""Dynamic command dispatch — hot-reloadable without restarting Ableton.

Add new commands here instead of editing __init__.py.
Toggle control surface off/on to pick up changes.
"""

from __future__ import absolute_import, print_function, unicode_literals

from . import tracks, browser, devices, arrangement, audio


def _resolve_track(song, track_index, track_type):
    """Resolve a track object from index and type."""
    if track_type == "return":
        if track_index < 0 or track_index >= len(song.return_tracks):
            raise IndexError("Return track index out of range")
        return song.return_tracks[track_index]
    elif track_type == "master":
        return song.master_track
    else:
        if track_index < 0 or track_index >= len(song.tracks):
            raise IndexError("Track index out of range")
        return song.tracks[track_index]


def _get_track_routing(song, p, ctrl):
    """Get output routing info for a track."""
    track_index = p.get("track_index", 0)
    track_type = p.get("track_type", "track")
    track = _resolve_track(song, track_index, track_type)

    current_type = None
    current_channel = None
    try:
        rt = track.output_routing_type
        current_type = rt.display_name if rt else None
    except Exception:
        pass
    try:
        rc = track.output_routing_channel
        current_channel = rc.display_name if rc else None
    except Exception:
        pass

    available_types = []
    try:
        for rt in track.available_output_routing_types:
            available_types.append(rt.display_name)
    except Exception:
        pass

    available_channels = []
    try:
        for rc in track.available_output_routing_channels:
            available_channels.append(rc.display_name)
    except Exception:
        pass

    return {
        "index": track_index,
        "name": track.name,
        "track_type": track_type,
        "output_routing_type": current_type,
        "output_routing_channel": current_channel,
        "available_output_routing_types": available_types,
        "available_output_routing_channels": available_channels,
    }


def _set_track_routing(song, p, ctrl):
    """Set output routing for a track by display name."""
    track_index = p.get("track_index", 0)
    track_type = p.get("track_type", "track")
    output_type = p.get("output_type", None)
    output_channel = p.get("output_channel", None)
    track = _resolve_track(song, track_index, track_type)

    result = {"index": track_index, "name": track.name, "track_type": track_type}

    if output_type is not None:
        found = False
        for rt in track.available_output_routing_types:
            if rt.display_name == output_type:
                track.output_routing_type = rt
                result["output_routing_type"] = rt.display_name
                found = True
                break
        if not found:
            available = [rt.display_name for rt in track.available_output_routing_types]
            raise ValueError(
                "Output type '{0}' not found. Available: {1}".format(
                    output_type, ", ".join(available)
                )
            )

    if output_channel is not None:
        found = False
        for rc in track.available_output_routing_channels:
            if rc.display_name == output_channel:
                track.output_routing_channel = rc
                result["output_routing_channel"] = rc.display_name
                found = True
                break
        if not found:
            available = [rc.display_name for rc in track.available_output_routing_channels]
            raise ValueError(
                "Output channel '{0}' not found. Available: {1}".format(
                    output_channel, ", ".join(available)
                )
            )

    return result


def _move_device(song, p, ctrl):
    """Move a device to a new position on a track."""
    track_index = p.get("track_index", 0)
    device_index = p.get("device_index", 0)
    new_position = p.get("new_position", 0)
    track_type = p.get("track_type", "track")
    track = devices.resolve_track(song, track_index, track_type)
    device_list = list(track.devices)
    if device_index < 0 or device_index >= len(device_list):
        raise IndexError("Device index out of range")
    if new_position < 0 or new_position >= len(device_list):
        raise IndexError("New position out of range")
    device = device_list[device_index]
    name = device.name
    track.move_device(device, new_position)
    return {
        "moved": name,
        "from": device_index,
        "to": new_position,
        "track_type": track_type,
    }


def _get_project_overview(song, p, ctrl):
    """Single-call project overview: session, tracks, groups, arrangement clips."""
    try:
        # 1. Session info
        session = {
            "tempo": song.tempo,
            "time_signature": "{0}/{1}".format(
                song.signature_numerator, song.signature_denominator
            ),
            "track_count": len(song.tracks),
            "return_track_count": len(song.return_tracks),
        }

        # 2. All tracks — compact summary with arrangement clip info
        track_list = []
        for i, track in enumerate(song.tracks):
            # Basic track info
            info = {
                "index": i,
                "name": track.name,
                "type": "audio" if track.has_audio_input else "midi",
                "mute": track.mute,
                "volume": round(track.mixer_device.volume.value, 4),
                "pan": round(track.mixer_device.panning.value, 2),
            }

            # Group membership
            try:
                info["is_group"] = track.is_foldable
            except Exception:
                info["is_group"] = False
            try:
                if track.is_grouped and track.group_track:
                    info["group"] = track.group_track.name
            except Exception:
                pass

            # Devices — names only
            info["devices"] = [d.name for d in track.devices]

            # Session clips — just count and names
            session_clips = []
            for slot in track.clip_slots:
                if slot.has_clip:
                    session_clips.append(slot.clip.name)
            if session_clips:
                info["session_clips"] = session_clips

            # Arrangement clips — compact summary
            arr_clips = []
            try:
                if hasattr(track, "arrangement_clips"):
                    for clip in track.arrangement_clips:
                        arr_clips.append({
                            "name": clip.name,
                            "start": clip.start_time,
                            "end": clip.end_time,
                            "muted": getattr(clip, "muted", False),
                            "is_audio": clip.is_audio_clip,
                        })
            except Exception:
                pass
            if arr_clips:
                info["arrangement_clips"] = arr_clips

            track_list.append(info)

        # 3. Return tracks
        returns = []
        for i, rt in enumerate(song.return_tracks):
            returns.append({
                "index": i,
                "name": rt.name,
                "devices": [d.name for d in rt.devices],
            })

        # 4. Master
        master = {
            "volume": round(song.master_track.mixer_device.volume.value, 4),
            "devices": [d.name for d in song.master_track.devices],
        }

        return {
            "session": session,
            "tracks": track_list,
            "return_tracks": returns,
            "master": master,
        }
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error in get_project_overview: " + str(e))
        raise



def _record_arrangement(song, p, ctrl):
    """Record session scenes to arrangement with live automation.

    Fires scenes at the right times based on the plan, recording
    everything to arrangement view. Also applies parameter automation
    in real-time during recording so it gets captured as arrangement
    automation.

    Params:
        plan: list of sections (same format as build_arrangement)
        automation: list of automation lanes:
            {"track_index": int, "parameter_name": str,
             "points": [{"time": float (beats), "value": float (0-1)}, ...]}
        stop_after: bool (default True) - stop recording after last section
    """
    from . import automation as _auto

    plan = p.get("plan", [])
    auto_lanes = p.get("automation", [])
    stop_after = p.get("stop_after", True)

    if not plan:
        return {"error": "no plan provided"}

    # Build scene fire times (in beats)
    scene_times = []
    total_beats = 0
    for i, s in enumerate(plan):
        beat = (s["bar"] - 1) * 4
        scene_times.append({"scene": i, "beat": beat, "name": s["name"]})
        end = beat + s["bars"] * 4
        if end > total_beats:
            total_beats = end

    # Resolve automation parameters and sort points by time
    auto_resolved = []
    for lane in auto_lanes:
        try:
            tidx = lane["track_index"]
            track = song.tracks[tidx]
            param = _auto._find_parameter(track, lane["parameter_name"])
            if param is None:
                if ctrl:
                    ctrl.log_message("record: param not found: {0} on track {1}".format(
                        lane["parameter_name"], tidx))
                continue
            pts = sorted(lane["points"], key=lambda x: float(x["time"]))
            auto_resolved.append({"param": param, "points": pts, "next": [0],
                                  "name": lane["parameter_name"], "track": tidx})
        except Exception as e:
            if ctrl:
                ctrl.log_message("record: auto resolve error: {0}".format(e))

    next_scene = [1]  # index into scene_times; scene 0 fires immediately

    def poll_and_fire():
        idx = next_scene[0]
        now = song.current_song_time

        # Check if we're past the end
        if now >= total_beats:
            if stop_after:
                song.record_mode = False
                song.stop_playing()
            if ctrl:
                ctrl.log_message("record_arrangement: done at {0}".format(now))
            return

        # Fire next scene 2 beats early — global quantization (1 bar)
        # will snap the actual launch to the correct bar line.
        if idx < len(scene_times):
            target = scene_times[idx]["beat"]
            if now >= target - 2.0:
                song.scenes[scene_times[idx]["scene"]].fire()
                if ctrl:
                    ctrl.log_message("record: fired {0} at {1}".format(
                        scene_times[idx]["name"], now))
                next_scene[0] += 1

        # Apply automation — set parameter values for any points we've passed
        for lane in auto_resolved:
            ni = lane["next"][0]
            pts = lane["points"]
            while ni < len(pts) and now >= float(pts[ni]["time"]):
                val = max(0.0, min(1.0, float(pts[ni]["value"])))
                try:
                    lane["param"].value = val
                except Exception:
                    pass
                ni += 1
                lane["next"][0] = ni

            # Interpolate between points for smooth automation
            if ni > 0 and ni < len(pts):
                prev = pts[ni - 1]
                nxt = pts[ni]
                t0 = float(prev["time"])
                t1 = float(nxt["time"])
                v0 = float(prev["value"])
                v1 = float(nxt["value"])
                if t1 > t0:
                    frac = (now - t0) / (t1 - t0)
                    frac = max(0.0, min(1.0, frac))
                    interp = v0 + (v1 - v0) * frac
                    try:
                        lane["param"].value = max(0.0, min(1.0, interp))
                    except Exception:
                        pass

        # Poll again (~100ms per tick)
        ctrl.schedule_message(1, poll_and_fire)

    # Setup: position at start, quantize to 1 bar, enable record, fire scene 0
    song.stop_playing()
    song.current_song_time = 0.0
    song.clip_trigger_quantization = 4  # 4 = 1 Bar

    # Set initial automation values before recording starts
    for lane in auto_resolved:
        if lane["points"]:
            val = max(0.0, min(1.0, float(lane["points"][0]["value"])))
            try:
                lane["param"].value = val
            except Exception:
                pass

    song.record_mode = True
    song.scenes[0].fire()
    if ctrl:
        ctrl.log_message("record: started, {0} scenes, {1} auto lanes".format(
            len(scene_times), len(auto_resolved)))

    # Start polling for subsequent scenes
    ctrl.schedule_message(1, poll_and_fire)

    return {
        "status": "recording_started",
        "total_scenes": len(scene_times),
        "total_beats": total_beats,
        "total_bars": total_beats / 4,
        "duration_seconds": total_beats * 60.0 / song.tempo,
        "automation_lanes": len(auto_resolved),
    }


def _manage_locators(song, p, ctrl):
    """List, delete, or replace all locators/cue_points.

    Actions:
        list: return all locators
        delete_all: remove all locators
        replace_all: delete all, then create from 'locators' list
            locators: [{"position": float, "name": str}, ...]
    """
    action = p.get("action", "list")
    cue_points = list(song.cue_points)

    if action == "list":
        return [{"name": cp.name, "time": cp.time} for cp in cue_points]

    original_time = song.current_song_time

    if action in ("delete_all", "replace_all"):
        # Delete all existing
        times = [cp.time for cp in cue_points]
        for t in times:
            song.current_song_time = t
            song.set_or_delete_cue()
        deleted = len(times)

        if action == "delete_all":
            song.current_song_time = original_time
            return {"deleted": deleted}

        # Create new locators
        locators = p.get("locators", [])
        created = []
        for loc in locators:
            pos = float(loc["position"])
            name = str(loc.get("name", ""))
            song.current_song_time = pos
            song.set_or_delete_cue()
            # Find the cue we just created and name it
            best_cue = None
            best_dist = 999999.0
            for cp in song.cue_points:
                dist = abs(cp.time - pos)
                if dist < best_dist:
                    best_dist = dist
                    best_cue = cp
            if best_cue and name:
                best_cue.name = name
                created.append({"name": name, "position": best_cue.time})
            elif best_cue:
                created.append({"name": best_cue.name, "position": best_cue.time})

        song.current_song_time = original_time
        return {"deleted": deleted, "created": created}

    return {"error": "unknown action"}


def _build_arrangement(song, p, ctrl):
    """Build arrangement as session scenes.

    Creates session clips from arrangement sources and duplicates them
    into scene slots matching the section plan. Clips are auto-named
    to match their track name. User then launches scenes to record.

    Params:
        plan: list of sections:
            {"name": str, "bar": int (1-indexed), "bars": int,
             "tracks": [int, ...] (track indices that should be ACTIVE)}
        source_bars: int (current loop length, auto-detected if omitted)
    """
    plan = p.get("plan", [])
    source_bars = p.get("source_bars", None)

    # Auto-detect source_bars from arrangement clips if not provided
    if source_bars is None:
        max_end = 0
        for track in song.tracks:
            try:
                for clip in track.arrangement_clips:
                    if clip.end_time > max_end:
                        max_end = clip.end_time
            except Exception:
                continue
        source_bars = max(int(max_end / 4), 16)
        if ctrl:
            ctrl.log_message("build_arrangement: auto-detected {0} source bars".format(
                source_bars))

    source_beats = source_bars * 4

    if ctrl:
        ctrl.log_message("build_arrangement: {0} sections".format(len(plan)))

    # Collect source clips per track from arrangement
    track_data = {}
    for i, track in enumerate(song.tracks):
        try:
            arr_clips = track.arrangement_clips
            if not arr_clips:
                continue
            source = [c for c in arr_clips if c.start_time < source_beats]
            if source:
                track_data[i] = source
        except Exception:
            continue

    # Ensure enough scenes exist
    while len(song.scenes) < len(plan):
        song.create_scene(-1)

    # Name scenes
    for si, section in enumerate(plan):
        try:
            song.scenes[si].name = section["name"]
        except Exception:
            pass

    # Build track sets per section
    section_tracks = []
    for s in plan:
        section_tracks.append(set(s.get("tracks", [])))

    # For each track, create source clip in slot 0 then dup to active scenes
    clips_created = 0
    skipped = []
    errors = []

    for tidx, source_clips in track_data.items():
        track = song.tracks[tidx]
        first = source_clips[0]
        slot0 = track.clip_slots[0]

        # Create session clip from first arrangement source
        try:
            if slot0.has_clip:
                slot0.delete_clip()

            if first.is_audio_clip:
                fp = first.file_path
                if not fp:
                    skipped.append({"index": tidx, "name": track.name,
                                    "reason": "no_file_path"})
                    continue
                slot0.create_audio_clip(fp)
                if not slot0.has_clip:
                    skipped.append({"index": tidx, "name": track.name,
                                    "reason": "audio_create_failed"})
                    continue
                sc = slot0.clip
                sc.looping = first.looping
                sc.loop_start = first.loop_start
                sc.loop_end = first.loop_end
                sc.warping = first.warping
                try:
                    sc.warp_mode = first.warp_mode
                except Exception:
                    pass

            elif first.is_midi_clip:
                loop_len = first.loop_end - first.loop_start
                if loop_len <= 0:
                    loop_len = first.length
                slot0.create_clip(loop_len)
                if not slot0.has_clip:
                    skipped.append({"index": tidx, "name": track.name,
                                    "reason": "midi_create_failed"})
                    continue
                sc = slot0.clip
                try:
                    notes = list(first.get_all_notes_extended())
                    if notes:
                        live_notes = tuple(
                            (int(n.pitch),
                             float(n.start_time),
                             float(n.duration),
                             int(round(n.velocity)),
                             bool(n.mute))
                            for n in notes
                        )
                        sc.set_notes(live_notes)
                except Exception as e:
                    if ctrl:
                        ctrl.log_message(
                            "  MIDI note copy fail {0}: {1}".format(tidx, e))
                    errors.append("MIDI {0}: {1}".format(tidx, str(e)))
                sc.looping = True
                sc.loop_start = first.loop_start
                sc.loop_end = first.loop_end
            else:
                continue
        except Exception as e:
            errors.append("Track {0} setup: {1}".format(tidx, str(e)))
            continue

        if not slot0.has_clip:
            continue

        # Name the source clip to match track name
        try:
            slot0.clip.name = track.name
        except Exception:
            pass

        # Duplicate to each active scene slot
        for si, st in enumerate(section_tracks):
            if tidx not in st:
                continue
            if si == 0:
                # Slot 0 already has the clip
                clips_created += 1
                continue
            target_slot = track.clip_slots[si]
            try:
                if target_slot.has_clip:
                    target_slot.delete_clip()
                slot0.duplicate_clip_to(target_slot)
                # Name duplicated clip to match track
                try:
                    target_slot.clip.name = track.name
                except Exception:
                    pass
                clips_created += 1
            except Exception as e:
                errors.append("Dup {0}->scene{1}: {2}".format(tidx, si, e))

        # If track NOT active in scene 0, remove clip from slot 0
        if tidx not in section_tracks[0]:
            try:
                slot0.delete_clip()
            except Exception:
                pass

        if ctrl:
            ctrl.log_message("  [{0}] {1}: done".format(tidx, track.name))

    if ctrl:
        ctrl.log_message("build done: {0} clips".format(clips_created))

    # Scene summary
    scene_summary = []
    for si, section in enumerate(plan):
        scene_summary.append({
            "scene": si,
            "name": section["name"],
            "bars": section["bars"],
            "track_count": len(section.get("tracks", [])),
        })

    return {
        "scenes_created": len(plan),
        "tracks_processed": len(track_data) - len(skipped),
        "clips_placed": clips_created,
        "source_bars": source_bars,
        "scenes": scene_summary,
        "skipped": skipped,
        "errors": errors[:20],
    }


def _fill_session_gaps(song, p, ctrl):
    """Fill empty session clip slots where the plan expects clips.

    For each section/track in the plan, if the session slot is empty but the
    track has a clip in another slot, duplicate it there.

    Params:
        plan: list of sections (same format as build/record)
    """
    plan = p.get("plan", [])
    if not plan:
        return {"error": "no plan provided"}

    filled = 0
    errors = []
    for i, section in enumerate(plan):
        for ti in section.get("tracks", []):
            try:
                track = song.tracks[ti]
                if i >= len(track.clip_slots):
                    continue
                slot = track.clip_slots[i]
                if slot.has_clip:
                    continue  # already has a clip
                # Find a source clip on this track
                source = None
                for s in track.clip_slots:
                    if s.has_clip:
                        source = s
                        break
                if source is None:
                    continue  # no clips at all on this track
                source.duplicate_clip_to(slot)
                filled += 1
            except Exception as e:
                errors.append("[{0}] scene {1}: {2}".format(ti, i, e))

    return {"filled": filled, "errors": errors}


def _place_clips(song, p, ctrl):
    """Place session clips into arrangement without recording.

    For each section in the plan, copies each track's session clip to the
    correct arrangement position. Does NOT use recording mode, so any
    existing arrangement content on non-plan tracks is untouched.

    Params:
        plan: list of sections (same format as build/record)
    """
    plan = p.get("plan", [])
    if not plan:
        return {"error": "no plan provided"}

    placed = 0
    errors = []
    for i, section in enumerate(plan):
        beat = (section["bar"] - 1) * 4
        for ti in section.get("tracks", []):
            try:
                track = song.tracks[ti]
                slot = track.clip_slots[i]
                if not slot.has_clip:
                    continue
                result = arrangement.copy_clip_to_arrangement(
                    song, ti, i, float(beat), ctrl)
                if result and result.get("copied"):
                    placed += 1
                else:
                    errors.append("[{0}] scene {1}: copy returned not-copied".format(ti, i))
            except Exception as e:
                errors.append("[{0}] scene {1}: {2}".format(ti, i, e))

    return {
        "clips_placed": placed,
        "errors": errors,
    }


def _record_automation(song, p, ctrl):
    """Record automation only — plays arrangement, no scene firing.

    Plays the existing arrangement in record mode while setting parameter
    values in real-time. Since no scenes are fired, existing arrangement
    clips (including FX, one-shots, etc.) are NOT overwritten.

    All tracks are disarmed before recording to prevent any audio/MIDI
    input from overwriting clips.

    Params:
        plan: list of sections (used only to calculate total length)
        automation: list of automation lanes (same format as record_arrangement)
        stop_after: bool (default True)
    """
    from . import automation as _auto

    plan = p.get("plan", [])
    auto_lanes = p.get("automation", [])
    stop_after = p.get("stop_after", True)

    if not auto_lanes:
        return {"error": "no automation lanes provided"}

    # Calculate total beats from plan
    total_beats = 0
    for s in plan:
        end = (s["bar"] - 1) * 4 + s["bars"] * 4
        if end > total_beats:
            total_beats = end

    if total_beats == 0:
        total_beats = max(float(pt["time"]) for lane in auto_lanes for pt in lane["points"]) + 16

    # Resolve automation parameters
    auto_resolved = []
    for lane in auto_lanes:
        try:
            tidx = lane["track_index"]
            track = song.tracks[tidx]
            param = _auto._find_parameter(track, lane["parameter_name"])
            if param is None:
                if ctrl:
                    ctrl.log_message("auto: param not found: {0} on track {1}".format(
                        lane["parameter_name"], tidx))
                continue
            pts = sorted(lane["points"], key=lambda x: float(x["time"]))
            auto_resolved.append({"param": param, "points": pts, "next": [0],
                                  "name": lane["parameter_name"], "track": tidx})
        except Exception as e:
            if ctrl:
                ctrl.log_message("auto: resolve error: {0}".format(e))

    def poll_automation():
        now = song.current_song_time

        if now >= total_beats:
            if stop_after:
                song.record_mode = False
                song.stop_playing()
            if ctrl:
                ctrl.log_message("record_automation: done at {0}".format(now))
            return

        # Apply automation with interpolation
        for lane in auto_resolved:
            ni = lane["next"][0]
            pts = lane["points"]
            while ni < len(pts) and now >= float(pts[ni]["time"]):
                val = max(0.0, min(1.0, float(pts[ni]["value"])))
                try:
                    lane["param"].value = val
                except Exception:
                    pass
                ni += 1
                lane["next"][0] = ni

            if ni > 0 and ni < len(pts):
                prev = pts[ni - 1]
                nxt = pts[ni]
                t0 = float(prev["time"])
                t1 = float(nxt["time"])
                v0 = float(prev["value"])
                v1 = float(nxt["value"])
                if t1 > t0:
                    frac = (now - t0) / (t1 - t0)
                    frac = max(0.0, min(1.0, frac))
                    interp = v0 + (v1 - v0) * frac
                    try:
                        lane["param"].value = max(0.0, min(1.0, interp))
                    except Exception:
                        pass

        ctrl.schedule_message(1, poll_automation)

    # Disarm ALL tracks so recording doesn't capture audio/MIDI input
    for track in song.tracks:
        try:
            if track.can_be_armed and track.arm:
                track.arm = False
        except Exception:
            pass

    # Setup
    song.stop_playing()
    song.current_song_time = 0.0

    # Set initial values
    for lane in auto_resolved:
        if lane["points"]:
            val = max(0.0, min(1.0, float(lane["points"][0]["value"])))
            try:
                lane["param"].value = val
            except Exception:
                pass

    # Start arrangement playback in record mode (no scene firing!)
    song.record_mode = True
    song.start_playing()

    if ctrl:
        ctrl.log_message("record_automation: started, {0} lanes, {1} beats".format(
            len(auto_resolved), total_beats))

    ctrl.schedule_message(1, poll_automation)

    return {
        "status": "recording_automation",
        "total_beats": total_beats,
        "total_bars": total_beats / 4,
        "duration_seconds": total_beats * 60.0 / song.tempo,
        "automation_lanes": len(auto_resolved),
    }


# Registry of dynamically dispatched commands.
# Key: command name, Value: (handler_func, param_extractor, needs_main_thread)
def _get_registry():
    """Build registry fresh each call so hot-reload picks up changes."""
    return {
        "set_return_track_name": {
            "handler": lambda song, p, ctrl: tracks.set_return_track_name(
                song, p.get("return_index", 0), p.get("name", ""), ctrl
            ),
            "modifying": True,
        },
        "load_on_return_track": {
            "handler": lambda song, p, ctrl: browser.load_on_return_track(
                song, p.get("return_index", 0), p.get("uri", ""), ctrl
            ),
            "modifying": True,
        },
        "move_device": {
            "handler": lambda song, p, ctrl: _move_device(song, p, ctrl),
            "modifying": True,
        },
        "get_track_meters": {
            "handler": lambda song, p, ctrl: tracks.get_track_meters(
                song,
                p.get("track_indices", None),
                p.get("include_returns", False),
                p.get("include_master", False),
                ctrl,
            ),
            "modifying": False,
        },
        "inspect_arrangement_clip": {
            "handler": lambda song, p, ctrl: arrangement.inspect_arrangement_clip(
                song,
                p.get("track_index", 0),
                p.get("arrangement_clip_index", 0),
                ctrl,
            ),
            "modifying": False,
        },
        "get_all_clip_gains": {
            "handler": lambda song, p, ctrl: audio.get_all_clip_gains(
                song, p.get("track_indices", None), ctrl
            ),
            "modifying": False,
        },
        "set_clip_gain": {
            "handler": lambda song, p, ctrl: audio.set_clip_gain(
                song,
                p.get("track_index", 0),
                p.get("clip_index", 0),
                p.get("gain", 0.5),
                ctrl,
            ),
            "modifying": True,
        },
        "set_clip_source_bpm": {
            "handler": lambda song, p, ctrl: audio.set_clip_source_bpm(
                song,
                p.get("track_index", 0),
                p.get("clip_index", 0),
                p.get("source_bpm", 120.0),
                p.get("duration_seconds", 0.0),
                ctrl,
            ),
            "modifying": True,
        },
        "copy_arrangement_to_session": {
            "handler": lambda song, p, ctrl: arrangement.copy_arrangement_to_session(
                song,
                p.get("track_index", 0),
                p.get("arrangement_clip_index", 0),
                p.get("clip_slot_index", 0),
                ctrl,
            ),
            "modifying": True,
        },
        "get_group_structure": {
            "handler": lambda song, p, ctrl: tracks.get_group_structure(song, ctrl),
            "modifying": False,
        },
        "relocate_track": {
            "handler": lambda song, p, ctrl: tracks.relocate_track(
                song,
                p.get("source_index", 0),
                p.get("target_index", 0),
                p.get("device_uris", None),
                ctrl,
            ),
            "modifying": True,
        },
        "move_to_group": {
            "handler": lambda song, p, ctrl: tracks.move_to_group(
                song,
                p.get("track_name", None),
                p.get("track_index", None),
                p.get("group_name", ""),
                p.get("position", "last"),
                p.get("device_uris", None),
                ctrl,
            ),
            "modifying": True,
        },
        "get_track_routing": {
            "handler": lambda song, p, ctrl: _get_track_routing(song, p, ctrl),
            "modifying": False,
        },
        "set_track_routing": {
            "handler": lambda song, p, ctrl: _set_track_routing(song, p, ctrl),
            "modifying": True,
        },
        "get_project_overview": {
            "handler": lambda song, p, ctrl: _get_project_overview(song, p, ctrl),
            "modifying": False,
        },
        "build_arrangement": {
            "handler": lambda song, p, ctrl: _build_arrangement(song, p, ctrl),
            "modifying": True,
        },
        "manage_locators": {
            "handler": lambda song, p, ctrl: _manage_locators(song, p, ctrl),
            "modifying": True,
        },
        "record_arrangement": {
            "handler": lambda song, p, ctrl: _record_arrangement(song, p, ctrl),
            "modifying": True,
        },
        "place_clips": {
            "handler": lambda song, p, ctrl: _place_clips(song, p, ctrl),
            "modifying": True,
        },
        "fill_session_gaps": {
            "handler": lambda song, p, ctrl: _fill_session_gaps(song, p, ctrl),
            "modifying": True,
        },
        "record_automation": {
            "handler": lambda song, p, ctrl: _record_automation(song, p, ctrl),
            "modifying": True,
        },
    }


def is_known(command_type):
    """Check if this command is in the dynamic registry."""
    return command_type in _get_registry()


def is_modifying(command_type):
    """Check if this command modifies state (needs main thread)."""
    reg = _get_registry()
    if command_type in reg:
        return reg[command_type].get("modifying", False)
    return False


def execute(command_type, params, song, ctrl):
    """Execute a dynamically registered command."""
    reg = _get_registry()
    if command_type not in reg:
        raise ValueError("Unknown dynamic command: " + command_type)
    return reg[command_type]["handler"](song, params, ctrl)
