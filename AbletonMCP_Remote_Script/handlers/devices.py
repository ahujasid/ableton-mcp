"""Device and parameter resolution; used by other handlers."""

from __future__ import absolute_import, print_function, unicode_literals


def resolve_track(song, track_index, track_type="track"):
    """Resolve a track by index and type (track, return, master)."""
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


def get_device_type(device, ctrl=None):
    """Get the type of a device."""
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


def get_device_parameters(song, track_index, device_index, track_type="track", ctrl=None):
    """Get all parameters for a device on any track type."""
    try:
        track = resolve_track(song, track_index, track_type)
        device_list = list(track.devices)
        if ctrl:
            ctrl.log_message(
                "Track '" + str(track.name) + "' has " + str(len(device_list)) + " devices"
            )
        if device_index < 0 or device_index >= len(device_list):
            raise IndexError(
                "Device index out of range (have " + str(len(device_list)) + " devices)"
            )
        device = device_list[device_index]
        parameters = []
        for i, param in enumerate(device.parameters):
            parameters.append({
                "index": i,
                "name": param.name,
                "value": param.value,
                "min": param.min,
                "max": param.max,
                "is_quantized": param.is_quantized,
                "value_items": list(param.value_items) if param.is_quantized else [],
            })
        return {
            "device_name": device.name,
            "device_type": device.class_name,
            "parameters": parameters,
        }
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error getting device parameters: " + str(e))
        raise


def set_device_parameter(
    song, track_index, device_index, parameter_index, value, track_type="track", ctrl=None
):
    """Set a device parameter on any track type."""
    try:
        track = resolve_track(song, track_index, track_type)
        device_list = list(track.devices)
        if device_index < 0 or device_index >= len(device_list):
            raise IndexError("Device index out of range")
        device = device_list[device_index]
        if parameter_index < 0 or parameter_index >= len(device.parameters):
            raise IndexError("Parameter index out of range")
        param = device.parameters[parameter_index]
        param.value = max(param.min, min(param.max, value))
        return {
            "name": param.name,
            "value": param.value,
            "track_type": track_type,
        }
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error setting device parameter: " + str(e))
        raise


def resolve_chain_device(song, track_index, device_index, chain_index, chain_device_index, track_type="track", ctrl=None):
    """Resolve a device inside a rack's chain."""
    track = resolve_track(song, track_index, track_type)
    device_list = list(track.devices)
    if device_index < 0 or device_index >= len(device_list):
        raise IndexError("Device index out of range")
    device = device_list[device_index]
    if not device.can_have_chains:
        raise Exception("Device is not a rack (cannot have chains)")
    chains = list(device.chains)
    if chain_index < 0 or chain_index >= len(chains):
        raise IndexError("Chain index out of range (have " + str(len(chains)) + " chains)")
    chain = chains[chain_index]
    chain_devices = list(chain.devices)
    if chain_device_index < 0 or chain_device_index >= len(chain_devices):
        raise IndexError("Chain device index out of range (have " + str(len(chain_devices)) + " devices)")
    return chain_devices[chain_device_index]


def get_chain_devices(song, track_index, device_index, chain_index=0, track_type="track", ctrl=None):
    """List all devices inside a rack's chain."""
    try:
        track = resolve_track(song, track_index, track_type)
        device_list = list(track.devices)
        if device_index < 0 or device_index >= len(device_list):
            raise IndexError("Device index out of range")
        device = device_list[device_index]
        if not device.can_have_chains:
            raise Exception("Device '" + device.name + "' is not a rack")
        chains = list(device.chains)
        if chain_index < 0 or chain_index >= len(chains):
            raise IndexError("Chain index out of range (have " + str(len(chains)) + " chains)")
        chain = chains[chain_index]
        devices = []
        for i, d in enumerate(chain.devices):
            devices.append({
                "index": i,
                "name": d.name,
                "class_name": d.class_name,
                "is_active": d.is_active,
                "can_have_chains": d.can_have_chains,
            })
        return {
            "rack_name": device.name,
            "chain_index": chain_index,
            "chain_name": chain.name,
            "chain_count": len(chains),
            "devices": devices,
        }
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error getting chain devices: " + str(e))
        raise


def get_chain_device_parameters(song, track_index, device_index, chain_index, chain_device_index, track_type="track", ctrl=None):
    """Get all parameters for a device inside a rack's chain."""
    try:
        device = resolve_chain_device(song, track_index, device_index, chain_index, chain_device_index, track_type, ctrl)
        parameters = []
        for i, param in enumerate(device.parameters):
            parameters.append({
                "index": i,
                "name": param.name,
                "value": param.value,
                "min": param.min,
                "max": param.max,
                "is_quantized": param.is_quantized,
                "value_items": list(param.value_items) if param.is_quantized else [],
            })
        return {
            "device_name": device.name,
            "device_type": device.class_name,
            "parameters": parameters,
        }
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error getting chain device parameters: " + str(e))
        raise


def set_chain_device_parameter(song, track_index, device_index, chain_index, chain_device_index, parameter_index, value, track_type="track", ctrl=None):
    """Set a parameter on a device inside a rack's chain."""
    try:
        device = resolve_chain_device(song, track_index, device_index, chain_index, chain_device_index, track_type, ctrl)
        if parameter_index < 0 or parameter_index >= len(device.parameters):
            raise IndexError("Parameter index out of range")
        param = device.parameters[parameter_index]
        param.value = max(param.min, min(param.max, value))
        return {
            "device_name": device.name,
            "name": param.name,
            "value": param.value,
            "track_type": track_type,
        }
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error setting chain device parameter: " + str(e))
        raise


def delete_device(song, track_index, device_index, track_type="track", ctrl=None):
    """Delete a device from a track."""
    try:
        track = resolve_track(song, track_index, track_type)
        device_list = list(track.devices)
        if device_index < 0 or device_index >= len(device_list):
            raise IndexError("Device index out of range (have " + str(len(device_list)) + " devices)")
        device = device_list[device_index]
        name = device.name
        class_name = device.class_name
        track.delete_device(device_index)
        return {
            "deleted": name,
            "class_name": class_name,
            "track_index": track_index,
            "track_type": track_type,
        }
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error deleting device: " + str(e))
        raise


def delete_chain_device(song, track_index, device_index, chain_index, chain_device_index, track_type="track", ctrl=None):
    """Delete a device from inside a rack's chain."""
    try:
        track = resolve_track(song, track_index, track_type)
        device_list = list(track.devices)
        if device_index < 0 or device_index >= len(device_list):
            raise IndexError("Device index out of range")
        device = device_list[device_index]
        if not device.can_have_chains:
            raise Exception("Device '" + device.name + "' is not a rack")
        chains = list(device.chains)
        if chain_index < 0 or chain_index >= len(chains):
            raise IndexError("Chain index out of range (have " + str(len(chains)) + " chains)")
        chain = chains[chain_index]
        chain_devices = list(chain.devices)
        if chain_device_index < 0 or chain_device_index >= len(chain_devices):
            raise IndexError("Chain device index out of range (have " + str(len(chain_devices)) + " devices)")
        target = chain_devices[chain_device_index]
        name = target.name
        class_name = target.class_name
        chain.delete_device(chain_device_index)
        return {
            "deleted": name,
            "class_name": class_name,
            "rack_name": device.name,
            "chain_index": chain_index,
            "chain_name": chain.name,
        }
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error deleting chain device: " + str(e))
        raise


def _serialize_device(device, ctrl=None, max_depth=10, _depth=0):
    """Serialize a device, recursively including chains for rack devices.

    Stops recursing past max_depth to avoid RecursionError on deeply nested racks.
    """
    device_info = {
        "name": device.name,
        "class_name": device.class_name,
        "type": get_device_type(device, ctrl),
    }
    if (
        getattr(device, "can_have_chains", False)
        and _depth < max_depth
    ):
        chains = []
        for chain_index, chain in enumerate(device.chains):
            chain_devices = []
            for dev_index, dev in enumerate(chain.devices):
                cd = _serialize_device(dev, ctrl, max_depth, _depth + 1)
                cd["index"] = dev_index
                chain_devices.append(cd)
            chains.append({
                "index": chain_index,
                "name": chain.name,
                "devices": chain_devices,
            })
        device_info["chains"] = chains
    return device_info


def get_rack_device_info(song, track_index, device_index, track_type="track", ctrl=None):
    """Get detailed information about a rack device's chains and nested devices."""
    try:
        track = resolve_track(song, track_index, track_type)
        device_list = list(track.devices)
        if device_index < 0 or device_index >= len(device_list):
            raise ValueError("Device index out of range")
        device = device_list[device_index]
        if not getattr(device, "can_have_chains", False):
            raise ValueError("Device at index %s is not a rack" % device_index)
        return _serialize_device(device, ctrl)
    except Exception as e:
        if ctrl:
            ctrl.log_message(
                "Error getting rack device info (track=%s, device=%s): %s"
                % (track_index, device_index, str(e))
            )
        raise


def get_macro_values(song, track_index, device_index, ctrl=None):
    """Get the values of all 8 macro controls on a rack device."""
    try:
        if track_index < 0 or track_index >= len(song.tracks):
            raise IndexError("Track index out of range")
        track = song.tracks[track_index]
        if device_index < 0 or device_index >= len(track.devices):
            raise IndexError("Device index out of range")
        device = track.devices[device_index]
        if not hasattr(device, "macros_mapped"):
            raise Exception("Device is not a rack (no macros)")
        macros = []
        for i in range(8):
            if i < len(device.parameters):
                macro_param = (
                    device.parameters[i + 1]
                    if len(device.parameters) > i + 1
                    else None
                )
                if macro_param:
                    macros.append({
                        "index": i,
                        "name": macro_param.name,
                        "value": macro_param.value,
                        "min": macro_param.min,
                        "max": macro_param.max,
                        "is_enabled": getattr(
                            macro_param, "is_enabled", True
                        ),
                    })
        return {
            "track_index": track_index,
            "device_index": device_index,
            "device_name": device.name,
            "macros": macros,
        }
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error getting macro values: " + str(e))
        raise


def set_macro_value(song, track_index, device_index, macro_index, value, ctrl=None):
    """Set the value of a specific macro control on a rack device."""
    try:
        if track_index < 0 or track_index >= len(song.tracks):
            raise IndexError("Track index out of range")
        track = song.tracks[track_index]
        if device_index < 0 or device_index >= len(track.devices):
            raise IndexError("Device index out of range")
        device = track.devices[device_index]
        if not hasattr(device, "macros_mapped"):
            raise Exception("Device is not a rack (no macros)")
        if macro_index < 0 or macro_index > 7:
            raise IndexError("Macro index must be 0-7")
        param_index = macro_index + 1
        if param_index >= len(device.parameters):
            raise Exception(
                "Macro {0} not available on this device".format(macro_index + 1)
            )
        macro_param = device.parameters[param_index]
        macro_param.value = value
        return {
            "track_index": track_index,
            "device_index": device_index,
            "macro_index": macro_index,
            "macro_name": macro_param.name,
            "value": macro_param.value,
        }
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error setting macro value: " + str(e))
        raise
