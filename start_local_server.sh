#!/bin/bash
cd "$(dirname "$0")"
source ableton_mcp_venv/bin/activate
python -m MCP_Server.server
