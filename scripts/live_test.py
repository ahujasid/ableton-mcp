#!/usr/bin/env python3
"""Live test for the core extended tools: undo state, delete_track's name
check, delete, undo (restores the track) and redo (deletes it again).

Runs only against an EMPTY Live set (File > New Live Set); creates and deletes
its own tracks, named mcp-test-*. Never run it on a song.

usage: python3 scripts/live_test.py [--keep] [--force]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from live_harness import TEST_PREFIX, check, expect_error, find_track, run, step  # noqa: E402

NAME = TEST_PREFIX + "-core"


def body(m, args):
    print("\n[tools]")
    names = m.tool_names()
    for t in ("get_undo_state", "undo", "redo", "delete_track"):
        check("tool listed: " + t, t in names)

    print("\n[undo state]")
    state = step("get_undo_state", lambda: m.tool("get_undo_state"))
    check("undo state has both flags", isinstance(state, dict) and {"can_undo", "can_redo"} <= set(state))

    print("\n[create test track]")
    before = m.tool("get_session_info")["track_count"]
    step("create_audio_track", lambda: m.text("create_audio_track", index=-1))
    idx = before
    step("set_track_name", lambda: m.text("set_track_name", track_index=idx, name=NAME))
    check("test track exists at the end", find_track(m, NAME) == idx)

    print("\n[delete_track safety]")
    expect_error("wrong expected_name is refused", lambda: m.tool(
        "delete_track", track_index=idx, expected_name=NAME + "-nope"), "does not match")
    check("track still there after refused delete", find_track(m, NAME) == idx)
    expect_error("master cannot be deleted", lambda: m.tool(
        "delete_track", track_index=0, expected_name="Main", track_type="master"), "master")
    expect_error("out-of-range index is refused", lambda: m.tool(
        "delete_track", track_index=999, expected_name=NAME), "out of range")

    print("\n[delete, undo, redo]")
    res = step("delete_track", lambda: m.tool("delete_track", track_index=idx, expected_name=NAME))
    check("delete reports the track", bool(res) and res.get("name") == NAME)
    check("track gone", find_track(m, NAME) is None)
    check("track count back to start", m.tool("get_session_info")["track_count"] == before)

    res = step("undo", lambda: m.tool("undo"))
    check("undo reports undone", bool(res) and res.get("undone") is True)
    check("undo restored the track", find_track(m, NAME) == idx)

    res = step("redo", lambda: m.tool("redo"))
    check("redo reports redone", bool(res) and res.get("redone") is True)
    check("redo deleted it again", find_track(m, NAME) is None)


if __name__ == "__main__":
    run(__doc__, body)
