"""interactive command — REPL for Ableton CLI."""

import json as json_mod
import shlex

import click

from cli.registry import REGISTRY, get_tool, search_tools, get_all_groups, get_tools_by_group
from cli.connection import get_connection


def _print_help():
    click.echo()
    click.secho("  Ableton CLI Interactive Mode", fg="cyan", bold=True)
    click.echo("  Commands:")
    click.echo("    list [group]          List tools (optionally filtered by group)")
    click.echo("    info <tool>           Show tool details")
    click.echo("    grep <pattern>        Search tools")
    click.echo("    call <tool> [json]    Call a tool")
    click.echo("    <tool> [json]         Shorthand for 'call <tool> [json]'")
    click.echo("    help                  Show this help")
    click.echo("    exit / quit           Exit")
    click.echo()


def _handle_list(args):
    group = args[0] if args else None
    groups = [group] if group else get_all_groups()
    for g in groups:
        tools = get_tools_by_group(g)
        if not tools:
            continue
        click.secho(f"\n  {g.upper()}", fg="cyan", bold=True)
        for t in tools:
            click.echo(f"    {click.style(t.name, fg='green'):<40s} {t.description}")
    total = sum(len(get_tools_by_group(g)) for g in groups)
    click.echo(f"\n  {total} tools")


def _handle_info(args):
    if not args:
        click.echo("  Usage: info <tool_name>")
        return
    tool = get_tool(args[0])
    if not tool:
        click.echo(f"  Unknown tool '{args[0]}'")
        return
    click.secho(f"\n  {tool.name}", fg="green", bold=True)
    click.echo(f"  {tool.description}")
    if tool.params:
        for name, p in tool.params.items():
            req = "*" if p.required else " "
            default = f" (default: {p.default})" if p.default is not None else ""
            click.echo(f"    {req} {name}: {p.type}{default} — {p.help}")
    click.echo()


def _handle_grep(args):
    if not args:
        click.echo("  Usage: grep <pattern>")
        return
    matches = search_tools(args[0])
    if not matches:
        click.echo(f"  No tools matching '{args[0]}'")
        return
    for t in matches:
        click.echo(f"    {click.style(t.name, fg='green'):<40s} {t.description}")


def _handle_call(args, conn):
    if not args:
        click.echo("  Usage: call <tool_name> [json_args]")
        return

    tool_name = args[0]
    tool = get_tool(tool_name)
    if not tool:
        click.echo(f"  Unknown tool '{tool_name}'")
        return

    # Parse JSON args if provided
    params = {}
    if len(args) > 1:
        json_str = " ".join(args[1:])
        try:
            params = json_mod.loads(json_str)
        except json_mod.JSONDecodeError as e:
            click.echo(f"  Invalid JSON: {e}")
            return
    else:
        # Fill defaults
        for name, p in tool.params.items():
            if not p.required:
                params[name] = p.default

    # Check required params
    for name, p in tool.params.items():
        if p.required and name not in params:
            click.echo(f"  Missing required param: {name}")
            return

    try:
        result = conn.send_command(tool.command, params)
        click.echo(json_mod.dumps(result, indent=2))
    except Exception as e:
        click.secho(f"  Error: {e}", fg="red")


@click.command("interactive")
@click.pass_context
def interactive_cmd(ctx):
    """Start an interactive REPL session.

    \b
    Maintains a persistent connection to Ableton for fast repeated calls.
    """
    host = ctx.obj.get("host", "localhost")
    port = ctx.obj.get("port", 9877)

    click.secho("\n  Connecting to Ableton...", fg="yellow")
    conn = get_connection(host, port)
    click.secho(f"  Connected to {host}:{port}", fg="green")
    _print_help()

    try:
        while True:
            try:
                line = input(click.style("ableton> ", fg="cyan"))
            except (EOFError, KeyboardInterrupt):
                click.echo()
                break

            line = line.strip()
            if not line:
                continue

            try:
                parts = shlex.split(line)
            except ValueError:
                parts = line.split()

            cmd = parts[0].lower()
            args = parts[1:]

            if cmd in ("exit", "quit", "q"):
                break
            elif cmd == "help":
                _print_help()
            elif cmd == "list":
                _handle_list(args)
            elif cmd == "info":
                _handle_info(args)
            elif cmd == "grep":
                _handle_grep(args)
            elif cmd == "call":
                _handle_call(args, conn)
            elif cmd in REGISTRY:
                # Shorthand: tool_name directly
                _handle_call([cmd] + args, conn)
            else:
                click.echo(f"  Unknown command: '{cmd}'. Type 'help' for available commands.")
    finally:
        conn.disconnect()
        click.echo("  Disconnected.")
