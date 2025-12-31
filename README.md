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
- **Arrangement recording**: Arm tracks and record into arrangement view with overdub support

## Components

The system consists of two main components:

1. **Ableton Remote Script** (`Ableton_Remote_Script/__init__.py`): A MIDI Remote Script for Ableton Live that creates a socket server to receive and execute commands
2. **MCP Server** (`server.py`): A Python server that implements the Model Context Protocol and connects to the Ableton Remote Script

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

Otherwise, install from [uv's official website][https://docs.astral.sh/uv/getting-started/installation/]

⚠️ Do not proceed before installing UV

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

⚠️ Only run one instance of the MCP server (either on Cursor or Claude Desktop), not both

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

4. Create a folder called 'AbletonMCP' in the Remote Scripts directory and paste the downloaded '\_\_init\_\_.py' file

3. Launch Ableton Live

4. Go to Settings/Preferences → Link, Tempo & MIDI

5. In the Control Surface dropdown, select "AbletonMCP"

6. Set Input and Output to "None"

## Usage

### Starting the Connection

1. Ensure the Ableton Remote Script is loaded in Ableton Live
2. Make sure the MCP server is configured in Claude Desktop or Cursor
3. The connection should be established automatically when you interact with Claude

### Using with Claude

Once the config file has been set on Claude, and the remote script is running in Ableton, you will see a hammer icon with tools for the Ableton MCP.

## Capabilities

### Session & Track Management
- Get session and track information
- Create and modify MIDI and audio tracks
- Group tracks together
- Set track colors for organization
- Control track volume, pan, mute, and solo

### Clip Operations
- Create, edit, and trigger clips
- Set clip colors
- Duplicate clips across tracks and slots
- Add and manipulate MIDI notes
- Quantize MIDI clips to a grid
- Transpose MIDI clips
- Control clip loop settings

### Scene Management
- Create, delete, and duplicate scenes
- Trigger/fire scenes
- Rename scenes

### Playback & Recording
- Control playback (start/stop/jump to position)
- Arm/disarm tracks for recording
- Start and stop arrangement recording
- Enable/disable arrangement overdub mode
- Get recording status and armed tracks information

### Arrangement Navigation
- Set loop start, end, and length
- Jump to specific positions in the arrangement
- Get current loop and playback information

### Devices & Effects
- Load instruments and effects from Ableton's browser
- Get all parameters for any device
- Set device parameter values
- Control device chains

### Session Control
- Change tempo and time signature
- Load sounds and instruments from browser
- Control transport and metronome

## Example Commands

Here are some examples of what you can ask Claude to do:

### Music Production
- "Create an 80s synthwave track" [Demo](https://youtu.be/VH9g66e42XA)
- "Create a Metro Boomin style hip-hop beat"
- "Create a new MIDI track with a synth bass instrument"
- "Add a jazz chord progression to the clip in track 1"

### Recording & Arrangement
- "Arm track 0 for recording"
- "Start recording in arrangement view"
- "Enable overdub mode and start recording"
- "Show me which tracks are armed for recording"
- "Set the loop to start at beat 4 and end at beat 8"
- "Jump to the 16 beat mark"

### Scene Management
- "Create a new scene called 'Chorus' at index 2"
- "Duplicate scene 0"
- "Trigger scene 1"
- "Delete scene 3"

### Clip Operations
- "Quantize the clip in track 0, slot 0 to 16th notes"
- "Transpose the clip in track 1 up by 5 semitones"
- "Duplicate the clip from track 0, slot 0 to track 1, slot 1"
- "Set the clip at track 0, slot 0 to red (color index 5)"

### Track Mixing
- "Set track 0 volume to 0.7"
- "Pan track 1 hard left"
- "Mute tracks 2 and 3"
- "Solo track 0"
- "Set track 0 to blue (color index 45)"

### Device Control
- "Show me all parameters for the first device on track 0"
- "Set parameter 3 of device 0 on track 0 to 0.8"
- "Add reverb to my drums"
- "Load a 808 drum rack into the selected track"

### Session Control
- "Set the tempo to 120 BPM"
- "Get information about the current Ableton session"
- "Create 4 MIDI tracks and group them together"


## Troubleshooting

- **Connection issues**: Make sure the Ableton Remote Script is loaded, and the MCP server is configured on Claude
- **Timeout errors**: Try simplifying your requests or breaking them into smaller steps
- **Have you tried turning it off and on again?**: If you're still having connection errors, try restarting both Claude and Ableton Live

## Technical Details

### Communication Protocol

The system uses a simple JSON-based protocol over TCP sockets:

- Commands are sent as JSON objects with a `type` and optional `params`
- Responses are JSON objects with a `status` and `result` or `message`

### Limitations & Security Considerations

- Creating complex musical arrangements might need to be broken down into smaller steps
- The tool is designed to work with Ableton's default devices and browser items
- Always save your work before extensive experimentation

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Disclaimer

This is a third-party integration and not made by Ableton.
