#!/usr/bin/env python3
"""Live test for 1.10.0: transport and song settings, locators, notes by id,
clip edits.

Runs only against an EMPTY Live set (File > New Live Set). Song settings it
changes (loop, metronome, quantization, scale, signature) are put back to what
they were. Creates one MIDI track (mcp-test-notes), deleted at the end, and one
locator (mcp-test-cue), which stays: there is no tool to delete locators.
Nothing plays.

usage: python3 scripts/live_test_transport.py [--keep] [--force]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from live_harness import TEST_PREFIX, check, expect_error, find_track, run, step  # noqa: E402

NAME = TEST_PREFIX + "-notes"


def body(m, args):
    print("\n[transport]")
    t0 = step("get_transport", lambda: m.tool("get_transport"))
    if not t0:
        return
    check("not playing", t0["is_playing"] is False, t0)
    check("cpu read", isinstance(t0.get("cpu"), dict), t0.get("cpu"))
    print("    %s" % dict((k, t0.get(k)) for k in ("tempo", "signature", "loop", "loop_start", "loop_length",
                                                    "metronome", "clip_trigger_quantization", "root_note",
                                                    "scale_name")))
    r = step("set loop 8..12, metronome on, 1/16, D Dorian, 7/8", lambda: m.tool(
        "set_song_settings", loop=True, loop_start=8, loop_length=4, metronome=True,
        clip_trigger_quantization="1/16", root_note="D", scale_name="Dorian", signature_numerator=7,
        signature_denominator=8))
    if r:
        a = r["after"]
        check("loop set", a["loop"] is True and a["loop_start"] == 8.0 and a["loop_length"] == 4.0, a)
        check("metronome on", a["metronome"] is True)
        check("quantization 1/16", a["clip_trigger_quantization"] == "1/16", a["clip_trigger_quantization"])
        check("scale D Dorian", (a["root_note"], a["scale_name"]) == ("D", "Dorian"), (a["root_note"], a["scale_name"]))
        check("signature 7/8", a["signature"] == "7/8", a["signature"])
    expect_error("unknown quantization refused",
                 lambda: m.tool("set_song_settings", clip_trigger_quantization="1/64"), "choose one of")
    num, den = (int(x) for x in t0["signature"].split("/"))
    step("restore song settings", lambda: m.tool(
        "set_song_settings", loop=t0["loop"], loop_start=t0["loop_start"], loop_length=t0["loop_length"],
        metronome=t0["metronome"], clip_trigger_quantization=t0["clip_trigger_quantization"],
        root_note=t0["root_note"], scale_name=t0["scale_name"], signature_numerator=num,
        signature_denominator=den))
    t1 = m.tool("get_transport")
    for k in ("loop", "loop_start", "loop_length", "metronome", "clip_trigger_quantization", "root_note",
              "scale_name", "signature"):
        check("restored %s" % k, t1[k] == t0[k], (t1[k], t0[k]))

    print("\n[locators]")
    step("create locator", lambda: m.text("create_locator", name=TEST_PREFIX + "-cue", time=16.0))
    r = step("jump by name", lambda: m.tool("jump_to_cue", cue=TEST_PREFIX + "-cue"))
    check("jumped to beat 16", bool(r) and r["time"] == 16.0, r)
    expect_error("unknown locator lists names", lambda: m.tool("jump_to_cue", cue="nope"), "Locators:")

    print("\n[notes by id]")
    before = m.tool("get_session_info")["track_count"]
    step("create midi track", lambda: m.text("create_midi_track", index=-1))
    idx = before
    step("name it", lambda: m.text("set_track_name", track_index=idx, name=NAME))
    if not check("test track exists", find_track(m, NAME) == idx):
        return
    C = {"track_index": idx, "clip_index": 0}
    step("create clip", lambda: m.text("create_clip", track_index=idx, clip_index=0, length=4.0))
    step("add 4 notes", lambda: m.text("add_notes_to_clip", track_index=idx, clip_index=0, notes=[
        {"pitch": 60, "start_time": 0.05, "duration": 0.5, "velocity": 100},
        {"pitch": 64, "start_time": 1.1, "duration": 0.5, "velocity": 100},
        {"pitch": 67, "start_time": 2.0, "duration": 0.5, "velocity": 100},
        {"pitch": 72, "start_time": 3.0, "duration": 0.5, "velocity": 100}]))
    n = step("get_notes", lambda: m.tool("get_notes", **C))
    if not n or not check("4 notes with ids", n["count"] == 4 and all("note_id" in x for x in n["notes"]), n):
        return
    ids = [x["note_id"] for x in n["notes"]]
    print("    ids %s, fields %s" % (ids, sorted(n["notes"][0])))
    step("modify: velocity 50 + probability 0.5 on the first, pitch 62 on the second", lambda: m.tool(
        "modify_notes", notes=[{"note_id": ids[0], "velocity": 50, "probability": 0.5},
                               {"note_id": ids[1], "pitch": 62}], **C))
    n2 = {x["note_id"]: x for x in m.tool("get_notes", **C)["notes"]}
    check("velocity changed in place", n2[ids[0]]["velocity"] == 50.0, n2[ids[0]])
    check("probability changed", abs(n2[ids[0]].get("probability", 1) - 0.5) < 1e-6, n2[ids[0]])
    check("pitch changed, same id", n2[ids[1]]["pitch"] == 62, n2[ids[1]])
    expect_error("unknown id refused", lambda: m.tool("modify_notes", notes=[{"note_id": 999999, "velocity": 1}],
                                                      **C), "not in this clip")
    step("remove the last note", lambda: m.tool("remove_notes", note_ids=[ids[3]], **C))
    check("3 notes left", m.tool("get_notes", **C)["count"] == 3)

    print("\n[clip edits]")
    step("quantize 1/4 fully", lambda: m.tool("edit_clip", action="quantize", grid="1/4", amount=1.0, **C))
    starts = sorted(x["start_time"] for x in m.tool("get_notes", **C)["notes"])
    check("notes on quarter notes", all(abs(s - round(s)) < 1e-6 for s in starts), starts)
    r = step("duplicate_loop", lambda: m.tool("edit_clip", action="duplicate_loop", **C))
    check("loop doubled to 8 beats", bool(r) and r["loop_end"] - r["loop_start"] == 8.0, r)
    check("notes doubled", m.tool("get_notes", **C)["count"] == 6)
    step("loop back to 0..4", lambda: m.tool("set_clip_properties", loop_start=0.0, loop_end=4.0, **C))
    r = step("crop", lambda: m.tool("edit_clip", action="crop", **C))
    check("cropped to 4 beats", bool(r) and r["length"] == 4.0, r)


if __name__ == "__main__":
    run(__doc__, body)
