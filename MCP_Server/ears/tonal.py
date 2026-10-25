"""Tonal content: chroma, key candidates (Krumhansl-Kessler) and chords per bar.

Chroma
------
STFT with an 8192-sample Hann window and 50 % hop. In each frame only
**spectral peaks** between 55 Hz and 5 kHz are used: local maxima within
-50 dB of the frame maximum. Each peak's frequency is refined by parabolic
interpolation on log magnitude and mapped to the nearest pitch class (A4 =
440 Hz). A peak's weight is its log-compressed magnitude,
``log1p(100 * |X| / sample_peak)``. Peak picking removes window sidelobes
and the smear between neighbouring bins, which matters for bass notes. The
compression stops a loud bassline from drowning out the chords above it.

Keys
----
The 12-bin chroma is Pearson-correlated with the Krumhansl-Kessler major and
minor profiles rotated to all 12 tonics. ``score`` is that correlation. The
relative major and minor (C major / A minor) often score close together;
treat the top two as a pair when the gap is small.

Chords
------
Per bar (4 beats from ``beat_offset_s``): sum the frame chroma, subtract the
bar's minimum (to remove the noise floor), and pick the binary template with
the highest cosine similarity. Templates are maj, min, 7, maj7, min7, sus4
and dim on every root. Sevenths are weighted 0.6, so a plain triad is not
mislabelled as a seventh chord. Note names use sharps.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

import numpy as np
from scipy import signal

from ._dsp import n_stft_frames, num, stft_chunks

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
KK_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
KK_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])

CHROMA_FFT = 8192
CHROMA_RANGE_HZ = (55.0, 5000.0)
PEAK_RANGE_DB = 50.0
SEVENTH_WEIGHT = 0.6

# (name suffix, semitone intervals above the root); 10 and 11 are sevenths.
CHORD_QUALITIES: List[Tuple[str, Tuple[int, ...]]] = [
    ("", (0, 4, 7)),
    ("m", (0, 3, 7)),
    ("7", (0, 4, 7, 10)),
    ("maj7", (0, 4, 7, 11)),
    ("m7", (0, 3, 7, 10)),
    ("sus4", (0, 5, 7)),
    ("dim", (0, 3, 6)),
]


def _chord_templates() -> Tuple[np.ndarray, List[str]]:
    rows, names = [], []
    for suffix, intervals in CHORD_QUALITIES:
        base = np.zeros(12)
        for iv in intervals:
            base[iv] = SEVENTH_WEIGHT if iv in (10, 11) else 1.0
        for root in range(12):
            rows.append(np.roll(base, root))
            names.append(NOTE_NAMES[root] + suffix)
    t = np.array(rows)
    return t / np.linalg.norm(t, axis=1, keepdims=True), names


_TEMPLATES, _TEMPLATE_NAMES = _chord_templates()


def frame_chroma(x: np.ndarray, sr: float, n_fft: int = CHROMA_FFT) -> Tuple[np.ndarray, np.ndarray]:
    """Per-frame chroma, shape ``(n_frames, 12)`` (unnormalised), plus frame centre times."""
    hop = n_fft // 2
    window = signal.get_window("hann", n_fft)
    scale = 2.0 / window.sum()
    ref = max(float(np.max(np.abs(x))) if x.size else 0.0, 1e-9)
    k_lo = max(2, int(math.floor(CHROMA_RANGE_HZ[0] * n_fft / sr)))
    k_hi = min(n_fft // 2 - 1, int(math.ceil(CHROMA_RANGE_HZ[1] * n_fft / sr)))
    n_frames = n_stft_frames(x.size, n_fft, hop)
    chroma = np.zeros((n_frames, 12))
    times = np.arange(n_frames) * hop / sr
    if k_hi <= k_lo:
        return chroma, times
    floor_ratio = 10 ** (-PEAK_RANGE_DB / 20.0)
    for start, spec in stft_chunks(x, n_fft, hop, window, chunk_frames=64):
        # Include one guard bin each side so edge bins can be tested as local maxima.
        mag = np.abs(spec[:, k_lo - 1:k_hi + 2]) * scale
        centre = mag[:, 1:-1]
        is_peak = (centre > mag[:, :-2]) & (centre >= mag[:, 2:])
        frame_max = centre.max(axis=1, keepdims=True)
        is_peak &= centre >= frame_max * floor_ratio
        is_peak &= centre > 1e-7
        f_idx, b_idx = np.nonzero(is_peak)
        if f_idx.size == 0:
            continue
        # Parabolic interpolation on log magnitude for the true peak frequency.
        la = np.log(mag[f_idx, b_idx] + 1e-12)
        lb = np.log(mag[f_idx, b_idx + 1] + 1e-12)
        lc = np.log(mag[f_idx, b_idx + 2] + 1e-12)
        denom = la - 2.0 * lb + lc
        safe = np.where(np.abs(denom) > 1e-12, denom, 1.0)
        delta = np.where(np.abs(denom) > 1e-12, 0.5 * (la - lc) / safe, 0.0)
        delta = np.clip(delta, -0.5, 0.5)
        freq = (k_lo + b_idx + delta) * sr / n_fft
        keep = (freq >= CHROMA_RANGE_HZ[0]) & (freq <= CHROMA_RANGE_HZ[1])
        if not np.any(keep):
            continue
        f_idx, freq = f_idx[keep], freq[keep]
        weight = np.log1p(100.0 * centre[f_idx, b_idx[keep]] / ref)
        pc = np.mod(np.round(69.0 + 12.0 * np.log2(freq / 440.0)).astype(int), 12)
        flat = np.bincount(f_idx * 12 + pc, weights=weight, minlength=12 * spec.shape[0])
        chroma[start:start + spec.shape[0]] += flat.reshape(-1, 12)
    return chroma, times


def _normalise_sum(v: np.ndarray, nd: int = 3) -> List[float]:
    """Round a distribution to ``nd`` decimals so it still sums to exactly 1."""
    total = float(v.sum())
    if total <= 0:
        return [0.0] * len(v)
    p = v / total
    r = np.round(p, nd)
    r[int(np.argmax(r))] += round(1.0 - float(r.sum()), nd)
    return [num(val, nd) for val in r]


def key_candidates(chroma: np.ndarray, top: int = 3) -> List[Dict]:
    """Top keys by Pearson correlation of chroma with rotated KK profiles."""
    if not np.any(chroma > 0) or np.allclose(chroma, chroma[0]):
        return []
    results = []
    for mode, profile in (("major", KK_MAJOR), ("minor", KK_MINOR)):
        for tonic in range(12):
            r = float(np.corrcoef(chroma, np.roll(profile, tonic))[0, 1])
            results.append((r, NOTE_NAMES[tonic], mode))
    results.sort(key=lambda t: -t[0])
    return [{"key": k, "mode": m, "score": num(r, 3)} for r, k, m in results[:top]]


def best_chord(chroma: np.ndarray) -> Tuple[Optional[str], float]:
    """Best chord template for a 12-bin chroma: ``(name, cosine similarity)``."""
    c = chroma - chroma.min()
    norm = float(np.linalg.norm(c))
    if norm <= 1e-12:
        return None, 0.0
    sims = _TEMPLATES @ (c / norm)
    i = int(np.argmax(sims))
    return _TEMPLATE_NAMES[i], float(sims[i])


def analyze_tonal(mid: np.ndarray, sr: float, bpm: Optional[float] = None, beat_offset_s: float = 0.0) -> Dict:
    """Tonal section of the report; ``chords_per_bar`` needs ``bpm``."""
    frames, times = frame_chroma(mid, sr)
    total = frames.sum(axis=0)
    out: Dict = {
        "chroma": _normalise_sum(total),
        "chroma_notes": NOTE_NAMES,
        "key_candidates": key_candidates(total),
    }
    if bpm:
        duration = mid.size / sr
        bar_s = 4.0 * 60.0 / float(bpm)
        chords = []
        b = 0
        while len(chords) < 512:
            start = beat_offset_s + b * bar_s
            if start + bar_s / 2.0 > duration:
                break
            b += 1
            if start + bar_s / 2.0 < 0:
                continue  # bar mostly before the audio starts
            sel = (times >= start) & (times < start + bar_s)
            name, conf = best_chord(frames[sel].sum(axis=0)) if np.any(sel) else (None, 0.0)
            chords.append({"bar": b, "chord": name, "confidence": num(conf, 2)})
        out["chords_per_bar"] = chords
    return out
