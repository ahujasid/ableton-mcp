"""call command — execute an Ableton tool."""

import json as json_mod
import sys

import click

from cli.registry import get_tool
from cli.connection import get_connection


def _parse_value(value_str: str, param_type: str):
    """Parse a string value into the correct Python type."""
    if param_type == "int":
        return int(value_str)
    elif param_type == "float":
        return float(value_str)
    elif param_type == "bool":
        if value_str.lower() in ("true", "1", "yes"):
            return True
        elif value_str.lower() in ("false", "0", "no"):
            return False
        raise click.BadParameter(f"Invalid bool: {value_str}")
    elif param_type == "json":
        return json_mod.loads(value_str)
    return value_str


def _build_params(tool, json_args, named_args):
    """Build params dict from either JSON string or --key=value args."""
    if json_args:
        try:
            params = json_mod.loads(json_args)
        except json_mod.JSONDecodeError as e:
            raise click.ClickException(f"Invalid JSON: {e}")
        if not isinstance(params, dict):
            raise click.ClickException("JSON args must be an object")
        return params

    # Parse named --key=value args
    params = {}
    i = 0
    while i < len(named_args):
        arg = named_args[i]
        if arg.startswith("--"):
            key = arg[2:].replace("-", "_")
            if "=" in key:
                key, val = key.split("=", 1)
            elif i + 1 < len(named_args) and not named_args[i + 1].startswith("--"):
                i += 1
                val = named_args[i]
            else:
                val = "true"  # bare flag
            if key in tool.params:
                params[key] = _parse_value(val, tool.params[key].type)
            else:
                raise click.ClickException(
                    f"Unknown parameter '--{key}' for tool '{tool.name}'. "
                    f"Available: {', '.join(tool.params.keys())}"
                )
        i += 1

    # Fill defaults for missing optional params
    for name, param in tool.params.items():
        if name not in params:
            if param.required:
                raise click.ClickException(
                    f"Missing required parameter '--{name}' for tool '{tool.name}'"
                )
            params[name] = param.default

    return params


@click.command("call")
@click.argument("tool_name")
@click.argument("json_args", required=False, default=None)
@click.argument("extra_args", nargs=-1, type=click.UNPROCESSED)
@click.pass_context
def call_cmd(ctx, tool_name, json_args, extra_args):
    """Call an Ableton tool.

    \b
    Examples:
      ableton-cli call get_session_info
      ableton-cli call set_tempo '{"tempo": 120}'
      ableton-cli call set_tempo --tempo 120
      echo '{"tempo": 120}' | ableton-cli call set_tempo
    """
    tool = get_tool(tool_name)
    if not tool:
        raise click.ClickException(
            f"Unknown tool '{tool_name}'. Run 'ableton-cli list' to see available tools."
        )

    output_json = ctx.obj.get("json", False)
    host = ctx.obj.get("host", "localhost")
    port = ctx.obj.get("port", 9877)

    # Check for stdin if no args provided
    if json_args is None and not extra_args and not sys.stdin.isatty():
        json_args = sys.stdin.read().strip()

    # Detect if json_args is actually a --flag (user passed named args without JSON)
    named_args = list(extra_args)
    if json_args and json_args.startswith("--"):
        named_args = [json_args] + named_args
        json_args = None

    params = _build_params(tool, json_args, named_args)

    # Special handling for tools that need custom logic
    if tool_name == "clip_to_grid":
        _handle_clip_to_grid(host, port, params, output_json)
        return
    if tool_name == "grid_to_clip":
        _handle_grid_to_clip(host, port, params, output_json)
        return

    conn = get_connection(host, port)
    try:
        result = conn.send_command(tool.command, params)
        if output_json or tool.returns_json:
            click.echo(json_mod.dumps(result, indent=2))
        else:
            if isinstance(result, dict):
                click.echo(json_mod.dumps(result, indent=2))
            else:
                click.echo(result)
    except Exception as e:
        raise click.ClickException(str(e))
    finally:
        conn.disconnect()


def _handle_clip_to_grid(host, port, params, output_json):
    """Special handler for clip_to_grid (needs grid_notation module)."""
    from MCP_Server.grid_notation import notes_to_grid

    conn = get_connection(host, port)
    try:
        result = conn.send_command("get_notes_from_clip", params)
        notes = result.get("notes", [])
        clip_length = result.get("clip_length", 4.0)
        clip_name = result.get("clip_name", "Unknown")
        grid = notes_to_grid(notes, clip_length)

        if output_json:
            click.echo(json_mod.dumps({
                "clip_name": clip_name,
                "clip_length": clip_length,
                "grid": grid,
            }, indent=2))
        else:
            click.echo(f"Clip: {clip_name} ({clip_length} beats)\n")
            click.echo(grid)
    except Exception as e:
        raise click.ClickException(str(e))
    finally:
        conn.disconnect()


def _handle_grid_to_clip(host, port, params, output_json):
    """Special handler for grid_to_clip (needs grid_notation module)."""
    from MCP_Server.grid_notation import parse_grid

    grid_str = params.pop("grid")
    length = params.pop("length", 4.0)
    notes = parse_grid(grid_str)

    conn = get_connection(host, port)
    try:
        # Create the clip first (ignore error if it exists)
        try:
            conn.send_command("create_clip", {
                "track_index": params["track_index"],
                "clip_index": params["clip_index"],
                "length": length,
            })
        except Exception:
            pass

        conn.send_command("add_notes_to_clip", {
            "track_index": params["track_index"],
            "clip_index": params["clip_index"],
            "notes": notes,
        })

        msg = f"Wrote {len(notes)} notes from grid to track {params['track_index']}, slot {params['clip_index']}"
        if output_json:
            click.echo(json_mod.dumps({"message": msg, "note_count": len(notes)}, indent=2))
        else:
            click.echo(msg)
    except Exception as e:
        raise click.ClickException(str(e))
    finally:
        conn.disconnect()
