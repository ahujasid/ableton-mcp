"""Top-level ``analyze()`` / ``compare()`` and the plain-English layers on top.

``analyze()`` returns a JSON-ready dict (plain floats rounded to 1-3
decimals, lists, ``None`` where a value is undefined). ``compare()`` diffs
two such reports and writes summary sentences only for differences above
these perceptual thresholds (see ``THRESHOLDS``).
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional, Sequence, Union

import numpy as np

from ._dsp import num
from .audio import as_frames, load_audio
from .loudness import measure as measure_loudness
from .rhythm import analyze_rhythm
from .spectrum import analyze_spectrum
from .stereo import analyze_stereo
from .tonal import analyze_tonal

Source = Union[str, "os.PathLike[str]", np.ndarray]

THRESHOLDS = {
    "band_db": 1.5,
    "octave_db": 2.0,
    "tilt_db_per_oct": 0.5,
    "crest_db": 1.5,
    "lra_lu": 1.5,
    "width_db": 2.0,
    "correlation": 0.1,
    "swing_points": 2.0,
    "loudness_lu": 1.0,
}

SPECTRAL_NOTE = (
    "Band and octave dB values are relative to each signal's own 20 Hz–20 kHz energy, "
    "so spectral deltas are inherently loudness-matched; loudness_offset_db is reported separately."
)

# Band -> (advice when the mix has MORE of it, advice when it has LESS).
BAND_ADVICE = {
    "sub": ("too much sub; shorten kick/808 tails, lower the sub layer or high-pass non-bass tracks at 30–40 Hz",
            "missing sub weight; boost 40–60 Hz on kick/bass or layer a sine sub"),
    "bass": ("boomy low end; cut 80–200 Hz on bass or kick, or sidechain the bass to the kick",
             "thin low end; boost 80–120 Hz on bass/kick or pick a fuller bass patch"),
    "low_mid": ("likely mud; thin chord voicings or cut 250–400 Hz",
                "may sound hollow; ease off low-mid cuts or add body around 300 Hz on pads/keys"),
    "mid": ("boxy/honky; cut 500 Hz–1 kHz on pads, keys or guitars",
            "scooped mids; leads may lack body, so lift 800 Hz–1.5 kHz"),
    "presence": ("harsh/forward; cut 2–4 kHz on synths or vocals, or use a dynamic EQ there",
                 "lacks presence/clarity; lift 2–4 kHz on the lead elements"),
    "brilliance": ("bright/sizzly; tame hats and cymbals or de-ess around 6–8 kHz",
                   "dull top end; add a high shelf from ~6 kHz or use brighter hats"),
    "air": ("airy/hissy; check hats, noise layers and reverb tails above 10 kHz",
            "lacks air; try a gentle high shelf above 10 kHz"),
}

# Stereo width key -> (where, advice if wider, advice if narrower).
WIDTH_ADVICE = {
    "width_db": ("overall (side vs mid energy)",
                 "check it in mono and rein in stereo wideners if it collapses",
                 "widen pads and FX with panning, stereo delays or chorus"),
    "low_width_db": ("below 150 Hz",
                     "make bass and kick mono below ~120 Hz (Utility Bass Mono)",
                     "fine for mono safety; only widen if the reference's wide low end is intended"),
    "mid_width_db": ("in the 150 Hz–5 kHz range",
                     "check that vocals and leads stay centred and solid in mono",
                     "pan or double-track chords and pads to open up the mids"),
    "high_width_db": ("above 5 kHz",
                      "check hats and reverbs in mono",
                      "widen hats, shakers and reverb returns with panning or stereo effects"),
}


# ---------------------------------------------------------------- analyze

def analyze(
    source: Source,
    sr: Optional[float] = None,
    start_s: Optional[float] = None,
    end_s: Optional[float] = None,
    bpm: Optional[float] = None,
    beat_offset_s: float = 0.0,
) -> Dict:
    """Measure a render: loudness, spectrum, stereo image, rhythm and tonality.

    Args:
        source: Path to a WAV/AIFF file, or an ndarray shaped ``(n,)`` or
            ``(n, channels)`` (then ``sr`` is required).
        sr: Sample rate for array input (ignored for files).
        start_s, end_s: Optional trim, in seconds.
        bpm: Song tempo. Enables groove/swing analysis and chords per bar.
        beat_offset_s: Time of a downbeat in seconds from the start of the
            analysed (trimmed) audio. It anchors the beat grid and bar 1.

    Returns:
        JSON-serialisable dict with keys ``duration_s``, ``sample_rate``,
        ``channels``, ``loudness``, ``spectrum``, ``stereo`` (2 channels only),
        ``rhythm``, ``tonal`` and ``warnings``.
    """
    if isinstance(source, np.ndarray):
        x, rate = as_frames(source, sr, start_s, end_s)
    else:
        x, rate = load_audio(source, start_s, end_s)
    if bpm is not None and bpm <= 0:
        raise ValueError("bpm must be positive")

    mid = x.mean(axis=1)
    report: Dict = {
        "duration_s": num(x.shape[0] / rate, 3),
        "sample_rate": int(rate),
        "channels": int(x.shape[1]),
        "loudness": measure_loudness(x, rate),
        "spectrum": analyze_spectrum(mid, rate),
    }
    if x.shape[1] == 2:
        report["stereo"] = analyze_stereo(x, rate)
    report["rhythm"] = analyze_rhythm(mid, rate, bpm, beat_offset_s)
    report["tonal"] = analyze_tonal(mid, rate, bpm, beat_offset_s)
    report["warnings"] = build_warnings(report)
    return report


def build_warnings(report: Dict) -> List[str]:
    """Plain-English red flags for a single analyze() report."""
    out: List[str] = []
    loud = report["loudness"]
    integrated = loud.get("integrated_lufs")
    tp = loud.get("true_peak_dbtp")

    if integrated is None:
        out.append("Render is silent or entirely below the -70 LUFS gate — check solo/mute states "
                   "and that the resampling track is actually recording.")
    elif integrated < -30.0:
        out.append(f"Very quiet render ({integrated:.1f} LUFS integrated) — check track levels/solo.")

    if tp is not None:
        limit = -2.0 if integrated is not None and integrated > -14.0 else -1.0
        if tp > limit:
            why = " (the safe ceiling for masters louder than -14 LUFS)" if limit == -2.0 else ""
            out.append(f"True peak {tp:+.1f} dBTP is above {limit:.0f} dBTP{why} — risk of inter-sample "
                       "clipping after encoding; lower the limiter ceiling.")
    sample_peak = loud.get("sample_peak_dbfs")
    if sample_peak is not None and sample_peak >= -0.01:
        out.append("Samples reach 0 dBFS — the render is probably clipping.")

    crest = loud.get("crest_db")
    if crest is not None and integrated is not None and crest < 6.0:
        out.append(f"Heavily limited, little transient punch (crest factor {crest:.1f} dB).")

    stereo = report.get("stereo")
    if stereo and stereo.get("low_correlation") is not None and stereo["low_correlation"] < 0.5:
        out.append(f"Low end has phase/stereo problems (correlation {stereo['low_correlation']:.2f} "
                   "below 150 Hz) — make bass and kick mono below ~120 Hz (Utility Bass Mono).")

    bands = {b["name"]: b["db"] for b in report["spectrum"]["bands"]}
    sub, bass, low_mid = bands.get("sub"), bands.get("bass"), bands.get("low_mid")
    if sub is not None and bass is not None and sub - bass > 6.0:
        out.append(f"Sub-heavy: the 20–60 Hz band is {sub - bass:.1f} dB above the 60–250 Hz band.")
    if low_mid is not None and bass is not None and integrated is not None and low_mid > bass:
        out.append(f"Possible low-mid build-up (mud): 250–500 Hz is {low_mid - bass:.1f} dB above 60–250 Hz.")
    return out


# ---------------------------------------------------------------- compare

def _band_range(lo: float, hi: float) -> str:
    if lo >= 1000:
        return f"{lo / 1000:g}–{hi / 1000:g} kHz"
    if hi >= 1000:
        return f"{lo:g} Hz–{hi / 1000:g} kHz"
    return f"{lo:g}–{hi:g} Hz"


def _diff(a, b, nd: int = 2) -> Optional[float]:
    if a is None or b is None:
        return None
    return num(a - b, nd)


def _over(delta: Optional[float], threshold: float) -> bool:
    return delta is not None and abs(delta) >= threshold - 1e-9


def compare(a: Union[Dict, Source], b: Union[Dict, Source], labels: Sequence[str] = ("mix", "reference")) -> Dict:
    """Compare two renders (analyze() reports or file paths).

    Deltas are ``a - b``, except ``loudness_offset_db``, which is ``b - a``
    (how much louder ``b`` is). ``summary`` holds one actionable sentence
    for each difference above ``THRESHOLDS``. Identical inputs give an
    empty summary.
    """
    ra = a if isinstance(a, dict) else analyze(a)
    rb = b if isinstance(b, dict) else analyze(b)
    la, lb = str(labels[0]), str(labels[1])
    you, them = f"Your {la}", f"the {lb}"
    summary: List[str] = []

    # Loudness
    ia, ib = ra["loudness"].get("integrated_lufs"), rb["loudness"].get("integrated_lufs")
    offset = _diff(ib, ia)
    if _over(offset, THRESHOLDS["loudness_lu"]):
        if offset > 0:
            summary.append(f"{you} is {offset:.1f} LU quieter than {them} ({ia:.1f} vs {ib:.1f} LUFS integrated) "
                           f"— push the master limiter about {offset:.1f} dB harder to match.")
        else:
            summary.append(f"{you} is {-offset:.1f} LU louder than {them} ({ia:.1f} vs {ib:.1f} LUFS integrated) "
                           f"— pull the limiter input down about {-offset:.1f} dB unless that loudness is intended.")

    # Spectrum
    sa, sb = ra["spectrum"], rb["spectrum"]
    band_d: Dict[str, Optional[float]] = {}
    for ba, bb in zip(sa["bands"], sb["bands"]):
        d = _diff(ba["db"], bb["db"])
        band_d[ba["name"]] = d
        if _over(d, THRESHOLDS["band_db"]):
            more, less = BAND_ADVICE.get(ba["name"], ("", ""))
            summary.append(f"{you} has {abs(d):.1f} dB {'more' if d > 0 else 'less'} {ba['name']} "
                           f"({_band_range(ba['lo_hz'], ba['hi_hz'])}) than {them} — {more if d > 0 else less}.")
    oct_d: Dict[str, Optional[float]] = {}
    big_octaves = []
    for oa, ob in zip(sa["octave_bands"], sb["octave_bands"]):
        d = _diff(oa["db"], ob["db"])
        oct_d[oa["name"]] = d
        if _over(d, THRESHOLDS["octave_db"]):
            name = oa["name"]
            label = f"{name[:-1]} kHz" if name.endswith("k") else f"{name} Hz"
            big_octaves.append(f"{label} {d:+.1f} dB")
    if big_octaves:
        summary.append(f"Octave bands differing by 2 dB or more ({la} minus {lb}): " + ", ".join(big_octaves) + ".")

    tilt = _diff(sa.get("tilt_db_per_oct"), sb.get("tilt_db_per_oct"))
    if _over(tilt, THRESHOLDS["tilt_db_per_oct"]):
        ta, tb = sa["tilt_db_per_oct"], sb["tilt_db_per_oct"]
        if tilt < 0:
            summary.append(f"{you} tilts {-tilt:.1f} dB/oct darker than {them} ({ta:.1f} vs {tb:.1f} dB/oct) "
                           "— it will sound duller overall; try a gentle high shelf on the mix bus or trim the low end.")
        else:
            summary.append(f"{you} tilts {tilt:.1f} dB/oct brighter than {them} ({ta:.1f} vs {tb:.1f} dB/oct) "
                           "— it will sound thinner/brighter; ease the top end or add low-end weight.")

    # Dynamics
    da, db_ = ra["loudness"], rb["loudness"]
    crest = _diff(da.get("crest_db"), db_.get("crest_db"))
    if _over(crest, THRESHOLDS["crest_db"]):
        ca, cb = da["crest_db"], db_["crest_db"]
        if crest < 0:
            summary.append(f"{you} has {-crest:.1f} dB less crest factor than {them} ({ca:.1f} vs {cb:.1f} dB) "
                           "— it is more squashed; back off bus compression or the limiter to recover punch.")
        else:
            summary.append(f"{you} has {crest:.1f} dB more crest factor than {them} ({ca:.1f} vs {cb:.1f} dB) "
                           "— to match its density, add drum-bus compression or soft clipping before the limiter.")
    lra = _diff(da.get("loudness_range_lu"), db_.get("loudness_range_lu"))
    if _over(lra, THRESHOLDS["lra_lu"]):
        if lra < 0:
            summary.append(f"{you}'s loudness range is {-lra:.1f} LU narrower than {them}'s — sections vary less "
                           "in level; build contrast with automation or arrangement (breakdowns, drops).")
        else:
            summary.append(f"{you}'s loudness range is {lra:.1f} LU wider than {them}'s — levels swing more "
                           "between sections; ride the quiet parts up or add gentle bus compression.")

    # Stereo
    st_a, st_b = ra.get("stereo"), rb.get("stereo")
    stereo_d: Dict[str, Optional[float]] = {}
    if st_a and st_b:
        for key in WIDTH_ADVICE:
            stereo_d[key] = _diff(st_a.get(key), st_b.get(key))
        for key in ("correlation", "low_correlation"):
            stereo_d[key] = _diff(st_a.get(key), st_b.get(key), 3)
        for key, (where, wider, narrower) in WIDTH_ADVICE.items():
            d = stereo_d.get(key)
            if _over(d, THRESHOLDS["width_db"]):
                summary.append(f"{you} is {abs(d):.1f} dB {'wider' if d > 0 else 'narrower'} {where} than {them} "
                               f"— {wider if d > 0 else narrower}.")
        d = stereo_d.get("correlation")
        if _over(d, THRESHOLDS["correlation"]):
            ca, cb = st_a["correlation"], st_b["correlation"]
            if d < 0:
                summary.append(f"{you}'s L/R correlation is {-d:.2f} lower than {them}'s ({ca:.2f} vs {cb:.2f}) "
                               "— more out-of-phase content; check wideners and Haas delays in mono.")
            else:
                summary.append(f"{you}'s L/R correlation is {d:.2f} higher than {them}'s ({ca:.2f} vs {cb:.2f}) "
                               "— it is closer to mono; add stereo interest with panning or stereo effects.")

    # Groove
    swing_d: Dict[str, Optional[float]] = {}
    rh_a, rh_b = ra.get("rhythm", {}), rb.get("rhythm", {})
    for band, who in (("low", "kick/bass"), ("high", "hats/percussion")):
        ga, gb = rh_a.get(f"{band}_band"), rh_b.get(f"{band}_band")
        if not ga or not gb:
            continue
        d = _diff(ga.get("swing_percent"), gb.get("swing_percent"), 1)
        if d is None:
            continue
        swing_d[band] = d
        if _over(d, THRESHOLDS["swing_points"]):
            bpm = rh_a.get("bpm") or rh_b.get("bpm")
            # Swing points -> ms: d/100 * one 8th note (= 2 * 15000/bpm ms).
            shift = (f" (move off-16ths about {abs(d) / 100 * 2 * 15000 / bpm:.0f} ms "
                     f"{'earlier' if d > 0 else 'later'})") if bpm else ""
            summary.append(f"{you}'s {who} swing is {ga['swing_percent']:.1f}% vs {gb['swing_percent']:.1f}% in "
                           f"{them} — {'reduce' if d > 0 else 'add'} about {abs(d):.0f} points of swing on the "
                           f"{who}{shift}.")

    deltas = {
        "bands": band_d,
        "octave_bands": oct_d,
        "centroid_hz": _diff(sa.get("centroid_hz"), sb.get("centroid_hz"), 1),
        "tilt_db_per_oct": tilt,
        "crest_db": crest,
        "loudness_range_lu": lra,
        "stereo": stereo_d,
        "swing_percent": swing_d,
    }
    return {
        "labels": [la, lb],
        "integrated_lufs": {la: ia, lb: ib},
        "loudness_offset_db": offset,
        "note": SPECTRAL_NOTE,
        "deltas": deltas,
        "summary": summary,
    }
