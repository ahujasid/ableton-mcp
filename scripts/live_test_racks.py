#!/usr/bin/env python3
"""Live test for 1.11.0: insert_device, racks and chains, drum pads, Simpler,
arrangement clips, note edits, clip envelopes, warp markers.

Runs only against an EMPTY Live set (File > New Live Set). Creates one MIDI
track (mcp-test-racks) and one audio track (mcp-test-audio), deleted at the
end, and a 2 s test tone in /tmp/claude. Nothing plays.

usage: python3 scripts/live_test_racks.py [--keep] [--force]
"""
import math
import os
import struct
import sys
import wave

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from live_harness import TEST_PREFIX, check, expect_error, find_track, run, step  # noqa: E402

MIDI = TEST_PREFIX + "-racks"
AUDIO = TEST_PREFIX + "-audio"
TONE = "/tmp/claude/mcp-test-tone.wav"


def write_tone(path, seconds=2.0, rate=48000):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * 220 * i / rate)))
                               for i in range(int(seconds * rate))))


def new_track(m, kind, name):
    idx = m.tool("get_session_info")["track_count"]
    step("create %s track" % kind, lambda: m.text("create_%s_track" % kind, index=-1))
    step("name it %s" % name, lambda: m.text("set_track_name", track_index=idx, name=name))
    return idx if check("%s exists" % name, find_track(m, name) == idx) else None


def body(m, args):
    t = new_track(m, "midi", MIDI)
    if t is None:
        return

    print("\n[insert_device + racks]")
    r = step("insert Drum Rack", lambda: m.tool("insert_device", track_index=t, device_name="Drum Rack"))
    check("drum rack is device 0", bool(r) and r["devices"][:1] == ["Drum Rack"], r)
    rack = step("get_rack on the drum rack", lambda: m.tool("get_rack", track_index=t, device="0"))
    check("is a drum rack, no loaded pads", bool(rack) and rack["is_drum_rack"] and rack["drum_pads"] == [], rack)
    expect_error("empty source pad refused",
                 lambda: m.tool("copy_drum_pad", track_index=t, device="0", source="C1", destination="D1"), "empty")
    r = step("rename pad C1", lambda: m.tool("set_drum_pad", track_index=t, device="0", pad="C1", name="mcp kick"))
    check("pad 36 renamed", bool(r) and r["pad"] == 36, r)
    expect_error("unknown device name refused",
                 lambda: m.tool("insert_device", track_index=t, device_name="No Such Device"), "")

    print("\n[Simpler]")
    t2 = new_track(m, "midi", MIDI + "-simpler")
    if t2 is not None:
        step("insert Simpler", lambda: m.tool("insert_device", track_index=t2, device_name="Simpler"))
        s = step("get_simpler (no sample)", lambda: m.tool("get_simpler", track_index=t2, device="0"))
        check("Classic mode", bool(s) and s["playback_mode"] == "Classic", s)
        write_tone(TONE)
        step("replace_sample with the tone", lambda: m.tool(
            "edit_simpler", track_index=t2, device="0", action="replace_sample",
            file_path="Z:" + TONE.replace("/", "\\")))
        s = step("set Slicing / Manual", lambda: m.tool(
            "edit_simpler", track_index=t2, device="0", action="set", playback_mode="Slicing",
            slicing_style="Manual"))
        check("sample loaded", bool(s) and s.get("sample") and s["sample"].get("length", 0) > 0, s)
        if s and s.get("sample"):
            mid = s["sample"]["length"] // 2
            s = step("insert a slice", lambda: m.tool("edit_simpler", track_index=t2, device="0",
                                                      action="insert_slice", time=mid))
            check("slice at the middle", bool(s) and mid in s["sample"]["slices"], s and s["sample"])

    print("\n[audio effect rack + chains]")
    a = new_track(m, "audio", AUDIO)
    if a is not None:
        step("insert Audio Effect Rack", lambda: m.tool("insert_device", track_index=a,
                                                        device_name="Audio Effect Rack"))
        r = step("insert chain Dry", lambda: m.tool("insert_rack_chain", track_index=a, device="0", name="Dry"))
        step("insert chain Wet", lambda: m.tool("insert_rack_chain", track_index=a, device="0", name="Wet"))
        r = step("Utility into chain 1", lambda: m.tool("insert_device", track_index=a, device_name="Utility",
                                                        chain="0/1"))
        check("Utility inside Wet", bool(r) and r["devices"] == ["Utility"], r)
        r = step("set chain 1 to -6 dB, panned", lambda: m.tool("set_rack_chain", track_index=a, device="0",
                                                                 chain=1, volume_db=-6, pan=-0.5))
        check("chain at -6 dB", bool(r) and r["after"]["volume"].startswith("-6.0"), r and r["after"])
        r = step("add a macro", lambda: m.tool("rack_macros", track_index=a, device="0", action="add_macro"))
        step("store a variation", lambda: m.tool("rack_macros", track_index=a, device="0",
                                                 action="store_variation"))
        rk = m.tool("get_rack", track_index=a, device="0")
        check("one variation stored", rk["variation_count"] >= 1, rk)
        step("delete it", lambda: m.tool("delete_rack_variation", track_index=a, device="0", variation=0))

        print("\n[arrangement audio clip + warp markers]")
        r = step("audio clip at beat 8", lambda: m.tool("create_arrangement_clip", track_index=a, start_time=8,
                                                        file_path="Z:" + TONE.replace("/", "\\"), name="tone"))
        if r:
            ai = r["arrangement_index"]
            step("warping on", lambda: m.tool("set_clip_properties", track_index=a, arrangement_index=ai,
                                              warping=True))
            w = step("get_warp_markers", lambda: m.tool("get_warp_markers", track_index=a, arrangement_index=ai))
            print("    markers %s" % (w and w.get("warp_markers")))
            r = step("add a warp marker at beat 1 (probes the WarpMarker API)", lambda: m.tool(
                "edit_warp_markers", track_index=a, arrangement_index=ai, action="add", beat_time=1.0))
            check("marker added", bool(r) and len(r["after"]) == len(r["before"]) + 1, r)
            if r:
                step("remove it", lambda: m.tool("edit_warp_markers", track_index=a, arrangement_index=ai,
                                                  action="remove", beat_time=1.0))
            step("delete the clip", lambda: m.tool("delete_arrangement_clip", track_index=a,
                                                   arrangement_index=ai, expected_clip_name="tone"))

    print("\n[arrangement MIDI clip + note edits + envelopes]")
    r = step("MIDI clip at beat 4", lambda: m.tool("create_arrangement_clip", track_index=t, start_time=4,
                                                   length=4, name="arr"))
    check("arrangement clip created", bool(r) and r.get("start_time") == 4.0, r)
    if r:
        step("delete it", lambda: m.tool("delete_arrangement_clip", track_index=t,
                                         arrangement_index=r["arrangement_index"], expected_clip_name="arr"))
    step("session clip", lambda: m.text("create_clip", track_index=t, clip_index=0, length=4.0))
    step("add 2 notes", lambda: m.text("add_notes_to_clip", track_index=t, clip_index=0, notes=[
        {"pitch": 36, "start_time": 0.1, "duration": 0.5, "velocity": 100},
        {"pitch": 38, "start_time": 1.0, "duration": 0.5, "velocity": 100}]))
    step("quantize_pitch 36", lambda: m.tool("edit_notes", track_index=t, clip_index=0, action="quantize_pitch",
                                             pitch=36, grid="1/4"))
    n = {x["pitch"]: x for x in m.tool("get_notes", track_index=t, clip_index=0)["notes"]}
    check("kick on the beat", abs(n[36]["start_time"]) < 1e-6, n[36])
    r = step("duplicate_region 0..2 -> 2", lambda: m.tool("edit_notes", track_index=t, clip_index=0,
                                                           action="duplicate_region", region_length=2,
                                                           destination_time=2))
    check("4 notes", bool(r) and r["notes_after"] == 4, r)
    r = step("volume envelope (probes the envelope API)", lambda: m.tool(
        "set_clip_envelope", track_index=t, clip_index=0, mixer="volume",
        points=[{"time": 0, "display": "0 dB"}, {"time": 2, "display": "-12 dB"}]))
    e = step("read it back", lambda: m.tool("get_clip_envelope", track_index=t, clip_index=0, mixer="volume",
                                            points=5))
    if e and e.get("samples"):
        print("    %s" % [s.get("display") for s in e["samples"]])
        check("-12 dB in the second half", "-12" in e["samples"][3].get("display", ""), e["samples"])
    step("clear it", lambda: m.tool("clear_clip_envelope", track_index=t, clip_index=0, mixer="volume"))
    c = m.tool("get_clip_envelope", track_index=t, clip_index=0, mixer="volume")
    check("envelope gone", c["has_envelope"] is False, c)


if __name__ == "__main__":
    run(__doc__, body)
