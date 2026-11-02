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


EXTENDED_TOOLS = [
    "get_undo_state", "undo", "redo", "delete_track",
    "get_mixer_state", "get_track_routing", "set_track_routing", "set_track_monitoring",
    "set_track_mixer", "get_track_meters", "back_to_arrangement",
    "get_automation_overrides", "re_enable_automation",
    "get_set_info", "get_device_chain", "get_device_routing", "get_signal_path", "get_clip_info",
    "get_scenes", "set_device_parameter_value", "set_device_active", "set_device_routing",
    "delete_device", "move_device", "set_clip_properties", "duplicate_track", "create_return_track",
    "create_scene", "duplicate_scene", "delete_scene", "set_scene", "fire_scene", "set_track_look",
    "get_transport", "set_song_settings", "jump_to_cue", "stop_all_clips", "capture_midi", "get_notes",
    "modify_notes", "remove_notes", "edit_clip",
]


def test_every_remote_command_has_a_tool():
    from live_fakes import load_script_module
    assert set(load_script_module().EXTENDED_COMMANDS) == set(EXTENDED_TOOLS)


@pytest.mark.parametrize("tool", EXTENDED_TOOLS)
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


def test_set_track_mixer_forwards_only_what_was_given(conn):
    c = conn({"changed": ["volume"]})
    call("set_track_mixer", track_index=2, volume_db=-6.0, sends={"A": 0.25})
    (cmd, params), = c.sent
    assert cmd == "set_track_mixer"
    assert params["volume_db"] == -6.0 and params["sends"] == {"A": 0.25}
    assert params["volume"] is None and params["mute"] is None and params["exclusive_solo"] is False


def test_set_track_routing_forwards_names(conn):
    c = conn({})
    call("set_track_routing", track_index=1, input_type="Ext. In", input_channel="3/4")
    assert c.sent[0][1] == {"track_index": 1, "track_type": "track", "input_type": "Ext. In",
                            "input_channel": "3/4", "output_type": None, "output_channel": None}


def test_get_track_meters_forwards_track_list(conn):
    c = conn({"tracks": []})
    call("get_track_meters", tracks=[{"track_type": "master"}], duration_ms=500)
    assert c.sent[0] == ("get_track_meters", {"tracks": [{"track_type": "master"}], "duration_ms": 500,
                                              "interval_ms": 50, "threshold": 0.001})


def test_re_enable_automation_without_track_is_song_wide(conn):
    c = conn({})
    call("re_enable_automation")
    call("re_enable_automation", track_type="return", track_index=1)
    assert c.sent == [("re_enable_automation", {}),
                      ("re_enable_automation", {"track_index": 1, "track_type": "return"})]


def test_set_track_monitoring_forwards_state(conn):
    c = conn({})
    call("set_track_monitoring", track_index=3, state="in")
    assert c.sent == [("set_track_monitoring", {"track_index": 3, "state": "in"})]


def test_meter_watch_fits_inside_the_socket_timeout():
    import inspect
    from live_fakes import load_script_module
    src = inspect.getsource(server.AbletonConnection._send_command_locked)
    assert '"get_track_meters": 15.0' in src
    assert load_script_module().MAX_METER_DURATION_MS / 1000.0 < 15.0
