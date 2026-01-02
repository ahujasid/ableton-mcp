"""
Decorators for Ableton MCP tool functions.

This module provides decorators that eliminate boilerplate in tool functions:
- Connection handling
- Error handling and logging
- Result formatting

Usage examples:

    # Simple command passthrough - returns JSON result
    @mcp.tool()
    @ableton_tool("get_session_info")
    async def get_session_info(ctx: Context) -> str:
        pass

    # Command with parameters - returns JSON result
    @mcp.tool()
    @ableton_tool("get_track_info")
    async def get_track_info(ctx: Context, track_index: int) -> str:
        pass

    # Command with custom result formatter
    @mcp.tool()
    @ableton_tool("create_midi_track", format_result=lambda r: f"Created: {r.get('name')}")
    async def create_midi_track(ctx: Context, index: int = -1) -> str:
        pass

    # Custom logic - receives ableton connection
    @mcp.tool()
    @ableton_tool()
    async def custom_tool(ctx: Context, ableton: AbletonConnection, param: int) -> str:
        result = await ableton.send_command_async("some_command", {"param": param})
        # Custom logic here
        return "Custom result"
"""

import json
import logging
from collections.abc import Callable
from functools import wraps
from typing import Any

logger = logging.getLogger("AbletonMCPServer")


def ableton_tool(
    command_type: str | None = None,
    format_result: Callable[[dict[str, Any]], str] | None = None,
    error_prefix: str | None = None,
):
    """
    Decorator for Ableton MCP tool functions.

    Handles connection management, error handling, and result formatting.

    Args:
        command_type: If provided, automatically calls this command with function kwargs.
                     If None, the function is called directly (for custom logic).
        format_result: Optional function to format the result dict into a string.
                      If None and command_type is set, returns JSON.
                      Ignored if command_type is None.
        error_prefix: Custom error message prefix. Defaults to "Error in {func_name}".

    The decorated function signature depends on command_type:
    - If command_type is set: function is not called (can be empty `pass`)
    - If command_type is None: function is called directly (use get_ableton_connection() inside)
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> str:
            # Import inside wrapper to pick up test patches
            from MCP_Server import server

            # Build error message prefix
            func_name = func.__name__
            err_prefix = error_prefix or f"Error in {func_name}"

            try:
                if command_type is not None:
                    ableton = server.get_ableton_connection()
                    # Auto-execute command with remaining kwargs as params
                    # Filter out 'ctx' from kwargs for the command params
                    params = {k: v for k, v in kwargs.items() if k != "ctx"}

                    # Only pass params if non-empty
                    if params:
                        result = await ableton.send_command_async(command_type, params)
                    else:
                        result = await ableton.send_command_async(command_type)

                    # Format result
                    if format_result is not None:
                        return format_result(result)
                    else:
                        return json.dumps(result, indent=2)
                else:
                    # Custom logic - call function directly
                    # Function should call get_ableton_connection() internally
                    return await func(*args, **kwargs)

            except Exception as e:
                logger.error(f"{err_prefix}: {str(e)}")
                return f"{err_prefix}: {str(e)}"

        return wrapper

    return decorator
