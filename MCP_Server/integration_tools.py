"""Focused tools; every command is explicitly registered and capability-gated."""
import json
from typing import Any
from mcp.server.fastmcp import Context
from mcp.server.fastmcp.exceptions import ToolError
from .telemetry_decorator import rich_telemetry_tool
from .dataset.trajectory_decorator import trajectory_tool

TOOL_DESCRIPTIONS = {
    "get_transport": (False, "Read transport and runtime-supported song settings. Unsupported properties return null with explanation. No version assumption."),
    "set_song_settings": (True, "Validated song settings: tempo (20..999), signature_numerator (1..99), signature_denominator (1,2,4,8,16), metronome/overdub/arrangement_overdub/scale_mode booleans, groove_amount (0..1.31), swing_amount (0..1), root_note (0..11). Every property is preflighted. Loop/warp and recording writes are excluded."),
    "jump_to_cue": (True, "Seek to an identified locator while stopped. params: cue_index,cue_id from get_locators. Refuses stale identities; verifies playhead after a tick."),
    "stop_all_clips": (True, "Request stopping all clips. Returns stop_requested, without claiming quantized stops have completed."),
    "get_tracks_overview": (False, "Compact bounded track summary preserving group-track arm safety. params: limit (1..128). Counts indicate truncation."),
    "check_arrangement_sync": (False, "Read-only bounded beat-grid/gap/overlap check across Arrangement clips. params: bar_beats (finite >0, max128). Yields between tracks; in_sync is null if inspection is incomplete. Never moves notes or clips."),
    "search_browser": (False, "Bounded yielding browser search. params: query, optional category, max_results (1..100), max_nodes (1..1500), max_depth (0..12), max_ms (10..5000). Returns truncation reason and unavailable categories; does not load or batch mutations."),
    "get_notes": (False, "Read bounded notes and stable note IDs from an explicitly addressed MIDI clip. params: track_index, location (session|arrangement), clip_index. Returns clip target_id for guarded edits. Requires extended host API."),
    "modify_notes": (True, "Modify notes in place by note_id, preserving extended metadata. params: track_index,target_id (track),location (session|arrangement),clip_index,clip_id and notes [{note_id, changed fields}]. All edits preflight before apply; stale IDs and unsupported hosts fail closed. Never replaces clips or envelopes."),
    "get_device_chain": (False, "Read bounded nested devices/parameters/rack chains and identities. params: track_index, track_type. Paths alternate device/chain indices; use returned IDs for writes."),
    "set_device_parameter_value": (True, "Guarded parameter write. params: track_index,track_type,target_id,device_path (list),device_id,parameter_index,parameter_id, and exactly one value or display_value (e.g. 1 kHz, 250 ms). Discovery/conversion never changes parameters; ambiguous display mappings fail."),
    "get_rack": (False, "Read a rack and bounded nested chains/parameters. params: track_index,track_type,device_path."),
    "set_rack_chain": (True, "Guarded rack chain controls. params: track_index,track_type,target_id,device_path,device_id,chain_index,chain_id and mute/solo booleans or volume/panning values."),
    "get_simpler": (False, "Read supported Simpler controls. params: track_index,track_type,device_path. Other device classes are rejected."),
    "edit_simpler": (True, "Guarded Simpler control edit. params: track_index,track_type,target_id,device_path,device_id and voices (1..32), retrigger (boolean), playback_mode (0..2). Sample replacement/warp editing is deferred."),
    "get_structure": (False, "Read bounded tracks/scenes with stable target IDs. params: limit (1..128). Read slot/clip identities using get_target_identity."),
    "edit_structure": (True, "Guarded structural edit. params.action: create_track/create_scene/duplicate_track/duplicate_scene/duplicate_clip/delete_track/delete_scene/delete_clip/rename_track/rename_scene/rename_clip. Track edits need track_index,target_id; scene edits scene_index,scene_id; clip edits also clip_index,clip_id. duplicate_clip also requires destination_index,destination_slot_id for an empty slot. Creation appends only; create_track accepts kind midi|audio, optional name and MIDI clip_length. Deletion is disabled by default. No arbitrary LOM properties."),
    "get_track_routing": (False, "Read current/available audio or MIDI routing names. params: track_index, track_type. Unsupported routes are reported explicitly."),
    "set_track_routing": (True, "Guarded routing edit. params: track_index, track_type, target_id, input_type/input_channel/output_type/output_channel (exact available names). Type and dependent channel changes require separate calls with an intervening read; unsafe compound requests fail before any write."),
    "get_mixer_state": (False, "Read one track/return/master mixer and its target_id. params: track_index (default 0), track_type (track|return|master). Pan and dB displays are separate; silence is JSON null plus silence=true."),
    "set_track_mixer": (True, "Guarded mixer edit. params: track_index, track_type, target_id from get_mixer_state; volume (parameter units) OR volume_db (number or 'silence'), panning, sends (index strings to values), mute/solo/arm booleans, optional exclusive_solo. Every field is preflighted; failures report rollback status."),
}


def register_tools(mcp, get_connection):
    def make_tool(command):
        async def tool(ctx: Context, params: dict[str, Any], user_prompt: str = "") -> str:
            from .script_handshake import require_capability
            # Ensure initial connection/handshake before checking advertised support.
            connection = get_connection()
            missing = require_capability(command)
            if missing:
                raise ToolError(missing)
            try:
                # Socket IO may wait for several host ticks; keep the event loop free.
                import asyncio
                result = await asyncio.to_thread(connection.send_command, command, params)
                return json.dumps(result, allow_nan=False)
            except Exception as error:
                raise ToolError(str(error)) from error
        return tool
    for command, (modifying, description) in TOOL_DESCRIPTIONS.items():
        tool = make_tool(command)
        tool.__name__ = command
        tool = trajectory_tool(command, modifying=modifying)(tool)
        tool = rich_telemetry_tool(command)(tool)
        mcp.tool(name=command, description=description)(tool)
