"""Pure MIDI transform preview extracted from PR #146; no Live or telemetry access."""

from __future__ import annotations


import math


import random


from bisect import bisect_right


from typing import Any, Dict, List, Optional, Sequence


NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


ROLES = ("drums", "bass", "chords", "lead", "perc", "pad")


UNPITCHED_ROLES = ("drums", "perc")


SIXTEENTH = 0.25


EPS = 1e-6


ONSET_TOLERANCE = 0.02


def _r(x: float, nd: int = 4) -> float:
    """Round for output; never returns -0.0."""
    v = round(float(x), nd)
    return 0.0 if v == 0 else v


def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _clamp(x, lo, hi):
    return lo if x < lo else hi if x > hi else x


def _round_half_up(x: float) -> int:
    return int(math.floor(x + 0.5))


def _nearest_index(t: float, grid: float) -> int:
    """Index of the nearest grid line (ties go to the later line)."""
    return int(math.floor(t / grid + 0.5 + 1e-9))


def _positive(value, label: str) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be a number (got {value!r})")
    if not v > 0 or math.isinf(v):
        raise ValueError(f"{label} must be > 0 (got {value!r})")
    return v


def _role(role) -> Optional[str]:
    if role is None or role == "":
        return None
    r = str(role).strip().lower()
    if r not in ROLES:
        raise ValueError(f"role must be one of {', '.join(ROLES)} (got {role!r})")
    return r


def _parse(note) -> Dict[str, Any]:
    """Core fields of a note, type-coerced (velocity defaults to 100)."""
    if not isinstance(note, dict):
        raise ValueError(f"each note must be a dict (got {type(note).__name__})")
    try:
        pitch = int(note["pitch"])
        start = float(note["start_time"])
    except KeyError as e:
        raise ValueError(f"note is missing {e.args[0]!r}: {note!r}")
    return {
        "pitch": pitch,
        "start_time": start,
        "duration": float(note.get("duration", SIXTEENTH)),
        "velocity": int(round(float(note.get("velocity", 100)))),
        "mute": bool(note.get("mute", False)),
    }


def _grid_label(g: float) -> str:
    labels = {4.0: "1 bar", 2.0: "1/2", 1.0: "1/4", 0.5: "1/8", 0.25: "1/16",
              0.125: "1/32", round(2 / 3, 6): "1/4T", round(1 / 3, 6): "1/8T",
              round(1 / 6, 6): "1/16T"}
    return labels.get(round(g, 6), f"{g:g}-beat")


def note_name(pitch: int) -> str:
    """Ableton-style name: 60 -> "C3", 48 -> "C2", 61 -> "C#3", 0 -> "C-2"."""
    p = int(pitch)
    return f"{NOTE_NAMES[p % 12]}{p // 12 - 2}"


_FLATS = {"DB": "C#", "EB": "D#", "FB": "E", "GB": "F#", "AB": "G#", "BB": "A#", "CB": "B",
          "E#": "F", "B#": "C"}


def _pitch_class(root) -> int:
    """0-11 from an int or a note name such as "A", "C#", "Bb"."""
    if isinstance(root, str):
        s = root.strip().upper().replace("♯", "#").replace("♭", "B")
        s = _FLATS.get(s, s)
        if s not in NOTE_NAMES:
            raise ValueError(f"unknown root {root!r}; use 0-11 or a name like 'A' or 'C#'")
        return NOTE_NAMES.index(s)
    return int(root) % 12


def _next_onsets(active, clip_length: float, lane: str) -> List[float]:
    """For each note (in ``active`` order), the next onset in its voice.

    lane "pitch": the next start of the same pitch (drum lanes).
    lane "onset": the next onset of any pitch (monophonic lines, chord changes).
    Notes within ONSET_TOLERANCE count as the same onset. The search wraps
    around the loop, so the last note's next onset is the first one plus
    ``clip_length``.
    """
    if lane == "pitch":
        lanes: Dict[int, List[float]] = {}
        for n in active:
            lanes.setdefault(n["pitch"], []).append(n["start_time"])
        for v in lanes.values():
            v.sort()
    else:
        all_onsets = sorted(n["start_time"] for n in active)
    out = []
    for n in active:
        starts = lanes[n["pitch"]] if lane == "pitch" else all_onsets
        s = n["start_time"]
        position = bisect_right(starts, s + ONSET_TOLERANCE)
        nxt = starts[position] if position < len(starts) else None
        out.append(nxt if nxt is not None else starts[0] + clip_length)
    return out


OP_ORDER = ("transpose", "scale", "quantize", "swing", "offset", "role_offsets",
            "velocity", "articulation", "humanize")


_SWING_EARLY = 0.2


_SWING_LATE = 0.45


_VELOCITY_KEYS = ("accent_map", "mode", "add", "multiply", "min", "max", "compress")


def _num(d: Dict[str, Any], key: str, default=None, *, lo=None, hi=None, label=""):
    v = d.get(key, default)
    if v is None:
        return None
    try:
        v = float(v)
    except (TypeError, ValueError):
        raise ValueError(f"{label}{key} must be a number (got {d.get(key)!r})")
    if (lo is not None and v < lo) or (hi is not None and v > hi) or math.isnan(v):
        rng = f">= {lo:g}" if hi is None else f"between {lo:g} and {hi:g}"
        raise ValueError(f"{label}{key} must be {rng} (got {v:g})")
    return v


SCALES: Dict[str, List[int]] = {
    "major": [0, 2, 4, 5, 7, 9, 11],
    "ionian": [0, 2, 4, 5, 7, 9, 11],
    "minor": [0, 2, 3, 5, 7, 8, 10],
    "aeolian": [0, 2, 3, 5, 7, 8, 10],
    "natural_minor": [0, 2, 3, 5, 7, 8, 10],
    "dorian": [0, 2, 3, 5, 7, 9, 10],
    "phrygian": [0, 1, 3, 5, 7, 8, 10],
    "lydian": [0, 2, 4, 6, 7, 9, 11],
    "mixolydian": [0, 2, 4, 5, 7, 9, 10],
    "locrian": [0, 1, 3, 5, 6, 8, 10],
    "harmonic_minor": [0, 2, 3, 5, 7, 8, 11],
    "melodic_minor": [0, 2, 3, 5, 7, 9, 11],
    "phrygian_dominant": [0, 1, 4, 5, 7, 8, 10],
    "hijaz": [0, 1, 4, 5, 7, 8, 10],
    "double_harmonic": [0, 1, 4, 5, 7, 8, 11],
    "pentatonic_major": [0, 2, 4, 7, 9],
    "pentatonic_minor": [0, 3, 5, 7, 10],
    "blues": [0, 3, 5, 6, 7, 10],
}


def _normalize_ops(ops) -> Dict[str, Any]:
    """Validate ops and fill in defaults. Unknown keys raise, so typos fail loudly."""
    if ops is None:
        return {}
    if not isinstance(ops, dict):
        raise ValueError("ops must be a dict")
    unknown = [k for k in ops if k not in OP_ORDER]
    if unknown:
        raise ValueError(f"unknown op(s) {unknown}; allowed: {', '.join(OP_ORDER)}")
    out: Dict[str, Any] = {}
    if ops.get("transpose") is not None:
        out["transpose"] = int(ops["transpose"])

    if ops.get("scale") is not None:
        sc = ops["scale"]
        if not isinstance(sc, dict):
            raise ValueError("scale must be a dict like {'root': 9, 'name': 'dorian'}")
        root = _pitch_class(sc.get("root", 0))
        if sc.get("intervals") is not None:
            ivs = sorted({int(i) % 12 for i in sc["intervals"]})
            label = "custom"
        elif sc.get("name") is not None:
            label = str(sc["name"]).strip().lower().replace(" ", "_").replace("-", "_")
            if label not in SCALES:
                raise ValueError(f"unknown scale {sc['name']!r}; known: {', '.join(SCALES)}")
            ivs = SCALES[label]
        else:
            raise ValueError("scale needs 'intervals' or 'name'")
        if not ivs:
            raise ValueError("scale intervals must not be empty")
        out["scale"] = {"root": root, "intervals": ivs, "name": label}

    if ops.get("quantize") is not None:
        q = ops["quantize"]
        out["quantize"] = {"grid": _positive(q.get("grid", SIXTEENTH), "quantize.grid"),
                           "strength": _num(q, "strength", 1.0, lo=0, hi=1, label="quantize.")}

    if ops.get("swing") is not None:
        s = ops["swing"]
        out["swing"] = {"percent": _num(s, "percent", 50, lo=50, hi=75, label="swing."),
                        "grid": _positive(s.get("grid", SIXTEENTH), "swing.grid")}

    if ops.get("offset") is not None:
        out["offset"] = float(ops["offset"])

    if ops.get("role_offsets") is not None:
        rules = []
        for rule in ops["role_offsets"]:
            if not isinstance(rule, dict) or "beats" not in rule:
                raise ValueError("each role_offsets rule needs 'beats' and 'pitches' or 'pitch_range'")
            beats = float(rule["beats"])
            if rule.get("pitch_range") is not None:
                lo, hi = (int(x) for x in rule["pitch_range"])
                rules.append({"pitches": None, "range": (min(lo, hi), max(lo, hi)), "beats": beats})
            elif rule.get("pitches") is not None or rule.get("pitch") is not None:
                ps = rule.get("pitches")
                ps = [rule["pitch"]] if ps is None else ps
                rules.append({"pitches": sorted({int(p) for p in ps}), "range": None, "beats": beats})
            else:
                raise ValueError("each role_offsets rule needs 'pitches' or 'pitch_range'")
        out["role_offsets"] = rules

    if ops.get("velocity") is not None:
        v = ops["velocity"]
        bad = [k for k in v if k not in _VELOCITY_KEYS]
        if bad:
            raise ValueError(f"unknown velocity key(s) {bad}; allowed: {', '.join(_VELOCITY_KEYS)}")
        nv: Dict[str, Any] = {}
        if v.get("accent_map") is not None:
            amap = list(v["accent_map"])
            if len(amap) not in (4, 16):
                raise ValueError("accent_map needs 4 values (per 16th in a beat) or 16 (per 16th in a bar)")
            nv["accent_map"] = [None if a is None else float(a) for a in amap]
            mode = str(v.get("mode", "set")).lower()
            if mode not in ("set", "scale"):
                raise ValueError("velocity.mode must be 'set' or 'scale'")
            nv["mode"] = mode
        if v.get("multiply") is not None:
            nv["multiply"] = _num(v, "multiply", lo=0, label="velocity.")
        if v.get("add") is not None:
            nv["add"] = float(v["add"])
        if v.get("compress") is not None:
            nv["compress"] = _num(v, "compress", lo=0, hi=1, label="velocity.")
        lo = _num(v, "min", 0, lo=0, hi=127, label="velocity.")
        hi = _num(v, "max", 127, lo=0, hi=127, label="velocity.")
        if lo > hi:
            raise ValueError("velocity.min must be <= velocity.max")
        if "min" in v or "max" in v:
            nv["min"], nv["max"] = lo, hi
        out["velocity"] = nv

    if ops.get("articulation") is not None:
        a = ops["articulation"]
        mode = str(a.get("mode", "")).lower()
        if mode == "staccato":
            out["articulation"] = {"mode": mode,
                                   "length": _positive(a.get("length", 0.15), "articulation.length")}
        elif mode == "legato":
            lane = str(a.get("lane") or "").lower()
            if not lane:
                lane = "pitch" if _role(a.get("role")) in UNPITCHED_ROLES else "onset"
            if lane not in ("pitch", "onset"):
                raise ValueError("articulation.lane must be 'pitch' (drums) or 'onset'")
            out["articulation"] = {"mode": mode, "gap": float(a.get("gap", 0.02)), "lane": lane}
        elif mode == "scale":
            out["articulation"] = {"mode": mode,
                                   "factor": _positive(a.get("factor", 1.0), "articulation.factor")}
        else:
            raise ValueError("articulation.mode must be 'staccato', 'legato' or 'scale'")

    if ops.get("humanize") is not None:
        h = ops["humanize"]
        out["humanize"] = {
            "timing_std": _num(h, "timing_std", 0.0, lo=0, label="humanize."),
            "velocity_std": _num(h, "velocity_std", 0.0, lo=0, label="humanize."),
            "seed": h.get("seed", 0) if h.get("seed") is not None else 0,
            "exclude_pitches": sorted({int(p) for p in (h.get("exclude_pitches") or [])}),
        }
    return out


def _snap_to_scale(pitch: int, root: int, intervals: Sequence[int]) -> int:
    allowed = {(root + i) % 12 for i in intervals}
    for d in range(12):
        if pitch - d >= 0 and (pitch - d) % 12 in allowed:
            return pitch - d
        if pitch + d <= 127 and (pitch + d) % 12 in allowed:
            return pitch + d
    return pitch


def _gauss_clipped(rng: random.Random, std: float) -> float:
    if std <= 0:
        return 0.0
    return _clamp(rng.gauss(0.0, std), -2.5 * std, 2.5 * std)


def transform_notes(notes: Sequence[Dict[str, Any]], ops: Optional[Dict[str, Any]],
                    clip_length: float) -> List[Dict[str, Any]]:
    """Apply batch edits in a fixed order and return new, loop-correct notes.

    The order is transpose -> scale -> quantize -> swing -> offset ->
    role_offsets -> velocity -> articulation -> humanize. The input is never
    mutated. Extra note keys such as ``note_id`` are kept.

    ops (all optional):
      transpose     int semitones; pitches are clamped to 0-127.
      scale         {"root": 0-11 or "A", "intervals": [...]} or {"root", "name": "dorian"}.
                    Snaps to the nearest scale tone; ties snap down.
      quantize      {"grid": 0.25, "strength": 0-1}.
      swing         {"percent": 50-75, "grid": 0.25|0.5}. Absolute: off-notes
                    (including ones already swung up to 72.5 %) are snapped
                    straight, then placed at pair_start + 2*grid*percent/100.
                    Straight finer subdivisions (16ths under 1/8 swing) stay put.
      offset        float beats added to every start.
      role_offsets  [{"pitches": [39], "beats": 0.015}, {"pitch_range": [42, 46], "beats": -0.005}].
                    The first matching rule wins. Rules match pitches after
                    transpose/scale.
      velocity      {"accent_map": [4 or 16 values, None = leave], "mode": "set"|"scale",
                     "multiply": f, "add": n, "compress": 0-1, "min": n, "max": n}.
                    Applied in that order. The accent slot is the note's grid
                    position after quantize, unswung, so swing and pushes don't
                    shift accents.
      articulation  {"mode": "staccato", "length": 0.15} caps note lengths;
                    {"mode": "legato", "gap": 0.02, "lane": "onset"|"pitch"} sets
                    every note to end ``gap`` before the next onset (lane
                    "pitch", or role drums/perc, uses the same pitch lane; it
                    wraps around the loop, and a negative gap overlaps for glide);
                    {"mode": "scale", "factor": 0.5}.
      humanize      {"timing_std": 0.003, "velocity_std": 4, "seed": 1, "exclude_pitches": [36]}.
                    Gaussian noise clipped to ±2.5 std. The seed defaults to 0,
                    so the result is always deterministic.

    Finally, starts are wrapped into [0, clip_length) (a note pushed before 0
    plays at the clip end), durations are clamped to [0.01, clip_length],
    velocities to 0-127, and the notes are sorted by (start_time, pitch).
    """
    _validate_preview(notes, ops, clip_length)
    _check_metadata_budget(notes)
    L = _positive(clip_length, "clip_length")
    spec = _normalize_ops(ops)

    items = []  # [note_copy, grid_pos, original_index]
    for i, n in enumerate(notes or []):
        core = _parse(n)
        c = dict(n)
        c.update(core)
        c["velocity"] = float(core["velocity"])
        items.append([c, core["start_time"], i])
    items.sort(key=lambda it: (it[0]["start_time"], it[0]["pitch"], it[2]))

    if "transpose" in spec:
        t = spec["transpose"]
        for c, _, _ in items:
            c["pitch"] = int(_clamp(c["pitch"] + t, 0, 127))

    if "scale" in spec:
        sc = spec["scale"]
        for c, _, _ in items:
            c["pitch"] = _snap_to_scale(c["pitch"], sc["root"], sc["intervals"])

    if "quantize" in spec:
        g, strength = spec["quantize"]["grid"], spec["quantize"]["strength"]
        for it in items:
            s = it[0]["start_time"]
            target = _nearest_index(s, g) * g
            it[0]["start_time"] = s + (target - s) * strength
    for it in items:
        it[1] = it[0]["start_time"]  # metric (grid) position, used for accents

    if "swing" in spec:
        g, pct = spec["swing"]["grid"], spec["swing"]["percent"]
        pair = 2 * g
        for it in items:
            s = it[0]["start_time"]
            k = math.floor(s / pair + 1e-9)
            phase = s - k * pair
            if (1 - _SWING_EARLY) * g - EPS <= phase <= (1 + _SWING_LATE) * g + EPS:
                it[1] = k * pair + g                       # straight position
                it[0]["start_time"] = k * pair + pair * pct / 100.0

    if "offset" in spec:
        for c, _, _ in items:
            c["start_time"] += spec["offset"]

    if "role_offsets" in spec:
        for c, _, _ in items:
            for rule in spec["role_offsets"]:
                p = c["pitch"]
                hit = (p in rule["pitches"]) if rule["pitches"] is not None else \
                    rule["range"][0] <= p <= rule["range"][1]
                if hit:
                    c["start_time"] += rule["beats"]
                    break

    for c, _, _ in items:  # wrap so later stages see loop positions
        c["start_time"] %= L

    if "velocity" in spec:
        v = spec["velocity"]
        if "accent_map" in v:
            amap = v["accent_map"]
            for c, gpos, _ in items:
                a = amap[_nearest_index(gpos, SIXTEENTH) % len(amap)]
                if a is None:
                    continue
                c["velocity"] = a if v["mode"] == "set" else c["velocity"] * a / 100.0
        if "multiply" in v:
            for c, _, _ in items:
                c["velocity"] *= v["multiply"]
        if "add" in v:
            for c, _, _ in items:
                c["velocity"] += v["add"]
        if "compress" in v and items:
            m = _mean([c["velocity"] for c, _, _ in items])
            for c, _, _ in items:
                c["velocity"] = m + (c["velocity"] - m) * (1.0 - v["compress"])
        if "min" in v:
            for c, _, _ in items:
                c["velocity"] = _clamp(c["velocity"], v["min"], v["max"])
        for c, _, _ in items:
            c["velocity"] = float(_clamp(_round_half_up(c["velocity"]), 0, 127))

    if "articulation" in spec:
        a = spec["articulation"]
        if a["mode"] == "staccato":
            for c, _, _ in items:
                c["duration"] = min(c["duration"], a["length"])
        elif a["mode"] == "scale":
            for c, _, _ in items:
                c["duration"] *= a["factor"]
        elif items:
            notes_now = [c for c, _, _ in items]
            nexts = _next_onsets(notes_now, L, a["lane"])
            for c, nx in zip(notes_now, nexts):
                end = nx - a["gap"]
                if nx > L - EPS:  # wrapped to the next loop pass: Ableton cuts at the loop end
                    end = min(end, L)
                c["duration"] = end - c["start_time"]

    if "humanize" in spec:
        h = spec["humanize"]
        rng = random.Random(h["seed"])
        excluded = set(h["exclude_pitches"])
        for c, _, _ in sorted(items, key=lambda it: (it[0]["start_time"], it[0]["pitch"], it[2])):
            if c["pitch"] in excluded:
                continue
            c["start_time"] += _gauss_clipped(rng, h["timing_std"])
            c["velocity"] = float(_clamp(_round_half_up(c["velocity"] + _gauss_clipped(rng, h["velocity_std"])), 0, 127))

    out = []
    for c, _, _ in items:
        s = _r(c["start_time"] % L)
        if s >= L:
            s = 0.0
        c["start_time"] = s
        c["duration"] = _r(_clamp(c["duration"], 0.01, L))
        c["velocity"] = int(_clamp(_round_half_up(c["velocity"]), 0, 127))
        c["pitch"] = int(_clamp(c["pitch"], 0, 127))
        out.append(c)
    out.sort(key=lambda c: (c["start_time"], c["pitch"]))
    return out


def describe_ops(ops: Optional[Dict[str, Any]]) -> str:
    """Short plain-English summary of what transform_notes will do with ``ops``."""
    spec = _normalize_ops(ops)
    parts = []
    if "transpose" in spec:
        parts.append(f"transpose {spec['transpose']:+d} semitones")
    if "scale" in spec:
        sc = spec["scale"]
        what = sc["name"].replace("_", " ") if sc["name"] != "custom" else \
            "scale " + str(sc["intervals"])
        parts.append(f"snap pitches to {NOTE_NAMES[sc['root']]} {what} (ties snap down)")
    if "quantize" in spec:
        q = spec["quantize"]
        parts.append(f"quantize starts to {_grid_label(q['grid'])} at {q['strength'] * 100:.0f}% strength")
    if "swing" in spec:
        s = spec["swing"]
        parts.append(f"swing off-{_grid_label(s['grid'])} notes to {s['percent']:g}% (absolute, "
                     f"re-applying won't stack)")
    if "offset" in spec:
        parts.append(f"shift every note {spec['offset']:+.3f} beats")
    if "role_offsets" in spec:
        rs = []
        for r in spec["role_offsets"]:
            who = ",".join(note_name(p) for p in r["pitches"]) if r["pitches"] is not None else \
                f"{note_name(r['range'][0])}–{note_name(r['range'][1])}"
            rs.append(f"{who} {r['beats']:+.3f}")
        parts.append("per-pitch microtiming (" + "; ".join(rs) + " beats)")
    if "velocity" in spec:
        v = spec["velocity"]
        vs = []
        if "accent_map" in v:
            vs.append(f"{len(v['accent_map'])}-step accent map ({v['mode']})")
        if "multiply" in v:
            vs.append(f"×{v['multiply']:g}")
        if "add" in v:
            vs.append(f"{v['add']:+g}")
        if "compress" in v:
            vs.append(f"compress {v['compress'] * 100:.0f}% toward the mean")
        if "min" in v:
            vs.append(f"limit to {v['min']:g}–{v['max']:g}")
        if vs:
            parts.append("velocity: " + ", ".join(vs))
    if "articulation" in spec:
        a = spec["articulation"]
        if a["mode"] == "staccato":
            parts.append(f"staccato (notes at most {a['length']:g} beats)")
        elif a["mode"] == "legato":
            lane = "same-pitch onset" if a["lane"] == "pitch" else "next onset"
            parts.append(f"legato: each note ends {a['gap']:g} beats before its {lane}")
        else:
            parts.append(f"scale note lengths ×{a['factor']:g}")
    if "humanize" in spec:
        h = spec["humanize"]
        ex = f", never touching {', '.join(note_name(p) for p in h['exclude_pitches'])}" \
            if h["exclude_pitches"] else ""
        parts.append(f"humanize timing σ {h['timing_std']:g} beats and velocity σ "
                     f"{h['velocity_std']:g} (seed {h['seed']}){ex}")
    if not parts:
        return "no changes"
    return "; ".join(parts) + "; then wrap starts into the loop"



def _validate_preview(notes, ops, clip_length):
    if not isinstance(notes, (list, tuple)) or len(notes) > 10000:
        raise ValueError('Preview is limited to 10000 notes')
    if isinstance(clip_length, bool) or not isinstance(clip_length, (int, float)) or not math.isfinite(clip_length) or not .01 <= clip_length <= 65536:
        raise ValueError('clip_length must be finite and within .01..65536')
    nested = {
        'scale': {'root','intervals','name'}, 'quantize': {'grid','strength'},
        'swing': {'percent','grid'}, 'velocity': set(_VELOCITY_KEYS),
        'articulation': {'mode','length','gap','lane','role','factor'},
        'humanize': {'timing_std','velocity_std','seed','exclude_pitches'},
    }
    if ops is not None:
        if not isinstance(ops,dict): raise ValueError('ops must be an object')
        for key, allowed in nested.items():
            if ops.get(key) is not None:
                if not isinstance(ops[key],dict) or set(ops[key])-allowed: raise ValueError('Invalid '+key+' fields')
        if ops.get('transpose') is not None and (type(ops['transpose']) is not int): raise ValueError('transpose must be integer')
    stack = [(ops, 0)]
    count = 0
    while stack:
        value, depth = stack.pop(); count += 1
        if count > 4096 or depth > 6: raise ValueError('Operation specification too large')
        if isinstance(value, dict):
            if len(value) > 32: raise ValueError('Too many operation fields')
            stack.extend((v, depth+1) for v in value.values())
        elif isinstance(value, (list, tuple)):
            if len(value) > 128: raise ValueError('Operation list too large')
            stack.extend((v, depth+1) for v in value)
        elif isinstance(value, bool): raise ValueError('Boolean is not a numeric transform value')
        elif isinstance(value, (int, float)):
            if not math.isfinite(value) or abs(value) > 1e6: raise ValueError('Transform values must be finite and bounded')
        elif isinstance(value, str):
            if len(value) > 256: raise ValueError('Operation string too long')
        elif value is not None: raise ValueError('Unsupported operation value')
    for note in notes:
        if not isinstance(note, dict) or len(note)>32: raise ValueError('Each note must be a bounded object')
        pitch=note.get('pitch')
        if isinstance(pitch,bool) or not isinstance(pitch,int) or not 0<=pitch<=127: raise ValueError('pitch must be an integer in 0..127')
        for key, default, low, high in [('start_time',0,-65536,65536),('duration',.25,.000001,65536),('velocity',100,0,127),('probability',1,0,1),('velocity_deviation',0,-127,127),('release_velocity',64,0,127)]:
            value=note.get(key,default)
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not low<=value<=high: raise ValueError('Invalid note '+key)
        if type(note.get('mute',False)) is not bool: raise ValueError('mute must be boolean')


def _check_metadata_budget(notes):
    pending=[(notes,0)]; size=0; count=0
    while pending:
        value,depth=pending.pop(); count+=1
        if count>400000 or depth>6: raise ValueError('Note metadata exceeds preview bounds')
        if isinstance(value,dict): pending.extend((v,depth+1) for v in value.values())
        elif isinstance(value,(list,tuple)):
            if len(value)>10000: raise ValueError('Note metadata list too large')
            pending.extend((v,depth+1) for v in value)
        elif isinstance(value,str):
            size+=len(value)
            if size>2000000: raise ValueError('Note metadata exceeds 2 MB')
        elif isinstance(value,(int,float)):
            try: finite=math.isfinite(value)
            except OverflowError: finite=False
            if not finite: raise ValueError('Note metadata must be finite')
        elif value is not None: raise ValueError('Unsupported note metadata')
