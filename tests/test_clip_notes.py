"""
Server-side tests for the clip-notes read/clear/write loop
(get_clip_notes, clear_notes_from_clip, add_notes_to_clip).
These exercise the real MCP_Server.server tool functions
with the Ableton socket connection mocked, so they run anywhere — no Ableton,
no network.

Run from the repo root:
    uv run pytest -v
    # or, in any env that has the server's deps:
    python -m pytest -v
"""

import json
import pytest

import MCP_Server.server as server


# --------------------------------------------------------------------------
# Test doubles
# --------------------------------------------------------------------------

class FakeConnection:
    """Stand-in for AbletonConnection. Records every command sent and returns
    a canned response (or raises) so we can test the tool logic in isolation."""

    def __init__(self, response=None, raise_exc=None):
        self.response = {} if response is None else response
        self.raise_exc = raise_exc
        self.sent = []  # list of (command_type, params) tuples

    def send_command(self, command_type, params=None):
        self.sent.append((command_type, params or {}))
        if self.raise_exc is not None:
            raise self.raise_exc
        return self.response


@pytest.fixture
def fake_conn(monkeypatch):
    """Factory: install a FakeConnection as the active Ableton connection and
    return it so the test can inspect what was sent."""
    def _make(response=None, raise_exc=None):
        conn = FakeConnection(response=response, raise_exc=raise_exc)
        monkeypatch.setattr(server, "get_ableton_connection", lambda: conn)
        return conn
    return _make


@pytest.fixture(autouse=True)
def _silence_telemetry(monkeypatch):
    """Make the telemetry side-effect in the tool decorators a no-op, so tests
    are hermetic and never touch the network."""
    class _Dummy:
        def record_event(self, *a, **k):
            pass
    import MCP_Server.telemetry_decorator as td
    monkeypatch.setattr(td, "get_telemetry", lambda: _Dummy(), raising=False)


@pytest.fixture(autouse=True)
def _script_capabilities_available(monkeypatch):
    """Tools gate on require_capability(), which needs a live Remote Script
    handshake. Report every capability as present so the tests exercise the
    tool body rather than the missing-script early return."""
    import MCP_Server.script_handshake as sh
    monkeypatch.setattr(sh, "require_capability", lambda name: None)


# A representative clip payload as the Remote Script would return it.
SAMPLE_NOTES = [
    {"pitch": 36, "start_time": 0.0, "duration": 0.25, "velocity": 100, "mute": False, "note_id": 1},
    {"pitch": 38, "start_time": 1.0, "duration": 0.50, "velocity": 90, "mute": True, "note_id": 2},
    {"pitch": 42, "start_time": 2.0, "duration": 0.25, "velocity": 80, "mute": False, "note_id": 3},
]


def _sample_response(notes=SAMPLE_NOTES, name="Fred Pattern", length=8.0):
    return {"clip_name": name, "length": length,
            "note_count": len(notes), "notes": notes}


# --------------------------------------------------------------------------
# get_clip_notes  (the reader shipped on main)
# --------------------------------------------------------------------------

def test_read_sends_correct_command_and_params(fake_conn):
    conn = fake_conn(response=_sample_response())
    server.get_clip_notes(None, track_index=2, clip_index=5)
    assert conn.sent == [("get_clip_notes", {"track_index": 2, "clip_index": 5})]


def test_read_returns_the_payload_as_json(fake_conn):
    fake_conn(response=_sample_response(name="Fred Pattern", length=8.0))
    payload = json.loads(server.get_clip_notes(None, 0, 0))
    assert payload["clip_name"] == "Fred Pattern"
    assert payload["length"] == 8.0
    assert payload["note_count"] == 3
    assert payload["notes"] == SAMPLE_NOTES


def test_read_empty_clip_is_zero_notes_not_an_error(fake_conn):
    fake_conn(response=_sample_response(notes=[]))
    payload = json.loads(server.get_clip_notes(None, 0, 0))
    assert payload["notes"] == []
    assert payload["note_count"] == 0


def test_read_connection_error_is_caught_and_reported(fake_conn):
    fake_conn(raise_exc=Exception("boom"))
    out = server.get_clip_notes(None, 0, 0)
    assert out.startswith("Error getting clip notes:")
    assert "boom" in out


def test_read_output_feeds_straight_into_add_notes(fake_conn):
    """The reader's note dicts are shaped exactly as add_notes_to_clip wants."""
    conn = fake_conn(response=_sample_response())
    notes = json.loads(server.get_clip_notes(None, 0, 0))["notes"]
    conn.response = {"note_count": len(notes)}
    server.add_notes_to_clip(None, 0, 0, notes)
    written = [c for c in conn.sent if c[0] == "add_notes_to_clip"][0][1]["notes"]
    assert written == SAMPLE_NOTES


def test_add_notes_forwards_track_clip_and_notes(fake_conn):
    conn = fake_conn(response={"note_count": 1})
    one = [{"pitch": 60, "start_time": 0.0, "duration": 1.0, "velocity": 100, "mute": False}]
    server.add_notes_to_clip(None, 3, 7, one)
    assert conn.sent == [("add_notes_to_clip",
                          {"track_index": 3, "clip_index": 7, "notes": one})]


# --------------------------------------------------------------------------
# clear_notes_from_clip  +  the true replace loop
# --------------------------------------------------------------------------

def test_clear_sends_correct_command_and_params(fake_conn):
    conn = fake_conn(response={"clip_name": "Fred", "cleared_count": 3})
    server.clear_notes_from_clip(None, track_index=1, clip_index=4)
    assert conn.sent == [("clear_notes_from_clip", {"track_index": 1, "clip_index": 4})]


def test_clear_output_reports_count_and_name(fake_conn):
    fake_conn(response={"clip_name": "Fred Pattern", "cleared_count": 5})
    out = server.clear_notes_from_clip(None, 0, 0)
    assert "Cleared 5 note" in out
    assert "Fred Pattern" in out


def test_clear_connection_error_is_reported(fake_conn):
    fake_conn(raise_exc=Exception("boom"))
    out = server.clear_notes_from_clip(None, 0, 0)
    assert out.startswith("Error clearing notes from clip:")
    assert "boom" in out


def test_true_replace_loop_read_clear_add(fake_conn):
    """The whole point of clear_notes_from_clip: read -> modify -> clear ->
    write yields a clip that holds ONLY the modified notes (not the union)."""
    conn = fake_conn(response=_sample_response())

    # read
    notes = json.loads(server.get_clip_notes(None, 0, 0))["notes"]

    # modify: transpose up a fifth
    for n in notes:
        n["pitch"] += 7

    # clear, then write the modified notes back
    conn.response = {"clip_name": "Fred Pattern", "cleared_count": 3}
    server.clear_notes_from_clip(None, 0, 0)
    conn.response = {"note_count": 3}
    server.add_notes_to_clip(None, 0, 0, notes)

    # the command sequence is read -> clear -> add, in that order
    assert [c[0] for c in conn.sent] == [
        "get_clip_notes", "clear_notes_from_clip", "add_notes_to_clip",
    ]
    # clear targeted the same slot
    clear_cmd = [c for c in conn.sent if c[0] == "clear_notes_from_clip"][0]
    assert clear_cmd[1] == {"track_index": 0, "clip_index": 0}
    # and the only notes written back are the transposed ones
    written = [c for c in conn.sent if c[0] == "add_notes_to_clip"][0][1]["notes"]
    assert [n["pitch"] for n in written] == [43, 45, 49]
