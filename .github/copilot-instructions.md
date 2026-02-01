# Ableton MCP Development Instructions

This project is an MCP (Model Context Protocol) server for controlling Ableton Live programmatically.

## Quick Reference

- **MCP Server:** `MCP_Server/server.py` - Tool definitions and socket communication
- **Remote Script:** `AbletonMCP_Remote_Script/__init__.py` - Ableton Live control surface

## Documentation

For detailed instructions, see the topic-specific docs:

- [Running Local Server](./docs/running-local-server.md) - How to run from local directory instead of cached package
- [Adding New Tools](./docs/adding-new-tools.md) - Steps for creating new MCP tools
- [Live API Insights](./docs/live-api-insights.md) - Key discoveries about Ableton's Python API
- [Debugging](./docs/debugging.md) - How to check logs and troubleshoot
