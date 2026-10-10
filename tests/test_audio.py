"""
Tests for MCP_Server.audio (record_audio / analyze_audio).
ffmpeg is mocked and the WAVs are generated here, so they run anywhere — no
Ableton, no BlackHole, no audio hardware.

Run from the repo root:
    uv run --extra audio pytest -v tests/test_audio.py
"""

import json
import math
import struct
import subprocess
import wave

import pytest

from MCP_Server import audio

np = pytest.importorskip("numpy")


def write_wav(path, left, right=None, rate=44100):
    """Write float samples in [-1, 1] as a 16-bit stereo WAV."""
    right = left if right is None else right
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        frames = b"".join(
            struct.pack("<hh", int(l * 32767), int(r * 32767)) for l, r in zip(left, right)
        )
        wav.writeframes(frames)
    return str(path)


def sine(freq, seconds=0.5, amp=0.5, rate=44100):
    return [amp * math.sin(2 * math.pi * freq * i / rate) for i in range(int(seconds * rate))]


# --------------------------------------------------------------------------
# analyze
# --------------------------------------------------------------------------

def test_analyze_sine_levels(tmp_path):
    result = audio.analyze(write_wav(tmp_path / "a.wav", sine(1000, amp=0.5)))
    assert result["peak_dbfs"] == pytest.approx(-6.0, abs=0.2)
    assert result["rms_dbfs"] == pytest.approx(-9.0, abs=0.2)  # sine RMS = peak - 3 dB
    assert result["clipped_samples"] == 0
    assert result["silent"] is False
    assert result["stereo_correlation"] == pytest.approx(1.0)
    assert result["balance_db"] == pytest.approx(0.0)


def test_analyze_bands(tmp_path):
    low = audio.analyze(write_wav(tmp_path / "low.wav", sine(80)))
    high = audio.analyze(write_wav(tmp_path / "high.wav", sine(8000)))
    assert low["band_energy_pct"]["low"] > 95
    assert high["band_energy_pct"]["high"] > 95
    assert low["spectral_centroid_hz"] < high["spectral_centroid_hz"]


def test_analyze_detects_phase_and_balance(tmp_path):
    left = sine(440)
    inverted = audio.analyze(write_wav(tmp_path / "inv.wav", left, [-x for x in left]))
    assert inverted["stereo_correlation"] == pytest.approx(-1.0)
    quieter_right = audio.analyze(write_wav(tmp_path / "bal.wav", left, [x / 2 for x in left]))
    assert quieter_right["balance_db"] == pytest.approx(-6.0, abs=0.2)


def test_analyze_hard_panned_crest_factor(tmp_path):
    # A sine has a 3 dB crest factor wherever it's panned; the silent right
    # channel must not drag the RMS down.
    left = sine(1000, amp=0.5)
    result = audio.analyze(write_wav(tmp_path / "hl.wav", left, [0.0] * len(left)))
    assert result["crest_factor_db"] == pytest.approx(3.0, abs=0.1)
    assert result["balance_db"] is None
    assert result["stereo_correlation"] is None


def test_analyze_silence_gives_hint(tmp_path):
    result = audio.analyze(write_wav(tmp_path / "s.wav", [0.0] * 4410))
    json.dumps(result, allow_nan=False)  # no -Infinity in the output
    assert result["peak_dbfs"] is None
    assert result["silent"] is True
    assert "BlackHole" in result["hint"]
    assert "band_energy_pct" not in result


def test_analyze_counts_clipping(tmp_path):
    result = audio.analyze(write_wav(tmp_path / "c.wav", [1.0] * 10 + [0.1] * 1000))
    assert result["clipped_samples"] == 20  # 10 frames x 2 channels


def test_analyze_rejects_files_outside_temp_dir(tmp_path, monkeypatch):
    path = write_wav(tmp_path / "a.wav", sine(440))
    other = tmp_path / "elsewhere"
    other.mkdir()
    monkeypatch.setattr(audio.tempfile, "gettempdir", lambda: str(other))
    with pytest.raises(ValueError, match="temp directory"):
        audio.analyze(path)
    with pytest.raises(ValueError, match="temp directory"):
        audio.analyze(str(other / ".." / "a.wav"))  # no escaping via ..


def test_analyze_rejects_long_files(tmp_path, monkeypatch):
    monkeypatch.setattr(audio, "MAX_ANALYZE_SECONDS", 0.1)
    with pytest.raises(ValueError, match="longer than"):
        audio.analyze(write_wav(tmp_path / "long.wav", sine(440, seconds=0.5)))


# --------------------------------------------------------------------------
# record (ffmpeg mocked)
# --------------------------------------------------------------------------

DEVICE_LIST = """\
[AVFoundation indev @ 0x1] AVFoundation video devices:
[AVFoundation indev @ 0x1] [0] FaceTime HD Camera
[AVFoundation indev @ 0x1] AVFoundation audio devices:
[AVFoundation indev @ 0x1] [0] BlackHole 64ch
[AVFoundation indev @ 0x1] [1] BlackHole 2ch
[AVFoundation indev @ 0x1] [2] MacBook Pro Microphone
"""


@pytest.fixture
def fake_ffmpeg(monkeypatch):
    calls = []

    def run(cmd, **kwargs):
        calls.append(cmd)
        if "-list_devices" in cmd:
            return subprocess.CompletedProcess(cmd, 1, "", DEVICE_LIST)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(audio.shutil, "which", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(audio.subprocess, "run", run)
    return calls


def test_list_input_devices_skips_video(fake_ffmpeg):
    assert audio.list_input_devices() == ["BlackHole 64ch", "BlackHole 2ch", "MacBook Pro Microphone"]


def test_record_uses_exact_device_name(fake_ffmpeg, tmp_path):
    out = audio.record(2, out_path=str(tmp_path / "x.wav"))
    cmd = fake_ffmpeg[-1]
    # The index, not the name: ffmpeg prefix-matches names, so ":BlackHole"
    # would open "BlackHole 64ch".
    assert cmd[cmd.index("-i") + 1] == ":1"
    assert cmd[cmd.index("-t") + 1] == "2.000"
    assert out == str(tmp_path / "x.wav")


def test_record_unknown_device(fake_ffmpeg):
    with pytest.raises(RuntimeError, match="not found. Available: BlackHole 64ch"):
        audio.record(2, device="Soundflower")


@pytest.mark.parametrize("seconds", [0, -1, 31])
def test_record_rejects_bad_duration(fake_ffmpeg, seconds):
    with pytest.raises(ValueError):
        audio.record(seconds)


def test_record_audio_tool_runs_off_the_event_loop(fake_ffmpeg, monkeypatch):
    import asyncio
    import inspect
    import MCP_Server.server as server

    used_thread = []
    real_to_thread = asyncio.to_thread

    async def spy(func, *args, **kwargs):
        used_thread.append(func)
        return await real_to_thread(func, *args, **kwargs)

    monkeypatch.setattr(server.asyncio, "to_thread", spy)
    result = server.record_audio(None, seconds=1)
    assert inspect.iscoroutine(result)
    assert asyncio.run(result).startswith("Recorded 1s from 'BlackHole 2ch'")
    assert used_thread == [audio.record]


def test_record_without_ffmpeg(monkeypatch):
    monkeypatch.setattr(audio.shutil, "which", lambda name: None)
    with pytest.raises(RuntimeError, match="brew install ffmpeg"):
        audio.record(2)
