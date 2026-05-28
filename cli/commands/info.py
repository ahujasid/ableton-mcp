"""info command — show tool schema and help."""

import json as json_mod

import click

from cli.registry import get_tool, REGISTRY


@click.command("info")
@click.argument("tool_name")
@click.pass_context
def info_cmd(ctx, tool_name):
    """Show detailed info and parameters for a tool.

    \b
    Example:
      ableton-cli info set_tempo
      ableton-cli info create_clip
    """
    tool = get_tool(tool_name)
    if not tool:
        # Suggest similar tools
        suggestions = [t for t in REGISTRY if tool_name.lower() in t.lower()]
        msg = f"Unknown tool '{tool_name}'."
        if suggestions:
            msg += f" Did you mean: {', '.join(suggestions[:5])}?"
        raise click.ClickException(msg)

    output_json = ctx.obj.get("json", False)

    if output_json:
        data = {
            "name": tool.name,
            "command": tool.command,
            "group": tool.group,
            "description": tool.description,
            "params": {
                name: {
                    "type": p.type,
                    "required": p.required,
                    "default": p.default,
                    "help": p.help,
                }
                for name, p in tool.params.items()
            },
        }
        click.echo(json_mod.dumps(data, indent=2))
        return

    click.secho(f"\n  {tool.name}", fg="green", bold=True)
    click.echo(f"  {tool.description}")
    click.echo(f"  Group: {click.style(tool.group, fg='cyan')}")
    click.echo(f"  Command: {tool.command}")

    if tool.params:
        click.echo(f"\n  {'Parameter':<25s} {'Type':<8s} {'Required':<10s} {'Default':<12s} Description")
        click.echo(f"  {'─' * 25} {'─' * 8} {'─' * 10} {'─' * 12} {'─' * 30}")
        for name, p in tool.params.items():
            req = click.style("yes", fg="red") if p.required else "no"
            default = str(p.default) if p.default is not None else "—"
            click.echo(f"  {name:<25s} {p.type:<8s} {req:<19s} {default:<12s} {p.help}")
    else:
        click.echo("\n  No parameters")

    # Show usage example
    click.echo(f"\n  Usage:")
    if tool.params:
        json_example = {}
        for name, p in tool.params.items():
            if p.type == "int":
                json_example[name] = p.default if p.default is not None else 0
            elif p.type == "float":
                json_example[name] = p.default if p.default is not None else 0.0
            elif p.type == "bool":
                json_example[name] = p.default if p.default is not None else True
            elif p.type == "json":
                json_example[name] = "..."
            else:
                json_example[name] = p.default if p.default not in (None, "") else "value"
        click.echo(f"    ableton-cli call {tool.name} '{json_mod.dumps(json_example)}'")
        # Named args version
        parts = []
        for name, p in tool.params.items():
            if p.required:
                flag = f"--{name.replace('_', '-')}"
                if p.type == "int":
                    parts.append(f"{flag} 0")
                elif p.type == "float":
                    parts.append(f"{flag} 0.0")
                elif p.type == "bool":
                    parts.append(f"{flag} true")
                else:
                    parts.append(f"{flag} value")
        if parts:
            click.echo(f"    ableton-cli call {tool.name} {' '.join(parts)}")
    else:
        click.echo(f"    ableton-cli call {tool.name}")
    click.echo()
