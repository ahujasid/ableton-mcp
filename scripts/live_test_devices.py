#!/usr/bin/env python3
"""Live test for the 1.9.0 tools: set info, safety switches, undo steps, device
chain and parameters by display value, device on/off, sidechain routing,
move/delete device, signal path, clip info and properties (MIDI and audio),
scenes, duplicate track, return track, track colour.

Runs only against an EMPTY Live set (File > New Live Set). Creates its own
tracks (mcp-test-*), scenes (mcp-test-*) and one return track, writes only to
those, and deletes them at the end. Nothing plays.

usage: python3 scripts/live_test_devices.py [--keep] [--force]
"""
import math
import os
import struct
import sys
import wave

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from live_harness import TEST_PREFIX, check, expect_error, find_track, run, step  # noqa: E402

AUDIO = TEST_PREFIX + "-dev"
MIDI = TEST_PREFIX + "-midi"
TONE = "/tmp/claude/mcp-test-tone.wav"


def write_tone(path, seconds=2.0, rate=48000, freq=220.0, level=0.25):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        frames = b"".join(struct.pack("<h", int(level * 32767 * math.sin(2 * math.pi * freq * i / rate)))
                          for i in range(int(seconds * rate)))
        w.writeframes(frames)


def device_names(m, idx):
    return [d["name"] for d in m.tool("get_device_chain", track_index=idx, include_parameters=False)["devices"]]


def param(chain_dev, name):
    return next(p for p in chain_dev["parameters"] if p["name"] == name)


def body(m, args):
    print("\n[set info]")
    info = step("get_set_info", lambda: m.tool("get_set_info"))
    check("a new set is not saved", bool(info) and info.get("is_saved") is False, info)

    print("\n[safety switches]")
    sc = step("get_safety_config", lambda: m.tool("get_safety_config"))
    check("safety config readable", bool(sc) and "delete" in sc.get("categories", {}), sc)
    m.set_safety({"read_only": True})
    expect_error("read_only refuses create_audio_track", lambda: m.text("create_audio_track", index=-1),
                 "read_only")
    m.set_safety({"allow": {"structure": False}})
    expect_error("structure off refuses create_scene", lambda: m.tool("create_scene", index=-1), "structure")
    m.set_safety({"saved_set_allow": {"delete": False}})

    print("\n[tracks]")
    before = m.tool("get_session_info")["track_count"]
    step("create audio track", lambda: m.text("create_audio_track", index=-1))
    a = before
    step("name it", lambda: m.text("set_track_name", track_index=a, name=AUDIO))
    step("create midi track", lambda: m.text("create_midi_track", index=-1))
    mi = before + 1
    step("name it", lambda: m.text("set_track_name", track_index=mi, name=MIDI))
    if not check("both test tracks exist", find_track(m, AUDIO) == a and find_track(m, MIDI) == mi):
        return
    T = {"track_index": a}

    print("\n[undo step per call]")
    step("set_track_look colour 5", lambda: m.tool("set_track_look", color_index=5, **T))
    step("set_track_look colour 9", lambda: m.tool("set_track_look", color_index=9, **T))
    step("undo once", lambda: m.tool("undo"))
    st = m.tool("get_mixer_state", include_routing=False)
    me = next(t for t in st["tracks"] if t["index"] == a)
    check("one undo reverts exactly one call (colour back to 5)", me.get("color_index") == 5, me.get("color_index"))

    print("\n[devices]")
    step("load Utility", lambda: m.text("load_instrument_or_effect", track_index=a, uri="query:AudioFx#Utility"))
    step("load Compressor", lambda: m.text("load_instrument_or_effect", track_index=a,
                                            uri="query:AudioFx#Compressor"))
    names = device_names(m, a)
    check("Utility then Compressor on the track", names[:2] == ["Utility", "Compressor"], names)
    chain = step("get_device_chain", lambda: m.tool("get_device_chain", **T))
    if chain and len(chain["devices"]) >= 2:
        u = chain["devices"][0]
        check("device_on read", u.get("device_on") is True, u)
        g = param(u, "Gain")
        print("    Utility Gain: %s (raw %s, %s..%s)" % (g["display"], g["value"], g["min"], g["max"]))
        check("Gain has dB display text", "dB" in g["display"], g)
        check("automation state read", g.get("automation") == "none", g)
        on = u["parameters"][0]
        check("parameter 0 is Device On with items", on["name"] == "Device On" and on.get("value_items"), on)

    r = step("Gain to +15 dB by display", lambda: m.tool("set_device_parameter_value", device="0",
                                                          parameter="Gain", display_value="+15 dB", **T))
    check("Gain shows 15.0 dB", bool(r) and r["after"]["display"].startswith("15.0"), r and r["after"])
    r = step("Gain to -6 dB", lambda: m.tool("set_device_parameter_value", device="0", parameter="Gain",
                                               display_value="-6 dB", expected_device_name="Utility", **T))
    check("Gain shows -6.0 dB", bool(r) and r["after"]["display"].startswith("-6.0"), r and r["after"])
    step("undo the -6 dB", lambda: m.tool("undo"))
    u = m.tool("get_device_chain", **T)["devices"][0]
    check("undo put Gain back to 15.0 dB", param(u, "Gain")["display"].startswith("15.0"), param(u, "Gain"))
    expect_error("+99 dB refused", lambda: m.tool("set_device_parameter_value", device="0", parameter="Gain",
                                                  display_value="+99 dB", **T), "outside")
    expect_error("unknown parameter lists names", lambda: m.tool("set_device_parameter_value", device="0",
                                                                 parameter="Nope", value=0, **T), "Parameters:")

    r = step("Utility off", lambda: m.tool("set_device_active", device="0", active=False, **T))
    check("Utility is off", bool(r) and r["device_on"] is False and r["is_active"] is False, r)
    sp = step("signal path while Utility is off", lambda: m.tool("get_signal_path", meter_ms=200, **T))
    if sp:
        check("problem: Utility switched off", any("'Utility' is switched off" in p for p in sp["problems"]),
              sp["problems"])
        check("gain parameters listed", any(p["name"] == "Gain" for p in sp["devices"][0]["gain_parameters"]))
        check("meters sampled", sp.get("meters", {}).get("samples", 0) >= 2, sp.get("meters"))
        print("    problems: %s" % sp["problems"])
    step("Utility on", lambda: m.tool("set_device_active", device="0", active=True, **T))

    print("\n[sidechain]")
    dr = step("compressor routing", lambda: m.tool("get_device_routing", device="1", **T))
    if dr:
        check("compressor has sidechain routing", dr["has_routing"] is True, dr)
        print("    types: %s" % dr["routing"].get("available_input_type"))
        choices = [c for c in (dr["routing"].get("available_input_type") or [])
                   if c != dr["routing"].get("input_type")]
        if choices:
            target = MIDI if MIDI in choices else choices[0]
            s = step("sidechain from %s" % target,
                     lambda: m.tool("set_device_routing", device="1", input_type=target, **T))
            check("sidechain set", bool(s) and s["after"]["input_type"] == target, s and s["after"])
            step("sidechain back", lambda: m.tool("set_device_routing", device="1",
                                                  input_type=dr["routing"]["input_type"], **T))
        expect_error("bad sidechain name lists choices",
                     lambda: m.tool("set_device_routing", device="1", input_type="Nowhere", **T), "Choices")
    u = step("utility routing", lambda: m.tool("get_device_routing", device="0", **T))
    check("Utility has no sidechain", bool(u) and u["has_routing"] is False, u)

    print("\n[move / delete device]")
    step("move Utility after Compressor", lambda: m.tool("move_device", device="0", target_index=2, **T))
    check("order is Compressor, Utility", device_names(m, a)[:2] == ["Compressor", "Utility"], device_names(m, a))
    step("move Utility to the midi track", lambda: m.tool("move_device", device="1", target_track_index=mi, **T))
    check("Utility now on the midi track", device_names(m, mi) == ["Utility"], device_names(m, mi))
    expect_error("delete with wrong name refused",
                 lambda: m.tool("delete_device", device="0", expected_device_name="EQ Eight", **T), "does not match")
    m.set_safety({"allow": {"delete": False}})
    expect_error("delete refused while delete switch is off",
                 lambda: m.tool("delete_device", device="0", expected_device_name="Compressor", **T), "delete")
    check("compressor still there", device_names(m, a) == ["Compressor"], device_names(m, a))
    m.set_safety({"saved_set_allow": {"delete": False}})
    step("delete Compressor", lambda: m.tool("delete_device", device="0", expected_device_name="Compressor", **T))
    check("audio track has no devices", device_names(m, a) == [], device_names(m, a))
    step("undo the delete", lambda: m.tool("undo"))
    check("undo brought the Compressor back", device_names(m, a) == ["Compressor"], device_names(m, a))

    print("\n[midi clip]")
    step("create midi clip", lambda: m.text("create_clip", track_index=mi, clip_index=0, length=4.0))
    c = step("clip info", lambda: m.tool("get_clip_info", track_index=mi, clip_index=0))
    check("midi clip 4 beats, looping", bool(c) and c["length"] == 4.0 and c["looping"] is True, c)
    r = step("loop 0..2, muted", lambda: m.tool("set_clip_properties", track_index=mi, clip_index=0,
                                                 loop_end=2.0, muted=True))
    check("loop end 2, muted", bool(r) and r["after"]["loop_end"] == 2.0 and r["after"]["muted"] is True,
          r and r["after"])
    r = step("loop 4..8 (moves past the old end)", lambda: m.tool("set_clip_properties", track_index=mi,
                                                                   clip_index=0, loop_start=4.0, loop_end=8.0))
    check("loop 4..8", bool(r) and (r["after"]["loop_start"], r["after"]["loop_end"]) == (4.0, 8.0),
          r and r["after"])
    expect_error("gain on a midi clip refused",
                 lambda: m.tool("set_clip_properties", track_index=mi, clip_index=0, gain=0.5), "audio clips")

    print("\n[audio clip]")
    write_tone(TONE)
    step("import tone", lambda: m.text("create_audio_clip", track_index=a, clip_index=0,
                                        path="Z:" + TONE.replace("/", "\\")))
    c = step("audio clip info", lambda: m.tool("get_clip_info", track_index=a, clip_index=0))
    if c:
        check("audio clip with gain display", c.get("is_audio_clip") and "dB" in str(c.get("gain_display")), c)
        print("    gain %s (%s), warp %s, file %s" % (c.get("gain"), c.get("gain_display"),
                                                     c.get("warp_mode_name"), c.get("file_path")))
    r = step("clip gain +6 dB", lambda: m.tool("set_clip_properties", track_index=a, clip_index=0, gain_db=6.0))
    check("clip gain shows 6.0 dB", bool(r) and str(r["after"]["gain_display"]).startswith("6.0"),
          r and r["after"].get("gain_display"))
    r = step("pitch +3", lambda: m.tool("set_clip_properties", track_index=a, clip_index=0, pitch_coarse=3))
    check("pitch is +3", bool(r) and r["after"]["pitch_coarse"] == 3)

    print("\n[scenes]")
    sc0 = m.tool("get_scenes")["scenes"]
    r = step("create scene at end", lambda: m.tool("create_scene", index=-1))
    new = len(sc0)
    check("scene added", bool(r) and r["index"] == new and r["scene_count"] == len(sc0) + 1, r)
    name = TEST_PREFIX + "-scene"
    r = step("name it and set tempo 100", lambda: m.tool("set_scene", scene_index=new, name=name, tempo=100))
    check("scene named with tempo", bool(r) and r["after"]["name"] == name and r["after"]["tempo"] == 100.0
          and r["after"]["tempo_enabled"] is True, r and r["after"])
    r = step("duplicate scene", lambda: m.tool("duplicate_scene", scene_index=new))
    check("copy below it", bool(r) and r["index"] == new + 1, r)
    expect_error("delete scene with wrong name refused",
                 lambda: m.tool("delete_scene", scene_index=new + 1, expected_name="Verse"), "does not match")
    step("delete the copy", lambda: m.tool("delete_scene", scene_index=new + 1, expected_name=r["name"] if r else name,
                                           allow_clips=True))
    check("one test scene left", len(m.tool("get_scenes")["scenes"]) == len(sc0) + 1)

    print("\n[duplicate track, return track]")
    r = step("duplicate midi track", lambda: m.tool("duplicate_track", track_index=mi))
    if r:
        check("copy right after it", r["new_index"] == mi + 1, r)
        step("name the copy", lambda: m.text("set_track_name", track_index=r["new_index"], name=TEST_PREFIX + "-dup"))
        check("copy has the Utility", device_names(m, r["new_index"]) == ["Utility"], device_names(m, r["new_index"]))
    r = step("create return track", lambda: m.tool("create_return_track"))
    if r:
        check("return added", r["return_track_count"] == m.tool("get_session_info")["return_track_count"], r)
        step("delete it again", lambda: m.tool("delete_track", track_type="return", track_index=r["index"],
                                               expected_name=r["name"]))

    print("\n[external audio effect (pedal loop insert)]")
    step("load External Audio Effect", lambda: m.text("load_instrument_or_effect", track_index=a,
                                                       uri="query:AudioFx#External%20Audio%20Effect"))
    ch = m.tool("get_device_chain", **T)["devices"]
    ext = next((d for d in ch if "External" in d["name"]), None)
    if check("External Audio Effect loaded", ext is not None, [d["name"] for d in ch]):
        print("    class %s, params %s" % (ext.get("class_name"), [p["name"] for p in ext["parameters"]]))
        er = m.tool("get_device_routing", device=ext["path"], **T)
        print("    routing visible to the API: %s" % er)


if __name__ == "__main__":
    run(__doc__, body)
