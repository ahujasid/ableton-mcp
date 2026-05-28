"""CLI connection helper — wraps MCP_Server.connection for CLI use."""

import sys

from MCP_Server.connection import AbletonConnection


def get_connection(host: str = "localhost", port: int = 9877) -> AbletonConnection:
    """Create and validate a connection to Ableton, or exit with error."""
    conn = AbletonConnection(host=host, port=port)
    if not conn.connect():
        print(f"Error: Could not connect to Ableton at {host}:{port}", file=sys.stderr)
        print("Make sure the Ableton Remote Script is running.", file=sys.stderr)
        sys.exit(1)
    return conn
