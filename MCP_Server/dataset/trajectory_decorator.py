"""Decorator that records (S_t → action → S_{t+1}) trajectory steps.

Active only when telemetry is enabled and the user has consented
(see dataset.recorder.dataset_enabled).
"""

from __future__ import annotations

import functools
import inspect
import logging
import os
import os.path as _os_path
import re
import threading
import time
from typing import Any, Callable

from .recorder import get_recorder
from .snapshot import fetch_snapshot

logger = logging.getLogger("ableton-mcp-dataset")

# Tools that change musical content — snapshot before and after. Transport and
# view tools are excluded: their actions are still recorded, only the pre/post
# hashes are skipped.
MODIFYING_TOOLS = {
    "create_midi_track",
    "create_audio_track",
    "set_track_name",
    "create_clip",
    "create_audio_clip",
    "add_notes_to_clip",
    "set_clip_name",
    "set_arrangement_clip_name",
    "set_tempo",
    "set_device_parameter",
    "load_instrument_or_effect",
    "load_drum_kit",
    "duplicate_to_arrangement",
}

_PARAM_KEYS = (
    "track_index",
    "clip_index",
    "device_index",
    "index",
    "length",
    "time",
    "destination_time",
    "tempo",
    "uri",
    "rack_uri",
    "kit_path",
    "name",
    "path",
    "include_notes",
    "include_params",
    "rating",
    "tags",
    "note",
    "text",
    "level",
    "winner",
    "candidate_a",
    "candidate_b",
    "search_query",
    "kept",
    "category_type",
)

# A `path` ending in one of these is a file on disk, not a Live browser category.
_AUDIO_EXTS = frozenset({
    ".wav", ".aiff", ".aif", ".flac", ".mp3", ".ogg", ".m4a", ".wma", ".alc", ".asd",
})


def _light_snapshots() -> bool:
    flag = os.environ.get("ABLETON_MCP_DATASET_LIGHT", "").strip().lower()
    return flag in {"1", "true", "yes", "on"}


def _snapshots_disabled() -> bool:
    """Kill switch: record actions but never snapshot state."""
    flag = os.environ.get("ABLETON_MCP_DATASET_NO_SNAPSHOTS", "").strip().lower()
    return flag in {"1", "true", "yes", "on"}


def _pre_cache_disabled() -> bool:
    """Kill switch: always take a fresh pre-snapshot, never reuse the cache."""
    flag = os.environ.get("ABLETON_MCP_DATASET_NO_PRE_CACHE", "").strip().lower()
    return flag in {"1", "true", "yes", "on"}


# Snapshots are the only dataset work on the tool's critical path — a
# synchronous round-trip to Live. Stop taking them if they turn slow or fail.
_SLOW_SNAPSHOT_SEC = float(os.environ.get("ABLETON_MCP_SNAPSHOT_SLOW_SEC", "2.0"))
_BREAKER_THRESHOLD = 3
_BREAKER_COOLDOWN_SEC = 120.0

_breaker_lock = threading.Lock()
_breaker_strikes = 0
_breaker_open_until = 0.0


def _breaker_is_open() -> bool:
    with _breaker_lock:
        return time.time() < _breaker_open_until


def _breaker_record(ok: bool, elapsed: float) -> None:
    """Trip the breaker after repeated slow/failed snapshots."""
    global _breaker_strikes, _breaker_open_until
    with _breaker_lock:
        if ok and elapsed < _SLOW_SNAPSHOT_SEC:
            _breaker_strikes = 0
            return
        _breaker_strikes += 1
        if _breaker_strikes >= _BREAKER_THRESHOLD:
            _breaker_open_until = time.time() + _BREAKER_COOLDOWN_SEC
            _breaker_strikes = 0
            logger.warning(
                "Trajectory snapshots paused for %.0fs — snapshots were slow or "
                "failing. Tool calls are unaffected; state capture resumes after "
                "the cooldown.",
                _BREAKER_COOLDOWN_SEC,
            )


# Tools in this repo signal failure by returning a string rather than raising.
_FAILURE_PREFIXES = (
    "error",
    "ableton remote script missing capability",
    "dataset recording is off",
    "failed to ",
    "could not ",
    "unknown command",
)


def _looks_like_failure(result: Any) -> bool:
    if not isinstance(result, str):
        return False
    head = result.lstrip().lower()
    return head.startswith(_FAILURE_PREFIXES)


def _is_browser_path(value: str) -> bool:
    """True for a Live browser location, false for anything filesystem-shaped.

    Browser paths are category strings like "Drums/Kits/808 Core Kit"; they name
    Live's own tree and contain no user identity. Filesystem paths must stay
    redacted because they routinely embed the OS username. Every ambiguous case
    is treated as a filesystem path.
    """
    if not value or len(value) > 500:
        return False
    if value.startswith(("/", "~", "\\\\")):
        return False  # POSIX absolute, home-relative, or UNC
    if re.match(r"^[A-Za-z]:[\\/]", value):
        return False  # Windows drive path
    if "\\" in value:
        return False  # Windows separators never appear in browser paths
    if _os_path.splitext(value)[1].lower() in _AUDIO_EXTS:
        return False  # a file, not a browser category
    return True


def _extract_params(kwargs: dict) -> dict[str, Any]:
    params: dict[str, Any] = {}
    for key in _PARAM_KEYS:
        if key not in kwargs or kwargs[key] is None:
            continue
        value = kwargs[key]
        if key == "path" and isinstance(value, str):
            if _is_browser_path(value):
                params["browser_path"] = value[:500]
            else:
                import os as _os

                params["file_extension"] = _os.path.splitext(value)[1].lower() or "unknown"
                params["has_path"] = True
            continue
        if key == "name":
            from .snapshot import _scrub_name

            params[key] = _scrub_name(value)
            continue
        if isinstance(value, str) and len(value) > 500:
            value = value[:500] + "..."
        params[key] = value

    notes = kwargs.get("notes")
    if isinstance(notes, list):
        params["notes_count"] = len(notes)
        compact = []
        for n in notes[:256]:
            if isinstance(n, dict):
                compact.append(
                    [
                        n.get("pitch", 0),
                        n.get("start_time", 0),
                        n.get("duration", 0),
                        n.get("velocity", 100),
                    ]
                )
        params["notes"] = compact
        if len(notes) > 256:
            params["notes_truncated"] = True
    return params


async def _try_elicit(kwargs: dict) -> bool:
    """Ask for consent through the client. True if the user actually answered.

    False means fall back to the text notice — either the client cannot render
    a dialog, or there was no ctx to render it through.
    """
    ctx = kwargs.get("ctx")
    if ctx is None:
        return False
    try:
        from .consent import UNKNOWN, try_elicit_consent

        state = await try_elicit_consent(ctx)
    except Exception as e:
        logger.debug("Consent elicitation failed: %s", e)
        return False
    if state is None:
        return False
    if state == UNKNOWN:
        # Dialog shown but dismissed; do not also nag with the text prompt
        return True
    try:
        from ..telemetry import refresh_consent_from_dataset

        refresh_consent_from_dataset()
    except Exception as e:
        logger.debug("Could not refresh telemetry consent: %s", e)
    return True


def _with_consent_notice(result: Any) -> Any:
    """Append the one-time consent question to a tool result.

    Only string results are touched, and only when the user has never been
    asked. Any failure here is swallowed: the consent prompt must never be the
    reason a tool call breaks.
    """
    if not isinstance(result, str):
        return result
    try:
        from .consent import maybe_consent_notice

        notice = maybe_consent_notice()
    except Exception as e:
        logger.debug("Consent notice unavailable: %s", e)
        return result
    return result + notice if notice else result


def _safe_get_recorder():
    """get_recorder() touches config/telemetry — never let that break a tool."""
    try:
        return get_recorder()
    except Exception as e:
        logger.debug("Could not get dataset recorder: %s", e)
        return None


def _adopt_prompt(recorder, kwargs: dict) -> None:
    """Promote the tool's ``user_prompt`` argument into the active intent.

    submit_intent owns the intent explicitly, so skip it there and let the
    caller's level/text win.
    """
    prompt = kwargs.get("user_prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        return
    try:
        recorder.observe_prompt(prompt)
    except Exception as e:
        logger.debug("Could not adopt user_prompt as intent: %s", e)


def _take_snapshot() -> tuple[str | None, dict | None]:
    """Returns (hash, snapshot) or (None, None) on failure / disabled Ableton.

    This is the only dataset work that runs synchronously inside a tool call.
    It never raises, and is skipped entirely while the breaker is open, so
    dataset collection can degrade without ever failing the user's tool call.
    """
    recorder = _safe_get_recorder()
    if recorder is None or _snapshots_disabled() or _breaker_is_open():
        return None, None

    started = time.time()
    try:
        from ..script_handshake import script_has_capability
        from ..server import get_ableton_connection

        if not script_has_capability("get_session_snapshot"):
            logger.debug("Skipping trajectory snapshot — Remote Script lacks get_session_snapshot")
            return None, None

        ableton = get_ableton_connection()
        light = _light_snapshots()
        snapshot = fetch_snapshot(
            ableton.send_command,
            include_notes=not light,
            include_params=not light,
        )
        elapsed = time.time() - started
        if snapshot is None:
            _breaker_record(False, elapsed)
            return None, None
        _breaker_record(True, elapsed)
        if elapsed >= _SLOW_SNAPSHOT_SEC:
            logger.debug("Trajectory snapshot took %.2fs", elapsed)
        state_hash, _ = recorder.record_state(snapshot)
        return state_hash, snapshot
    except Exception as e:
        _breaker_record(False, time.time() - started)
        logger.warning("Trajectory snapshot failed: %s", e)
        return None, None


def _passive_watch_active() -> bool:
    """True when human edits in Live would be noticed.

    The pre-hash cache is only sound if something is watching for out-of-band
    changes. Without a running poller (or a Remote Script that can report
    them), a cached hash could describe state that a human has since edited,
    so we fall back to snapshotting every time.
    """
    try:
        from ..dataset.passive_poller import poller_is_running
        from ..script_handshake import script_has_capability

        return poller_is_running() and script_has_capability("drain_passive_events")
    except Exception:
        return False


def _pre_snapshot() -> tuple[str | None, str | None]:
    """Pre-action state hash plus its provenance ("fresh" or "cached").

    The previous action's post-state is this action's pre-state unless Live
    changed in between. Saves one full snapshot round-trip per modifying call.

    Invalidation rides on the passive poller, so a human edit made within one
    poll interval of a tool call can still be missed. There is also no LOM
    listener for device parameter changes, arrangement-clip edits, or send
    values, so a human turning a knob never clears the cache. Set
    ABLETON_MCP_DATASET_NO_PRE_CACHE=1 to always snapshot.

    A wrong pre_hash is worse than a missing one, so the source is returned for
    stamping onto the action.
    """
    if _pre_cache_disabled():
        state_hash, _ = _take_snapshot()
        return state_hash, ("fresh" if state_hash else None)
    recorder = _safe_get_recorder()
    if recorder is None:
        return None, None
    if _passive_watch_active():
        cached = recorder.take_cached_state_hash()
        if cached is not None:
            logger.debug("Reusing cached pre-snapshot hash=%s", cached)
            return cached, "cached"
    state_hash, _ = _take_snapshot()
    return state_hash, ("fresh" if state_hash else None)


def trajectory_tool(tool_name: str, modifying: bool | None = None):
    """Record action (+ optional pre/post state) when dataset mode is on.

    Args:
        tool_name: Canonical tool name for the action log
        modifying: If True, snapshot before/after. Defaults to membership in MODIFYING_TOOLS.
    """
    if modifying is None:
        modifying = tool_name in MODIFYING_TOOLS

    # submit_intent sets the intent itself, with an explicit level
    adopts_prompt = tool_name != "submit_intent"

    def _begin(recorder, kwargs: dict) -> tuple[str | None, str | None, float]:
        """Shared pre-call work. Returns (pre_hash, pre_hash_source, start)."""
        if adopts_prompt:
            _adopt_prompt(recorder, kwargs)
        pre_hash = pre_hash_source = None
        if modifying:
            pre_hash, pre_hash_source = _pre_snapshot()
        return pre_hash, pre_hash_source, time.time()

    def _finish(recorder, kwargs: dict, pre_hash, pre_hash_source,
                start: float, success: bool, error: str | None) -> None:
        """Shared post-call work. Never raises — recording must not break a tool."""
        duration_ms = (time.time() - start) * 1000
        post_hash = None
        if modifying:
            post_hash, _ = _take_snapshot()
        try:
            recorder.record_action(
                tool=tool_name,
                params=_extract_params(kwargs),
                pre_hash=pre_hash,
                post_hash=post_hash,
                pre_hash_source=pre_hash_source,
                success=success,
                duration_ms=duration_ms,
                error=error,
            )
        except Exception as log_error:
            logger.debug("Failed to record trajectory action: %s", log_error)

    def _classify(result: Any) -> tuple[bool, str | None]:
        """Many tools signal failure by returning a string instead of raising."""
        if _looks_like_failure(result):
            return False, result
        return True, None

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs) -> Any:
            recorder = _safe_get_recorder()
            if recorder is None:
                return _with_consent_notice(func(*args, **kwargs))

            pre_hash, pre_hash_source, start = _begin(recorder, kwargs)
            success, error = False, None
            try:
                result = func(*args, **kwargs)
                success, error = _classify(result)
                return result
            except Exception as e:
                error = str(e)
                raise
            finally:
                _finish(recorder, kwargs, pre_hash, pre_hash_source,
                        start, success, error)

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            recorder = _safe_get_recorder()
            if recorder is None:
                result = await func(*args, **kwargs)
                # Prefer a real client dialog; fall back to the text prompt
                if await _try_elicit(kwargs):
                    recorder = _safe_get_recorder()
                    if recorder is not None:
                        return result
                return _with_consent_notice(result)

            pre_hash, pre_hash_source, start = _begin(recorder, kwargs)
            success, error = False, None
            try:
                result = await func(*args, **kwargs)
                success, error = _classify(result)
                return result
            except Exception as e:
                error = str(e)
                raise
            finally:
                _finish(recorder, kwargs, pre_hash, pre_hash_source,
                        start, success, error)

        if inspect.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator
