#!/usr/bin/env python3
"""Live test for the mixer, routing, monitoring, meter and automation tools.

Runs only against an EMPTY Live set (File > New Live Set); creates its own
audio track (mcp-test-mixer) and writes only to it, then deletes it. Solo is
set and cleared on the test track only. Nothing plays.

usage: python3 scripts/live_test_mixer.py [--keep] [--force]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from live_harness import TEST_PREFIX, check, expect_error, find_track, run, step  # noqa: E402

NAME = TEST_PREFIX + "-mixer"


def mine(state, idx):
    return next(t for t in state["tracks"] if t["index"] == idx)


def body(m, args):
    before = m.tool("get_session_info")["track_count"]
    step("create_audio_track", lambda: m.text("create_audio_track", index=-1))
    idx = before
    step("name test track", lambda: m.text("set_track_name", track_index=idx, name=NAME))
    if not check("test track at the end", find_track(m, NAME) == idx):
        return
    T = {"track_index": idx}

    print("\n[get_mixer_state]")
    st = step("get_mixer_state", lambda: m.tool("get_mixer_state"))
    if st:
        t = mine(st, idx)
        check("test track listed with its name", t["name"] == NAME)
        check("volume has Live's dB text", "dB" in (t["volume"] or {}).get("display", ""), t["volume"])
        check("audio track has monitoring", t.get("monitoring") in ("in", "auto", "off"), t.get("monitoring"))
        check("routing read", bool(t["routing"].get("output_type")), t["routing"])
        check("master present", st["master"] and st["master"]["volume"] is not None)
        check("returns listed", len(st["returns"]) == m.tool("get_session_info")["return_track_count"])
        check("solo summary lists exist", isinstance(st["soloed"], list) and isinstance(st["silenced_by_solo"], list))
        check("no unexpected unavailable fields on a plain audio track", "unavailable" not in t,
              t.get("unavailable"))

    print("\n[set_track_mixer]")
    r = step("volume_db -6", lambda: m.tool("set_track_mixer", volume_db=-6, **T))
    check("display reads -6.0 dB", bool(r) and r["after"]["volume"]["display"].startswith("-6.0"),
          r and r["after"]["volume"])
    r = step("pan 0.5", lambda: m.tool("set_track_mixer", panning=0.5, **T))
    check("pan display is right of centre", bool(r) and "R" in r["after"]["panning"]["display"],
          r and r["after"]["panning"])
    if st and st["returns"]:
        r = step("send A 0.3", lambda: m.tool("set_track_mixer", sends={"A": 0.3}, **T))
        check("send A is 0.3", bool(r) and abs(r["after"]["sends"][0]["value"] - 0.3) < 1e-6)
    expect_error("pan 3 is refused", lambda: m.tool("set_track_mixer", panning=3, **T), "outside")
    expect_error("+12 dB is refused", lambda: m.tool("set_track_mixer", volume_db=12, **T), "maximum")
    r = step("mute", lambda: m.tool("set_track_mixer", mute=True, **T))
    check("muted", bool(r) and r["after"]["mute"] is True)
    step("unmute", lambda: m.tool("set_track_mixer", mute=False, **T))
    r = step("arm", lambda: m.tool("set_track_mixer", arm=True, **T))
    check("armed", bool(r) and r["after"]["arm"] is True)
    step("disarm", lambda: m.tool("set_track_mixer", arm=False, **T))

    print("\n[solo]")
    r = step("solo test track (exclusive)", lambda: m.tool("set_track_mixer", solo=True, exclusive_solo=True, **T))
    check("soloed", bool(r) and r["after"]["solo"] is True)
    st2 = step("mixer state while soloed", lambda: m.tool("get_mixer_state", include_routing=False))
    if st2:
        check("only the test track is soloed", st2["soloed"] == [NAME], st2["soloed"])
        others = [t["name"] for t in st2["tracks"] if t["index"] != idx]
        check("other tracks are silenced by solo", set(others) <= set(st2["silenced_by_solo"]),
              st2["silenced_by_solo"])
    step("unsolo", lambda: m.tool("set_track_mixer", solo=False, **T))
    st3 = step("mixer state after unsolo", lambda: m.tool("get_mixer_state", include_routing=False))
    check("nothing silenced after unsolo", bool(st3) and st3["silenced_by_solo"] == [], st3 and st3["silenced_by_solo"])

    print("\n[undo a mixer change]")
    step("volume_db -12", lambda: m.tool("set_track_mixer", volume_db=-12, **T))
    step("undo", lambda: m.tool("undo"))
    st4 = step("read back", lambda: m.tool("get_mixer_state", include_routing=False))
    if st4:
        disp = mine(st4, idx)["volume"]["display"]
        check("undo put the fader back to -6 dB", disp.startswith("-6.0"), disp)

    print("\n[routing]")
    r = step("get_track_routing", lambda: m.tool("get_track_routing", **T))
    if r:
        check("input types offered", bool(r["available_input_type"]), r)
        check("output types offered", bool(r["available_output_type"]), r)
        print("    input types:  %s" % r["available_input_type"])
        print("    input chans:  %s" % r["available_input_channel"])
        print("    output types: %s" % r["available_output_type"])
        print("    output chans: %s" % r["available_output_channel"])
        orig_in = (r["input_type"], r["input_channel"])
        chans = [c for c in r["available_input_channel"] if c != r["input_channel"]]
        if chans:
            s = step("set input channel %s" % chans[0],
                     lambda: m.tool("set_track_routing", input_channel=chans[0], **T))
            check("input channel changed", bool(s) and s["after"]["input_channel"] == chans[0], s and s["after"])
            s = step("restore input", lambda: m.tool("set_track_routing", input_type=orig_in[0],
                                                     input_channel=orig_in[1], **T))
            check("input restored", bool(s) and (s["after"]["input_type"], s["after"]["input_channel"]) == orig_in)
        outs = [o for o in r["available_output_type"] if o != r["output_type"]]
        if outs:
            orig_out = (r["output_type"], r["output_channel"])
            s = step("set output type %s" % outs[0], lambda: m.tool("set_track_routing", output_type=outs[0], **T))
            check("output type changed", bool(s) and s["after"]["output_type"] == outs[0], s and s["after"])
            s = step("restore output", lambda: m.tool("set_track_routing", output_type=orig_out[0],
                                                      output_channel=orig_out[1], **T))
            check("output restored", bool(s) and s["after"]["output_type"] == orig_out[0])
        expect_error("unknown channel is refused with choices",
                     lambda: m.tool("set_track_routing", input_channel="99/100", **T), "Choices")
    rr = step("return track routing", lambda: m.tool("get_track_routing", track_type="return", track_index=0))
    if rr:
        check("return output readable", rr.get("output_type") is not None, rr)
        # Live 12 gives return tracks input routing (measured 2026-11-19: Ext. In 1/2).
        check("return input is a value or null with a reason",
              rr.get("input_type") is not None or "input_type" in rr.get("unavailable", {}), rr)
    rm = step("master routing", lambda: m.tool("get_track_routing", track_type="master"))
    check("master output readable", bool(rm) and rm.get("output_type") is not None, rm)

    print("\n[monitoring]")
    for state in ("in", "off", "auto"):
        r = step("monitor %s" % state, lambda s=state: m.tool("set_track_monitoring", track_index=idx, state=s))
        check("monitoring is %s" % state, bool(r) and r["monitoring"] == state, r)
    expect_error("bad state refused", lambda: m.tool("set_track_monitoring", track_index=idx, state="on"),
                 "in, auto, off")

    print("\n[meters]")
    r = step("meters for 300 ms", lambda: m.tool("get_track_meters", duration_ms=300, tracks=[
        T, {"track_type": "return", "track_index": 0}, {"track_type": "master"}]))
    if r:
        t, ret, master = r["tracks"]
        check("several samples taken", r["samples"] >= 3, r["samples"])
        check("test track output meter is known", t["output_signal"] is not None, t)
        check("test track input meter is known", t["input_signal"] is not None, t)
        check("master output meter is known", master["output_signal"] is not None, master)
        print("    test track %s / return %s / master %s" % (t["peaks"], ret["peaks"], master["peaks"]))

    print("\n[arrangement and automation]")
    r = step("back_to_arrangement", lambda: m.tool("back_to_arrangement"))
    check("back_to_arrangement reports state", bool(r) and r.get("back_to_arranger") is False, r)
    r = step("get_automation_overrides", lambda: m.tool("get_automation_overrides"))
    check("an empty set has no overridden automation", bool(r) and r["overridden_count"] == 0, r)
    r = step("re_enable_automation (song)", lambda: m.tool("re_enable_automation"))
    check("re_enable reports song scope", bool(r) and r.get("scope") == "song", r)
    r = step("re_enable_automation (track)", lambda: m.tool("re_enable_automation", **T))
    check("track re-enable has nothing to do", bool(r) and r.get("re_enabled") == [], r)


if __name__ == "__main__":
    run(__doc__, body)
