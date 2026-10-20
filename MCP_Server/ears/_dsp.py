"""Shared DSP and formatting helpers for the ``ears`` analysis modules.

Everything here is deliberately small and dependency-light (numpy + scipy).
The STFT helper processes frames in chunks so that long renders never
materialise a full frames-by-bins matrix in memory.
"""

from __future__ import annotations

import math
from typing import Iterator, Optional, Tuple

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from scipy import fft as sp_fft

# Power floor used when converting to dB, so silence maps to a finite value.
EPS = 1e-12


def num(value, nd: int = 2) -> Optional[float]:
    """Round to a plain Python float; ``None`` for missing / NaN / infinite."""
    if value is None:
        return None
    v = float(value)
    if not math.isfinite(v):
        return None
    r = round(v, nd)
    return 0.0 if r == 0 else r  # avoid "-0.0" in JSON


def power_db(power, floor_db: float = -120.0) -> float:
    """10*log10 of a power ratio, clamped at ``floor_db``."""
    p = float(power)
    if not math.isfinite(p) or p <= 10 ** (floor_db / 10.0):
        return floor_db
    return 10.0 * math.log10(p)


def amp_db(amplitude, floor_db: float = -120.0) -> float:
    """20*log10 of an amplitude ratio, clamped at ``floor_db``."""
    a = float(abs(amplitude))
    if not math.isfinite(a) or a <= 10 ** (floor_db / 20.0):
        return floor_db
    return 20.0 * math.log10(a)


def next_pow2(n: float) -> int:
    """Smallest power of two >= n (and >= 2)."""
    return max(2, 1 << int(math.ceil(math.log2(max(2.0, float(n))))))


def stft_chunks(
    x: np.ndarray,
    n_fft: int,
    hop: int,
    window: np.ndarray,
    center: bool = True,
    chunk_frames: int = 256,
) -> Iterator[Tuple[int, np.ndarray]]:
    """Yield ``(first_frame_index, complex_spectra)`` for successive frame chunks.

    Frames are ``n_fft`` long, spaced ``hop`` samples apart. With
    ``center=True`` the signal is zero-padded by ``n_fft // 2`` on both sides,
    so frame ``i`` is centred on sample ``i * hop`` (time ``i * hop / sr``).
    ``complex_spectra`` has shape ``(frames_in_chunk, n_fft // 2 + 1)``.
    """
    x = np.asarray(x, dtype=np.float64)
    if center:
        x = np.pad(x, (n_fft // 2, n_fft // 2))
    if x.size < n_fft:
        x = np.pad(x, (0, n_fft - x.size))
    frames = sliding_window_view(x, n_fft)[::hop]  # zero-copy view
    n_frames = frames.shape[0]
    for start in range(0, n_frames, chunk_frames):
        block = frames[start:start + chunk_frames] * window
        yield start, sp_fft.rfft(block, axis=1)


def n_stft_frames(n_samples: int, n_fft: int, hop: int, center: bool = True) -> int:
    """Number of frames :func:`stft_chunks` yields for a signal of this length."""
    padded = n_samples + (2 * (n_fft // 2) if center else 0)
    padded = max(padded, n_fft)
    return 1 + (padded - n_fft) // hop
