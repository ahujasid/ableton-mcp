#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# ///
"""talk to the AbletonMCP remote script socket directly, bypassing the MCP server.

usage:
  scripts/abl.py get_session_info
  scripts/abl.py get_track_info '{"track_index": 0}'
  scripts/abl.py introspect '{"path": "tracks[0].devices[1]"}'
"""
import json
import socket
import sys


def call(cmd: str, params: dict | None = None, host: str = "localhost", port: int = 9877, timeout: float = 15.0) -> dict:
    s = socket.create_connection((host, port), timeout=timeout)
    s.sendall(json.dumps({"type": cmd, "params": params or {}}).encode())
    chunks: list[bytes] = []
    while True:
        chunk = s.recv(65536)
        if not chunk:
            break
        chunks.append(chunk)
        try:
            return json.loads(b"".join(chunks).decode())
        except json.JSONDecodeError:
            continue
    raise SystemExit("connection closed without a full json response")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    params = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    timeout = float(params.get("seconds", 0)) + 15.0
    print(json.dumps(call(sys.argv[1], params, timeout=timeout), indent=2))
