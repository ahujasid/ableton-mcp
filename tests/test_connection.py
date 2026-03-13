"""Tests verifying thread-safe connection access and protocol adoption in source files.

These tests grep the actual source files on disk to confirm that:
- threading.Lock protects _ableton_connection access
- No time.sleep calls exist in the send_command method
- No sendall(b'') liveness test pattern exists
- Remote Script has a ping command handler
- Both files use struct.pack for length-prefix framing
"""

import re


def test_lock_serializes_access(server_source: str) -> None:
    """Verify _connection_lock exists and is a threading.Lock in server.py."""
    assert "_connection_lock" in server_source, (
        "Missing '_connection_lock' variable in server.py"
    )
    assert "threading.Lock()" in server_source, (
        "Missing 'threading.Lock()' creation in server.py"
    )
    assert "with _connection_lock" in server_source, (
        "Missing 'with _connection_lock' usage in get_ableton_connection"
    )


def test_no_time_sleep_in_send_command(server_source: str) -> None:
    """Verify send_command method does not contain time.sleep calls."""
    # Extract the send_command method body
    match = re.search(
        r"def send_command\(.*?\n(.*?)(?=\n    def |\nclass |\n[a-zA-Z@])",
        server_source,
        re.DOTALL,
    )
    assert match is not None, "Could not find send_command method in server.py"

    method_body = match.group(1)
    assert "time.sleep" not in method_body, (
        f"Found 'time.sleep' in send_command method body -- "
        f"artificial delays should be removed"
    )


def test_no_sendall_empty_bytes(server_source: str) -> None:
    """Verify server.py does not contain sendall(b'') or sendall(b\"\") pattern."""
    assert "sendall(b'')" not in server_source, (
        "Found sendall(b'') in server.py -- "
        "empty bytes liveness test should be replaced with ping command"
    )
    assert 'sendall(b"")' not in server_source, (
        'Found sendall(b"") in server.py -- '
        "empty bytes liveness test should be replaced with ping command"
    )


def test_ping_command_exists(remote_script_source: str) -> None:
    """Verify 'ping' appears in the Remote Script's command dispatch."""
    # Check for ping in the command dispatch (either as string literal or method)
    assert '"ping"' in remote_script_source or "'ping'" in remote_script_source, (
        "Missing 'ping' command handler in Remote Script dispatch"
    )


def test_struct_pack_in_both_files(
    remote_script_source: str, server_source: str
) -> None:
    """Verify both files use struct.pack for length-prefix framing."""
    assert "struct.pack" in remote_script_source, (
        "Missing struct.pack in Remote Script -- length-prefix framing not implemented"
    )
    assert "struct.pack" in server_source, (
        "Missing struct.pack in MCP Server -- length-prefix framing not implemented"
    )


def test_struct_unpack_in_both_files(
    remote_script_source: str, server_source: str
) -> None:
    """Verify both files use struct.unpack for length-prefix framing."""
    assert "struct.unpack" in remote_script_source, (
        "Missing struct.unpack in Remote Script -- length-prefix framing not implemented"
    )
    assert "struct.unpack" in server_source, (
        "Missing struct.unpack in MCP Server -- length-prefix framing not implemented"
    )


def test_no_receive_full_response(server_source: str) -> None:
    """Verify receive_full_response method has been removed/replaced."""
    assert "def receive_full_response" not in server_source, (
        "receive_full_response method still exists in server.py -- "
        "should be replaced with recv_message"
    )


def test_import_struct_in_both_files(
    remote_script_source: str, server_source: str
) -> None:
    """Verify both files import struct module."""
    assert "import struct" in remote_script_source, (
        "Missing 'import struct' in Remote Script"
    )
    assert "import struct" in server_source, (
        "Missing 'import struct' in MCP Server"
    )
