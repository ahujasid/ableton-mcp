"""Shared fixtures for ableton-mcp tests."""

import json
import socket
import threading
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_ableton_connection():
    """Create a mock Ableton connection for MCP server tests."""
    with patch("MCP_Server.server.get_ableton_connection") as mock_get_conn:
        mock_conn = MagicMock()
        mock_conn.send_command_async = AsyncMock()
        mock_get_conn.return_value = mock_conn
        yield mock_conn


class MockSocket:
    """Mock socket for testing without real network connections."""

    def __init__(self):
        self.connected = False
        self.sent_data = []
        self.recv_queue = []
        self.timeout = None
        self.closed = False

    def connect(self, address):
        self.connected = True
        self.address = address

    def close(self):
        self.closed = True
        self.connected = False

    def settimeout(self, timeout):
        self.timeout = timeout

    def sendall(self, data):
        if self.closed:
            raise ConnectionError("Socket is closed")
        self.sent_data.append(data)

    def recv(self, buffer_size):
        if self.closed:
            raise ConnectionError("Socket is closed")
        if self.recv_queue:
            return self.recv_queue.pop(0)
        return b""

    def queue_response(self, response: dict):
        """Queue a JSON response to be returned by recv."""
        self.recv_queue.append(json.dumps(response).encode("utf-8"))


@pytest.fixture
def mock_socket():
    """Provide a mock socket instance."""
    return MockSocket()


@pytest.fixture
def mock_socket_module(mock_socket):
    """Patch socket module to return mock socket."""
    with patch("socket.socket") as mock_socket_class:
        mock_socket_class.return_value = mock_socket
        yield mock_socket


class MockTCPServer:
    """Simple TCP server for integration-style tests."""

    def __init__(self, host="localhost", port=0):
        self.host = host
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((host, port))
        self.port = self.server_socket.getsockname()[1]
        self.server_socket.listen(1)
        self.running = False
        self.thread = None
        self.responses = {}
        self.received_commands = []

    def set_response(self, command_type: str, response: dict):
        """Set response for a specific command type."""
        self.responses[command_type] = response

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._serve)
        self.thread.daemon = True
        self.thread.start()

    def stop(self):
        self.running = False
        try:
            self.server_socket.close()
        except Exception:
            pass
        if self.thread:
            self.thread.join(timeout=1.0)

    def _serve(self):
        self.server_socket.settimeout(0.5)
        while self.running:
            try:
                client, _ = self.server_socket.accept()
                self._handle_client(client)
            except TimeoutError:
                continue
            except Exception:
                break

    def _handle_client(self, client):
        try:
            client.settimeout(5.0)
            data = client.recv(8192)
            if data:
                command = json.loads(data.decode("utf-8"))
                self.received_commands.append(command)
                command_type = command.get("type", "")

                if command_type in self.responses:
                    response = self.responses[command_type]
                else:
                    response = {"status": "success", "result": {}}

                client.sendall(json.dumps(response).encode("utf-8"))
        except Exception:
            pass
        finally:
            try:
                client.close()
            except Exception:
                pass


@pytest.fixture
def mock_tcp_server():
    """Provide a mock TCP server for integration tests."""
    server = MockTCPServer()
    server.start()
    yield server
    server.stop()


@pytest.fixture
def mock_ableton_responses():
    """Common Ableton response fixtures."""
    return {
        "ping": {"status": "success", "result": {"status": "ok"}},
        "get_session_info": {
            "status": "success",
            "result": {
                "tempo": 120.0,
                "signature_numerator": 4,
                "signature_denominator": 4,
                "track_count": 2,
                "return_track_count": 2,
                "master_track": {"name": "Master", "volume": 0.85, "panning": 0.0},
            },
        },
        "create_midi_track": {
            "status": "success",
            "result": {"index": 0, "name": "1-MIDI"},
        },
        "set_tempo": {"status": "success", "result": {"tempo": 140.0}},
    }
