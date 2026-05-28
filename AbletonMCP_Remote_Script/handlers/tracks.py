"""Track creation, deletion, properties, colors, arm."""

from __future__ import absolute_import, print_function, unicode_literals


def get_track_info(song, track_index, ctrl=None):
    """Get information about a track."""
    try:
        if track_index < 0 or track_index >= len(song.tracks):
            raise IndexError("Track index out of range")
        track = song.tracks[track_index]
        clip_slots = []
        for slot_index, slot in enumerate(track.clip_slots):
            clip_info = None
            if slot.has_clip:
                clip = slot.clip
                clip_info = {
                    "name": clip.name,
                    "length": clip.length,
                    "is_playing": clip.is_playing,
                    "is_recording": clip.is_recording,
                }
            clip_slots.append({
                "index": slot_index,
                "has_clip": slot.has_clip,
                "clip": clip_info,
            })
        from . import devices as dev_mod
        devices_list = []
        for device_index, device in enumerate(track.devices):
            dev_info = {
                "index": device_index,
                "name": device.name,
                "class_name": device.class_name,
                "type": dev_mod.get_device_type(device, ctrl),
            }
            if getattr(device, "can_have_chains", False):
                chains = []
                for chain_index, chain in enumerate(device.chains):
                    chains.append({
                        "index": chain_index,
                        "name": chain.name,
                        "device_count": len(chain.devices),
                    })
                dev_info["chains"] = chains
            devices_list.append(dev_info)
        result = {
            "index": track_index,
            "name": track.name,
            "is_audio_track": track.has_audio_input,
            "is_midi_track": track.has_midi_input,
            "mute": track.mute,
            "solo": track.solo,
            "arm": False,
            "volume": track.mixer_device.volume.value,
            "panning": track.mixer_device.panning.value,
            "clip_slots": clip_slots,
            "devices": devices_list,
        }
        try:
            result["arm"] = track.arm
        except Exception:
            pass
        return result
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error getting track info: " + str(e))
        raise


def create_midi_track(song, index, ctrl=None):
    """Create a new MIDI track at the specified index."""
    try:
        song.create_midi_track(index)
        new_track_index = len(song.tracks) - 1 if index == -1 else index
        new_track = song.tracks[new_track_index]
        return {"index": new_track_index, "name": new_track.name}
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error creating MIDI track: " + str(e))
        raise


def create_audio_track(song, index, ctrl=None):
    """Create a new audio track."""
    try:
        if index < 0:
            index = len(song.tracks)
        song.create_audio_track(index)
        new_track = song.tracks[index]
        return {"index": index, "name": new_track.name}
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error creating audio track: " + str(e))
        raise


def create_return_track(song, ctrl=None):
    """Create a new return track."""
    try:
        song.create_return_track()
        new_index = len(song.return_tracks) - 1
        new_track = song.return_tracks[new_index]
        return {"index": new_index, "name": new_track.name}
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error creating return track: " + str(e))
        raise


def set_track_name(song, track_index, name, ctrl=None):
    """Set the name of a track."""
    try:
        if track_index < 0 or track_index >= len(song.tracks):
            raise IndexError("Track index out of range")
        track = song.tracks[track_index]
        track.name = name
        return {"name": track.name}
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error setting track name: " + str(e))
        raise


def delete_track(song, track_index, ctrl=None):
    """Delete a track at the specified index."""
    try:
        if track_index < 0 or track_index >= len(song.tracks):
            raise IndexError("Track index out of range")
        song.delete_track(track_index)
        return {"deleted": True, "track_index": track_index}
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error deleting track: " + str(e))
        raise


def duplicate_track(song, track_index, ctrl=None):
    """Duplicate a track at the specified index."""
    try:
        if track_index < 0 or track_index >= len(song.tracks):
            raise IndexError("Track index out of range")
        song.duplicate_track(track_index)
        new_index = track_index + 1
        new_track = song.tracks[new_index]
        return {"index": new_index, "name": new_track.name}
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error duplicating track: " + str(e))
        raise


def set_track_color(song, track_index, color_index, ctrl=None):
    """Set track color."""
    try:
        if track_index < 0 or track_index >= len(song.tracks):
            raise IndexError("Track index out of range")
        track = song.tracks[track_index]
        track.color_index = color_index
        return {"track_index": track_index, "color_index": track.color_index}
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error setting track color: " + str(e))
        raise


def arm_track(song, track_index, ctrl=None):
    """Arm a track for recording."""
    try:
        if track_index < 0 or track_index >= len(song.tracks):
            raise IndexError("Track index out of range")
        track = song.tracks[track_index]
        if not track.can_be_armed:
            raise Exception(
                "Track cannot be armed (may be an audio track without audio input)"
            )
        track.arm = True
        return {
            "track_index": track_index,
            "track_name": track.name,
            "armed": track.arm,
        }
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error arming track: " + str(e))
        raise


def disarm_track(song, track_index, ctrl=None):
    """Disarm a track from recording."""
    try:
        if track_index < 0 or track_index >= len(song.tracks):
            raise IndexError("Track index out of range")
        track = song.tracks[track_index]
        track.arm = False
        return {
            "track_index": track_index,
            "track_name": track.name,
            "armed": track.arm,
        }
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error disarming track: " + str(e))
        raise


def set_track_arm(song, track_index, arm, ctrl=None):
    """Set the arm state of a track."""
    try:
        if track_index < 0 or track_index >= len(song.tracks):
            raise IndexError("Track index out of range")
        track = song.tracks[track_index]
        track.arm = bool(arm)
        return {"arm": track.arm}
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error setting track arm: " + str(e))
        raise


def group_tracks(song, track_indices, name, ctrl=None):
    """Group tracks (simplified; selects first track)."""
    try:
        if not track_indices or len(track_indices) == 0:
            raise ValueError("No tracks specified")
        for i in track_indices:
            if i < 0 or i >= len(song.tracks):
                raise IndexError("Track index {0} out of range".format(i))
        song.view.selected_track = song.tracks[track_indices[0]]
        return {
            "grouped": True,
            "track_count": len(track_indices),
            "name": name,
        }
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error grouping tracks: " + str(e))
        raise


def get_all_tracks_info(song, ctrl=None):
    """Get summary info for all tracks at once."""
    try:
        tracks_list = []
        for i, track in enumerate(song.tracks):
            devices_list = []
            for d in track.devices:
                devices_list.append({"name": d.name, "class_name": d.class_name})
            track_info = {
                "index": i,
                "name": track.name,
                "is_audio": track.has_audio_input,
                "is_midi": track.has_midi_input,
                "mute": track.mute,
                "solo": track.solo,
                "volume": track.mixer_device.volume.value,
                "panning": track.mixer_device.panning.value,
                "color_index": track.color_index,
                "devices": devices_list,
            }
            try:
                track_info["arm"] = track.arm
            except Exception:
                track_info["arm"] = False
            tracks_list.append(track_info)
        return {"tracks": tracks_list, "count": len(tracks_list)}
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error getting all tracks info: " + str(e))
        raise


def set_return_track_name(song, return_index, name, ctrl=None):
    """Set the name of a return track."""
    try:
        if return_index < 0 or return_index >= len(song.return_tracks):
            raise IndexError("Return track index out of range")
        track = song.return_tracks[return_index]
        track.name = name
        return {"index": return_index, "name": track.name}
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error setting return track name: " + str(e))
        raise


def _get_volume_db(track):
    """Get the fader dB string from Ableton's own conversion."""
    try:
        vol_param = track.mixer_device.volume
        # Try str_for_value if available (returns e.g. "-6.0 dB")
        try:
            return vol_param.str_for_value(vol_param.value)
        except Exception:
            pass
        # Fallback: try __str__
        try:
            s = str(vol_param)
            if "dB" in s or "-" in s:
                return s
        except Exception:
            pass
    except Exception:
        pass
    return None


def get_track_meters(song, track_indices=None, include_returns=False, include_master=False, ctrl=None):
    """Read output meters and fader values for tracks.

    Returns pre-fader meter levels (0.0-1.0) plus fader value and dB string
    so the caller can compute post-fader levels.
    """
    try:
        results = []
        if track_indices is None:
            track_indices = list(range(len(song.tracks)))
        for i in track_indices:
            if i < 0 or i >= len(song.tracks):
                continue
            track = song.tracks[i]
            vol = track.mixer_device.volume
            results.append({
                "index": i,
                "name": track.name,
                "type": "track",
                "left": track.output_meter_left,
                "right": track.output_meter_right,
                "volume": vol.value,
                "volume_min": vol.min,
                "volume_max": vol.max,
                "volume_db": _get_volume_db(track),
                "mute": track.mute,
            })
        if include_returns:
            for i, track in enumerate(song.return_tracks):
                vol = track.mixer_device.volume
                results.append({
                    "index": i,
                    "name": track.name,
                    "type": "return",
                    "left": track.output_meter_left,
                    "right": track.output_meter_right,
                    "volume": vol.value,
                    "volume_min": vol.min,
                    "volume_max": vol.max,
                    "volume_db": _get_volume_db(track),
                    "mute": track.mute,
                })
        if include_master:
            master = song.master_track
            vol = master.mixer_device.volume
            results.append({
                "index": 0,
                "name": "Master",
                "type": "master",
                "left": master.output_meter_left,
                "right": master.output_meter_right,
                "volume": vol.value,
                "volume_min": vol.min,
                "volume_max": vol.max,
                "volume_db": _get_volume_db(master),
            })
        return {"meters": results, "count": len(results)}
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error getting track meters: " + str(e))
        raise


def get_group_structure(song, ctrl=None):
    """Get group/folder structure for all tracks.

    Returns is_foldable, is_grouped, group_track info so callers can
    understand the nesting hierarchy.
    """
    try:
        results = []
        for i, track in enumerate(song.tracks):
            info = {
                "index": i,
                "name": track.name,
                "is_foldable": False,
                "is_grouped": False,
                "group_track_index": None,
                "group_track_name": None,
            }
            try:
                info["is_foldable"] = track.is_foldable
            except Exception:
                pass
            try:
                info["is_grouped"] = track.is_grouped
            except Exception:
                pass
            try:
                if track.is_grouped and track.group_track:
                    gt = track.group_track
                    # Find index of group track
                    for j, t in enumerate(song.tracks):
                        if t == gt:
                            info["group_track_index"] = j
                            info["group_track_name"] = gt.name
                            break
            except Exception:
                pass
            results.append(info)
        return {"tracks": results, "count": len(results)}
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error getting group structure: " + str(e))
        raise


def relocate_track(song, source_index, target_index, device_uris=None, ctrl=None):
    """Relocate a track by recreating it at a new position.

    Creates a new track at target_index, loads devices from URIs,
    copies properties (name, color, volume, pan, mute), then deletes
    the source track.

    Args:
        source_index: Index of track to move.
        target_index: Where to create the new track (within a group = inside it).
        device_uris: List of browser URIs to load on the new track, in order.
    """
    try:
        if source_index < 0 or source_index >= len(song.tracks):
            raise IndexError("Source track index out of range")

        src = song.tracks[source_index]

        # Capture properties
        name = src.name
        color = src.color_index
        vol = src.mixer_device.volume.value
        pan = src.mixer_device.panning.value
        mute = src.mute
        solo = src.solo
        is_midi = src.has_midi_input

        # Create new track at target position
        if is_midi:
            song.create_midi_track(target_index)
        else:
            song.create_audio_track(target_index)

        # Adjust source index if target was before it
        actual_source = source_index
        if target_index <= source_index:
            actual_source = source_index + 1

        new_track = song.tracks[target_index]

        # Set properties
        new_track.name = name
        new_track.color_index = color
        new_track.mixer_device.volume.value = vol
        new_track.mixer_device.panning.value = pan
        new_track.mute = mute
        if solo:
            new_track.solo = True

        # Load devices from URIs
        loaded_devices = []
        if device_uris and ctrl:
            from . import browser as br
            app = ctrl.application()
            for uri in device_uris:
                try:
                    item = br.find_browser_item_by_uri(app.browser, uri, ctrl=ctrl)
                    if item:
                        song.view.selected_track = new_track
                        app.browser.load_item(item)
                        loaded_devices.append(uri)
                    else:
                        loaded_devices.append("NOT_FOUND:" + uri)
                except Exception as load_err:
                    loaded_devices.append("ERROR:" + str(load_err))
                    if ctrl:
                        ctrl.log_message("Error loading URI {0}: {1}".format(uri, str(load_err)))

        # Delete old track
        song.delete_track(actual_source)

        # Figure out final index (deletion may shift)
        final_index = target_index
        if actual_source < target_index:
            final_index = target_index - 1

        return {
            "relocated": True,
            "name": name,
            "from_index": source_index,
            "to_index": final_index,
            "loaded_devices": loaded_devices,
        }
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error relocating track: " + str(e))
        raise


def move_to_group(song, track_name=None, track_index=None,
                   group_name=None, position="last", device_uris=None, ctrl=None):
    """Move a track into a group by name, handling index math internally.

    Args:
        track_name: Name of track to move (used if track_index not given).
        track_index: Index of track to move (takes priority over name).
        group_name: Name of the destination group bus.
        position: Where in the group: "first", "last", or "before:TRACK_NAME"
                  or "after:TRACK_NAME".
        device_uris: List of browser URIs to load on the new track.
    """
    try:
        tracks = list(song.tracks)

        # Resolve source track
        src_idx = track_index
        if src_idx is None:
            for i, t in enumerate(tracks):
                if t.name == track_name:
                    src_idx = i
                    break
            if src_idx is None:
                raise ValueError("Track not found: " + str(track_name))

        # Resolve group
        group_idx = None
        for i, t in enumerate(tracks):
            if t.name == group_name:
                try:
                    if t.is_foldable:
                        group_idx = i
                        break
                except Exception:
                    pass
        if group_idx is None:
            raise ValueError("Group not found: " + str(group_name))

        # Find group members (tracks whose group_track == group track)
        group_track = tracks[group_idx]
        members = []
        for i, t in enumerate(tracks):
            if i == group_idx:
                continue
            try:
                if t.is_grouped and t.group_track == group_track:
                    members.append(i)
            except Exception:
                pass

        if not members:
            # Empty group — insert right after the bus
            target = group_idx + 1
        elif position == "first":
            target = members[0]
        elif position == "last":
            target = members[-1]
        elif position.startswith("before:"):
            ref_name = position[7:]
            target = None
            for m in members:
                if tracks[m].name == ref_name:
                    target = m
                    break
            if target is None:
                raise ValueError("Reference track not found in group: " + ref_name)
        elif position.startswith("after:"):
            ref_name = position[6:]
            target = None
            for m in members:
                if tracks[m].name == ref_name:
                    # Insert at this position pushes ref track down,
                    # but we want AFTER, so use the next member or last
                    ref_pos = m
                    target = ref_pos + 1
                    # Check if target is still inside the group
                    if target > members[-1]:
                        target = members[-1]
                    break
            if target is None:
                raise ValueError("Reference track not found in group: " + ref_name)
        else:
            target = members[-1]

        return relocate_track(song, src_idx, target, device_uris, ctrl)
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error in move_to_group: " + str(e))
        raise


def get_track_routing(song, track_index, track_type="track", ctrl=None):
    """Get output routing info for a track: current routing and available options."""
    try:
        if track_type == "return":
            if track_index < 0 or track_index >= len(song.return_tracks):
                raise IndexError("Return track index out of range")
            track = song.return_tracks[track_index]
        elif track_type == "master":
            track = song.master_track
        else:
            if track_index < 0 or track_index >= len(song.tracks):
                raise IndexError("Track index out of range")
            track = song.tracks[track_index]

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
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error getting track routing: " + str(e))
        raise


def set_track_routing(song, track_index, output_type=None, output_channel=None,
                      track_type="track", ctrl=None):
    """Set output routing for a track by display name.

    Args:
        track_index: Index of track.
        output_type: Display name of output routing type (e.g. "SUB LIMITER").
        output_channel: Display name of output routing channel (e.g. "Track In").
        track_type: "track", "return", or "master".
    """
    try:
        if track_type == "return":
            if track_index < 0 or track_index >= len(song.return_tracks):
                raise IndexError("Return track index out of range")
            track = song.return_tracks[track_index]
        elif track_type == "master":
            track = song.master_track
        else:
            if track_index < 0 or track_index >= len(song.tracks):
                raise IndexError("Track index out of range")
            track = song.tracks[track_index]

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
                    "Output routing type '{0}' not found. Available: {1}".format(
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
                    "Output routing channel '{0}' not found. Available: {1}".format(
                        output_channel, ", ".join(available)
                    )
                )

        return result
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error setting track routing: " + str(e))
        raise


def get_return_tracks_info(song, ctrl=None):
    """Get info for all return tracks."""
    try:
        returns = []
        for i, track in enumerate(song.return_tracks):
            devices_list = []
            for d in track.devices:
                devices_list.append({"name": d.name, "class_name": d.class_name})
            returns.append({
                "index": i,
                "name": track.name,
                "volume": track.mixer_device.volume.value,
                "panning": track.mixer_device.panning.value,
                "color_index": track.color_index,
                "devices": devices_list,
            })
        return {"return_tracks": returns, "count": len(returns)}
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error getting return tracks info: " + str(e))
        raise
