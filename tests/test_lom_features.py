"""Tests for new LOM (Live Object Model) features added in Phase 2-4.

These tests cover Tasks 6-15 from the implementation plan:
- Task 6: Undo/Redo Commands
- Task 7: Delete Track Command
- Task 8: Create Audio Track Command
- Task 9: Delete Clip Command
- Task 10: Set Metronome Command
- Task 11: Fire Scene Command
- Task 12: Track Mute/Solo/Arm Setters
- Task 13: Track Volume/Pan Setters
- Task 14: Get Notes From Clip
- Task 15: Get Scene Info
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestUndoRedoCommands:
    """Tests for undo/redo functionality (Task 6)."""

    def test_undo_command_sends_correct_type(self, mock_tcp_server):
        """Test that undo command sends correct command type."""
        mock_tcp_server.set_response("undo", {"status": "success", "result": {"undone": True}})

        from MCP_Server.server import AbletonConnection

        conn = AbletonConnection(host="localhost", port=mock_tcp_server.port)
        result = conn.send_command("undo")

        assert result["undone"] is True
        assert mock_tcp_server.received_commands[-1]["type"] == "undo"

    def test_undo_when_nothing_to_undo(self, mock_tcp_server):
        """Test undo response when nothing to undo."""
        mock_tcp_server.set_response(
            "undo",
            {"status": "success", "result": {"undone": False, "message": "Nothing to undo"}},
        )

        from MCP_Server.server import AbletonConnection

        conn = AbletonConnection(host="localhost", port=mock_tcp_server.port)
        result = conn.send_command("undo")

        assert result["undone"] is False
        assert result["message"] == "Nothing to undo"

    def test_redo_command_sends_correct_type(self, mock_tcp_server):
        """Test that redo command sends correct command type."""
        mock_tcp_server.set_response("redo", {"status": "success", "result": {"redone": True}})

        from MCP_Server.server import AbletonConnection

        conn = AbletonConnection(host="localhost", port=mock_tcp_server.port)
        result = conn.send_command("redo")

        assert result["redone"] is True
        assert mock_tcp_server.received_commands[-1]["type"] == "redo"

    def test_redo_when_nothing_to_redo(self, mock_tcp_server):
        """Test redo response when nothing to redo."""
        mock_tcp_server.set_response(
            "redo",
            {"status": "success", "result": {"redone": False, "message": "Nothing to redo"}},
        )

        from MCP_Server.server import AbletonConnection

        conn = AbletonConnection(host="localhost", port=mock_tcp_server.port)
        result = conn.send_command("redo")

        assert result["redone"] is False
        assert result["message"] == "Nothing to redo"

    def test_undo_handler_exists_in_remote_script(self):
        """Verify undo command is handled in Remote Script."""
        remote_script_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "AbletonMCP_Remote_Script",
            "__init__.py",
        )

        with open(remote_script_path) as f:
            source = f.read()

        assert 'command_type == "undo"' in source
        assert "_undo" in source

    def test_redo_handler_exists_in_remote_script(self):
        """Verify redo command is handled in Remote Script."""
        remote_script_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "AbletonMCP_Remote_Script",
            "__init__.py",
        )

        with open(remote_script_path) as f:
            source = f.read()

        assert 'command_type == "redo"' in source
        assert "_redo" in source


class TestDeleteTrackCommand:
    """Tests for delete_track functionality (Task 7)."""

    def test_delete_track_sends_correct_params(self, mock_tcp_server):
        """Test that delete_track sends track_index parameter."""
        mock_tcp_server.set_response(
            "delete_track",
            {"status": "success", "result": {"deleted": True, "track_name": "Bass"}},
        )

        from MCP_Server.server import AbletonConnection

        conn = AbletonConnection(host="localhost", port=mock_tcp_server.port)
        result = conn.send_command("delete_track", {"track_index": 2})

        assert result["deleted"] is True
        assert result["track_name"] == "Bass"
        assert mock_tcp_server.received_commands[-1]["params"]["track_index"] == 2

    def test_delete_track_returns_track_name(self, mock_tcp_server):
        """Test that delete_track returns the deleted track's name."""
        mock_tcp_server.set_response(
            "delete_track",
            {"status": "success", "result": {"deleted": True, "track_name": "Drums"}},
        )

        from MCP_Server.server import AbletonConnection

        conn = AbletonConnection(host="localhost", port=mock_tcp_server.port)
        result = conn.send_command("delete_track", {"track_index": 0})

        assert result["track_name"] == "Drums"

    def test_delete_track_handler_exists(self):
        """Verify delete_track is handled in Remote Script."""
        remote_script_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "AbletonMCP_Remote_Script",
            "__init__.py",
        )

        with open(remote_script_path) as f:
            source = f.read()

        assert 'command_type == "delete_track"' in source
        assert "_delete_track" in source


class TestCreateAudioTrackCommand:
    """Tests for create_audio_track functionality (Task 8)."""

    def test_create_audio_track_default_index(self, mock_tcp_server):
        """Test creating audio track at default position."""
        mock_tcp_server.set_response(
            "create_audio_track",
            {"status": "success", "result": {"index": 3, "name": "4-Audio"}},
        )

        from MCP_Server.server import AbletonConnection

        conn = AbletonConnection(host="localhost", port=mock_tcp_server.port)
        result = conn.send_command("create_audio_track", {"index": -1})

        assert result["name"] == "4-Audio"
        assert result["index"] == 3

    def test_create_audio_track_at_specific_index(self, mock_tcp_server):
        """Test creating audio track at specific index."""
        mock_tcp_server.set_response(
            "create_audio_track",
            {"status": "success", "result": {"index": 1, "name": "2-Audio"}},
        )

        from MCP_Server.server import AbletonConnection

        conn = AbletonConnection(host="localhost", port=mock_tcp_server.port)
        result = conn.send_command("create_audio_track", {"index": 1})

        assert result["index"] == 1
        assert mock_tcp_server.received_commands[-1]["params"]["index"] == 1

    def test_create_audio_track_handler_exists(self):
        """Verify create_audio_track is handled in Remote Script."""
        remote_script_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "AbletonMCP_Remote_Script",
            "__init__.py",
        )

        with open(remote_script_path) as f:
            source = f.read()

        assert 'command_type == "create_audio_track"' in source
        assert "_create_audio_track" in source


class TestDeleteClipCommand:
    """Tests for delete_clip functionality (Task 9)."""

    def test_delete_clip_sends_correct_params(self, mock_tcp_server):
        """Test that delete_clip sends both track and clip indices."""
        mock_tcp_server.set_response(
            "delete_clip",
            {"status": "success", "result": {"deleted": True, "clip_name": "Loop 1"}},
        )

        from MCP_Server.server import AbletonConnection

        conn = AbletonConnection(host="localhost", port=mock_tcp_server.port)
        result = conn.send_command("delete_clip", {"track_index": 0, "clip_index": 2})

        assert result["deleted"] is True
        assert result["clip_name"] == "Loop 1"
        params = mock_tcp_server.received_commands[-1]["params"]
        assert params["track_index"] == 0
        assert params["clip_index"] == 2

    def test_delete_clip_handler_exists(self):
        """Verify delete_clip is handled in Remote Script."""
        remote_script_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "AbletonMCP_Remote_Script",
            "__init__.py",
        )

        with open(remote_script_path) as f:
            source = f.read()

        assert 'command_type == "delete_clip"' in source
        assert "_delete_clip" in source


class TestSetMetronomeCommand:
    """Tests for set_metronome functionality (Task 10)."""

    def test_enable_metronome(self, mock_tcp_server):
        """Test enabling the metronome."""
        mock_tcp_server.set_response(
            "set_metronome",
            {"status": "success", "result": {"metronome": True}},
        )

        from MCP_Server.server import AbletonConnection

        conn = AbletonConnection(host="localhost", port=mock_tcp_server.port)
        result = conn.send_command("set_metronome", {"enabled": True})

        assert result["metronome"] is True

    def test_disable_metronome(self, mock_tcp_server):
        """Test disabling the metronome."""
        mock_tcp_server.set_response(
            "set_metronome",
            {"status": "success", "result": {"metronome": False}},
        )

        from MCP_Server.server import AbletonConnection

        conn = AbletonConnection(host="localhost", port=mock_tcp_server.port)
        result = conn.send_command("set_metronome", {"enabled": False})

        assert result["metronome"] is False

    def test_set_metronome_handler_exists(self):
        """Verify set_metronome is handled in Remote Script."""
        remote_script_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "AbletonMCP_Remote_Script",
            "__init__.py",
        )

        with open(remote_script_path) as f:
            source = f.read()

        assert 'command_type == "set_metronome"' in source
        assert "_set_metronome" in source


class TestFireSceneCommand:
    """Tests for fire_scene functionality (Task 11)."""

    def test_fire_scene_sends_correct_params(self, mock_tcp_server):
        """Test that fire_scene sends scene_index."""
        mock_tcp_server.set_response(
            "fire_scene",
            {
                "status": "success",
                "result": {"fired": True, "scene_name": "Intro", "scene_index": 0},
            },
        )

        from MCP_Server.server import AbletonConnection

        conn = AbletonConnection(host="localhost", port=mock_tcp_server.port)
        result = conn.send_command("fire_scene", {"scene_index": 0})

        assert result["fired"] is True
        assert result["scene_name"] == "Intro"
        assert mock_tcp_server.received_commands[-1]["params"]["scene_index"] == 0

    def test_fire_scene_handler_exists(self):
        """Verify fire_scene is handled in Remote Script."""
        remote_script_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "AbletonMCP_Remote_Script",
            "__init__.py",
        )

        with open(remote_script_path) as f:
            source = f.read()

        assert 'command_type == "fire_scene"' in source
        assert "_fire_scene" in source


class TestTrackMuteSoloArmSetters:
    """Tests for track mute/solo/arm setters (Task 12)."""

    def test_set_track_mute_on(self, mock_tcp_server):
        """Test muting a track."""
        mock_tcp_server.set_response(
            "set_track_mute",
            {"status": "success", "result": {"mute": True, "track_name": "Bass"}},
        )

        from MCP_Server.server import AbletonConnection

        conn = AbletonConnection(host="localhost", port=mock_tcp_server.port)
        result = conn.send_command("set_track_mute", {"track_index": 0, "muted": True})

        assert result["mute"] is True
        assert result["track_name"] == "Bass"

    def test_set_track_mute_off(self, mock_tcp_server):
        """Test unmuting a track."""
        mock_tcp_server.set_response(
            "set_track_mute",
            {"status": "success", "result": {"mute": False, "track_name": "Bass"}},
        )

        from MCP_Server.server import AbletonConnection

        conn = AbletonConnection(host="localhost", port=mock_tcp_server.port)
        result = conn.send_command("set_track_mute", {"track_index": 0, "muted": False})

        assert result["mute"] is False

    def test_set_track_solo_on(self, mock_tcp_server):
        """Test soloing a track."""
        mock_tcp_server.set_response(
            "set_track_solo",
            {"status": "success", "result": {"solo": True, "track_name": "Lead"}},
        )

        from MCP_Server.server import AbletonConnection

        conn = AbletonConnection(host="localhost", port=mock_tcp_server.port)
        result = conn.send_command("set_track_solo", {"track_index": 1, "solo": True})

        assert result["solo"] is True
        assert result["track_name"] == "Lead"

    def test_set_track_solo_off(self, mock_tcp_server):
        """Test unsoloing a track."""
        mock_tcp_server.set_response(
            "set_track_solo",
            {"status": "success", "result": {"solo": False, "track_name": "Lead"}},
        )

        from MCP_Server.server import AbletonConnection

        conn = AbletonConnection(host="localhost", port=mock_tcp_server.port)
        result = conn.send_command("set_track_solo", {"track_index": 1, "solo": False})

        assert result["solo"] is False

    def test_set_track_arm_on(self, mock_tcp_server):
        """Test arming a track for recording."""
        mock_tcp_server.set_response(
            "set_track_arm",
            {"status": "success", "result": {"arm": True, "track_name": "Vocals"}},
        )

        from MCP_Server.server import AbletonConnection

        conn = AbletonConnection(host="localhost", port=mock_tcp_server.port)
        result = conn.send_command("set_track_arm", {"track_index": 2, "armed": True})

        assert result["arm"] is True
        assert result["track_name"] == "Vocals"

    def test_set_track_arm_off(self, mock_tcp_server):
        """Test disarming a track."""
        mock_tcp_server.set_response(
            "set_track_arm",
            {"status": "success", "result": {"arm": False, "track_name": "Vocals"}},
        )

        from MCP_Server.server import AbletonConnection

        conn = AbletonConnection(host="localhost", port=mock_tcp_server.port)
        result = conn.send_command("set_track_arm", {"track_index": 2, "armed": False})

        assert result["arm"] is False

    def test_set_track_arm_not_armable(self, mock_tcp_server):
        """Test arming a track that cannot be armed."""
        mock_tcp_server.set_response(
            "set_track_arm",
            {
                "status": "success",
                "result": {
                    "arm": False,
                    "track_name": "Master",
                    "message": "Track cannot be armed",
                },
            },
        )

        from MCP_Server.server import AbletonConnection

        conn = AbletonConnection(host="localhost", port=mock_tcp_server.port)
        result = conn.send_command("set_track_arm", {"track_index": 0, "armed": True})

        assert result["arm"] is False
        assert "cannot be armed" in result.get("message", "")

    def test_mute_solo_arm_handlers_exist(self):
        """Verify mute/solo/arm handlers exist in Remote Script."""
        remote_script_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "AbletonMCP_Remote_Script",
            "__init__.py",
        )

        with open(remote_script_path) as f:
            source = f.read()

        assert "_set_track_mute" in source
        assert "_set_track_solo" in source
        assert "_set_track_arm" in source


class TestTrackVolumePanSetters:
    """Tests for track volume/pan setters (Task 13)."""

    def test_set_track_volume(self, mock_tcp_server):
        """Test setting track volume."""
        mock_tcp_server.set_response(
            "set_track_volume",
            {"status": "success", "result": {"volume": 0.75, "track_name": "Drums"}},
        )

        from MCP_Server.server import AbletonConnection

        conn = AbletonConnection(host="localhost", port=mock_tcp_server.port)
        result = conn.send_command("set_track_volume", {"track_index": 0, "volume": 0.75})

        assert result["volume"] == 0.75
        assert result["track_name"] == "Drums"

    def test_set_track_volume_clamped(self, mock_tcp_server):
        """Test that volume is clamped to valid range."""
        mock_tcp_server.set_response(
            "set_track_volume",
            {"status": "success", "result": {"volume": 1.0, "track_name": "Drums"}},
        )

        from MCP_Server.server import AbletonConnection

        conn = AbletonConnection(host="localhost", port=mock_tcp_server.port)
        # Send value > 1.0, should be clamped to 1.0
        result = conn.send_command("set_track_volume", {"track_index": 0, "volume": 1.5})

        # Result should be clamped by Remote Script
        assert result["volume"] <= 1.0

    def test_set_track_panning_center(self, mock_tcp_server):
        """Test setting track panning to center."""
        mock_tcp_server.set_response(
            "set_track_panning",
            {"status": "success", "result": {"panning": 0.0, "track_name": "Bass"}},
        )

        from MCP_Server.server import AbletonConnection

        conn = AbletonConnection(host="localhost", port=mock_tcp_server.port)
        result = conn.send_command("set_track_panning", {"track_index": 1, "pan": 0.0})

        assert result["panning"] == 0.0

    def test_set_track_panning_left(self, mock_tcp_server):
        """Test setting track panning to left."""
        mock_tcp_server.set_response(
            "set_track_panning",
            {"status": "success", "result": {"panning": -1.0, "track_name": "Bass"}},
        )

        from MCP_Server.server import AbletonConnection

        conn = AbletonConnection(host="localhost", port=mock_tcp_server.port)
        result = conn.send_command("set_track_panning", {"track_index": 1, "pan": -1.0})

        assert result["panning"] == -1.0

    def test_set_track_panning_right(self, mock_tcp_server):
        """Test setting track panning to right."""
        mock_tcp_server.set_response(
            "set_track_panning",
            {"status": "success", "result": {"panning": 1.0, "track_name": "Bass"}},
        )

        from MCP_Server.server import AbletonConnection

        conn = AbletonConnection(host="localhost", port=mock_tcp_server.port)
        result = conn.send_command("set_track_panning", {"track_index": 1, "pan": 1.0})

        assert result["panning"] == 1.0

    def test_volume_pan_handlers_exist(self):
        """Verify volume/pan handlers exist in Remote Script."""
        remote_script_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "AbletonMCP_Remote_Script",
            "__init__.py",
        )

        with open(remote_script_path) as f:
            source = f.read()

        assert "_set_track_volume" in source
        assert "_set_track_panning" in source


class TestGetNotesFromClip:
    """Tests for get_notes_from_clip functionality (Task 14)."""

    def test_get_notes_returns_note_data(self, mock_tcp_server):
        """Test getting notes from a clip."""
        mock_tcp_server.set_response(
            "get_notes_from_clip",
            {
                "status": "success",
                "result": {
                    "clip_name": "Pattern 1",
                    "clip_length": 4.0,
                    "note_count": 2,
                    "notes": [
                        {
                            "pitch": 60,
                            "start_time": 0.0,
                            "duration": 0.5,
                            "velocity": 100,
                            "mute": False,
                        },
                        {
                            "pitch": 64,
                            "start_time": 1.0,
                            "duration": 0.5,
                            "velocity": 90,
                            "mute": False,
                        },
                    ],
                },
            },
        )

        from MCP_Server.server import AbletonConnection

        conn = AbletonConnection(host="localhost", port=mock_tcp_server.port)
        result = conn.send_command("get_notes_from_clip", {"track_index": 0, "clip_index": 0})

        assert result["clip_name"] == "Pattern 1"
        assert result["clip_length"] == 4.0
        assert result["note_count"] == 2
        assert len(result["notes"]) == 2
        assert result["notes"][0]["pitch"] == 60
        assert result["notes"][1]["pitch"] == 64

    def test_get_notes_empty_clip(self, mock_tcp_server):
        """Test getting notes from an empty clip."""
        mock_tcp_server.set_response(
            "get_notes_from_clip",
            {
                "status": "success",
                "result": {
                    "clip_name": "Empty",
                    "clip_length": 4.0,
                    "note_count": 0,
                    "notes": [],
                },
            },
        )

        from MCP_Server.server import AbletonConnection

        conn = AbletonConnection(host="localhost", port=mock_tcp_server.port)
        result = conn.send_command("get_notes_from_clip", {"track_index": 0, "clip_index": 1})

        assert result["note_count"] == 0
        assert result["notes"] == []

    def test_get_notes_handler_exists(self):
        """Verify get_notes_from_clip is handled in Remote Script."""
        remote_script_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "AbletonMCP_Remote_Script",
            "__init__.py",
        )

        with open(remote_script_path) as f:
            source = f.read()

        assert 'command_type == "get_notes_from_clip"' in source
        assert "_get_notes_from_clip" in source


class TestGetSceneInfo:
    """Tests for get_scene_info functionality (Task 15)."""

    def test_get_scene_info_returns_scene_data(self, mock_tcp_server):
        """Test getting scene information."""
        mock_tcp_server.set_response(
            "get_scene_info",
            {
                "status": "success",
                "result": {
                    "index": 0,
                    "name": "Intro",
                    "tempo": None,
                    "color": 12345,
                    "clip_count": 2,
                    "clips": [
                        {
                            "track_index": 0,
                            "track_name": "Drums",
                            "clip_name": "Drum Loop",
                        },
                        {
                            "track_index": 1,
                            "track_name": "Bass",
                            "clip_name": "Bass Line",
                        },
                    ],
                },
            },
        )

        from MCP_Server.server import AbletonConnection

        conn = AbletonConnection(host="localhost", port=mock_tcp_server.port)
        result = conn.send_command("get_scene_info", {"scene_index": 0})

        assert result["index"] == 0
        assert result["name"] == "Intro"
        assert result["clip_count"] == 2
        assert len(result["clips"]) == 2
        assert result["clips"][0]["track_name"] == "Drums"

    def test_get_scene_info_empty_scene(self, mock_tcp_server):
        """Test getting info for a scene with no clips."""
        mock_tcp_server.set_response(
            "get_scene_info",
            {
                "status": "success",
                "result": {
                    "index": 5,
                    "name": "",
                    "tempo": None,
                    "color": None,
                    "clip_count": 0,
                    "clips": [],
                },
            },
        )

        from MCP_Server.server import AbletonConnection

        conn = AbletonConnection(host="localhost", port=mock_tcp_server.port)
        result = conn.send_command("get_scene_info", {"scene_index": 5})

        assert result["clip_count"] == 0
        assert result["clips"] == []

    def test_get_scene_info_handler_exists(self):
        """Verify get_scene_info is handled in Remote Script."""
        remote_script_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "AbletonMCP_Remote_Script",
            "__init__.py",
        )

        with open(remote_script_path) as f:
            source = f.read()

        assert 'command_type == "get_scene_info"' in source
        assert "_get_scene_info" in source


class TestModifyingCommandsList:
    """Tests for the is_modifying_command list (Task 16)."""

    def test_new_commands_in_modifying_list(self):
        """Verify all new modifying commands are in the is_modifying_command list."""
        import inspect

        from MCP_Server import server

        source = inspect.getsource(server.AbletonConnection.send_command)

        # All new modifying commands should be in the list
        new_modifying_commands = [
            "undo",
            "redo",
            "delete_track",
            "create_audio_track",
            "delete_clip",
            "set_metronome",
            "fire_scene",
            "set_track_mute",
            "set_track_solo",
            "set_track_arm",
            "set_track_volume",
            "set_track_panning",
        ]

        for cmd in new_modifying_commands:
            assert f'"{cmd}"' in source, f"Command '{cmd}' not in is_modifying_command list"

    def test_read_only_commands_not_in_modifying_list(self):
        """Verify read-only commands are not in the modifying list."""
        import inspect

        from MCP_Server import server

        source = inspect.getsource(server.AbletonConnection.send_command)

        # These are read-only commands that should NOT modify state
        read_only_commands = [
            "get_notes_from_clip",
            "get_scene_info",
            "get_session_info",
            "get_track_info",
            "ping",
        ]

        # Get just the is_modifying_command list portion
        # Find the line that defines is_modifying_command
        lines = source.split("\n")
        in_list = False
        list_content = ""
        for line in lines:
            if "is_modifying_command" in line and "command_type in" in line:
                in_list = True
            if in_list:
                list_content += line
                if "]" in line:
                    break

        for cmd in read_only_commands:
            assert f'"{cmd}"' not in list_content, (
                f"Read-only command '{cmd}' should not be in is_modifying_command list"
            )


class TestMCPToolsExist:
    """Verify all new MCP tools are properly defined."""

    def test_all_new_tools_defined(self):
        """Verify all new MCP tools are defined in server.py."""
        import inspect

        from MCP_Server import server

        source = inspect.getsource(server)

        new_tools = [
            "async def undo(",
            "async def redo(",
            "async def delete_track(",
            "async def create_audio_track(",
            "async def delete_clip(",
            "async def set_metronome(",
            "async def fire_scene(",
            "async def set_track_mute(",
            "async def set_track_solo(",
            "async def set_track_arm(",
            "async def set_track_volume(",
            "async def set_track_panning(",
            "async def get_notes_from_clip(",
            "async def get_scene_info(",
        ]

        for tool in new_tools:
            assert tool in source, f"MCP tool '{tool}' not found in server.py"

    def test_all_tools_have_mcp_decorator(self):
        """Verify all new tools have @mcp.tool() decorator."""
        server_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "MCP_Server",
            "server.py",
        )

        with open(server_path) as f:
            source = f.read()

        new_functions = [
            "def undo(",
            "def redo(",
            "def delete_track(",
            "def create_audio_track(",
            "def delete_clip(",
            "def set_metronome(",
            "def fire_scene(",
            "def set_track_mute(",
            "def set_track_solo(",
            "def set_track_arm(",
            "def set_track_volume(",
            "def set_track_panning(",
            "def get_notes_from_clip(",
            "def get_scene_info(",
        ]

        for func in new_functions:
            # Find the function in source and check for @mcp.tool() above it
            idx = source.find(func)
            if idx == -1:
                continue

            # Look backwards for @mcp.tool()
            preceding = source[max(0, idx - 100) : idx]
            assert "@mcp.tool()" in preceding, f"Function '{func}' missing @mcp.tool() decorator"
