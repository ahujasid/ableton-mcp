import inspect
import json
import re
import socket
import unittest
from unittest.mock import MagicMock, call, patch

from MCP_Server import server


NEW_TOOLS = {
    "get_capabilities",
    "get_mixer_parameters",
    "set_mixer_parameter",
    "set_mixer_parameters",
    "get_device_parameters",
    "set_device_parameter",
    "set_device_parameters",
    "get_clip_notes",
    "replace_clip_notes",
    "clear_clip_notes",
    "get_clip_properties",
    "get_output_meter_levels",
    "set_clip_loop",
    "delete_session_clip",
    "duplicate_session_clip",
    "duplicate_session_scene_clips",
    "fire_scene",
    "stop_all_clips",
    "back_to_arrangement",
    "duplicate_session_clip_to_arrangement",
    "delete_arrangement_clip",
}


class _Telemetry:
    def record_event(self, **kwargs):
        return None


class _Socket:
    def __init__(self, response):
        self.response = response
        self.timeouts = []
        self.sent = []
        self.closed = False

    def sendall(self, data):
        self.sent.append(data)

    def settimeout(self, value):
        self.timeouts.append(value)

    def recv(self, _buffer_size):
        if self.response is None:
            raise socket.timeout("timed out")
        response, self.response = self.response, None
        return response

    def close(self):
        self.closed = True


class ServerContractTests(unittest.TestCase):
    def _call(self, function, *args, **kwargs):
        with patch(
            "MCP_Server.telemetry_decorator.get_telemetry",
            return_value=_Telemetry(),
        ):
            return function(None, *args, **kwargs)

    def test_existing_and_mvp_tools_are_registered_with_json_schemas(self):
        registered = set(server.mcp._tool_manager._tools)
        self.assertTrue(NEW_TOOLS.issubset(registered))
        self.assertTrue(
            {"get_session_info", "create_clip", "add_notes_to_clip", "duplicate_to_arrangement"}
            .issubset(registered)
        )
        self.assertNotIn("replace_arrangement_clip", registered)
        self.assertNotIn("trim_arrangement_clip", registered)

        device_schema = server.mcp._tool_manager._tools["set_device_parameter"].parameters
        self.assertEqual(device_schema["properties"]["device_path"]["type"], "array")
        path_schema = device_schema["$defs"]["DevicePathItem"]
        self.assertEqual(path_schema["properties"]["index"]["type"], "integer")
        self.assertEqual(path_schema["properties"]["expected_name"]["type"], "string")
        self.assertEqual(path_schema["properties"]["expected_class_name"]["type"], "string")
        self.assertEqual(path_schema["properties"]["chain_index"]["type"], "integer")
        self.assertEqual(path_schema["properties"]["expected_chain_name"]["type"], "string")

        note_schema = server.mcp._tool_manager._tools["replace_clip_notes"].parameters
        self.assertEqual(note_schema["properties"]["notes"]["type"], "array")
        self.assertIn("ClipNote", note_schema["$defs"])

    def test_new_tools_use_basic_telemetry_only(self):
        source = inspect.getsource(server)
        for name in NEW_TOOLS:
            basic = re.search(
                rf'@telemetry_tool\("{re.escape(name)}"\)', source
            )
            rich = re.search(
                rf'@rich_telemetry_tool\("{re.escape(name)}"', source
            )
            self.assertIsNotNone(basic, name)
            self.assertIsNone(rich, name)

    def test_device_parameter_is_exact_pass_through_and_structured(self):
        connection = MagicMock()
        connection.send_command.return_value = {
            "target": {"parameter_index": 3},
            "previous": {"value": 0.4},
            "applied": {"value": 0.45},
        }
        path = [{
            "index": 0,
            "expected_name": "Bass Synth",
            "expected_class_name": "InstrumentDevice",
        }]

        with patch.object(server, "get_ableton_connection", return_value=connection):
            result = self._call(
                server.set_device_parameter,
                2,
                "Bass",
                path,
                3,
                "Cutoff",
                0.45,
                expected_current_value=0.4,
                tolerance=0.001,
                dry_run=False,
                overwrite=False,
            )

        connection.send_command.assert_called_once_with(
            "set_device_parameter",
            {
                "track_index": 2,
                "expected_track_name": "Bass",
                "track_kind": "track",
                "device_path": path,
                "parameter_index": 3,
                "expected_parameter_name": "Cutoff",
                "value": 0.45,
                "tolerance": 0.001,
                "dry_run": False,
                "overwrite": False,
                "expected_current_value": 0.4,
            },
        )
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["result"]["applied"]["value"], 0.45)

    def test_batch_mixer_parameters_are_passed_as_one_preflight_request(self):
        connection = MagicMock()
        connection.send_command.return_value = {"applied": 2, "changes": []}
        changes = [
            {
                "track_index": 1,
                "expected_track_name": "Bass",
                "parameter_name": "volume",
                "value": 0.75,
            },
            {
                "track_index": 2,
                "expected_track_name": "Lead",
                "parameter_name": "panning",
                "value": -0.1,
            },
        ]

        with patch.object(server, "get_ableton_connection", return_value=connection):
            result = self._call(
                server.set_mixer_parameters,
                changes,
                dry_run=True,
                overwrite=False,
            )

        connection.send_command.assert_called_once_with(
            "set_mixer_parameters",
            {"parameters": changes, "dry_run": True, "overwrite": False},
        )
        self.assertEqual(result["status"], "success")

    def test_remote_error_retains_command_code_and_details(self):
        connection = MagicMock()
        connection.send_command.side_effect = server.AbletonRemoteError(
            "Destination is occupied",
            command="delete_session_clip",
            code="destination_occupied",
            details={"track_index": 3, "clip_index": 4},
        )

        with patch.object(server, "get_ableton_connection", return_value=connection):
            result = self._call(
                server.delete_session_clip,
                3,
                "[MCP TEST] Bass",
                4,
                "[MCP TEST] A",
            )

        self.assertEqual(result["status"], "error")
        self.assertEqual(
            result["error"],
            {
                "type": "remote_error",
                "message": "Destination is occupied",
                "command": "delete_session_clip",
                "code": "destination_occupied",
                "details": {"track_index": 3, "clip_index": 4},
            },
        )

    def test_connection_classifies_remote_error_from_wire(self):
        response = json.dumps({
            "status": "error",
            "message": "Parameter changed",
            "code": "stale_value",
            "details": {"actual": 0.7},
        }).encode("utf-8")
        sock = _Socket(response)
        connection = server.AbletonConnection("127.0.0.1", 9877, sock=sock)

        with self.assertRaises(server.AbletonRemoteError) as caught:
            connection.send_command("set_device_parameter", {"value": 0.5})

        error = caught.exception
        self.assertEqual(error.command, "set_device_parameter")
        self.assertEqual(error.code, "stale_value")
        self.assertEqual(error.details, {"actual": 0.7})
        self.assertFalse(sock.closed)

    def test_timeout_classification_covers_new_mutations_and_reads(self):
        self.assertEqual(
            server.AbletonConnection.timeout_for_command("set_mixer_parameter"),
            server.MUTATION_TIMEOUT_SECONDS,
        )
        self.assertEqual(
            server.AbletonConnection.timeout_for_command("replace_clip_notes"),
            server.MUTATION_TIMEOUT_SECONDS,
        )
        self.assertEqual(
            server.AbletonConnection.timeout_for_command("get_device_parameters"),
            server.READ_TIMEOUT_SECONDS,
        )
        self.assertEqual(
            server.AbletonConnection.timeout_for_command("create_audio_clip"),
            65.0,
        )
        self.assertTrue(
            {
                "set_mixer_parameters",
                "set_device_parameters",
                "clear_clip_notes",
                "set_clip_loop",
                "duplicate_session_scene_clips",
                "fire_scene",
                "stop_all_clips",
                "back_to_arrangement",
                "delete_arrangement_clip",
            }.issubset(server.MODIFYING_COMMANDS)
        )

    def test_socket_timeout_is_structured_and_uses_mutation_budget(self):
        sock = _Socket(None)
        connection = server.AbletonConnection("127.0.0.1", 9877, sock=sock)

        with self.assertRaises(server.AbletonTimeoutError) as caught:
            connection.send_command("replace_clip_notes", {"notes": []})

        self.assertEqual(caught.exception.command, "replace_clip_notes")
        self.assertEqual(
            caught.exception.details["timeout_seconds"],
            server.MUTATION_TIMEOUT_SECONDS,
        )
        self.assertEqual(sock.timeouts[-1], server.MUTATION_TIMEOUT_SECONDS)
        self.assertTrue(sock.closed)

    def test_meter_and_quantized_audition_contracts_are_exact_pass_through(self):
        connection = MagicMock()
        connection.send_command.side_effect = [
            {"left": 0.2, "right": 0.3},
            {"applied": {"fired": True, "global_quantization": 4}},
            {"applied": True},
        ]
        with patch.object(server, "get_ableton_connection", return_value=connection):
            meter = self._call(
                server.get_output_meter_levels, 1, "Bass", track_kind="track"
            )
            fired = self._call(
                server.fire_scene, 7, "[MCP TEST] Scene",
                expected_global_quantization=4,
            )
            stopped = self._call(
                server.stop_all_clips, quantized=True, dry_run=False
            )

        assert meter["status"] == "success"
        assert fired["status"] == "success"
        assert stopped["status"] == "success"
        assert connection.send_command.call_args_list == [
            call(
                "get_output_meter_levels",
                {"track_index": 1, "expected_track_name": "Bass", "track_kind": "track"},
            ),
            call(
                "fire_scene",
                {"scene_index": 7, "expected_scene_name": "[MCP TEST] Scene",
                 "expected_global_quantization": 4},
            ),
            call(
                "stop_all_clips", {"quantized": True, "dry_run": False}
            ),
        ]


if __name__ == "__main__":
    unittest.main()
