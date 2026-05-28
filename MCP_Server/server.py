# ableton_mcp_server.py
"""Ableton MCP server: FastMCP setup, connection lifecycle, tool registration."""

import logging
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict

from mcp.server.fastmcp import FastMCP

from MCP_Server.connection import AbletonConnection
from MCP_Server.tools import register_all

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("AbletonMCPServer")

_ableton_connection: Any = None


@asynccontextmanager
async def server_lifespan(server: FastMCP) -> AsyncIterator[Dict[str, Any]]:
    """Manage server startup and shutdown lifecycle."""
    try:
        logger.info("AbletonMCP server starting up")
        try:
            get_ableton_connection()
            logger.info("Successfully connected to Ableton on startup")
        except Exception as e:
            logger.warning(f"Could not connect to Ableton on startup: {str(e)}")
            logger.warning("Make sure the Ableton Remote Script is running")
        yield {}
    finally:
        global _ableton_connection
        if _ableton_connection:
            logger.info("Disconnecting from Ableton on shutdown")
            _ableton_connection.disconnect()
            _ableton_connection = None
        logger.info("AbletonMCP server shut down")


# Create the MCP server with lifespan support
mcp = FastMCP("AbletonMCP", lifespan=server_lifespan)


def get_ableton_connection() -> AbletonConnection:
    """Get or create a persistent Ableton connection."""
    global _ableton_connection
    if _ableton_connection is not None:
        try:
            _ableton_connection.sock.settimeout(1.0)
            _ableton_connection.sock.sendall(b"")
            return _ableton_connection
        except Exception as e:
            logger.warning(f"Existing connection is no longer valid: {str(e)}")
            try:
                _ableton_connection.disconnect()
            except Exception:
                pass
            _ableton_connection = None
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            logger.info(f"Connecting to Ableton (attempt {attempt}/{max_attempts})...")
            _ableton_connection = AbletonConnection(host="localhost", port=9877)
            if _ableton_connection.connect():
                logger.info("Created new persistent connection to Ableton")
                try:
                    _ableton_connection.send_command("get_session_info")
                    logger.info("Connection validated successfully")
                    return _ableton_connection
                except Exception as e:
                    logger.error(f"Connection validation failed: {str(e)}")
                    _ableton_connection.disconnect()
                    _ableton_connection = None
        except Exception as e:
            logger.error(f"Connection attempt {attempt} failed: {str(e)}")
            if _ableton_connection:
                _ableton_connection.disconnect()
                _ableton_connection = None
        if attempt < max_attempts:
            time.sleep(1.0)
    raise Exception(
        "Could not connect to Ableton. Make sure the Remote Script is running."
    )


# Register all tool modules (must be after get_ableton_connection is defined)
register_all(mcp, get_ableton_connection)


def main() -> None:
    """Run the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
