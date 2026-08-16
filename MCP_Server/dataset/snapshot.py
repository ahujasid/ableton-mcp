"""Helpers to fetch, scrub, and hash Ableton session snapshots."""

from __future__ import annotations

import logging
import re
from typing import Any, Callable

from .schema import stable_hash

logger = logging.getLogger("ableton-mcp-dataset")

# Names users never wrote: Live's own defaults, plus generic musical labels
# that carry training signal without identifying anyone. Anything outside this
# set is treated as user-authored free text and redacted.
_SAFE_NAME_RE = re.compile(
    r"""^(
        (audio|midi|return)\ ?track(\ \d+)?
      | track\ ?\d*
      | [a-z]-return
      | \d+-(audio|midi)
      | master | return | scene(\ \d+)? | clip(\ \d+)?
      | kick | snare | hat | hi-?hat | clap | tom | crash | ride | perc(ussion)?
      | drums? | bass | sub | lead | pad | keys | piano | synth | pluck | arp
      | guitar | vocal(s)?| vox | strings | brass | fx | riser | sweep | noise
      | chord(s)? | melody | harmony | loop | sample | intro | verse | chorus
      | bridge | drop | outro | break(down)?
    )$""",
    re.IGNORECASE | re.VERBOSE,
)

# Keys whose values are free text the user typed
_NAME_KEYS = frozenset({"name", "clip_name", "track_name", "scene_name", "chain_name"})


def _scrub_name(value: Any) -> Any:
    """Keep Live defaults and generic musical labels; redact anything else.

    Track and clip names are the one place a snapshot picks up prose the user
    wrote — "chorus for Sarah's wedding", client names, unreleased titles.
    Length is preserved as a coarse signal, but the text does not leave the
    machine.
    """
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if not stripped or _SAFE_NAME_RE.match(stripped):
        return value
    return f"<name:{len(stripped)}>"


def scrub_snapshot(node: Any) -> Any:
    """Recursively redact user-authored names in a snapshot tree."""
    if isinstance(node, dict):
        return {
            key: _scrub_name(value) if key in _NAME_KEYS else scrub_snapshot(value)
            for key, value in node.items()
        }
    if isinstance(node, list):
        return [scrub_snapshot(item) for item in node]
    return node


def fetch_snapshot(
    send_command: Callable[..., dict[str, Any]],
    include_notes: bool = True,
    include_params: bool = True,
) -> dict[str, Any] | None:
    """Fetch a session snapshot via the Ableton TCP bridge.

    The result is scrubbed here, at the single point where snapshots enter the
    dataset pipeline, so no caller can accidentally record raw user names.

    Returns None on failure (caller should continue without blocking the action).
    """
    try:
        raw = send_command(
            "get_session_snapshot",
            {
                "include_notes": include_notes,
                "include_params": include_params,
            },
        )
    except Exception as e:
        logger.warning("Failed to fetch session snapshot: %s", e)
        return None
    if raw is None:
        return None
    return scrub_snapshot(raw)


def snapshot_hash(snapshot: dict[str, Any] | None) -> str | None:
    if snapshot is None:
        return None
    return stable_hash(snapshot)
