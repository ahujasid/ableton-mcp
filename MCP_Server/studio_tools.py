"""Studio tools for the ``studio-upgrades`` fork.

Registered on the shared FastMCP instance from ``server.py``:

* devices by name on any track, return or the master; several parameters at
  once in display units ("1.2 kHz", "-6 dB"); compressor sidechain routing
* clip automation envelopes
* groove pool, clip properties (pitch / warp / gain / loop), song scale
* track management (returns, delete, duplicate) and a mixer overview
* "ears": real-time resample renders measured by ``MCP_Server.ears`` and
  compared against reference tracks
* MIDI review, masking forecast and note transforms via ``midi_tools``
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import Context

logger = logging.getLogger("AbletonMCPServer")

RENDER_DIR = Path(os.environ.get("ABLETON_MCP_RENDER_DIR",
                                 str(Path.home() / ".ableton-mcp" / "renders")))
MAX_TOOL_WAIT_S = float(os.environ.get("ABLETON_MCP_MAX_TOOL_WAIT", "50"))

# label -> {"path", "report", "source"}; "last" always points at the newest render
_AUDIO_REPORTS: Dict[str, Dict[str, Any]] = {}


def _server():
    from . import server
    return server


def _send(capability: str, command: str, params: Dict[str, Any]):
    """Capability-gated send. Returns (result, None) or (None, message)."""
    return _server()._fork_command(capability, command, params)


def _err(action: str, e: Exception) -> str:
    logger.error(f"Error {action}: {e}")
    return f"Error {action}: {e}"


def _dump(obj: Any) -> str:
    return json.dumps(obj, indent=2, default=str)


# ── timing helpers ───────────────────────────────────────────────────────────

def _beats_per_bar() -> float:
    try:
        info = _server().get_ableton_connection().send_command("get_session_info", {})
        num = float(info.get("signature_numerator", 4) or 4)
        den = float(info.get("signature_denominator", 4) or 4)
        return num * 4.0 / den
    except Exception:
        return 4.0


def _bar_to_beat(bar: float, beats_per_bar: float) -> float:
    return (float(bar) - 1.0) * beats_per_bar


# ── audio report store ───────────────────────────────────────────────────────

def _safe_label(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", text or "").strip("-")
    return cleaned[:60] or "render"


def _register_report(label: str, path: str, report: Dict[str, Any], source: str) -> None:
    entry = {"path": path, "report": report, "source": source, "label": label}
    _AUDIO_REPORTS[label] = entry
    if source == "render":
        _AUDIO_REPORTS["last"] = entry


def _resolve_report(ref: str):
    """(report, readable name) for a label ("last", "drop-v2", "ref-four") or a file path."""
    ref = (ref or "last").strip()
    if ref in _AUDIO_REPORTS:
        entry = _AUDIO_REPORTS[ref]
        return entry["report"], entry.get("label") or ref
    if os.path.exists(ref):
        from . import ears
        return ears.analyze(ref), Path(ref).stem
    known = ", ".join(sorted(_AUDIO_REPORTS)) or "none yet"
    raise ValueError(f"No audio report or file called '{ref}'. Known labels: {known}")


def _compact_report(report: Dict[str, Any]) -> Dict[str, Any]:
    """Drop bulky fields (raw chroma, onset lists) for the tool reply."""
    out = dict(report)
    tonal = dict(out.get("tonal") or {})
    tonal.pop("chroma", None)
    tonal.pop("chroma_notes", None)
    if tonal:
        out["tonal"] = tonal
    return out


def _wait_file_stable(path: str, timeout: float = 15.0) -> None:
    deadline = time.time() + timeout
    last = -1
    while time.time() < deadline:
        try:
            size = os.path.getsize(path)
        except OSError:
            size = -1
        if size > 0 and size == last:
            return
        last = size
        time.sleep(0.4)
    if last <= 0:
        raise RuntimeError(f"Rendered file never appeared or stayed empty: {path}")


_RENDER_RUNNING = ("preparing", "positioning", "recording", "finalizing")


def _wait_for_render(job_id: str, max_wait: float) -> Dict[str, Any]:
    conn = _server().get_ableton_connection()
    deadline = time.time() + max_wait
    status: Dict[str, Any] = {}
    while True:
        status = conn.send_command("get_render_status", {"job_id": job_id})
        if status.get("state") not in _RENDER_RUNNING:
            return status
        if time.time() >= deadline:
            return status
        time.sleep(0.5)


def _finish_render(status: Dict[str, Any], label: str) -> Dict[str, Any]:
    from . import ears

    src = status["file_path"]
    _wait_file_stable(src)
    RENDER_DIR.mkdir(parents=True, exist_ok=True)
    dest = RENDER_DIR / f"{_safe_label(label)}-{status['id']}{Path(src).suffix or '.wav'}"
    shutil.copy2(src, dest)
    start = float(status.get("window_offset_s", 0.0))
    length = float(status.get("window_seconds", 0.0)) or None
    report = ears.analyze(
        str(dest),
        start_s=start,
        end_s=(start + length) if length else None,
        bpm=status.get("tempo"),
        beat_offset_s=0.0,
    )
    report["render"] = {
        "label": label,
        "bars": f"beats {status.get('start_beat')}–{status.get('end_beat')}",
        "solo_tracks": status.get("solo_tracks") or [],
        "file": str(dest),
    }
    _register_report(label, str(dest), report, "render")
    return report


def _render_reply(status: Dict[str, Any], label: str) -> str:
    state = status.get("state")
    if state == "done":
        report = _finish_render(status, label)
        return _dump(_compact_report(report))
    if state in _RENDER_RUNNING:
        return (f"Render '{label}' is still {state} (job {status.get('id')}, "
                f"~{status.get('expected_seconds')} s of audio). "
                f"Call get_render_result with job_id='{status.get('id')}' and label='{label}'.")
    return f"Render failed: {status.get('error') or status}"


# ── registration ─────────────────────────────────────────────────────────────

def register(mcp, rich_telemetry_tool) -> None:  # noqa: C901 - flat list of tools

    # ── devices ──────────────────────────────────────────────────────────────

    @mcp.tool()
    @rich_telemetry_tool("add_device")
    def add_device(ctx: Context, track_index: int, name: str, track_type: str = "track",
                   position: Optional[int] = None, user_prompt: str = "") -> str:
        """
        Add a Live device by name, e.g. "EQ Eight", "Compressor", "Glue Compressor",
        "Saturator", "Reverb", "Echo", "Utility", "Auto Filter", "Drum Buss", "Roar",
        "Limiter". Works on tracks, return tracks and the master.

        Parameters:
        - track_index: Track index (or return index when track_type="return"; ignored for "master")
        - name: Device name as shown in Live's browser
        - track_type: "track" (default), "return" or "master"
        - position: Optional index in the device chain (default: end)
        """
        try:
            params = {"track_index": track_index, "track_type": track_type, "name": name}
            if position is not None:
                params["position"] = position
            result, missing = _send("add_device", "add_device", params)
            if missing:
                return missing
            chain = " → ".join(d["name"] for d in result.get("devices", []))
            note = ("; " + "; ".join(result["notes"])) if result.get("notes") else ""
            return f"Added {name} to '{result.get('track_name')}' via {result.get('method')}. Chain: {chain}{note}"
        except Exception as e:
            return _err("adding device", e)

    @mcp.tool()
    @rich_telemetry_tool("delete_device")
    def delete_device(ctx: Context, track_index: int, device_index: int,
                      track_type: str = "track", user_prompt: str = "") -> str:
        """
        Remove a device from a track, return track or the master.

        Parameters:
        - track_index / track_type: Which track ("track", "return", "master")
        - device_index: Position in the device chain
        """
        try:
            result, missing = _send("delete_device", "delete_device", {
                "track_index": track_index, "track_type": track_type,
                "device_index": device_index})
            if missing:
                return missing
            chain = " → ".join(d["name"] for d in result.get("devices", [])) or "(empty)"
            return f"Deleted {result.get('deleted')} from '{result.get('track_name')}'. Chain: {chain}"
        except Exception as e:
            return _err("deleting device", e)

    @mcp.tool()
    @rich_telemetry_tool("set_device_parameters")
    def set_device_parameters(ctx: Context, track_index: int, device_index: int,
                              changes: List[Dict[str, Any]], track_type: str = "track",
                              user_prompt: str = "") -> str:
        """
        Set several parameters of one device in one call, by name, in the units
        Live displays. Prefer this over set_device_parameter.

        Parameters:
        - track_index / track_type: Which track ("track", "return", "master")
        - device_index: Position in the device chain
        - changes: list of {"name": "Frequency", "display": "1.2 kHz"} or
          {"name": "Dry/Wet", "display": "25 %"} or {"name": "Threshold", "display": "-18 dB"}
          or {"name": "Filter Type", "display": "Lowpass"} or {"index": 3, "value": 0.5}
          or {"name": "Drive", "normalized": 0.3}
        """
        try:
            result, missing = _send("set_device_parameters", "set_device_parameters", {
                "track_index": track_index, "track_type": track_type,
                "device_index": device_index, "changes": changes})
            if missing:
                return missing
            parts = [f"{r['name']} = {r['display']}" for r in result.get("set", [])]
            return f"{result.get('device_name')} on '{result.get('track_name')}': " + ", ".join(parts)
        except Exception as e:
            return _err("setting device parameters", e)

    @mcp.tool()
    @rich_telemetry_tool("set_sidechain")
    def set_sidechain(ctx: Context, track_index: int, device_index: int,
                      source_track_index: Optional[int] = None,
                      source_track_name: str = "", tap: str = "post fx",
                      enable: bool = True, track_type: str = "track",
                      user_prompt: str = "") -> str:
        """
        Feed a compressor's sidechain from another track (e.g. duck the bass with
        the kick) and switch sidechain on. Works with Live's Compressor.

        Parameters:
        - track_index / device_index / track_type: The compressor
        - source_track_index or source_track_name: The trigger track (e.g. the kick)
        - tap: "pre fx", "post fx" (default) or "post mixer"
        - enable: Turn the sidechain switch on
        """
        try:
            params = {"track_index": track_index, "device_index": device_index,
                      "track_type": track_type, "tap": tap, "enable": enable}
            if source_track_index is not None:
                params["source_track_index"] = source_track_index
            if source_track_name:
                params["source_track_name"] = source_track_name
            result, missing = _send("set_sidechain", "set_sidechain", params)
            if missing:
                return missing
            return (f"{result.get('device_name')} on '{result.get('track_name')}' now keyed from "
                    f"{result.get('source')} ({result.get('channel') or 'default tap'})"
                    + ("" if result.get("enabled_parameter") else
                       " — couldn't find the sidechain switch; turn S/C on by hand"))
        except Exception as e:
            return _err("setting sidechain", e)

    # ── automation ───────────────────────────────────────────────────────────

    @mcp.tool()
    @rich_telemetry_tool("write_clip_automation")
    def write_clip_automation(ctx: Context, track_index: int, clip_index: int,
                              target: Dict[str, Any], points: List[Dict[str, Any]],
                              curve: str = "linear", resolution: float = 0.0625,
                              clear_existing: bool = True, user_prompt: str = "") -> str:
        """
        Draw an automation envelope inside a Session clip: filter sweeps, volume
        rides, send throws, pan moves. The envelope travels with the clip when it
        is placed in the Arrangement. Arrangement clips can't be written, so put
        section-long moves in a section-long Session clip.

        Parameters:
        - target: {"device_index": 1, "parameter_name": "Frequency"} or
          {"device_index": 1, "parameter_index": 4} or {"mixer": "volume"} or
          {"mixer": "panning"} or {"mixer": "send", "send_index": 0}
        - points: breakpoints in clip beats, each with "value" (raw), "display"
          ("800 Hz", "-12 dB", "40 %") or "normalized" (0-1), e.g.
          [{"time": 0, "display": "300 Hz"}, {"time": 28, "display": "8 kHz"}, {"time": 32, "display": "300 Hz"}]
        - curve: "linear", "ease_in", "ease_out", "s_curve", "exp" or "step"
        - resolution: ramp step size in beats (default 1/64 note = 0.0625)
        - clear_existing: replace the parameter's existing envelope in this clip
        """
        try:
            result, missing = _send("write_clip_automation", "write_clip_automation", {
                "track_index": track_index, "clip_index": clip_index, "target": target,
                "points": points, "curve": curve, "resolution": resolution,
                "clear_existing": clear_existing})
            if missing:
                return missing
            return (f"Automated {result.get('parameter')} in '{result.get('clip_name')}': "
                    f"{result.get('first_display')} → {result.get('last_display')} "
                    f"over beats {result.get('start')}–{result.get('end')} "
                    f"({result.get('steps')} steps)")
        except Exception as e:
            return _err("writing automation", e)

    @mcp.tool()
    @rich_telemetry_tool("clear_clip_automation")
    def clear_clip_automation(ctx: Context, track_index: int, clip_index: int,
                              target: Optional[Dict[str, Any]] = None,
                              user_prompt: str = "") -> str:
        """
        Clear one envelope (pass target, same format as write_clip_automation) or
        every envelope in a Session clip (omit target).
        """
        try:
            params = {"track_index": track_index, "clip_index": clip_index}
            if target:
                params["target"] = target
            result, missing = _send("clear_clip_automation", "clear_clip_automation", params)
            if missing:
                return missing
            return f"Cleared {result.get('cleared')} automation in '{result.get('clip_name')}'"
        except Exception as e:
            return _err("clearing automation", e)

    @mcp.tool()
    @rich_telemetry_tool("get_clip_automation")
    def get_clip_automation(ctx: Context, track_index: int, clip_index: int,
                            target: Dict[str, Any], resolution: float = 1.0,
                            user_prompt: str = "") -> str:
        """
        Read back an envelope as sampled values (to verify a write).

        Parameters:
        - target: Same format as write_clip_automation
        - resolution: Sample spacing in beats
        """
        try:
            result, missing = _send("get_clip_automation", "get_clip_automation", {
                "track_index": track_index, "clip_index": clip_index,
                "target": target, "resolution": resolution})
            if missing:
                return missing
            return _dump(result)
        except Exception as e:
            return _err("reading automation", e)

    # ── groove ───────────────────────────────────────────────────────────────

    @mcp.tool()
    @rich_telemetry_tool("get_groove_pool")
    def get_groove_pool(ctx: Context, user_prompt: str = "") -> str:
        """List the grooves in the set's Groove Pool and the global groove amount."""
        try:
            result, missing = _send("get_groove_pool", "get_groove_pool", {})
            if missing:
                return missing
            return _dump(result)
        except Exception as e:
            return _err("reading groove pool", e)

    @mcp.tool()
    @rich_telemetry_tool("load_groove")
    def load_groove(ctx: Context, name: str, track_index: Optional[int] = None,
                    clip_index: Optional[int] = None, user_prompt: str = "") -> str:
        """
        Load a groove from Live's library into the Groove Pool by name (reused if
        it's already there) and optionally apply it to a Session clip. Live 11+
        swing grooves live in Core Library > Grooves > Swing, e.g.
        "Swing MPC 3000 16ths 54" (also 57, 61, 64, 68, 71, 74) and
        "Swing 16ths 54" (Basic: 52, 54, 57, 59, 61, 64, 66, ...). For exact
        values such as 56 or 58 %, use transform_clip_notes swing instead.

        Parameters:
        - name: Groove name without the .agr extension
        - track_index / clip_index: Optional clip to apply it to
        """
        try:
            params = {"name": name}
            if track_index is not None and clip_index is not None:
                params.update({"track_index": track_index, "clip_index": clip_index})
            result, missing = _send("load_groove", "load_groove", params)
            if missing:
                return missing
            applied = f", applied to clip ({result['applied_to_clip']})" if result.get("applied_to_clip") else ""
            return f"Loaded {result.get('loaded')} into the Groove Pool (index {result.get('groove_index')}){applied}"
        except Exception as e:
            return _err("loading groove", e)

    @mcp.tool()
    @rich_telemetry_tool("set_groove")
    def set_groove(ctx: Context, groove_index: int, timing: Optional[float] = None,
                   random: Optional[float] = None, velocity: Optional[float] = None,
                   quantize: Optional[float] = None, base: Optional[str] = None,
                   user_prompt: str = "") -> str:
        """
        Adjust a groove in the pool. Amounts are 0-1 (Live shows 0-100 %).

        Parameters:
        - timing: How far notes move toward the groove's timing
        - random: Random timing amount (keep at 0 for tight dance music)
        - velocity: How much the groove's accents shape velocity
        - quantize: Pre-quantise before applying
        - base: "1/4", "1/8", "1/8T", "1/16", "1/16T" or "1/32"
        """
        try:
            params = {"groove_index": groove_index}
            for k, v in (("timing", timing), ("random", random), ("velocity", velocity),
                         ("quantize", quantize), ("base", base)):
                if v is not None:
                    params[k] = v
            result, missing = _send("set_groove", "set_groove", params)
            if missing:
                return missing
            return _dump(result)
        except Exception as e:
            return _err("setting groove", e)

    @mcp.tool()
    @rich_telemetry_tool("assign_groove")
    def assign_groove(ctx: Context, track_index: int, clip_index: int,
                      groove_index: Optional[int] = None, user_prompt: str = "") -> str:
        """
        Apply a Groove Pool groove to a Session clip (omit groove_index to remove it).
        """
        try:
            params = {"track_index": track_index, "clip_index": clip_index}
            if groove_index is not None:
                params["groove_index"] = groove_index
            result, missing = _send("assign_groove", "assign_groove", params)
            if missing:
                return missing
            return f"'{result.get('clip_name')}' groove: {result.get('groove') or 'none'}"
        except Exception as e:
            return _err("assigning groove", e)

    @mcp.tool()
    @rich_telemetry_tool("set_groove_amount")
    def set_groove_amount(ctx: Context, amount: float, user_prompt: str = "") -> str:
        """Set the global groove amount (0-1.3; 1.0 = 100 %)."""
        try:
            result, missing = _send("set_groove_amount", "set_groove_amount", {"amount": amount})
            if missing:
                return missing
            return f"Global groove amount: {round(result.get('global_amount', 0) * 100)} %"
        except Exception as e:
            return _err("setting groove amount", e)

    # ── clips, scale, tracks ─────────────────────────────────────────────────

    @mcp.tool()
    @rich_telemetry_tool("set_clip_properties")
    def set_clip_properties(ctx: Context, track_index: int, clip_index: int,
                            properties: Dict[str, Any], arrangement: bool = False,
                            user_prompt: str = "") -> str:
        """
        Change clip properties.

        Audio clips: pitch_coarse (semitones), pitch_fine (cents), gain (0-1),
        warping (bool), warp_mode ("beats", "tones", "texture", "re-pitch",
        "complex", "complex pro").
        Any clip: looping, loop_start, loop_end, start_marker, end_marker (beats),
        muted, name.

        Parameters:
        - arrangement: True to address the Nth Arrangement clip of the track instead of a Session slot
        """
        try:
            result, missing = _send("set_clip_properties", "set_clip_properties", {
                "track_index": track_index, "clip_index": clip_index,
                "properties": properties, "arrangement": arrangement})
            if missing:
                return missing
            return _dump(result)
        except Exception as e:
            return _err("setting clip properties", e)

    @mcp.tool()
    @rich_telemetry_tool("get_song_scale")
    def get_song_scale(ctx: Context, user_prompt: str = "") -> str:
        """Read the set's root note and scale (Live 12 Scale Mode)."""
        try:
            result, missing = _send("get_song_scale", "get_song_scale", {})
            if missing:
                return missing
            return _dump(result)
        except Exception as e:
            return _err("reading scale", e)

    @mcp.tool()
    @rich_telemetry_tool("set_song_scale")
    def set_song_scale(ctx: Context, root_note: Optional[str] = None,
                       scale_name: Optional[str] = None,
                       scale_mode: Optional[bool] = None, user_prompt: str = "") -> str:
        """
        Set the set's root and scale (Live 12), which scale-aware devices and MIDI
        tools follow. Scale names as Live shows them, e.g. "Minor", "Dorian",
        "Phrygian", "Phrygian Dominant", "Harmonic Minor", "Mixolydian".

        Parameters:
        - root_note: "A", "C#", ... (sharps)
        - scale_name: Live's scale name
        - scale_mode: Turn Scale Mode on/off
        """
        try:
            params = {}
            if root_note is not None:
                params["root_note"] = root_note
            if scale_name is not None:
                params["scale_name"] = scale_name
            if scale_mode is not None:
                params["scale_mode"] = scale_mode
            result, missing = _send("set_song_scale", "set_song_scale", params)
            if missing:
                return missing
            return f"Scale: {result.get('root_name')} {result.get('scale_name')} (scale mode {'on' if result.get('scale_mode') else 'off'})"
        except Exception as e:
            return _err("setting scale", e)

    @mcp.tool()
    @rich_telemetry_tool("create_return_track")
    def create_return_track(ctx: Context, name: str = "", user_prompt: str = "") -> str:
        """Create a return track (then add_device with track_type="return")."""
        try:
            result, missing = _send("create_return_track", "create_return_track", {"name": name})
            if missing:
                return missing
            return f"Created return {result.get('return_index')} '{result.get('name')}'"
        except Exception as e:
            return _err("creating return track", e)

    @mcp.tool()
    @rich_telemetry_tool("delete_track")
    def delete_track(ctx: Context, track_index: int, track_type: str = "track",
                     user_prompt: str = "") -> str:
        """Delete a track or return track. Indices of later tracks shift down."""
        try:
            result, missing = _send("delete_track", "delete_track", {
                "track_index": track_index, "track_type": track_type})
            if missing:
                return missing
            return f"Deleted {result.get('track_type')} '{result.get('deleted')}'"
        except Exception as e:
            return _err("deleting track", e)

    @mcp.tool()
    @rich_telemetry_tool("duplicate_track")
    def duplicate_track(ctx: Context, track_index: int, name: str = "",
                        user_prompt: str = "") -> str:
        """Duplicate a track (devices, clips, mixer). The copy lands right after it."""
        try:
            result, missing = _send("duplicate_track", "duplicate_track", {
                "track_index": track_index, "name": name})
            if missing:
                return missing
            return f"Duplicated '{result.get('source')}' to index {result.get('new_index')} '{result.get('name')}'"
        except Exception as e:
            return _err("duplicating track", e)

    @mcp.tool()
    @rich_telemetry_tool("get_mixer_overview")
    def get_mixer_overview(ctx: Context, user_prompt: str = "") -> str:
        """Every track, return and the master: device chain, volume (dB), pan, sends, mute, solo."""
        try:
            result, missing = _send("get_mixer_overview", "get_mixer_overview", {})
            if missing:
                return missing
            return _dump(result)
        except Exception as e:
            return _err("reading mixer", e)

    # ── ears ─────────────────────────────────────────────────────────────────

    @mcp.tool()
    @rich_telemetry_tool("render_section")
    def render_section(ctx: Context, start_bar: float, bars: float = 8, label: str = "",
                       solo_tracks: Optional[List[int]] = None, preroll_beats: float = 4.0,
                       user_prompt: str = "") -> str:
        """
        Render part of the Arrangement and measure it: Claude's ears.

        Records the master in real time (Resampling onto a muted "MCP Render"
        track), then reports integrated loudness (LUFS), true peak, loudness
        range, crest factor, spectral balance by band and octave, stereo width
        and low-end mono compatibility, measured swing and kick timing, the most
        likely key and chords per bar, plus plain-English warnings. The user's
        loop, metronome, arm and solo states are restored afterwards.

        Takes as long as the music (8 bars at 125 BPM ≈ 15 s plus preroll). Keep
        renders to 16 bars or less so they finish within one call; longer ones
        return a job id for get_render_result.

        Parameters:
        - start_bar: First bar (1-based)
        - bars: How many bars to measure
        - label: Name for this render, to compare later (e.g. "drop-v1")
        - solo_tracks: Optional track indices to solo for a stem render (e.g. kick + bass)
        - preroll_beats: Beats recorded before the window so reverbs and delays are already sounding
        """
        try:
            bpb = _beats_per_bar()
            start_beat = _bar_to_beat(start_bar, bpb)
            end_beat = start_beat + float(bars) * bpb
            label = label or f"bar{int(start_bar)}x{int(bars)}"
            params = {"start_beat": start_beat, "end_beat": end_beat,
                      "preroll_beats": preroll_beats}
            if solo_tracks:
                params["solo_tracks"] = list(solo_tracks)
            job, missing = _send("start_render", "start_render", params)
            if missing:
                return missing
            status = _wait_for_render(job["id"], min(MAX_TOOL_WAIT_S, float(job.get("expected_seconds", 30)) + 20))
            return _render_reply(status, label)
        except Exception as e:
            return _err("rendering", e)

    @mcp.tool()
    @rich_telemetry_tool("get_render_result")
    def get_render_result(ctx: Context, job_id: str = "", label: str = "",
                          user_prompt: str = "") -> str:
        """
        Wait for (up to ~50 s) and return the measurement of a render that was
        still running when render_section returned.
        """
        try:
            status = _wait_for_render(job_id, MAX_TOOL_WAIT_S)
            return _render_reply(status, label or f"render-{status.get('id', '')}")
        except Exception as e:
            return _err("reading render", e)

    @mcp.tool()
    @rich_telemetry_tool("analyze_audio_file")
    def analyze_audio_file(ctx: Context, path: str, label: str = "",
                           start_seconds: Optional[float] = None,
                           end_seconds: Optional[float] = None,
                           bpm: Optional[float] = None,
                           downbeat_seconds: float = 0.0, user_prompt: str = "") -> str:
        """
        Measure an audio file on this computer: a reference track, a Suno stem,
        a bounce. Same report as render_section. Give it a label to compare against.

        Parameters:
        - path: WAV/AIFF/FLAC file path on the user's computer
        - label: Name for comparisons (e.g. "ref-four")
        - start_seconds / end_seconds: Optional window (e.g. the reference's drop)
        - bpm: The track's tempo, to enable swing and chords-per-bar
        - downbeat_seconds: Time of a downbeat, counted from start_seconds (0 if the window starts on one)
        """
        try:
            from . import ears
            report = ears.analyze(path, start_s=start_seconds, end_s=end_seconds,
                                  bpm=bpm, beat_offset_s=downbeat_seconds)
            label = label or _safe_label(Path(path).stem)
            _register_report(label, path, report, "file")
            report = dict(report)
            report["label"] = label
            return _dump(_compact_report(report))
        except Exception as e:
            return _err("analysing audio", e)

    @mcp.tool()
    @rich_telemetry_tool("compare_audio")
    def compare_audio(ctx: Context, a: str = "last", b: str = "",
                      user_prompt: str = "") -> str:
        """
        Compare two measured sounds, loudness-matched: our render vs a reference,
        or version 1 vs version 2. Only differences above audible thresholds are
        listed in the summary.

        Parameters:
        - a: Label of a render or analysed file ("last" = newest render), or a file path
        - b: Label or file path to compare against (usually the reference)
        """
        try:
            from . import ears
            if not b:
                return "Give b: a reference label or file path to compare against."
            report_a, name_a = _resolve_report(a)
            report_b, name_b = _resolve_report(b)
            result = ears.compare(report_a, report_b, labels=(name_a, name_b))
            return _dump(result)
        except Exception as e:
            return _err("comparing audio", e)

    # ── MIDI review and transforms ───────────────────────────────────────────

    def _clip_notes(track_index: int, clip_index: int) -> Dict[str, Any]:
        conn = _server().get_ableton_connection()
        return conn.send_command("get_clip_notes", {"track_index": track_index,
                                                    "clip_index": clip_index})

    def _tempo() -> Optional[float]:
        try:
            return float(_server().get_ableton_connection().send_command(
                "get_session_info", {}).get("tempo"))
        except Exception:
            return None

    @mcp.tool()
    @rich_telemetry_tool("review_clip")
    def review_clip(ctx: Context, track_index: int, clip_index: int, role: str = "",
                    user_prompt: str = "") -> str:
        """
        Ears by proxy for one MIDI clip: velocity and accent profile, measured
        swing and microtiming, articulation, density, chord names, low-interval
        (mud) violations, bar-to-bar variation, syncopation, and flags with fixes.

        Parameters:
        - role: Optional "drums", "bass", "chords", "lead", "perc" or "pad" (tunes the checks)
        """
        try:
            from . import midi_tools
            data = _clip_notes(track_index, clip_index)
            report = midi_tools.review_notes(data.get("notes", []),
                                             float(data.get("length", 4.0)),
                                             role=role or None, bpm=_tempo())
            report["clip_name"] = data.get("clip_name")
            return _dump(report)
        except Exception as e:
            return _err("reviewing clip", e)

    @mcp.tool()
    @rich_telemetry_tool("forecast_masking")
    def forecast_masking(ctx: Context, clips: List[Dict[str, Any]],
                         user_prompt: str = "") -> str:
        """
        Predict low-end and low-mid clashes between parts that play together,
        from their notes (before anyone listens).

        Parameters:
        - clips: list of {"track_index": 2, "clip_index": 0, "role": "bass"}; use role
          "drums" for drum racks so they count as rhythm, not pitch
        """
        try:
            from . import midi_tools
            conn = _server().get_ableton_connection()
            info = conn.send_command("get_session_info", {})
            names = {t["index"]: t["name"] for t in info.get("tracks", [])}
            parts = []
            for c in clips:
                ti, ci = int(c["track_index"]), int(c.get("clip_index", 0))
                data = _clip_notes(ti, ci)
                role = c.get("role")
                parts.append({
                    "name": names.get(ti, f"track {ti}") + f" [{data.get('clip_name') or ci}]",
                    "notes": data.get("notes", []),
                    "clip_length": float(data.get("length", 4.0)),
                    "role": role,
                    "pitched": role not in ("drums", "perc"),
                })
            return _dump(midi_tools.forecast_masking(parts))
        except Exception as e:
            return _err("forecasting masking", e)

    @mcp.tool()
    @rich_telemetry_tool("transform_clip_notes")
    def transform_clip_notes(ctx: Context, track_index: int, clip_index: int,
                             ops: Dict[str, Any], target_clip_index: Optional[int] = None,
                             new_name: str = "", user_prompt: str = "") -> str:
        """
        Rewrite a MIDI clip's notes musically in one step: transpose, snap to a
        scale, quantize, swing, role-based microtiming, accent maps, articulation,
        light humanising. Optionally write the result to another slot as a variant
        (keeps the original for A/B).

        ops keys (all optional; applied in this order):
        - transpose: semitones
        - scale: {"root": 9, "name": "dorian"} or {"root": 9, "intervals": [0,2,3,5,7,9,10]}
        - quantize: {"grid": 0.25, "strength": 1.0}
        - swing: {"percent": 58, "grid": 0.25}  (absolute; re-applying doesn't stack)
        - offset: beats added to every note
        - role_offsets: [{"pitches": [39], "beats": 0.02}, {"pitch_range": [42, 46], "beats": -0.005}]
        - velocity: {"accent_map": [100, 62, 84, 58], "mode": "set"} or {"add": -10} or
          {"multiply": 0.9} or {"compress": 0.5} or {"min": 40, "max": 110}
        - articulation: {"mode": "staccato", "length": 0.15} or {"mode": "legato", "gap": 0.02}
          or {"mode": "scale", "factor": 0.5}
        - humanize: {"timing_std": 0.003, "velocity_std": 4, "seed": 1, "exclude_pitches": [36]}

        Parameters:
        - target_clip_index: Write to this slot instead (copies the clip there first, overwriting)
        - new_name: Name for the target clip
        """
        try:
            from . import midi_tools
            conn = _server().get_ableton_connection()
            dest = clip_index
            if target_clip_index is not None and target_clip_index != clip_index:
                conn.send_command("copy_clip", {
                    "track_index": track_index, "clip_index": clip_index,
                    "target_track_index": track_index, "target_clip_index": target_clip_index,
                    "overwrite": True, **({"new_name": new_name} if new_name else {})})
                dest = target_clip_index
            data = _clip_notes(track_index, dest)
            length = float(data.get("length", 4.0))
            new_notes = midi_tools.transform_notes(data.get("notes", []), ops, length)
            payload = [{"pitch": int(n["pitch"]), "start_time": float(n["start_time"]),
                        "duration": float(n["duration"]), "velocity": int(n["velocity"]),
                        "mute": bool(n.get("mute", False))} for n in new_notes]
            conn.send_command("clear_notes_from_clip", {"track_index": track_index,
                                                        "clip_index": dest})
            conn.send_command("add_notes_to_clip", {"track_index": track_index,
                                                    "clip_index": dest, "notes": payload})
            if new_name and dest == clip_index:
                conn.send_command("set_clip_name", {"track_index": track_index,
                                                    "clip_index": dest, "name": new_name})
            return (f"{midi_tools.describe_ops(ops)} → wrote {len(payload)} notes to "
                    f"track {track_index}, slot {dest}")
        except Exception as e:
            return _err("transforming notes", e)
