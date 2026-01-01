"""Tests for async/sync transition in MCP server."""

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestSendCommandAsync:
    """Test the async wrapper for send_command."""

    @pytest.mark.asyncio
    async def test_send_command_async_calls_sync_in_thread(self, mock_tcp_server):
        """Test that send_command_async properly wraps sync call."""
        from MCP_Server.server import AbletonConnection

        mock_tcp_server.set_response(
            "get_session_info",
            {
                "status": "success",
                "result": {"tempo": 120.0, "track_count": 2},
            },
        )

        conn = AbletonConnection(host="localhost", port=mock_tcp_server.port)

        # Call the async method
        result = await conn.send_command_async("get_session_info")

        assert "tempo" in result
        assert result["tempo"] == 120.0

    @pytest.mark.asyncio
    async def test_send_command_async_with_params(self, mock_tcp_server):
        """Test async command with parameters."""
        from MCP_Server.server import AbletonConnection

        mock_tcp_server.set_response(
            "set_tempo", {"status": "success", "result": {"tempo": 140.0}}
        )

        conn = AbletonConnection(host="localhost", port=mock_tcp_server.port)
        result = await conn.send_command_async("set_tempo", {"tempo": 140.0})

        assert result["tempo"] == 140.0

    @pytest.mark.asyncio
    async def test_send_command_async_propagates_exception(self):
        """Test that exceptions from sync call propagate through async wrapper."""
        from MCP_Server.server import AbletonConnection

        conn = AbletonConnection(host="localhost", port=99999)  # Invalid port

        with pytest.raises(Exception):
            await conn.send_command_async("get_session_info")

    @pytest.mark.asyncio
    async def test_sequential_async_commands(self, mock_tcp_server):
        """Test multiple async commands work sequentially."""
        from MCP_Server.server import AbletonConnection

        mock_tcp_server.set_response(
            "get_session_info",
            {"status": "success", "result": {"tempo": 120.0}},
        )
        mock_tcp_server.set_response(
            "ping", {"status": "success", "result": {"status": "ok"}}
        )

        conn = AbletonConnection(host="localhost", port=mock_tcp_server.port)

        # Run commands sequentially (AbletonConnection uses a single socket)
        result1 = await conn.send_command_async("get_session_info")
        assert result1["tempo"] == 120.0

        # Need new connection for second command since server closes after each
        conn2 = AbletonConnection(host="localhost", port=mock_tcp_server.port)
        result2 = await conn2.send_command_async("ping")
        assert result2["status"] == "ok"


class TestAsyncToolEndpoints:
    """Test that MCP tool endpoints are properly async."""

    def test_all_tools_are_async(self):
        """Verify all MCP tool endpoints are async functions."""
        import inspect

        from MCP_Server import server

        # Find all functions decorated with @mcp.tool()
        # They should all be async
        async_tools = []
        for name, obj in inspect.getmembers(server):
            if inspect.iscoroutinefunction(obj):
                # Check if it looks like a tool endpoint
                if hasattr(obj, "__wrapped__") or "ctx" in str(
                    inspect.signature(obj).parameters
                ):
                    async_tools.append(name)

        # Known tool endpoints that should be async
        expected_async_tools = [
            "get_session_info",
            "get_track_info",
            "create_midi_track",
            "set_track_name",
            "create_clip",
            "add_notes_to_clip",
            "set_clip_name",
            "set_tempo",
            "load_instrument_or_effect",
            "fire_clip",
            "stop_clip",
            "start_playback",
            "stop_playback",
            "get_browser_tree",
            "get_browser_items_at_path",
            "load_drum_kit",
        ]

        # Verify these are all coroutine functions
        for tool_name in expected_async_tools:
            tool_func = getattr(server, tool_name, None)
            if tool_func:
                assert inspect.iscoroutinefunction(
                    tool_func
                ), f"{tool_name} should be async"

    @pytest.mark.asyncio
    async def test_get_session_info_uses_async(self, mock_tcp_server):
        """Test get_session_info tool uses async method."""
        from MCP_Server.server import AbletonConnection, get_session_info

        mock_tcp_server.set_response(
            "ping", {"status": "success", "result": {"status": "ok"}}
        )
        mock_tcp_server.set_response(
            "get_session_info",
            {
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
        )

        # Patch get_ableton_connection to return our test connection
        conn = AbletonConnection(host="localhost", port=mock_tcp_server.port)

        with patch("MCP_Server.server.get_ableton_connection", return_value=conn):
            ctx = MagicMock()
            result = await get_session_info(ctx)

        assert "tempo" in result
        parsed = json.loads(result)
        assert parsed["tempo"] == 120.0


class TestAnyioThreadPool:
    """Test that anyio thread pool is used correctly."""

    @pytest.mark.asyncio
    async def test_anyio_to_thread_is_used(self):
        """Verify send_command_async uses anyio.to_thread.run_sync."""
        import inspect

        from MCP_Server.server import AbletonConnection

        source = inspect.getsource(AbletonConnection.send_command_async)

        assert "anyio.to_thread.run_sync" in source

    @pytest.mark.asyncio
    async def test_blocking_call_runs_in_thread(self, mock_tcp_server):
        """Test that blocking socket calls run in a separate thread."""
        import threading

        from MCP_Server.server import AbletonConnection

        mock_tcp_server.set_response(
            "get_session_info",
            {"status": "success", "result": {"tempo": 120.0}},
        )

        conn = AbletonConnection(host="localhost", port=mock_tcp_server.port)

        main_thread = threading.current_thread()
        call_threads = []

        original_send = conn.send_command

        def track_thread(*args, **kwargs):
            call_threads.append(threading.current_thread())
            return original_send(*args, **kwargs)

        with patch.object(conn, "send_command", side_effect=track_thread):
            await conn.send_command_async("get_session_info")

        # The sync call should happen in a different thread (anyio worker thread)
        assert call_threads, "send_command should have been called"
        assert call_threads[0] != main_thread, "async call should run in worker thread, not main"
