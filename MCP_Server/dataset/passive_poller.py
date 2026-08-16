"""Background poller: drain Live UI events → Supabase dataset_events."""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any

from .recorder import dataset_enabled, get_recorder
from .snapshot import fetch_snapshot

logger = logging.getLogger("ableton-mcp-dataset")

_DEFAULT_INTERVAL = float(os.environ.get("ABLETON_MCP_PASSIVE_POLL_SEC", "2.0"))
_SNAPSHOT_DEBOUNCE_SEC = float(os.environ.get("ABLETON_MCP_PASSIVE_SNAPSHOT_DEBOUNCE", "1.5"))


class PassiveEventPoller:
    """Poll Remote Script `drain_passive_events` while dataset consent is on."""

    def __init__(self, interval: float = _DEFAULT_INTERVAL):
        self.interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._pending_snapshot = False
        self._last_burst_ts = 0.0

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="passive-poller", daemon=True)
        self._thread.start()
        logger.info("Passive event poller started (interval=%.1fs)", self.interval)

    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive() and not self._stop.is_set())

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=self.interval + 1.0)
        self._thread = None

    def _loop(self) -> None:
        while not self._stop.wait(self.interval):
            if not dataset_enabled():
                continue
            try:
                self._tick()
            except Exception as e:
                logger.debug("Passive poll tick failed: %s", e)

    def _tick(self) -> None:
        from ..script_handshake import script_has_capability
        from ..server import get_ableton_connection

        recorder = get_recorder()
        if recorder is None:
            return

        # Age out edits that nobody undid → implicit "keep"
        try:
            recorder.sweep_implicit_preferences()
        except Exception as e:
            logger.debug("Implicit preference sweep failed: %s", e)

        if not script_has_capability("drain_passive_events"):
            return

        ableton = get_ableton_connection()
        result = ableton.send_command("drain_passive_events")
        events = result.get("events") or []

        if events:
            self._pending_snapshot = True
            self._last_burst_ts = time.time()
            for ev in events:
                recorder.record_passive_event(
                    kind=str(ev.get("type") or "unknown"),
                    detail=ev.get("detail") if isinstance(ev.get("detail"), dict) else {},
                    track_index=ev.get("track_index"),
                    clip_index=ev.get("clip_index"),
                    ts=ev.get("ts"),
                )

        # Debounced post-burst snapshot
        if self._pending_snapshot and (time.time() - self._last_burst_ts) >= _SNAPSHOT_DEBOUNCE_SEC:
            self._pending_snapshot = False
            if not script_has_capability("get_session_snapshot"):
                return
            snapshot = fetch_snapshot(ableton.send_command)
            if snapshot is not None:
                state_hash, _ = recorder.record_state(snapshot)
                logger.debug("Passive burst snapshot hash=%s", state_hash)


_poller: PassiveEventPoller | None = None
_poller_lock = threading.Lock()


def start_passive_poller() -> PassiveEventPoller | None:
    if not dataset_enabled():
        return None
    global _poller
    with _poller_lock:
        if _poller is None:
            _poller = PassiveEventPoller()
            _poller.start()
        return _poller


def poller_is_running() -> bool:
    """True when the passive poller thread is alive and draining Live events."""
    with _poller_lock:
        poller = _poller
    return bool(poller and poller.is_running())


def stop_passive_poller() -> None:
    global _poller
    with _poller_lock:
        if _poller is not None:
            _poller.stop()
            _poller = None
