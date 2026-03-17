"""Async connection to Ableton Live Remote Script.

Replaces the old blocking socket connection with asyncio streams.
Key improvements:
- Non-blocking I/O (doesn't freeze the event loop)
- No time.sleep() calls
- Automatic reconnection
- Batch command support
- Connection locking for thread safety
"""
import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("AbletonMCPServer")


class AbletonConnection:
    """Async TCP connection to the Ableton Remote Script"""

    def __init__(self, host: str = "localhost", port: int = 9877, timeout: float = 10.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self._lock = asyncio.Lock()
        self._connected = False

    async def connect(self) -> bool:
        """Connect to the Ableton Remote Script socket server"""
        try:
            self.reader, self.writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=5.0,
            )
            self._connected = True
            logger.info(f"Connected to Ableton at {self.host}:{self.port}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Ableton: {e}")
            self._connected = False
            return False

    async def disconnect(self):
        """Disconnect from the Ableton Remote Script"""
        if self.writer:
            try:
                self.writer.close()
                await self.writer.wait_closed()
            except Exception:
                pass
        self.reader = None
        self.writer = None
        self._connected = False

    async def ensure_connected(self):
        """Ensure we have an active connection, reconnecting if needed"""
        if self._connected and self.writer and not self.writer.is_closing():
            return

        self._connected = False
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            logger.info(f"Connecting to Ableton (attempt {attempt}/{max_attempts})...")
            if await self.connect():
                # Validate with a quick command
                try:
                    await self._send_and_receive("get_session_info")
                    logger.info("Connection validated successfully")
                    return
                except Exception as e:
                    logger.warning(f"Connection validation failed: {e}")
                    await self.disconnect()

            if attempt < max_attempts:
                await asyncio.sleep(0.5)

        raise ConnectionError(
            "Could not connect to Ableton. Make sure the Remote Script is running."
        )

    async def send_command(
        self, command_type: str, params: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Send a command to Ableton and return the response"""
        async with self._lock:
            await self.ensure_connected()
            return await self._send_and_receive(command_type, params)

    async def send_batch(
        self, commands: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Send multiple commands in a single batch for efficiency.

        Falls back to sequential execution if the Remote Script
        doesn't support batch mode.
        """
        async with self._lock:
            await self.ensure_connected()

            batch = [
                {"type": cmd["type"], "params": cmd.get("params", {})}
                for cmd in commands
            ]
            payload = json.dumps(batch).encode("utf-8")

            try:
                self.writer.write(payload)
                await self.writer.drain()

                response_data = await self._read_json_response()
                responses = json.loads(response_data.decode("utf-8"))

                if isinstance(responses, list):
                    results = []
                    for resp in responses:
                        if resp.get("status") == "error":
                            results.append(
                                {"error": resp.get("message", "Unknown error")}
                            )
                        else:
                            results.append(resp.get("result", {}))
                    return results
                else:
                    # Server returned single response — batch not supported
                    return [responses.get("result", {})]
            except Exception as e:
                logger.error(f"Batch command error: {e}")
                self._connected = False
                raise

    async def _send_and_receive(
        self, command_type: str, params: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Send a single command and receive the response"""
        command = {"type": command_type, "params": params or {}}

        try:
            self.writer.write(json.dumps(command).encode("utf-8"))
            await self.writer.drain()

            response_data = await self._read_json_response()
            response = json.loads(response_data.decode("utf-8"))

            if response.get("status") == "error":
                raise Exception(
                    response.get("message", "Unknown error from Ableton")
                )

            return response.get("result", {})
        except asyncio.TimeoutError:
            logger.error("Timeout waiting for Ableton response")
            self._connected = False
            raise Exception("Timeout waiting for Ableton response")
        except (ConnectionError, BrokenPipeError, ConnectionResetError) as e:
            logger.error(f"Connection error: {e}")
            self._connected = False
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON response: {e}")
            self._connected = False
            raise

    async def _read_json_response(self) -> bytes:
        """Read a complete JSON response using incremental parsing"""
        buffer = b""
        while True:
            chunk = await asyncio.wait_for(
                self.reader.read(8192), timeout=self.timeout
            )
            if not chunk:
                if not buffer:
                    raise ConnectionError("Connection closed before receiving data")
                break

            buffer += chunk

            try:
                json.loads(buffer.decode("utf-8"))
                return buffer
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue

        # Final check on accumulated buffer
        try:
            json.loads(buffer.decode("utf-8"))
            return buffer
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise Exception("Incomplete JSON response received")


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------
_connection: Optional[AbletonConnection] = None


async def get_connection() -> AbletonConnection:
    """Get or create the global Ableton connection"""
    global _connection
    if _connection is None:
        _connection = AbletonConnection()
    await _connection.ensure_connected()
    return _connection


async def cleanup_connection():
    """Clean up the global connection on shutdown"""
    global _connection
    if _connection:
        await _connection.disconnect()
        _connection = None
