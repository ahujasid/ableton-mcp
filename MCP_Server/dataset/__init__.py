"""Supabase-backed music-creation trajectory dataset recording (opt-in)."""

from .consent import consent_state, needs_prompt, record_consent
from .recorder import SessionRecorder, dataset_enabled, get_recorder, reset_recorder_for_tests
from .schema import (
    CollectionMode,
    EventType,
    PreferenceRating,
    PreferenceSource,
    SessionMeta,
    TrajectoryEvent,
    categorize_tool,
    stable_hash,
)
from .hierarchy import enrich_export_row, label_action, label_intent

__all__ = [
    "CollectionMode",
    "EventType",
    "PreferenceRating",
    "PreferenceSource",
    "SessionMeta",
    "SessionRecorder",
    "TrajectoryEvent",
    "categorize_tool",
    "consent_state",
    "dataset_enabled",
    "needs_prompt",
    "record_consent",
    "enrich_export_row",
    "get_recorder",
    "label_action",
    "label_intent",
    "reset_recorder_for_tests",
    "stable_hash",
]
