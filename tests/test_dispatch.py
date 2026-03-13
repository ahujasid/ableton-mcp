"""Tests verifying dict-based command dispatch in the Remote Script.

These tests grep the actual source files on disk to confirm that:
- _read_commands and _write_commands dispatch dicts exist
- No if/elif command dispatch chain remains in _process_command
- Unknown commands return a clear error message naming the command
- All existing command type strings are registered in dispatch dicts
"""

import re
import pytest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_dict_dispatch_exists(remote_script_source: str) -> None:
    """Verify _read_commands and _write_commands dicts exist as class attributes."""
    assert re.search(r"self\._read_commands\s*[=:{]", remote_script_source), (
        "Missing _read_commands dict -- dict-based dispatch should define self._read_commands"
    )
    assert re.search(r"self\._write_commands\s*[=:{]", remote_script_source), (
        "Missing _write_commands dict -- dict-based dispatch should define self._write_commands"
    )


def test_no_elif_chain(remote_script_source: str) -> None:
    """Verify _process_command does not contain if/elif dispatch chain."""
    # Extract _process_command method body
    match = re.search(
        r"def _process_command\(self.*?\).*?(?=\n    def |\nclass |\Z)",
        remote_script_source,
        re.DOTALL,
    )
    assert match, "Could not find _process_command method"
    method_body = match.group(0)

    assert "elif command_type ==" not in method_body, (
        "Found 'elif command_type ==' in _process_command -- "
        "should use dict-based dispatch instead of if/elif chain"
    )
    assert "elif command_type in" not in method_body, (
        "Found 'elif command_type in' in _process_command -- "
        "should use dict-based dispatch instead of batch check pattern"
    )


def test_unknown_command_error(remote_script_source: str) -> None:
    """Verify _process_command returns error with command name for unknown commands."""
    match = re.search(
        r"def _process_command\(self.*?\).*?(?=\n    def |\nclass |\Z)",
        remote_script_source,
        re.DOTALL,
    )
    assert match, "Could not find _process_command method"
    method_body = match.group(0)

    assert "Unknown command" in method_body, (
        "Missing 'Unknown command' error message in _process_command -- "
        "unknown commands should return a clear error naming the command"
    )


def test_ping_in_read_commands(remote_script_source: str) -> None:
    """Verify 'ping' is registered as a key in _read_commands dict."""
    # Find the _read_commands dict definition
    match = re.search(
        r"self\._read_commands\s*(?::\s*dict\[.*?\]\s*)?=\s*\{([^}]+)\}",
        remote_script_source,
        re.DOTALL,
    )
    assert match, "Could not find _read_commands dict definition"
    dict_body = match.group(1)

    assert '"ping"' in dict_body, (
        "Missing 'ping' key in _read_commands dict -- "
        "ping should be registered as a read command"
    )


def test_all_existing_commands_registered(remote_script_source: str) -> None:
    """Verify all command type strings appear as dict keys in dispatch tables."""
    expected_commands = [
        "get_session_info",
        "get_track_info",
        "create_midi_track",
        "set_track_name",
        "create_clip",
        "add_notes_to_clip",
        "set_clip_name",
        "set_tempo",
        "fire_clip",
        "stop_clip",
        "start_playback",
        "stop_playback",
        "load_browser_item",
        "get_browser_item",
        "get_browser_categories",
        "get_browser_items",
        "get_browser_tree",
        "get_browser_items_at_path",
        "ping",
    ]

    for cmd in expected_commands:
        assert f'"{cmd}"' in remote_script_source, (
            f"Command '{cmd}' not found as a dict key in Remote Script source -- "
            f"all existing commands should be registered in dispatch dicts"
        )
