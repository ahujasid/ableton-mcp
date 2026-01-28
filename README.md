# AbletonMCP Enhanced - AI Control for Ableton Live
[![smithery badge](https://smithery.ai/badge/@itsuzef/ableton-mcp)](https://smithery.ai/server/@itsuzef/ableton-mcp/deployments)

This tool connects Ableton Live to AI assistants like Claude and Cursor through the Model Context Protocol (MCP), allowing you to control Ableton Live with natural language commands.

This is an enhanced fork of the original [AbletonMCP](https://github.com/ahujasid/ableton-mcp) by Siddharth Ahuja, with significant improvements to make it easier to install and use.

## What You Can Do With This Tool

- Create and manipulate MIDI and audio tracks
- Load instruments, effects, and sounds from Ableton's library
- Create and edit MIDI clips with notes
- Control playback (start, stop, fire clips)
- Adjust device parameters (like EQ settings)
- And much more!

## Quick Start Guide for Music Producers

### Option 1: Install via Smithery (Easiest)

If you're using Claude Desktop, the easiest way to install is with Smithery:

```bash
npx -y @smithery/cli install @itsuzef/ableton-mcp --client claude
```

This will automatically set up the MCP server in Claude Desktop. You'll still need to install the Ableton Remote Script (see Step 4 below).

### Option 2: Manual Installation

#### Step 1: Install Python (One-time setup)

If you don't have Python installed:

1. Download and install Python 3.10 or newer:
   - For Mac: [Download Python](https://www.python.org/downloads/)
   - For Windows: [Download Python](https://www.python.org/downloads/windows/)

2. During installation, make sure to check "Add Python to PATH"

#### Step 2: Install AbletonMCP (One-time setup)

Open Terminal (Mac) or Command Prompt (Windows) and run these commands:

```bash
# Create a folder for AbletonMCP
python -m venv ableton-mcp-env

# On Mac/Linux:
source ableton-mcp-env/bin/activate

# On Windows:
ableton-mcp-env\Scripts\activate

# Install AbletonMCP
pip install git+https://github.com/itsuzef/ableton-mcp.git
```

#### Step 3: Install the Ableton Remote Script (One-time setup)

With the same Terminal/Command Prompt window open:

```bash
# Install the Remote Script to Ableton
ableton-mcp install
```

If the automatic installation doesn't work, the tool will tell you where to manually place the files.

#### Step 4: Set Up Ableton Live (One-time setup)

1. Launch Ableton Live
2. Go to Preferences → Link, Tempo & MIDI
3. In the Control Surface dropdown, select "AbletonMCP_Remote_Script"
4. Set Input and Output to "None"
5. Click "OK" to save settings

#### Step 5: Connect to Your AI Assistant

#### For Claude Desktop:

1. Go to Claude → Settings → Developer → Edit Config
2. Add this to your `claude_desktop_config.json`:

```json
{
    "mcpServers": {
        "AbletonMCP": {
            "command": "PATH_TO_YOUR_ENVIRONMENT/bin/ableton-mcp",
            "args": [
                "server"
            ]
        }
    }
}
```

Replace `PATH_TO_YOUR_ENVIRONMENT` with the full path to where you created your environment. For example:
- Mac: `/Users/yourusername/ableton-mcp-env`
- Windows: `C:\Users\yourusername\ableton-mcp-env`

#### For Cursor:

1. Go to Cursor Settings → MCP
2. Add this command:

```
PATH_TO_YOUR_ENVIRONMENT/bin/ableton-mcp server
```

Replace `PATH_TO_YOUR_ENVIRONMENT` as explained above.

#### For Other AI Tools:

Any AI tool that supports MCP can be connected by pointing it to the `ableton-mcp server` command in your environment.

#### Step 6: Start Creating Music with AI!

1. Open Ableton Live
2. Open your AI assistant (Claude, Cursor, etc.)
3. Start asking your AI to control Ableton!

> **Note**: If you installed via Smithery (Option 1), you can skip steps 1-3 and 5 of the manual installation. You only need to install the Ableton Remote Script (Step 4) and then you're ready to go!

## Example Commands to Try

- "Create a new MIDI track with a synth bass instrument"
- "Add reverb to track 1"
- "Create a 4-bar MIDI clip with a simple melody"
- "Load a drum rack into track 2"
- "Add a jazz chord progression to the clip in track 1"
- "Set the tempo to 120 BPM"
- "Play the clip in track 2"
- "Apply a low cut EQ preset to track 1"

## Troubleshooting

### Connection Issues

- **Make sure Ableton Live is running** before using AI commands
- **Check that the Remote Script is enabled** in Ableton's MIDI preferences
- **Restart both Ableton and your AI assistant** if you're having connection problems

### Common Errors

- **"Command not found"**: Make sure you've activated your environment with `source ableton-mcp-env/bin/activate` (Mac/Linux) or `ableton-mcp-env\Scripts\activate` (Windows)
- **"Could not connect to Ableton"**: Ensure Ableton is running and the Remote Script is enabled
- **"Remote Script not found"**: Try running `ableton-mcp install` again or follow the manual installation instructions

### Getting Help

If you're still having issues, check the [GitHub issues page](https://github.com/itsuzef/ableton-mcp/issues) or create a new issue with details about your problem.

## Advanced Usage

For those comfortable with command line tools, AbletonMCP offers additional commands:

```bash
# Show version information
ableton-mcp version

# Show available MCP functions
ableton-mcp info

# Start the server with custom host/port
ableton-mcp server --host 127.0.0.1 --port 8080
```

## Acknowledgments

This project is based on the original [AbletonMCP](https://github.com/ahujasid/ableton-mcp) by Siddharth Ahuja. I've built upon that foundation to create an enhanced version with additional features and improvements.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Disclaimer

This is a third-party integration and not made by Ableton.
