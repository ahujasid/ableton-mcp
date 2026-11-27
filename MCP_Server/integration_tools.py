"""Focused tools; every command is explicitly registered and capability-gated."""
import json
from typing import Any
from mcp.server.fastmcp import Context
from mcp.server.fastmcp.exceptions import ToolError
from .telemetry_decorator import rich_telemetry_tool
from .dataset.trajectory_decorator import trajectory_tool

TOOL_DESCRIPTIONS = {
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
