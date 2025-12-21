# AbletonMCP - Ableton Live Model Context Protocol Integration
[![smithery badge](https://smithery.ai/badge/@ahujasid/ableton-mcp)](https://smithery.ai/server/@ahujasid/ableton-mcp)

AbletonMCP connects Ableton Live to Claude AI through the Model Context Protocol (MCP), allowing Claude to directly interact with and control Ableton Live. This integration enables prompt-assisted music production, track creation, and Live session manipulation.

### Join the Community

Give feedback, get inspired, and build on top of the MCP: [Discord](https://discord.gg/3ZrMyGKnaU). Made by [Siddharth](https://x.com/sidahuj)

## Features

- **Two-way communication**: Connect Claude AI to Ableton Live through a socket-based server
- **Track manipulation**: Create, modify, and manipulate MIDI and audio tracks
- **Instrument and effect selection**: Claude can access and load the right instruments, effects and sounds from Ableton's library
- **Clip creation**: Create and edit MIDI clips with notes
- **Session control**: Start and stop playback, fire clips, and control transport
- **Audio analysis**: Analyze audio for BPM, beats, chords, and descriptive AI analysis
- **Audio capture**: Record audio from Ableton for analysis
- **Groove alignment**: Align vocal/audio timing to drum grooves via warp markers

## Components

The system consists of several components:

1. **Ableton Remote Script** (`AbletonMCP_Remote_Script/__init__.py`): A MIDI Remote Script for Ableton Live that creates a socket server to receive and execute commands
2. **MCP Server** (`MCP_Server/server.py`): A Python server that implements the Model Context Protocol and connects to the Ableton Remote Script
3. **Audio Analysis** (`MCP_Server/audio_analysis.py`): Audio analysis tools including vocal-to-MIDI conversion and groove alignment
4. **ALS Warp Injector** (`MCP_Server/als_warp_injector.py`): Tool to inject warp markers directly into Ableton Live Set files
5. **Max for Live Devices** (`Max4Live/`): Helper devices for audio capture and warp marker application

## Installation

### Installing via Smithery

To install Ableton Live Integration for Claude Desktop automatically via [Smithery](https://smithery.ai/server/@ahujasid/ableton-mcp):

```bash
npx -y @smithery/cli install @ahujasid/ableton-mcp --client claude
```

### Prerequisites

- Ableton Live 10 or newer
- Python 3.8 or newer
- [uv package manager](https://astral.sh/uv)

If you're on Mac, please install uv as:
```
brew install uv
```

Otherwise, install from [uv's official website](https://docs.astral.sh/uv/getting-started/installation/)

### Claude for Desktop Integration

[Follow along with the setup instructions video](https://youtu.be/iJWJqyVuPS8)

1. Go to Claude > Settings > Developer > Edit Config > claude_desktop_config.json to include the following:

```json
{
    "mcpServers": {
        "AbletonMCP": {
            "command": "uvx",
            "args": [
                "ableton-mcp"
            ]
        }
    }
}
```

### Cursor Integration

Run ableton-mcp without installing it permanently through uvx. Go to Cursor Settings > MCP and paste this as a command:

```
uvx ableton-mcp
```

### Installing the Ableton Remote Script

[Follow along with the setup instructions video](https://youtu.be/iJWJqyVuPS8)

1. Download the `AbletonMCP_Remote_Script/__init__.py` file from this repo

2. Copy the folder to Ableton's MIDI Remote Scripts directory. Different OS and versions have different locations. **One of these should work, you might have to look**:

   **For macOS:**
   - Method 1: Go to Applications > Right-click on Ableton Live app → Show Package Contents → Navigate to:
     `Contents/App-Resources/MIDI Remote Scripts/`
   - Method 2: If it's not there in the first method, use the direct path (replace XX with your version number):
     `/Users/[Username]/Library/Preferences/Ableton/Live XX/User Remote Scripts`

   **For Windows:**
   - Method 1:
     C:\Users\[Username]\AppData\Roaming\Ableton\Live x.x.x\Preferences\User Remote Scripts
   - Method 2:
     `C:\ProgramData\Ableton\Live XX\Resources\MIDI Remote Scripts\`
   - Method 3:
     `C:\Program Files\Ableton\Live XX\Resources\MIDI Remote Scripts\`
   *Note: Replace XX with your Ableton version number (e.g., 10, 11, 12)*

3. Create a folder called 'AbletonMCP' in the Remote Scripts directory and paste the downloaded '\_\_init\_\_.py' file

4. Launch Ableton Live

5. Go to Settings/Preferences → Link, Tempo & MIDI

6. In the Control Surface dropdown, select "AbletonMCP"

7. Set Input and Output to "None"

### Installing Max for Live Devices (Optional)

The `Max4Live/` folder contains helper devices for advanced features:

#### AudioCapture.amxd
Required for the `audio_capture` MCP tool. Captures audio from Ableton for analysis.

1. Copy `Max4Live/AudioCapture.amxd` to your Ableton User Library:
   - macOS: `~/Music/Ableton/User Library/Presets/Audio Effects/Max Audio Effect/`
   - Windows: `C:\Users\[Username]\Documents\Ableton\User Library\Presets\Audio Effects\Max Audio Effect\`

2. In Ableton, drag the AudioCapture device onto your Master track (or any track you want to capture)

3. The device will automatically save captured audio to `/tmp/` when triggered by the MCP server

## Usage

### Starting the Connection

1. Ensure the Ableton Remote Script is loaded in Ableton Live
2. Make sure the MCP server is configured in Claude Desktop or Cursor
3. The connection should be established automatically when you interact with Claude

### Using with Claude

Once the config file has been set on Claude, and the remote script is running in Ableton, you will see a hammer icon with tools for the Ableton MCP.

## Capabilities

- Get session and track information
- Create and modify MIDI and audio tracks
- Create, edit, and trigger clips
- Control playback
- Load instruments and effects from Ableton's browser
- Add notes to MIDI clips
- Change tempo and other session parameters
- Analyze audio for BPM, beats, and chord progressions
- Convert vocals/audio to MIDI rhythm tracks
- Align audio timing to groove templates via warp markers

## Example Commands

Here are some examples of what you can ask Claude to do:

- "Create an 80s synthwave track" [Demo](https://youtu.be/VH9g66e42XA)
- "Create a Metro Boomin style hip-hop beat"
- "Create a new MIDI track with a synth bass instrument"
- "Add reverb to my drums"
- "Create a 4-bar MIDI clip with a simple melody"
- "Get information about the current Ableton session"
- "Load a 808 drum rack into the selected track"
- "Add a jazz chord progression to the clip in track 1"
- "Set the tempo to 120 BPM"
- "Play the clip in track 2"
- "Analyze the audio file for BPM and chords"
- "Convert the vocal track to a MIDI rhythm"
- "Align the vocal timing to match the drum groove"

## Advanced: Groove Alignment & Warp Markers

The groove alignment tools allow you to align vocals or other audio to a target drum groove. This is useful for mashups or tightening up loose performances.

### Workflow

1. **Create rhythm MIDI from vocals**: Use `vocal_to_midi` to detect transients in a vocal and create a MIDI drum pattern representing the rhythm

2. **Analyze alignment**: Use `groove_analyze` to compare the vocal rhythm to a target drum pattern

3. **Export warp markers**: Use `groove_export_warp_markers` to generate timing adjustments

4. **Inject into ALS file**: Use the ALS Warp Injector to apply warp markers directly to your Ableton project file

### ALS Warp Injector

The `als_warp_injector.py` tool injects warp markers directly into Ableton Live Set (.als) files:

```bash
# Basic usage
uv run python MCP_Server/als_warp_injector.py input.als warp_markers.json -o output.als

# With density control (markers per bar)
uv run python MCP_Server/als_warp_injector.py input.als warp_markers.json -o output.als -d 1

# With per-clip density (different density for different sections)
uv run python MCP_Server/als_warp_injector.py input.als warp_markers.json -o output.als \
  --density-map "104:1,137:1,161:2"

# With maximum offset limit (skip adjustments > 200ms to avoid distortion)
uv run python MCP_Server/als_warp_injector.py input.als warp_markers.json -o output.als \
  --density-map "104:1,137:1,161:2" --max-offset 200
```

**Parameters:**
- `-o, --output`: Output ALS file path
- `-t, --track`: Track name pattern to match (default: "Vocals")
- `-b, --bpm`: Project tempo in BPM
- `-d, --density`: Markers per bar (0=all, 1=1/bar, 2=2/bar, etc.)
- `--density-map`: Per-clip densities as "beat:density,beat:density"
- `--max-offset`: Maximum timing adjustment in ms (skip larger to avoid distortion)

## Troubleshooting

- **Connection issues**: Make sure the Ableton Remote Script is loaded, and the MCP server is configured on Claude
- **Timeout errors**: Try simplifying your requests or breaking them into smaller steps
- **Have you tried turning it off and on again?**: If you're still having connection errors, try restarting both Claude and Ableton Live
- **Remote Script not updating**: After modifying the Remote Script, you may need to fully restart Ableton (not just reload the script)
- **Audio capture not working**: Ensure the AudioCapture M4L device is loaded on a track and the `/tmp/` directory is writable

## Technical Details

### Communication Protocol

The system uses a simple JSON-based protocol over TCP sockets:

- Commands are sent as JSON objects with a `type` and optional `params`
- Responses are JSON objects with a `status` and `result` or `message`

### Audio Analysis APIs

- **ChordMini**: Used for BPM detection, beat tracking, and chord recognition (free, rate-limited)
- **Google Gemini**: Used for natural language audio description and analysis (requires `GOOGLE_API_KEY` environment variable)

### Limitations & Security Considerations

- Creating complex musical arrangements might need to be broken down into smaller steps
- The tool is designed to work with Ableton's default devices and browser items
- Always save your work before extensive experimentation
- The ALS Warp Injector modifies project files directly - always keep backups

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Disclaimer

This is a third-party integration and not made by Ableton.
