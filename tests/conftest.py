"""Shared test fixtures for the ableton-mcp test suite."""

import os
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent


@pytest.fixture
def root_dir() -> Path:
    """Return the project root directory."""
    return ROOT_DIR


@pytest.fixture
def remote_script_source() -> str:
    """Read and return the AbletonMCP Remote Script source code."""
    source_path = ROOT_DIR / "AbletonMCP_Remote_Script" / "__init__.py"
    return source_path.read_text(encoding="utf-8")


@pytest.fixture
def server_source() -> str:
    """Read and return the MCP Server source code."""
    source_path = ROOT_DIR / "MCP_Server" / "server.py"
    return source_path.read_text(encoding="utf-8")
