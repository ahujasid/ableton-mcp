"""list command — show all available tools."""

import json as json_mod

import click

from cli.registry import REGISTRY, get_all_groups, get_tools_by_group


@click.command("list")
@click.option("--group", "-g", default=None, help="Filter by group (e.g. session, tracks, clips)")
@click.pass_context
def list_cmd(ctx, group):
    """List all available Ableton tools."""
    output_json = ctx.obj.get("json", False)

    if output_json:
        if group:
            tools = get_tools_by_group(group)
        else:
            tools = list(REGISTRY.values())
        data = [
            {"name": t.name, "group": t.group, "description": t.description}
            for t in tools
        ]
        click.echo(json_mod.dumps(data, indent=2))
        return

    groups = [group] if group else get_all_groups()
    for g in groups:
        tools = get_tools_by_group(g)
        if not tools:
            continue
        click.secho(f"\n  {g.upper()}", fg="cyan", bold=True)
        for t in tools:
            click.echo(f"    {click.style(t.name, fg='green'):<40s} {t.description}")

    total = sum(len(get_tools_by_group(g)) for g in groups)
    click.echo(f"\n  {total} tools available")
