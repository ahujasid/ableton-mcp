"""Live-side tests for the 1.9 studio commands, against small LOM fakes."""

import math

import pytest

from test_remote_script_bridge import _load_script_module, make_instance


@pytest.fixture(scope="module")
def mod():
    return _load_script_module()


# ------------------------------------------------------------------ fakes

class Param(object):
    def __init__(self, name, value=0.0, lo=0.0, hi=1.0, fmt=None, items=None):
        self.name = name
        self.value = value
        self.min = lo
        self.max = hi
        self._fmt = fmt or (lambda v: "%.2f" % v)
        self.value_items = items or []
        self.is_quantized = bool(items)

    def str_for_value(self, v):
        if self.value_items:
            return self.value_items[int(round(v - self.min))]
        return self._fmt(v)


def freq_param():
    # Live-like log frequency knob: 0..1 -> 20 Hz..20 kHz
    def fmt(v):
        hz = 20.0 * (1000.0 ** v)
        return ("%.2f kHz" % (hz / 1000.0)) if hz >= 1000 else ("%.0f Hz" % hz)
    return Param("Frequency", 0.5, 0.0, 1.0, fmt)


def db_param(name="Threshold"):
    return Param(name, 0.0, -60.0, 0.0, lambda v: "%.1f dB" % v)


class Envelope(object):
    def __init__(self):
        self.steps = []

    def insert_step(self, t, length, value):
        self.steps.append((t, length, value))

    def value_at_time(self, t):
        value = None
        for start, length, v in self.steps:
            if start <= t + 1e-9:
                value = v
        return value if value is not None else 0.0


class Clip(object):
    def __init__(self, name="Clip", length=8.0, audio=False):
        self.name = name
        self.length = length
        self.loop_end = length
        self.looping = True
        self.is_audio_clip = audio
        self.envelopes = {}
        self.groove = None
        self.start_time = 0.0
        self.end_time = length

    def automation_envelope(self, param):
        return self.envelopes.get(param.name)

    def create_automation_envelope(self, param):
        env = Envelope()
        self.envelopes[param.name] = env
        return env

    def clear_envelope(self, param):
        self.envelopes.pop(param.name, None)

    def clear_all_envelopes(self):
        self.envelopes = {}


class Slot(object):
    def __init__(self, clip=None):
        self.clip = clip

    @property
    def has_clip(self):
        return self.clip is not None


class Device(object):
    def __init__(self, name, params=(), class_name="AudioEffect"):
        self.name = name
        self.class_name = class_name
        self.parameters = list(params)


class Mixer(object):
    def __init__(self):
        self.volume = Param("Track Volume", 0.85, 0.0, 1.0, lambda v: "%.1f dB" % (40 * math.log10(max(v, 1e-9) / 0.85)))
        self.panning = Param("Track Panning", 0.0, -1.0, 1.0)
        self.sends = [Param("Send A"), Param("Send B")]
        self.track_activator = Param("Track Activator", 1.0, 0.0, 1.0, items=["Off", "On"])


class RoutingType(object):
    def __init__(self, name):
        self.display_name = name


class Track(object):
    def __init__(self, name="T", devices=(), slots=0, audio=False):
        self.name = name
        self.devices = list(devices)
        self.clip_slots = [Slot() for _ in range(slots)]
        self.mixer_device = Mixer()
        self.mute = False
        self.solo = False
        self.arm = False
        self.can_be_armed = True
        self.has_audio_input = audio
        self.has_midi_input = not audio
        self.arrangement_clips = []
        self.available_input_routing_types = [RoutingType("Ext. In"), RoutingType("Resampling"),
                                              RoutingType("1-Kick")]
        self.input_routing_type = None
        self.current_monitoring_state = 1
        self.inserted = []

    def delete_device(self, index):
        del self.devices[index]

    def delete_clip(self, clip):
        self.arrangement_clips.remove(clip)


class Groove(object):
    def __init__(self, name):
        self.name = name
        self.base = 3
        self.timing_amount = 1.0
        self.random_amount = 0.0
        self.velocity_amount = 0.0
        self.quantization_amount = 0.0


class Pool(object):
    def __init__(self, grooves):
        self.grooves = grooves


class View(object):
    selected_track = None
    highlighted_clip_slot = None
    detail_clip = None


class Song(object):
    def __init__(self, tracks=(), returns=()):
        self.tracks = list(tracks)
        self.return_tracks = list(returns)
        self.master_track = Track("Master")
        self.view = View()
        self.groove_pool = Pool([Groove("MPC 16 Swing-58")])
        self.groove_amount = 1.0
        self.root_note = 0
        self.scale_name = "Major"
        self.scale_mode = False
        self.scale_intervals = [0, 2, 4, 5, 7, 9, 11]
        self.tempo = 120.0
        self.loop = True
        self.metronome = True
        self.punch_in = False
        self.punch_out = False
        self.record_mode = False
        self.is_playing = False
        self.current_song_time = 10.0
        self.back_to_arranger = True

    def create_audio_track(self, index):
        self.tracks.append(Track("Audio", audio=True))

    def create_return_track(self):
        self.return_tracks.append(Track("Return"))

    def delete_track(self, i):
        del self.tracks[i]

    def delete_return_track(self, i):
        del self.return_tracks[i]

    def duplicate_track(self, i):
        self.tracks.insert(i + 1, Track(self.tracks[i].name + " copy"))

    def start_playing(self):
        self.is_playing = True

    def stop_playing(self):
        self.is_playing = False


def inst(mod, song, browser=None):
    i = make_instance(mod)
    i._song = song
    i._render_job = None

    class App(object):
        pass
    app = App()
    app.browser = browser
    i.application = lambda: app
    return i


# ------------------------------------------------------------------ display values

def test_parse_quantity(mod):
    p = mod.AbletonMCP._parse_quantity
    assert p("1.20 kHz") == (1200.0, "hz")
    assert p("-6.0 dB") == (-6.0, "db")
    assert p("350 ms") == (pytest.approx(0.35), "s")
    assert p("-inf dB")[0] == float("-inf")
    assert p("Lowpass") is None


def test_value_for_display_bisects_log_knob(mod):
    i = inst(mod, Song())
    p = freq_param()
    raw = i._value_for_display(p, "1.2 kHz")
    assert p.str_for_value(raw) == "1.20 kHz"
    raw = i._value_for_display(p, "300 Hz")
    assert p.str_for_value(raw) == "300 Hz"


def test_value_for_display_quantized_and_clamped(mod):
    i = inst(mod, Song())
    p = Param("Filter Type", 0, 0, 2, items=["Lowpass", "Highpass", "Bandpass"])
    assert i._value_for_display(p, "highpass") == 1.0
    with pytest.raises(Exception):
        i._value_for_display(p, "Notch")
    t = db_param()
    assert i._value_for_display(t, "+10 dB") == 0.0  # clamps at max


def test_set_device_parameters_by_name(mod):
    eq = Device("Auto Filter", [freq_param(), Param("Resonance", 0.1), db_param("Drive")])
    song = Song([Track("Pads", devices=[eq])])
    out = inst(mod, song)._cmd_set_device_parameters({
        "track_index": 0, "device_index": 0,
        "changes": [{"name": "frequency", "display": "800 Hz"},
                    {"name": "Resonance", "normalized": 0.4},
                    {"index": 2, "value": -12}]})
    assert [r["display"] for r in out["set"]] == ["800 Hz", "0.40", "-12.0 dB"]


def test_set_device_parameter_on_return_with_display(mod):
    song = Song([Track("A")], returns=[Track("Verb", devices=[Device("Reverb", [db_param("Decay")])])])
    out = inst(mod, song)._set_device_parameter(0, 0, 0, 0.0, track_type="return", display="-20 dB")
    assert out["display"] == "-20.0 dB"


# ------------------------------------------------------------------ devices

def test_add_device_prefers_insert_device(mod):
    track = Track("Bass")

    def insert_device(name, index=None):
        track.devices.insert(len(track.devices) if index is None else index, Device(name))
    track.insert_device = insert_device
    out = inst(mod, Song([track]))._cmd_add_device({"track_index": 0, "name": "Saturator"})
    assert out["method"] == "insert_device"
    assert [d["name"] for d in out["devices"]] == ["Saturator"]


def test_add_device_falls_back_to_browser_on_master(mod):
    class Item(object):
        def __init__(self, name, children=()):
            self.name = name
            self.children = list(children)
            self.is_loadable = not children
            self.is_folder = bool(children)

    class Browser(object):
        audio_effects = Item("root", [Item("Dynamics", [Item("Limiter.adv")])])
        instruments = Item("root")
        loaded = []

        def load_item(self, item):
            self.loaded.append(item.name)
            song.view.selected_track.devices.append(Device("Limiter"))

    song = Song([Track("A")])
    browser = Browser()
    out = inst(mod, song, browser)._cmd_add_device(
        {"track_index": 0, "track_type": "master", "name": "Limiter"})
    assert out["method"] == "browser"
    assert browser.loaded == ["Limiter.adv"]
    assert song.master_track.devices[-1].name == "Limiter"


def test_delete_device(mod):
    song = Song([Track("A", devices=[Device("EQ Eight"), Device("Compressor")])])
    out = inst(mod, song)._cmd_delete_device({"track_index": 0, "device_index": 0})
    assert out["deleted"] == "EQ Eight"
    assert [d["name"] for d in out["devices"]] == ["Compressor"]


def test_sidechain_routes_from_named_track(mod):
    comp = Device("Compressor", [Param("S/C On", 0, 0, 1, items=["Off", "On"]), db_param()])
    comp.available_input_routing_types = [RoutingType("No Input"), RoutingType("1-Kick"),
                                          RoutingType("2-Bass")]
    comp.available_input_routing_channels = [RoutingType("Pre FX"), RoutingType("Post FX"),
                                             RoutingType("Post Mixer")]
    comp.input_routing_type = None
    comp.input_routing_channel = None
    song = Song([Track("Kick"), Track("Bass", devices=[comp])])
    out = inst(mod, song)._cmd_set_sidechain({"track_index": 1, "device_index": 0,
                                              "source_track_index": 0})
    assert out["source"] == "1-Kick"
    assert out["channel"] == "Post FX"
    assert comp.parameters[0].value == 1
    assert out["enabled_parameter"] == "S/C On"


def test_sidechain_unsupported_device(mod):
    song = Song([Track("Bass", devices=[Device("Glue Compressor")])])
    with pytest.raises(Exception, match="doesn't expose sidechain"):
        inst(mod, song)._cmd_set_sidechain({"track_index": 0, "device_index": 0,
                                            "source_track_name": "Kick"})


# ------------------------------------------------------------------ automation

def automation_song():
    filt = Device("Auto Filter", [freq_param(), Param("Mode", 0, 0, 2, items=["A", "B", "C"])])
    track = Track("Pads", devices=[filt], slots=2)
    track.clip_slots[0].clip = Clip("Build", 32.0)
    return Song([track]), track


def test_write_ramp_then_hold(mod):
    song, track = automation_song()
    out = inst(mod, song)._cmd_write_clip_automation({
        "track_index": 0, "clip_index": 0,
        "target": {"device_index": 0, "parameter_name": "Frequency"},
        "points": [{"time": 0, "display": "300 Hz"}, {"time": 28, "display": "8 kHz"}],
        "resolution": 0.5})
    env = track.clip_slots[0].clip.envelopes["Frequency"]
    assert out["steps"] == 57  # 56 ramp steps + final hold
    assert env.steps[0][0] == 0 and env.steps[-1][0] == 28
    assert env.steps[-1][1] == pytest.approx(4.0)  # hold to clip end
    values = [s[2] for s in env.steps]
    assert values == sorted(values)  # monotonic sweep
    assert out["last_display"] == "8.00 kHz"


def test_write_leading_hold_and_step_curve(mod):
    song, track = automation_song()
    inst(mod, song)._cmd_write_clip_automation({
        "track_index": 0, "clip_index": 0,
        "target": {"mixer": "send", "send_index": 1},
        "points": [{"time": 4, "value": 0.0}, {"time": 7.5, "value": 0.8}, {"time": 8, "value": 0.0}],
        "curve": "step"})
    steps = track.clip_slots[0].clip.envelopes["Send B"].steps
    assert steps[0] == (0.0, 4.0, 0.0)
    assert steps[1] == (4.0, 3.5, 0.0)
    assert steps[2] == (7.5, 0.5, 0.8)


def test_quantized_param_uses_steps(mod):
    song, track = automation_song()
    out = inst(mod, song)._cmd_write_clip_automation({
        "track_index": 0, "clip_index": 0,
        "target": {"device_index": 0, "parameter_name": "Mode"},
        "points": [{"time": 0, "display": "A"}, {"time": 16, "display": "C"}]})
    assert out["steps"] == 2


def test_clear_existing_and_read_back(mod):
    song, track = automation_song()
    i = inst(mod, song)
    target = {"mixer": "volume"}
    i._cmd_write_clip_automation({"track_index": 0, "clip_index": 0, "target": target,
                                  "points": [{"time": 0, "value": 0.5}]})
    i._cmd_write_clip_automation({"track_index": 0, "clip_index": 0, "target": target,
                                  "points": [{"time": 0, "value": 0.7}]})
    env = track.clip_slots[0].clip.envelopes["Track Volume"]
    assert len(env.steps) == 1
    read = i._cmd_get_clip_automation({"track_index": 0, "clip_index": 0, "target": target,
                                       "resolution": 8})
    assert read["has_envelope"] and read["samples"][0]["value"] == 0.7
    i._cmd_clear_clip_automation({"track_index": 0, "clip_index": 0})
    assert track.clip_slots[0].clip.envelopes == {}


# ------------------------------------------------------------------ groove, clips, scale

def test_groove_pool_round_trip(mod):
    song, track = automation_song()
    i = inst(mod, song)
    pool = i._cmd_get_groove_pool({})
    assert pool["grooves"][0]["base"] == "1/16"
    i._cmd_set_groove({"groove_index": 0, "timing": 0.7, "random": 0.0, "base": "1/8"})
    assert song.groove_pool.grooves[0].timing_amount == 0.7
    assert song.groove_pool.grooves[0].base == 1
    i._cmd_assign_groove({"track_index": 0, "clip_index": 0, "groove_index": 0})
    assert track.clip_slots[0].clip.groove.name == "MPC 16 Swing-58"
    i._cmd_assign_groove({"track_index": 0, "clip_index": 0})
    assert track.clip_slots[0].clip.groove is None
    assert i._cmd_set_groove_amount({"amount": 2})["global_amount"] == 1.3


def test_clip_properties_audio_vs_midi(mod):
    t = Track("Vox", slots=2, audio=True)
    t.clip_slots[0].clip = Clip("Chop", audio=True)
    t.clip_slots[1].clip = Clip("Keys")
    i = inst(mod, Song([t]))
    out = i._cmd_set_clip_properties({"track_index": 0, "clip_index": 0, "properties": {
        "pitch_coarse": -5, "warp_mode": "complex pro", "looping": False}})
    assert out["changed"] == {"pitch_coarse": -5, "warp_mode": 6, "looping": False}
    with pytest.raises(Exception, match="audio clips"):
        i._cmd_set_clip_properties({"track_index": 0, "clip_index": 1,
                                    "properties": {"pitch_coarse": 2}})


def test_song_scale(mod):
    song = Song()
    out = inst(mod, song)._cmd_set_song_scale({"root_note": "A", "scale_name": "Dorian",
                                               "scale_mode": True})
    assert out["root_name"] == "A" and out["scale_name"] == "Dorian" and out["scale_mode"]


def test_track_management_and_mixer_overview(mod):
    song = Song([Track("Kick"), Track("Bass")])
    i = inst(mod, song)
    assert i._cmd_create_return_track({"name": "Plate"})["return_index"] == 0
    assert i._cmd_duplicate_track({"track_index": 1, "name": "Bass B"})["new_index"] == 2
    overview = i._cmd_get_mixer_overview({})
    kinds = [(r["kind"], r["name"]) for r in overview["tracks"]]
    assert kinds == [("track", "Kick"), ("track", "Bass"), ("track", "Bass B"),
                     ("return", "Plate"), ("master", "Master")]
    i._cmd_delete_track({"track_index": 0, "track_type": "return"})
    assert song.return_tracks == []


def test_dispatch_routes_studio_commands(mod):
    song = Song([Track("A")])
    i = inst(mod, song)
    i.schedule_message = lambda delay, cb: cb()
    resp = i._process_command({"type": "set_song_scale", "params": {"root_note": "D"}})
    assert resp["status"] == "success" and resp["result"]["root_name"] == "D"
    resp = i._process_command({"type": "get_groove_pool", "params": {}})
    assert resp["result"]["grooves"][0]["name"] == "MPC 16 Swing-58"


# ------------------------------------------------------------------ render

class RenderClip(object):
    def __init__(self, start, path, start_marker=0.0, warping=False):
        self.start_time = start
        self.end_time = start + 40
        self.file_path = path
        self.name = "rec"
        self.start_marker = start_marker
        self.warping = warping
        self.sample_rate = 48000

    def beat_to_sample_time(self, beat):
        return beat * 0.5 * self.sample_rate  # 120 BPM


def render_setup(mod):
    song = Song([Track("Kick"), Track("Bass")])
    song.tracks[1].arm = True
    song.tracks[0].implicit_arm = True
    song.start_time = 10.0
    song.stop_all_clips = lambda quantized=True: None
    i = inst(mod, song)
    pending = []
    i.schedule_message = lambda delay, cb: pending.append(cb)

    def tick(n=1):
        for _ in range(n):
            batch = list(pending)
            del pending[:]
            for cb in batch:
                cb()
    return song, i, tick


def status(i):
    return i._cmd_get_render_status({})


def test_render_phases_record_and_restore(mod):
    song, i, tick = render_setup(mod)
    song.view.selected_track = song.tracks[0]
    job = i._cmd_start_render({"start_beat": 64, "end_beat": 96, "preroll_beats": 4,
                               "solo_tracks": [1]})
    render = song.tracks[-1]
    assert job["state"] == "preparing" and job["expected_seconds"] == 18.0
    assert render.name == "MCP Render" and not song.record_mode

    tick()  # preparing -> routed + configured -> positioning
    assert status(i)["state"] == "positioning"
    assert render.input_routing_type.display_name == "Resampling"
    assert render.arm and not render.mute and render.current_monitoring_state == 2
    assert song.tracks[1].arm is False and song.tracks[0].implicit_arm is False
    assert song.tracks[1].solo is True
    assert song.start_time == 60 and song.current_song_time == 60
    assert not song.loop and not song.metronome and song.back_to_arranger is False

    tick()  # positioning confirmed -> recording
    assert status(i)["state"] == "recording" and song.record_mode and song.is_playing
    song.current_song_time = 80
    tick()
    assert status(i)["state"] == "recording"
    song.current_song_time = 96.1
    tick()
    assert status(i)["state"] == "finalizing"
    render.arrangement_clips.append(RenderClip(60.0, "/tmp/rec.wav", start_marker=0.25))
    tick(4)
    st = i._cmd_get_render_status({"job_id": job["id"]})
    assert st["state"] == "done" and st["file_path"] == "/tmp/rec.wav"
    # unwarped: start_marker (s) + 4 beats of preroll at 120 BPM
    assert st["window_offset_s"] == 2.25
    assert st["window_seconds"] == 16.0
    assert "_saved" not in st and "_params" not in st
    # everything the user had is back; the take is muted so it never plays in the song
    assert song.loop and song.metronome and not song.record_mode and not song.is_playing
    assert song.tracks[1].arm is True and song.tracks[1].solo is False
    assert render.arm is False and render.mute is True
    assert song.current_song_time == 10.0 and song.start_time == 10.0
    assert song.view.selected_track is song.tracks[0]


def test_render_waits_for_routing_on_new_track(mod):
    song, i, tick = render_setup(mod)
    real = Track("x", audio=True).available_input_routing_types
    original_create = song.create_audio_track

    def create(index):
        original_create(index)
        song.tracks[-1].available_input_routing_types = []
    song.create_audio_track = create
    i._cmd_start_render({"start_beat": 0, "end_beat": 16})
    tick(3)
    assert status(i)["state"] == "preparing"
    song.tracks[-1].available_input_routing_types = real
    tick()
    assert status(i)["state"] == "positioning"


def test_render_routing_never_appears(mod):
    song, i, tick = render_setup(mod)
    song.tracks.append(Track("MCP Render", audio=True))
    song.tracks[-1].available_input_routing_types = [RoutingType("Ext. In")]
    i._cmd_start_render({"start_beat": 0, "end_beat": 16})
    tick(105)
    st = status(i)
    assert st["state"] == "error" and "Resampling" in st["error"]
    assert song.tracks[1].arm is True and song.loop is True and not song.record_mode


def test_render_warped_offset_uses_sample_time(mod):
    song, i, tick = render_setup(mod)
    i._cmd_start_render({"start_beat": 8, "end_beat": 16, "preroll_beats": 4})
    tick(2)
    song.current_song_time = 16.5
    tick()
    song.tracks[-1].arrangement_clips.append(RenderClip(4.0, "/tmp/w.wav", start_marker=1.0, warping=True))
    tick(4)
    # (start_marker 1 + 4 beats) at 0.5 s per beat
    assert status(i)["window_offset_s"] == 2.5


def test_render_reuses_track_and_refuses_overlap(mod):
    song, i, tick = render_setup(mod)
    i._cmd_start_render({"start_beat": 0, "end_beat": 16})
    with pytest.raises(Exception, match="already running"):
        i._cmd_start_render({"start_beat": 0, "end_beat": 16})
    i._cmd_cancel_render({})
    count = len(song.tracks)
    i._cmd_start_render({"start_beat": 0, "end_beat": 16})
    assert len(song.tracks) == count


def test_render_errors_if_playback_stops(mod):
    song, i, tick = render_setup(mod)
    i._cmd_start_render({"start_beat": 0, "end_beat": 64})
    tick(2)
    song.is_playing = False
    tick(12)
    st = status(i)
    assert st["state"] == "error" and "stopped" in st["error"]
    assert song.loop is True


# ------------------------------------------------------------------ review fixes

def test_duplicate_track_uses_selected_copy(mod):
    song = Song([Track("Group"), Track("Child"), Track("Other")])

    def dup(index):
        song.tracks.insert(2, Track("Group copy"))  # lands after the child
        song.view.selected_track = song.tracks[2]
    song.duplicate_track = dup
    out = inst(mod, song)._cmd_duplicate_track({"track_index": 0, "name": "Group B"})
    assert out["new_index"] == 2 and song.tracks[2].name == "Group B"


def test_clip_properties_moves_range_later_end_first(mod):
    order = []

    class OrderedClip(Clip):
        def __setattr__(self, key, value):
            if key in ("loop_start", "loop_end"):
                order.append(key)
            object.__setattr__(self, key, value)
    t = Track("Loop", slots=1)
    t.clip_slots[0].clip = OrderedClip("Loop", 4.0)
    del order[:]
    inst(mod, Song([t]))._cmd_set_clip_properties({"track_index": 0, "clip_index": 0,
                                                   "properties": {"loop_start": 8, "loop_end": 12}})
    assert order == ["loop_end", "loop_start"]


def test_automation_rejects_arrangement_clips(mod):
    song, track = automation_song()
    with pytest.raises(Exception, match="Arrangement"):
        inst(mod, song)._cmd_write_clip_automation({
            "track_index": 0, "clip_index": 0, "arrangement": True,
            "target": {"mixer": "volume"}, "points": [{"time": 0, "value": 0.5}]})


def test_load_groove_from_core_library_and_reuse(mod):
    class Item(object):
        def __init__(self, name, children=(), folder=False):
            self.name = name
            self.children = list(children)
            self.is_folder = folder

    class Browser(object):
        packs = Item("packs", [Item("Core Library", [Item("Grooves", [
            Item("Swing", [Item("MPC 16 Swing-62.agr")], folder=True)], folder=True)], folder=True)])
        user_library = Item("user")
        current_project = Item("proj")

        def load_item(self, item):
            song.groove_pool.grooves.append(Groove(item.name[:-4]))

    song, track = automation_song()
    i = inst(mod, song, Browser())
    out = i._cmd_load_groove({"name": "MPC 16 Swing-62", "track_index": 0, "clip_index": 0})
    assert out["groove_index"] == 1 and out["applied_to_clip"] == "MPC 16 Swing-62"
    again = i._cmd_load_groove({"name": "mpc 16 swing-62.agr"})
    assert again["loaded"] == "(already in pool)" and len(song.groove_pool.grooves) == 2


def test_pan_display_values(mod):
    p = mod.AbletonMCP._parse_quantity
    assert p("50L") == (-50.0, "pan") and p("25 R") == (25.0, "pan") and p("C") == (0.0, "pan")
    i = inst(mod, Song())
    pan = Param("Pan", 0.0, -1.0, 1.0,
                lambda v: "C" if abs(v) < 0.005 else ("%dL" % round(-v * 50) if v < 0 else "%dR" % round(v * 50)))
    assert pan.str_for_value(i._value_for_display(pan, "20L")) == "20L"


def test_sidechain_matches_attached_track(mod):
    kick = Track("Kick")
    comp = Device("Compressor", [Param("S/C On", 0, 0, 1, items=["Off", "On"])])
    a, b = RoutingType("Kick"), RoutingType("Kick")
    a.attached_object, b.attached_object = Track("Kick"), kick  # two tracks named Kick
    comp.available_input_routing_types = [a, b]
    comp.available_input_routing_channels = []
    comp.input_routing_type = None
    song = Song([kick, Track("Bass", devices=[comp])])
    inst(mod, song)._cmd_set_sidechain({"track_index": 1, "device_index": 0, "source_track_index": 0})
    assert comp.input_routing_type is b
