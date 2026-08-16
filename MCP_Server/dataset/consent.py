"""Persistent consent state for dataset recording.

The env-var opt-in (``ABLETON_MCP_ENABLE_DATASET``) is invisible to anyone who
does not read the docs, so in practice nobody was ever asked. This module lets
the question be asked in the chat itself, once, and remembers the answer.

Three states, and the distinction matters:

    UNKNOWN  — never answered. Recording is ON (opt-out default); the next tool
               call still surfaces the prompt so the user can decline.
    GRANTED  — the user said yes, in their own words. Recording is ON.
    DENIED   — the user said no. Recording is OFF, permanently, and the question
               is never asked again.

Default-on for UNKNOWN makes this opt-out: recording starts without waiting for
an answer, and a user who wants no part of it must actively decline — in the
chat, in the client dialog, or with ``ABLETON_MCP_DISABLE_DATASET``. Note the
consequence: a client that cannot render the prompt, or a user who never reads
it, is recorded without having answered. Dataset rows contain prompts, MIDI, and
device state, so that window is not free — see ``dataset_enabled``.

``ABLETON_MCP_DISABLE_DATASET`` still overrides everything, and the env-var
opt-in still works for headless/CI use where no one can answer a chat prompt.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("ableton-mcp-dataset")

UNKNOWN = "unknown"
GRANTED = "granted"
DENIED = "denied"

# Consent is per-install, not per-project: the same person answering once should
# not be re-asked because they opened a different Live set.
_STATE_DIR = Path(
    os.environ.get("ABLETON_MCP_STATE_DIR", "")
    or (Path.home() / ".ableton-mcp")
)
_STATE_FILE = _STATE_DIR / "consent.json"

_lock = threading.Lock()
_cache: dict[str, Any] | None = None


def _read_state() -> dict[str, Any]:
    """Load persisted consent, tolerating a missing or corrupt file."""
    global _cache
    if _cache is not None:
        return _cache
    try:
        with open(_STATE_FILE, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("consent state is not an object")
        _cache = data
    except FileNotFoundError:
        _cache = {}
    except Exception as e:
        # A damaged file must not wedge the server into a state where it can
        # neither record nor re-ask. Treat it as never-asked.
        logger.debug("Consent state unreadable (%s); treating as unasked", e)
        _cache = {}
    return _cache


def _write_state(state: dict[str, Any]) -> None:
    global _cache
    _cache = state
    try:
        _STATE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = _STATE_FILE.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        os.replace(tmp, _STATE_FILE)
    except Exception as e:
        # Losing the answer means re-asking next session — annoying, not fatal.
        logger.warning("Could not persist dataset consent: %s", e)


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def consent_state() -> str:
    """Return UNKNOWN / GRANTED / DENIED, honouring env overrides.

    The kill switch wins outright. The env opt-in counts as a grant so headless
    and CI setups keep working without anyone to answer a prompt.

    UNKNOWN is reported as-is rather than collapsed into GRANTED: the prompting
    logic needs to tell "never answered" from "said yes" so it knows to still
    ask. Whether UNKNOWN records is a separate question, answered by
    ``recording_allowed``.
    """
    if _env_flag("ABLETON_MCP_DISABLE_DATASET"):
        return DENIED
    if _env_flag("ABLETON_MCP_ENABLE_DATASET"):
        return GRANTED
    with _lock:
        return _read_state().get("state", UNKNOWN)


def recording_allowed() -> bool:
    """True when consent permits recording. Opt-out: UNKNOWN counts as yes.

    Only an explicit DENIED — the user declining in chat or in the client
    dialog, or ``ABLETON_MCP_DISABLE_DATASET`` — stops recording. Never having
    answered does not.
    """
    return consent_state() != DENIED


def record_consent(granted: bool, quote: str | None = None) -> str:
    """Persist the user's answer. ``quote`` is what they actually said.

    Storing the raw phrasing matters: consent relayed through a model is only
    as good as the model's faithfulness, so keep the evidence for later audit.
    """
    state = GRANTED if granted else DENIED
    with _lock:
        payload = dict(_read_state())
        payload.update({
            "state": state,
            "answered_at": time.time(),
            "user_said": (quote or "").strip()[:500] or None,
        })
        _write_state(payload)
    logger.info("Dataset consent recorded: %s", state)
    return state


def needs_prompt() -> bool:
    """True when the user has never been asked."""
    return consent_state() == UNKNOWN


def mark_prompted() -> None:
    """Note that the question has been surfaced, so it is asked once per session."""
    with _lock:
        payload = dict(_read_state())
        payload["last_prompted_at"] = time.time()
        _write_state(payload)


CONSENT_NOTICE = (
    "\n\n---\n"
    "[Ask the user this now, before continuing. Do not answer it yourself, and "
    "do not assume — relay their reply verbatim.]\n\n"
    "**This session is being contributed to the open Ableton MCP training "
    "dataset. Do you want to keep contributing?**\n\n"
    "Recording is on by default. What you make here — your prompts, MIDI "
    "notes, track and clip names, and device settings — is uploaded and may be "
    "published as part of an open dataset used to train music-production "
    "models. Email addresses and file paths are stripped first.\n\n"
    "Reply **no** to stop recording, or **yes** to keep contributing. You will "
    "only be asked once; you can change your mind later by saying so.\n"
    "---"
)


ELICIT_MESSAGE = (
    "This session is being contributed to the open Ableton MCP training "
    "dataset. Keep contributing?\n\n"
    "Recording is on by default. What you make here — your prompts, MIDI "
    "notes, track and clip names, and device settings — is uploaded and may be "
    "published as part of an open dataset used to train music-production "
    "models. Email addresses and file paths are stripped first.\n\n"
    "Decline to stop recording. You are asked once, and can change your mind "
    "later."
)


async def try_elicit_consent(ctx: Any) -> str | None:
    """Ask for consent via a real client dialog. Returns a state, or None.

    Preferred over the text prompt because the *client* renders it and the user
    answers directly — the model cannot fabricate an answer it never received.

    Returns None when elicitation is unavailable (older mcp, or a client that
    does not implement it), which means the caller should fall back to
    appending the text notice. A user who cancels or declines the dialog is a
    real answer, not a fallback.
    """
    if ctx is None or not needs_prompt():
        return None
    try:
        from pydantic import BaseModel, Field

        class DatasetConsent(BaseModel):
            contribute: bool = Field(
                description=(
                    "Yes, contribute my sessions to the open dataset"
                ),
            )

        result = await ctx.elicit(message=ELICIT_MESSAGE, schema=DatasetConsent)
    except Exception as e:
        # Unsupported client, older mcp, or transport error — text fallback
        logger.debug("Elicitation unavailable (%s); falling back to text", e)
        return None

    action = getattr(result, "action", None)
    if action == "accept":
        data = getattr(result, "data", None)
        agreed = bool(getattr(data, "contribute", False))
        return record_consent(agreed, quote="(via client dialog)")
    if action == "decline":
        return record_consent(False, quote="(declined in client dialog)")
    # "cancel" — dismissed without answering. Left UNKNOWN so the question can
    # be asked again in a later session. Under the opt-out default this means
    # recording continues in the meantime: only an explicit no stops it.
    logger.debug("Consent dialog dismissed without an answer — recording continues")
    mark_prompted()
    return UNKNOWN


def maybe_consent_notice() -> str:
    """Return the consent question to append to a tool result, or "".

    Empty once the user has answered, or if they were already asked this
    session — the prompt should read as a question, not a nag.
    """
    if not needs_prompt():
        return ""
    with _lock:
        last = _read_state().get("last_prompted_at") or 0
    # Re-ask on a later session if it went unanswered, but never twice in a row
    if time.time() - last < 3600:
        return ""
    mark_prompted()
    return CONSENT_NOTICE


def reset_for_tests() -> None:
    global _cache
    with _lock:
        _cache = None
