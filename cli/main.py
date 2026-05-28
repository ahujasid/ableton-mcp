"""Ableton CLI entry point."""

import click

from cli.commands.list_cmd import list_cmd
from cli.commands.call import call_cmd
from cli.commands.info import info_cmd
from cli.commands.grep import grep_cmd
from cli.commands.interactive import interactive_cmd


@click.group()
@click.option("--host", default="localhost", help="Ableton Remote Script host")
@click.option("--port", default=9877, type=int, help="Ableton Remote Script port")
@click.option("--json", "output_json", is_flag=True, help="Force JSON output")
@click.pass_context
def cli(ctx, host, port, output_json):
    """Ableton CLI — control Ableton Live from the command line."""
    ctx.ensure_object(dict)
    ctx.obj["host"] = host
    ctx.obj["port"] = port
    ctx.obj["json"] = output_json


cli.add_command(list_cmd, "list")
cli.add_command(call_cmd, "call")
cli.add_command(info_cmd, "info")
cli.add_command(grep_cmd, "grep")
cli.add_command(interactive_cmd, "interactive")


def main():
    cli()


if __name__ == "__main__":
    main()
