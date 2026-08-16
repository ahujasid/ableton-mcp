"""Canonical schema for AbletonMCP music-creation trajectory datasets.

Training unit: (intent?, S_t, action, S_{t+1}, preference?)

Product telemetry (Supabase) is separate — this schema is for local dataset recording only.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


SCHEMA_VERSION = 2


class EventType(str, Enum):
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    INTENT = "intent"
    ACTION = "action"
    STATE = "state"
    PREFERENCE = "preference"
    AUDITION = "audition"


class CollectionMode(str, Enum):
    AGENT = "agent"  # LLM via MCP
    ASSISTED = "assisted"  # human + agent
    PASSIVE = "passive"  # human-only (future)


class PreferenceRating(str, Enum):
    BETTER = "better"
    SAME = "same"
    WORSE = "worse"
    KEEP = "keep"
    REJECT = "reject"
    THUMBS_UP = "thumbs_up"
    THUMBS_DOWN = "thumbs_down"
    PAIRWISE = "pairwise"


class PreferenceSource(str, Enum):
    """Where a preference came from — filter on this when training."""

    HUMAN = "human"  # explicit rate_last_action / prefer_candidate call
    IMPLICIT = "implicit"  # inferred from behaviour (undo, survival)


ACTION_CATEGORIES = {
    "create_midi_track": "create",
    "create_audio_track": "create",
    "create_clip": "create",
    "create_audio_clip": "create",
    "set_track_name": "edit",
    "set_clip_name": "edit",
    "set_arrangement_clip_name": "edit",
    "add_notes_to_clip": "edit_midi",
    "set_tempo": "mix",
    "set_device_parameter": "mix",
    "fire_clip": "transport",
    "stop_clip": "transport",
    "start_playback": "transport",
    "stop_playback": "transport",
    "set_arrangement_time": "transport",
    "switch_to_arrangement_view": "transport",
    "duplicate_to_arrangement": "arrangement",
    "load_instrument_or_effect": "browse",
    "load_drum_kit": "browse",
}


def new_id(prefix: str = "") -> str:
    uid = uuid.uuid4().hex[:12]
    return f"{prefix}_{uid}" if prefix else uid


def now_ts() -> float:
    return time.time()


def stable_hash(obj: Any) -> str:
    """Canonical SHA-256 of a JSON-serializable object (for state fingerprints)."""
    payload = json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def categorize_tool(tool_name: str) -> str:
    if tool_name.startswith("human_"):
        return "passive"
    return ACTION_CATEGORIES.get(tool_name, "other")


@dataclass
class SessionMeta:
    session_id: str
    started_at: float
    mode: str = CollectionMode.AGENT.value
    schema_version: int = SCHEMA_VERSION
    ableton_mcp_version: str | None = None
    notes: str | None = None
    active_intent_id: str | None = None
    ended_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TrajectoryEvent:
    """One JSONL line in events.jsonl."""

    type: str
    session_id: str
    ts: float = field(default_factory=now_ts)
    v: int = SCHEMA_VERSION
    event_id: str = field(default_factory=lambda: new_id("evt"))

    # Monotonic position of this event within its session (1-based).
    step_id: int | None = None

    # Optional payload fields (only some used per type)
    intent_id: str | None = None
    text: str | None = None
    level: int | None = None  # hierarchical intent level 1–5

    action_id: str | None = None
    tool: str | None = None
    category: str | None = None
    params: dict[str, Any] | None = None
    pre_hash: str | None = None
    post_hash: str | None = None
    success: bool | None = None
    duration_ms: float | None = None
    error: str | None = None

    state_hash: str | None = None
    state_path: str | None = None  # relative path under session dir

    target_action_id: str | None = None
    rating: str | None = None
    rating_source: str | None = None  # human | implicit
    tags: list[str] | None = None
    note: str | None = None
    winner: str | None = None
    candidate_a: str | None = None
    candidate_b: str | None = None

    uri: str | None = None
    kept: bool | None = None
    search_query: str | None = None
    dwell_ms: float | None = None

    extra: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return {k: v for k, v in data.items() if v is not None}


def make_session_start(session_id: str, mode: str = CollectionMode.AGENT.value) -> TrajectoryEvent:
    return TrajectoryEvent(
        type=EventType.SESSION_START.value,
        session_id=session_id,
        extra={"mode": mode},
    )


def make_intent(
    session_id: str,
    text: str,
    level: int | None = None,
    intent_id: str | None = None,
) -> TrajectoryEvent:
    return TrajectoryEvent(
        type=EventType.INTENT.value,
        session_id=session_id,
        intent_id=intent_id or new_id("intent"),
        text=text,
        level=level,
    )


def make_action(
    session_id: str,
    tool: str,
    params: dict[str, Any] | None = None,
    pre_hash: str | None = None,
    post_hash: str | None = None,
    success: bool = True,
    duration_ms: float | None = None,
    error: str | None = None,
    intent_id: str | None = None,
    action_id: str | None = None,
    text: str | None = None,
    level: int | None = None,
) -> TrajectoryEvent:
    return TrajectoryEvent(
        type=EventType.ACTION.value,
        session_id=session_id,
        action_id=action_id or new_id("act"),
        tool=tool,
        category=categorize_tool(tool),
        params=params,
        pre_hash=pre_hash,
        post_hash=post_hash,
        success=success,
        duration_ms=duration_ms,
        error=error,
        intent_id=intent_id,
        text=text,
        level=level,
    )


def make_state(
    session_id: str,
    state_hash: str,
    state_path: str,
    intent_id: str | None = None,
) -> TrajectoryEvent:
    return TrajectoryEvent(
        type=EventType.STATE.value,
        session_id=session_id,
        state_hash=state_hash,
        state_path=state_path,
        intent_id=intent_id,
    )


def make_preference(
    session_id: str,
    rating: str,
    target_action_id: str | None = None,
    tags: list[str] | None = None,
    note: str | None = None,
    winner: str | None = None,
    candidate_a: str | None = None,
    candidate_b: str | None = None,
    intent_id: str | None = None,
    rating_source: str = PreferenceSource.HUMAN.value,
) -> TrajectoryEvent:
    return TrajectoryEvent(
        type=EventType.PREFERENCE.value,
        session_id=session_id,
        rating=rating,
        rating_source=rating_source,
        target_action_id=target_action_id,
        tags=tags,
        note=note,
        winner=winner,
        candidate_a=candidate_a,
        candidate_b=candidate_b,
        intent_id=intent_id,
    )


def make_audition(
    session_id: str,
    uri: str,
    kept: bool | None = None,
    search_query: str | None = None,
    dwell_ms: float | None = None,
    intent_id: str | None = None,
) -> TrajectoryEvent:
    return TrajectoryEvent(
        type=EventType.AUDITION.value,
        session_id=session_id,
        uri=uri,
        kept=kept,
        search_query=search_query,
        dwell_ms=dwell_ms,
        intent_id=intent_id,
    )


