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
- **Scene Management**: Create, list, fire, and rename scenes
- **Advanced Device Control**: Get and set device parameters by name, delete devices, and find devices by name.
- **Automation**: Write automation curves for device parameters.
- **Max for Live Integration**: Modify `.amxd` files by changing default parameter values.
- **Arrangement View Control**: List and create locators, and set the song position.
- **Mixer Control**: List return tracks and set send levels.
- **User Feedback**: Display messages in the Ableton Live status bar.

## Project History

This project was created by Siddharth Ahuja and has been improved with the help of the community. The latest updates include a host of new features that significantly expand the capabilities of AbletonMCP, including:

- Enhanced browser navigation with recursive exploration.
- Scene management.
- Advanced device control.
- Automation writing.
- Max for Live integration.
- Arrangement View control.
- Mixer control.
- Audio track creation.
- User feedback messages.

## Installation

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

## Command List

### Session Control
- `get_session_info()`: Get detailed information about the current Ableton session.
  - **Example**: "Get the session info."
- `set_tempo(tempo: float)`: Set the tempo of the Ableton session.
  - **Example**: "Set the tempo to 120 BPM."
- `start_playback()`: Start playing the Ableton session.
  - **Example**: "Start playback."
- `stop_playback()`: Stop playing the Ableton session.
  - **Example**: "Stop playback."

### Track Control
- `get_track_info(track_index: int)`: Get detailed information about a specific track.
  - **Example**: "Get info for track 1."
- `create_midi_track(index: int = -1)`: Create a new MIDI track.
  - **Example**: "Create a new MIDI track."
- `create_audio_track(index: int = -1)`: Create a new audio track.
  - **Example**: "Create a new audio track."
- `set_track_name(track_index: int, name: str)`: Set the name of a track.
  - **Example**: "Rename track 1 to 'Drums'."

### Clip Control
- `create_clip(track_index: int, clip_index: int, length: float = 4.0)`: Create a new MIDI clip.
  - **Example**: "Create a 4-bar clip in track 1, slot 1."
- `add_notes_to_clip(track_index: int, clip_index: int, notes: List[Dict[str, Union[int, float, bool]]])`: Add MIDI notes to a clip.
  - **Example**: "Add a C4 note to the clip in track 1, slot 1."
- `set_clip_name(track_index: int, clip_index: int, name: str)`: Set the name of a clip.
  - **Example**: "Rename the clip in track 1, slot 1 to 'Intro'."
- `get_clip_info(track_index: int, clip_index: int)`: Get detailed information about a specific clip.
  - **Example**: "Get info for the clip in track 1, slot 1."
- `fire_clip(track_index: int, clip_index: int)`: Start playing a clip.
  - **Example**: "Play the clip in track 1, slot 1."
- `stop_clip(track_index: int, clip_index: int)`: Stop playing a clip.
  - **Example**: "Stop the clip in track 1, slot 1."

### Device Control
- `load_instrument_or_effect(track_index: int, uri: str)`: Load an instrument, effect, or audio file from the browser onto a track.
  - **Example**: "Load the 'Operator' synth on track 1."
- `get_device_parameters(track_index: int, device_index: int)`: Get a list of parameters for a specific device on a track.
  - **Example**: "Get the parameters for the first device on track 1."
- `get_device_details(track_index: int, device_index: int)`: Get detailed information about a specific device on a track.
  - **Example**: "Get details for the first device on track 1."
- `find_device_by_name(track_index: int, device_name: str)`: Find the index of a device on a track by its name.
  - **Example**: "Find the 'Operator' synth on track 1."
- `set_device_parameter(track_index: int, device_index: int, value: float, parameter_index: int = None, parameter_name: str = None)`: Set the value of a parameter for a specific device.
  - **Example**: "Set the 'Filter Freq' on the first device of track 1 to 800."
- `delete_device(track_index: int, device_index: int)`: Delete a device from a track.
  - **Example**: "Delete the first device from track 1."
- `write_automation(track_index: int, clip_index: int, device_index: int, points: List[Dict[str, float]], parameter_index: int = None, parameter_name: str = None)`: Write automation points for a device parameter within a clip.
  - **Example**: "Create a filter sweep automation on the first device of track 1."

### Scene Control
- `list_scenes()`: Get a list of all scenes in the Ableton session.
  - **Example**: "List all scenes."
- `fire_scene(scene_index: int)`: Fire a scene in the Ableton session.
  - **Example**: "Fire scene 1."
- `create_scene(scene_index: int = -1)`: Create a new scene in the Ableton session.
  - **Example**: "Create a new scene."
- `rename_scene(scene_index: int, name: str)`: Rename a scene in the Ableton session.
  - **Example**: "Rename scene 1 to 'Intro'."

### Browser Control
- `get_browser_tree(category_type: str = "all", max_depth: int = 2)`: Get a hierarchical tree of browser categories from Ableton.
  - **Example**: "Get the browser tree for instruments, up to 3 levels deep."
- `get_browser_items_at_path(path: str)`: Get browser items at a specific path in Ableton's browser.
  - **Example**: "Get the items in the 'Drums' category."
- `load_drum_kit(track_index: int, rack_uri: str, kit_path: str)`: Load a drum rack and then load a specific drum kit into it.
  - **Example**: "Load the '808 Core Kit' on track 1."

### Max for Live Control
- `modify_m4l_device_default(input_filepath: str, output_filepath: str, parameter_name: str, new_default_value: float)`: Creates a new Max for Live device file with a modified default value for a parameter.
  - **Example**: "Take the device 'MyReverb.amxd' and create a new version at 'MyReverb_Long.amxd' where the 'Decay' parameter defaults to 5.0"

### Arrangement View Control
- `list_locators()`: Get a list of all locators (cue points) in the Ableton session.
  - **Example**: "List all locators."
- `create_locator(time: float)`: Create a new locator (cue point) at a specific time in the arrangement.
  - **Example**: "Create a locator at beat 32."
- `set_song_position(time: float)`: Set the song's current playback time in the arrangement.
  - **Example**: "Set the song position to beat 16."

### Mixer Control
- `list_return_tracks()`: Get a list of all return tracks in the Ableton session.
  - **Example**: "List all return tracks."
- `set_send_level(track_index: int, send_index: int, level: float)`: Set the send level for a track.
  - **Example**: "Set the first send on track 1 to 0.5."

### User Feedback
- `show_message(message: str)`: Display a message in Ableton's status bar.
  - **Example**: "Show the message 'Hello from the AI!' in Ableton."

## Troubleshooting

- **Connection issues**: Make sure the Ableton Remote Script is loaded, and the MCP server is configured on Claude
- **Timeout errors**: Try simplifying your requests or breaking them into smaller steps
- **Have you tried turning it off and on again?**: If you're still having connection errors, try restarting both Claude and Ableton Live

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Disclaimer

This is a third-party integration and not made by Ableton.
