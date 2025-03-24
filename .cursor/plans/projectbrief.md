# Ableton MCP Project Brief

## Overview
The Ableton MCP (Model Context Protocol) project provides a bridge between external applications and Ableton Live through a socket-based communication protocol. It consists of two main components:

1. MCP Server (Python-based FastMCP server)
2. Ableton Remote Script (Python-based Live control surface script)

## Core Requirements

### Communication Protocol
- Socket-based communication on localhost:9877
- JSON message format for commands and responses
- Reliable error handling and connection management
- Support for both synchronous and asynchronous operations

### Core Functionality
- Track management (create, modify, control)
- Clip management (create, edit, playback)
- Device management (load, parameter control)
- Browser integration (navigate, load items)
- Transport control (play, stop, tempo)
- Session information access

### Technical Requirements
- Clean error handling and logging
- Robust connection management
- Thread-safe operations
- Efficient message parsing
- Comprehensive API documentation

## Goals

1. Provide a stable and efficient bridge between external applications and Ableton Live
2. Enable comprehensive control over Ableton Live's core functionality
3. Maintain clean separation between server and remote script components
4. Ensure robust error handling and recovery
5. Deliver clear documentation for all available functionality 