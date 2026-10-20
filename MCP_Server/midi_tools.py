"""MIDI note analysis and transformation: "ears by proxy".

An assistant that writes MIDI into Ableton Live cannot hear the result. This
module reads the note data and reports what a producer would hear (flat
velocities, robotic timing, muddy low voicings, parts masking each other), and
applies musically correct batch transforms (absolute swing, scale snapping,
accent maps, per-instrument microtiming, seeded humanisation).

Pure standard library. Every public function returns JSON-serialisable data;
floats are rounded to 4 decimals.

Conventions
-----------
* A note is a dict ``{"pitch", "start_time", "duration", "velocity", "mute"}``.
  Extra keys (``note_id``, ``probability`` ...) are carried through
  :func:`transform_notes`. :func:`tile_notes` drops ``note_id`` from the copies,
  because a copy is a new note.
* Time is in beats, 4/4: one bar = 4 beats, one 16th = 0.25 beat.
* Pitch names follow Ableton: MIDI 60 = C3 (48 = C2, 36 = C1, 24 = C0), sharps.
* The analysers ignore muted notes and notes that start outside
  ``[0, clip_length)``, because they don't sound. Both are counted and flagged.
"""

from __future__ import annotations

import math
import random
from itertools import combinations
from typing import Any, Dict, List, Optional, Sequence

__all__ = [
    "NOTE_NAMES",
    "ROLES",
    "LOW_INTERVAL_LIMITS",
    "SCALES",
    "CHORD_TEMPLATES",
    "METRIC_WEIGHTS_16",
    "OP_ORDER",
    "note_name",
    "midi_to_hz",
    "interval_name",
    "low_interval_limit",
    "low_interval_violations",
    "identify_chord",
    "chord_name",
    "review_notes",
    "forecast_masking",
    "transform_notes",
    "describe_ops",
    "tile_notes",
]

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
ROLES = ("drums", "bass", "chords", "lead", "perc", "pad")
#: Roles treated as unpitched (Drum Rack lanes, not melodic pitches) unless a
#: part explicitly says ``"pitched": True``.
UNPITCHED_ROLES = ("drums", "perc")

SIXTEENTH = 0.25
BAR_BEATS = 4.0
EPS = 1e-6
#: Notes whose starts are this close (in beats) belong to the same onset/chord.
ONSET_TOLERANCE = 0.02

# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _r(x: float, nd: int = 4) -> float:
    """Round for output; never returns -0.0."""
    v = round(float(x), nd)
    return 0.0 if v == 0 else v


def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _pstd(xs: Sequence[float]) -> float:
    """Population standard deviation (0 for fewer than two values)."""
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / len(xs))


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


def _sounding(notes, clip_length: float):
    """Split parsed notes into (active, muted, outside-the-loop)."""
    parsed = [_parse(n) for n in (notes or [])]
    muted = [n for n in parsed if n["mute"]]
    live = [n for n in parsed if not n["mute"]]
    active = [n for n in live if -EPS < n["start_time"] < clip_length - EPS]
    outside = [n for n in live if not (-EPS < n["start_time"] < clip_length - EPS)]
    active.sort(key=lambda n: (n["start_time"], n["pitch"]))
    return parsed, active, muted, outside


def _onset_clusters(notes) -> List[List[Dict[str, Any]]]:
    """Group start-sorted notes whose starts lie within ONSET_TOLERANCE of the group's first."""
    groups: List[List[Dict[str, Any]]] = []
    for n in sorted(notes, key=lambda n: (n["start_time"], n["pitch"])):
        if groups and n["start_time"] - groups[-1][0]["start_time"] <= ONSET_TOLERANCE + EPS:
            groups[-1].append(n)
        else:
            groups.append([n])
    return groups


def _grid_label(g: float) -> str:
    labels = {4.0: "1 bar", 2.0: "1/2", 1.0: "1/4", 0.5: "1/8", 0.25: "1/16",
              0.125: "1/32", round(2 / 3, 6): "1/4T", round(1 / 3, 6): "1/8T",
              round(1 / 6, 6): "1/16T"}
    return labels.get(round(g, 6), f"{g:g}-beat")


# ---------------------------------------------------------------------------
# 1. Names and frequencies
# ---------------------------------------------------------------------------


def note_name(pitch: int) -> str:
    """Ableton-style name: 60 -> "C3", 48 -> "C2", 61 -> "C#3", 0 -> "C-2"."""
    p = int(pitch)
    return f"{NOTE_NAMES[p % 12]}{p // 12 - 2}"


def midi_to_hz(pitch: float) -> float:
    """Equal-tempered frequency, A4 = MIDI 69 = 440 Hz (Ableton calls it A3)."""
    return _r(440.0 * 2.0 ** ((float(pitch) - 69.0) / 12.0))


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


_INTERVAL_NAMES = {
    0: "unison", 1: "minor 2nd", 2: "major 2nd", 3: "minor 3rd", 4: "major 3rd",
    5: "perfect 4th", 6: "tritone", 7: "perfect 5th", 8: "minor 6th", 9: "major 6th",
    10: "minor 7th", 11: "major 7th", 12: "octave", 13: "minor 9th", 14: "major 9th",
    15: "minor 10th", 16: "major 10th", 17: "perfect 11th", 18: "augmented 11th",
    19: "perfect 12th", 20: "minor 13th", 21: "major 13th", 22: "minor 14th",
    23: "major 14th", 24: "two octaves",
}


def interval_name(semitones: int) -> str:
    s = abs(int(semitones))
    if s in _INTERVAL_NAMES:
        return _INTERVAL_NAMES[s]
    octaves, rem = divmod(s, 12)
    return f"{octaves} octaves" if rem == 0 else f"{_INTERVAL_NAMES[rem]} + {octaves} octaves"


# ---------------------------------------------------------------------------
# 2. Low-interval limits
# ---------------------------------------------------------------------------

#: Lowest allowed MIDI pitch for the BOTTOM note of an interval (Ableton names).
#: Below these the interval turns to mud. Octaves are unlimited.
LOW_INTERVAL_LIMITS: Dict[int, int] = {
    1: 52,   # minor 2nd   -> E2
    2: 51,   # major 2nd   -> D#2
    3: 48,   # minor 3rd   -> C2
    4: 46,   # major 3rd   -> A#1
    5: 46,   # perfect 4th -> A#1
    6: 47,   # tritone     -> B1
    7: 34,   # perfect 5th -> A#0
    8: 41,   # minor 6th   -> F1
    9: 41,   # major 6th   -> F1
    10: 41,  # minor 7th   -> F1
    11: 41,  # major 7th   -> F1
    12: 0,   # octave      -> unlimited
    13: 40,  # minor 9th   -> E1
    14: 39,  # major 9th   -> D#1
}


def low_interval_limit(interval: int) -> int:
    """Lowest allowed bottom note (MIDI) for an interval in semitones.

    Intervals up to a major 9th use :data:`LOW_INTERVAL_LIMITS`. A unison or
    any whole number of octaves has no limit. Wider intervals take the limit of
    ``interval % 12`` lowered ("relaxed") by one octave, never below 0. For
    example, a minor 10th (15) may sit with its bottom note at C1 (36), and a
    perfect 12th (19) at A#-1 (22). The relaxation is a single octave however
    wide the interval is: a 3rd two octaves up is already clear, and this keeps
    the rule easy to state.
    """
    iv = abs(int(interval))
    if iv in LOW_INTERVAL_LIMITS:
        return LOW_INTERVAL_LIMITS[iv]
    base = iv % 12
    if base == 0:
        return 0
    return max(0, LOW_INTERVAL_LIMITS[base] - 12)


def low_interval_violations(pitches: Sequence[int]) -> List[Dict[str, Any]]:
    """Pairs in a chord whose bottom note sits below the low-interval limit.

    The function checks every adjacent pair of the sorted chord and every chord
    tone against the lowest note, which is the implied bass. A bottom note that
    is exactly at the limit is allowed. Each violation is returned as
    ``{low, high, interval, interval_name, limit, limit_name, message}``.
    """
    ps = sorted({int(p) for p in pitches})
    if len(ps) < 2:
        return []
    pairs = list(zip(ps, ps[1:]))
    bass = ps[0]
    pairs += [(bass, p) for p in ps[2:]]
    out = []
    for lo, hi in sorted(set(pairs)):
        iv = hi - lo
        limit = low_interval_limit(iv)
        if lo < limit:
            out.append({
                "low": lo,
                "high": hi,
                "interval": iv,
                "interval_name": interval_name(iv),
                "limit": limit,
                "limit_name": note_name(limit),
                "message": (f"{note_name(lo)}–{note_name(hi)} {interval_name(iv)} sits below "
                            f"its low-interval limit — its bottom note should be "
                            f"{note_name(limit)} or higher"),
            })
    return out


# ---------------------------------------------------------------------------
# Chord naming
# ---------------------------------------------------------------------------

#: (suffix, intervals from root) in priority order. When two exact matches tie
#: on other criteria, the earlier template wins.
CHORD_TEMPLATES = (
    ("", (0, 4, 7)),
    ("m", (0, 3, 7)),
    ("7", (0, 4, 7, 10)),
    ("maj7", (0, 4, 7, 11)),
    ("m7", (0, 3, 7, 10)),
    ("m7b5", (0, 3, 6, 10)),
    ("dim7", (0, 3, 6, 9)),
    ("9", (0, 2, 4, 7, 10)),
    ("maj9", (0, 2, 4, 7, 11)),
    ("m9", (0, 2, 3, 7, 10)),
    ("11", (0, 2, 4, 5, 7, 10)),
    ("m11", (0, 2, 3, 5, 7, 10)),
    ("13", (0, 2, 4, 7, 9, 10)),
    ("sus2", (0, 2, 7)),
    ("sus4", (0, 5, 7)),
    ("7sus4", (0, 5, 7, 10)),
    ("6", (0, 4, 7, 9)),
    ("m6", (0, 3, 7, 9)),
    ("add9", (0, 2, 4, 7)),
    ("m(add9)", (0, 2, 3, 7)),
    ("dim", (0, 3, 6)),
    ("aug", (0, 4, 8)),
    ("5", (0, 7)),
)


def _build_variants():
    """(priority, suffix, pitch-class set, level). Level 0 is the full template;
    level 1 is a common reduced voicing (no 5th, 11 without its 3rd, 13 without its 9th)."""
    out = []
    for prio, (suffix, tmpl) in enumerate(CHORD_TEMPLATES):
        full = frozenset(tmpl)
        out.append((prio, suffix, full, 0))
        reduced = []
        if 7 in full and len(full) >= 4:
            reduced.append(full - {7})
        if suffix == "11":
            reduced += [full - {4}, full - {4, 7}]
        if suffix == "13":
            reduced += [full - {2}, full - {2, 7}]
        for v in reduced:
            out.append((prio, suffix, frozenset(v), 1))
    return out


_CHORD_VARIANTS = _build_variants()


def identify_chord(pitches: Sequence[int], bass: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """Best-effort chord name from pitches.

    The root is the bass note whenever the pitch-class set fits a template from
    that root. Otherwise the function takes the best exact match from another
    chord tone and writes it as a slash chord (e.g. "Am/C"). If nothing matches
    exactly, it returns the closest template with ``exact=False`` and a "~"
    prefix on the name. Pass ``bass`` (a MIDI pitch from another part) to name a
    rootless voicing over that bass: C-E-G-B with bass=A gives "Am9".
    """
    ps = sorted({int(p) for p in pitches})
    if bass is not None:
        ps = sorted(set(ps) | {int(bass)})
    if not ps:
        return None
    bass_pc = (int(bass) if bass is not None else ps[0]) % 12
    pcs = {p % 12 for p in ps}
    if len(pcs) == 1:
        nm = NOTE_NAMES[bass_pc]
        return {"name": nm, "root": nm, "quality": "octaves", "bass": nm, "exact": True}

    best = None
    for root in sorted(pcs):
        rel = frozenset((pc - root) % 12 for pc in pcs)
        for prio, suffix, vset, level in _CHORD_VARIANTS:
            if rel == vset:
                key = (level, 0 if root == bass_pc else 1, prio)
                if best is None or key < best[0]:
                    best = (key, root, suffix)
    exact = best is not None
    if not exact:
        for root in sorted(pcs):
            rel = {(pc - root) % 12 for pc in pcs}
            for prio, (suffix, tmpl) in enumerate(CHORD_TEMPLATES):
                t = set(tmpl)
                score = 2 * len(rel & t) - 2 * len(rel - t) - len(t - rel)
                score += 0.5 if root == bass_pc else 0.0
                key = (-score, prio, root)
                if best is None or key < best[0]:
                    best = (key, root, suffix)
    _, root, suffix = best
    name = NOTE_NAMES[root] + suffix
    if root != bass_pc:
        name += "/" + NOTE_NAMES[bass_pc]
    if not exact:
        name = "~" + name
    quality = {"": "maj", "m": "min"}.get(suffix, suffix)
    return {"name": name, "root": NOTE_NAMES[root], "quality": quality,
            "bass": NOTE_NAMES[bass_pc], "exact": exact}


def chord_name(pitches: Sequence[int], bass: Optional[int] = None) -> Optional[str]:
    """Shortcut for ``identify_chord(...)["name"]`` (None for no pitches)."""
    info = identify_chord(pitches, bass)
    return info["name"] if info else None


# ---------------------------------------------------------------------------
# 3. review_notes
# ---------------------------------------------------------------------------

#: Longuet-Higgins & Lee metric hierarchy on a 16th grid, shifted to be
#: non-negative: downbeat 4, beat 3 = 3, beats 2 & 4 = 2, off-8ths = 1,
#: off-16ths = 0.
METRIC_WEIGHTS_16 = [4, 0, 1, 0, 2, 0, 1, 0, 3, 0, 1, 0, 2, 0, 1, 0]

_STACCATO_BEATS = 0.2
_LEGATO_WINDOW = 0.05
_LONG_BEATS = 1.0
_ON_GRID = 0.002
_GHOST_VELOCITY = 45
_FLAT_VELOCITY_STD = 6.0
_PER_NOTE_CAP = 256
_CHORD_LIST_CAP = 32


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
        nxt = next((t for t in starts if t > s + ONSET_TOLERANCE), None)
        out.append(nxt if nxt is not None else starts[0] + clip_length)
    return out


def review_notes(notes: Sequence[Dict[str, Any]], clip_length: float,
                 role: Optional[str] = None, bpm: Optional[float] = None) -> Dict[str, Any]:
    """Describe what a clip will sound like, as numbers plus plain-English flags.

    Parameters
    ----------
    notes : list of note dicts (muted notes are counted, then ignored).
    clip_length : loop length in beats.
    role : optional "drums", "bass", "chords", "lead", "perc" or "pad". Drums
        and perc skip the chord and interval checks. Bass is checked for
        polyphony and overlapping notes.
    bpm : optional tempo. When given, timing offsets are also reported in ms.

    Timing uses a straight 16th grid. A note counts as an off-16th when its
    nearest 16th is odd (.25, .75 ...), which catches 16th swing up to just
    under 75 %. ``swing_percent`` is 50 + d/0.5*100, where d is the mean delay
    of the off-16ths; it is reported only when there are at least 4 of them.
    ``jitter_std`` is the spread of offsets around the on/off class means, so
    a consistent swing doesn't count as jitter. Parts that contain 32nd notes
    skew the swing estimate.
    """
    L = _positive(clip_length, "clip_length")
    role = _role(role)
    if bpm is not None:
        bpm = _positive(bpm, "bpm")
    parsed, active, muted, outside = _sounding(notes, L)
    n_bars = max(1, int(math.ceil(L / BAR_BEATS - 1e-9)))
    drums_like = role in UNPITCHED_ROLES
    flags: List[str] = []

    def ms(beats: float) -> float:
        return _r(beats * 60000.0 / bpm)

    pitches = [n["pitch"] for n in active]
    counts: Dict[str, Any] = {
        "notes": len(parsed),
        "muted": len(muted),
        "active": len(active),
        "outside_clip": len(outside),
        "distinct_pitches": len(set(pitches)),
        "pitch_range": None,
    }
    if pitches:
        lo, hi = min(pitches), max(pitches)
        counts["pitch_range"] = {"lowest": lo, "lowest_name": note_name(lo),
                                 "highest": hi, "highest_name": note_name(hi),
                                 "span_semitones": hi - lo}
    result: Dict[str, Any] = {"role": role, "clip_length": _r(L), "bars": n_bars,
                              "bpm": _r(bpm) if bpm else None, "counts": counts}

    if outside:
        flags.append(f"{len(outside)} note{'s start' if len(outside) != 1 else ' starts'} outside the "
                     f"clip (0–{L:g} beats) and won't play — move them inside or lengthen the clip")
    if muted:
        flags.append(f"{len(muted)} muted note{'s' if len(muted) != 1 else ''} ignored by this review")
    if not active:
        flags.insert(0, "clip has no unmuted notes inside the loop — nothing will sound")
        result.update({k: None for k in ("velocity", "timing", "articulation", "density",
                                         "polyphony", "syncopation", "repetition")})
        result["flags"] = flags
        return result

    # --- velocity --------------------------------------------------------
    vels = [n["velocity"] for n in active]
    v_std = _pstd(vels)
    slot_vels: List[List[int]] = [[] for _ in range(16)]
    for n in active:
        slot_vels[_nearest_index(n["start_time"], SIXTEENTH) % 16].append(n["velocity"])
    velocity = {
        "mean": _r(_mean(vels)),
        "std": _r(v_std),
        "min": min(vels),
        "max": max(vels),
        "flat": v_std < _FLAT_VELOCITY_STD,
        "accent_map_16": [_r(_mean(s)) if s else None for s in slot_vels],
        "ghost_notes": sum(1 for v in vels if v < _GHOST_VELOCITY),
    }

    # --- timing ----------------------------------------------------------
    on_offs: List[float] = []
    off_offs: List[float] = []
    per_note = []
    for n in active:
        s = n["start_time"]
        idx = _nearest_index(s, SIXTEENTH)
        off = s - idx * SIXTEENTH
        (off_offs if idx % 2 else on_offs).append(off)
        if len(per_note) < _PER_NOTE_CAP:
            entry = {"start_time": _r(s), "pitch": n["pitch"], "offset_beats": _r(off)}
            if bpm:
                entry["offset_ms"] = ms(off)
            per_note.append(entry)
    all_offs = on_offs + off_offs
    m_on, m_off = _mean(on_offs), _mean(off_offs)
    residuals = [o - m_on for o in on_offs] + [o - m_off for o in off_offs]
    jitter = math.sqrt(_mean([x * x for x in residuals])) if residuals else 0.0
    systematic = _mean(all_offs)
    on_grid_share = sum(1 for o in all_offs if abs(o) < _ON_GRID) / len(all_offs)

    def _cls(offs):
        d = {"count": len(offs),
             "mean_offset": _r(_mean(offs)) if offs else None,
             "std": _r(_pstd(offs)) if offs else None}
        if bpm and offs:
            d["mean_offset_ms"] = ms(_mean(offs))
            d["std_ms"] = ms(_pstd(offs))
        return d

    swing = _r(50.0 + m_off / 0.5 * 100.0) if len(off_offs) >= 4 else None
    timing: Dict[str, Any] = {
        "grid": SIXTEENTH,
        "per_note": per_note,
        "per_note_truncated": len(active) > _PER_NOTE_CAP,
        "on_16ths": _cls(on_offs),
        "off_16ths": _cls(off_offs),
        "swing_percent": swing,
        "systematic_offset": _r(systematic),
        "jitter_std": _r(jitter),
        "on_grid_share": _r(on_grid_share),
    }
    if bpm:
        timing["systematic_offset_ms"] = ms(systematic)
        timing["jitter_std_ms"] = ms(jitter)

    # --- articulation ----------------------------------------------------
    lane = "pitch" if drums_like else "onset"
    nexts = _next_onsets(active, L, lane)
    durs = [n["duration"] for n in active]
    ends = [n["start_time"] + n["duration"] for n in active]
    legato = sum(1 for e, nx in zip(ends, nexts) if e >= nx - _LEGATO_WINDOW)
    overlapping = [n for n, e, nx in zip(active, ends, nexts) if e > nx + 1e-3]
    articulation = {
        "mean_duration": _r(_mean(durs)),
        "staccato_share": _r(sum(1 for d in durs if d < _STACCATO_BEATS) / len(durs)),
        "legato_share": _r(legato / len(durs)),
        "long_share": _r(sum(1 for d in durs if d >= _LONG_BEATS) / len(durs)),
        "voice": "same pitch lane" if lane == "pitch" else "next onset",
    }
    past_end = [n for n in active if n["start_time"] + n["duration"] > L + EPS]

    # --- density -----------------------------------------------------------
    clusters = _onset_clusters(active)
    per_bar = [0] * n_bars
    for g in clusters:
        per_bar[min(n_bars - 1, int(g[0]["start_time"] // BAR_BEATS))] += 1
    density = {"notes_per_beat": _r(len(active) / L), "onsets": len(clusters),
               "onsets_per_bar": per_bar}

    # --- polyphony & chords ---------------------------------------------
    events = []
    for n in active:
        s, e = n["start_time"], min(n["start_time"] + n["duration"], L)
        if e > s:
            events += [(round(s, 6), 1), (round(e, 6), -1)]
    events.sort()
    cur = max_poly = 0
    for _, d in events:
        cur += d
        max_poly = max(max_poly, cur)

    chords = []
    bad_chords = []
    if not drums_like:
        for g in clusters:
            ps = sorted({n["pitch"] for n in g})
            if len(ps) < 3:
                continue
            info = identify_chord(ps)
            viol = low_interval_violations(ps)
            entry = {"start_time": _r(g[0]["start_time"]), "pitches": ps,
                     "notes": [note_name(p) for p in ps], "name": info["name"],
                     "exact": info["exact"], "low_interval_violations": viol}
            chords.append(entry)
            if viol:
                bad_chords.append(entry)
    polyphony = {
        "max_simultaneous": max_poly,
        "chord_count": len(chords),
        "chords": chords[:_CHORD_LIST_CAP],
        "chords_truncated": len(chords) > _CHORD_LIST_CAP,
        "chords_breaking_low_interval_limits": len(bad_chords),
        "chord_analysis": "skipped for " + role if drums_like else "on",
    }

    # --- syncopation -------------------------------------------------------
    total_slots = max(1, int(math.ceil(L / SIXTEENTH - 1e-9)))
    onset_slots = sorted({_nearest_index(g[0]["start_time"], SIXTEENTH) % total_slots
                          for g in clusters})
    score = 0
    for i, s in enumerate(onset_slots):
        nxt = onset_slots[i + 1] if i + 1 < len(onset_slots) else onset_slots[0] + total_slots
        w = METRIC_WEIGHTS_16[s % 16]
        rest_w = max((METRIC_WEIGHTS_16[(j % total_slots) % 16] for j in range(s + 1, nxt)),
                     default=-1)
        if rest_w > w:
            score += rest_w - w
    k = len(onset_slots)
    syncopation = {
        "onset_slots": k,
        "off_8th_share": _r(sum(1 for s in onset_slots if s % 4 == 2) / k),
        "off_16th_share": _r(sum(1 for s in onset_slots if s % 2 == 1) / k),
        "score": score,
        "score_per_bar": _r(score / n_bars),
        "method": ("Longuet-Higgins/Lee: each onset followed by silence on a stronger "
                   "16th adds (stronger weight - onset weight); weights per bar "
                   "16th = " + ",".join(map(str, METRIC_WEIGHTS_16))),
    }

    # --- repetition --------------------------------------------------------
    # Starts are rounded to 1/48 beat so humanised timing doesn't count as variation.
    loop_units = max(1, _round_half_up(L * 48))
    bars: List[List] = [[] for _ in range(n_bars)]
    for n in active:
        q = _round_half_up(n["start_time"] * 48) % loop_units
        b = min(n_bars - 1, q // 192)
        bars[b].append((n["pitch"], q - b * 192))
    seen: Dict[tuple, int] = {}
    form = []
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    for b in bars:
        key = tuple(sorted(b))
        if key not in seen:
            seen[key] = len(seen)
        form.append(letters[seen[key]] if seen[key] < len(letters) else "?")
    distinct = len(seen)
    repetition = {"bars": n_bars, "distinct_bar_patterns": distinct,
                  "variation_ratio": _r(distinct / n_bars), "form": "".join(form)}

    # --- stacked duplicates ---------------------------------------------
    stacked = []
    by_pitch: Dict[int, List[Dict[str, Any]]] = {}
    for n in active:
        by_pitch.setdefault(n["pitch"], []).append(n)
    for lane_notes in by_pitch.values():
        for a, b in zip(lane_notes, lane_notes[1:]):
            if b["start_time"] < a["start_time"] + a["duration"] - EPS:
                stacked.append(b)

    # --- flags ---------------------------------------------------------------
    n_act = len(active)
    if n_act >= 4 and v_std < _FLAT_VELOCITY_STD:
        flags.append(f"velocity is flat (std {v_std:.1f}) — add an accent map")
    if n_act >= 4 and on_grid_share == 1.0:
        flags.append("every note is exactly on the grid and every part may share this — "
                     "consider role-specific microtiming")
    if len(on_offs) >= 4 and abs(m_on) >= 0.02:
        where = "late" if m_on > 0 else "early"
        extra = f" ({abs(ms(m_on)):g} ms)" if bpm else ""
        flags.append(f"on-beat notes sit {abs(m_on):.3f} beats{extra} {where} on average — "
                     f"intended lay-back/push? otherwise quantize")
    if bad_chords:
        kb = len(bad_chords)
        flags.append(f"{kb} chord{'s' if kb != 1 else ''} break{'s' if kb == 1 else ''} "
                     f"low-interval limits, e.g. {bad_chords[0]['low_interval_violations'][0]['message']}"
                     f" — open the voicing or move it up")
    if n_bars >= 2 and distinct == 1:
        flags.append(f"bar pattern never changes across {n_bars} bars — vary a bar "
                     f"(fill, pickup, dropped or moved note)")
    if stacked:
        ex = stacked[0]
        flags.append(f"notes overlap in the same pitch (stacked duplicates): {len(stacked)}, "
                     f"e.g. {note_name(ex['pitch'])} at beat {ex['start_time']:g} — delete the "
                     f"duplicate or shorten the earlier note")
    if role == "bass":
        if max_poly > 1:
            flags.append(f"bass plays up to {max_poly} notes at once — keep the bass monophonic "
                         f"(move upper notes to another part)")
        if overlapping:
            flags.append(f"bass notes longer than the gap to the next note (legato) — intended? "
                         f"{len(overlapping)} overlap{'s' if len(overlapping) == 1 else ''} the "
                         f"next note, which triggers glide on a "
                         f"mono synth; shorten them if not")
    if past_end:
        flags.append(f"{len(past_end)} note{'s run' if len(past_end) != 1 else ' runs'} past the clip "
                     f"end ({L:g} beats) and get cut at the loop point")

    result.update({
        "velocity": velocity,
        "timing": timing,
        "articulation": articulation,
        "density": density,
        "polyphony": polyphony,
        "syncopation": syncopation,
        "repetition": repetition,
        "flags": flags,
    })
    return result


# ---------------------------------------------------------------------------
# 4. forecast_masking
# ---------------------------------------------------------------------------

_LOW_MID_MAX = 71   # B3, ~494 Hz
_SUB_BELOW = 48     # C2, ~65 Hz
_MASK_SPAN_CAP = 64.0
_MASK_SPAN_MAX = 1024.0


def _slot_pitches(notes, L: float, span: float, n_slots: int):
    """Pitches sounding in each 16th slot when the clip loops over the span.

    A note occupies every slot it overlaps. On the grid this is exactly
    ``start <= t < start + duration``. Off the grid it also counts the slot the
    note starts in, so swung notes are not missed. Notes are cut at the clip
    end, as Ableton does when a clip loops.
    """
    slots: List[List[int]] = [[] for _ in range(n_slots)]
    onsets = set()
    k = 0
    while k * L < span - EPS:
        base = k * L
        for n in notes:
            s = n["start_time"] + base
            if s >= span - EPS:
                continue
            e = min(n["start_time"] + n["duration"], L) + base
            first = int(math.floor(s / SIXTEENTH + 1e-9))
            last = int(math.ceil(e / SIXTEENTH - 1e-9))
            onsets.add(first)
            for t in range(first, min(max(last, first + 1), n_slots)):
                slots[t].append(n["pitch"])
        k += 1
    return slots, onsets


def _mask_suggestion(zone: str, pa: Dict[str, Any], pb: Dict[str, Any]) -> str:
    lo, hi = sorted((pa, pb), key=lambda p: p["median"])
    bass = pa if pa["role"] == "bass" else pb if pb["role"] == "bass" else None

    def chordy(p):
        return p["role"] in ("chords", "pad") or p["max_poly"] >= 3

    if zone == "sub":
        owner = bass or lo
        other = pb if owner is pa else pa
        return (f"both reach below C2 (~65 Hz): let '{owner['name']}' own the sub — move "
                f"'{other['name']}' up an octave, high-pass it around 100 Hz, or sidechain it "
                f"to '{owner['name']}'")
    if bass is not None:
        other = pb if bass is pa else pa
        if chordy(other):
            target = note_name(max(60, bass["highest"] + 12))
            return (f"raise '{other['name']}' voicing above {target} or drop its root while "
                    f"'{bass['name']}' plays (or high-pass it around 150–200 Hz)")
        return (f"sidechain '{other['name']}' to '{bass['name']}' or alternate rhythmically "
                f"(play it in the bass's gaps), or move it up an octave")
    if chordy(lo) or chordy(hi):
        c = hi if chordy(hi) else lo
        o = lo if c is hi else hi
        return (f"spread the registers: voice '{c['name']}' an octave away from "
                f"'{o['name']}', or sidechain/alternate them rhythmically")
    return (f"sidechain or alternate rhythmically — or move '{hi['name']}' up an octave "
            f"so the two lines sit apart")


def forecast_masking(parts: Sequence[Dict[str, Any]],
                     span_beats: Optional[float] = None) -> Dict[str, Any]:
    """Predict where parts will mask each other when they play together.

    ``parts`` is a list of ``{"name", "notes", "clip_length", "role"?, "pitched"?}``.
    Each part loops its own clip over the span. By default the span is the LCM
    of the clip lengths, capped at 64 beats. A part is unpitched when its role
    is drums or perc or when ``"pitched": False``; an explicit
    ``"pitched": True`` overrides the role. Unpitched parts are left out of
    pitch masking and listed under ``rhythmic_layers``.

    Every pair of pitched parts is checked on 16th slots:

    * zone "low-mid": both parts sound at MIDI 71 (B3, ~494 Hz) or below,
      within 12 semitones of each other.
    * zone "sub": both parts sound below MIDI 48 (C2, ~65 Hz).

    Conflicts are sorted by ``share``, the conflicting slots over all slots.
    """
    if not parts:
        raise ValueError("parts must be a non-empty list")
    P = []
    for i, part in enumerate(parts):
        if not isinstance(part, dict):
            raise ValueError("each part must be a dict")
        name = str(part.get("name") or f"part {i + 1}")
        L = _positive(part.get("clip_length"), f"clip_length of part '{name}'")
        role = _role(part.get("role"))
        pitched = part.get("pitched")
        pitched = (role not in UNPITCHED_ROLES) if pitched is None else bool(pitched)
        _, active, _, _ = _sounding(part.get("notes") or [], L)
        P.append({"name": name, "role": role, "pitched": pitched, "L": L, "notes": active})

    if span_beats is None:
        lcm = 1
        for p in P:
            u = max(1, _round_half_up(p["L"] / SIXTEENTH))
            lcm = lcm * u // math.gcd(lcm, u)
            if lcm * SIXTEENTH >= _MASK_SPAN_CAP:
                break
        span = min(lcm * SIXTEENTH, _MASK_SPAN_CAP)
    else:
        span = _positive(span_beats, "span_beats")
        if span > _MASK_SPAN_MAX:
            raise ValueError(f"span_beats is capped at {_MASK_SPAN_MAX:g}")
    n_slots = max(1, int(math.ceil(span / SIXTEENTH - 1e-9)))

    registers = []
    for p in P:
        p["slots"], p["onsets"] = _slot_pitches(p["notes"], p["L"], span, n_slots)
        ps = sorted(n["pitch"] for n in p["notes"])
        p["max_poly"] = max((len(set(s)) for s in p["slots"]), default=0)
        if ps:
            med = ps[(len(ps) - 1) // 2]
            p.update(lowest=ps[0], highest=ps[-1], median=med)
            registers.append({
                "name": p["name"], "role": p["role"], "pitched": p["pitched"],
                "lowest": ps[0], "lowest_name": note_name(ps[0]),
                "highest": ps[-1], "highest_name": note_name(ps[-1]),
                "median": med, "median_name": note_name(med),
            })
        else:
            p.update(lowest=None, highest=None, median=0)
            registers.append({"name": p["name"], "role": p["role"], "pitched": p["pitched"],
                              "lowest": None, "lowest_name": None, "highest": None,
                              "highest_name": None, "median": None, "median_name": None})

    pitched = [p for p in P if p["pitched"] and p["notes"]]
    conflicts = []
    for pa, pb in combinations(pitched, 2):
        low_mid, sub = [], []
        for t in range(n_slots):
            A, B = pa["slots"][t], pb["slots"][t]
            if not A or not B:
                continue
            la = {x for x in A if x <= _LOW_MID_MAX}
            lb = {y for y in B if y <= _LOW_MID_MAX}
            if la and lb and any(abs(x - y) <= 12 for x in la for y in lb):
                low_mid.append(t)
            if min(A) < _SUB_BELOW and min(B) < _SUB_BELOW:
                sub.append(t)
        for zone, slots in (("low-mid", low_mid), ("sub", sub)):
            if slots:
                conflicts.append({
                    "a": pa["name"], "b": pb["name"], "zone": zone,
                    "share": _r(len(slots) / n_slots), "slots": len(slots),
                    "example_beats": [_r(t * SIXTEENTH) for t in slots[:5]],
                    "suggestion": _mask_suggestion(zone, pa, pb),
                })
    conflicts.sort(key=lambda c: (-c["share"], c["zone"] != "sub", c["a"], c["b"]))

    bars_in_span = span / BAR_BEATS
    rhythmic = [{
        "name": p["name"], "role": p["role"],
        "onsets_per_bar": _r(len(p["onsets"]) / bars_in_span),
        "onset_slot_share": _r(len(p["onsets"]) / n_slots),
    } for p in P if not p["pitched"]]

    if conflicts:
        c = conflicts[0]
        summary = (f"{len(conflicts)} masking risk{'s' if len(conflicts) != 1 else ''}; worst: "
                   f"'{c['a']}' vs '{c['b']}' in the {c['zone']} zone for "
                   f"{c['share'] * 100:.0f}% of 16ths")
    else:
        summary = "no low-register masking predicted between pitched parts"
    return {
        "span_beats": _r(span),
        "slots": n_slots,
        "conflicts": conflicts,
        "registers": registers,
        "rhythmic_layers": rhythmic,
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# 5. transform_notes
# ---------------------------------------------------------------------------

#: The fixed order in which transform_notes applies ops.
OP_ORDER = ("transpose", "scale", "quantize", "swing", "offset", "role_offsets",
            "velocity", "articulation", "humanize")

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

# Swing treats a note as an off-note when its phase inside the 2*grid pair lies
# in [0.8*grid, 1.45*grid]. That covers notes played slightly early and notes
# already swung by up to 72.5 %, so re-swinging is absolute and never stacks.
# The window stops short of 0.75*grid and 1.5*grid so that straight subdivisions
# stay put: the "e" and "a" 16ths under 1/8 swing, and the 32nds under 1/16
# swing. A note swung above 72.5 % sits exactly where a straight subdivision
# would. It is not re-detected; re-applying the same percent still changes
# nothing, but a later, different percent won't move it.
_SWING_EARLY = 0.2
_SWING_LATE = 0.45

_VELOCITY_KEYS = ("accent_map", "mode", "add", "multiply", "min", "max", "compress")
_COPY_INVALID_KEYS = ("note_id",)


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
        lo = _num(v, "min", 1, lo=1, hi=127, label="velocity.")
        hi = _num(v, "max", 127, lo=1, hi=127, label="velocity.")
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
    velocities to 1-127, and the notes are sorted by (start_time, pitch).
    """
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
            c["velocity"] = float(_clamp(_round_half_up(c["velocity"]), 1, 127))

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
            c["velocity"] = float(_clamp(_round_half_up(c["velocity"] + _gauss_clipped(rng, h["velocity_std"])), 1, 127))

    out = []
    for c, _, _ in items:
        s = _r(c["start_time"] % L)
        if s >= L:
            s = 0.0
        c["start_time"] = s
        c["duration"] = _r(_clamp(c["duration"], 0.01, L))
        c["velocity"] = int(_clamp(_round_half_up(c["velocity"]), 1, 127))
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


# ---------------------------------------------------------------------------
# 6. tile_notes
# ---------------------------------------------------------------------------


def tile_notes(notes: Sequence[Dict[str, Any]], repeat_every: float,
               repeat_count: int) -> List[Dict[str, Any]]:
    """Repeat a pattern ``repeat_count`` times in total, ``repeat_every`` beats apart.

    The first pass keeps the notes where they are; pass i is shifted by
    ``i * repeat_every``. Every note is a copy, so the input is never mutated.
    ``note_id`` is dropped from the shifted copies because they are new notes.
    The result is sorted by (start_time, pitch). This matches
    ``add_notes_to_clip``'s ``repeat_every``/``repeat_count``.
    """
    count = int(repeat_count)
    if count < 1 or count > 256:
        raise ValueError("repeat_count must be between 1 and 256")
    every = float(repeat_every)
    if count > 1 and not every > 0:
        raise ValueError("repeat_every must be > 0 when repeat_count > 1")
    out = []
    for i in range(count):
        for n in notes or []:
            c = dict(n)
            c["start_time"] = _r(float(n["start_time"]) + i * every)
            if i:
                for k in _COPY_INVALID_KEYS:
                    c.pop(k, None)
            out.append(c)
    out.sort(key=lambda c: (c["start_time"], c.get("pitch", 0)))
    return out
