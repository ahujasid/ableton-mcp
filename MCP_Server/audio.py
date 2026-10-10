"""Record and analyze what Live is playing.

Live's API has no way to render audio, so we record its output from a loopback
device instead (macOS + ffmpeg):

  1. brew install ffmpeg blackhole-2ch
  2. In Audio MIDI Setup, create a Multi-Output Device with your speakers AND
     BlackHole 2ch, and pick it as Live's output (Settings -> Audio). You keep
     hearing playback while BlackHole receives a copy.

record() writes a WAV; analyze() turns a WAV into a few numbers a model can
reason about (levels, stereo balance, rough tonal balance). analyze() needs
numpy:  pip install "ableton-mcp[audio]"
"""

import math
import os
import re
import shutil
import subprocess
import tempfile
import time
import wave

DEFAULT_DEVICE = "BlackHole 2ch"
MAX_SECONDS = 30.0
MAX_ANALYZE_SECONDS = 120.0
SAMPLE_RATE = 44100

# Rough frequency bands, in Hz, for the tonal-balance summary.
BANDS = {"low": (20, 250), "mid": (250, 4000), "high": (4000, 20000)}


def _ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise RuntimeError("ffmpeg not found. Install it with: brew install ffmpeg")
    return path


def _input_devices() -> dict:
    """{name: avfoundation index} for the audio inputs ffmpeg can see."""
    proc = subprocess.run(
        [_ffmpeg(), "-hide_banner", "-f", "avfoundation", "-list_devices", "true", "-i", ""],
        capture_output=True, text=True, timeout=20,
    )
    # ffmpeg prints the list to stderr: a video section, then an audio section.
    audio_section = proc.stderr.split("audio devices:", 1)[-1] if "audio devices:" in proc.stderr else ""
    return {name: int(idx) for idx, name in re.findall(r"\[(\d+)\] (.+)", audio_section)}


def list_input_devices() -> list:
    """Names of the audio inputs ffmpeg can see, in avfoundation index order."""
    return list(_input_devices())


def record(seconds: float, device: str = DEFAULT_DEVICE, out_path: str = None) -> str:
    """Record `seconds` of the named input device to a stereo 16-bit WAV.
    Blocks until done and returns the file path.

    Capture starts roughly 0.5 s after the call (device lookup + ffmpeg
    startup), so whatever plays in that window is not recorded."""
    if not 0 < seconds <= MAX_SECONDS:
        raise ValueError(f"seconds must be between 0 and {MAX_SECONDS:g}")
    # Look the device up ourselves and pass its index: ffmpeg's own name
    # matching is by prefix, so ":BlackHole" would also open "BlackHole 64ch".
    devices = _input_devices()
    if device not in devices:
        raise RuntimeError(
            f"Audio input '{device}' not found. Available: {', '.join(devices) or 'none'}. "
            "Install BlackHole (brew install blackhole-2ch) and route Live's output to it "
            "through a Multi-Output Device."
        )
    if out_path is None:
        out_path = os.path.join(tempfile.gettempdir(), f"ableton_mcp_{int(time.time() * 1000)}.wav")

    proc = subprocess.run(
        [_ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
         "-f", "avfoundation", "-i", f":{devices[device]}",
         "-t", f"{seconds:.3f}", "-ac", "2", "-ar", str(SAMPLE_RATE), "-c:a", "pcm_s16le",
         out_path],
        capture_output=True, text=True, timeout=seconds + 30,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg failed: {proc.stderr.strip() or 'no output'}. If macOS blocked it, allow "
            "Microphone access for the app running this server (System Settings -> Privacy & "
            "Security -> Microphone)."
        )
    return out_path


def _db(x: float):
    # None rather than -inf for silence: json.dumps writes -inf as -Infinity,
    # which strict JSON parsers reject.
    return round(20 * math.log10(x), 1) if x > 0 else None


def analyze(path: str) -> dict:
    """Summarize a 16-bit PCM WAV: levels, stereo image and tonal balance.
    Only reads files in the temp directory, where record() writes."""
    tmp = os.path.realpath(tempfile.gettempdir())
    real = os.path.realpath(path)
    if os.path.commonpath([real, tmp]) != tmp:
        raise ValueError(f"Can only analyze recordings in the temp directory ({tmp})")
    try:
        import numpy as np
    except ImportError:
        raise RuntimeError('analyze_audio needs numpy: pip install "ableton-mcp[audio]"')

    with wave.open(path, "rb") as wav:
        if wav.getsampwidth() != 2:
            raise ValueError("Only 16-bit PCM WAV files are supported")
        rate, channels = wav.getframerate(), wav.getnchannels()
        if wav.getnframes() > MAX_ANALYZE_SECONDS * rate:
            raise ValueError(f"File is longer than {MAX_ANALYZE_SECONDS:g} seconds")
        frames = wav.readframes(wav.getnframes())
    samples = np.frombuffer(frames, dtype="<i2").astype(np.float64) / 32768.0
    samples = samples.reshape(-1, channels)
    if not samples.size:
        raise ValueError("File contains no audio")
    left, right = samples[:, 0], samples[:, -1]

    # Levels per channel, so a hard-panned source isn't diluted by a silent side.
    ch_peak = np.abs(samples).max(axis=0)
    ch_rms = np.sqrt(np.mean(samples ** 2, axis=0))
    peak = float(ch_peak.max())
    crests = [_db(p) - _db(r) for p, r in zip(ch_peak, ch_rms) if r > 0]
    result = {
        "duration_sec": round(len(samples) / rate, 2),
        "peak_dbfs": _db(peak),
        "rms_dbfs": _db(float(np.sqrt(np.mean(samples ** 2)))),  # averaged over channels
        "crest_factor_db": round(max(crests), 1) if crests else None,
        "clipped_samples": int(np.sum(np.abs(samples) >= 0.999)),
        "silent": peak < 1e-4,
    }
    if result["silent"]:
        result["hint"] = ("Nothing was captured. Is playback running and is Live's output "
                          "set to the Multi-Output Device that includes BlackHole?")
        return result

    if channels > 1:
        l_rms, r_rms = ch_rms[0], ch_rms[-1]
        result["balance_db"] = round(_db(r_rms) - _db(l_rms), 1) if l_rms > 0 and r_rms > 0 else None
        # 1 = mono, ~0 = wide, <0 = phase issues; undefined if one side is silent
        corr = np.corrcoef(left, right)[0, 1] if left.std() > 0 and right.std() > 0 else None
        result["stereo_correlation"] = round(float(corr), 2) if corr is not None else None

    # Sum per-channel spectra rather than the mono mix, so out-of-phase
    # material (which cancels in mono) still shows up.
    power = (np.abs(np.fft.rfft(samples, axis=0)) ** 2).sum(axis=1)
    freqs = np.fft.rfftfreq(len(samples), 1 / rate)
    energy = {name: float(power[(freqs >= lo) & (freqs < hi)].sum()) for name, (lo, hi) in BANDS.items()}
    total = sum(energy.values()) or 1.0
    result["band_energy_pct"] = {name: round(100 * e / total, 1) for name, e in energy.items()}
    result["spectral_centroid_hz"] = round(float((freqs * power).sum() / power.sum()))
    return result
