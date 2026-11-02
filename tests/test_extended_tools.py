"""MCP side of the extended tools: each tool is called through FastMCP (so the
argument schema is exercised too) with the Ableton connection faked, and the
test checks the command and params that would go to Live."""

import asyncio
import json

import pytest

import MCP_Server.server as server


class FakeConnection(object):
    def __init__(self, response=None, raise_exc=None):
        self.response = {} if response is None else response
        self.raise_exc = raise_exc
        self.sent = []

    def send_command(self, command_type, params=None):
        self.sent.append((command_type, params or {}))
        if self.raise_exc is not None:
            raise self.raise_exc
        return self.response


@pytest.fixture
def conn(monkeypatch):
    def _make(response=None, raise_exc=None):
        c = FakeConnection(response, raise_exc)
        monkeypatch.setattr(server, "get_ableton_connection", lambda: c)
        return c
    return _make


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch):
    class _Dummy(object):
        def record_event(self, *a, **k):
            pass
    import MCP_Server.telemetry_decorator as td
    import MCP_Server.script_handshake as sh
    monkeypatch.setattr(td, "get_telemetry", lambda: _Dummy(), raising=False)
    monkeypatch.setattr(sh, "require_capability", lambda name: None)


def call(name, **args):
    """Call a registered tool the way an MCP client would; return its text."""
    result = asyncio.run(server.mcp.call_tool(name, args))
    blocks = result[0] if isinstance(result, tuple) else result
    return blocks[0].text


@pytest.mark.parametrize("tool", ["get_undo_state", "undo", "redo", "delete_track"])
def test_tool_is_registered(tool):
    names = {t.name for t in asyncio.run(server.mcp.list_tools())}
    assert tool in names


@pytest.mark.parametrize("tool", ["get_undo_state", "undo", "redo"])
def test_no_arg_tools_send_their_command(conn, tool):
    c = conn({"can_undo": True, "can_redo": False})
    assert json.loads(call(tool)) == {"can_undo": True, "can_redo": False}
    assert c.sent == [(tool, {})]


def test_delete_track_forwards_name_and_type(conn):
    c = conn({"deleted": "return", "index": 1, "name": "B-Delay", "remaining": 1})
    out = json.loads(call("delete_track", track_index=1, expected_name="B-Delay", track_type="return"))
    assert out["deleted"] == "return"
    assert c.sent == [("delete_track", {"track_index": 1, "expected_name": "B-Delay",
                                        "track_type": "return"})]


def test_delete_track_requires_expected_name(conn):
    conn({})
    with pytest.raises(Exception):
        call("delete_track", track_index=0)


def test_errors_from_live_come_back_as_error_text(conn):
    conn(raise_exc=RuntimeError("Nothing to undo"))
    assert call("undo") == "Error undoing: Nothing to undo"


def test_missing_capability_is_reported_without_sending(conn, monkeypatch):
    import MCP_Server.script_handshake as sh
    c = conn({})
    monkeypatch.setattr(sh, "require_capability", lambda name: "missing " + name)
    assert call("redo") == "missing redo"
    assert c.sent == []


def test_extended_writes_get_the_modifying_timeout():
    from MCP_Server.extended_tools import MODIFYING_COMMANDS
    assert {"undo", "redo", "delete_track"} <= MODIFYING_COMMANDS
