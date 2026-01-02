"""
AbletonMCP Remote Script for Ableton Live.

This Remote Script connects Ableton Live to Claude AI through the Model Context
Protocol (MCP). It creates a TCP socket server that receives commands from the
MCP server and executes them within Ableton's Python runtime.

Architecture:
    Claude AI <-> MCP Server <-> TCP Socket (port 9877) <-> This Script <-> Ableton Live

Commands are JSON objects with 'type' and 'params' fields. Responses contain
'status' and 'result' or 'message'. State-modifying commands are automatically
scheduled on Ableton's main thread via schedule_message.
"""

import json
import queue
import socket
import threading
import traceback

from _Framework.ControlSurface import ControlSurface

from .commands import CommandContext, CommandRegistry

# Constants for socket communication
DEFAULT_PORT = 9877
HOST = "localhost"


def create_instance(c_instance):
    """Create and return the AbletonMCP script instance."""
    return AbletonMCP(c_instance)


class AbletonMCP(ControlSurface):
    """AbletonMCP Remote Script for Ableton Live."""

    def __init__(self, c_instance):
        """Initialize the control surface."""
        ControlSurface.__init__(self, c_instance)
        self.log_message("AbletonMCP Remote Script initializing...")

        # Socket server for communication
        self.server = None
        self.client_threads = []
        self.server_thread = None
        self.running = False

        # Cache the song reference for easier access
        self._song = self.song()

        # Cache for browser URIs to avoid repeated tree traversal
        self._browser_uri_cache = {}

        # Start the socket server
        self.start_server()

        self.log_message("AbletonMCP initialized")

        # Show a message in Ableton
        self.show_message(f"AbletonMCP: Listening for commands on port {DEFAULT_PORT}")

    def disconnect(self):
        """Called when Ableton closes or the control surface is removed."""
        self.log_message("AbletonMCP disconnecting...")
        self.running = False

        # Stop the server
        if self.server:
            try:
                self.server.close()
            except socket.error as e:
                self.log_message(f"Error closing server socket: {e}")
            except Exception as e:
                self.log_message(f"Unexpected error closing server: {e}")

        # Wait for the server thread to exit
        if self.server_thread and self.server_thread.is_alive():
            self.server_thread.join(1.0)

        # Clean up any client threads
        for client_thread in self.client_threads[:]:
            if client_thread.is_alive():
                self.log_message("Client thread still alive during disconnect")

        ControlSurface.disconnect(self)
        self.log_message("AbletonMCP disconnected")

    def start_server(self):
        """Start the socket server in a separate thread."""
        try:
            self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server.bind((HOST, DEFAULT_PORT))
            self.server.listen(5)  # Allow up to 5 pending connections

            self.running = True
            self.server_thread = threading.Thread(target=self._server_thread)
            self.server_thread.daemon = True
            self.server_thread.start()

            self.log_message(f"Server started on port {DEFAULT_PORT}")
        except Exception as e:
            self.log_message(f"Error starting server: {e}")
            self.show_message(f"AbletonMCP: Error starting server - {e}")

    def _server_thread(self):
        """Server thread implementation - handles client connections."""
        try:
            self.log_message("Server thread started")
            self.server.settimeout(1.0)

            while self.running:
                try:
                    client, address = self.server.accept()
                    self.log_message(f"Connection accepted from {address}")
                    self.show_message("AbletonMCP: Client connected")

                    client_thread = threading.Thread(
                        target=self._handle_client,
                        args=(client,)
                    )
                    client_thread.daemon = True
                    client_thread.start()

                    self.client_threads.append(client_thread)
                    self.client_threads = [t for t in self.client_threads if t.is_alive()]

                except socket.timeout:
                    continue
                except Exception as e:
                    if self.running:
                        self.log_message(f"Server accept error: {e}")
                    import time
                    time.sleep(0.5)

            self.log_message("Server thread stopped")
        except Exception as e:
            self.log_message(f"Server thread error: {e}")

    def _handle_client(self, client):
        """Handle communication with a connected client."""
        self.log_message("Client handler started")
        client.settimeout(None)
        buffer = ""

        try:
            while self.running:
                try:
                    data = client.recv(8192)

                    if not data:
                        self.log_message("Client disconnected")
                        break

                    buffer += data.decode("utf-8")

                    try:
                        command = json.loads(buffer)
                        buffer = ""

                        self.log_message(f"Received command: {command.get('type', 'unknown')}")

                        response = self._process_command(command)

                        client.sendall(json.dumps(response).encode("utf-8"))
                    except ValueError:
                        # Incomplete JSON, wait for more data
                        continue

                except Exception as e:
                    self.log_message(f"Error handling client data: {e}")
                    self.log_message(traceback.format_exc())

                    error_response = {
                        "status": "error",
                        "message": str(e),
                    }
                    try:
                        client.sendall(json.dumps(error_response).encode("utf-8"))
                    except Exception as send_error:
                        self.log_message(f"Failed to send error response: {send_error}")
                        break

                    if not isinstance(e, ValueError):
                        break
        except Exception as e:
            self.log_message(f"Error in client handler: {e}")
        finally:
            try:
                client.close()
            except socket.error as e:
                self.log_message(f"Error closing client socket: {e}")
            except Exception as e:
                self.log_message(f"Unexpected error closing client: {e}")
            self.log_message("Client handler stopped")

    def _create_command_context(self) -> CommandContext:
        """Create a CommandContext for executing commands."""
        return CommandContext(
            song=self._song,
            application=self.application(),
            log_message=self.log_message,
            show_message=self.show_message,
            schedule_message=self.schedule_message,
            browser_uri_cache=self._browser_uri_cache,
        )

    def _process_command(self, command):
        """Process a command from the client and return a response."""
        command_type = command.get("type", "")
        params = command.get("params", {})

        response = {
            "status": "success",
            "result": {},
        }

        try:
            # Look up the command in the registry
            command_class = CommandRegistry.get(command_type)

            if command_class is None:
                response["status"] = "error"
                response["message"] = f"Unknown command: {command_type}"
                return response

            # Create command instance
            cmd = command_class()

            # Create context for command execution
            context = self._create_command_context()

            # Check if command requires main thread execution
            if cmd.requires_main_thread:
                # Execute on main thread via queue
                response_queue = queue.Queue()

                def main_thread_task():
                    try:
                        result = cmd.execute(context, params)
                        response_queue.put({"status": "success", "result": result})
                    except Exception as e:
                        self.log_message(f"Error in main thread task: {e}")
                        self.log_message(traceback.format_exc())
                        response_queue.put({"status": "error", "message": str(e)})

                try:
                    self.schedule_message(0, main_thread_task)
                except AssertionError:
                    # Already on main thread
                    main_thread_task()

                try:
                    task_response = response_queue.get(timeout=10.0)
                    if task_response.get("status") == "error":
                        response["status"] = "error"
                        response["message"] = task_response.get("message", "Unknown error")
                    else:
                        response["result"] = task_response.get("result", {})
                except queue.Empty:
                    response["status"] = "error"
                    response["message"] = "Timeout waiting for operation to complete"
            else:
                # Execute directly (read-only commands)
                response["result"] = cmd.execute(context, params)

        except Exception as e:
            self.log_message(f"Error processing command: {e}")
            self.log_message(traceback.format_exc())
            response["status"] = "error"
            response["message"] = str(e)

        return response
