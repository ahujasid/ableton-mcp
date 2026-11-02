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
        self.back_to_arranger = False
        self.muted_via_solo = False
        self._mute = self._solo = self._arm = False
        self._monitoring = 1  # auto
        self.mixer_device = FakeMixer(sends, history)
        self.devices = []
        self.clip_slots = []
        self._in_type, self._in_chan = Routing("Ext. In"), Routing("1/2")
        self._out_type, self._out_chan = Routing("Master"), Routing("Track In")
        for side in ("input", "output"):
            for part in ("left", "right", "level"):
                setattr(self, "%s_meter_%s" % (side, part), 0.0)

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
    def __init__(self, name, params):
        self.name = name
        self.parameters = params


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
