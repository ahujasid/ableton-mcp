"""Persistent consent state for dataset recording.

The env-var opt-in (``ABLETON_MCP_ENABLE_DATASET``) is invisible to anyone who
does not read the docs, so in practice nobody was ever asked. This module lets
the question be asked in the chat itself, once, and remembers the answer.

Three states, and the distinction matters:

    UNKNOWN  — never answered. Recording is OFF; the next tool call surfaces the
               prompt so the user can opt in.
    GRANTED  — the user said yes, in their own words. Recording is ON.
    DENIED   — the user said no. Recording is OFF, permanently, and the question
               is never asked again.

Default-off for UNKNOWN makes this opt-in: nothing is recorded until the user
actively says yes — in the chat, in the client dialog, or with
``ABLETON_MCP_ENABLE_DATASET``. A client that cannot render the prompt, or a
user who never reads it, contributes nothing. Dataset rows contain prompts,
MIDI, and device state, so silence is treated as no.

``ABLETON_MCP_DISABLE_DATASET`` still overrides everything, and the env-var
opt-in works for headless/CI use where no one can answer a chat prompt.
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

# Bump ONLY when what gets collected materially changes — a new category of
# data, not a reworded prompt. A bump re-opens the question for people who
# already granted, because they consented to the older, narrower scope and
# cannot be assumed to accept the new one.
#
# A bump deliberately does NOT re-ask anyone who said no. Re-prompting a denial
# with the same question is nagging; the only honest reason to return to a
# declined user is to tell them the scope changed, and that is a different
# message than this one. Until that message exists, DENIED is final.
CONSENT_VERSION = 1

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

    UNKNOWN is reported as-is rather than collapsed into DENIED: the prompting
    logic needs to tell "never answered" from "said no" so it knows to still
    ask. Whether UNKNOWN records is a separate question, answered by
    ``recording_allowed``.
    """
    if _env_flag("ABLETON_MCP_DISABLE_DATASET"):
        return DENIED
    if _env_flag("ABLETON_MCP_ENABLE_DATASET"):
        return GRANTED
    with _lock:
        state = _read_state()
        answer = state.get("state", UNKNOWN)
        if answer != GRANTED:
            return answer
        # A grant is only valid for the scope it was given under. If collection
        # has widened since, fall back to UNKNOWN: recording stops and the
        # question is asked again. A stale grant must never authorise data the
        # user was never told about.
        #
        # A grant written before this field existed is treated as version 1,
        # not as invalid. Those users were asked about, and agreed to, exactly
        # the scope version 1 describes — the field's absence is our bookkeeping
        # gap, not a gap in their consent, and re-asking them would be nagging.
        stored = state.get("consent_version", 1)
        if not isinstance(stored, int) or stored < CONSENT_VERSION:
            return UNKNOWN
        return GRANTED


def recording_allowed() -> bool:
    """True when consent permits recording. Opt-in: only GRANTED counts as yes.

    An explicit grant — the user agreeing in chat or in the client dialog, or
    ``ABLETON_MCP_ENABLE_DATASET`` — is required. Never having answered means
    no recording, so an unanswered or unrenderable prompt contributes nothing.
    """
    return consent_state() == GRANTED


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
            # Pin the answer to the scope it was given under, so a later
            # widening of what is collected re-opens the question.
            "consent_version": CONSENT_VERSION,
            # A fresh answer clears the ask-throttle. It is only there to stop
            # an unanswered prompt repeating within a session, and this is an
            # answer.
            "last_prompted_at": None,
        })
        _write_state(payload)
    logger.info("Dataset consent recorded: %s (v%d)", state, CONSENT_VERSION)
    return state


def needs_prompt() -> bool:
    """True when the question is open — never answered, or answered under an
    older collection scope that has since widened."""
    return consent_state() == UNKNOWN


# How long to stay quiet after surfacing the question without getting an
# answer. Long enough that a dismissed prompt does not reappear on the user's
# very next action, short enough that a later session gets another chance.
_ASK_COOLDOWN_SEC = 3600


def may_ask_now() -> bool:
    """True when the question is open AND we have not just asked.

    Both the client dialog and the text notice go through this. They used to
    disagree — only the text path checked the cooldown — so dismissing the
    dialog re-opened it on the very next tool call. Asking again immediately
    after someone closed the box is nagging, and it pressures an answer that
    should be freely given.
    """
    if not needs_prompt():
        return False
    with _lock:
        last = _read_state().get("last_prompted_at") or 0
    return (time.time() - last) >= _ASK_COOLDOWN_SEC


def mark_prompted() -> None:
    """Note that the question has been surfaced, so it is not asked again for a while."""
    with _lock:
        payload = dict(_read_state())
        payload["last_prompted_at"] = time.time()
        # Tie the throttle to the current scope, so a version bump is not
        # silently muted for an hour by a timestamp from the previous one.
        payload["prompted_version"] = CONSENT_VERSION
        _write_state(payload)


def _unmark_prompted(previous: float | None) -> None:
    """Restore the cooldown after an ask that never actually reached the user."""
    with _lock:
        payload = dict(_read_state())
        payload["last_prompted_at"] = previous
        _write_state(payload)


CONSENT_NOTICE = (
    "\n\n---\n"
    "[Ask the user this now, before continuing. Do not answer it yourself, and "
    "do not assume — relay their reply verbatim.]\n\n"
    "**Would you like to contribute this session to the open Ableton MCP "
    "training dataset?**\n\n"
    "Recording is off unless you say yes. If you opt in, what you make here — "
    "your prompts, MIDI notes, track and clip names, and device settings — is "
    "uploaded and may be published as part of an open dataset used to train "
    "music-production models. Email addresses and file paths are stripped "
    "first.\n\n"
    "Reply **yes** to contribute, or **no** to decline. Nothing is recorded "
    "unless you say yes. You will only be asked once; you can change your mind "
    "later by saying so.\n"
    "---"
)


ELICIT_MESSAGE = (
    "Contribute this session to the open Ableton MCP training dataset?\n\n"
    "Recording is off unless you opt in. If you accept, what you make here — "
    "your prompts, MIDI notes, track and clip names, and device settings — is "
    "uploaded and may be published as part of an open dataset used to train "
    "music-production models. Email addresses and file paths are stripped "
    "first.\n\n"
    "Decline and nothing is recorded. You are asked once, and can change your "
    "mind later."
)


async def try_elicit_consent(ctx: Any) -> str | None:
    """Ask for consent via a real client dialog. Returns a state, or None.

    Preferred over the text prompt because the *client* renders it and the user
    answers directly — the model cannot fabricate an answer it never received.

    Returns None when elicitation is unavailable (older mcp, or a client that
    does not implement it), which means the caller should fall back to
    appending the text notice. A user who cancels or declines the dialog is a
    real answer, not a fallback.

    The three MCP actions are not interchangeable:

        accept + contribute=True   → GRANTED. The only path that starts recording.
        accept + contribute=False  → DENIED. They engaged and said no; stop asking.
        decline                    → DENIED. Same, via the client's own no button.
        cancel                     → UNKNOWN. Dismissed without deciding, so the
                                     question survives to a later session.

    That last distinction is the point: a dismissed dialog is not a no, and
    collapsing it into one would either lose the chance to ask or nag someone
    who already answered.
    """
    if ctx is None or not may_ask_now():
        return None
    # Stamp before awaiting, not after. The dialog is open for as long as the
    # user ignores it, and other tool calls keep arriving in the meantime; if
    # the cooldown were only recorded on the way out, each of those would see a
    # stale timestamp and open a dialog of its own.
    with _lock:
        previous = _read_state().get("last_prompted_at")
    mark_prompted()
    try:
        from pydantic import BaseModel, Field

        class DatasetConsent(BaseModel):
            # default=False is load-bearing: the box must render unchecked, so
            # an accept with an untouched form is a no rather than a silent yes.
            contribute: bool = Field(
                default=False,
                title="Contribute my sessions to the open dataset",
                description=(
                    "Uploads your prompts, MIDI, track and clip names, and "
                    "device settings. Leave unchecked to keep them private. "
                    "You can change this later by saying so in the chat."
                ),
            )

        result = await ctx.elicit(message=ELICIT_MESSAGE, schema=DatasetConsent)
    except Exception as e:
        # Unsupported client, older mcp, or transport error — text fallback.
        # Undo the cooldown stamped above: nothing was ever shown, and leaving
        # it would suppress the text notice too, which on these clients is the
        # only way the question ever reaches the user.
        _unmark_prompted(previous)
        logger.debug("Elicitation unavailable (%s); falling back to text", e)
        return None

    action = getattr(result, "action", None)
    if action == "accept":
        data = getattr(result, "data", None)
        agreed = bool(getattr(data, "contribute", False))
        return record_consent(
            agreed,
            quote=(
                "(accepted in client dialog)" if agreed
                else "(client dialog submitted without opting in)"
            ),
        )
    if action == "decline":
        return record_consent(False, quote="(declined in client dialog)")
    # "cancel" — dismissed without answering. Left UNKNOWN so the question can
    # be asked again in a later session (the cooldown was already stamped
    # above, so not on the user's next keystroke). Under the opt-in default
    # nothing is recorded in the meantime: only an explicit yes starts it.
    logger.debug("Consent dialog dismissed without an answer — recording stays off")
    return UNKNOWN


def maybe_consent_notice() -> str:
    """Return the consent question to append to a tool result, or "".

    Empty once the user has answered, or if they were asked recently — the
    prompt should read as a question, not a nag.
    """
    # studio-upgrades fork: never interrupt tool results with the dataset
    # question unless explicitly enabled. Recording stays off (opt-in).
    if os.environ.get("ABLETON_MCP_ASK_DATASET_CONSENT", "").lower() not in ("1", "true", "yes", "on"):
        return ""
    if not may_ask_now():
        return ""
    mark_prompted()
    return CONSENT_NOTICE


def reset_for_tests() -> None:
    global _cache
    with _lock:
        _cache = None
