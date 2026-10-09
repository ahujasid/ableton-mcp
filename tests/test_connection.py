"""Socket response regressions; no Live instance or network is required."""

import json
import socket

import pytest

from MCP_Server.server import AbletonConnection


class ResponseSocket:
    def __init__(self, chunks):
        self.chunks = iter(chunks)
        self.timeouts = []
        self.closed = False
        self.commands = []
        self.timeout = None
        self.response_delay = 0.0

    def connect(self, address):
        pass

    def settimeout(self, timeout):
        self.timeouts.append(timeout)
        self.timeout = timeout

    def sendall(self, data):
        self.commands.append(json.loads(data))

    def recv(self, size):
        if self.timeout is not None and self.response_delay > self.timeout:
            raise socket.timeout("Response exceeds configured timeout")
        chunk = next(self.chunks, b"")
        if isinstance(chunk, Exception):
            raise chunk
        return chunk

    def close(self):
        self.closed = True


def response_bytes(result):
    return json.dumps({"status": "success", "result": result},
                      ensure_ascii=False).encode("utf-8")


@pytest.mark.parametrize("command,timeout", [
    ("get_session_info", 10.0),
    ("set_tempo", 15.0),
    ("create_audio_clip", 65.0),
])
def test_response_preserves_command_timeout(command, timeout):
    sock = ResponseSocket([response_bytes({"complete": True})])
    connection = AbletonConnection("localhost", 9877, sock=sock)

    assert connection.send_command(command) == {"complete": True}
    assert sock.timeout == timeout


def test_audio_import_can_reply_after_fifteen_seconds():
    sock = ResponseSocket([response_bytes({"complete": True})])
    sock.response_delay = 20.0
    connection = AbletonConnection("localhost", 9877, sock=sock)

    assert connection.send_command("create_audio_clip") == {"complete": True}


def test_response_split_inside_utf8_character_is_received():
    payload = response_bytes({"name": "café"})
    split = payload.index(b"\xc3") + 1
    sock = ResponseSocket([payload[:split], payload[split:]])
    connection = AbletonConnection("localhost", 9877, sock=sock)

    assert connection.send_command("get_track_info") == {"name": "café"}
    assert not sock.closed


@pytest.mark.parametrize("failure", [
    socket.timeout("late reply"),
    ConnectionResetError("reset"),
    b"",
])
def test_incomplete_response_closes_socket_before_next_command(failure, monkeypatch):
    previous_socket = ResponseSocket([b'{"status":', failure])
    connection = AbletonConnection("localhost", 9877, sock=previous_socket)

    with pytest.raises(Exception):
        connection.send_command("get_session_info")

    assert previous_socket.closed
    assert connection.sock is None

    replacement_socket = ResponseSocket([response_bytes({"tempo": 120})])
    monkeypatch.setattr(socket, "socket", lambda *args: replacement_socket)
    assert connection.send_command("get_session_info") == {"tempo": 120}


def test_invalid_utf8_closes_socket_without_waiting_for_more_data():
    sock = ResponseSocket([b'{"status":"success","result":"\xff"}'])
    connection = AbletonConnection("localhost", 9877, sock=sock)

    with pytest.raises(Exception, match="invalid start byte"):
        connection.send_command("get_track_info")

    assert sock.closed
    assert connection.sock is None


def test_failed_connect_closes_created_socket(monkeypatch):
    sock = ResponseSocket([])

    def refuse_connection(address):
        raise ConnectionRefusedError("Live is unavailable")

    sock.connect = refuse_connection
    monkeypatch.setattr(socket, "socket", lambda *args: sock)
    connection = AbletonConnection("localhost", 9877)

    assert not connection.connect()
    assert sock.closed
    assert connection.sock is None
