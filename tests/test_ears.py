"""Tests for MCP_Server.ears, the render-analysis package.

Every signal is synthesised here; no audio files are committed. pyloudnorm
is used only as an optional cross-check (skipped if it is not installed).
"""

import json
import time

import numpy as np
import pytest
import soundfile as sf
from scipy import signal

from MCP_Server.ears import analyze, compare, load_audio
from MCP_Server.ears import loudness as ld
from MCP_Server.ears import tonal as tn

SR = 48000


# ------------------------------------------------------------------ helpers

def sine(freq, dur, sr=SR, amp=1.0, phase=0.0):
    t = np.arange(int(round(dur * sr))) / sr
    return amp * np.sin(2 * np.pi * freq * t + phase)


def pink_noise(n, seed=0, peak=0.5):
    rng = np.random.default_rng(seed)
    spec = np.fft.rfft(rng.normal(size=n))
    k = np.arange(spec.size, dtype=float)
    k[0] = 1.0
    y = np.fft.irfft(spec / np.sqrt(k), n)
    return y / np.max(np.abs(y)) * peak


def peaking_eq(x, f0, gain_db, q, sr=SR):
    """RBJ cookbook peaking EQ (test-only helper)."""
    a = 10 ** (gain_db / 40)
    w0 = 2 * np.pi * f0 / sr
    alpha = np.sin(w0) / (2 * q)
    b = [1 + alpha * a, -2 * np.cos(w0), 1 - alpha * a]
    den = [1 + alpha / a, -2 * np.cos(w0), 1 - alpha / a]
    return signal.lfilter(b, den, x, axis=0)


def hat_clicks(swing=50.0, bpm=120.0, bars=16, sr=SR, seed=3):
    """Short high-passed noise clicks on every 16th; off-16ths delayed for ``swing`` %."""
    rng = np.random.default_rng(seed)
    s16 = 60.0 / bpm / 4.0
    y = np.zeros(int((bars * 16 * s16 + 1.0) * sr))
    sos = signal.butter(4, 6000, btype="high", fs=sr, output="sos")
    length = int(0.004 * sr)
    env = np.exp(-np.arange(length) / (0.001 * sr))
    for k in range(bars * 16):
        t = k * s16 + ((swing - 50.0) / 100.0 * 2.0 * s16 if k % 2 else 0.0)
        i = int(round(t * sr))
        y[i:i + length] += 0.5 * signal.sosfilt(sos, rng.normal(size=length) * env)
    return y


def kick_track(bpm=120.0, bars=16, sr=SR):
    """60 Hz decaying sine bursts on every beat."""
    beat = 60.0 / bpm
    y = np.zeros(int((bars * 4 * beat + 1.0) * sr))
    tt = np.arange(int(0.3 * sr)) / sr
    kick = 0.8 * np.sin(2 * np.pi * 60 * tt) * np.exp(-tt / 0.08)
    for b in range(bars * 4):
        i = int(round(b * beat * sr))
        y[i:i + kick.size] += kick
    return y


def midi_hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def tones(midis, dur, amp=0.1, sr=SR):
    return sum(sine(midi_hz(m), dur, sr, amp) for m in midis)


def assert_plain_json(obj, path="report"):
    """Only dict/list/str/int/float/bool/None, i.e. no numpy scalar types anywhere."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            assert isinstance(k, str), f"{path}: non-str key {k!r}"
            assert_plain_json(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            assert_plain_json(v, f"{path}[{i}]")
    else:
        assert obj is None or type(obj) in (str, int, float, bool), f"{path}: {type(obj).__name__}"


# ------------------------------------------------------------------ loading

@pytest.mark.parametrize("ext,subtype", [("wav", "PCM_16"), ("wav", "PCM_24"), ("wav", "FLOAT"),
                                         ("aiff", "PCM_16"), ("aiff", "PCM_24")])
def test_load_audio_formats(tmp_path, ext, subtype):
    x = np.c_[sine(440, 1.0, amp=0.5), sine(660, 1.0, amp=0.25)]
    path = tmp_path / f"t.{ext}"
    sf.write(path, x, SR, subtype=subtype)
    y, sr = load_audio(path)
    assert sr == SR and y.dtype == np.float64 and y.shape == x.shape
    assert np.max(np.abs(y - x)) < 1e-3

    part, _ = load_audio(path, start_s=0.25, end_s=0.75)
    assert part.shape == (SR // 2, 2)
    assert np.allclose(part, y[SR // 4:3 * SR // 4])


def test_load_audio_mono_and_errors(tmp_path):
    path = tmp_path / "mono.wav"
    sf.write(path, sine(440, 0.5, amp=0.5), SR)
    y, _ = load_audio(path)
    assert y.shape == (SR // 2, 1)

    with pytest.raises(ValueError, match="not found"):
        load_audio(tmp_path / "missing.wav")
    empty = tmp_path / "empty.wav"
    empty.write_bytes(b"")
    with pytest.raises(ValueError, match="empty"):
        load_audio(empty)
    zero = tmp_path / "zero.wav"
    sf.write(zero, np.zeros((0, 2)), SR)
    with pytest.raises(ValueError):
        load_audio(zero)
    with pytest.raises(ValueError):
        load_audio(path, start_s=5.0)
    with pytest.raises(ValueError):
        analyze(np.zeros(100))  # array without sr


def test_analyze_path_matches_array(tmp_path):
    x = np.c_[pink_noise(3 * SR, 1), pink_noise(3 * SR, 2)]
    path = tmp_path / "noise.wav"
    sf.write(path, x, SR, subtype="FLOAT")
    from_file = analyze(path)
    from_array = analyze(x.astype(np.float32).astype(np.float64), sr=SR)
    assert from_file == from_array


# ------------------------------------------------------------------ loudness

def test_k_weighting_matches_bs1770_48k_coefficients():
    sos = ld.k_weighting_sos(48000)
    assert np.allclose(sos[0, :3], [1.53512485958697, -2.69169618940638, 1.19839281085285], atol=1e-8)
    assert np.allclose(sos[0, 4:], [-1.69065929318241, 0.73248077421585], atol=1e-8)
    assert np.allclose(sos[1, :3], [1.0, -2.0, 1.0])
    assert np.allclose(sos[1, 4:], [-1.99004745483398, 0.99007225036621], atol=1e-8)


@pytest.mark.parametrize("sr", [44100, 48000, 96000])
def test_997hz_sine_loudness(sr):
    s = sine(997, 10.0, sr)
    assert ld.integrated_loudness(np.c_[s, s], sr) == pytest.approx(0.0, abs=0.1)
    assert ld.integrated_loudness(np.c_[s, np.zeros_like(s)], sr) == pytest.approx(-3.01, abs=0.1)


@pytest.mark.parametrize("sr", [44100, 48000])
def test_integrated_loudness_matches_pyloudnorm(sr):
    pyln = pytest.importorskip("pyloudnorm")
    rng = np.random.default_rng(sr)
    for i, level in enumerate((0.02, 0.1, 0.3)):
        x = rng.normal(0, level, (sr * 6 + 777 * i, 2))
        if i == 2:  # add a quiet tail so the relative gate actually removes blocks
            x[-2 * sr:] *= 0.01
        ours = ld.integrated_loudness(x, sr)
        ref = pyln.Meter(sr).integrated_loudness(x)
        assert ours == pytest.approx(ref, abs=0.1)


def test_gating_and_loudness_range():
    # 10 s at -20 dBFS then 10 s 12 dB quieter: LRA should be close to 12 LU.
    rng = np.random.default_rng(5)
    loud = rng.normal(0, 0.1, (10 * SR, 2))
    quiet = loud * 10 ** (-12 / 20)
    rep = ld.measure(np.vstack([loud, quiet]), SR)
    assert rep["loudness_range_lu"] == pytest.approx(12.0, abs=1.0)
    assert rep["short_term_max_lufs"] >= rep["integrated_lufs"]
    # Silence is gated out entirely.
    silent = ld.measure(np.zeros((SR * 4, 2)), SR)
    assert silent["integrated_lufs"] is None and silent["loudness_range_lu"] is None


def test_true_peak_intersample():
    n = np.arange(SR)
    x = np.sin(np.pi / 2 * n + np.pi / 4)  # fs/4, 45 deg: samples sit at +/-0.707
    rep = ld.measure(x[:, None], SR)
    assert rep["sample_peak_dbfs"] == pytest.approx(-3.01, abs=0.05)
    assert rep["true_peak_dbtp"] - rep["sample_peak_dbfs"] == pytest.approx(3.0, abs=0.5)


def test_level_figures_for_sine():
    rep = ld.measure(sine(1000, 2.0, amp=0.5)[:, None], SR)
    assert rep["sample_peak_dbfs"] == pytest.approx(-6.02, abs=0.01)
    assert rep["rms_dbfs"] == pytest.approx(-9.03, abs=0.01)
    assert rep["crest_db"] == pytest.approx(3.01, abs=0.02)


# ------------------------------------------------------------------ stereo

def test_stereo_identical_and_inverted():
    x = pink_noise(4 * SR, 9)
    same = analyze(np.c_[x, x], sr=SR)["stereo"]
    assert same["correlation"] == pytest.approx(1.0, abs=1e-3)
    assert same["width_db"] < -60
    assert same["low_correlation"] == pytest.approx(1.0, abs=1e-3)
    assert same["mono_compat_ok"] is True

    inv = analyze(np.c_[x, -x], sr=SR)
    assert inv["stereo"]["correlation"] == pytest.approx(-1.0, abs=1e-3)
    assert inv["stereo"]["width_db"] > 60
    assert inv["stereo"]["mono_compat_ok"] is False
    assert any("phase" in w for w in inv["warnings"])


def test_stereo_band_widths():
    # Mono low end, decorrelated top end.
    rng = np.random.default_rng(4)
    low = signal.sosfilt(signal.butter(4, 100, fs=SR, output="sos"), rng.normal(size=4 * SR))
    hp = signal.butter(4, 6000, "high", fs=SR, output="sos")
    hl, hr = (signal.sosfilt(hp, rng.normal(size=4 * SR)) for _ in range(2))
    st = analyze(np.c_[low + hl, low + hr], sr=SR)["stereo"]
    assert st["low_correlation"] > 0.95
    assert st["high_width_db"] == pytest.approx(0.0, abs=1.0)
    assert st["low_width_db"] < -20
    assert "stereo" not in analyze(low, sr=SR)  # mono input has no stereo section


# ------------------------------------------------------------------ spectrum

def _bands(rep):
    return {b["name"]: b["db"] for b in rep["spectrum"]["bands"]}


def test_sine_lands_in_its_band():
    b50 = _bands(analyze(sine(50, 4.0, amp=0.5), sr=SR))
    assert max(b50, key=b50.get) == "sub" and b50["sub"] > -0.5
    b3k = _bands(analyze(sine(3000, 4.0, amp=0.5), sr=SR))
    assert max(b3k, key=b3k.get) == "presence" and b3k["presence"] > -0.5


def test_named_bands_tile_the_spectrum():
    rep = analyze(pink_noise(8 * SR, 2), sr=SR)
    total = sum(10 ** (b["db"] / 10) for b in rep["spectrum"]["bands"])
    assert total == pytest.approx(1.0, abs=0.01)
    assert len(rep["spectrum"]["octave_bands"]) == 10


def test_tilt_sign_convention():
    # PSD slope: pink = -3 dB/oct, white = 0 dB/oct (negative = darker).
    pink = analyze(pink_noise(20 * SR, 11), sr=SR)["spectrum"]
    white = analyze(np.random.default_rng(12).normal(0, 0.1, 20 * SR), sr=SR)["spectrum"]
    assert pink["tilt_db_per_oct"] == pytest.approx(-3.0, abs=1.0)
    assert white["tilt_db_per_oct"] == pytest.approx(0.0, abs=0.5)
    assert pink["centroid_hz"] < white["centroid_hz"]
    assert pink["rolloff85_hz"] < white["rolloff85_hz"]
    # Pink has equal energy per octave, so the octave_bands values are flat.
    octs = [o["db"] for o in pink["octave_bands"][1:9]]
    assert max(octs) - min(octs) < 1.0


# ------------------------------------------------------------------ rhythm

@pytest.mark.parametrize("swing", [58.0, 50.0])
def test_swing_in_high_band(swing):
    y = hat_clicks(swing)
    rh = analyze(np.c_[y, y], sr=SR, bpm=120)["rhythm"]
    hb = rh["high_band"]
    assert hb["onsets"] == pytest.approx(256, abs=4)
    assert hb["swing_percent"] == pytest.approx(swing, abs=2.0)
    assert abs(hb["on16_mean_ms"]) < 3.0
    assert hb["timing_spread_ms"] < 3.0
    assert rh["tempo_estimate_bpm"] == pytest.approx(120, abs=2)


def test_swing_with_beat_offset():
    lead = int(0.3 * SR)
    y = np.concatenate([np.zeros(lead), hat_clicks(62.0, bars=8)])
    hb = analyze(y, sr=SR, bpm=120, beat_offset_s=0.3)["rhythm"]["high_band"]
    assert hb["swing_percent"] == pytest.approx(62.0, abs=2.0)


def test_swing_is_immune_to_render_latency():
    # Whole render 12 ms late (latency, or a downbeat guessed slightly early).
    y = np.concatenate([np.zeros(int(0.012 * SR)), hat_clicks(58.0, bars=8)])
    hb = analyze(y, sr=SR, bpm=120)["rhythm"]["high_band"]
    assert hb["on16_mean_ms"] == pytest.approx(12.0, abs=1.5)  # latency is visible...
    assert hb["swing_percent"] == pytest.approx(58.0, abs=2.0)  # ...but swing ignores it
    assert hb["swing_percent_raw_grid"] == pytest.approx(58.0 + 12.0 / 250.0 * 100.0, abs=2.0)


def test_kick_grid_offset():
    rh = analyze(kick_track(), sr=SR, bpm=120)["rhythm"]
    assert rh["low_band"]["onsets"] == pytest.approx(64, abs=2)
    assert abs(rh["kick_grid_offset_ms"]) < 5.0
    assert rh["tempo_estimate_bpm"] == pytest.approx(120, abs=2)


def test_rhythm_without_bpm_has_only_basics():
    rh = analyze(kick_track(bars=4), sr=SR)["rhythm"]
    assert set(rh) == {"onset_count", "tempo_estimate_bpm"}
    assert rh["onset_count"] == pytest.approx(16, abs=1)


# ------------------------------------------------------------------ tonal

def test_c_major_triad_key():
    # C-E-G across octaves (root doubled in the bass, as voiced in practice).
    y = tones([36, 48, 52, 55, 60, 64, 67, 72, 76, 79], 8.0)
    tonal = analyze(y, sr=SR)["tonal"]
    assert len(tonal["chroma"]) == 12
    assert sum(tonal["chroma"]) == pytest.approx(1.0, abs=1e-9)
    top = tonal["key_candidates"][0]
    assert (top["key"], top["mode"]) in {("C", "major"), ("A", "minor")}
    assert (top["key"], top["mode"]) == ("C", "major")
    assert len(tonal["key_candidates"]) == 3


def test_equal_ceg_prefers_c_major():
    tonal = analyze(tones([48, 52, 55, 60, 64, 67, 72, 76, 79], 8.0), sr=SR)["tonal"]
    assert (tonal["key_candidates"][0]["key"], tonal["key_candidates"][0]["mode"]) == ("C", "major")


def test_a_minor_key():
    # A-C-E-G with A as the bass root. Without a bass cue this pitch set is
    # equally C6, and Krumhansl-Kessler then leans C major.
    y = tones([45, 57, 60, 64, 67, 69, 72, 76, 79], 8.0)
    top = analyze(y, sr=SR)["tonal"]["key_candidates"][0]
    assert (top["key"], top["mode"]) == ("A", "minor")


def test_chords_per_bar():
    y = np.concatenate([tones([48, 60, 64, 67], 2.0), tones([45, 57, 60, 64], 2.0)])
    chords = analyze(np.c_[y, y], sr=SR, bpm=120)["tonal"]["chords_per_bar"]
    assert [c["chord"] for c in chords] == ["C", "Am"]
    assert all(c["confidence"] > 0.8 for c in chords)


def test_chord_vocabulary():
    progression = [[48, 60, 64, 67, 71], [45, 57, 60, 64, 67], [43, 55, 59, 62, 65],
                   [50, 62, 65, 69], [48, 60, 65, 67], [47, 59, 62, 65]]
    y = np.concatenate([tones(p, 2.0) for p in progression])
    names = [c["chord"] for c in analyze(y, sr=SR, bpm=120)["tonal"]["chords_per_bar"]]
    assert names == ["Cmaj7", "Am7", "G7", "Dm", "Csus4", "Bdim"]


def test_best_chord_template_direct():
    chroma = np.zeros(12)
    chroma[[9, 0, 4]] = 1.0  # A C E
    assert tn.best_chord(chroma)[0] == "Am"
    assert tn.best_chord(np.zeros(12)) == (None, 0.0)


# ------------------------------------------------------------------ report / compare

def test_report_is_plain_json():
    hats = hat_clicks(56.0, bars=4)
    y = hats + tones([45, 57, 60, 64], hats.size / SR)
    rep = analyze(np.c_[y, 0.9 * y], sr=SR, bpm=120)
    json.dumps(rep, allow_nan=False)
    assert_plain_json(rep)
    for key in ("duration_s", "sample_rate", "channels", "loudness", "spectrum", "stereo", "rhythm", "tonal",
                "warnings"):
        assert key in rep
    assert rep["channels"] == 2 and rep["sample_rate"] == SR


def test_warnings():
    quiet = analyze(np.random.default_rng(1).normal(0, 0.003, (4 * SR, 2)), sr=SR)["warnings"]
    assert any("very quiet" in w.lower() for w in quiet)

    hot = analyze(np.c_[sine(997, 3.0), sine(997, 3.0)], sr=SR)["warnings"]
    assert any("true peak" in w.lower() for w in hot)

    squashed = np.clip(np.random.default_rng(2).normal(0, 1.0, (4 * SR, 2)), -0.5, 0.5)
    assert any("heavily limited" in w.lower() for w in analyze(squashed, sr=SR)["warnings"])

    sub_heavy = sine(40, 4.0, amp=0.5) + sine(120, 4.0, amp=0.01)
    assert any("sub-heavy" in w.lower() for w in analyze(sub_heavy, sr=SR)["warnings"])

    muddy = sine(350, 4.0, amp=0.5) + sine(100, 4.0, amp=0.1)
    assert any("mud" in w.lower() for w in analyze(muddy, sr=SR)["warnings"])

    silent = analyze(np.zeros((2 * SR, 2)), sr=SR)
    assert any("silent" in w.lower() for w in silent["warnings"])
    json.dumps(silent, allow_nan=False)


def test_compare_identical_is_empty():
    x = np.c_[pink_noise(6 * SR, 21), pink_noise(6 * SR, 22)]
    result = compare(analyze(x, sr=SR), analyze(x.copy(), sr=SR))
    assert result["summary"] == []
    assert result["loudness_offset_db"] == 0.0
    assert all(v == 0.0 for v in result["deltas"]["bands"].values())
    json.dumps(result, allow_nan=False)
    assert_plain_json(result)


def test_compare_low_mid_bell_boost():
    ref = np.c_[pink_noise(10 * SR, 31), pink_noise(10 * SR, 32)] * 0.5
    mix = peaking_eq(ref, 300.0, 4.0, 1.0)
    result = compare(analyze(mix, sr=SR), analyze(ref, sr=SR))
    assert result["deltas"]["bands"]["low_mid"] >= 1.5
    low_mid_lines = [s for s in result["summary"] if "low_mid" in s]
    assert low_mid_lines, result["summary"]
    assert low_mid_lines[0].startswith("Your mix has") and "more low_mid" in low_mid_lines[0]
    assert "spectral deltas are inherently loudness-matched" in result["note"]


def test_compare_paths_loudness_and_swing(tmp_path):
    a = hat_clicks(54.0, bars=8)
    b = hat_clicks(60.0, bars=8) * 10 ** (6 / 20)
    pa, pb = tmp_path / "a.wav", tmp_path / "b.wav"
    sf.write(pa, np.c_[a, a], SR, subtype="FLOAT")
    sf.write(pb, np.c_[b, b], SR, subtype="FLOAT")
    from_paths = compare(pa, pb)
    assert from_paths["loudness_offset_db"] == pytest.approx(6.0, abs=0.2)
    assert any("quieter" in s for s in from_paths["summary"])

    with_grid = compare(analyze(pa, bpm=120), analyze(pb, bpm=120), labels=("verse", "chorus"))
    assert with_grid["deltas"]["swing_percent"]["high"] == pytest.approx(-6.0, abs=1.5)
    swing_lines = [s for s in with_grid["summary"] if "swing" in s]
    assert swing_lines and swing_lines[0].startswith("Your verse") and "add about" in swing_lines[0]


# ------------------------------------------------------------------ performance

def test_performance_60s_stereo(capsys):
    x = np.random.default_rng(0).normal(0, 0.1, (60 * SR, 2))
    t0 = time.perf_counter()
    rep = analyze(x, sr=SR, bpm=120)
    elapsed = time.perf_counter() - t0
    with capsys.disabled():
        print(f"\n[ears] analyze() on 60 s 48 kHz stereo noise: {elapsed:.2f} s")
    assert rep["duration_s"] == 60.0
    assert elapsed < 8.0
