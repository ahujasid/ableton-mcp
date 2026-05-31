#!/usr/bin/env python3
"""
AbletonMCP integration test suite.
Run with Ableton Live open and AbletonMCP control surface active.

Usage:
    python3 test_ableton_mcp.py
"""

import socket
import json
import time
import sys

HOST = "localhost"
PORT = 9877
TIMEOUT = 10.0

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
SKIP = "\033[33mSKIP\033[0m"
WARN = "\033[33mWARN\033[0m"

results = {"pass": 0, "fail": 0, "skip": 0}


def send_command(sock, command_type, params=None):
    cmd = {"type": command_type}
    if params:
        cmd["params"] = params
    sock.sendall(json.dumps(cmd).encode("utf-8"))
    sock.settimeout(TIMEOUT)
    data = b""
    deadline = time.time() + TIMEOUT
    while time.time() < deadline:
        try:
            chunk = sock.recv(8192)
        except socket.timeout:
            break
        if not chunk:
            break
        data += chunk
        try:
            return json.loads(data.decode("utf-8"))
        except ValueError:
            continue
    raise TimeoutError("No response to '{}' in {}s".format(command_type, TIMEOUT))


def check(name, condition, detail=""):
    if condition:
        print("  [{}] {}{}".format(PASS, name, " — " + detail if detail else ""))
        results["pass"] += 1
    else:
        print("  [{}] {}{}".format(FAIL, name, " — " + detail if detail else ""))
        results["fail"] += 1
    return condition


def skip(name, reason):
    print("  [{}] {} — {}".format(SKIP, name, reason))
    results["skip"] += 1


def section(title):
    print("\n\033[1m{}\033[0m".format(title))
    print("─" * 50)


def connect():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5.0)
    try:
        sock.connect((HOST, PORT))
        return sock
    except Exception as e:
        print("\033[31mCannot connect to Ableton on port {}:{}\033[0m".format(HOST, PORT))
        print("Make sure Ableton is running with AbletonMCP control surface active.")
        sys.exit(1)


# ─── Track state ──────────────────────────────────────────────────────────────
test_track_index = None
initial_track_count = None


def run_tests():
    global test_track_index, initial_track_count

    print("\n\033[1mAbletonMCP Test Suite\033[0m")
    print("=" * 50)

    # Wait for any existing connection (MCP server) to be cleaned up
    print("Waiting for port to be available...", end=" ", flush=True)
    for _ in range(20):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.5)
            s.connect((HOST, PORT))
            s.sendall(json.dumps({"type": "get_session_info"}).encode("utf-8"))
            s.settimeout(1.0)
            try:
                data = s.recv(8192)
                if data:
                    s.close()
                    time.sleep(0.5)  # let Ableton clean up after us
                    break
            except:
                pass
            s.close()
        except:
            pass
        time.sleep(0.3)
    print("OK")

    print("Connecting to {}:{}...".format(HOST, PORT))
    t0 = time.time()
    sock = connect()
    connect_ms = int((time.time() - t0) * 1000)
    print("Connected in {}ms\n".format(connect_ms))

    # ── 1. Session info ─────────────────────────────────────────────────────
    section("1. get_session_info")
    t0 = time.time()
    r = send_command(sock, "get_session_info")
    elapsed_ms = int((time.time() - t0) * 1000)

    check("returns status:success", r.get("status") == "success")
    info = json.loads(r["result"]) if isinstance(r.get("result"), str) else r.get("result", {})
    check("has tempo field", "tempo" in info, "tempo={}".format(info.get("tempo")))
    check("has track_count", "track_count" in info, "count={}".format(info.get("track_count")))
    check("has signature_numerator", "signature_numerator" in info)
    check("has master_track", "master_track" in info)
    check("response under 1s", elapsed_ms < 1000, "{}ms".format(elapsed_ms))
    initial_track_count = info.get("track_count", 0)

    # ── 2. get_track_info ───────────────────────────────────────────────────
    section("2. get_track_info")
    if initial_track_count > 0:
        r = send_command(sock, "get_track_info", {"track_index": 0})
        check("returns status:success", r.get("status") == "success")
        ti = json.loads(r["result"]) if isinstance(r.get("result"), str) else r.get("result", {})
        check("has name", "name" in ti, "name={}".format(ti.get("name")))
        check("has clip_slots", "clip_slots" in ti)
        check("has devices list", "devices" in ti)
        check("has volume", "volume" in ti)

        # out of range
        r2 = send_command(sock, "get_track_info", {"track_index": 9999})
        check("out-of-range returns error", r2.get("status") == "error")
    else:
        skip("get_track_info", "no tracks in session")

    # ── 3. Unknown command ──────────────────────────────────────────────────
    section("3. Error handling")
    r = send_command(sock, "nonexistent_command_xyz")
    check("unknown command returns error", r.get("status") == "error")
    check("error has message field", "message" in r)

    # ── 4. create_midi_track ────────────────────────────────────────────────
    section("4. create_midi_track")
    r = send_command(sock, "create_midi_track", {"index": -1})
    check("returns status:success", r.get("status") == "success")
    tr = json.loads(r["result"]) if isinstance(r.get("result"), str) else r.get("result", {})
    check("result has index", "index" in tr, "index={}".format(tr.get("index")))
    check("result has name", "name" in tr)
    test_track_index = tr.get("index", initial_track_count)

    # verify track count increased
    r2 = send_command(sock, "get_session_info")
    info2 = json.loads(r2["result"]) if isinstance(r2.get("result"), str) else r2.get("result", {})
    check("track_count increased by 1",
          info2.get("track_count", 0) == initial_track_count + 1,
          "{} -> {}".format(initial_track_count, info2.get("track_count")))

    # ── 5. set_track_name ───────────────────────────────────────────────────
    section("5. set_track_name")
    r = send_command(sock, "set_track_name", {"track_index": test_track_index, "name": "MCPTest"})
    check("returns status:success", r.get("status") == "success")
    nr = json.loads(r["result"]) if isinstance(r.get("result"), str) else r.get("result", {})
    check("name is updated", nr.get("name") == "MCPTest", "name={}".format(nr.get("name")))

    r2 = send_command(sock, "set_track_name", {"track_index": 9999, "name": "x"})
    check("invalid index returns error", r2.get("status") == "error")

    # ── 6. create_clip ──────────────────────────────────────────────────────
    section("6. create_clip")
    r = send_command(sock, "create_clip", {"track_index": test_track_index, "clip_index": 0, "length": 4.0})
    check("returns status:success", r.get("status") == "success")
    cr = json.loads(r["result"]) if isinstance(r.get("result"), str) else r.get("result", {})
    check("result has length", "length" in cr, "length={}".format(cr.get("length")))
    check("length is correct", cr.get("length") == 4.0)

    # duplicate slot should fail
    r2 = send_command(sock, "create_clip", {"track_index": test_track_index, "clip_index": 0, "length": 4.0})
    check("duplicate slot returns error", r2.get("status") == "error")

    # ── 7. add_notes_to_clip ────────────────────────────────────────────────
    section("7. add_notes_to_clip")
    notes = [
        {"pitch": 60, "start_time": 0.0, "duration": 0.5, "velocity": 100, "mute": False},
        {"pitch": 64, "start_time": 1.0, "duration": 0.5, "velocity": 80, "mute": False},
        {"pitch": 67, "start_time": 2.0, "duration": 0.5, "velocity": 90, "mute": False},
    ]
    r = send_command(sock, "add_notes_to_clip", {"track_index": test_track_index, "clip_index": 0, "notes": notes})
    check("returns status:success", r.get("status") == "success")
    nr = json.loads(r["result"]) if isinstance(r.get("result"), str) else r.get("result", {})
    check("note_count matches", nr.get("note_count") == 3, "count={}".format(nr.get("note_count")))

    # no clip in slot
    r2 = send_command(sock, "add_notes_to_clip", {"track_index": test_track_index, "clip_index": 5, "notes": notes})
    check("empty slot returns error", r2.get("status") == "error")

    # ── 8. set_clip_name ────────────────────────────────────────────────────
    section("8. set_clip_name")
    r = send_command(sock, "set_clip_name", {"track_index": test_track_index, "clip_index": 0, "name": "TestClip"})
    check("returns status:success", r.get("status") == "success")
    cn = json.loads(r["result"]) if isinstance(r.get("result"), str) else r.get("result", {})
    check("name updated", cn.get("name") == "TestClip")

    # ── 9. set_tempo ────────────────────────────────────────────────────────
    section("9. set_tempo")
    original_tempo = info.get("tempo", 120.0)
    r = send_command(sock, "set_tempo", {"tempo": 140.0})
    check("returns status:success", r.get("status") == "success")
    tr2 = json.loads(r["result"]) if isinstance(r.get("result"), str) else r.get("result", {})
    check("tempo updated to 140", abs(tr2.get("tempo", 0) - 140.0) < 0.1, "tempo={}".format(tr2.get("tempo")))

    # restore
    send_command(sock, "set_tempo", {"tempo": original_tempo})
    r3 = send_command(sock, "get_session_info")
    i3 = json.loads(r3["result"]) if isinstance(r3.get("result"), str) else r3.get("result", {})
    check("tempo restored to {}".format(original_tempo), abs(i3.get("tempo", 0) - original_tempo) < 0.1)

    # ── 10. Browser ─────────────────────────────────────────────────────────
    section("10. Browser")
    r = send_command(sock, "get_browser_tree", {"category_type": "drums"})
    check("get_browser_tree returns success", r.get("status") == "success")
    bt = json.loads(r["result"]) if isinstance(r.get("result"), str) else r.get("result", {})
    check("has categories", len(bt.get("categories", [])) > 0)

    r2 = send_command(sock, "get_browser_items_at_path", {"path": "drums"})
    check("get_browser_items_at_path returns success", r2.get("status") == "success")
    bp = json.loads(r2["result"]) if isinstance(r2.get("result"), str) else r2.get("result", {})
    check("has items", len(bp.get("items", [])) > 0, "{} items".format(len(bp.get("items", []))))

    r3 = send_command(sock, "get_browser_items_at_path", {"path": "nonexistent_xyz"})
    check("invalid path returns error gracefully", "error" in (json.loads(r3["result"]) if isinstance(r3.get("result"), str) else r3.get("result", {})))

    # ── 11. Sequential commands ──────────────────────────────────────────────
    section("11. Sequential stress test (5 rapid commands)")
    t0 = time.time()
    for i in range(5):
        r = send_command(sock, "get_session_info")
    elapsed = time.time() - t0
    check("5 get_session_info in under 3s", elapsed < 3.0, "{:.2f}s".format(elapsed))

    # ── 12. Cleanup ──────────────────────────────────────────────────────────
    section("12. Cleanup")
    # We can't delete tracks via MCP, just note it
    skip("delete test track", "delete_track not in API — remove 'MCPTest' track manually")

    sock.close()

    # ── Summary ──────────────────────────────────────────────────────────────
    total = results["pass"] + results["fail"] + results["skip"]
    print("\n" + "=" * 50)
    print("\033[1mResults: {}/{} passed, {} failed, {} skipped\033[0m".format(
        results["pass"], total - results["skip"], results["fail"], results["skip"]))

    if results["fail"] == 0:
        print("\033[32mAll tests passed.\033[0m")
    else:
        print("\033[31m{} test(s) failed.\033[0m".format(results["fail"]))

    return results["fail"] == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
