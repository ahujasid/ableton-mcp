"""Environment-backed configuration for the AbletonMCP telemetry collector."""

import os
from dataclasses import dataclass
from dataclasses import field


@dataclass
class TelemetryConfig:
    """Settings used by :mod:`MCP_Server.telemetry`."""

    supabase_url: str = field(
        default_factory=lambda: os.environ.get(
            "ABLETON_MCP_TELEMETRY_SUPABASE_URL", ""
        )
    )
    supabase_anon_key: str = field(
        default_factory=lambda: os.environ.get(
            "ABLETON_MCP_TELEMETRY_SUPABASE_ANON_KEY", ""
        )
    )
    enabled: bool = True
    timeout: float = 1.5
    max_prompt_length: int = 1000


telemetry_config = TelemetryConfig()
