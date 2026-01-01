"""Ableton Live integration through the Model Context Protocol."""

__version__ = "0.1.0"

# Expose key classes and functions for easier imports
from .server import AbletonConnection as AbletonConnection
from .server import get_ableton_connection as get_ableton_connection
