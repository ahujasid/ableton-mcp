#!/usr/bin/env python3
"""ableton-cli: Direct CLI for Ableton MCP Remote Script.

Usage:
    ableton-cli get_session_info
    ableton-cli set_tempo --tempo 128
    ableton-cli create_midi_track --index -1
    ableton-cli get_all_tracks_info
    ableton-cli add_notes_to_clip --track_index 0 --clip_index 0 --notes '[{"pitch":60,"start_time":0,"duration":0.5,"velocity":100}]'

Run without args for interactive mode.
"""

import argparse
import json
import logging
import os
import sys

logging.disable(logging.CRITICAL)

# Import connection module directly to avoid pulling in the full MCP server
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "MCP_Server"))
from connection import AbletonConnection


def connect():
    conn = AbletonConnection(host="localhost", port=9877)
    if not conn.connect():
        print("Error: Could not connect to Ableton. Is the AbletonMCP control surface enabled?", file=sys.stderr)
        sys.exit(1)
    return conn


def run_command(conn, command_type, params=None):
    try:
        result = conn.send_command(command_type, params or {})
        print(json.dumps(result, indent=2))
        return result
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return None


def interactive(conn):
    print("Ableton CLI (interactive). Type 'help' for commands, 'quit' to exit.")
    while True:
        try:
            line = input("ableton> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        if line in ("quit", "exit"):
            break
        if line == "help":
            print("Commands: get_session_info, get_all_tracks_info, set_tempo <bpm>,")
            print("  create_midi_track, create_audio_track, set_track_name <idx> <name>,")
            print("  create_clip <track> <clip> <length>, add_notes_to_clip <track> <clip> <json>,")
            print("  Any command_type [json_params]")
            print("  quit/exit")
            continue

        parts = line.split(None, 1)
        cmd = parts[0]
        params = {}
        if len(parts) > 1:
            try:
                params = json.loads(parts[1])
            except json.JSONDecodeError:
                # Try simple key=value parsing for convenience
                for token in parts[1].split():
                    if "=" in token:
                        k, v = token.split("=", 1)
                        try:
                            v = json.loads(v)
                        except json.JSONDecodeError:
                            pass
                        params[k] = v
        run_command(conn, cmd, params)


def main():
    if len(sys.argv) < 2:
        conn = connect()
        interactive(conn)
        conn.disconnect()
        return

    parser = argparse.ArgumentParser(description="Ableton CLI")
    parser.add_argument("command", help="Command to send (e.g. get_session_info)")
    parser.add_argument("--params", "-p", help="JSON params", default="{}")
    # Common shorthand args
    parser.add_argument("--tempo", type=float)
    parser.add_argument("--index", type=int)
    parser.add_argument("--track_index", type=int)
    parser.add_argument("--clip_index", type=int)
    parser.add_argument("--name", type=str)
    parser.add_argument("--notes", type=str)
    parser.add_argument("--length", type=float)
    parser.add_argument("--volume", type=float)
    parser.add_argument("--pan", type=float)
    parser.add_argument("--mute", type=bool)
    parser.add_argument("--solo", type=bool)

    args = parser.parse_args()
    params = json.loads(args.params)

    # Merge shorthand args into params
    for key in ["tempo", "index", "track_index", "clip_index", "name", "notes", "length", "volume", "pan", "mute", "solo"]:
        val = getattr(args, key, None)
        if val is not None:
            if key == "notes":
                val = json.loads(val)
            params[key] = val

    conn = connect()
    run_command(conn, args.command, params)
    conn.disconnect()


if __name__ == "__main__":
    main()
