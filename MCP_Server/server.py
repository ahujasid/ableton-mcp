"""AbletonMCP Server - MCP server for Ableton Live integration.

Modular architecture: each tool category lives in its own module under tools/.
Uses async connection for non-blocking communication with Ableton.
Includes response caching for read-only operations.
"""
from mcp.server.fastmcp import FastMCP
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator, Dict, Any

from MCP_Server.connection import get_connection, cleanup_connection
from MCP_Server.cache import ResponseCache

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("AbletonMCPServer")

# Global cache instance (2s TTL for read-only operations)
cache = ResponseCache(default_ttl=2.0)


@asynccontextmanager
async def server_lifespan(server: FastMCP) -> AsyncIterator[Dict[str, Any]]:
    """Manage server startup and shutdown lifecycle"""
    try:
        logger.info("AbletonMCP server starting up")
        try:
            conn = await get_connection()
            logger.info("Successfully connected to Ableton on startup")
        except Exception as e:
            logger.warning(f"Could not connect to Ableton on startup: {e}")
            logger.warning("Make sure the Ableton Remote Script is running")
        yield {}
    finally:
        await cleanup_connection()
        logger.info("AbletonMCP server shut down")


# Create the MCP server with lifespan support
mcp = FastMCP("AbletonMCP", lifespan=server_lifespan)

# ---------------------------------------------------------------------------
# Register all tool modules
# ---------------------------------------------------------------------------
from MCP_Server.tools import (
    session_tools,
    track_tools,
    clip_tools,
    scene_tools,
    device_tools,
    transport_tools,
    browser_tools,
    ai_tools,
)

session_tools.register(mcp, get_connection, cache)
track_tools.register(mcp, get_connection, cache)
clip_tools.register(mcp, get_connection, cache)
scene_tools.register(mcp, get_connection, cache)
device_tools.register(mcp, get_connection, cache)
transport_tools.register(mcp, get_connection, cache)
browser_tools.register(mcp, get_connection, cache)
ai_tools.register(mcp, get_connection, cache)


# Main execution
def main():
    """Run the MCP server"""
    mcp.run()


if __name__ == "__main__":
    main()
