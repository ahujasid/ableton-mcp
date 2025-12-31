# AbletonMCP Extended - Ableton Live Model Context Protocol Integration

**76 tools for comprehensive Ableton Live control**

AbletonMCP Extended connects Ableton Live to Claude AI through the Model Context Protocol (MCP), allowing Claude to directly interact with and control Ableton Live. This extended version includes 76 tools for comprehensive music production, track creation, arrangement manipulation, and Live session control.

Based on the original [ableton-mcp](https://github.com/ahujasid/ableton-mcp) by Siddharth Ahuja, with 56 additional tools for professional workflows.

### Join the Community

Give feedback, get inspired, and build on top of the MCP: [Discord](https://discord.gg/3ZrMyGKnaU). Made by [Siddharth](https://x.com/sidahuj)

## Features

- **Two-way communication**: Connect Claude AI to Ableton Live through a socket-based server
- **Track manipulation**: Create, modify, and manipulate MIDI and audio tracks
- **Instrument and effect selection**: Claude can access and load the right instruments, effects and sounds from Ableton's library
- **Clip creation**: Create and edit MIDI clips with notes
- **Session control**: Start and stop playback, fire clips, and control transport
- **Arrangement recording**: Arm tracks and record into arrangement view with overdub support
- **Audio sample loading**: Load audio files and samples into clip slots from Ableton's browser
- **Audio warping**: Control warp modes, enable/disable warping, and manipulate audio time-stretching
- **Audio clip manipulation**: Crop and reverse audio clips for creative sound design
- **Audio analysis**: Comprehensive analysis including BPM detection, transient detection, frequency content, and waveform descriptions
- **Audio-to-MIDI transcription**: Analyze audio files and transcribe them to MIDI with tempo, key, and note detection (powered by audio2llm)
- **Track freezing and export**: Freeze tracks to render audio, enabling CPU-efficient playback and audio extraction workflows

## Components

The system consists of two main components:

1. **Ableton Remote Script** (`Ableton_Remote_Script/__init__.py`): A MIDI Remote Script for Ableton Live that creates a socket server to receive and execute commands
2. **MCP Server** (`server.py`): A Python server that implements the Model Context Protocol and connects to the Ableton Remote Script

## Installation

### Quick Install

Install via pip/uvx:

```bash
uvx ableton-mcp-extended
```

### Optional: Enhanced Audio-to-MIDI Transcription

For **significantly better polyphonic audio transcription** (detecting chords, multiple instruments simultaneously), install `basic-pitch`:

```bash
pip install basic-pitch
```

**Why install this?**
- **Without basic-pitch**: Monophonic transcription (one note at a time) - works for simple melodies
- **With basic-pitch**: Polyphonic transcription (multiple simultaneous notes) - works for chords, complex arrangements, and full mixes

The `analyze_audio_file` tool will automatically use the best available transcription method. Basic Pitch provides professional-grade transcription powered by Spotify's ML model.

**Workflow with audio2llm:**
1. Provide Claude with any WAV/MP3 audio file path
2. Claude analyzes it and extracts: tempo, key, and musical notes
3. Claude can recreate the audio as MIDI in Ableton or generate complementary parts
4. Perfect for sampling, remixing, or learning from reference tracks

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
                "ableton-mcp-extended"
            ]
        }
    }
}
```

### Cursor Integration

Run ableton-mcp-extended without installing it permanently through uvx. Go to Cursor Settings > MCP and paste this as a command:

```
uvx ableton-mcp-extended
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
- **Set send levels** for routing to reverb/delay return tracks

### Clip Operations
- Create, edit, and trigger clips
- **Delete clips** from clip slots
- Set clip colors
- Duplicate clips across tracks and slots
- Add and manipulate MIDI notes
- **Read MIDI notes from clips** (pitch, timing, velocity, duration)
- Quantize MIDI clips to a grid
- Transpose MIDI clips
- Control clip loop settings (loop start, end, start/end markers)
- **Apply groove/swing** to MIDI clips for human feel
- **Capture recently played MIDI** into clips (Live 11+)

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
- **Copy clips from session view to arrangement timeline**
- **Inspect arrangement clips** - see what's placed on the timeline for each track
- **Delete time sections** - remove a section of the arrangement and shift everything left
- **Duplicate time sections** - copy a section and paste it immediately after
- **Insert silence** - push everything to the right to create empty space
- **Create locators/markers** - mark important sections (verse, chorus, etc.)
- **Create automation lanes** for volume, pan, sends, and device parameters
- **Clear automation** in specific time ranges

### Devices & Effects
- Load instruments and effects from Ableton's browser
- Get all parameters for any device
- Set device parameter values
- Control device chains
- **Get and set macro controls** on rack devices (all 8 macros)

### Audio Clip Operations
- Load audio samples from Ableton's browser into clip slots
- Get detailed information about audio clips (warp settings, loop points, etc.)
- Set warp mode (Beats, Tones, Texture, Re-Pitch, Complex, Complex Pro)
- Enable/disable warping for audio clips
- Crop audio clips to loop boundaries
- Reverse audio clip samples for creative effects

### Audio Analysis
- Comprehensive audio clip analysis with detailed characteristics
- BPM and tempo detection from warped clips
- Transient detection using warp markers (identifies hit positions)
- Transient density analysis (distinguishes drums from sustained sounds)
- Audio file properties (sample rate, bit depth, duration, channels)
- Frequency content analysis based on warp mode and clip properties
- Waveform envelope description (gain, fades, loop characteristics)
- Pitch and key information when available

### Session Control
- Change tempo and time signature
- **Tap tempo** to set BPM by rhythm
- **Enable/disable metronome** for recording
- Load sounds and instruments from browser
- Control transport

## Example Commands

Here are some examples of what you can ask Claude to do:

### Music Production
- "Create an 80s synthwave track" [Demo](https://youtu.be/VH9g66e42XA)
- "Create a Metro Boomin style hip-hop beat"
- "Create a new MIDI track with a synth bass instrument"
- "Add a jazz chord progression to the clip in track 1"

### Recording & Arrangement
- "Turn on the metronome"
- "Enable metronome for recording"
- "Tap tempo" (call multiple times to set tempo by rhythm)
- "Arm track 0 for recording"
- "Start recording in arrangement view"
- "Enable overdub mode and start recording"
- "Show me which tracks are armed for recording"
- "Set the loop to start at beat 4 and end at beat 8"
- "Jump to the 16 beat mark"
- "Copy the clip from track 1, slot 0 to arrangement at beat 8"
- "Place this session clip at bar 16 in the arrangement"
- "Show me what clips are in the arrangement on track 0"
- "Delete the section from beat 8 to beat 16 in the arrangement"
- "Duplicate the 8-bar section from beat 0 to 8"
- "Insert 4 bars of silence at beat 16"
- "Create a locator at beat 32 called 'Chorus'"
- "Mark the verse section at beat 8"

### Scene Management
- "Create a new scene called 'Chorus' at index 2"
- "Duplicate scene 0"
- "Trigger scene 1"
- "Delete scene 3"

### Clip Operations
- "Quantize the clip in track 0, slot 0 to 16th notes"
- "Transpose the clip in track 1 up by 5 semitones"
- "Duplicate the clip from track 0, slot 0 to track 1, slot 1"
- "Delete the clip in track 2, slot 3"
- "Set the clip at track 0, slot 0 to red (color index 5)"
- "Read the MIDI notes from the clip at track 1, slot 0"
- "Show me all the notes in track 2, clip 1"
- "Set the loop points for track 0, clip 0 to start at 0 and end at 4 beats"
- "Apply groove to the clip at track 0, slot 0 with 80% swing"
- "Add swing to my drum pattern in track 1"
- "Capture the MIDI I just played into track 0, slot 1"

### Track Mixing
- "Set track 0 volume to 0.7"
- "Pan track 1 hard left"
- "Mute tracks 2 and 3"
- "Solo track 0"
- "Set track 0 to blue (color index 45)"
- "Set send A on track 1 to 0.5"
- "Route track 2 to reverb at 70%"
- "Increase the delay send on track 0 to 0.8"

### Device Control
- "Show me all parameters for the first device on track 0"
- "Set parameter 3 of device 0 on track 0 to 0.8"
- "Get the macro values for the rack on track 1"
- "Set macro 1 on the drum rack to 0.75"
- "Adjust the filter cutoff macro to 0.5"
- "Add reverb to my drums"
- "Load a 808 drum rack into the selected track"

### Audio Clip Manipulation
- "Load an audio sample from the browser into track 0, slot 0"
- "Get info about the audio clip in track 1, slot 2"
- "Set the warp mode to Complex Pro for the clip at track 0, slot 0"
- "Enable warping for the audio clip in track 1, slot 0"
- "Disable warping for track 2, clip 3"
- "Crop the audio clip at track 0, slot 1 to its loop boundaries"
- "Reverse the audio sample in track 1, slot 0"

### Audio Analysis
- "Analyze the audio clip in track 0, slot 0"
- "Tell me about the frequency content of the clip at track 1, slot 2"
- "Describe the transients in the audio clip on track 2, slot 0"
- "What's the BPM and rhythm characteristics of track 0, clip 1?"
- "Give me a comprehensive analysis of the drum loop in track 3, slot 0"
- "Analyze the waveform and audio properties of track 1, clip 0"

### Automation
- "Create a volume fade from 0 to 1 over 8 beats on track 0"
- "Automate the pan from left to right on track 2"
- "Add a filter sweep automation on device 0 parameter 3"
- "Create a reverb send build from beat 4 to beat 8"
- "Clear all automation on track 1"
- "Automate the volume to drop at beat 16"

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
