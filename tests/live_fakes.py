"""Fake Live Object Model pieces for testing Remote Script commands offline.

Only what the extended commands touch is modelled. Attribute names match the
real Python LOM (song.tracks, track.mixer_device.volume, ...), so a handler
that works here calls the same members inside Live. Every LOM write is logged
in song.history so a test can assert that a refused command changed nothing.
"""

import importlib.util
import math
import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
REPO_SCRIPT = REPO_ROOT / "AbletonMCP_Remote_Script" / "__init__.py"


def load_script_module():
    """Import the Live-side script with _Framework stubbed out."""
    framework = types.ModuleType("_Framework")
    control_surface_mod = types.ModuleType("_Framework.ControlSurface")

    class _StubControlSurface(object):
        def __init__(self, *args, **kwargs):
            pass

        def log_message(self, *args, **kwargs):
            pass

        def show_message(self, *args, **kwargs):
            pass

    control_surface_mod.ControlSurface = _StubControlSurface
    framework.ControlSurface = control_surface_mod
    sys.modules.setdefault("_Framework", framework)
    sys.modules.setdefault("_Framework.ControlSurface", control_surface_mod)
    spec = importlib.util.spec_from_file_location("ableton_mcp_script_extended", REPO_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_script(module, song):
    """An AbletonMCP instance bound to a fake song, without opening a socket.
    schedule_message runs the task at once, as if Live's main thread did."""
    inst = module.AbletonMCP.__new__(module.AbletonMCP)
    inst._song = song
    inst.log_message = lambda *a, **k: None
    inst.show_message = lambda *a, **k: None
    inst.scheduled = []

    def schedule_message(delay, fn):
        inst.scheduled.append(fn)
        fn()

    inst.schedule_message = schedule_message
    return inst


class Unsupported(object):
    """Descriptor for a LOM property a track type doesn't have: reading it raises,
    as Live does (e.g. input routing on the master)."""

    def __get__(self, obj, owner):
        raise RuntimeError("not available on this track")


class History(object):
    def __init__(self):
        self.events = []

    def log(self, *event):
        self.events.append(event)


class FakeParameter(object):
    def __init__(self, name, value=0.0, min=0.0, max=1.0, history=None, kind="linear"):
        self.name = name
        self._value = value
        self.min = min
        self.max = max
        self.kind = kind
        self.automation_state = 0
        self.original_name = name
        self.is_quantized = False
        self.is_enabled = True
        self.value_items = []
        self._history = history

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, v):
        if self._history is not None:
            self._history.log("set", self.name, v)
        self._value = v

    def str_for_value(self, v):
        if self.kind == "volume":
            # Monotonic stand-in for Live's fader curve: 0.85 = 0 dB, 1.0 = +6 dB.
            if v <= 0:
                return "-inf dB"
            return "%.1f dB" % (6.0 * math.log(v / 0.85) / math.log(1.0 / 0.85))
        if self.kind == "pan":
            if abs(v) < 1e-9:
                return "C"
            return "%d%s" % (round(abs(v) * 50), "R" if v > 0 else "L")
        if self.kind == "db_linear":
            return "%.1f dB" % v
        return "%.2f" % v

    def __str__(self):
        return self.str_for_value(self._value)

    def re_enable_automation(self):
        if self._history is not None:
            self._history.log("re_enable", self.name)
        self.automation_state = 1


class FakeMixer(object):
    def __init__(self, sends, history):
        self.volume = FakeParameter("Track Volume", 0.85, history=history, kind="volume")
        self.panning = FakeParameter("Track Panning", 0.0, -1.0, 1.0, history=history, kind="pan")
        self.sends = [FakeParameter("%s-Send" % chr(65 + i), history=history) for i in range(sends)]


class Routing(object):
    """Stand-in for Live's RoutingType / RoutingChannel."""

    def __init__(self, display_name):
        self.display_name = display_name

    def __repr__(self):
        return "Routing(%r)" % self.display_name


INPUT_TYPES = ["Ext. In", "Resampling", "No Input", "2-MIDI"]
INPUT_CHANNELS = {"Ext. In": ["1/2", "3/4", "1", "2", "3", "4"], "Resampling": ["Post FX"],
                  "No Input": [], "2-MIDI": ["Post FX", "Pre FX"]}
OUTPUT_TYPES = ["Master", "Ext. Out", "Sends Only"]
OUTPUT_CHANNELS = {"Master": ["Track In"], "Ext. Out": ["1/2", "3/4", "1", "2", "3", "4"],
                   "Sends Only": []}


class FakeTrack(object):
    def __init__(self, name, history, audio=True, sends=0, armable=True):
        self.name = name
        self._history = history
        self.has_audio_input = audio
        self.has_midi_input = not audio
        self.can_be_armed = armable
        self.is_grouped = False
        self.group_track = None
        self.is_foldable = False
        self.fold_state = 0
        self.color_index = 0
        self.back_to_arranger = False
        self.muted_via_solo = False
        self._mute = self._solo = self._arm = False
        self._monitoring = 1  # auto
        self.mixer_device = FakeMixer(sends, history)
        self.devices = []
        self.clip_slots = []
        self.arrangement_clips = []
        self._in_type, self._in_chan = Routing("Ext. In"), Routing("1/2")
        self._out_type, self._out_chan = Routing("Master"), Routing("Track In")
        for side in ("input", "output"):
            for part in ("left", "right", "level"):
                setattr(self, "%s_meter_%s" % (side, part), 0.0)

    def delete_device(self, index):
        self._history.log("track.delete_device", self.name, index)
        del self.devices[index]

    def _set(self, attr, value):
        self._history.log("set", self.name, attr, value)
        setattr(self, "_" + attr, value)

    mute = property(lambda s: s._mute, lambda s, v: s._set("mute", v))
    solo = property(lambda s: s._solo, lambda s, v: s._set("solo", v))
    arm = property(lambda s: s._arm, lambda s, v: s._set("arm", v))
    current_monitoring_state = property(lambda s: s._monitoring, lambda s, v: s._set("monitoring", v))

    # Routing: lists of Routing objects; setting takes one of them.
    @property
    def available_input_routing_types(self):
        return [Routing(n) for n in INPUT_TYPES]

    @property
    def available_input_routing_channels(self):
        return [Routing(n) for n in INPUT_CHANNELS[self._in_type.display_name]]

    @property
    def available_output_routing_types(self):
        return [Routing(n) for n in OUTPUT_TYPES]

    @property
    def available_output_routing_channels(self):
        return [Routing(n) for n in OUTPUT_CHANNELS[self._out_type.display_name]]

    def _set_type(self, side, value):
        self._set(side + "_type", value)
        chans = (INPUT_CHANNELS if side == "in" else OUTPUT_CHANNELS)[value.display_name]
        setattr(self, "_%s_chan" % side, Routing(chans[0]) if chans else None)

    input_routing_type = property(lambda s: s._in_type, lambda s, v: s._set_type("in", v))
    input_routing_channel = property(lambda s: s._in_chan, lambda s, v: s._set("in_chan", v))
    output_routing_type = property(lambda s: s._out_type, lambda s, v: s._set_type("out", v))
    output_routing_channel = property(lambda s: s._out_chan, lambda s, v: s._set("out_chan", v))


class FakeReturnTrack(FakeTrack):
    """Return tracks have no input routing or input meters, and no arm."""
    available_input_routing_types = Unsupported()
    available_input_routing_channels = Unsupported()
    input_routing_type = Unsupported()
    input_routing_channel = Unsupported()
    input_meter_left = Unsupported()
    input_meter_right = Unsupported()
    input_meter_level = Unsupported()

    def __init__(self, *a, **k):
        k["armable"] = False
        super(FakeReturnTrack, self).__init__(*a, **k)

    def __setattr__(self, key, value):
        if key.startswith("input_meter_"):
            return  # no input meters to initialise
        object.__setattr__(self, key, value)


class FakeMasterTrack(FakeReturnTrack):
    mute = Unsupported()
    solo = Unsupported()
    muted_via_solo = Unsupported()

    def __setattr__(self, key, value):
        if key in ("muted_via_solo",) or key.startswith("input_meter_"):
            return
        object.__setattr__(self, key, value)


class FakeDevice(object):
    """A device. Parameter 0 is "Device On", as in Live."""

    def __init__(self, name, params, history=None, class_name="AudioEffect", dtype=2, chains=None,
                 device_on=True):
        self._history = history
        self.name = name
        self.class_name = class_name
        self.class_display_name = class_name
        self.type = dtype
        self.latency_in_ms = 0.0
        on = FakeParameter("Device On", 1.0 if device_on else 0.0, 0.0, 1.0, history=history)
        on.original_name = "Device On"
        on.is_quantized = True
        on.value_items = ["Off", "On"]
        self.parameters = [on] + list(params)
        self.chains = chains or []
        self.can_have_chains = chains is not None

    @property
    def is_active(self):
        return self.parameters[0].value >= 0.5


class FakeSidechainDevice(FakeDevice):
    """A Compressor-like device with sidechain input routing."""

    def __init__(self, name, params, history=None):
        super(FakeSidechainDevice, self).__init__(name, params, history, class_name="Compressor2")
        self._sc_type, self._sc_chan = Routing("No Input"), None

    @property
    def available_input_routing_types(self):
        return [Routing(n) for n in ("No Input", "1-Audio", "2-MIDI", "Ext. In")]

    @property
    def available_input_routing_channels(self):
        return [Routing(n) for n in {"1-Audio": ["Pre FX", "Post FX", "Post Mixer"],
                                     "Ext. In": ["1/2", "3/4"]}.get(self._sc_type.display_name, [])]

    def _set_sc(self, attr, v):
        self._history.log("set", self.name, attr, v.display_name)
        setattr(self, attr, v)
        if attr == "_sc_type":
            chans = self.available_input_routing_channels
            self._sc_chan = chans[0] if chans else None

    input_routing_type = property(lambda s: s._sc_type, lambda s, v: s._set_sc("_sc_type", v))
    input_routing_channel = property(lambda s: s._sc_chan, lambda s, v: s._set_sc("_sc_chan", v))


class FakeChain(object):
    def __init__(self, name, devices, history):
        self.name = name
        self.devices = devices
        self.mute = False
        self.solo = False
        self._history = history

    def delete_device(self, index):
        self._history.log("chain.delete_device", self.name, index)
        del self.devices[index]


def utility(history, gain=0.0, automated=0):
    """Live 12 Utility: Output (Live 11: Gain) shown in dB over a -35..35 range (raw = dB here)."""
    g = FakeParameter("Output", gain, -35.0, 35.0, history=history, kind="db_linear")
    g.automation_state = automated
    return FakeDevice("Utility", [g, FakeParameter("Mono", 0.0, 0.0, 1.0, history=history)],
                      history, class_name="StereoGain")


class FakeClip(object):
    def __init__(self, name, history, audio=True, length=4.0, arrangement=False):
        self._history = history
        self.name = name
        self.is_audio_clip = audio
        self.is_midi_clip = not audio
        self.is_arrangement_clip = arrangement
        self.length = length
        self.looping = True
        self.loop_start, self.loop_end = 0.0, length
        self.start_marker, self.end_marker = 0.0, length
        self.muted = False
        self.color_index = 0
        self.launch_mode = 0
        self.has_envelopes = False
        self.start_time, self.end_time = 0.0, length
        if audio:
            self._gain = 0.4
            self.warping = True
            self.warp_mode = 0
            self.pitch_coarse = 0
            self.pitch_fine = 0.0
            self.file_path = "Z:\\home\\jeremy\\take.wav"
            self.sample_rate = 48000.0
        self._ready = True

    def __setattr__(self, key, value):
        h = self.__dict__.get("_history") if self.__dict__.get("_ready") else None
        if h is not None and not key.startswith("_"):
            if key == "loop_start" and value >= self.__dict__.get("loop_end", float("inf")):
                raise RuntimeError("loop_start must be before loop_end")
            h.log("clip", key, value)
        object.__setattr__(self, key, value)

    # Clip gain: 0..1 raw, shown in dB; 0.4 = 0 dB, 1.0 = +24 dB, 0 = -inf
    gain = property(lambda s: s._gain, lambda s, v: s._set_gain(v))

    def _set_gain(self, v):
        self.__dict__["_gain"] = v
        if self._history is not None and not self.__dict__.get("_quiet"):
            self._history.log("clip", "gain", v)

    @property
    def gain_display_string(self):
        if self._gain <= 0:
            return "-inf dB"
        return "%.1f dB" % (24.0 * math.log(self._gain / 0.4) / math.log(1.0 / 0.4))


class FakeClipSlot(object):
    def __init__(self, clip=None):
        self.clip = clip

    @property
    def has_clip(self):
        return self.clip is not None


class FakeScene(object):
    def __init__(self, name, history, empty=True):
        self._history = history
        self.name = name
        self.is_empty = empty
        self.tempo = 120.0
        self.tempo_enabled = False
        self.time_signature_numerator = 4
        self.time_signature_denominator = 4
        self.time_signature_enabled = False
        self.color_index = 0
        self._ready = True

    def __setattr__(self, key, value):
        h = self.__dict__.get("_history") if self.__dict__.get("_ready") else None
        if h is not None and not key.startswith("_"):
            h.log("scene", key, value)
        object.__setattr__(self, key, value)

    def fire(self):
        self._history.log("scene.fire", self.name)


class FakeSong(object):
    def __init__(self, track_names=("1-Audio", "2-MIDI"), return_names=("A-Reverb", "B-Delay")):
        self.h = History()
        n = len(return_names)
        self.tracks = [FakeTrack(name, self.h, sends=n) for name in track_names]
        self.return_tracks = [FakeReturnTrack(name, self.h, sends=n) for name in return_names]
        self.master_track = FakeMasterTrack("Main", self.h)
        self.undo_depth = 0
        self.redo_depth = 0
        self._back_to_arranger = False
        self.re_enable_automation_enabled = False
        self.exclusive_solo = True
        self.file_path = ""
        self.name = ""
        self.tempo = 120.0
        self.scenes = [FakeScene("", self.h) for _ in range(2)]
        self.undo_steps = []  # "begin"/"end" in order, to check they pair up

    @property
    def history(self):
        return self.h.events

    # Undo history
    @property
    def can_undo(self):
        return self.undo_depth > 0

    @property
    def can_redo(self):
        return self.redo_depth > 0

    def undo(self):
        self.h.log("undo")
        self.undo_depth -= 1
        self.redo_depth += 1

    def redo(self):
        self.h.log("redo")
        self.redo_depth -= 1
        self.undo_depth += 1

    # Structure
    def delete_track(self, index):
        self.h.log("delete_track", index)
        del self.tracks[index]
        self.undo_depth += 1

    def begin_undo_step(self):
        self.undo_steps.append("begin")

    def end_undo_step(self):
        self.undo_steps.append("end")

    def duplicate_track(self, index):
        self.h.log("duplicate_track", index)
        src = self.tracks[index]
        self.tracks.insert(index + 1, FakeTrack(src.name + " copy", self.h, sends=len(self.return_tracks)))

    def create_return_track(self):
        self.h.log("create_return_track")
        self.return_tracks.append(FakeReturnTrack("%s-Return" % chr(65 + len(self.return_tracks)), self.h))

    def move_device(self, device, target, index):
        self.h.log("move_device", device.name, target.name, index)
        for t in self.tracks + self.return_tracks + [self.master_track]:
            if device in t.devices:
                t.devices.remove(device)
        target.devices.insert(index, device)
        return index

    def create_scene(self, index):
        self.h.log("create_scene", index)
        sc = FakeScene("", self.h)
        if index == -1:
            self.scenes.append(sc)
        else:
            self.scenes.insert(index, sc)

    def duplicate_scene(self, index):
        self.h.log("duplicate_scene", index)
        self.scenes.insert(index + 1, FakeScene(self.scenes[index].name, self.h, self.scenes[index].is_empty))

    def delete_scene(self, index):
        self.h.log("delete_scene", index)
        del self.scenes[index]

    def delete_return_track(self, index):
        self.h.log("delete_return_track", index)
        del self.return_tracks[index]
        self.undo_depth += 1

    # Transport / automation
    @property
    def back_to_arranger(self):
        return self._back_to_arranger

    @back_to_arranger.setter
    def back_to_arranger(self, v):
        self.h.log("back_to_arranger", v)
        self._back_to_arranger = v

    def re_enable_automation(self):
        self.h.log("song.re_enable_automation")
        self.re_enable_automation_enabled = False
