"""Supabase access for trajectory datasets — reuses telemetry config credentials."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("ableton-mcp-dataset")

try:
    from supabase import Client, ClientOptions, create_client

    HAS_SUPABASE = True
except ImportError:
    HAS_SUPABASE = False
    Client = Any  # type: ignore


def get_supabase_config() -> tuple[str, str] | None:
    """Return (url, anon_key) from MCP_Server.config, or None if unavailable."""
    try:
        from ..config import telemetry_config

        if not telemetry_config.has_credentials:
            return None
        return telemetry_config.supabase_url, telemetry_config.supabase_anon_key
    except Exception as e:
        logger.debug("Dataset: could not load telemetry config: %s", e)
        return None


def create_supabase_client(session_id: str | None = None) -> Client | None:
    """Build a Supabase client for dataset writes.

    ``session_id`` is sent as the ``x-session-id`` header. RLS uses it to scope
    updates to the caller's own session, so a public anon key cannot be used to
    rewrite anyone else's rows.
    """
    if not HAS_SUPABASE:
        logger.warning("Dataset: supabase package not installed")
        return None
    creds = get_supabase_config()
    if not creds:
        logger.warning("Dataset: Supabase credentials not configured")
        return None
    url, key = creds
    options = ClientOptions(auto_refresh_token=False, persist_session=False)
    if session_id:
        options.headers = {**(getattr(options, "headers", None) or {}),
                           "x-session-id": session_id}
    return create_client(url, key, options=options)


def create_admin_client() -> Client | None:
    """Client for operator-side tooling (export, semantics) that must read.

    Anon has insert-only rights by design — the anon key is public, so granting
    it select would expose every user's data. Reads therefore require the
    service_role key, which stays in the operator's environment and is never
    packaged:

        export ABLETON_MCP_SUPABASE_SERVICE_KEY="<service_role key>"
    """
    import os

    if not HAS_SUPABASE:
        logger.error("supabase package not installed")
        return None
    try:
        from ..config import telemetry_config

        url = telemetry_config.supabase_url
    except Exception:
        url = ""
    key = os.environ.get("ABLETON_MCP_SUPABASE_SERVICE_KEY", "").strip()
    if not url or not key:
        logger.error(
            "Export/semantics need ABLETON_MCP_SUPABASE_URL and "
            "ABLETON_MCP_SUPABASE_SERVICE_KEY (service_role) in the environment."
        )
        return None
    options = ClientOptions(auto_refresh_token=False, persist_session=False)
    return create_client(url, key, options=options)


def get_customer_uuid() -> str | None:
    """Reuse the anonymous customer UUID from product telemetry when available."""
    try:
        from ..telemetry import get_telemetry

        return get_telemetry()._customer_uuid
    except Exception:
        return None
