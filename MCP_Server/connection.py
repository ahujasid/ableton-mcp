"""AbletonConnection: socket client for the Ableton Remote Script."""

import json
import logging
import socket
from dataclasses import dataclass
from typing import Any, Dict

logger = logging.getLogger("AbletonMCPServer")


@dataclass
class AbletonConnection:
    host: str
    port: int
    sock: socket.socket = None

    def connect(self) -> bool:
        """Connect to the Ableton Remote Script socket server."""
        if self.sock:
            return True
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.host, self.port))
            logger.info(f"Connected to Ableton at {self.host}:{self.port}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Ableton: {str(e)}")
            self.sock = None
            return False

    def disconnect(self) -> None:
        """Disconnect from the Ableton Remote Script."""
        if self.sock:
            try:
                self.sock.close()
            except Exception as e:
                logger.error(f"Error disconnecting from Ableton: {str(e)}")
            finally:
                self.sock = None

    def receive_full_response(self, sock: socket.socket, buffer_size: int = 8192) -> bytes:
        """Receive the complete response, potentially in multiple chunks."""
        chunks = []
        sock.settimeout(15.0)
        try:
            while True:
                try:
                    chunk = sock.recv(buffer_size)
                    if not chunk:
                        if not chunks:
                            raise Exception("Connection closed before receiving any data")
                        break
                    chunks.append(chunk)
                    try:
                        data = b"".join(chunks)
                        json.loads(data.decode("utf-8"))
                        logger.info(f"Received complete response ({len(data)} bytes)")
                        return data
                    except json.JSONDecodeError:
                        continue
                except socket.timeout:
                    logger.warning("Socket timeout during chunked receive")
                    break
                except (ConnectionError, BrokenPipeError, ConnectionResetError) as e:
                    logger.error(f"Socket connection error during receive: {str(e)}")
                    raise
        except Exception as e:
            logger.error(f"Error during receive: {str(e)}")
            raise
        if chunks:
            data = b"".join(chunks)
            logger.info(f"Returning data after receive completion ({len(data)} bytes)")
            try:
                json.loads(data.decode("utf-8"))
                return data
            except json.JSONDecodeError:
                raise Exception("Incomplete JSON response received")
        raise Exception("No data received")

    def send_command(self, command_type: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Send a command to Ableton and return the response."""
        if not self.sock and not self.connect():
            raise ConnectionError("Not connected to Ableton")
        command = {"type": command_type, "params": params or {}}
        is_modifying_command = command_type in [
            "create_midi_track", "create_audio_track", "set_track_name",
            "create_clip", "add_notes_to_clip", "set_clip_name",
            "set_tempo", "fire_clip", "stop_clip", "set_device_parameter",
            "start_playback", "stop_playback", "load_instrument_or_effect",
            "arm_track", "disarm_track", "set_arrangement_overdub",
            "start_arrangement_recording", "stop_arrangement_recording",
            "set_loop_start", "set_loop_end", "set_loop_length", "set_playback_position",
            "create_scene", "delete_scene", "duplicate_scene", "trigger_scene", "set_scene_name",
            "set_track_color", "set_clip_color",
            "quantize_clip", "transpose_clip", "duplicate_clip",
            "group_tracks", "set_track_volume", "set_track_pan", "set_track_mute", "set_track_solo",
            "load_audio_sample", "set_warp_mode", "set_clip_warp", "crop_clip", "reverse_clip",
            "set_clip_loop_points", "set_clip_start_marker", "set_clip_end_marker", "set_track_send",
            "copy_clip_to_arrangement", "create_automation", "clear_automation",
            "delete_time", "duplicate_time", "insert_silence", "create_locator",
            "delete_clip", "set_metronome", "tap_tempo", "set_macro_value", "capture_midi", "apply_groove",
            "freeze_track", "unfreeze_track", "export_track_audio",
            "create_return_track", "delete_track", "duplicate_track", "set_track_arm",
            "set_chain_device_parameter",
            "delete_device", "delete_chain_device",
            "set_return_track_name", "load_on_return_track",
            "switch_to_view", "record_arrangement_clip",
        ]
        try:
            logger.info(f"Sending command: {command_type} with params: {params}")
            self.sock.sendall(json.dumps(command).encode("utf-8"))
            logger.info("Command sent, waiting for response...")
            if is_modifying_command:
                import time
                time.sleep(0.1)
            self.sock.settimeout(15.0 if is_modifying_command else 10.0)
            response_data = self.receive_full_response(self.sock)
            logger.info(f"Received {len(response_data)} bytes of data")
            response = json.loads(response_data.decode("utf-8"))
            logger.info(f"Response parsed, status: {response.get('status', 'unknown')}")
            if response.get("status") == "error":
                logger.error(f"Ableton error: {response.get('message')}")
                raise Exception(response.get("message", "Unknown error from Ableton"))
            if is_modifying_command:
                import time
                time.sleep(0.1)
            return response.get("result", {})
        except socket.timeout:
            logger.error("Socket timeout while waiting for response from Ableton")
            self.sock = None
            raise Exception("Timeout waiting for Ableton response")
        except (ConnectionError, BrokenPipeError, ConnectionResetError) as e:
            logger.error(f"Socket connection error: {str(e)}")
            self.sock = None
            raise Exception(f"Connection to Ableton lost: {str(e)}")
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON response from Ableton: {str(e)}")
            self.sock = None
            raise Exception(f"Invalid response from Ableton: {str(e)}")
        except Exception as e:
            logger.error(f"Error communicating with Ableton: {str(e)}")
            self.sock = None
            raise Exception(f"Communication error with Ableton: {str(e)}")
