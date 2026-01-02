"""Additional tests for 100% server.py coverage."""

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from MCP_Server.server import AbletonConnection


class TestReceiveFullResponseEdgeCases:
    """Test edge cases in receive_full_response."""

    def test_timeout_immediately_with_no_data(self):
        """Test immediate timeout with no data at all."""
        conn = AbletonConnection(host="localhost", port=9877)

        mock_sock = MagicMock()
        # First recv raises timeout
        mock_sock.recv.side_effect = TimeoutError("Socket timeout")

        with pytest.raises(Exception) as exc_info:
            conn.receive_full_response(mock_sock)

        assert "No data" in str(exc_info.value)

    def test_timeout_with_partial_data(self):
        """Test timeout during receive with partial valid JSON."""
        conn = AbletonConnection(host="localhost", port=9877)

        mock_sock = MagicMock()
        # Send partial JSON, then timeout, leaving incomplete data
        partial_json = '{"status": "success"'  # Missing closing brace

        call_count = [0]

        def recv_side_effect(_):
            call_count[0] += 1
            if call_count[0] == 1:
                return partial_json.encode("utf-8")
            raise TimeoutError("Socket timeout")

        mock_sock.recv.side_effect = recv_side_effect

        with pytest.raises(Exception) as exc_info:
            conn.receive_full_response(mock_sock)

        assert "Incomplete JSON" in str(exc_info.value)

    def test_timeout_with_complete_data(self):
        """Test timeout after receiving complete JSON."""
        conn = AbletonConnection(host="localhost", port=9877)

        mock_sock = MagicMock()
        complete_json = '{"status": "success", "result": {}}'

        call_count = [0]

        def recv_side_effect(_):
            call_count[0] += 1
            if call_count[0] == 1:
                return complete_json.encode("utf-8")
            raise TimeoutError("Socket timeout")

        mock_sock.recv.side_effect = recv_side_effect

        # Should succeed because we got complete JSON before timeout
        result = conn.receive_full_response(mock_sock)
        parsed = json.loads(result.decode("utf-8"))
        assert parsed["status"] == "success"

    def test_connection_closed_after_partial_data(self):
        """Test connection closed (empty chunk) after receiving partial data."""
        conn = AbletonConnection(host="localhost", port=9877)

        mock_sock = MagicMock()
        # Send partial JSON, then empty chunk (connection closed)
        partial_json = '{"status": "success"'  # Missing closing brace

        call_count = [0]

        def recv_side_effect(_):
            call_count[0] += 1
            if call_count[0] == 1:
                return partial_json.encode("utf-8")
            return b""  # Empty chunk = connection closed

        mock_sock.recv.side_effect = recv_side_effect

        with pytest.raises(Exception) as exc_info:
            conn.receive_full_response(mock_sock)

        # Should fail with incomplete JSON or similar error
        assert "Incomplete" in str(exc_info.value) or "JSON" in str(exc_info.value)

    def test_connection_closed_after_complete_data(self):
        """Test connection closed after receiving complete JSON data."""
        conn = AbletonConnection(host="localhost", port=9877)

        mock_sock = MagicMock()
        complete_json = '{"status": "success", "result": {}}'

        call_count = [0]

        def recv_side_effect(_):
            call_count[0] += 1
            if call_count[0] == 1:
                return complete_json.encode("utf-8")
            return b""  # Empty chunk = connection closed

        mock_sock.recv.side_effect = recv_side_effect

        # Should succeed because we got complete JSON
        result = conn.receive_full_response(mock_sock)
        parsed = json.loads(result.decode("utf-8"))
        assert parsed["status"] == "success"

    def test_timeout_after_complete_chunks_via_break(self):
        """Test that timeout after receiving chunks leads to return at line 98."""
        conn = AbletonConnection(host="localhost", port=9877)

        mock_sock = MagicMock()
        # Send complete JSON in chunks, then timeout
        json_part1 = '{"status":'
        json_part2 = '"success"}'

        call_count = [0]

        def recv_side_effect(_):
            call_count[0] += 1
            if call_count[0] == 1:
                return json_part1.encode("utf-8")
            elif call_count[0] == 2:
                return json_part2.encode("utf-8")
            raise TimeoutError("Socket timeout")

        mock_sock.recv.side_effect = recv_side_effect

        result = conn.receive_full_response(mock_sock)
        parsed = json.loads(result.decode("utf-8"))
        assert parsed["status"] == "success"

    def test_connection_error_during_receive(self):
        """Test connection error during receive."""
        conn = AbletonConnection(host="localhost", port=9877)

        mock_sock = MagicMock()
        mock_sock.recv.side_effect = ConnectionResetError("Connection reset")

        with pytest.raises(Exception):
            conn.receive_full_response(mock_sock)

    def test_broken_pipe_during_receive(self):
        """Test broken pipe during receive."""
        conn = AbletonConnection(host="localhost", port=9877)

        mock_sock = MagicMock()
        mock_sock.recv.side_effect = BrokenPipeError("Broken pipe")

        with pytest.raises(Exception):
            conn.receive_full_response(mock_sock)

    def test_no_data_received(self):
        """Test receiving no data at all."""
        conn = AbletonConnection(host="localhost", port=9877)

        mock_sock = MagicMock()
        mock_sock.recv.return_value = b""

        with pytest.raises(Exception) as exc_info:
            conn.receive_full_response(mock_sock)

        assert "Connection closed" in str(exc_info.value) or "No data" in str(exc_info.value)

    def test_timeout_with_no_chunks(self):
        """Test timeout when no data received at all."""
        conn = AbletonConnection(host="localhost", port=9877)

        mock_sock = MagicMock()
        mock_sock.recv.side_effect = TimeoutError("Immediate timeout")

        with pytest.raises(Exception) as exc_info:
            conn.receive_full_response(mock_sock)

        assert "No data" in str(exc_info.value)


class TestSendCommandErrorHandling:
    """Test error handling in send_command."""

    def test_timeout_error_resets_socket(self):
        """Test that timeout error resets socket."""
        conn = AbletonConnection(host="localhost", port=9877)

        mock_sock = MagicMock()
        mock_sock.sendall = MagicMock()
        mock_sock.settimeout = MagicMock()

        conn.sock = mock_sock

        with patch.object(conn, "receive_full_response", side_effect=TimeoutError("Timeout")):
            with pytest.raises(Exception) as exc_info:
                conn.send_command("get_session_info")

            assert "Timeout" in str(exc_info.value)
            assert conn.sock is None

    def test_connection_error_resets_socket(self):
        """Test that connection error resets socket."""
        conn = AbletonConnection(host="localhost", port=9877)

        mock_sock = MagicMock()
        conn.sock = mock_sock

        with patch.object(
            conn, "receive_full_response", side_effect=ConnectionError("Lost connection")
        ):
            with pytest.raises(Exception) as exc_info:
                conn.send_command("get_session_info")

            assert "Connection" in str(exc_info.value)
            assert conn.sock is None

    def test_broken_pipe_resets_socket(self):
        """Test that broken pipe error resets socket."""
        conn = AbletonConnection(host="localhost", port=9877)

        mock_sock = MagicMock()
        conn.sock = mock_sock

        with patch.object(conn, "receive_full_response", side_effect=BrokenPipeError("Pipe broken")):
            with pytest.raises(Exception) as exc_info:
                conn.send_command("get_session_info")

            assert "Connection" in str(exc_info.value) or "lost" in str(exc_info.value).lower()
            assert conn.sock is None

    def test_connection_reset_resets_socket(self):
        """Test that connection reset error resets socket."""
        conn = AbletonConnection(host="localhost", port=9877)

        mock_sock = MagicMock()
        conn.sock = mock_sock

        with patch.object(
            conn, "receive_full_response", side_effect=ConnectionResetError("Reset")
        ):
            with pytest.raises(Exception) as exc_info:
                conn.send_command("get_session_info")

            assert "Connection" in str(exc_info.value)
            assert conn.sock is None

    def test_json_decode_error_resets_socket(self):
        """Test that JSON decode error resets socket."""
        conn = AbletonConnection(host="localhost", port=9877)

        mock_sock = MagicMock()
        conn.sock = mock_sock

        # Return invalid JSON
        with patch.object(conn, "receive_full_response", return_value=b"not valid json"):
            with pytest.raises(Exception) as exc_info:
                conn.send_command("get_session_info")

            assert "Invalid" in str(exc_info.value) or "JSON" in str(exc_info.value)
            assert conn.sock is None

    def test_generic_exception_resets_socket(self):
        """Test that generic exceptions reset socket."""
        conn = AbletonConnection(host="localhost", port=9877)

        mock_sock = MagicMock()
        conn.sock = mock_sock

        with patch.object(conn, "receive_full_response", side_effect=Exception("Unknown error")):
            with pytest.raises(Exception) as exc_info:
                conn.send_command("get_session_info")

            assert "Communication error" in str(exc_info.value) or "Unknown" in str(exc_info.value)
            assert conn.sock is None


class TestGetAbletonConnectionRetryLogic:
    """Test get_ableton_connection retry logic."""

    def test_ping_failure_triggers_reconnect(self):
        """Test that ping failure triggers reconnection."""
        import MCP_Server.server

        # Set up an existing connection that will fail ping
        mock_existing = MagicMock()
        mock_existing.sock = MagicMock()
        mock_existing.sock.settimeout = MagicMock()
        mock_existing.sock.sendall = MagicMock()
        mock_existing.receive_full_response = MagicMock(
            side_effect=Exception("Ping failed")
        )
        mock_existing.disconnect = MagicMock()

        MCP_Server.server._ableton_connection = mock_existing

        # The ping failure will cause disconnect and retry - mock the reconnection too
        with patch("MCP_Server.server.AbletonConnection") as MockConn:
            mock_new = MagicMock()
            mock_new.connect.return_value = False
            MockConn.return_value = mock_new

            with patch("time.sleep"), pytest.raises(Exception):
                MCP_Server.server.get_ableton_connection()

        # Cleanup
        MCP_Server.server._ableton_connection = None

    def test_ping_returns_error_status(self):
        """Test that ping returning error status triggers reconnection."""
        import MCP_Server.server

        mock_existing = MagicMock()
        mock_existing.sock = MagicMock()
        mock_existing.sock.settimeout = MagicMock()
        mock_existing.sock.sendall = MagicMock()
        mock_existing.receive_full_response = MagicMock(
            return_value=json.dumps({"status": "error", "message": "Not ok"}).encode()
        )
        mock_existing.disconnect = MagicMock()

        MCP_Server.server._ableton_connection = mock_existing

        # Mock the reconnection attempts to also fail
        with patch("MCP_Server.server.AbletonConnection") as MockConn:
            mock_new = MagicMock()
            mock_new.connect.return_value = False
            MockConn.return_value = mock_new

            with patch("time.sleep"), pytest.raises(Exception):
                MCP_Server.server.get_ableton_connection()

        MCP_Server.server._ableton_connection = None

    def test_disconnect_error_during_reconnect(self):
        """Test that disconnect errors are handled during reconnect."""
        import MCP_Server.server

        mock_existing = MagicMock()
        mock_existing.sock = MagicMock()
        mock_existing.sock.settimeout = MagicMock()
        mock_existing.sock.sendall.side_effect = Exception("Send failed")
        mock_existing.disconnect = MagicMock(side_effect=Exception("Disconnect error"))

        MCP_Server.server._ableton_connection = mock_existing

        # Mock the reconnection attempts to fail
        with patch("MCP_Server.server.AbletonConnection") as MockConn:
            mock_new = MagicMock()
            mock_new.connect.return_value = False
            MockConn.return_value = mock_new

            with patch("time.sleep"), pytest.raises(Exception):
                MCP_Server.server.get_ableton_connection()

        MCP_Server.server._ableton_connection = None

    def test_connection_validation_failure(self):
        """Test that connection validation failure triggers retry."""
        import MCP_Server.server

        MCP_Server.server._ableton_connection = None

        # Mock a connection that connects but fails validation
        with patch("MCP_Server.server.AbletonConnection") as MockConn:
            mock_instance = MagicMock()
            mock_instance.connect.return_value = True
            mock_instance.send_command.side_effect = Exception("Validation failed")
            mock_instance.disconnect = MagicMock()
            MockConn.return_value = mock_instance

            with patch("time.sleep"), pytest.raises(Exception):
                MCP_Server.server.get_ableton_connection()

        MCP_Server.server._ableton_connection = None

    def test_connect_returns_false(self):
        """Test handling when connect() returns False."""
        import MCP_Server.server

        MCP_Server.server._ableton_connection = None

        with patch("MCP_Server.server.AbletonConnection") as MockConn:
            mock_instance = MagicMock()
            mock_instance.connect.return_value = False
            MockConn.return_value = mock_instance

            with patch("time.sleep"), pytest.raises(Exception):
                MCP_Server.server.get_ableton_connection()

        MCP_Server.server._ableton_connection = None

    def test_exception_during_connection_attempt(self):
        """Test exception during connection attempt triggers cleanup."""
        import MCP_Server.server

        MCP_Server.server._ableton_connection = None

        with patch("MCP_Server.server.AbletonConnection") as MockConn:
            mock_instance = MagicMock()
            mock_instance.connect.side_effect = Exception("Connection exception")
            mock_instance.disconnect = MagicMock()
            MockConn.return_value = mock_instance

            with patch("time.sleep"), pytest.raises(Exception):
                MCP_Server.server.get_ableton_connection()

        MCP_Server.server._ableton_connection = None

    def test_successful_ping_returns_connection(self):
        """Test that successful ping returns existing connection."""
        import MCP_Server.server

        mock_existing = MagicMock()
        mock_existing.sock = MagicMock()
        mock_existing.sock.settimeout = MagicMock()
        mock_existing.sock.sendall = MagicMock()
        mock_existing.receive_full_response = MagicMock(
            return_value=json.dumps({"status": "success", "result": {}}).encode()
        )

        MCP_Server.server._ableton_connection = mock_existing

        result = MCP_Server.server.get_ableton_connection()
        assert result is mock_existing

        MCP_Server.server._ableton_connection = None

    def test_successful_new_connection(self):
        """Test successful new connection creation."""
        import MCP_Server.server

        MCP_Server.server._ableton_connection = None

        with patch("MCP_Server.server.AbletonConnection") as MockConn:
            mock_instance = MagicMock()
            mock_instance.connect.return_value = True
            mock_instance.send_command.return_value = {"tempo": 120.0}
            MockConn.return_value = mock_instance

            result = MCP_Server.server.get_ableton_connection()
            assert result is mock_instance

        MCP_Server.server._ableton_connection = None


class TestServerLifespan:
    """Test server_lifespan async context manager."""

    @pytest.mark.asyncio
    async def test_lifespan_startup_success(self):
        """Test server lifespan with successful connection."""
        from MCP_Server.server import server_lifespan

        mock_server = MagicMock()

        with patch("MCP_Server.server.get_ableton_connection") as mock_get_conn:
            mock_get_conn.return_value = MagicMock()

            async with server_lifespan(mock_server):
                pass

    @pytest.mark.asyncio
    async def test_lifespan_startup_connection_failure(self):
        """Test server lifespan with connection failure on startup."""
        from MCP_Server.server import server_lifespan

        mock_server = MagicMock()

        with patch("MCP_Server.server.get_ableton_connection") as mock_get_conn:
            mock_get_conn.side_effect = Exception("Connection failed")

            async with server_lifespan(mock_server):
                pass

    @pytest.mark.asyncio
    async def test_lifespan_shutdown_with_connection(self):
        """Test server lifespan properly disconnects on shutdown."""
        import MCP_Server.server
        from MCP_Server.server import server_lifespan

        mock_server = MagicMock()
        mock_conn = MagicMock()

        MCP_Server.server._ableton_connection = mock_conn

        with patch("MCP_Server.server.get_ableton_connection") as mock_get_conn:
            mock_get_conn.return_value = mock_conn

            async with server_lifespan(mock_server):
                pass

        mock_conn.disconnect.assert_called_once()
        assert MCP_Server.server._ableton_connection is None

    @pytest.mark.asyncio
    async def test_lifespan_shutdown_without_connection(self):
        """Test server lifespan shutdown when no connection exists."""
        import MCP_Server.server
        from MCP_Server.server import server_lifespan

        mock_server = MagicMock()
        MCP_Server.server._ableton_connection = None

        with patch("MCP_Server.server.get_ableton_connection") as mock_get_conn:
            mock_get_conn.side_effect = Exception("No connection")

            async with server_lifespan(mock_server):
                pass

        assert MCP_Server.server._ableton_connection is None


class TestMCPToolSuccessPaths:
    """Test success paths in MCP tool endpoints."""

    @pytest.mark.asyncio
    async def test_get_session_info_success(self, mock_ableton_connection):
        """Test get_session_info success."""
        from MCP_Server.server import get_session_info

        mock_ableton_connection.send_command_async.return_value = {"tempo": 120.0, "tracks": []}

        result = await get_session_info(MagicMock())
        assert "tempo" in result

    @pytest.mark.asyncio
    async def test_get_track_info_success(self, mock_ableton_connection):
        """Test get_track_info success."""
        from MCP_Server.server import get_track_info

        mock_ableton_connection.send_command_async.return_value = {"name": "Track 1", "index": 0}

        result = await get_track_info(MagicMock(), track_index=0)
        assert "Track 1" in result

    @pytest.mark.asyncio
    async def test_create_midi_track_success(self, mock_ableton_connection):
        """Test create_midi_track success."""
        from MCP_Server.server import create_midi_track

        mock_ableton_connection.send_command_async.return_value = {"name": "MIDI Track"}

        result = await create_midi_track(MagicMock())
        assert "MIDI Track" in result

    @pytest.mark.asyncio
    async def test_set_track_name_success(self, mock_ableton_connection):
        """Test set_track_name success."""
        from MCP_Server.server import set_track_name

        mock_ableton_connection.send_command_async.return_value = {"name": "New Name"}

        result = await set_track_name(MagicMock(), track_index=0, name="New Name")
        assert "New Name" in result

    @pytest.mark.asyncio
    async def test_create_clip_success(self, mock_ableton_connection):
        """Test create_clip success."""
        from MCP_Server.server import create_clip

        mock_ableton_connection.send_command_async.return_value = {}

        result = await create_clip(MagicMock(), track_index=0, clip_index=0)
        assert "Created new clip" in result

    @pytest.mark.asyncio
    async def test_add_notes_to_clip_success(self, mock_ableton_connection):
        """Test add_notes_to_clip success."""
        from MCP_Server.server import add_notes_to_clip

        mock_ableton_connection.send_command_async.return_value = {}

        result = await add_notes_to_clip(MagicMock(), track_index=0, clip_index=0, notes=[{"pitch": 60}])
        assert "Added 1 notes" in result

    @pytest.mark.asyncio
    async def test_set_clip_name_success(self, mock_ableton_connection):
        """Test set_clip_name success."""
        from MCP_Server.server import set_clip_name

        mock_ableton_connection.send_command_async.return_value = {}

        result = await set_clip_name(MagicMock(), track_index=0, clip_index=0, name="Clip Name")
        assert "Clip Name" in result

    @pytest.mark.asyncio
    async def test_set_tempo_success(self, mock_ableton_connection):
        """Test set_tempo success."""
        from MCP_Server.server import set_tempo

        mock_ableton_connection.send_command_async.return_value = {}

        result = await set_tempo(MagicMock(), tempo=140.0)
        assert "140" in result

    @pytest.mark.asyncio
    async def test_fire_clip_success(self, mock_ableton_connection):
        """Test fire_clip success."""
        from MCP_Server.server import fire_clip

        mock_ableton_connection.send_command_async.return_value = {}

        result = await fire_clip(MagicMock(), track_index=0, clip_index=0)
        assert "Started playing" in result

    @pytest.mark.asyncio
    async def test_stop_clip_success(self, mock_ableton_connection):
        """Test stop_clip success."""
        from MCP_Server.server import stop_clip

        mock_ableton_connection.send_command_async.return_value = {}

        result = await stop_clip(MagicMock(), track_index=0, clip_index=0)
        assert "Stopped clip" in result

    @pytest.mark.asyncio
    async def test_start_playback_success(self, mock_ableton_connection):
        """Test start_playback success."""
        from MCP_Server.server import start_playback

        mock_ableton_connection.send_command_async.return_value = {}

        result = await start_playback(MagicMock())
        assert "Started playback" in result

    @pytest.mark.asyncio
    async def test_stop_playback_success(self, mock_ableton_connection):
        """Test stop_playback success."""
        from MCP_Server.server import stop_playback

        mock_ableton_connection.send_command_async.return_value = {}

        result = await stop_playback(MagicMock())
        assert "Stopped playback" in result

    @pytest.mark.asyncio
    async def test_undo_success(self, mock_ableton_connection):
        """Test undo success."""
        from MCP_Server.server import undo

        mock_ableton_connection.send_command_async.return_value = {"undone": True}

        result = await undo(MagicMock())
        assert "Undid" in result

    @pytest.mark.asyncio
    async def test_redo_success(self, mock_ableton_connection):
        """Test redo success."""
        from MCP_Server.server import redo

        mock_ableton_connection.send_command_async.return_value = {"redone": True}

        result = await redo(MagicMock())
        assert "Redid" in result

    @pytest.mark.asyncio
    async def test_delete_track_success(self, mock_ableton_connection):
        """Test delete_track success."""
        from MCP_Server.server import delete_track

        mock_ableton_connection.send_command_async.return_value = {"track_name": "Track 1"}

        result = await delete_track(MagicMock(), track_index=0)
        assert "Deleted track" in result

    @pytest.mark.asyncio
    async def test_create_audio_track_success(self, mock_ableton_connection):
        """Test create_audio_track success."""
        from MCP_Server.server import create_audio_track

        mock_ableton_connection.send_command_async.return_value = {"name": "Audio Track"}

        result = await create_audio_track(MagicMock())
        assert "Audio Track" in result

    @pytest.mark.asyncio
    async def test_delete_clip_success(self, mock_ableton_connection):
        """Test delete_clip success."""
        from MCP_Server.server import delete_clip

        mock_ableton_connection.send_command_async.return_value = {"clip_name": "Clip 1"}

        result = await delete_clip(MagicMock(), track_index=0, clip_index=0)
        assert "Deleted clip" in result

    @pytest.mark.asyncio
    async def test_set_metronome_success(self, mock_ableton_connection):
        """Test set_metronome success."""
        from MCP_Server.server import set_metronome

        mock_ableton_connection.send_command_async.return_value = {"metronome": True}

        result = await set_metronome(MagicMock(), enabled=True)
        assert "enabled" in result

    @pytest.mark.asyncio
    async def test_fire_scene_success(self, mock_ableton_connection):
        """Test fire_scene success."""
        from MCP_Server.server import fire_scene

        mock_ableton_connection.send_command_async.return_value = {"scene_name": "Scene 1"}

        result = await fire_scene(MagicMock(), scene_index=0)
        assert "Scene 1" in result

    @pytest.mark.asyncio
    async def test_set_track_mute_success(self, mock_ableton_connection):
        """Test set_track_mute success."""
        from MCP_Server.server import set_track_mute

        mock_ableton_connection.send_command_async.return_value = {"mute": True, "track_name": "Track 1"}

        result = await set_track_mute(MagicMock(), track_index=0, muted=True)
        assert "muted" in result

    @pytest.mark.asyncio
    async def test_set_track_solo_success(self, mock_ableton_connection):
        """Test set_track_solo success."""
        from MCP_Server.server import set_track_solo

        mock_ableton_connection.send_command_async.return_value = {"solo": True, "track_name": "Track 1"}

        result = await set_track_solo(MagicMock(), track_index=0, solo=True)
        assert "soloed" in result

    @pytest.mark.asyncio
    async def test_set_track_arm_success(self, mock_ableton_connection):
        """Test set_track_arm success."""
        from MCP_Server.server import set_track_arm

        mock_ableton_connection.send_command_async.return_value = {"arm": True, "track_name": "Track 1"}

        result = await set_track_arm(MagicMock(), track_index=0, armed=True)
        assert "armed" in result

    @pytest.mark.asyncio
    async def test_set_track_arm_with_message(self, mock_ableton_connection):
        """Test set_track_arm with message response."""
        from MCP_Server.server import set_track_arm

        mock_ableton_connection.send_command_async.return_value = {"message": "Cannot arm return track"}

        result = await set_track_arm(MagicMock(), track_index=0, armed=True)
        assert "Cannot arm" in result

    @pytest.mark.asyncio
    async def test_set_track_volume_success(self, mock_ableton_connection):
        """Test set_track_volume success."""
        from MCP_Server.server import set_track_volume

        mock_ableton_connection.send_command_async.return_value = {"volume": 0.85, "track_name": "Track 1"}

        result = await set_track_volume(MagicMock(), track_index=0, volume=0.85)
        assert "volume" in result.lower()

    @pytest.mark.asyncio
    async def test_set_track_panning_left(self, mock_ableton_connection):
        """Test set_track_panning left."""
        from MCP_Server.server import set_track_panning

        mock_ableton_connection.send_command_async.return_value = {"panning": -0.5, "track_name": "Track 1"}

        result = await set_track_panning(MagicMock(), track_index=0, pan=-0.5)
        assert "left" in result

    @pytest.mark.asyncio
    async def test_set_track_panning_right(self, mock_ableton_connection):
        """Test set_track_panning right."""
        from MCP_Server.server import set_track_panning

        mock_ableton_connection.send_command_async.return_value = {"panning": 0.5, "track_name": "Track 1"}

        result = await set_track_panning(MagicMock(), track_index=0, pan=0.5)
        assert "right" in result

    @pytest.mark.asyncio
    async def test_set_track_panning_center(self, mock_ableton_connection):
        """Test set_track_panning center."""
        from MCP_Server.server import set_track_panning

        mock_ableton_connection.send_command_async.return_value = {"panning": 0.0, "track_name": "Track 1"}

        result = await set_track_panning(MagicMock(), track_index=0, pan=0.0)
        assert "center" in result

    @pytest.mark.asyncio
    async def test_get_notes_from_clip_success(self, mock_ableton_connection):
        """Test get_notes_from_clip success."""
        from MCP_Server.server import get_notes_from_clip

        mock_ableton_connection.send_command_async.return_value = {"notes": []}

        result = await get_notes_from_clip(MagicMock(), track_index=0, clip_index=0)
        assert "notes" in result

    @pytest.mark.asyncio
    async def test_get_scene_info_success(self, mock_ableton_connection):
        """Test get_scene_info success."""
        from MCP_Server.server import get_scene_info

        mock_ableton_connection.send_command_async.return_value = {"name": "Scene 1", "index": 0}

        result = await get_scene_info(MagicMock(), scene_index=0)
        assert "Scene 1" in result


class TestMCPToolErrorPaths:
    """Test error handling in MCP tool endpoints."""

    @pytest.mark.asyncio
    async def test_get_session_info_error(self, mock_ableton_connection):
        """Test get_session_info error handling."""
        from MCP_Server.server import get_session_info

        mock_ableton_connection.send_command_async.side_effect = Exception("Test error")

        result = await get_session_info(MagicMock())
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_get_track_info_error(self, mock_ableton_connection):
        """Test get_track_info error handling."""
        from MCP_Server.server import get_track_info

        mock_ableton_connection.send_command_async.side_effect = Exception("Test error")

        result = await get_track_info(MagicMock(), track_index=0)
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_create_midi_track_error(self, mock_ableton_connection):
        """Test create_midi_track error handling."""
        from MCP_Server.server import create_midi_track

        mock_ableton_connection.send_command_async.side_effect = Exception("Test error")

        result = await create_midi_track(MagicMock())
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_set_track_name_error(self, mock_ableton_connection):
        """Test set_track_name error handling."""
        from MCP_Server.server import set_track_name

        mock_ableton_connection.send_command_async.side_effect = Exception("Test error")

        result = await set_track_name(MagicMock(), track_index=0, name="Test")
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_create_clip_error(self, mock_ableton_connection):
        """Test create_clip error handling."""
        from MCP_Server.server import create_clip

        mock_ableton_connection.send_command_async.side_effect = Exception("Test error")

        result = await create_clip(MagicMock(), track_index=0, clip_index=0)
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_add_notes_to_clip_error(self, mock_ableton_connection):
        """Test add_notes_to_clip error handling."""
        from MCP_Server.server import add_notes_to_clip

        mock_ableton_connection.send_command_async.side_effect = Exception("Test error")

        result = await add_notes_to_clip(MagicMock(), track_index=0, clip_index=0, notes=[])
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_set_clip_name_error(self, mock_ableton_connection):
        """Test set_clip_name error handling."""
        from MCP_Server.server import set_clip_name

        mock_ableton_connection.send_command_async.side_effect = Exception("Test error")

        result = await set_clip_name(MagicMock(), track_index=0, clip_index=0, name="Test")
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_set_tempo_error(self, mock_ableton_connection):
        """Test set_tempo error handling."""
        from MCP_Server.server import set_tempo

        mock_ableton_connection.send_command_async.side_effect = Exception("Test error")

        result = await set_tempo(MagicMock(), tempo=120.0)
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_fire_clip_error(self, mock_ableton_connection):
        """Test fire_clip error handling."""
        from MCP_Server.server import fire_clip

        mock_ableton_connection.send_command_async.side_effect = Exception("Test error")

        result = await fire_clip(MagicMock(), track_index=0, clip_index=0)
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_stop_clip_error(self, mock_ableton_connection):
        """Test stop_clip error handling."""
        from MCP_Server.server import stop_clip

        mock_ableton_connection.send_command_async.side_effect = Exception("Test error")

        result = await stop_clip(MagicMock(), track_index=0, clip_index=0)
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_start_playback_error(self, mock_ableton_connection):
        """Test start_playback error handling."""
        from MCP_Server.server import start_playback

        mock_ableton_connection.send_command_async.side_effect = Exception("Test error")

        result = await start_playback(MagicMock())
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_stop_playback_error(self, mock_ableton_connection):
        """Test stop_playback error handling."""
        from MCP_Server.server import stop_playback

        mock_ableton_connection.send_command_async.side_effect = Exception("Test error")

        result = await stop_playback(MagicMock())
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_undo_error(self, mock_ableton_connection):
        """Test undo error handling."""
        from MCP_Server.server import undo

        mock_ableton_connection.send_command_async.side_effect = Exception("Test error")

        result = await undo(MagicMock())
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_undo_nothing_to_undo(self, mock_ableton_connection):
        """Test undo when nothing to undo."""
        from MCP_Server.server import undo

        mock_ableton_connection.send_command_async.return_value = {"undone": False, "message": "Nothing to undo"}

        result = await undo(MagicMock())
        assert "Nothing to undo" in result

    @pytest.mark.asyncio
    async def test_redo_error(self, mock_ableton_connection):
        """Test redo error handling."""
        from MCP_Server.server import redo

        mock_ableton_connection.send_command_async.side_effect = Exception("Test error")

        result = await redo(MagicMock())
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_redo_nothing_to_redo(self, mock_ableton_connection):
        """Test redo when nothing to redo."""
        from MCP_Server.server import redo

        mock_ableton_connection.send_command_async.return_value = {"redone": False, "message": "Nothing to redo"}

        result = await redo(MagicMock())
        assert "Nothing to redo" in result

    @pytest.mark.asyncio
    async def test_delete_track_error(self, mock_ableton_connection):
        """Test delete_track error handling."""
        from MCP_Server.server import delete_track

        mock_ableton_connection.send_command_async.side_effect = Exception("Test error")

        result = await delete_track(MagicMock(), track_index=0)
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_create_audio_track_error(self, mock_ableton_connection):
        """Test create_audio_track error handling."""
        from MCP_Server.server import create_audio_track

        mock_ableton_connection.send_command_async.side_effect = Exception("Test error")

        result = await create_audio_track(MagicMock())
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_delete_clip_error(self, mock_ableton_connection):
        """Test delete_clip error handling."""
        from MCP_Server.server import delete_clip

        mock_ableton_connection.send_command_async.side_effect = Exception("Test error")

        result = await delete_clip(MagicMock(), track_index=0, clip_index=0)
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_set_metronome_error(self, mock_ableton_connection):
        """Test set_metronome error handling."""
        from MCP_Server.server import set_metronome

        mock_ableton_connection.send_command_async.side_effect = Exception("Test error")

        result = await set_metronome(MagicMock(), enabled=True)
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_fire_scene_error(self, mock_ableton_connection):
        """Test fire_scene error handling."""
        from MCP_Server.server import fire_scene

        mock_ableton_connection.send_command_async.side_effect = Exception("Test error")

        result = await fire_scene(MagicMock(), scene_index=0)
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_set_track_mute_error(self, mock_ableton_connection):
        """Test set_track_mute error handling."""
        from MCP_Server.server import set_track_mute

        mock_ableton_connection.send_command_async.side_effect = Exception("Test error")

        result = await set_track_mute(MagicMock(), track_index=0, muted=True)
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_set_track_solo_error(self, mock_ableton_connection):
        """Test set_track_solo error handling."""
        from MCP_Server.server import set_track_solo

        mock_ableton_connection.send_command_async.side_effect = Exception("Test error")

        result = await set_track_solo(MagicMock(), track_index=0, solo=True)
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_set_track_arm_error(self, mock_ableton_connection):
        """Test set_track_arm error handling."""
        from MCP_Server.server import set_track_arm

        mock_ableton_connection.send_command_async.side_effect = Exception("Test error")

        result = await set_track_arm(MagicMock(), track_index=0, armed=True)
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_set_track_volume_error(self, mock_ableton_connection):
        """Test set_track_volume error handling."""
        from MCP_Server.server import set_track_volume

        mock_ableton_connection.send_command_async.side_effect = Exception("Test error")

        result = await set_track_volume(MagicMock(), track_index=0, volume=0.5)
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_set_track_panning_error(self, mock_ableton_connection):
        """Test set_track_panning error handling."""
        from MCP_Server.server import set_track_panning

        mock_ableton_connection.send_command_async.side_effect = Exception("Test error")

        result = await set_track_panning(MagicMock(), track_index=0, pan=0.0)
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_get_notes_from_clip_error(self, mock_ableton_connection):
        """Test get_notes_from_clip error handling."""
        from MCP_Server.server import get_notes_from_clip

        mock_ableton_connection.send_command_async.side_effect = Exception("Test error")

        result = await get_notes_from_clip(MagicMock(), track_index=0, clip_index=0)
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_get_scene_info_error(self, mock_ableton_connection):
        """Test get_scene_info error handling."""
        from MCP_Server.server import get_scene_info

        mock_ableton_connection.send_command_async.side_effect = Exception("Test error")

        result = await get_scene_info(MagicMock(), scene_index=0)
        assert "Error" in result


class TestArrangementToolErrors:
    """Test error handling in arrangement tools."""

    @pytest.mark.asyncio
    async def test_set_loop_region_error(self, mock_ableton_connection):
        """Test set_loop_region error handling."""
        from MCP_Server.server import set_loop_region

        mock_ableton_connection.send_command_async.side_effect = Exception("Test error")

        result = await set_loop_region(MagicMock(), start=0.0, length=4.0)
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_set_loop_enabled_error(self, mock_ableton_connection):
        """Test set_loop_enabled error handling."""
        from MCP_Server.server import set_loop_enabled

        mock_ableton_connection.send_command_async.side_effect = Exception("Test error")

        result = await set_loop_enabled(MagicMock(), enabled=True)
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_continue_playing_error(self, mock_ableton_connection):
        """Test continue_playing error handling."""
        from MCP_Server.server import continue_playing

        mock_ableton_connection.send_command_async.side_effect = Exception("Test error")

        result = await continue_playing(MagicMock())
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_jump_by_bars_error(self, mock_ableton_connection):
        """Test jump_by_bars error handling."""
        from MCP_Server.server import jump_by_bars

        mock_ableton_connection.send_command_async.side_effect = Exception("Test error")

        result = await jump_by_bars(MagicMock(), bars=4)
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_get_cue_points_error(self, mock_ableton_connection):
        """Test get_cue_points error handling."""
        from MCP_Server.server import get_cue_points

        mock_ableton_connection.send_command_async.side_effect = Exception("Test error")

        result = await get_cue_points(MagicMock())
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_jump_to_next_cue_point_error(self, mock_ableton_connection):
        """Test jump_to_next_cue_point error handling."""
        from MCP_Server.server import jump_to_next_cue_point

        mock_ableton_connection.send_command_async.side_effect = Exception("Test error")

        result = await jump_to_next_cue_point(MagicMock())
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_jump_to_next_cue_point_no_cue(self, mock_ableton_connection):
        """Test jump_to_next_cue_point when no cue found."""
        from MCP_Server.server import jump_to_next_cue_point

        mock_ableton_connection.send_command_async.return_value = {"jumped": False, "message": "No next cue point"}

        result = await jump_to_next_cue_point(MagicMock())
        assert "No next cue point" in result

    @pytest.mark.asyncio
    async def test_jump_to_prev_cue_point_error(self, mock_ableton_connection):
        """Test jump_to_prev_cue_point error handling."""
        from MCP_Server.server import jump_to_prev_cue_point

        mock_ableton_connection.send_command_async.side_effect = Exception("Test error")

        result = await jump_to_prev_cue_point(MagicMock())
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_jump_to_prev_cue_point_no_cue(self, mock_ableton_connection):
        """Test jump_to_prev_cue_point when no cue found."""
        from MCP_Server.server import jump_to_prev_cue_point

        mock_ableton_connection.send_command_async.return_value = {"jumped": False, "message": "No previous cue point"}

        result = await jump_to_prev_cue_point(MagicMock())
        assert "No previous cue point" in result

    @pytest.mark.asyncio
    async def test_create_cue_point_updated(self, mock_ableton_connection):
        """Test create_cue_point when cue already exists."""
        from MCP_Server.server import create_cue_point

        mock_ableton_connection.send_command_async.return_value = {
            "updated": True,
            "time": 4.0,
            "message": "Cue point already exists at beat 4.0"
        }

        result = await create_cue_point(MagicMock(), time=4.0)
        assert "already exists" in result

    @pytest.mark.asyncio
    async def test_create_cue_point_updated_no_message(self, mock_ableton_connection):
        """Test create_cue_point when cue updated without message."""
        from MCP_Server.server import create_cue_point

        mock_ableton_connection.send_command_async.return_value = {
            "updated": True,
            "time": 4.0
        }

        result = await create_cue_point(MagicMock(), time=4.0)
        assert "already exists" in result


class TestBrowserTools:
    """Test browser tool functionality."""

    @pytest.mark.asyncio
    async def test_get_browser_tree_no_categories(self, mock_ableton_connection):
        """Test get_browser_tree with no categories found."""
        from MCP_Server.server import get_browser_tree

        mock_ableton_connection.send_command_async.return_value = {
            "available_categories": ["sounds", "drums"],
            "categories": []
        }

        result = await get_browser_tree(MagicMock(), category_type="invalid")
        assert "No categories found" in result
        assert "Available browser categories" in result

    @pytest.mark.asyncio
    async def test_get_browser_tree_browser_not_available(self, mock_ableton_connection):
        """Test get_browser_tree when browser not available."""
        from MCP_Server.server import get_browser_tree

        mock_ableton_connection.send_command_async.side_effect = Exception("Browser is not available")

        result = await get_browser_tree(MagicMock())
        assert "browser is not available" in result.lower()

    @pytest.mark.asyncio
    async def test_get_browser_tree_live_not_accessible(self, mock_ableton_connection):
        """Test get_browser_tree when Live not accessible."""
        from MCP_Server.server import get_browser_tree

        mock_ableton_connection.send_command_async.side_effect = Exception("Could not access Live application")

        result = await get_browser_tree(MagicMock())
        assert "Could not access" in result

    @pytest.mark.asyncio
    async def test_get_browser_tree_generic_error(self, mock_ableton_connection):
        """Test get_browser_tree generic error."""
        from MCP_Server.server import get_browser_tree

        mock_ableton_connection.send_command_async.side_effect = Exception("Some other error")

        result = await get_browser_tree(MagicMock())
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_get_browser_tree_with_tree(self, mock_ableton_connection):
        """Test get_browser_tree with actual tree data."""
        from MCP_Server.server import get_browser_tree

        mock_ableton_connection.send_command_async.return_value = {
            "total_folders": 5,
            "categories": [
                {
                    "name": "Instruments",
                    "path": "/instruments",
                    "has_more": True,
                    "children": [
                        {"name": "Piano", "path": "/instruments/piano", "children": []}
                    ]
                }
            ]
        }

        result = await get_browser_tree(MagicMock())
        assert "Instruments" in result
        assert "Piano" in result

    @pytest.mark.asyncio
    async def test_get_browser_items_at_path_error_with_categories(self, mock_ableton_connection):
        """Test get_browser_items_at_path with error and available categories."""
        from MCP_Server.server import get_browser_items_at_path

        mock_ableton_connection.send_command_async.return_value = {
            "error": "Category not found",
            "available_categories": ["sounds", "drums"]
        }

        result = await get_browser_items_at_path(MagicMock(), path="invalid/path")
        assert "Category not found" in result
        assert "Available browser categories" in result

    @pytest.mark.asyncio
    async def test_get_browser_items_at_path_browser_not_available(self, mock_ableton_connection):
        """Test get_browser_items_at_path when browser not available."""
        from MCP_Server.server import get_browser_items_at_path

        mock_ableton_connection.send_command_async.side_effect = Exception("Browser is not available")

        result = await get_browser_items_at_path(MagicMock(), path="sounds")
        assert "browser is not available" in result.lower()

    @pytest.mark.asyncio
    async def test_get_browser_items_at_path_live_not_accessible(self, mock_ableton_connection):
        """Test get_browser_items_at_path when Live not accessible."""
        from MCP_Server.server import get_browser_items_at_path

        mock_ableton_connection.send_command_async.side_effect = Exception("Could not access Live application")

        result = await get_browser_items_at_path(MagicMock(), path="sounds")
        assert "Could not access" in result

    @pytest.mark.asyncio
    async def test_get_browser_items_at_path_unknown_category(self, mock_ableton_connection):
        """Test get_browser_items_at_path with unknown category."""
        from MCP_Server.server import get_browser_items_at_path

        mock_ableton_connection.send_command_async.side_effect = Exception("Unknown or unavailable category")

        result = await get_browser_items_at_path(MagicMock(), path="invalid")
        assert "Unknown or unavailable category" in result

    @pytest.mark.asyncio
    async def test_get_browser_items_at_path_not_found(self, mock_ableton_connection):
        """Test get_browser_items_at_path when path not found."""
        from MCP_Server.server import get_browser_items_at_path

        mock_ableton_connection.send_command_async.side_effect = Exception("Path part 'invalid' not found")

        result = await get_browser_items_at_path(MagicMock(), path="sounds/invalid")
        assert "not found" in result.lower()

    @pytest.mark.asyncio
    async def test_get_browser_items_at_path_generic_error(self, mock_ableton_connection):
        """Test get_browser_items_at_path generic error."""
        from MCP_Server.server import get_browser_items_at_path

        mock_ableton_connection.send_command_async.side_effect = Exception("Some other error")

        result = await get_browser_items_at_path(MagicMock(), path="sounds")
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_get_browser_items_at_path_success(self, mock_ableton_connection):
        """Test get_browser_items_at_path success."""
        from MCP_Server.server import get_browser_items_at_path

        mock_ableton_connection.send_command_async.return_value = {
            "items": [{"name": "Piano", "is_loadable": True}]
        }

        result = await get_browser_items_at_path(MagicMock(), path="sounds")
        assert "Piano" in result


class TestLoadDrumKit:
    """Test load_drum_kit functionality."""

    @pytest.mark.asyncio
    async def test_load_drum_kit_rack_load_fails(self, mock_ableton_connection):
        """Test load_drum_kit when rack load fails."""
        from MCP_Server.server import load_drum_kit

        mock_ableton_connection.send_command_async.return_value = {"loaded": False}

        result = await load_drum_kit(MagicMock(), track_index=0, rack_uri="drums/rack", kit_path="drums/kit")
        assert "Failed to load drum rack" in result

    @pytest.mark.asyncio
    async def test_load_drum_kit_path_error(self, mock_ableton_connection):
        """Test load_drum_kit when kit path has error."""
        from MCP_Server.server import load_drum_kit

        call_count = [0]

        async def mock_send(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return {"loaded": True}
            return {"error": "Path not found"}

        mock_ableton_connection.send_command_async.side_effect = mock_send

        result = await load_drum_kit(MagicMock(), track_index=0, rack_uri="drums/rack", kit_path="invalid/path")
        assert "failed to find drum kit" in result.lower()

    @pytest.mark.asyncio
    async def test_load_drum_kit_no_loadable_kits(self, mock_ableton_connection):
        """Test load_drum_kit when no loadable kits found."""
        from MCP_Server.server import load_drum_kit

        call_count = [0]

        async def mock_send(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return {"loaded": True}
            return {"items": [{"name": "Folder", "is_loadable": False}]}

        mock_ableton_connection.send_command_async.side_effect = mock_send

        result = await load_drum_kit(MagicMock(), track_index=0, rack_uri="drums/rack", kit_path="drums/kits")
        assert "no loadable drum kits found" in result.lower()

    @pytest.mark.asyncio
    async def test_load_drum_kit_success(self, mock_ableton_connection):
        """Test load_drum_kit success."""
        from MCP_Server.server import load_drum_kit

        call_count = [0]

        async def mock_send(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return {"loaded": True}
            elif call_count[0] == 2:
                return {"items": [{"name": "Kit1", "is_loadable": True, "uri": "kit1_uri"}]}
            return {"loaded": True}

        mock_ableton_connection.send_command_async.side_effect = mock_send

        result = await load_drum_kit(MagicMock(), track_index=0, rack_uri="drums/rack", kit_path="drums/kits")
        assert "Loaded drum rack and kit" in result

    @pytest.mark.asyncio
    async def test_load_drum_kit_error(self, mock_ableton_connection):
        """Test load_drum_kit error handling."""
        from MCP_Server.server import load_drum_kit

        mock_ableton_connection.send_command_async.side_effect = Exception("Test error")

        result = await load_drum_kit(MagicMock(), track_index=0, rack_uri="drums/rack", kit_path="drums/kit")
        assert "Error" in result


class TestLoadInstrumentOrEffect:
    """Test load_instrument_or_effect functionality."""

    @pytest.mark.asyncio
    async def test_load_instrument_success_with_new_devices(self, mock_ableton_connection):
        """Test load_instrument_or_effect with new devices."""
        from MCP_Server.server import load_instrument_or_effect

        mock_ableton_connection.send_command_async.return_value = {
            "loaded": True,
            "new_devices": ["Wavetable", "EQ Eight"]
        }

        result = await load_instrument_or_effect(MagicMock(), track_index=0, uri="instruments/wavetable")
        assert "Loaded instrument" in result
        assert "Wavetable" in result

    @pytest.mark.asyncio
    async def test_load_instrument_success_no_new_devices(self, mock_ableton_connection):
        """Test load_instrument_or_effect without new devices list."""
        from MCP_Server.server import load_instrument_or_effect

        mock_ableton_connection.send_command_async.return_value = {
            "loaded": True,
            "devices_after": ["Simpler"]
        }

        result = await load_instrument_or_effect(MagicMock(), track_index=0, uri="instruments/simpler")
        assert "Loaded instrument" in result
        assert "Simpler" in result

    @pytest.mark.asyncio
    async def test_load_instrument_failure(self, mock_ableton_connection):
        """Test load_instrument_or_effect failure."""
        from MCP_Server.server import load_instrument_or_effect

        mock_ableton_connection.send_command_async.return_value = {"loaded": False}

        result = await load_instrument_or_effect(MagicMock(), track_index=0, uri="invalid/uri")
        assert "Failed to load" in result

    @pytest.mark.asyncio
    async def test_load_instrument_error(self, mock_ableton_connection):
        """Test load_instrument_or_effect error."""
        from MCP_Server.server import load_instrument_or_effect

        mock_ableton_connection.send_command_async.side_effect = Exception("Test error")

        result = await load_instrument_or_effect(MagicMock(), track_index=0, uri="test/uri")
        assert "Error" in result


class TestMainFunction:
    """Test main() function."""

    def test_main_runs_mcp(self):
        """Test that main() runs the MCP server."""
        from MCP_Server.server import main, mcp

        with patch.object(mcp, "run") as mock_run:
            main()
            mock_run.assert_called_once()


class TestCommandDelay:
    """Test command delay functionality."""

    def test_command_delay_applied(self, mock_tcp_server):
        """Test that command delay is applied when env var is set."""
        import os

        # Set delay environment variable
        original = os.environ.get("ABLETON_MCP_COMMAND_DELAY")
        os.environ["ABLETON_MCP_COMMAND_DELAY"] = "0.01"

        try:
            # Need to reload the module to pick up the new env var
            import importlib

            import MCP_Server.server

            importlib.reload(MCP_Server.server)

            mock_tcp_server.set_response(
                "create_midi_track",
                {"status": "success", "result": {"index": 0, "name": "1-MIDI"}}
            )

            conn = MCP_Server.server.AbletonConnection(host="localhost", port=mock_tcp_server.port)
            result = conn.send_command("create_midi_track", {"index": -1})

            assert result["name"] == "1-MIDI"
        finally:
            if original is not None:
                os.environ["ABLETON_MCP_COMMAND_DELAY"] = original
            elif "ABLETON_MCP_COMMAND_DELAY" in os.environ:
                del os.environ["ABLETON_MCP_COMMAND_DELAY"]

            # Reload to restore original state
            import importlib

            import MCP_Server.server

            importlib.reload(MCP_Server.server)
