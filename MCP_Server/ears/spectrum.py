"""Long-term spectral balance from a Welch PSD of the mid signal.

Conventions
-----------
* All band values are **relative**: ``db = 10*log10(band_energy / total)``
  where ``total`` is the energy between 20 Hz and 20 kHz (or Nyquist). The
  seven named bands tile 20 Hz-20 kHz, so their linear shares sum to 1.
  Because of this normalisation, spectral comparisons between two renders
  are inherently loudness-matched.
* ``tilt_db_per_oct`` is the slope of the **power spectral density** (energy
  per Hz) against octaves, fitted to the 63 Hz-8 kHz octave bands. White noise
  is 0 dB/oct, pink noise -3 dB/oct, and commercial mixes often land around
  -4 to -6 dB/oct. Negative means darker. This equals the slope of
  the ``octave_bands`` energy values minus 3.01 dB/oct, because each octave
  is twice as wide as the one below it.
* ``centroid_hz`` is power-weighted, over 20 Hz-20 kHz.
* ``rolloff85_hz`` is the frequency below which 85 % of the 20 Hz-20 kHz
  energy lies.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from scipy import fft as sp_fft
from scipy import signal

from ._dsp import EPS, next_pow2, num, power_db

BANDS: List[Tuple[str, float, float]] = [
    ("sub", 20.0, 60.0),
    ("bass", 60.0, 250.0),
    ("low_mid", 250.0, 500.0),
    ("mid", 500.0, 2000.0),
    ("presence", 2000.0, 5000.0),
    ("brilliance", 5000.0, 10000.0),
    ("air", 10000.0, 20000.0),
]

# Ten octave bands on exact base-2 centres (1 kHz * 2^k), nominal labels.
OCTAVE_BANDS: List[Tuple[str, float]] = [
    (label, 1000.0 * 2.0 ** k)
    for k, label in zip(range(-5, 5), ["31.5", "63", "125", "250", "500", "1k", "2k", "4k", "8k", "16k"])
]
TILT_RANGE_HZ = (60.0, 8500.0)  # selects the 63 Hz ... 8 kHz octave centres
TOTAL_RANGE_HZ = (20.0, 20000.0)


def welch_psd(x: np.ndarray, sr: float, nperseg: Optional[int] = None) -> Tuple[np.ndarray, np.ndarray]:
    """One-sided Welch PSD (Hann window, 50 % overlap, per-segment mean removed).

    Segments are processed in batches, so memory stays bounded on long files.
    The default segment length gives about 3 Hz resolution (16384 points at
    44.1/48 kHz) so the 20-60 Hz sub band spans more than ten bins.
    """
    x = np.asarray(x, dtype=np.float64)
    if nperseg is None:
        nperseg = next_pow2(sr / 3.0)
    nperseg = int(min(nperseg, x.size))
    nperseg = max(nperseg, 16)
    if x.size < nperseg:
        x = np.pad(x, (0, nperseg - x.size))
    hop = max(1, nperseg // 2)
    window = signal.get_window("hann", nperseg)
    frames = sliding_window_view(x, nperseg)[::hop]
    acc = np.zeros(nperseg // 2 + 1)
    for s in range(0, frames.shape[0], 64):
        block = frames[s:s + 64]
        block = (block - block.mean(axis=1, keepdims=True)) * window
        acc += np.sum(np.abs(sp_fft.rfft(block, axis=1)) ** 2, axis=0)
    psd = acc / (frames.shape[0] * sr * np.sum(window ** 2))
    psd[1:-1] *= 2.0  # one-sided
    freqs = np.arange(psd.size) * sr / nperseg
    return freqs, psd


def _overlap_weights(freqs: np.ndarray, lo: float, hi: float) -> np.ndarray:
    """Fraction of each PSD bin (bin k spans f_k +/- df/2) that lies inside [lo, hi)."""
    df = freqs[1] - freqs[0]
    left = np.maximum(freqs - df / 2.0, lo)
    right = np.minimum(freqs + df / 2.0, hi)
    return np.clip((right - left) / df, 0.0, 1.0)


def band_energy(freqs: np.ndarray, psd: np.ndarray, lo: float, hi: float) -> float:
    return float(np.sum(psd * _overlap_weights(freqs, lo, hi)))


def analyze_spectrum(mid: np.ndarray, sr: float) -> Dict:
    """Spectral balance of a mono (mid) signal. See the module docstring for conventions."""
    freqs, psd = welch_psd(mid, sr)
    nyq = sr / 2.0
    t_lo, t_hi = TOTAL_RANGE_HZ[0], min(TOTAL_RANGE_HZ[1], nyq)
    total = band_energy(freqs, psd, t_lo, t_hi)
    silent = total <= EPS * 1e-6

    def rel_db(lo: float, hi: float) -> Optional[float]:
        if lo >= nyq or silent:
            return None
        return power_db(band_energy(freqs, psd, lo, min(hi, nyq)) / total)

    bands = [
        {"name": name, "lo_hz": lo, "hi_hz": hi, "db": num(rel_db(lo, hi), 2)}
        for name, lo, hi in BANDS
    ]

    octaves = []
    fit_x, fit_y = [], []
    for label, fc in OCTAVE_BANDS:
        lo, hi = fc / np.sqrt(2.0), fc * np.sqrt(2.0)
        db = rel_db(lo, hi)
        octaves.append({"name": label, "centre_hz": num(fc, 1), "lo_hz": num(lo, 1),
                        "hi_hz": num(hi, 1), "db": num(db, 2)})
        if db is not None and TILT_RANGE_HZ[0] <= fc <= TILT_RANGE_HZ[1] and hi <= nyq:
            # Energy per Hz: subtract 10*log10(bandwidth) so the slope describes the PSD.
            fit_x.append(np.log2(fc))
            fit_y.append(db - 10.0 * np.log10(hi - lo))
    tilt = float(np.polyfit(fit_x, fit_y, 1)[0]) if len(fit_x) >= 3 and not silent else None

    centroid = rolloff = None
    if not silent:
        w = psd * _overlap_weights(freqs, t_lo, t_hi)
        centroid = float(np.sum(freqs * w) / np.sum(w))
        cum = np.cumsum(w)
        target = 0.85 * cum[-1]
        k = int(np.searchsorted(cum, target))
        # Interpolate inside the bin that crosses 85 %.
        prev = cum[k - 1] if k > 0 else 0.0
        frac = (target - prev) / max(cum[k] - prev, EPS)
        df = freqs[1] - freqs[0]
        rolloff = float(freqs[k] - df / 2.0 + frac * df)
        rolloff = min(max(rolloff, t_lo), t_hi)

    return {
        "bands": bands,
        "octave_bands": octaves,
        "centroid_hz": num(centroid, 1),
        "rolloff85_hz": num(rolloff, 1),
        "tilt_db_per_oct": num(tilt, 2),
    }
