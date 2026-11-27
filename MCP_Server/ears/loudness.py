"""Loudness and level metering: ITU-R BS.1770-4 / EBU R128 / EBU Tech 3342.

K-weighting
-----------
The two K-weighting biquads are derived for any sample rate from the
published analog-prototype constants (Brecht De Man's fit of the BS.1770
filters, also used by libebur128 and pyloudnorm's ``"DeMan"`` class):

* stage 1, high shelf: +3.9998 dB, pole frequency 1681.97 Hz, Q 0.70718
* stage 2, high pass:  38.135 Hz, Q 0.50033

Both are mapped to z-domain coefficients with the bilinear transform,
pre-warped at the pole frequency. This is the cookbook (RBJ) shelf/high-pass
written in pole-frequency form. RBJ's own shelf formula places ``f0`` at the
shelf midpoint, which is why pyloudnorm's default class feeds it 1500 Hz.
At 48 kHz the result reproduces the coefficients printed in BS.1770-4 to
about 1e-9, and 997 Hz gets the +0.691 dB that the -0.691 constant cancels.

Gating (BS.1770-4): 400 ms blocks, 75 % overlap, absolute gate -70 LUFS,
relative gate -10 LU. Channel weights: 1.0 for L/R/C (and mono), 1.41 for
surround channels 4 and 5 of a 5-channel file.
"""

from __future__ import annotations

import math
from typing import Dict, Optional

import numpy as np
from scipy import signal

from ._dsp import amp_db, num, power_db

# Published K-weighting prototype constants (see module docstring).
_SHELF_F0 = 1681.974450955533
_SHELF_GAIN_DB = 3.999843853973347
_SHELF_Q = 0.7071752369554196
_HP_F0 = 38.13547087602444
_HP_Q = 0.5003270373238773

ABS_GATE_LUFS = -70.0
REL_GATE_LU = -10.0
LRA_REL_GATE_LU = -20.0


def k_weighting_sos(sr: float) -> np.ndarray:
    """Second-order sections (shape (2, 6)) of the BS.1770 K-weighting filter."""
    # Stage 1: high shelf. Analog prototype H(s) = (Vh s^2 + Vb s/Q + 1)/(s^2 + s/Q + 1)
    # with s normalised to the pole frequency, then the bilinear transform with K = tan(pi f0/fs).
    k = math.tan(math.pi * _SHELF_F0 / sr)
    vh = 10.0 ** (_SHELF_GAIN_DB / 20.0)
    vb = vh ** 0.4996667741545416
    a0 = 1.0 + k / _SHELF_Q + k * k
    shelf = [
        (vh + vb * k / _SHELF_Q + k * k) / a0,
        2.0 * (k * k - vh) / a0,
        (vh - vb * k / _SHELF_Q + k * k) / a0,
        1.0,
        2.0 * (k * k - 1.0) / a0,
        (1.0 - k / _SHELF_Q + k * k) / a0,
    ]
    # Stage 2: second-order high-pass with numerator (1, -2, 1), as published.
    k = math.tan(math.pi * _HP_F0 / sr)
    a0 = 1.0 + k / _HP_Q + k * k
    highpass = [1.0, -2.0, 1.0, 1.0, 2.0 * (k * k - 1.0) / a0, (1.0 - k / _HP_Q + k * k) / a0]
    return np.array([shelf, highpass])


def k_weight(x: np.ndarray, sr: float) -> np.ndarray:
    """Apply K-weighting to every channel of an ``(n, channels)`` signal."""
    return signal.sosfilt(k_weighting_sos(sr), x, axis=0)


def channel_weights(channels: int) -> np.ndarray:
    """BS.1770 channel gains: 1.0 for L/R/C/mono, 1.41 for 5.x surrounds."""
    g = np.ones(channels)
    if channels == 5:
        g[3:5] = 1.41
    return g


def _block_loudness(sq_cumsum: np.ndarray, weights: np.ndarray, block: int, hop: int) -> np.ndarray:
    """Loudness (LUFS) of every complete ``block``-sample window, ``hop`` apart.

    ``sq_cumsum`` is the cumulative sum of squared K-weighted samples with a
    leading zero row, shape ``(n + 1, channels)``. A signal shorter than one
    block is measured as a single block spanning all of it.
    """
    n = sq_cumsum.shape[0] - 1
    if n < block:
        z = (sq_cumsum[n] - sq_cumsum[0]) / max(n, 1)
        z = z[None, :]
    else:
        starts = np.arange(0, n - block + 1, hop)
        z = (sq_cumsum[starts + block] - sq_cumsum[starts]) / block
    power = np.maximum(z, 0.0) @ weights  # cumsum rounding can go a hair negative
    with np.errstate(divide="ignore"):
        return -0.691 + 10.0 * np.log10(power)


def _gated_integrated(block_lufs: np.ndarray) -> float:
    """BS.1770-4 two-stage gating over per-block loudness values."""
    above_abs = block_lufs[block_lufs > ABS_GATE_LUFS]
    if above_abs.size == 0:
        return float("-inf")
    rel_gate = 10.0 * np.log10(np.mean(10.0 ** (above_abs / 10.0))) + REL_GATE_LU
    gated = above_abs[above_abs > rel_gate]
    if gated.size == 0:
        return float("-inf")
    # Mean of block powers, where power = 10^((L + 0.691)/10); the 0.691 cancels.
    return float(10.0 * np.log10(np.mean(10.0 ** (gated / 10.0))))


def _loudness_range(short_term: np.ndarray) -> Optional[float]:
    """EBU Tech 3342 LRA from short-term (3 s) loudness values."""
    st = short_term[short_term > ABS_GATE_LUFS]
    if st.size == 0:
        return None
    rel_gate = 10.0 * np.log10(np.mean(10.0 ** (st / 10.0))) + LRA_REL_GATE_LU
    st = st[st >= rel_gate]
    if st.size == 0:
        return None
    return float(np.percentile(st, 95) - np.percentile(st, 10))


def _sq_cumsum(xk: np.ndarray) -> np.ndarray:
    cs = np.zeros((xk.shape[0] + 1, xk.shape[1]))
    np.cumsum(np.square(xk), axis=0, out=cs[1:])
    return cs


def integrated_loudness(x: np.ndarray, sr: float) -> float:
    """Gated integrated loudness in LUFS (``-inf`` for silence)."""
    x = np.asarray(x, dtype=np.float64)
    if x.ndim == 1:
        x = x[:, None]
    cs = _sq_cumsum(k_weight(x, sr))
    blocks = _block_loudness(cs, channel_weights(x.shape[1]), int(round(0.4 * sr)), int(round(0.1 * sr)))
    return _gated_integrated(blocks)


def true_peak(x: np.ndarray, oversample: int = 4, chunk: int = 1 << 16) -> float:
    """Linear true-peak amplitude: max |sample| after ``oversample``x polyphase upsampling.

    Uses :func:`scipy.signal.resample_poly` on overlapping chunks (64-sample
    context on each side, wider than the interpolation filter) so memory
    stays bounded while the result matches upsampling the whole signal.
    """
    x = np.asarray(x, dtype=np.float64)
    if x.ndim == 1:
        x = x[:, None]
    pad = 64
    n = x.shape[0]
    peak = float(np.max(np.abs(x))) if n else 0.0
    for c in range(x.shape[1]):
        col = x[:, c]
        for s in range(0, n, chunk):
            e = min(n, s + chunk)
            a, b = max(0, s - pad), min(n, e + pad)
            y = signal.resample_poly(col[a:b], oversample, 1)
            y = y[(s - a) * oversample:(e - a) * oversample]
            if y.size:
                peak = max(peak, float(np.max(np.abs(y))))
    return peak


def measure(x: np.ndarray, sr: float) -> Dict[str, Optional[float]]:
    """All loudness/level figures for ``x`` shaped ``(n, channels)``.

    Returns a JSON-ready dict (values rounded, ``None`` where undefined):

    * ``integrated_lufs``: BS.1770-4 gated loudness. ``None`` if every block
      is under the -70 LUFS gate.
    * ``short_term_max_lufs``: loudest 3 s window (100 ms hop). Renders
      shorter than 3 s are measured as one window.
    * ``loudness_range_lu``: EBU Tech 3342 (3 s windows, 100 ms hop, -70 LUFS
      absolute and -20 LU relative gates, 95th minus 10th percentile).
      ``None`` for renders shorter than 3 s.
    * ``true_peak_dbtp``: 4x oversampled peak over all channels.
    * ``sample_peak_dbfs``, ``rms_dbfs`` (power average over all channels; a
      full-scale sine is -3.01 dBFS), ``crest_db`` (sample peak minus RMS).
    """
    x = np.asarray(x, dtype=np.float64)
    if x.ndim == 1:
        x = x[:, None]
    weights = channel_weights(x.shape[1])
    cs = _sq_cumsum(k_weight(x, sr))
    hop = int(round(0.1 * sr))

    integrated = _gated_integrated(_block_loudness(cs, weights, int(round(0.4 * sr)), hop))
    st_block = int(round(3.0 * sr))
    short_term = _block_loudness(cs, weights, st_block, hop)
    finite_st = short_term[np.isfinite(short_term)]
    st_max = float(np.max(finite_st)) if finite_st.size else None
    lra = _loudness_range(short_term) if x.shape[0] >= st_block else None

    sample_peak = float(np.max(np.abs(x)))
    tp = true_peak(x)
    ms = float(np.mean(np.square(x)))
    sample_peak_db = amp_db(sample_peak)
    rms_db = power_db(ms)
    return {
        "integrated_lufs": num(integrated, 2),
        "short_term_max_lufs": num(st_max, 2),
        "loudness_range_lu": num(lra, 2),
        "true_peak_dbtp": num(amp_db(tp), 2),
        "sample_peak_dbfs": num(sample_peak_db, 2),
        "rms_dbfs": num(rms_db, 2),
        "crest_db": num(sample_peak_db - rms_db, 2) if ms > 0 else None,
    }
