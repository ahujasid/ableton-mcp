"""ears: audio analysis that gives an assistant something like hearing.

The assistant renders part of a song (resampled in real time inside Ableton
Live) to a WAV/AIFF file. This package measures it and compares it with
reference tracks, so the assistant can reason about loudness, spectral
balance, stereo image, groove and key without listening.

Runtime dependencies: numpy, scipy, soundfile.

Public API::

    load_audio(path, start_s=None, end_s=None) -> (samples[n, ch] float64, sample_rate)
    analyze(source, sr=None, start_s=None, end_s=None, bpm=None, beat_offset_s=0.0) -> dict
    compare(a, b, labels=("mix", "reference")) -> dict

``analyze()`` and ``compare()`` return JSON-serialisable dicts. Conventions
(relative band dB, tilt sign, width scale, swing definition) are documented
in the ``spectrum``, ``stereo`` and ``rhythm`` modules.
"""

from .audio import load_audio
from .report import THRESHOLDS, analyze, compare

__all__ = ["load_audio", "analyze", "compare", "THRESHOLDS"]
