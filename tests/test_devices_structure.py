"""Remote Script side of the 1.9.0 commands: set info, device chain and
parameters by display value, device on/off, sidechain routing, delete/move
device, signal path, clip info/properties, scenes, duplicate/return tracks,
track look, and one undo step per write. Refusals must change nothing."""

import pytest

from live_fakes import (FakeChain, FakeClip, FakeClipSlot, FakeDevice, FakeParameter,
                        FakeSidechainDevice, FakeSong, load_script_module, make_script, utility)


@pytest.fixture(scope="module")
def script_module():
    return load_script_module()


@pytest.fixture
def song():
    s = FakeSong(track_names=("1-Audio", "2-MIDI", "3-Audio"))
    t = s.tracks[0]
    t.devices = [utility(s.h, gain=-30.0, automated=1), FakeSidechainDevice("Compressor", [
        FakeParameter("Threshold", -20.0, -60.0, 0.0, history=s.h, kind="db_linear")], s.h)]
    inner = FakeDevice("Saturator", [FakeParameter("Drive", 5.0, 0.0, 36.0, history=s.h, kind="db_linear")], s.h)
    t.devices.append(FakeDevice("FX Rack", [], s.h, class_name="AudioEffectGroupDevice",
                                chains=[FakeChain("Dry", [], s.h), FakeChain("Wet", [inner], s.h)]))
    t.clip_slots = [FakeClipSlot(FakeClip("take 1", s.h)), FakeClipSlot()]
    t.arrangement_clips = [FakeClip("arr take", s.h, arrangement=True)]
    s.tracks[1].clip_slots = [FakeClipSlot(FakeClip("beat", s.h, audio=False)), FakeClipSlot()]
    return s


@pytest.fixture
def script(script_module, song):
    return make_script(script_module, song)


def run(script, command, **params):
    return script._process_command({"type": command, "params": params})


def ok(script, command, **params):
    reply = run(script, command, **params)
    assert reply["status"] == "success", reply
    return reply["result"]


def err(script, command, **params):
    reply = run(script, command, **params)
    assert reply["status"] == "error", reply
    return reply["message"]


# ------------------------------------------------------------------ undo steps

def test_each_write_is_one_undo_step(script, song):
    ok(script, "set_device_active", track_index=0, device="0", active=False)
    ok(script, "set_scene", scene_index=0, name="Verse")
    assert song.undo_steps == ["begin", "end", "begin", "end"]


def test_a_refused_write_still_closes_its_undo_step(script, song):
    err(script, "set_scene", scene_index=0)
    assert song.undo_steps == ["begin", "end"]


def test_reads_and_undo_open_no_undo_step(script, song):
    song.undo_depth = 1
    ok(script, "get_device_chain", track_index=0)
    ok(script, "undo")
    assert song.undo_steps == []


# ------------------------------------------------------------------ set info

def test_set_info_new_set_is_not_saved(script, song):
    info = ok(script, "get_set_info")
    assert info["is_saved"] is False and info["file_path"] == ""
    assert info["track_count"] == 3 and info["scene_count"] == 2


def test_set_info_saved_set(script, song):
    song.file_path = "Z:\\home\\jeremy\\Songs\\Song.als"
    assert ok(script, "get_set_info")["is_saved"] is True


# ------------------------------------------------------------------ device chain

def test_device_chain_lists_devices_with_display_and_automation(script):
    chain = ok(script, "get_device_chain", track_index=0)["devices"]
    assert [d["name"] for d in chain] == ["Utility", "Compressor", "FX Rack"]
    gain = next(p for p in chain[0]["parameters"] if p["name"] == "Gain")
    assert gain["display"] == "-30.0 dB" and gain["automation"] == "playing"
    assert chain[0]["device_on"] is True and chain[0]["type"] == "audio_effect"
    on = chain[0]["parameters"][0]
    assert on["name"] == "Device On" and on["value_items"] == ["Off", "On"]


def test_device_chain_opens_racks_and_shows_sidechain(script):
    chain = ok(script, "get_device_chain", track_index=0)["devices"]
    assert chain[1]["sidechain"] == {"input_type": "No Input", "input_channel": None}
    wet = chain[2]["chains"][1]
    assert wet["name"] == "Wet" and wet["devices"][0]["path"] == "2/1/0"
    assert wet["devices"][0]["name"] == "Saturator"


def test_device_chain_depth_zero_counts_rack_devices(script):
    chain = ok(script, "get_device_chain", track_index=0, max_depth=0, include_parameters=False)["devices"]
    assert chain[2]["chains"][1] == {"index": 1, "name": "Wet", "mute": False, "solo": False, "device_count": 1}
    assert "parameters" not in chain[0]


def test_max_parameters_truncates(script):
    d = ok(script, "get_device_chain", track_index=0, max_parameters=1)["devices"][0]
    assert len(d["parameters"]) == 1 and d["parameters_truncated"] is True and d["parameter_count"] == 3


# ------------------------------------------------------------------ set parameter

def test_set_parameter_by_display_value(script, song):
    r = ok(script, "set_device_parameter_value", track_index=0, device="0", parameter="Gain",
           display_value="+15 dB")
    assert abs(song.tracks[0].devices[0].parameters[1].value - 15.0) < 0.06
    assert r["after"]["display"] == "15.0 dB" and r["before"]["display"] == "-30.0 dB"


def test_setting_an_automated_parameter_says_it_overrides_automation(script):
    r = ok(script, "set_device_parameter_value", track_index=0, device="0", parameter="gain", value=10.0)
    assert r["notes"] and "overrides its automation" in r["notes"][0]


def test_set_parameter_inside_a_rack_by_path(script, song):
    ok(script, "set_device_parameter_value", track_index=0, device="2/1/0", parameter="Drive", value=12.0)
    assert song.tracks[0].devices[2].chains[1].devices[0].parameters[1].value == 12.0


def test_set_quantized_parameter_by_item_name(script, song):
    ok(script, "set_device_parameter_value", track_index=0, device="1", parameter="Device On",
       display_value="Off")
    assert song.tracks[0].devices[1].is_active is False


@pytest.mark.parametrize("kwargs, msg", [
    (dict(parameter="Gain", display_value="+50 dB"), "outside"),
    (dict(parameter="Gain", value=99.0), "outside"),
    (dict(parameter="Nope", value=1.0), "No parameter"),
    (dict(parameter="Gain"), "exactly one"),
    (dict(parameter="Gain", value=1.0, display_value="1 dB"), "exactly one"),
    (dict(parameter="Gain", value=1.0, expected_device_name="EQ Eight"), "does not match"),
    (dict(parameter="Device On", display_value="Maybe"), "is not one of"),
])
def test_bad_parameter_writes_change_nothing(script, song, kwargs, msg):
    assert msg in err(script, "set_device_parameter_value", track_index=0, device="0", **kwargs)
    assert song.history == []


@pytest.mark.parametrize("path, msg", [("7", "out of range"), ("2/5/0", "chain 5"), ("2/1", "use 'd'"),
                                        ("x", "not a number")])
def test_bad_device_paths_are_refused(script, song, path, msg):
    assert msg in err(script, "set_device_active", track_index=0, device=path, active=False)
    assert song.history == []


def test_disabled_parameter_is_refused(script, song):
    song.tracks[0].devices[0].parameters[1].is_enabled = False
    assert "disabled" in err(script, "set_device_parameter_value", track_index=0, device="0",
                             parameter="Gain", value=0.0)
    assert song.history == []


# ------------------------------------------------------------------ on/off, routing

def test_set_device_active_toggles_device_on(script, song):
    r = ok(script, "set_device_active", track_index=0, device="0", active=False)
    assert r == {"track": "1-Audio", "device": "0", "device_name": "Utility", "was_on": True,
                 "device_on": False, "is_active": False}


def test_sidechain_routing_by_name(script, song):
    r = ok(script, "set_device_routing", track_index=0, device="1", input_type="Ext. In", input_channel="3/4")
    assert r["after"] == {"input_type": "Ext. In", "input_channel": "3/4"}
    full = ok(script, "get_device_routing", track_index=0, device="1")
    assert full["has_routing"] and "1-Audio" in full["routing"]["available_input_type"]


def test_sidechain_wrong_name_lists_choices(script, song):
    msg = err(script, "set_device_routing", track_index=0, device="1", input_type="Kick")
    assert "Choices" in msg and "'Ext. In'" in msg
    assert song.history == []


def test_device_without_sidechain(script, song):
    assert ok(script, "get_device_routing", track_index=0, device="0")["has_routing"] is False
    assert "no input" in err(script, "set_device_routing", track_index=0, device="0", input_type="Ext. In")


# ------------------------------------------------------------------ delete/move device

def test_delete_device_needs_matching_name(script, song):
    assert "does not match" in err(script, "delete_device", track_index=0, device="0",
                                   expected_device_name="Compressor")
    assert "expected_device_name" in err(script, "delete_device", track_index=0, device="0")
    assert song.history == []
    r = ok(script, "delete_device", track_index=0, device="0", expected_device_name="Utility")
    assert r["remaining"] == ["Compressor", "FX Rack"]


def test_delete_device_inside_a_rack(script, song):
    ok(script, "delete_device", track_index=0, device="2/1/0", expected_device_name="Saturator")
    assert song.tracks[0].devices[2].chains[1].devices == []


def test_move_device_to_another_track(script, song):
    r = ok(script, "move_device", track_index=0, device="0", target_track_index=2, target_index=0)
    assert r["to_track"] == "3-Audio" and r["devices"] == ["Utility"]
    assert [d.name for d in song.tracks[0].devices] == ["Compressor", "FX Rack"]


def test_move_device_out_of_range_target(script, song):
    assert "out of range" in err(script, "move_device", track_index=0, device="0", target_index=9)
    assert song.history == []


# ------------------------------------------------------------------ signal path

def test_signal_path_reports_automated_gain_and_listeners(script, song):
    song.tracks[2]._in_type = type(song.tracks[2]._in_type)("1-Audio")
    sp = ok(script, "get_signal_path", track_index=0)
    assert [d["name"] for d in sp["devices"]] == ["Utility", "Compressor", "FX Rack"]
    assert sp["devices"][0]["gain_parameters"][0]["display"] == "-30.0 dB"
    assert any("Gain is automated" in p for p in sp["problems"])
    assert sp["fed_to_tracks"] == [{"track_index": 2, "name": "3-Audio", "input_channel": "1/2"}]
    assert "Track Delay" in sp["not_visible_to_the_api"]


def test_signal_path_problems(script, song):
    t = song.tracks[0]
    t._mute = True
    t.devices[1].parameters[0]._value = 0.0
    t._out_type = type(t._out_type)("Sends Only")
    p = ok(script, "get_signal_path", track_index=0)["problems"]
    assert "track is muted" in p
    assert any("'Compressor' is switched off" in x for x in p)
    assert any("Sends Only" in x for x in p)
    assert any("Auto and the track is not armed" in x for x in p)


def test_signal_path_with_meters(script, song):
    song.tracks[0].output_meter_left = 0.5
    sp = ok(script, "get_signal_path", track_index=0, meter_ms=30)
    assert sp["meters"]["tracks"][0]["output_signal"] is True


def test_signal_path_on_master(script):
    sp = ok(script, "get_signal_path", track_type="master")
    assert sp["track"]["name"] == "Main" and sp["fed_to_tracks"] == []


# ------------------------------------------------------------------ clips

def test_clip_info_audio(script):
    c = ok(script, "get_clip_info", track_index=0, clip_index=0)
    assert c["name"] == "take 1" and c["gain_display"] == "0.0 dB" and c["warp_mode_name"] == "Beats"
    a = ok(script, "get_clip_info", track_index=0, arrangement_index=0)
    assert a["name"] == "arr take" and a["where"] == "arrangement 0" and "start_time" in a


def test_clip_info_errors(script):
    assert "empty" in err(script, "get_clip_info", track_index=0, clip_index=1)
    assert "out of range" in err(script, "get_clip_info", track_index=0, arrangement_index=4)
    assert "regular tracks" in err(script, "get_clip_info", track_type="master", clip_index=0)


def test_set_clip_gain_db_and_loop(script, song):
    r = ok(script, "set_clip_properties", track_index=0, clip_index=0, gain_db=6.0, loop_end=2.0, muted=True)
    assert r["after"]["gain_display"] == "6.0 dB" and r["after"]["loop_end"] == 2.0 and r["after"]["muted"]


def test_moving_loop_later_writes_end_first(script, song):
    ok(script, "set_clip_properties", track_index=0, clip_index=0, loop_start=6.0, loop_end=8.0)
    c = song.tracks[0].clip_slots[0].clip
    assert (c.loop_start, c.loop_end) == (6.0, 8.0)


@pytest.mark.parametrize("kwargs, msg", [
    (dict(track_index=1, clip_index=0, gain=0.5), "only exist on audio clips"),
    (dict(track_index=1, clip_index=0, gain_db=3.0), "only exists on audio clips"),
    (dict(track_index=0, clip_index=0, gain=2.0), "outside 0..1"),
    (dict(track_index=0, clip_index=0, gain_db=40.0), "outside this clip's gain range"),
    (dict(track_index=0, clip_index=0, pitch_coarse=60), "-48..48"),
    (dict(track_index=0, clip_index=0), "Nothing to set"),
])
def test_bad_clip_writes_change_nothing(script, song, kwargs, msg):
    before = song.tracks[0].clip_slots[0].clip.gain
    assert msg in err(script, "set_clip_properties", **kwargs)
    assert [e for e in song.history if e[1] != "gain"] == []
    assert song.tracks[0].clip_slots[0].clip.gain == before


# ------------------------------------------------------------------ scenes, tracks

def test_scene_lifecycle(script, song):
    assert len(ok(script, "get_scenes")["scenes"]) == 2
    r = ok(script, "create_scene", index=-1)
    assert r["index"] == 2 and r["scene_count"] == 3
    ok(script, "set_scene", scene_index=2, name="Chorus", tempo=128)
    assert song.scenes[2].name == "Chorus" and song.scenes[2].tempo_enabled is True
    dup = ok(script, "duplicate_scene", scene_index=2)
    assert dup["name"] == "Chorus" and dup["index"] == 3
    ok(script, "delete_scene", scene_index=3, expected_name="Chorus")
    assert len(song.scenes) == 3


def test_delete_scene_guards(script, song):
    assert "does not match" in err(script, "delete_scene", scene_index=0, expected_name="Verse")
    song.scenes[0].__dict__["is_empty"] = False
    assert "has clips" in err(script, "delete_scene", scene_index=0, expected_name="")
    song.scenes[:] = song.scenes[:1]
    assert "last one" in err(script, "delete_scene", scene_index=0, expected_name="", allow_clips=True)
    assert [e for e in song.history if e[0] == "delete_scene"] == []


def test_bad_scene_tempo_writes_nothing(script, song):
    assert "20..999" in err(script, "set_scene", scene_index=0, name="X", tempo=5)
    assert song.history == []


def test_fire_scene(script, song):
    ok(script, "fire_scene", scene_index=1)
    assert ("scene.fire", "") in song.history


def test_duplicate_track_and_return(script, song):
    r = ok(script, "duplicate_track", track_index=1)
    assert r["new_index"] == 2 and r["new_name"] == "2-MIDI copy" and r["track_count"] == 4
    assert ok(script, "create_return_track")["return_track_count"] == 3
    assert "regular tracks" in err(script, "duplicate_track", track_index=0, track_type="return")


def test_track_look(script, song):
    r = ok(script, "set_track_look", track_index=0, color_index=12)
    assert r["color_index"] == 12
    assert "not a group track" in err(script, "set_track_look", track_index=0, folded=True)
    assert "0..69" in err(script, "set_track_look", track_index=0, color_index=70)
    song.tracks[1].is_foldable = True
    assert ok(script, "set_track_look", track_index=1, folded=True)["folded"] is True


def test_mixer_state_has_group_and_colour(script, song):
    song.tracks[2].is_grouped = True
    song.tracks[2].group_track = song.tracks[1]
    t = ok(script, "get_mixer_state", include_routing=False)["tracks"]
    assert t[2]["group_track"] == "2-MIDI" and t[0]["color_index"] == 0
