"""Fake Live Object Model pieces for testing Remote Script commands offline.

Only what the extended commands touch is modelled. Attribute names match the
real Python LOM (song.tracks, track.mixer_device.volume, ...), so a handler
that works here calls the same members inside Live.
"""

import importlib.util
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


class FakeParameter(object):
    def __init__(self, name, value=0.0, min=0.0, max=1.0):
        self.name = name
        self.value = value
        self.min = min
        self.max = max


class FakeMixer(object):
    def __init__(self, sends=0):
        self.volume = FakeParameter("Track Volume", 0.85)
        self.panning = FakeParameter("Track Panning", 0.0, -1.0, 1.0)
        self.sends = [FakeParameter("Send %s" % chr(65 + i)) for i in range(sends)]


class FakeTrack(object):
    def __init__(self, name, audio=True, sends=0):
        self.name = name
        self.has_audio_input = audio
        self.has_midi_input = not audio
        self.mute = False
        self.solo = False
        self.arm = False
        self.mixer_device = FakeMixer(sends)
        self.devices = []
        self.clip_slots = []


class FakeSong(object):
    def __init__(self, track_names=("1-Audio", "2-MIDI"), return_names=("A-Reverb", "B-Delay")):
        n_returns = len(return_names)
        self.tracks = [FakeTrack(n, sends=n_returns) for n in track_names]
        self.return_tracks = [FakeTrack(n, sends=n_returns) for n in return_names]
        self.master_track = FakeTrack("Main")
        self.history = []  # every mutating LOM call, in order
        self.undo_depth = 0
        self.redo_depth = 0

    # Undo history
    @property
    def can_undo(self):
        return self.undo_depth > 0

    @property
    def can_redo(self):
        return self.redo_depth > 0

    def undo(self):
        self.history.append("undo")
        self.undo_depth -= 1
        self.redo_depth += 1

    def redo(self):
        self.history.append("redo")
        self.redo_depth -= 1
        self.undo_depth += 1

    # Structure
    def delete_track(self, index):
        self.history.append(("delete_track", index))
        del self.tracks[index]
        self.undo_depth += 1

    def delete_return_track(self, index):
        self.history.append(("delete_return_track", index))
        del self.return_tracks[index]
        self.undo_depth += 1
