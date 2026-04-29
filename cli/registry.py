"""Tool registry: single source of truth for all Ableton CLI/MCP tools."""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field


@dataclass
class Param:
    type: str  # "int", "float", "str", "bool", "json"
    required: bool = True
    default: Any = None
    help: str = ""


@dataclass
class Tool:
    name: str
    command: str  # Ableton Remote Script command name
    group: str
    description: str
    params: Dict[str, Param] = field(default_factory=dict)
    returns_json: bool = False  # True if result should be displayed as JSON


def _build_registry() -> Dict[str, Tool]:
    tools: List[Tool] = []

    # ── Session ──────────────────────────────────────────────────────────
    tools += [
        Tool("get_session_info", "get_session_info", "session",
             "Get detailed information about the current Ableton session",
             returns_json=True),
        Tool("set_tempo", "set_tempo", "session",
             "Set the tempo of the Ableton session",
             params={"tempo": Param("float", help="BPM value")}),
        Tool("start_playback", "start_playback", "session",
             "Start playing the Ableton session"),
        Tool("stop_playback", "stop_playback", "session",
             "Stop playing the Ableton session"),
    ]

    # ── Tracks ───────────────────────────────────────────────────────────
    tools += [
        Tool("get_track_info", "get_track_info", "tracks",
             "Get detailed information about a specific track",
             params={"track_index": Param("int", help="Track index")},
             returns_json=True),
        Tool("get_all_tracks_info", "get_all_tracks_info", "tracks",
             "Get summary info for all tracks at once",
             returns_json=True),
        Tool("get_return_tracks_info", "get_return_tracks_info", "tracks",
             "Get info for all return tracks",
             returns_json=True),
        Tool("create_midi_track", "create_midi_track", "tracks",
             "Create a new MIDI track",
             params={"index": Param("int", required=False, default=-1,
                                    help="Track index (-1 = end of list)")}),
        Tool("create_audio_track", "create_audio_track", "tracks",
             "Create a new audio track",
             params={"index": Param("int", required=False, default=-1,
                                    help="Track index (-1 = end of list)")}),
        Tool("create_return_track", "create_return_track", "tracks",
             "Create a new return track (for sends like reverb/delay)"),
        Tool("set_track_name", "set_track_name", "tracks",
             "Set the name of a track",
             params={
                 "track_index": Param("int", help="Track index"),
                 "name": Param("str", help="New track name"),
             }),
        Tool("delete_track", "delete_track", "tracks",
             "Delete a track at the specified index",
             params={"track_index": Param("int", help="Track index")}),
        Tool("set_track_color", "set_track_color", "tracks",
             "Set track color",
             params={
                 "track_index": Param("int", help="Track index"),
                 "color_index": Param("int", help="Color index (0-69)"),
             }),
        Tool("arm_track", "arm_track", "tracks",
             "Arm a track for recording",
             params={"track_index": Param("int", help="Track index")}),
        Tool("set_track_arm", "set_track_arm", "tracks",
             "Set the arm state of a track",
             params={
                 "track_index": Param("int", help="Track index"),
                 "arm": Param("bool", help="Arm state (true/false)"),
             }),
    ]

    # ── Clips ────────────────────────────────────────────────────────────
    tools += [
        Tool("create_clip", "create_clip", "clips",
             "Create a new MIDI clip",
             params={
                 "track_index": Param("int", help="Track index"),
                 "clip_index": Param("int", help="Clip slot index"),
                 "length": Param("float", required=False, default=4.0,
                                 help="Length in beats (default 4.0)"),
             }),
        Tool("add_notes_to_clip", "add_notes_to_clip", "clips",
             "Add MIDI notes to a clip",
             params={
                 "track_index": Param("int", help="Track index"),
                 "clip_index": Param("int", help="Clip slot index"),
                 "notes": Param("json", help="JSON array of {pitch, start_time, duration, velocity, mute}"),
             }),
        Tool("set_clip_name", "set_clip_name", "clips",
             "Set the name of a clip",
             params={
                 "track_index": Param("int", help="Track index"),
                 "clip_index": Param("int", help="Clip slot index"),
                 "name": Param("str", help="New clip name"),
             }),
        Tool("fire_clip", "fire_clip", "clips",
             "Start playing a clip",
             params={
                 "track_index": Param("int", help="Track index"),
                 "clip_index": Param("int", help="Clip slot index"),
             }),
        Tool("stop_clip", "stop_clip", "clips",
             "Stop playing a clip",
             params={
                 "track_index": Param("int", help="Track index"),
                 "clip_index": Param("int", help="Clip slot index"),
             }),
        Tool("delete_clip", "delete_clip", "clips",
             "Delete a clip from a clip slot",
             params={
                 "track_index": Param("int", help="Track index"),
                 "clip_index": Param("int", help="Clip slot index"),
             }),
        Tool("get_clip_notes", "get_clip_notes", "clips",
             "Read all MIDI notes from a clip",
             params={
                 "track_index": Param("int", help="Track index"),
                 "clip_index": Param("int", help="Clip slot index"),
             },
             returns_json=True),
    ]

    # ── Mixer ────────────────────────────────────────────────────────────
    tools += [
        Tool("set_track_volume", "set_track_volume", "mixer",
             "Set track volume (0.0=-inf dB, 0.85=0dB, 1.0=+6dB)",
             params={
                 "track_index": Param("int", help="Track index"),
                 "volume": Param("float", help="Volume (0.0-1.0)"),
             }),
        Tool("set_track_pan", "set_track_pan", "mixer",
             "Set track pan (-1.0=left, 0.0=center, 1.0=right)",
             params={
                 "track_index": Param("int", help="Track index"),
                 "pan": Param("float", help="Pan (-1.0 to 1.0)"),
             }),
        Tool("set_track_mute", "set_track_mute", "mixer",
             "Set track mute state",
             params={
                 "track_index": Param("int", help="Track index"),
                 "mute": Param("bool", help="Mute state (true/false)"),
             }),
        Tool("set_track_solo", "set_track_solo", "mixer",
             "Set track solo state",
             params={
                 "track_index": Param("int", help="Track index"),
                 "solo": Param("bool", help="Solo state (true/false)"),
             }),
        Tool("set_track_send", "set_track_send", "mixer",
             "Set track send level",
             params={
                 "track_index": Param("int", help="Track index"),
                 "send_index": Param("int", help="Send index (0=A, 1=B, ...)"),
                 "value": Param("float", help="Send level (0.0-1.0)"),
             }),
    ]

    # ── Devices ──────────────────────────────────────────────────────────
    tools += [
        Tool("get_device_parameters", "get_device_parameters", "devices",
             "Get all parameters for a device",
             params={
                 "track_index": Param("int", help="Track index"),
                 "device_index": Param("int", help="Device index"),
                 "track_type": Param("str", required=False, default="track",
                                     help="Track type: track|return|master"),
             },
             returns_json=True),
        Tool("set_device_parameter", "set_device_parameter", "devices",
             "Set a device parameter value",
             params={
                 "track_index": Param("int", help="Track index"),
                 "device_index": Param("int", help="Device index"),
                 "parameter_index": Param("int", help="Parameter index"),
                 "value": Param("float", help="Value (0.0-1.0)"),
                 "track_type": Param("str", required=False, default="track",
                                     help="Track type: track|return|master"),
             }),
    ]

    # ── Browser ──────────────────────────────────────────────────────────
    tools += [
        Tool("get_browser_tree", "get_browser_tree", "browser",
             "Get a hierarchical tree of browser categories",
             params={
                 "category_type": Param("str", required=False, default="all",
                                        help="Category: all|instruments|sounds|drums|audio_effects|midi_effects"),
             },
             returns_json=True),
        Tool("get_browser_items_at_path", "get_browser_items_at_path", "browser",
             "Get browser items at a specific path",
             params={
                 "path": Param("str", help="Browser path (e.g. 'instruments/synths/bass')"),
             },
             returns_json=True),
        Tool("load_instrument_or_effect", "load_browser_item", "browser",
             "Load an instrument or effect onto a track by URI",
             params={
                 "track_index": Param("int", help="Track index"),
                 "item_uri": Param("str", help="Browser item URI"),
             }),
    ]

    # ── Scenes ───────────────────────────────────────────────────────────
    tools += [
        Tool("create_scene", "create_scene", "scenes",
             "Create a new scene",
             params={
                 "index": Param("int", required=False, default=-1,
                                help="Scene index (-1 = end)"),
                 "name": Param("str", required=False, default="",
                               help="Scene name"),
             }),
        Tool("trigger_scene", "trigger_scene", "scenes",
             "Trigger/fire a scene",
             params={
                 "scene_index": Param("int", help="Scene index"),
             }),
        Tool("set_scene_name", "set_scene_name", "scenes",
             "Set the name of a scene",
             params={
                 "scene_index": Param("int", help="Scene index"),
                 "name": Param("str", help="New scene name"),
             }),
    ]

    # ── Arrangement ──────────────────────────────────────────────────────
    tools += [
        Tool("create_locator", "create_locator", "arrangement",
             "Create a locator/marker at a position",
             params={
                 "position": Param("float", help="Position in beats"),
                 "name": Param("str", required=False, default="",
                               help="Locator name"),
             }),
        Tool("copy_clip_to_arrangement", "copy_clip_to_arrangement", "arrangement",
             "Copy a session clip to arrangement at a given time",
             params={
                 "track_index": Param("int", help="Track index"),
                 "clip_index": Param("int", help="Clip slot index"),
                 "arrangement_time": Param("float", help="Arrangement position in beats"),
             }),
        Tool("get_arrangement_clips", "get_arrangement_clips", "arrangement",
             "Get all clips in arrangement view for a track",
             params={
                 "track_index": Param("int", help="Track index"),
             },
             returns_json=True),
        Tool("create_automation", "create_automation", "arrangement",
             "Create automation for a parameter",
             params={
                 "track_index": Param("int", help="Track index"),
                 "parameter_name": Param("str", help="Parameter name (e.g. Volume, Pan)"),
                 "automation_points": Param("json",
                                            help='JSON array: [{"time": 0, "value": 0.5}, ...]'),
             }),
    ]

    # ── Audio ────────────────────────────────────────────────────────────
    tools += [
        Tool("load_audio_sample", "load_audio_sample", "audio",
             "Load an audio sample into a clip slot",
             params={
                 "track_index": Param("int", help="Track index"),
                 "clip_index": Param("int", help="Clip slot index"),
                 "file_path": Param("str", required=False, default="",
                                    help="File path to audio sample"),
                 "browser_uri": Param("str", required=False, default="",
                                      help="Browser URI (preferred)"),
             }),
    ]

    # ── MIDI ─────────────────────────────────────────────────────────────
    tools += [
        Tool("get_notes_from_clip", "get_notes_from_clip", "midi",
             "Read all MIDI notes from a clip (pitch, timing, duration, velocity)",
             params={
                 "track_index": Param("int", help="Track index"),
                 "clip_index": Param("int", help="Clip slot index"),
             },
             returns_json=True),
        Tool("clip_to_grid", "get_notes_from_clip", "midi",
             "Read a MIDI clip and display as ASCII grid notation",
             params={
                 "track_index": Param("int", help="Track index"),
                 "clip_index": Param("int", help="Clip slot index"),
             }),
        Tool("grid_to_clip", "grid_to_clip", "midi",
             "Write ASCII grid notation to a MIDI clip",
             params={
                 "track_index": Param("int", help="Track index"),
                 "clip_index": Param("int", help="Clip slot index"),
                 "grid": Param("str", help="ASCII grid notation string"),
                 "length": Param("float", required=False, default=4.0,
                                 help="Clip length in beats (default 4.0)"),
             }),
    ]

    return {t.name: t for t in tools}


REGISTRY: Dict[str, Tool] = _build_registry()


def get_tool(name: str) -> Optional[Tool]:
    return REGISTRY.get(name)


def get_tools_by_group(group: str) -> List[Tool]:
    return [t for t in REGISTRY.values() if t.group == group]


def get_all_groups() -> List[str]:
    seen = []
    for t in REGISTRY.values():
        if t.group not in seen:
            seen.append(t.group)
    return seen


def search_tools(pattern: str) -> List[Tool]:
    """Search tools by name or description (case-insensitive substring match)."""
    pattern = pattern.lower()
    return [
        t for t in REGISTRY.values()
        if pattern in t.name.lower() or pattern in t.description.lower()
    ]
