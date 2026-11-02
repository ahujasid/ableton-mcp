"""Shared harness for the live tests (scripts/live_test*.py).

Starts this checkout's MCP server over stdio (so a live test exercises the tool
layer, the socket and the Remote Script together), offers check/step helpers
that tally PASS/FAIL, and refuses to touch a set that looks like a real song.

A live test only ever writes to tracks it created itself (named with the
TEST_PREFIX) and deletes them again at the end, unless --keep is given.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEST_PREFIX = "mcp-test"

PASS, FAIL = [], []

# What a new, untouched Live set looks like: Live's default track names, no
# clips, no devices. Anything else is treated as a song.
DEFAULT_TRACK = re.compile(r"^\d+-(MIDI|Audio)$")
DEFAULT_RETURN = re.compile(r"^[A-Z]-(Reverb|Delay)$")
MAX_EMPTY_TRACKS = 4


class ToolError(RuntimeError):
    pass


class Mcp(object):
    """Minimal MCP client over stdio for this repo's ableton-mcp server."""

    def __init__(self, cmd=None):
        # The test server gets its own safety config (everything allowed, the
        # empty-set guard is the protection here), so the user's switches don't
        # change test results; set_safety() rewrites it mid-test.
        os.makedirs("/tmp/claude", exist_ok=True)
        self.safety_path = os.path.join("/tmp/claude", "ableton-mcp-live-test-safety-%d.json" % os.getpid())
        self.set_safety({"saved_set_allow": {"delete": False}})
        env = dict(os.environ, ABLETON_MCP_DISABLE_TELEMETRY="true", DISABLE_TELEMETRY="true",
                   ABLETON_MCP_DISABLE_DATASET="1", ABLETON_MCP_SAFETY_CONFIG=self.safety_path)
        cmd = cmd or ["uv", "run", "--frozen", "--directory", REPO, "ableton-mcp"]
        self.log = tempfile.NamedTemporaryFile(prefix="ableton-mcp-live-", suffix=".log", delete=False)
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.log,
                                     env=env, text=True, bufsize=1)
        self.next_id = 0
        self.rpc("initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                                "clientInfo": {"name": "ableton-mcp-live-test", "version": "1"}})
        self.notify("notifications/initialized")

    def set_safety(self, cfg):
        """Replace the test server's safety config (re-read on the next call)."""
        tmp = self.safety_path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(cfg, f)
        os.replace(tmp, self.safety_path)
        # mtime granularity: make sure the next stat sees a change
        st = os.stat(self.safety_path)
        os.utime(self.safety_path, ns=(st.st_atime_ns, st.st_mtime_ns + 1000))

    def _send(self, body):
        self.proc.stdin.write(json.dumps(body) + "\n")
        self.proc.stdin.flush()

    def notify(self, method, params=None):
        self._send({"jsonrpc": "2.0", "method": method, **({"params": params} if params else {})})

    def rpc(self, method, params):
        self.next_id += 1
        my_id = self.next_id
        self._send({"jsonrpc": "2.0", "id": my_id, "method": method, "params": params})
        while True:
            line = self.proc.stdout.readline()
            if not line:
                raise RuntimeError("MCP server exited; log: " + self.log.name)
            msg = json.loads(line)
            if msg.get("id") != my_id:
                continue  # a notification or server request
            if "error" in msg:
                raise RuntimeError(msg["error"])
            return msg["result"]

    def text(self, _tool, **args):
        """Call a tool and return its text. Raises ToolError on an error reply."""
        res = self.rpc("tools/call", {"name": _tool, "arguments": args})
        text = "\n".join(b.get("text", "") for b in res.get("content", []))
        if res.get("isError") or text.startswith("Error") or "missing capability" in text:
            raise ToolError("%s: %s" % (_tool, text))
        return text

    def tool(self, _tool, **args):
        """Call a tool whose success reply is JSON, and return it parsed."""
        return json.loads(self.text(_tool, **args))

    def tool_names(self):
        return {t["name"] for t in self.rpc("tools/list", {})["tools"]}

    def close(self):
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=5)
        except Exception:  # noqa: BLE001
            self.proc.kill()


def check(label, cond, detail=""):
    (PASS if cond else FAIL).append(label)
    print(("  ok   " if cond else "  FAIL ") + label + (("  (%s)" % detail) if detail and not cond else ""))
    return cond


def step(label, fn):
    """Run fn; a raised exception counts as a failure of label and returns None."""
    try:
        return fn()
    except Exception as e:  # noqa: BLE001
        check(label, False, str(e))
        return None


def expect_error(label, fn, contains=""):
    """Pass when fn raises ToolError (whose text holds contains)."""
    try:
        fn()
    except ToolError as e:
        return check(label, contains in str(e), "error text was: %s" % e)
    return check(label, False, "no error")


def track_names(m):
    session = m.tool("get_session_info")
    return [m.tool("get_track_info", track_index=i)["name"] for i in range(session["track_count"])]


def find_track(m, name):
    names = track_names(m)
    return names.index(name) if name in names else None


def guard_empty_set(m, force=False):
    """Exit unless the open set is an untouched new set. Prints why."""
    session = m.tool("get_session_info")
    problems, soft = [], []  # soft problems are the only ones --force overrides
    if session["track_count"] > MAX_EMPTY_TRACKS:
        problems.append("%d tracks (an empty set has at most %d)" % (session["track_count"], MAX_EMPTY_TRACKS))
    for i in range(min(session["track_count"], MAX_EMPTY_TRACKS + 1)):
        t = m.tool("get_track_info", track_index=i)
        if not DEFAULT_TRACK.match(t["name"]) and not t["name"].startswith(TEST_PREFIX):
            problems.append("track %d is named %r" % (i, t["name"]))
        if any(s.get("has_clip") for s in t.get("clip_slots", [])):
            soft.append("track %d has clips" % i)
        if t.get("devices"):
            soft.append("track %d has devices" % i)
    if session.get("return_track_count", 0) > 2:
        problems.append("%d return tracks" % session["return_track_count"])
    print("Open set: %d tracks, %d returns, %.1f BPM" % (
        session["track_count"], session.get("return_track_count", 0), session["tempo"]))
    if problems or (soft and not force):
        print("REFUSING: this does not look like an empty set:\n  - " + "\n  - ".join(problems + soft))
        print("Open a new empty set (File > New Live Set) and run again."
              + ("" if problems else " --force overrides clips/devices only."))
        sys.exit(2)
    leftovers = [n for n in track_names(m) if n.startswith(TEST_PREFIX)]
    if leftovers:
        print("Note: leftover test tracks from an earlier run: %s" % leftovers)
    return session


def remove_test_tracks(m, start_count=None, start_returns=None):
    """Delete every track whose name starts with TEST_PREFIX, highest index first.

    With start_count, also delete tracks the test added past the set's starting
    track count that still have Live's default name and nothing on them: a test
    that died between create and rename would otherwise leave '5-Audio' behind,
    and the next run's empty-set guard refuses a 5-track set.
    """
    names = track_names(m)
    for i in reversed(range(len(names))):
        stray = False
        if start_count is not None and i >= start_count and DEFAULT_TRACK.match(names[i]):
            t = m.tool("get_track_info", track_index=i)
            stray = not t.get("devices") and not any(s.get("has_clip") for s in t.get("clip_slots", []))
        if names[i].startswith(TEST_PREFIX) or stray:
            step("cleanup: delete %s" % names[i],
                 lambda i=i: m.tool("delete_track", track_index=i, expected_name=names[i]))
    try:
        scenes = m.tool("get_scenes")["scenes"]
    except Exception:
        scenes = []
    for sc in reversed(scenes):
        if str(sc.get("name", "")).startswith(TEST_PREFIX):
            step("cleanup: delete scene %s" % sc["name"],
                 lambda sc=sc: m.tool("delete_scene", scene_index=sc["index"], expected_name=sc["name"],
                                      allow_clips=True))
    if start_returns is not None:
        rets = m.tool("get_mixer_state", include_routing=False)["returns"]
        for r in reversed(rets):
            if r["index"] >= start_returns:
                step("cleanup: delete return %s" % r["name"],
                     lambda r=r: m.tool("delete_track", track_type="return", track_index=r["index"],
                                        expected_name=r["name"]))


def parser(description):
    ap = argparse.ArgumentParser(description=description)
    ap.add_argument("--keep", action="store_true", help="leave the test tracks in the set")
    ap.add_argument("--force", action="store_true",
                    help="allow clips/devices on default-named tracks; track count and names are always checked")
    return ap


def run(description, body):
    """Parse args, start the server, guard the set, run body(m), clean up, report."""
    args = parser(description).parse_args()
    m = Mcp()
    try:
        session = guard_empty_set(m, args.force)  # reads only, so it goes first
        info = m.tool("get_remote_script_info")
        print("Remote Script %s (expected %s)" % (info.get("script_version"), info.get("expected_version")))
        if info.get("script_version") != info.get("expected_version"):
            print("Remote Script is stale: run scripts/deploy.sh, then restart Live.")
            sys.exit(2)
        try:
            body(m, args)
        finally:
            if not args.keep:
                remove_test_tracks(m, session["track_count"], session.get("return_track_count"))
    finally:
        m.close()
        for f in (m.safety_path, m.safety_path + ".tmp"):
            if os.path.exists(f):
                os.remove(f)
    print("\n%d passed, %d failed" % (len(PASS), len(FAIL)))
    for f in FAIL:
        print("  FAIL " + f)
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    # python3 scripts/live_harness.py --guard : exit 0 only when the open set is empty (reads only).
    if "--guard" in sys.argv:
        _m = Mcp()
        try:
            guard_empty_set(_m)
        finally:
            _m.close()
        print("OK: the open set is empty")
