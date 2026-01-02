"""Tests for conftest.py fixture coverage."""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestMockSocket:
    """Test MockSocket class methods for coverage."""

    def test_settimeout(self, mock_socket):
        """Test MockSocket.settimeout."""
        mock_socket.settimeout(5.0)
        assert mock_socket.timeout == 5.0

    def test_sendall_when_closed(self, mock_socket):
        """Test MockSocket.sendall raises when closed."""
        mock_socket.close()
        with pytest.raises(ConnectionError):
            mock_socket.sendall(b"test")

    def test_sendall_when_open(self, mock_socket):
        """Test MockSocket.sendall stores data."""
        mock_socket.sendall(b"test data")
        assert b"test data" in mock_socket.sent_data

    def test_recv_when_closed(self, mock_socket):
        """Test MockSocket.recv raises when closed."""
        mock_socket.close()
        with pytest.raises(ConnectionError):
            mock_socket.recv(1024)

    def test_recv_with_queued_data(self, mock_socket):
        """Test MockSocket.recv returns queued data."""
        mock_socket.queue_response({"status": "success"})
        data = mock_socket.recv(1024)
        parsed = json.loads(data.decode("utf-8"))
        assert parsed["status"] == "success"

    def test_recv_empty_queue(self, mock_socket):
        """Test MockSocket.recv returns empty when no data queued."""
        data = mock_socket.recv(1024)
        assert data == b""

    def test_queue_response(self, mock_socket):
        """Test MockSocket.queue_response."""
        mock_socket.queue_response({"key": "value"})
        assert len(mock_socket.recv_queue) == 1


class TestMockTCPServer:
    """Test MockTCPServer class for coverage."""

    def test_server_handles_client_exception(self, mock_tcp_server):
        """Test that server handles client exceptions gracefully."""
        # This tests the exception handling in _serve and _handle_client
        import socket

        # Connect and send invalid data that will cause an exception
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            client.connect(("localhost", mock_tcp_server.port))
            client.sendall(b"not valid json")
            # Server should handle this gracefully
        finally:
            client.close()

    def test_server_default_response(self, mock_tcp_server):
        """Test server returns default response for unknown commands."""
        import socket

        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            client.connect(("localhost", mock_tcp_server.port))
            client.sendall(json.dumps({"type": "unknown_command", "params": {}}).encode())
            client.settimeout(5.0)
            data = client.recv(8192)
            response = json.loads(data.decode("utf-8"))
            assert response["status"] == "success"
        finally:
            client.close()

    def test_server_set_response(self, mock_tcp_server):
        """Test server.set_response sets up command responses."""
        mock_tcp_server.set_response("test_cmd", {"status": "success", "result": {"test": True}})
        assert "test_cmd" in mock_tcp_server.responses

    def test_server_stores_received_commands(self, mock_tcp_server):
        """Test server stores received commands."""
        import socket

        mock_tcp_server.set_response("ping", {"status": "success", "result": {}})

        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            client.connect(("localhost", mock_tcp_server.port))
            client.sendall(json.dumps({"type": "ping", "params": {}}).encode())
            client.settimeout(5.0)
            client.recv(8192)
        finally:
            client.close()

        # Give server time to process
        import time
        time.sleep(0.1)

        assert len(mock_tcp_server.received_commands) > 0
        assert mock_tcp_server.received_commands[-1]["type"] == "ping"

    def test_server_stop_with_thread(self, mock_tcp_server):
        """Test server.stop properly stops thread."""
        # Server is already running from fixture
        assert mock_tcp_server.running
        mock_tcp_server.stop()
        assert not mock_tcp_server.running

    def test_server_stop_handles_socket_error(self):
        """Test server.stop handles socket close errors."""
        from tests.conftest import MockTCPServer

        server = MockTCPServer()
        server.start()
        # Force close the socket before stop to test error handling
        server.server_socket.close()
        server.stop()  # Should not raise
        assert not server.running
