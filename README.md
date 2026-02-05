ableton-mcp fork of https://github.com/ahujasid/ableton-mcp by https://github.com/ahujasid

Installation:

dw repo https://github.com/BuggedPlayer/ableton-mcp-beta/releases/tag/ableton
unzip repo where you prefer
dw Claude https://claude.com/download
dw Wisp flow (for vocal input into claude)

powershell

install uv        powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
uv python install 
uv sync
script

copy ableton script into ableton folder
add ableton script into midi settings
update claude script with (claude-settings-develoe-settings)

{
  "mcpServers": {
    "AbletonMCP": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "location of the repo",
        "ableton-mcp"
      ]
    }
  },
  "preferences": {
    "coworkScheduledTasksEnabled": false,
    "sidebarMode": "chat"
  }
}

rename repo/.venv/pyenv.cfg with your windows username

restart claude
open ableton
open a new chat in claude
say connect to ableton/live
