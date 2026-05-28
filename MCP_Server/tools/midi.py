"""MIDI tools: get notes from clip, clip_to_grid, grid_to_clip."""

import json
import logging
from typing import Any, Callable

from mcp.server.fastmcp import Context

logger = logging.getLogger("AbletonMCPServer")


def register(mcp: Any, get_ableton_connection: Callable[[], Any]) -> None:
    @mcp.tool()
    def get_notes_from_clip(ctx: Context, track_index: int, clip_index: int) -> str:
        """Read all MIDI notes from a clip (pitch, timing, duration, velocity). Parameters: track_index, clip_index."""
        try:
            ableton = get_ableton_connection()
            result = ableton.send_command("get_notes_from_clip", {
                "track_index": track_index,
                "clip_index": clip_index,
            })
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error getting notes from clip: {str(e)}")
            return f"Error getting notes from clip: {str(e)}"

    @mcp.tool()
    def clip_to_grid(ctx: Context, track_index: int, clip_index: int) -> str:
        """Read a MIDI clip and display as ASCII grid notation (drum or melodic). Parameters: track_index, clip_index."""
        try:
            from MCP_Server.grid_notation import notes_to_grid
            ableton = get_ableton_connection()
            result = ableton.send_command("get_notes_from_clip", {
                "track_index": track_index,
                "clip_index": clip_index,
            })
            notes = result.get("notes", [])
            clip_length = result.get("clip_length", 4.0)
            clip_name = result.get("clip_name", "Unknown")
            grid = notes_to_grid(notes, clip_length)
            return f"Clip: {clip_name} ({clip_length} beats)\n\n{grid}"
        except ImportError:
            return "Error: grid_notation module not available"
        except Exception as e:
            logger.error(f"Error converting clip to grid: {str(e)}")
            return f"Error converting clip to grid: {str(e)}"

    @mcp.tool()
    def grid_to_clip(
        ctx: Context,
        track_index: int,
        clip_index: int,
        grid: str,
        length: float = 4.0,
    ) -> str:
        """Write ASCII grid notation to a MIDI clip. Parameters: track_index, clip_index, grid (ASCII grid string), length (beats, default 4.0)."""
        try:
            from MCP_Server.grid_notation import parse_grid
            notes = parse_grid(grid)
            ableton = get_ableton_connection()
            try:
                ableton.send_command("create_clip", {
                    "track_index": track_index,
                    "clip_index": clip_index,
                    "length": length,
                })
            except Exception:
                pass
            ableton.send_command("add_notes_to_clip", {
                "track_index": track_index,
                "clip_index": clip_index,
                "notes": notes,
            })
            return f"Wrote {len(notes)} notes from grid to track {track_index}, slot {clip_index}"
        except ImportError:
            return "Error: grid_notation module not available"
        except Exception as e:
            logger.error(f"Error writing grid to clip: {str(e)}")
            return f"Error writing grid to clip: {str(e)}"

    @mcp.tool()
    def parse_grid_preview(
        ctx: Context,
        grid: str,
        is_drums: bool = None,
        steps_per_beat: int = 4,
    ) -> str:
        """Preview parsed note events from ASCII grid without writing to Ableton."""
        try:
            from MCP_Server.grid_notation import parse_grid

            notes = parse_grid(grid, is_drums=is_drums, steps_per_beat=steps_per_beat)
            preview = {
                "note_count": len(notes),
                "steps_per_beat": steps_per_beat,
                "is_drums": is_drums,
                "notes_preview": notes[:32],
            }
            if notes:
                end_time = max(
                    n.get("start_time", 0.0) + n.get("duration", 0.0) for n in notes
                )
                preview["estimated_length_beats"] = end_time
            return json.dumps(preview, indent=2)
        except ImportError:
            return "Error: grid_notation module not available"
        except Exception as e:
            logger.error(f"Error parsing grid preview: {str(e)}")
            return f"Error parsing grid preview: {str(e)}"
