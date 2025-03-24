# Technical Context

## Technologies

### Server Component
- Python 3.x
- FastMCP framework for MCP server implementation
- Socket programming for communication
- JSON for data serialization
- Threading for concurrent operations

### Remote Script Component
- Python 2.x (Ableton Live's Python runtime)
- Ableton Live API (_Framework)
- Socket programming for communication
- JSON for data serialization
- Threading for background operations

## Development Setup

### Server Requirements
```python
# Required Python packages
fastmcp==1.0.0  # Model Context Protocol framework
```

### Remote Script Installation
1. Place the AbletonMCP_Remote_Script folder in:
   - Windows: `%APPDATA%\Ableton\Live x.x\User Remote Scripts`
   - macOS: `~/Library/Preferences/Ableton/Live x.x/User Remote Scripts`
2. Enable the script in Ableton Live's MIDI preferences

## Dependencies

### External Dependencies
- Ableton Live 10.x or later
- Python 3.7+ for server component
- Network port 9877 available for socket communication

### Internal Dependencies
- _Framework (provided by Ableton Live)
- Live API objects (accessed through Remote Script)

## Configuration

### Server Configuration
- Default port: 9877
- Host: localhost
- Connection timeout: 15 seconds
- Retry attempts: 3
- Retry delay: 1 second

### Remote Script Configuration
- Socket timeout: None (blocking mode)
- Buffer size: 8192 bytes
- JSON encoding: UTF-8

## Development Tools

### Recommended Tools
- Python IDE with debugging support
- Socket testing tools (e.g., netcat)
- JSON validator
- Log monitoring tools

### Testing Environment
- Local Ableton Live instance
- Python virtual environment for server
- Network monitoring tools
- Debug logging enabled 