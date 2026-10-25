"""Server-side tests for the 1.9 studio tools (connection mocked, no Live)."""

import asyncio
import inspect
import json

import numpy as np
import pytest

import MCP_Server.server as server
import MCP_Server.studio_tools as studio


def call(tool, *args, **kwargs):
    result = tool(*args, **kwargs)
    if inspect.iscoroutine(result):
        return asyncio.run(result)
    return result


def tool(name):
    return server.mcp._tool_manager._tools[name].fn


class Conn(object):
    def __init__(self, handlers=None):
        self.sent = []
        self.handlers = handlers or {}

    def send_command(self, command, params=None):
        params = params or {}
        self.sent.append((command, params))
        h = self.handlers.get(command)
        if callable(h):
            return h(params)
        return h if h is not None else {}


@pytest.fixture
def conn(monkeypatch):
    import MCP_Server.script_handshake as sh
    import MCP_Server.telemetry_decorator as td

    class _Dummy(object):
        def record_event(self, *a, **k):
            pass

    monkeypatch.setattr(td, "get_telemetry", lambda: _Dummy(), raising=False)
    monkeypatch.setattr(sh, "require_capability", lambda name: None)
    c = Conn()
    monkeypatch.setattr(server, "get_ableton_connection", lambda: c)
    studio._AUDIO_REPORTS.clear()
    return c


def test_dataset_tools_hidden_by_default():
    names = set(server.mcp._tool_manager._tools)
    assert "set_dataset_consent" not in names and "submit_intent" not in names
    assert {"render_section", "write_clip_automation", "add_device", "review_clip"} <= names


def test_add_device_and_parameters(conn):
    conn.handlers["add_device"] = {"track_name": "Bass", "method": "insert_device",
                                   "devices": [{"name": "Compressor"}], "notes": []}
    out = call(tool("add_device"), None, track_index=0, name="Compressor", track_type="return")
    assert conn.sent[-1] == ("add_device", {"track_index": 0, "track_type": "return",
                                            "name": "Compressor"})
    assert "Chain: Compressor" in out
    conn.handlers["set_device_parameters"] = {"device_name": "Compressor", "track_name": "Bass",
                                              "set": [{"name": "Threshold", "display": "-24.0 dB"}]}
    out = call(tool("set_device_parameters"), None, 0, 1,
               [{"name": "Threshold", "display": "-24 dB"}])
    assert "Threshold = -24.0 dB" in out


def test_write_automation_passes_points(conn):
    conn.handlers["write_clip_automation"] = {"parameter": "Frequency", "clip_name": "Build",
                                              "first_display": "300 Hz", "last_display": "8.00 kHz",
                                              "start": 0, "end": 28, "steps": 449}
    pts = [{"time": 0, "display": "300 Hz"}, {"time": 28, "display": "8 kHz"}]
    out = call(tool("write_clip_automation"), None, 3, 0,
               {"device_index": 1, "parameter_name": "Frequency"}, pts, curve="exp")
    sent = conn.sent[-1][1]
    assert sent["points"] == pts and sent["curve"] == "exp"
    assert "300 Hz → 8.00 kHz" in out


def write_wav(path, seconds=1.0, sr=48000):
    import soundfile as sf
    rng = np.random.default_rng(0)
    sf.write(str(path), rng.normal(0, 0.1, (int(seconds * sr), 2)), sr)


def test_render_section_copies_and_analyses(conn, tmp_path, monkeypatch):
    src = tmp_path / "rec.wav"
    write_wav(src)
    monkeypatch.setattr(studio, "RENDER_DIR", tmp_path / "renders")
    seen = {}

    def fake_analyze(path, **kw):
        seen.update(kw, path=path)
        return {"loudness": {"integrated_lufs": -9.1}, "tonal": {"chroma": [0] * 12, "key_candidates": []}}

    import MCP_Server.ears as ears
    monkeypatch.setattr(ears, "analyze", fake_analyze)
    conn.handlers.update({
        "get_session_info": {"signature_numerator": 4, "signature_denominator": 4, "tempo": 125},
        "start_render": lambda p: {"id": "r1", "state": "recording", "expected_seconds": 1.0,
                                   **p},
        "get_render_status": {"id": "r1", "state": "done", "file_path": str(src),
                              "window_offset_s": 1.92, "window_seconds": 15.36, "tempo": 125.0,
                              "start_beat": 128.0, "end_beat": 160.0, "solo_tracks": [0, 4]},
    })
    out = json.loads(call(tool("render_section"), None, start_bar=33, bars=8, label="drop v1",
                          solo_tracks=[0, 4]))
    start = [p for c, p in conn.sent if c == "start_render"][0]
    assert start["start_beat"] == 128.0 and start["end_beat"] == 160.0
    assert start["solo_tracks"] == [0, 4]
    assert seen["start_s"] == 1.92 and seen["end_s"] == pytest.approx(17.28)
    assert seen["bpm"] == 125.0
    assert (tmp_path / "renders").exists() and seen["path"].endswith(".wav")
    assert "chroma" not in out["tonal"]
    assert out["render"]["label"] == "drop v1"
    assert set(studio._AUDIO_REPORTS) == {"drop v1", "last"}


def test_render_still_running_returns_job(conn, monkeypatch):
    monkeypatch.setattr(studio, "MAX_TOOL_WAIT_S", 0.0)
    conn.handlers.update({
        "get_session_info": {"signature_numerator": 4, "signature_denominator": 4},
        "start_render": {"id": "r9", "state": "recording", "expected_seconds": 90},
        "get_render_status": {"id": "r9", "state": "recording", "expected_seconds": 90},
    })
    out = call(tool("render_section"), None, start_bar=1, bars=48, label="long")
    assert "get_render_result" in out and "r9" in out


def test_compare_audio_uses_labels(conn, monkeypatch):
    import MCP_Server.ears as ears
    studio._register_report("mix", "/x.wav", {"id": "mix"}, "render")
    studio._register_report("ref", "/y.wav", {"id": "ref"}, "file")
    monkeypatch.setattr(ears, "compare", lambda a, b, labels: {"a": a["id"], "b": b["id"],
                                                               "labels": list(labels)})
    out = json.loads(call(tool("compare_audio"), None, a="last", b="ref"))
    assert out == {"a": "mix", "b": "ref", "labels": ["mix", "ref"]}
    err = call(tool("compare_audio"), None, a="nope", b="ref")
    assert "Known labels" in err


def test_transform_clip_notes_into_variant(conn, monkeypatch):
    import MCP_Server.midi_tools as mt
    notes = [{"pitch": 40, "start_time": 0.25, "duration": 0.2, "velocity": 90, "mute": False,
              "note_id": 7}]
    conn.handlers["get_clip_notes"] = {"clip_name": "Bass", "length": 4.0, "notes": notes}
    monkeypatch.setattr(mt, "transform_notes",
                        lambda n, ops, length: [dict(x, start_time=0.29) for x in n])
    monkeypatch.setattr(mt, "describe_ops", lambda ops: "swing 58 %")
    out = call(tool("transform_clip_notes"), None, 2, 0, {"swing": {"percent": 58}},
               target_clip_index=1, new_name="Bass swung")
    order = [c for c, _ in conn.sent]
    assert order == ["copy_clip", "get_clip_notes", "clear_notes_from_clip", "add_notes_to_clip"]
    assert conn.sent[0][1]["new_name"] == "Bass swung" and conn.sent[0][1]["overwrite"] is True
    added = conn.sent[-1][1]
    assert added["clip_index"] == 1
    assert added["notes"] == [{"pitch": 40, "start_time": 0.29, "duration": 0.2,
                               "velocity": 90, "mute": False}]
    assert out.startswith("swing 58 %")


def test_forecast_masking_names_parts(conn, monkeypatch):
    import MCP_Server.midi_tools as mt
    conn.handlers["get_session_info"] = {"tracks": [{"index": 0, "name": "Drums"},
                                                    {"index": 1, "name": "Bass"}]}
    conn.handlers["get_clip_notes"] = {"clip_name": "A", "length": 4.0, "notes": []}
    captured = {}
    monkeypatch.setattr(mt, "forecast_masking", lambda parts: captured.setdefault("parts", parts))
    call(tool("forecast_masking"), None, [{"track_index": 0, "clip_index": 0, "role": "drums"},
                                          {"track_index": 1, "clip_index": 0, "role": "bass"}])
    parts = captured["parts"]
    assert [p["name"] for p in parts] == ["Drums [A]", "Bass [A]"]
    assert [p["pitched"] for p in parts] == [False, True]


def test_end_to_end_render_and_compare_with_real_ears(conn, tmp_path, monkeypatch):
    """Real analysis on a synthetic 'render': kick on beats, swung hats."""
    import soundfile as sf
    sr, bpm = 48000, 125.0
    beat = 60.0 / bpm
    seconds = 16 * beat + 2 * beat  # 4 bars + 2 beats preroll
    t = np.arange(int(seconds * sr)) / sr
    y = np.zeros_like(t)
    rng = np.random.default_rng(1)
    for k in range(int(seconds / beat)):
        start = int(k * beat * sr)
        n = int(0.15 * sr)
        env = np.exp(-np.arange(n) / (0.03 * sr))
        y[start:start + n] += 0.8 * np.sin(2 * np.pi * 55 * np.arange(n) / sr) * env
    for k in range(int(seconds / (beat / 4))):
        off = 0.04 * beat if k % 2 else 0.0  # 58 % swing
        start = int((k * beat / 4 + off) * sr)
        n = int(0.02 * sr)
        if start + n < len(y):
            y[start:start + n] += 0.2 * rng.normal(size=n) * np.exp(-np.arange(n) / (0.004 * sr))
    stereo = np.stack([y, y], axis=1) * 0.5
    src = tmp_path / "rec.wav"
    sf.write(str(src), stereo, sr)
    monkeypatch.setattr(studio, "RENDER_DIR", tmp_path / "renders")
    conn.handlers.update({
        "get_session_info": {"signature_numerator": 4, "signature_denominator": 4},
        "start_render": {"id": "r2", "state": "recording", "expected_seconds": 9},
        "get_render_status": {"id": "r2", "state": "done", "file_path": str(src),
                              "window_offset_s": 2 * beat, "window_seconds": 16 * beat,
                              "tempo": bpm, "start_beat": 0.0, "end_beat": 16.0},
    })
    report = json.loads(call(tool("render_section"), None, start_bar=1, bars=4, label="groove"))
    assert report["loudness"]["integrated_lufs"] < 0
    assert abs(report["rhythm"]["high_band"]["swing_percent"] - 58) <= 2
    studio._register_report("ref", str(src), report, "file")
    out = json.loads(call(tool("compare_audio"), None, a="groove", b="ref"))
    assert out["summary"] == []


def test_transform_with_real_midi_tools(conn):
    notes = [{"pitch": 42, "start_time": i * 0.25, "duration": 0.1, "velocity": 100,
              "mute": False} for i in range(16)]
    conn.handlers["get_clip_notes"] = {"clip_name": "Hats", "length": 4.0, "notes": notes}
    call(tool("transform_clip_notes"), None, 0, 0,
         {"swing": {"percent": 58, "grid": 0.25},
          "velocity": {"accent_map": [100, 62, 84, 58], "mode": "set"}})
    written = conn.sent[-1][1]["notes"]
    assert [round(n["start_time"], 3) for n in written[:4]] == [0.0, 0.29, 0.5, 0.79]
    assert [n["velocity"] for n in written[:4]] == [100, 62, 84, 58]


def _wav_with_header_sizes(path, frames, sr=48000, data_size=None, riff_size=None):
    import struct
    pcm = (np.sin(np.arange(frames) / 10.0) * 12000).astype("<i2").tobytes()
    fmt = struct.pack("<HHIIHH", 1, 1, sr, sr * 2, 2, 16)
    body = b"WAVE" + b"fmt " + struct.pack("<I", 16) + fmt + b"data" + struct.pack(
        "<I", len(pcm) if data_size is None else data_size) + pcm
    riff = len(body) if riff_size is None else riff_size
    path.write_bytes(b"RIFF" + struct.pack("<I", riff) + body)


def test_repair_wav_header_fixes_unfinalised_take(tmp_path):
    import soundfile as sf
    p = tmp_path / "take.wav"
    _wav_with_header_sizes(p, 4800, data_size=0, riff_size=36)
    assert studio._repair_wav_header(p) is True
    x, sr = sf.read(str(p))
    assert sr == 48000 and len(x) == 4800
    assert studio._repair_wav_header(p) is False  # already consistent


def test_repair_wav_header_leaves_other_files(tmp_path):
    p = tmp_path / "take.aif"
    p.write_bytes(b"FORM\x00\x00\x00\x04AIFF")
    assert studio._repair_wav_header(p) is False


def test_copy_shared_copies_and_names_the_take_on_failure(tmp_path):
    src = tmp_path / "a.wav"
    _wav_with_header_sizes(src, 480)
    dest = tmp_path / "b.wav"
    studio._copy_shared(str(src), dest)
    assert dest.read_bytes() == src.read_bytes()
    with pytest.raises(OSError, match="couldn't read the recorded take"):
        studio._copy_shared(str(tmp_path / "missing.wav"), tmp_path / "c.wav", timeout=0)
