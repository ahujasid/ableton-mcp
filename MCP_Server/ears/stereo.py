"""Stereo image: L/R correlation and side-vs-mid energy, overall and per band.

``width_db = 10*log10(E_side / E_mid)`` with ``mid = (L+R)/2`` and
``side = (L-R)/2``. 0 dB means as much side as mid energy (very wide).
About -10 dB is a typically wide mix, below -20 dB is narrow, and identical
channels sit at the -100 dB floor. Inverted channels give +100.

Band splits use 4th-order Butterworth filters (``sosfilt``). The phase shift
is identical on both channels, so correlation and width are unaffected.
"""

from __future__ import annotations

from typing import Dict, Optional

import numpy as np
from scipy import signal

from ._dsp import num

LOW_SPLIT_HZ = 150.0
HIGH_SPLIT_HZ = 5000.0
_WIDTH_FLOOR = 1e-10  # relative floor -> width clamps to +/-100 dB


def correlation(left: np.ndarray, right: np.ndarray) -> Optional[float]:
    """Pearson correlation of L and R; ``None`` when either channel is silent."""
    l = left - left.mean()
    r = right - right.mean()
    denom = np.sqrt(np.dot(l, l) * np.dot(r, r))
    if denom <= 1e-20 * max(l.size, 1):
        return None
    return float(np.dot(l, r) / denom)


def width_db(left: np.ndarray, right: np.ndarray) -> Optional[float]:
    """Side energy minus mid energy, in dB (clamped to +/-100)."""
    m = 0.5 * (left + right)
    s = 0.5 * (left - right)
    em, es = float(np.dot(m, m)), float(np.dot(s, s))
    total = em + es
    if total <= 1e-20 * max(left.size, 1):
        return None
    floor = _WIDTH_FLOOR * total
    return float(10.0 * np.log10((es + floor) / (em + floor)))


def analyze_stereo(x: np.ndarray, sr: float) -> Dict:
    """Stereo metrics for a 2-channel ``(n, 2)`` signal."""
    left, right = x[:, 0], x[:, 1]

    lp =signal.butter(4, LOW_SPLIT_HZ, btype="low", fs=sr, output="sos")
    low = signal.sosfilt(lp, x, axis=0)
    low_corr = correlation(low[:, 0], low[:, 1])

    hi_edge = min(HIGH_SPLIT_HZ, 0.45 * sr)
    bp = signal.butter(4, [LOW_SPLIT_HZ, hi_edge], btype="band", fs=sr, output="sos")
    mid_band = signal.sosfilt(bp, x, axis=0)

    high_w = None
    if HIGH_SPLIT_HZ < 0.45 * sr:
        hp = signal.butter(4, HIGH_SPLIT_HZ, btype="high", fs=sr, output="sos")
        high = signal.sosfilt(hp, x, axis=0)
        high_w = width_db(high[:, 0], high[:, 1])

    return {
        "correlation": num(correlation(left, right), 3),
        "width_db": num(width_db(left, right), 2),
        "low_correlation": num(low_corr, 3),
        "low_width_db": num(width_db(low[:, 0], low[:, 1]), 2),
        "mid_width_db": num(width_db(mid_band[:, 0], mid_band[:, 1]), 2),
        "high_width_db": num(high_w, 2),
        # No low end at all cannot cancel in mono, so that counts as OK.
        "mono_compat_ok": bool(low_corr is None or low_corr > 0.7),
    }
