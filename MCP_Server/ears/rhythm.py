"""Rhythm: onsets, tempo estimate, and groove (swing / timing) against a known grid.

Onset detection
---------------
1. **Spectral flux** on a 5 ms hop. Each band (full, low <150 Hz, high
   >5 kHz) has its own STFT window: about 40 ms for the low band, so it
   resolves bass frequencies, and about 10 ms for the high band. Magnitudes
   are log-compressed (``log1p(1000*|X|)``, full-scale sine = 1) and the
   positive frame-to-frame increase is averaged over the band's bins.
2. **Peak picking**: local maxima above a moving-average threshold (+/-100
   ms), at least 45 ms apart.
3. **Refinement**: a flux peak is only accurate to about half a window. Each
   onset is re-timed on the Hilbert envelope of the zero-phase band-filtered
   signal: within the window around the coarse time, find the envelope peak
   and the minimum before it. The onset is where the envelope first rises
   halfway from that minimum to the peak, interpolated to sub-sample
   precision.

Grid conventions (when ``bpm`` is given)
----------------------------------------
``beat_offset_s`` is the time of a downbeat (beat 0), in seconds from the
start of the analysed audio. Every onset is assigned to its nearest 16th.
Even 16ths (positions 0 and 0.5 of a beat) are **on-16ths**, odd ones (0.25
and 0.75) are **off-16ths**. Onsets more than 0.45 of a 16th from any grid
line are ignored as ambiguous (triplets, 32nds). The tolerance still catches
off-16ths swung up to about 72 %.

* ``*_mean_ms`` / ``*_std_ms``: signed offset from the straight grid
  (positive = late).
* ``swing_percent = 50 + mean_off16_delay / (2 * sixteenth) * 100``. The delay
  is measured against the *straight* grid, so 50 is straight and 58 is a
  typical MPC/Ableton swing. A constant render latency also shifts this
  figure. ``on16_mean_ms`` shows that latency, and ``beat_offset_s`` can
  compensate for it.
* ``timing_spread_ms``: pooled standard deviation of on- and off-16th
  offsets around their own means. It measures looseness independently of
  swing.
"""

from __future__ import annotations

import math
from typing import Dict, Optional

import numpy as np
from scipy import fft as sp_fft
from scipy import signal
from scipy.ndimage import gaussian_filter1d, uniform_filter1d

from ._dsp import n_stft_frames, next_pow2, num, stft_chunks

HOP_S = 0.005
TEMPO_RANGE_BPM = (70.0, 180.0)
LOW_BAND_HZ = 150.0
HIGH_BAND_HZ = 5000.0
GRID_TOLERANCE_16THS = 0.45
MIN_ONSET_GAP_S = 0.045

_LOG_GAIN = 1000.0
_NOVELTY_FLOOR = 0.02  # mean per-bin log increase; below this a band counts as silent


def _hop(sr: float) -> int:
    return max(1, int(round(HOP_S * sr)))


def spectral_flux(x: np.ndarray, sr: float, n_fft: int, hop: int, f_lo: float, f_hi: float) -> np.ndarray:
    """Log-magnitude spectral flux of ``x`` restricted to ``f_lo <= f < f_hi``.

    Frame ``i`` is centred at ``i * hop / sr`` seconds. Returns the mean
    positive log-magnitude increase per bin, one value per frame.
    """
    window = signal.get_window("hann", n_fft)
    scale = 2.0 / window.sum()
    k_lo = max(1, int(math.ceil(f_lo * n_fft / sr)))
    k_hi = min(n_fft // 2, int(math.ceil(f_hi * n_fft / sr)) - 1)
    n_frames = n_stft_frames(x.size, n_fft, hop)
    novelty = np.zeros(n_frames)
    if k_hi < k_lo:
        return novelty
    n_bins = k_hi - k_lo + 1
    prev = np.zeros((1, n_bins))  # the render is treated as preceded by silence
    for start, spec in stft_chunks(x, n_fft, hop, window):
        logm = np.log1p(_LOG_GAIN * scale * np.abs(spec[:, k_lo:k_hi + 1]))
        diff = np.diff(np.vstack([prev, logm]), axis=0)
        novelty[start:start + logm.shape[0]] = np.maximum(diff, 0.0).sum(axis=1) / n_bins
        prev = logm[-1:]
    return novelty


def pick_peaks(novelty: np.ndarray, fps: float) -> np.ndarray:
    """Frame indices of onset peaks in a novelty curve (empty if the band is silent)."""
    if novelty.size < 3:
        return np.zeros(0, dtype=int)
    peak = float(novelty.max())
    if peak < _NOVELTY_FLOOR:
        return np.zeros(0, dtype=int)
    n = novelty / peak
    w = max(1, int(round(0.1 * fps)))
    threshold = np.maximum(uniform_filter1d(n, 2 * w + 1, mode="nearest") + 0.05, 0.08)
    # Lead with a zero so an onset right at t=0 (frame 0) can register as a peak.
    padded = np.concatenate([[0.0], n])
    idx, _ = signal.find_peaks(padded, height=np.concatenate([[np.inf], threshold]),
                               distance=max(1, int(round(MIN_ONSET_GAP_S * fps))))
    return idx - 1


def _hilbert_envelope(y: np.ndarray, sr: float, chunk: int = 1 << 18) -> np.ndarray:
    """Amplitude envelope via the analytic signal, computed on overlapping chunks."""
    n = y.size
    pad = int(0.25 * sr)
    env = np.empty(n)
    for s in range(0, n, chunk):
        e = min(n, s + chunk)
        a, b = max(0, s - pad), min(n, e + pad)
        seg = y[a:b]
        analytic = signal.hilbert(seg, N=sp_fft.next_fast_len(seg.size))[:seg.size]
        env[s:e] = np.abs(analytic[s - a:e - a])
    return env


def band_envelope(x: np.ndarray, sr: float, band: str) -> np.ndarray:
    """Smoothed amplitude envelope of the low (<150 Hz) or high (>5 kHz) band, zero-phase."""
    if band == "low":
        sos = signal.butter(4, LOW_BAND_HZ, btype="low", fs=sr, output="sos")
        smooth_s = 0.002
    else:
        sos = signal.butter(4, min(HIGH_BAND_HZ, 0.45 * sr), btype="high", fs=sr, output="sos")
        smooth_s = 0.001
    y = signal.sosfiltfilt(sos, x)
    env = _hilbert_envelope(y, sr)
    size = max(1, int(round(smooth_s * sr)))
    return uniform_filter1d(env, size, mode="nearest") if size > 1 else env


def refine_onsets(coarse_s: np.ndarray, env: np.ndarray, sr: float, n_fft: int) -> np.ndarray:
    """Re-time coarse onsets on a band envelope (half-rise point, see module docstring)."""
    if coarse_s.size == 0:
        return coarse_s
    half = n_fft / 2.0 / sr + 0.010
    n = env.size
    out = np.empty(coarse_s.size)
    for i, c in enumerate(coarse_s):
        lo, hi = c - half, c + half
        if i > 0:
            lo = max(lo, 0.5 * (coarse_s[i - 1] + c))
        if i < coarse_s.size - 1:
            hi = min(hi, 0.5 * (c + coarse_s[i + 1]))
        a, b = max(0, int(lo * sr)), min(n, int(math.ceil(hi * sr)) + 1)
        if b - a < 3:
            out[i] = c
            continue
        seg = env[a:b]
        p = int(np.argmax(seg))
        m = int(np.argmin(seg[:p + 1]))
        base, top = seg[m], seg[p]
        if top - base <= 1e-9 or top <= 0:
            out[i] = c
            continue
        thr = base + 0.5 * (top - base)
        j = m + int(np.argmax(seg[m:p + 1] >= thr))
        if j > 0 and seg[j] > seg[j - 1]:
            frac = (thr - seg[j - 1]) / (seg[j] - seg[j - 1])
            pos = (j - 1) + float(np.clip(frac, 0.0, 1.0))
        else:
            pos = float(j)
        out[i] = (a + pos) / sr
    out.sort()
    # Collapse double detections of one event.
    keep = np.concatenate([[True], np.diff(out) > 0.025])
    return out[keep]


def estimate_tempo(novelty: np.ndarray, fps: float) -> Optional[float]:
    """Tempo (BPM, 70-180) from the autocorrelation of the onset envelope.

    Each candidate scores ``ac(T) + 0.5*ac(2T) + 0.25*ac(4T)``, weighted by a
    log-normal prior centred on 120 BPM (one-octave spread). The prior
    resolves the octave ambiguity that evenly spaced 16ths would leave.
    """
    if novelty.size < 2 * fps or not np.any(novelty > 0):
        return None
    x = gaussian_filter1d(novelty, 2.0)
    x = x - x.mean()
    n = x.size
    nfft = sp_fft.next_fast_len(2 * n)
    spec = sp_fft.rfft(x, nfft)
    ac = sp_fft.irfft(spec * np.conj(spec), nfft)[:n]
    if ac[0] <= 0:
        return None
    ac = ac / ac[0]
    bpms = np.arange(TEMPO_RANGE_BPM[0], TEMPO_RANGE_BPM[1] + 1e-9, 0.1)
    lags = 60.0 / bpms * fps
    grid = np.arange(n)

    def at(lag):
        return np.interp(lag, grid, ac, right=0.0)

    score = at(lags) + 0.5 * at(2 * lags) + 0.25 * at(4 * lags)
    prior = np.exp(-0.5 * np.log2(bpms / 120.0) ** 2)
    weighted = np.maximum(score, 0.0) * prior
    if not np.any(weighted > 0):
        return None
    return float(bpms[int(np.argmax(weighted))])


def grid_stats(times_s: np.ndarray, bpm: float, beat_offset_s: float) -> Dict:
    """Offsets of onsets from a straight 16th grid, swing and spread (see module docstring)."""
    s16 = 60.0 / bpm / 4.0
    u = (np.asarray(times_s) - beat_offset_s) / s16
    k = np.round(u)
    dev_ms = (u - k) * s16 * 1000.0
    ok = np.abs(u - k) <= GRID_TOLERANCE_16THS
    parity = np.mod(k, 2)
    on, off = dev_ms[ok & (parity == 0)], dev_ms[ok & (parity == 1)]
    beat = dev_ms[ok & (np.mod(k, 4) == 0)]

    def mean(v):
        return float(np.mean(v)) if v.size else None

    def std(v):
        return float(np.std(v)) if v.size else None

    spread = None
    if on.size + off.size:
        ss = (np.sum((on - on.mean()) ** 2) if on.size else 0.0) + \
             (np.sum((off - off.mean()) ** 2) if off.size else 0.0)
        spread = math.sqrt(ss / (on.size + off.size))
    swing = 50.0 + float(np.mean(off)) / (2.0 * s16 * 1000.0) * 100.0 if off.size else None
    return {
        "onsets": int(np.size(times_s)),
        "on16_count": int(on.size),
        "on16_mean_ms": num(mean(on), 2),
        "on16_std_ms": num(std(on), 2),
        "off16_count": int(off.size),
        "off16_mean_ms": num(mean(off), 2),
        "off16_std_ms": num(std(off), 2),
        "swing_percent": num(swing, 1),
        "timing_spread_ms": num(spread, 2),
        "_beat_mean_ms": mean(beat),
    }


def detect_band_onsets(mid: np.ndarray, sr: float, band: str) -> np.ndarray:
    """Refined onset times (seconds) in the ``"low"`` or ``"high"`` band."""
    hop = _hop(sr)
    if band == "low":
        n_fft = next_pow2(0.040 * sr)
        f_lo, f_hi = 20.0, LOW_BAND_HZ
    else:
        n_fft = next_pow2(0.010 * sr)
        f_lo, f_hi = min(HIGH_BAND_HZ, 0.45 * sr), sr / 2.0 + 1.0
    nov = spectral_flux(mid, sr, n_fft, hop, f_lo, f_hi)
    coarse = pick_peaks(nov, sr / hop) * hop / sr
    if coarse.size == 0:
        return coarse
    return refine_onsets(coarse, band_envelope(mid, sr, band), sr, n_fft)


def analyze_rhythm(mid: np.ndarray, sr: float, bpm: Optional[float] = None, beat_offset_s: float = 0.0) -> Dict:
    """Rhythm section of the report. Grid metrics need ``bpm``."""
    hop = _hop(sr)
    fps = sr / hop
    full_nov = spectral_flux(mid, sr, next_pow2(0.020 * sr), hop, 30.0, min(16000.0, sr / 2.0))
    out: Dict = {
        "onset_count": int(pick_peaks(full_nov, fps).size),
        "tempo_estimate_bpm": num(estimate_tempo(full_nov, fps), 1),
    }
    if not bpm:
        return out

    out["bpm"] = num(bpm, 3)
    out["beat_offset_s"] = num(beat_offset_s, 4)
    stats = {}
    for band, label in (("low", "<150 Hz (kick/bass)"), ("high", ">5 kHz (hats/shakers)")):
        st = grid_stats(detect_band_onsets(mid, sr, band), float(bpm), float(beat_offset_s))
        st["range"] = label
        stats[band] = st
    beat_mean = stats["low"].pop("_beat_mean_ms")
    stats["high"].pop("_beat_mean_ms")
    if beat_mean is None:
        beat_mean = stats["low"]["on16_mean_ms"]
    out["low_band"] = stats["low"]
    out["high_band"] = stats["high"]
    out["kick_grid_offset_ms"] = num(beat_mean, 2)
    return out
