"""grep command — search tools by name or description."""

import json as json_mod

import click

from cli.registry import search_tools


@click.command("grep")
@click.argument("pattern")
@click.pass_context
def grep_cmd(ctx, pattern):
    """Search tools by name or description.

    \b
    Examples:
      ableton-cli grep track
      ableton-cli grep "clip"
      ableton-cli grep midi
    """
    output_json = ctx.obj.get("json", False)
    matches = search_tools(pattern)

    if not matches:
        click.echo(f"No tools matching '{pattern}'")
        return

    if output_json:
        data = [
            {"name": t.name, "group": t.group, "description": t.description}
            for t in matches
        ]
        click.echo(json_mod.dumps(data, indent=2))
        return

    click.echo(f"\n  {len(matches)} tools matching '{pattern}':\n")
    for t in matches:
        group_tag = click.style(f"[{t.group}]", fg="cyan")
        click.echo(f"    {click.style(t.name, fg='green'):<40s} {group_tag:<20s} {t.description}")
    click.echo()
