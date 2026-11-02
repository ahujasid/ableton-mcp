"""Remote Script side of the mixer, routing, monitoring, meter and automation
commands, against fake Live objects. Every refusal is checked to have changed
nothing (song.history stays empty)."""

import pytest

from live_fakes import FakeDevice, FakeParameter, FakeSong, load_script_module, make_script


@pytest.fixture(scope="module")
def script_module():
    return load_script_module()


@pytest.fixture
def song():
    return FakeSong()


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


# ------------------------------------------------------------------ get_mixer_state

def test_mixer_state_covers_tracks_returns_and_master(script):
    st = ok(script, "get_mixer_state")
    assert [t["name"] for t in st["tracks"]] == ["1-Audio", "2-MIDI"]
    assert [t["name"] for t in st["returns"]] == ["A-Reverb", "B-Delay"]
    assert st["master"]["name"] == "Main"


def test_mixer_state_track_fields(script):
    t = ok(script, "get_mixer_state")["tracks"][0]
    assert t["volume"]["display"] == "0.0 dB" and t["volume"]["value"] == 0.85
    assert t["panning"]["display"] == "C"
    assert t["monitoring"] == "auto" and t["arm"] is False
    assert [s["return_name"] for s in t["sends"]] == ["A-Reverb", "B-Delay"]
    assert t["routing"] == {"input_type": "Ext. In", "input_channel": "1/2",
                            "output_type": "Master", "output_channel": "Track In"}
    assert "unavailable" not in t


def test_return_input_routing_is_null_with_a_reason_not_a_value(script):
    r = ok(script, "get_mixer_state")["returns"][0]
    assert r["routing"]["input_type"] is None
    assert "input_type" in r["routing"]["unavailable"]
    assert r["routing"]["output_type"] == "Master"


def test_master_has_no_mute_solo_or_sends_fields(script):
    m = ok(script, "get_mixer_state")["master"]
    assert "mute" not in m and "solo" not in m and "sends" not in m
    assert m["volume"]["display"] == "0.0 dB"


def test_solo_summary_lists(script, song):
    song.tracks[0]._solo = True
    song.tracks[1].muted_via_solo = True
    st = ok(script, "get_mixer_state")
    assert st["soloed"] == ["1-Audio"]
    assert st["silenced_by_solo"] == ["2-MIDI"]


def test_mixer_state_without_routing(script):
    t = ok(script, "get_mixer_state", include_routing=False)["tracks"][0]
    assert "routing" not in t


# ------------------------------------------------------------------ routing

def test_get_track_routing_lists_choices(script):
    r = ok(script, "get_track_routing", track_index=0)
    assert r["input_type"] == "Ext. In"
    assert "3/4" in r["available_input_channel"]
    assert r["available_output_type"] == ["Master", "Ext. Out", "Sends Only"]
    assert r["monitoring"] == "auto"


def test_set_routing_type_then_channel(script, song):
    r = ok(script, "set_track_routing", track_index=0, output_type="Ext. Out", output_channel="3")
    assert r["changed"] == ["output_type", "output_channel"]
    assert r["before"]["output_type"] == "Master"
    assert r["after"]["output_type"] == "Ext. Out" and r["after"]["output_channel"] == "3"


def test_set_routing_matches_case_insensitively(script, song):
    ok(script, "set_track_routing", track_index=0, input_type="ext. in", input_channel="3/4")
    assert song.tracks[0].input_routing_channel.display_name == "3/4"


def test_unknown_routing_name_lists_choices_and_changes_nothing(script, song):
    msg = err(script, "set_track_routing", track_index=0, input_channel="7/8")
    assert "'3/4'" in msg and "Choices" in msg
    assert song.history == []


def test_set_routing_needs_a_field(script, song):
    assert "at least one" in err(script, "set_track_routing", track_index=0)


def test_return_track_output_routing(script, song):
    ok(script, "set_track_routing", track_type="return", track_index=1, output_type="Ext. Out")
    assert song.return_tracks[1].output_routing_type.display_name == "Ext. Out"


# ------------------------------------------------------------------ monitoring

@pytest.mark.parametrize("state,value", [("in", 0), ("Auto", 1), ("OFF", 2)])
def test_set_monitoring(script, song, state, value):
    r = ok(script, "set_track_monitoring", track_index=1, state=state)
    assert song.tracks[1].current_monitoring_state == value
    assert r["before"] == "auto"


def test_bad_monitoring_state_is_refused(script, song):
    assert "in, auto, off" in err(script, "set_track_monitoring", track_index=0, state="on")
    assert song.history == []


def test_monitoring_on_return_is_refused(script, song):
    assert "regular tracks" in err(script, "set_track_monitoring", track_type="return", track_index=0,
                                   state="in")


# ------------------------------------------------------------------ set_track_mixer

def test_set_volume_db_finds_the_fader_value(script, song):
    r = ok(script, "set_track_mixer", track_index=0, volume_db=-6)
    assert r["after"]["volume"]["display"] == "-6.0 dB"
    assert r["before"]["volume"]["display"] == "0.0 dB"
    assert 0 < song.tracks[0].mixer_device.volume.value < 0.85


def test_volume_db_minus_inf_and_above_max(script, song):
    ok(script, "set_track_mixer", track_index=0, volume_db=float("-inf"))
    assert song.tracks[0].mixer_device.volume.value == 0.0
    assert "maximum" in err(script, "set_track_mixer", track_index=0, volume_db=12)


def test_volume_and_volume_db_together_are_refused(script, song):
    assert "not both" in err(script, "set_track_mixer", track_index=0, volume=0.5, volume_db=-6)
    assert song.history == []


def test_set_pan_sends_mute(script, song):
    r = ok(script, "set_track_mixer", track_index=1, panning=-0.5, sends={"A": 0.3, "1": 0.2},
           mute=True)
    t = song.tracks[1]
    assert t.mixer_device.panning.value == -0.5
    assert [s.value for s in t.mixer_device.sends] == [0.3, 0.2]
    assert t.mute is True
    assert r["after"]["panning"]["display"] == "25L"


def test_send_by_return_name(script, song):
    ok(script, "set_track_mixer", track_index=0, sends={"B-Delay": 0.7})
    assert song.tracks[0].mixer_device.sends[1].value == 0.7


def test_a_bad_field_writes_nothing_at_all(script, song):
    """Validation happens before any write: a good volume plus a bad pan changes nothing."""
    assert "outside" in err(script, "set_track_mixer", track_index=0, volume=0.5, panning=3)
    assert "out of range" in err(script, "set_track_mixer", track_index=0, mute=True, sends={"C": 0.1})
    assert song.history == []


def test_solo_is_not_exclusive_by_default(script, song):
    song.tracks[1]._solo = True
    r = ok(script, "set_track_mixer", track_index=0, solo=True)
    assert song.tracks[1].solo is True
    assert any("exclusive_solo" in n for n in r["notes"])


def test_exclusive_solo_unsolos_the_others(script, song):
    song.tracks[1]._solo = True
    song.return_tracks[0]._solo = True
    r = ok(script, "set_track_mixer", track_index=0, solo=True, exclusive_solo=True)
    assert song.tracks[0].solo and not song.tracks[1].solo and not song.return_tracks[0].solo
    assert sorted(r["notes"]) == ["unsoloed 2-MIDI", "unsoloed A-Reverb"]


def test_master_has_no_mute_or_sends(script, song):
    assert "no mute" in err(script, "set_track_mixer", track_type="master", mute=True)
    assert "no sends" in err(script, "set_track_mixer", track_type="master", sends={"A": 0.1})
    assert song.history == []


def test_master_volume(script, song):
    ok(script, "set_track_mixer", track_type="master", volume_db=-3)
    assert str(song.master_track.mixer_device.volume) == "-3.0 dB"


def test_return_cannot_be_armed(script, song):
    assert "cannot be armed" in err(script, "set_track_mixer", track_type="return", track_index=0, arm=True)


def test_nothing_to_set_is_refused(script):
    assert "Nothing to set" in err(script, "set_track_mixer", track_index=0)


# ------------------------------------------------------------------ meters

def test_meters_report_peaks_and_signal(script, song):
    song.tracks[0].output_meter_level = 0.6
    r = ok(script, "get_track_meters", tracks=[{"track_index": 0}, {"track_index": 1}], duration_ms=0)
    a, b = r["tracks"]
    assert a["output_signal"] is True and a["peaks"]["output_meter_level"] == 0.6
    assert b["output_signal"] is False and b["input_signal"] is False


def test_missing_meters_are_unknown_not_silent(script, song):
    r = ok(script, "get_track_meters", tracks=[{"track_type": "return", "track_index": 0}], duration_ms=0)
    ret = r["tracks"][0]
    assert ret["input_signal"] is None
    assert ret["peaks"]["input_meter_level"] is None
    assert "input_meter_level" in ret["unavailable"]
    assert ret["output_signal"] is False


def test_meters_default_to_every_track(script):
    r = ok(script, "get_track_meters", duration_ms=0)
    assert [(t["track_type"], t["index"]) for t in r["tracks"]] == [
        ("track", 0), ("track", 1), ("return", 0), ("return", 1), ("master", 0)]


def test_meter_duration_is_capped(script, monkeypatch, script_module):
    clock = {"t": 0.0}
    monkeypatch.setattr(script_module.time, "time", lambda: clock["t"])
    monkeypatch.setattr(script_module.time, "sleep", lambda s: clock.__setitem__("t", clock["t"] + s))
    r = ok(script, "get_track_meters", tracks=[{"track_index": 0}], duration_ms=999999, interval_ms=1000)
    assert r["duration_ms"] == script_module.MAX_METER_DURATION_MS
    assert r["samples"] == 11  # one at t=0, then one per second up to 10 s


# ------------------------------------------------------------------ arrangement / automation

def test_back_to_arrangement_only_acts_when_lit(script, song):
    assert ok(script, "back_to_arrangement") == {"was_lit": False, "back_to_arranger": False}
    assert song.history == []
    song._back_to_arranger = True
    assert ok(script, "back_to_arrangement") == {"was_lit": True, "back_to_arranger": False}


def _override(song):
    song.tracks[1].mixer_device.volume.automation_state = 2
    p = FakeParameter("Cutoff", history=song.h)
    p.automation_state = 2
    q = FakeParameter("Resonance", history=song.h)
    q.automation_state = 1
    song.tracks[0].devices = [FakeDevice("Auto Filter", [p, q])]
    song.re_enable_automation_enabled = True


def test_automation_overrides_lists_overridden_only(script, song):
    _override(song)
    r = ok(script, "get_automation_overrides")
    assert r["overridden_count"] == 2
    assert {(x["track"], x["parameter"]) for x in r["parameters"]} == {
        ("1-Audio", "Cutoff"), ("2-MIDI", "Track Volume")}
    assert r["re_enable_automation_enabled"] is True


def test_automation_overrides_include_playing(script, song):
    _override(song)
    r = ok(script, "get_automation_overrides", include_playing=True)
    assert len(r["parameters"]) == 3 and r["overridden_count"] == 2


def test_re_enable_automation_whole_song(script, song):
    _override(song)
    r = ok(script, "re_enable_automation")
    assert r == {"scope": "song", "was_enabled": True}
    assert song.history == [("song.re_enable_automation",)]


def test_re_enable_automation_one_track(script, song):
    _override(song)
    r = ok(script, "re_enable_automation", track_index=0)
    assert r["re_enabled"] == ["0:Auto Filter / Cutoff"]
    assert song.tracks[1].mixer_device.volume.automation_state == 2  # other track untouched
