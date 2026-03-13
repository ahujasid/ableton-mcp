"""Tests for length-prefix framing protocol.

Verifies that the send_message/recv_message/recv_exact protocol functions
correctly handle:
- Simple dict roundtrips
- Large payloads (1MB+)
- Empty dict payloads
- Unicode payloads (instrument names)
- Malformed headers (incomplete)
- Oversized payload rejection (>10MB)
"""

import json
import socket
import struct
import threading

import pytest


# Reference implementation of the protocol functions.
# Tests verify this logic works correctly; grep-based tests in test_connection.py
# verify the actual source files use the same pattern.


def _recv_exact(sock: socket.socket, n: int) -> bytes | None:
    """Read exactly n bytes from socket."""
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            return None
        buf.extend(chunk)
    return bytes(buf)


def send_message(sock: socket.socket, data: dict) -> None:
    """Send a length-prefixed JSON message."""
    payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
    header = struct.pack(">I", len(payload))
    sock.sendall(header + payload)


def recv_message(sock: socket.socket, timeout: float = 15.0) -> dict:
    """Receive a length-prefixed JSON message."""
    sock.settimeout(timeout)
    header = _recv_exact(sock, 4)
    if not header:
        raise ConnectionError("Connection closed while reading header")
    length = struct.unpack(">I", header)[0]
    if length > 10 * 1024 * 1024:  # 10MB safety limit
        raise ValueError(f"Message too large: {length} bytes")
    payload = _recv_exact(sock, length)
    if not payload:
        raise ConnectionError("Connection closed while reading payload")
    return json.loads(payload.decode("utf-8"))


class TestProtocolRoundtrip:
    """Test send_message + recv_message roundtrips over socket pairs."""

    def test_send_recv_roundtrip(self) -> None:
        """Simple dict roundtrips correctly via length-prefix framing."""
        a, b = socket.socketpair()
        try:
            original = {"type": "get_session_info", "params": {"track_index": 3}}
            send_message(a, original)
            result = recv_message(b)
            assert result == original
        finally:
            a.close()
            b.close()

    def test_large_payload(self) -> None:
        """1MB payload roundtrips correctly via length-prefix framing."""
        a, b = socket.socketpair()
        try:
            # Create a ~1MB payload
            large_data = {"data": "x" * (1024 * 1024)}
            result_holder: list[dict] = []
            error_holder: list[Exception] = []

            def sender():
                try:
                    send_message(a, large_data)
                except Exception as e:
                    error_holder.append(e)

            t = threading.Thread(target=sender)
            t.start()
            result = recv_message(b, timeout=30.0)
            t.join(timeout=5.0)
            assert not error_holder, f"Sender raised: {error_holder[0]}"
            assert result == large_data
        finally:
            a.close()
            b.close()

    def test_empty_dict_payload(self) -> None:
        """Empty dict {} roundtrips correctly."""
        a, b = socket.socketpair()
        try:
            send_message(a, {})
            result = recv_message(b)
            assert result == {}
        finally:
            a.close()
            b.close()

    def test_unicode_payload(self) -> None:
        """Dict with Unicode characters (instrument names) roundtrips correctly."""
        a, b = socket.socketpair()
        try:
            original = {
                "type": "load_instrument",
                "name": "Glockenspiel \u00fc\u00e4\u00f6",
                "category": "\u30d4\u30a2\u30ce",
                "emoji_test": "\U0001f3b5\U0001f3b6",
            }
            send_message(a, original)
            result = recv_message(b)
            assert result == original
        finally:
            a.close()
            b.close()

    def test_malformed_header(self) -> None:
        """Incomplete header (less than 4 bytes then close) raises ConnectionError."""
        a, b = socket.socketpair()
        try:
            # Send only 2 bytes then close
            a.sendall(b"\x00\x01")
            a.close()
            with pytest.raises(ConnectionError, match="reading header"):
                recv_message(b)
        finally:
            try:
                a.close()
            except OSError:
                pass
            b.close()

    def test_oversized_payload_rejected(self) -> None:
        """Length header claiming >10MB raises ValueError."""
        a, b = socket.socketpair()
        try:
            # Pack a length of 11MB
            header = struct.pack(">I", 11 * 1024 * 1024)
            a.sendall(header)
            with pytest.raises(ValueError, match="too large"):
                recv_message(b)
        finally:
            a.close()
            b.close()

    def test_multiple_messages_sequential(self) -> None:
        """Multiple messages can be sent and received sequentially."""
        a, b = socket.socketpair()
        try:
            messages = [
                {"type": "ping"},
                {"type": "get_session_info"},
                {"type": "set_tempo", "params": {"tempo": 140.0}},
            ]
            for msg in messages:
                send_message(a, msg)
            for msg in messages:
                result = recv_message(b)
                assert result == msg
        finally:
            a.close()
            b.close()
