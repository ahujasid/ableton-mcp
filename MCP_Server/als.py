"""read arrangement automation straight from a saved .als (gzipped XML).

Live's API exposes whether a parameter is automated but not the arrangement
lane's breakpoints; the file has them exactly. an envelope's EnvelopeTarget/
PointeeId names the AutomationTarget Id that sits inside the automated
parameter's element, so: index every AutomationTarget by its enclosing
track / device / parameter, then join the envelopes.
"""

from __future__ import annotations

import gzip
import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, asdict
from typing import Any

TRACK_TAGS = {"MidiTrack", "AudioTrack", "ReturnTrack", "MainTrack", "GroupTrack"}
# element tags that are containers, not devices or parameters
SKIP_AS_DEVICE = {"Devices", "DeviceChain", "Chains", "Chain", "Branches", "Branch", "MixerDevice",
                  "MainSequencer", "FreezeSequencer", "AudioToMidiDeviceChain", "MidiToAudioDeviceChain",
                  "DrumBranches", "ReturnBranches", "BranchPresets", "Mixer"}
# the value field inside a parameter element
VALUE_TAGS = ("Manual", "Value")


@dataclass
class Breakpoint:
    time: float
    value: float
    curve: list[float] | None = None  # [c1x, c1y, c2x, c2y] bezier handles, if any


@dataclass
class Envelope:
    track: str
    track_tag: str
    device: str
    device_tag: str
    param: str
    param_xpath: str
    pointee_id: int
    current_value: float | None
    events: list[Breakpoint] = field(default_factory=list)

    def value_at(self, t: float) -> float | None:
        """linear interpolation between breakpoints (curve handles ignored)."""
        ev = [e for e in self.events]
        if not ev:
            return None
        if t <= ev[0].time:
            return ev[0].value
        for a, b in zip(ev, ev[1:]):
            if a.time <= t <= b.time:
                if b.time == a.time:
                    return b.value
                f = (t - a.time) / (b.time - a.time)
                return a.value + f * (b.value - a.value)
        return ev[-1].value


def load_xml(path: str) -> ET.Element:
    with gzip.open(path, "rb") as f:
        return ET.fromstring(f.read())


def _name_of_track(el: ET.Element) -> str:
    n = el.find("Name/EffectiveName")
    if n is not None and n.get("Value"):
        return n.get("Value")
    n = el.find("Name/UserName")
    if n is not None and n.get("Value"):
        return n.get("Value")
    return el.tag


def _name_of_device(el: ET.Element) -> str:
    if el.tag == "Mixer":
        return "mixer"
    n = el.find("UserName")
    if n is not None and n.get("Value"):
        return n.get("Value")
    return el.tag


def _macro_display_name(device: ET.Element, macro_tag: str) -> str | None:
    # MacroControls.N -> MacroDisplayNames.N
    idx = macro_tag.split(".")[-1]
    n = device.find("MacroDisplayNames.%s" % idx)
    if n is not None and n.get("Value"):
        return n.get("Value")
    return None


def index_targets(root: ET.Element) -> dict[int, dict[str, Any]]:
    """map AutomationTarget Id -> {track, device, param, ...} by walking with an ancestor stack."""
    out: dict[int, dict[str, Any]] = {}

    def walk(el: ET.Element, ancestors: list[ET.Element]) -> None:
        for child in el:
            if child.tag == "AutomationTarget" and child.get("Id"):
                out[int(child.get("Id"))] = _describe(el, ancestors)
            walk(child, ancestors + [el])

    walk(root, [])
    return out


def _describe(param_el: ET.Element, ancestors: list[ET.Element]) -> dict[str, Any]:
    track = next((a for a in ancestors if a.tag in TRACK_TAGS), None)
    # device: nearest ancestor under a <Devices> container (or the track's MixerDevice)
    device = None
    for i in range(len(ancestors) - 1, -1, -1):
        a = ancestors[i]
        parent = ancestors[i - 1] if i > 0 else None
        if parent is not None and parent.tag == "Devices":
            device = a
            break
        if a.tag == "Mixer" and track is not None:
            device = a
            break
    cur = None
    for vt in VALUE_TAGS:
        v = param_el.find(vt)
        if v is not None and v.get("Value") is not None:
            try:
                cur = float(v.get("Value"))
            except ValueError:
                cur = v.get("Value")
            break
    param_name = param_el.tag
    if device is not None and param_el.tag.startswith("MacroControls."):
        param_name = _macro_display_name(device, param_el.tag) or param_el.tag
    # path inside the device for disambiguation (e.g. Bands.0/ParameterA/Freq)
    dev_idx = ancestors.index(device) if device is not None and device in ancestors else -1
    xpath = "/".join(a.tag for a in ancestors[dev_idx + 1:] + [param_el]) if dev_idx >= 0 else param_el.tag
    return {
        "track": _name_of_track(track) if track is not None else "?",
        "track_tag": track.tag if track is not None else "?",
        "device": _name_of_device(device) if device is not None else "?",
        "device_tag": device.tag if device is not None else "?",
        "param": param_name,
        "param_xpath": xpath,
        "current_value": cur,
    }


def read_automation(path: str) -> dict[str, Any]:
    root = load_xml(path)
    targets = index_targets(root)
    envelopes: list[Envelope] = []
    for env in root.iter("AutomationEnvelope"):
        pid_el = env.find("EnvelopeTarget/PointeeId")
        if pid_el is None:
            continue
        pid = int(pid_el.get("Value"))
        desc = targets.get(pid, {"track": "?", "track_tag": "?", "device": "?", "device_tag": "?",
                                 "param": "?", "param_xpath": "?", "current_value": None})
        events: list[Breakpoint] = []
        for ev in env.iterfind("Automation/Events/*"):
            t = float(ev.get("Time"))
            raw = ev.get("Value")
            if raw in ("true", "false"):
                val = 1.0 if raw == "true" else 0.0
            else:
                try:
                    val = float(raw)
                except (TypeError, ValueError):
                    continue
            curve = None
            if ev.get("CurveControl1X") is not None:
                curve = [float(ev.get(k)) for k in ("CurveControl1X", "CurveControl1Y", "CurveControl2X", "CurveControl2Y")]
            events.append(Breakpoint(t, val, curve))
        events.sort(key=lambda e: e.time)
        envelopes.append(Envelope(pointee_id=pid, events=events, **desc))
    return {
        "file": path,
        "mtime": os.path.getmtime(path),
        "envelopes": envelopes,
    }


def envelopes_as_dicts(result: dict[str, Any]) -> dict[str, Any]:
    out = dict(result)
    out["envelopes"] = [asdict(e) for e in result["envelopes"]]
    return out


def grid(result: dict[str, Any], bar_beats: float = 4.0, bars: int | None = None, levels: int = 10) -> str:
    """text projection: one row per envelope, one char per bar (position within the
    envelope's own min..max over the song; '·' = at min). the same view for every lane."""
    envs = result["envelopes"]
    if bars is None:
        last = max((e.events[-1].time for e in envs if e.events), default=0.0)
        bars = max(1, int(last // bar_beats) + 1)
    lines = []
    for e in envs:
        vals = [e.value_at(b * bar_beats) for b in range(bars)]
        vals = [v for v in vals if v is not None]
        lo, hi = (min(vals), max(vals)) if vals else (0.0, 0.0)
        row = ""
        for b in range(bars):
            v = e.value_at(b * bar_beats)
            if v is None or hi == lo:
                row += "·"
            else:
                k = int((v - lo) / (hi - lo) * (levels - 1))
                row += "·" if k == 0 else str(min(k, levels - 1))
        lines.append("%-14s %-16s %-22s [%g → %g] %s" % (e.track[:14], e.device[:16], e.param[:22], lo, hi, row))
    return "\n".join(lines)
