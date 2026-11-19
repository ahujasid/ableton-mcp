"""Error reporting and naming regressions (Remote Script 1.8.2).

* A refusal from Live (status "error") was re-wrapped as
  "Communication error with Ableton: ..." and dropped the socket, as if the
  connection had failed.
* get_session_info hardcoded the master track name as "Master" while the
  mixer tools returned Live's real name ("Main" in Live 12).
"""

import json
import socket
import types

import pytest

from MCP_Server.server import AbletonCommandError, AbletonConnection
from test_remote_script_bridge import _load_script_module, make_instance


@pytest.fixture(scope="module")
def script_module():
    return _load_script_module()


class _FakeSocket:
    def __init__(self):
        self.sent = []

    def sendall(self, data):
        self.sent.append(data)

    def settimeout(self, _timeout):
        pass


def _connection_replying(reply):
    conn = AbletonConnection(host="127.0.0.1", port=0)
    conn.sock = _FakeSocket()
    if isinstance(reply, Exception):
        def receive(_sock):
            raise reply
    else:
        def receive(_sock):
            return json.dumps(reply).encode("utf-8")
    conn.receive_full_response = receive
    return conn


def test_live_refusal_is_passed_through_unprefixed_and_keeps_socket():
    conn = _connection_replying(
        {"status": "error", "message": "The master track cannot be muted"})
    sock = conn.sock

    with pytest.raises(AbletonCommandError) as excinfo:
        conn.send_command("set_track_mute", {"track_type": "master"})

    assert str(excinfo.value) == "The master track cannot be muted"
    assert conn.sock is sock


def test_transport_failures_still_reported_and_reset_socket():
    conn = _connection_replying(socket.timeout())
    with pytest.raises(Exception, match="Timeout waiting for Ableton response"):
        conn.send_command("get_session_info")
    assert conn.sock is None

    conn = _connection_replying(ValueError("boom"))
    with pytest.raises(Exception, match="^Communication error with Ableton: boom$"):
        conn.send_command("get_session_info")
    assert conn.sock is None


def _song_with_master(name):
    param = lambda v: types.SimpleNamespace(value=v)
    master = types.SimpleNamespace(
        mixer_device=types.SimpleNamespace(volume=param(0.85), panning=param(0.0)))
    if name is not None:
        master.name = name
    return types.SimpleNamespace(
        tempo=120.0, signature_numerator=4, signature_denominator=4,
        tracks=[], return_tracks=[], master_track=master,
        is_playing=False, current_song_time=0.0, song_length=0.0,
        loop=False, loop_start=0.0, loop_length=4.0)


@pytest.mark.parametrize("live_name, expected", [
    ("Main", "Main"),      # Live 12
    ("Master", "Master"),  # Live 11
    (None, "Master"),      # attribute missing: fall back
])
def test_session_info_reports_live_master_name(script_module, live_name, expected):
    inst = make_instance(script_module)
    inst._song = _song_with_master(live_name)
    assert inst._get_session_info()["master_track"]["name"] == expected
