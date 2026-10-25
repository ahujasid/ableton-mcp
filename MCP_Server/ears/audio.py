"""Audio input: read WAV/AIFF files and normalise array inputs.

All analysis code works on float64 arrays shaped ``(n_samples, channels)``;
mono material stays ``(n, 1)``.
"""

from __future__ import annotations

import os
from typing import Optional, Tuple, Union

import numpy as np
import soundfile as sf

PathLike = Union[str, "os.PathLike[str]"]


def load_audio(
    path: PathLike,
    start_s: Optional[float] = None,
    end_s: Optional[float] = None,
) -> Tuple[np.ndarray, int]:
    """Read an audio file (WAV, AIFF, FLAC, ... anything libsndfile reads).

    Integer and float encodings are both returned as float64 in [-1, 1]
    (float files may exceed that range; values are passed through).

    Args:
        path: File path.
        start_s: Optional start time in seconds (default: file start).
        end_s: Optional end time in seconds (default: file end).

    Returns:
        ``(samples, sample_rate)`` with ``samples`` shaped ``(n, channels)``.

    Raises:
        ValueError: missing, empty or unreadable file, or an empty time range.
    """
    p = os.fspath(path)
    if not os.path.isfile(p):
        raise ValueError(f"Audio file not found: {p}")
    if os.path.getsize(p) == 0:
        raise ValueError(f"Audio file is empty (0 bytes): {p}")
    try:
        info = sf.info(p)
    except Exception as exc:  # libsndfile raises its own error types
        raise ValueError(f"Could not read audio file {p}: {exc}") from exc

    sr = int(info.samplerate)
    if start_s is not None and start_s < 0:
        raise ValueError("start_s must be >= 0")
    if start_s is not None and end_s is not None and end_s <= start_s:
        raise ValueError("end_s must be greater than start_s")
    start = 0 if start_s is None else int(round(start_s * sr))
    stop = None if end_s is None else int(round(end_s * sr))

    try:
        data, sr = sf.read(p, dtype="float64", always_2d=True, start=start, stop=stop)
    except Exception as exc:
        raise ValueError(f"Could not decode audio file {p}: {exc}") from exc
    if data.shape[0] == 0:
        raise ValueError(
            f"No audio samples in {p} (empty file, or start/end range outside the file; "
            f"file length is {info.frames / max(sr, 1):.2f} s)"
        )
    return np.ascontiguousarray(data), int(sr)


def as_frames(
    data: np.ndarray,
    sr: Optional[float],
    start_s: Optional[float] = None,
    end_s: Optional[float] = None,
) -> Tuple[np.ndarray, int]:
    """Validate an in-memory signal and return it as ``(n, channels)`` float64.

    A 1-D array is treated as mono. A 2-D array is expected as
    ``(n, channels)``; an array that is clearly ``(channels, n)`` (at most 8
    rows and more columns than rows) is transposed.
    """
    if sr is None or sr <= 0:
        raise ValueError("sr (sample rate) is required when analysing an array")
    x = np.asarray(data, dtype=np.float64)
    if x.ndim == 1:
        x = x[:, None]
    elif x.ndim == 2:
        if x.shape[0] <= 8 and x.shape[1] > x.shape[0]:
            x = x.T
    else:
        raise ValueError(f"Audio array must be 1-D or 2-D, got shape {x.shape}")
    if not np.all(np.isfinite(x)):
        raise ValueError("Audio array contains NaN or infinite values")
    sr = int(round(sr))
    if start_s is not None or end_s is not None:
        a = 0 if start_s is None else max(0, int(round(start_s * sr)))
        b = x.shape[0] if end_s is None else int(round(end_s * sr))
        x = x[a:b]
    if x.shape[0] == 0:
        raise ValueError("Audio array is empty (or the start/end range selects nothing)")
    return np.ascontiguousarray(x), sr
