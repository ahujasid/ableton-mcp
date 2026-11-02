"""ableton_io_check parsing: pw-link -l output and WAV level maths."""

import importlib.util
import math
import struct
import wave
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "ableton_io_check", Path(__file__).resolve().parents[1] / "scripts" / "ableton_io_check.py")
io = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(io)

PW_LINK_L = """\
alsa_output.x.Scarlett_4i4.pro-output-0:playback_AUX0
  |<- Ableton Live 12 Trial:out_3
Ableton Live 12 Trial:out_1
  |-> alsa_output.x.Scarlett_4i4.pro-output-0:playback_FL
alsa_input.x.Scarlett_4i4.pro-input-0:capture_AUX2
  |-> Ableton Live 12 Trial:in_3
"""


def test_parse_links_both_directions():
    links = io.parse_links(PW_LINK_L)
    assert ("Ableton Live 12 Trial:out_3", "alsa_output.x.Scarlett_4i4.pro-output-0:playback_AUX0") in links
    assert ("Ableton Live 12 Trial:out_1", "alsa_output.x.Scarlett_4i4.pro-output-0:playback_FL") in links
    assert ("alsa_input.x.Scarlett_4i4.pro-input-0:capture_AUX2", "Ableton Live 12 Trial:in_3") in links
    assert len(links) == 3


def test_levels_per_channel(tmp_path):
    path = tmp_path / "t.wav"
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(48000)
        frames = b"".join(struct.pack("<hh", 16384, 0) for _ in range(100))
        w.writeframes(frames)
    vals, n = io.levels(str(path), 2)
    assert n == 100
    assert abs(vals[0][0] - (-6.02)) < 0.05 and vals[1][0] == -math.inf


def test_a_failed_check_is_unknown_not_ok():
    rep = io.Report()
    rep.add("links", "ok", "a")
    rep.add("levels", "unknown", "b")
    assert rep.exit_code() == 3
    rep.add("mixer", "problem", "c")
    assert rep.exit_code() == 1
