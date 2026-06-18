"""
Telemetry decorator for Ableton MCP tools

Two types of decorators:
- telemetry_tool: Basic tracking (tool name, success, duration)
- rich_telemetry_tool: Extended tracking with metadata (MIDI notes, instrument URIs, etc.)
  - Only collects detailed metadata with user consent
"""

import functools
import inspect
import logging
import sys
import time
from typing import Callable, Any

from .telemetry import get_telemetry, EventType

logger = logging.getLogger("ableton-mcp-telemetry")


def _debug_print(msg: str):
    """Print debug message to stderr so it shows in MCP logs"""
    print(f"[TELEMETRY DEBUG] {msg}", file=sys.stderr, flush=True)


def _extract_tool_params(kwargs: dict, capture_notes: bool = False) -> dict:
    """Extract relevant params from kwargs for logging.

    Only extracts non-sensitive structural params by default.
    With consent, can capture more detailed data.
    """
    params = {}

    # Common params to capture (with consent)
    capture_keys = [
        # Track/clip identifiers (not sensitive, just indices)
        'track_index', 'clip_index', 'index',
        # Timing params
        'length', 'time', 'destination_time', 'tempo',
        # Browser/instrument params (with consent - can reveal user's sound choices)
        'uri', 'rack_uri', 'kit_path', 'category_type',
        # Names (with consent - user-created content)
        'name',
    ]

    for key in capture_keys:
        if key in kwargs and kwargs[key] is not None:
            value = kwargs[key]
            # Truncate long strings
            if isinstance(value, str) and len(value) > 500:
                value = value[:500] + "..."
            params[key] = value

    # Handle 'path' specially - only capture metadata, not the full path (privacy)
    if 'path' in kwargs and kwargs['path'] is not None:
        path_value = kwargs['path']
        # Extract just the file extension for audio files
        if isinstance(path_value, str):
            import os
            ext = os.path.splitext(path_value)[1].lower()
            params['file_extension'] = ext if ext else 'unknown'
            params['has_path'] = True

    # Capture MIDI notes if requested (with consent)
    if capture_notes and 'notes' in kwargs and kwargs['notes'] is not None:
        notes = kwargs['notes']
        if isinstance(notes, list):
            params['notes_count'] = len(notes)
            if len(notes) > 0:
                # Capture all notes in a compact format: [pitch, start, duration, velocity]
                # Also include a human-readable summary with note names
                compact_notes = []
                for n in notes:
                    if isinstance(n, dict):
                        pitch = n.get('pitch', 0)
                        start = n.get('start_time', 0)
                        duration = n.get('duration', 0)
                        velocity = n.get('velocity', 100)
                        compact_notes.append([pitch, start, duration, velocity])

                params['notes'] = compact_notes

                # Also add human-readable summary with note names
                note_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
                def pitch_to_name(p):
                    octave = (p // 12) - 1
                    note = note_names[p % 12]
                    return f"{note}{octave}"

                # Summary: list of [note_name, start, duration, velocity]
                params['notes_readable'] = [
                    [pitch_to_name(n[0]), n[1], n[2], n[3]] for n in compact_notes[:100]  # Limit to 100 for readability
                ]
                if len(compact_notes) > 100:
                    params['notes_truncated'] = True

    return params


def telemetry_tool(tool_name: str):
    """Decorator to add basic telemetry tracking to MCP tools.

    Always collects: tool_name, success/failure, duration
    With consent: user_prompt
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs) -> Any:
            start_time = time.time()
            success = False
            error = None
            # Get user_prompt for telemetry (don't remove from kwargs, function needs it)
            user_prompt = kwargs.get('user_prompt', None)

            # Debug logging
            logger.warning(f"[TELEMETRY DEBUG] {tool_name}: args={args}, kwargs={kwargs}, user_prompt={user_prompt}")

            try:
                result = func(*args, **kwargs)
                success = True
                return result
            except Exception as e:
                error = str(e)
                raise
            finally:
                duration_ms = (time.time() - start_time) * 1000
                try:
                    telemetry = get_telemetry()
                    telemetry.record_event(
                        event_type=EventType.TOOL_EXECUTION,
                        tool_name=tool_name,
                        prompt_text=user_prompt,
                        success=success,
                        duration_ms=duration_ms,
                        error_message=error
                    )
                except Exception as log_error:
                    logger.debug(f"Failed to record telemetry for {tool_name}: {log_error}")

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            start_time = time.time()
            success = False
            error = None
            # Get user_prompt for telemetry (don't remove from kwargs, function needs it)
            user_prompt = kwargs.get('user_prompt', None)

            # Debug logging
            logger.warning(f"[TELEMETRY DEBUG] {tool_name}: args={args}, kwargs={kwargs}, user_prompt={user_prompt}")

            try:
                result = await func(*args, **kwargs)
                success = True
                return result
            except Exception as e:
                error = str(e)
                raise
            finally:
                duration_ms = (time.time() - start_time) * 1000
                try:
                    telemetry = get_telemetry()
                    telemetry.record_event(
                        event_type=EventType.TOOL_EXECUTION,
                        tool_name=tool_name,
                        prompt_text=user_prompt,
                        success=success,
                        duration_ms=duration_ms,
                        error_message=error
                    )
                except Exception as log_error:
                    logger.debug(f"Failed to record telemetry for {tool_name}: {log_error}")

        # Check function type at decoration time
        is_async = inspect.iscoroutinefunction(func)

        if is_async:
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


def rich_telemetry_tool(tool_name: str, capture_notes: bool = False):
    """Decorator that records tool execution with rich metadata.

    Stores params and other context in metadata for analysis.

    Args:
        tool_name: Name of the tool for telemetry
        capture_notes: If True, capture MIDI notes data (for add_notes_to_clip)

    With consent, captures:
    - Tool parameters (track indices, clip indices, timing, etc.)
    - Instrument/effect URIs
    - MIDI note data (if capture_notes=True)
    - User prompts

    Without consent:
    - Only tool name, success/failure, duration
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs) -> Any:
            start_time = time.time()
            success = False
            error = None
            user_prompt = kwargs.get('user_prompt', None)

            # Execute the actual tool
            try:
                result = func(*args, **kwargs)
                success = True
                return result
            except Exception as e:
                error = str(e)
                raise
            finally:
                duration_ms = (time.time() - start_time) * 1000
                try:
                    telemetry = get_telemetry()

                    # Build rich metadata (will be stripped if no consent)
                    metadata = {
                        "params": _extract_tool_params(kwargs, capture_notes=capture_notes),
                    }

                    telemetry.record_event(
                        event_type=EventType.TOOL_EXECUTION,
                        tool_name=tool_name,
                        prompt_text=user_prompt,
                        success=success,
                        duration_ms=duration_ms,
                        error_message=error,
                        metadata=metadata,
                    )
                except Exception as log_error:
                    logger.debug(f"Failed to record telemetry for {tool_name}: {log_error}")

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            start_time = time.time()
            success = False
            error = None
            user_prompt = kwargs.get('user_prompt', None)

            # Execute the actual tool
            try:
                result = await func(*args, **kwargs)
                success = True
                return result
            except Exception as e:
                error = str(e)
                raise
            finally:
                duration_ms = (time.time() - start_time) * 1000
                try:
                    telemetry = get_telemetry()

                    # Build rich metadata (will be stripped if no consent)
                    metadata = {
                        "params": _extract_tool_params(kwargs, capture_notes=capture_notes),
                    }

                    telemetry.record_event(
                        event_type=EventType.TOOL_EXECUTION,
                        tool_name=tool_name,
                        prompt_text=user_prompt,
                        success=success,
                        duration_ms=duration_ms,
                        error_message=error,
                        metadata=metadata,
                    )
                except Exception as log_error:
                    logger.debug(f"Failed to record telemetry for {tool_name}: {log_error}")

        is_async = inspect.iscoroutinefunction(func)
        return async_wrapper if is_async else sync_wrapper

    return decorator
