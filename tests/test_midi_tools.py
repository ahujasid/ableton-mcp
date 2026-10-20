"""Tests for MCP_Server.midi_tools (pure-Python MIDI analysis and transforms).

Run from the repo root:
    python3 -m pytest -q tests/test_midi_tools.py
"""

import copy
import json
import random

import pytest

from MCP_Server import midi_tools as mt


def N(pitch, start, dur=0.25, vel=100, mute=False, **extra):
    note = {"pitch": pitch, "start_time": start, "duration": dur, "velocity": vel, "mute": mute}
    note.update(extra)
    return note


def straight_16ths(pitch=42, bars=1, vel=100, dur=0.1):
    return [N(pitch, i * 0.25, dur, vel) for i in range(16 * bars)]


def starts(notes):
    return [n["start_time"] for n in notes]


def circular_distance(a, b, length):
    d = abs(a - b) % length
    return min(d, length - d)


# ---------------------------------------------------------------------------
# Names and frequencies
# ---------------------------------------------------------------------------


def test_note_names_use_ableton_octaves_and_sharps():
    assert mt.note_name(60) == "C3"
    assert mt.note_name(48) == "C2"
    assert mt.note_name(36) == "C1"
    assert mt.note_name(24) == "C0"
    assert mt.note_name(61) == "C#3"
    assert mt.note_name(46) == "A#1"
    assert mt.note_name(0) == "C-2"
    assert mt.note_name(127) == "G8"


def test_midi_to_hz():
    assert mt.midi_to_hz(69) == 440.0
    assert mt.midi_to_hz(57) == 220.0
    assert mt.midi_to_hz(60) == pytest.approx(261.6256)
    assert mt.midi_to_hz(48) == pytest.approx(130.8128)


# ---------------------------------------------------------------------------
# Low-interval limits
# ---------------------------------------------------------------------------


def test_low_interval_limit_table_and_wide_intervals():
    assert mt.LOW_INTERVAL_LIMITS[3] == 48 and mt.note_name(48) == "C2"
    assert mt.LOW_INTERVAL_LIMITS[7] == 34 and mt.note_name(34) == "A#0"
    assert mt.low_interval_limit(12) == 0
    assert mt.low_interval_limit(24) == 0
    # Above a 9th: limit of interval % 12, relaxed by one octave, never below 0.
    assert mt.low_interval_limit(15) == 48 - 12   # minor 10th
    assert mt.low_interval_limit(19) == 34 - 12   # perfect 12th
    assert mt.low_interval_limit(25) == 52 - 12   # minor 2nd + 2 octaves
    assert all(mt.low_interval_limit(i) >= 0 for i in range(0, 60))


def test_minor_third_limit_is_inclusive_at_c2():
    # C2 + D#2 (Ableton naming): the bottom note sits exactly on the limit, so it's allowed.
    assert mt.low_interval_violations([48, 51]) == []
    # One semitone lower (B1 + D2) breaks the limit.
    v = mt.low_interval_violations([47, 50])
    assert len(v) == 1
    assert v[0]["low"] == 47 and v[0]["high"] == 50 and v[0]["interval"] == 3
    assert v[0]["limit_name"] == "C2"
    assert "B1–D2" in v[0]["message"] and "minor 3rd" in v[0]["message"]
    # C2 + D#2 in scientific naming is MIDI 36 + 39 (Ableton C1 + D#1): flagged.
    assert mt.low_interval_violations([36, 39])[0]["limit_name"] == "C2"


def test_fifth_from_a_sharp_1_is_allowed():
    assert mt.low_interval_violations([46, 53]) == []        # A#1–F2
    assert mt.low_interval_violations([34, 41]) == []        # A#0–F1 (exactly on the limit)
    assert len(mt.low_interval_violations([33, 40])) == 1    # A0–E1


def test_chord_tones_are_checked_against_the_bass():
    # E1 B1 D#2: the adjacent pairs (5th, major 3rd) are fine, but E1–D#2 is a
    # major 7th below F1.
    v = mt.low_interval_violations([40, 47, 51])
    assert [(x["low"], x["high"], x["interval"]) for x in v] == [(40, 51, 11)]
    assert v[0]["limit_name"] == "F1"


def test_octaves_and_unisons_are_never_flagged():
    assert mt.low_interval_violations([12, 24, 36]) == []
    assert mt.low_interval_violations([30, 30]) == []


# ---------------------------------------------------------------------------
# Chord naming
# ---------------------------------------------------------------------------


def test_chord_names():
    assert mt.chord_name([60, 64, 67, 71]) == "Cmaj7"            # rootless Am9 alone
    assert mt.chord_name([57, 60, 64, 67, 71]) == "Am9"          # A-C-E-G-B
    assert mt.chord_name([60, 64, 67, 71], bass=45) == "Am9"     # rootless over bass A
    assert mt.chord_name([45, 48, 52, 55]) == "Am7"
    assert mt.chord_name([48, 52, 57]) == "Am/C"                 # inversion -> slash chord
    assert mt.chord_name([50, 53, 57, 60, 64]) == "Dm9"
    assert mt.chord_name([55, 59, 62, 65]) == "G7"
    assert mt.chord_name([59, 62, 65, 69]) == "Bm7b5"
    assert mt.chord_name([60, 62, 67]) == "Csus2"
    assert mt.chord_name([45, 55, 60]) == "Am7"                  # shell voicing, no 5th


def test_unrecognised_cluster_is_marked_approximate():
    info = mt.identify_chord([60, 61, 62])
    assert info["exact"] is False and info["name"].startswith("~")
    assert mt.chord_name([]) is None


# ---------------------------------------------------------------------------
# review_notes
# ---------------------------------------------------------------------------


def test_review_is_json_serialisable_and_counts():
    notes = straight_16ths() + [N(60, 0, 1, mute=True)]
    r = mt.review_notes(notes, 4, role="drums", bpm=120)
    json.dumps(r)
    assert r["counts"]["notes"] == 17
    assert r["counts"]["muted"] == 1
    assert r["counts"]["active"] == 16
    assert r["counts"]["pitch_range"]["lowest_name"] == "F#1"


def test_review_empty_clip():
    r = mt.review_notes([], 4)
    json.dumps(r)
    assert r["velocity"] is None
    assert any("no unmuted notes" in f for f in r["flags"])


def test_review_measures_58_percent_swing():
    swung = mt.transform_notes(straight_16ths(), {"swing": {"percent": 58, "grid": 0.25}}, 4)
    r = mt.review_notes(swung, 4, bpm=120)
    t = r["timing"]
    assert t["swing_percent"] == pytest.approx(58.0, abs=0.01)
    assert t["off_16ths"]["count"] == 8
    assert t["off_16ths"]["mean_offset"] == pytest.approx(0.04)
    assert t["off_16ths"]["mean_offset_ms"] == pytest.approx(20.0)   # 0.04 beat at 120 bpm
    assert t["on_16ths"]["mean_offset"] == 0.0
    assert t["jitter_std"] == 0.0   # consistent swing isn't jitter
    assert t["on_grid_share"] == 0.5


def test_review_swing_survives_humanize_and_needs_four_off_notes():
    swung = mt.transform_notes(
        straight_16ths(bars=2),
        {"swing": {"percent": 58}, "humanize": {"timing_std": 0.003, "seed": 3}}, 8)
    t = mt.review_notes(swung, 8)["timing"]
    assert t["swing_percent"] == pytest.approx(58.0, abs=1.0)
    assert 0.001 < t["jitter_std"] < 0.006
    # A heavy 70 % swing is still recognised as off-16ths.
    heavy = mt.transform_notes(straight_16ths(), {"swing": {"percent": 70}}, 4)
    assert mt.review_notes(heavy, 4)["timing"]["swing_percent"] == pytest.approx(70.0)
    # With fewer than 4 off-16ths there is no swing estimate.
    few = [N(42, 0), N(42, 0.29), N(42, 1), N(42, 1.29), N(42, 2.29)]
    assert mt.review_notes(few, 4)["timing"]["swing_percent"] is None


def test_review_timing_in_ms():
    r = mt.review_notes([N(36, 0.01), N(36, 1)], 4, bpm=120)
    first = r["timing"]["per_note"][0]
    assert first["offset_beats"] == 0.01
    assert first["offset_ms"] == 5.0


def test_review_velocity_accent_map_and_ghosts():
    notes = [N(42, i * 0.25, 0.1, 100 if i % 2 == 0 else 40) for i in range(16)]
    v = mt.review_notes(notes, 4, role="drums")["velocity"]
    assert v["accent_map_16"] == [100.0, 40.0] * 8
    assert v["ghost_notes"] == 8
    assert v["std"] == 30.0 and v["flat"] is False
    sparse = mt.review_notes([N(36, 0), N(38, 1)], 4)["velocity"]["accent_map_16"]
    assert sparse[0] == 100.0 and sparse[1] is None and sparse[4] == 100.0


def test_review_flags_flat_robotic_and_repetitive_parts():
    eighths = [N(42, i * 0.5, 0.25, 100) for i in range(16)]   # 2 bars
    flags = " | ".join(mt.review_notes(eighths, 8)["flags"])
    assert "velocity is flat (std 0.0) — add an accent map" in flags
    assert "every note is exactly on the grid" in flags
    assert "bar pattern never changes across 2 bars" in flags


def test_review_repetition_form_ignores_humanize():
    bar = [N(36, 0), N(38, 1), N(36, 2.5), N(38, 3)]
    four = mt.tile_notes(bar, 4, 3) + [N(36, 12), N(38, 13), N(38, 15.5)]
    four = mt.transform_notes(four, {"humanize": {"timing_std": 0.003, "seed": 9}}, 16)
    rep = mt.review_notes(four, 16, role="drums")["repetition"]
    assert rep["form"] == "AAAB"
    assert rep["distinct_bar_patterns"] == 2
    assert rep["variation_ratio"] == 0.5


def test_review_names_chords_and_respects_drum_role():
    am9 = [N(p, 0, 4, 80) for p in (57, 60, 64, 67, 71)]
    poly = mt.review_notes(am9, 4, role="chords")["polyphony"]
    assert poly["max_simultaneous"] == 5
    assert poly["chords"][0]["name"] == "Am9"
    assert poly["chords"][0]["notes"] == ["A2", "C3", "E3", "G3", "B3"]
    assert poly["chords"][0]["low_interval_violations"] == []
    drums = mt.review_notes(am9, 4, role="drums")["polyphony"]
    assert drums["chords"] == [] and drums["chord_analysis"] == "skipped for drums"


def test_review_flags_muddy_low_chords():
    notes = [N(p, beat, 1, 90) for beat in (0, 1, 2) for p in (47, 50, 54)]   # Bm, B1 root
    r = mt.review_notes(notes, 4, role="chords")
    assert r["polyphony"]["chords_breaking_low_interval_limits"] == 3
    flag = next(f for f in r["flags"] if "low-interval" in f)
    assert flag.startswith("3 chords break low-interval limits, e.g. B1–D2 minor 3rd")
    # The same notes as drums: no chord/interval checks.
    assert not any("low-interval" in f for f in mt.review_notes(notes, 4, role="drums")["flags"])


def test_review_flags_stacked_duplicates():
    r = mt.review_notes([N(36, 0), N(36, 0), N(38, 1), N(42, 2)], 4)
    assert any("stacked duplicates" in f for f in r["flags"])


def test_review_bass_role_checks():
    bass = [N(40, 0, 1.2), N(52, 0, 0.5), N(43, 1, 0.5), N(45, 2, 0.5)]
    r = mt.review_notes(bass, 4, role="bass")
    flags = " | ".join(r["flags"])
    assert "bass plays up to 2 notes at once" in flags
    assert "bass notes longer than the gap to the next note (legato) — intended?" in flags
    assert r["polyphony"]["max_simultaneous"] == 2
    # The same overlap is not flagged for a pad.
    assert "legato" not in " ".join(mt.review_notes(bass, 4, role="pad")["flags"])


def test_review_articulation_shares():
    notes = [N(40, 0, 0.1), N(40, 1, 0.98), N(43, 2, 2.0)]
    a = mt.review_notes(notes, 4, role="bass")["articulation"]
    assert a["staccato_share"] == pytest.approx(1 / 3, abs=1e-4)
    # 2nd note ends 0.02 before the next onset; the last note runs to the loop end.
    assert a["legato_share"] == pytest.approx(2 / 3, abs=1e-4)
    assert a["long_share"] == pytest.approx(1 / 3, abs=1e-4)


def test_review_flags_notes_outside_and_past_the_clip():
    r = mt.review_notes([N(36, 0), N(36, 4.5), N(40, 3.5, 1.0)], 4)
    flags = " | ".join(r["flags"])
    assert "start outside the clip" in flags
    assert "run past the clip end" in flags
    assert r["counts"]["outside_clip"] == 1


def test_syncopation_score():
    four_on_floor = [N(36, b) for b in (0, 1, 2, 3)]
    s = mt.review_notes(four_on_floor, 4, role="drums")["syncopation"]
    assert s["score"] == 0 and s["off_8th_share"] == 0.0
    # Onsets at 16th slots 0, 3, 6, 10: slot 3 anticipates beat 2 (+2), slot 6
    # anticipates beat 3 (+2), slot 10 anticipates beat 4 (+1).
    pushed = [N(36, 0), N(36, 0.75), N(36, 1.5), N(36, 2.5)]
    s = mt.review_notes(pushed, 4, role="drums")["syncopation"]
    assert s["score"] == 5
    assert s["off_16th_share"] == 0.25
    assert s["off_8th_share"] == 0.5


def test_density():
    notes = [N(60, 0), N(64, 0), N(67, 0), N(60, 2)] + [N(60, 4)]
    d = mt.review_notes(notes, 8)["density"]
    assert d["onsets_per_bar"] == [2, 1]
    assert d["notes_per_beat"] == pytest.approx(5 / 8)


def test_unknown_role_raises():
    with pytest.raises(ValueError):
        mt.review_notes([N(36, 0)], 4, role="vocals")


# ---------------------------------------------------------------------------
# forecast_masking
# ---------------------------------------------------------------------------


def _bass_e1_e2():
    # E1 (40) / E2 (52) octave 8ths.
    return [N(p, i * 0.5, 0.45) for i, p in enumerate([40, 52] * 4)]


def test_masking_flags_bass_against_low_chord_voicing():
    keys_low = [N(p, 0, 4, 80) for p in (52, 55, 59)]          # E2 G2 B2
    res = mt.forecast_masking([
        {"name": "Bass", "notes": _bass_e1_e2(), "clip_length": 4, "role": "bass"},
        {"name": "Keys", "notes": keys_low, "clip_length": 4, "role": "chords"},
    ])
    json.dumps(res)
    low_mid = [c for c in res["conflicts"] if c["zone"] == "low-mid"]
    assert len(low_mid) == 1
    c = low_mid[0]
    assert {c["a"], c["b"]} == {"Bass", "Keys"}
    assert c["share"] == 1.0
    assert c["example_beats"] == [0.0, 0.25, 0.5, 0.75, 1.0]
    assert "raise 'Keys' voicing above" in c["suggestion"] and "drop its root" in c["suggestion"]
    assert not any(c["zone"] == "sub" for c in res["conflicts"])   # chords stay above C2
    regs = {r["name"]: r for r in res["registers"]}
    assert regs["Bass"]["lowest_name"] == "E1" and regs["Bass"]["highest_name"] == "E2"
    assert regs["Keys"]["median_name"] == "G2"


def test_masking_ignores_chords_voiced_at_c4():
    keys_high = [N(p, 0, 4, 80) for p in (72, 76, 79)]         # C4 E4 G4
    res = mt.forecast_masking([
        {"name": "Bass", "notes": _bass_e1_e2(), "clip_length": 4, "role": "bass"},
        {"name": "Keys", "notes": keys_high, "clip_length": 4, "role": "chords"},
    ])
    assert res["conflicts"] == []
    assert "no low-register masking" in res["summary"]


def test_masking_sub_collision_and_drums_excluded():
    pad = [N(p, 0, 4, 70) for p in (43, 50, 55)]               # G1 root under the pad
    kick = [N(36, b, 0.25) for b in (0, 1, 2, 3)]
    res = mt.forecast_masking([
        {"name": "Bass", "notes": _bass_e1_e2(), "clip_length": 4, "role": "bass"},
        {"name": "Pad", "notes": pad, "clip_length": 4, "role": "pad"},
        {"name": "Drums", "notes": kick, "clip_length": 4, "role": "drums"},
    ])
    zones = {(c["zone"]) for c in res["conflicts"]}
    assert zones == {"sub", "low-mid"}
    assert all("Drums" not in (c["a"], c["b"]) for c in res["conflicts"])
    sub = next(c for c in res["conflicts"] if c["zone"] == "sub")
    assert "let 'Bass' own the sub" in sub["suggestion"]
    assert res["rhythmic_layers"] == [
        {"name": "Drums", "role": "drums", "onsets_per_bar": 4.0, "onset_slot_share": 0.25}]


def test_masking_loops_parts_over_the_lcm_span():
    bass = [N(40, 0, 1)]                      # 1 beat every 4
    lead = [N(45, 4, 1)]                      # beat 4 of a 6-beat clip
    res = mt.forecast_masking([
        {"name": "Bass", "notes": bass, "clip_length": 4},
        {"name": "Lead", "notes": lead, "clip_length": 6},
    ])
    assert res["span_beats"] == 12.0
    # Bass sounds at 0, 4 and 8; the lead sounds at 4 and 10. They meet only at beat 4.
    c = res["conflicts"][0]
    assert c["example_beats"] == [4.0, 4.25, 4.5, 4.75]
    capped = mt.forecast_masking([
        {"name": "A", "notes": bass, "clip_length": 7},
        {"name": "B", "notes": lead, "clip_length": 9.75},
    ])
    assert capped["span_beats"] == 64.0


# ---------------------------------------------------------------------------
# transform_notes
# ---------------------------------------------------------------------------


def test_swing_58_moves_off_16ths_by_exactly_0_04():
    out = mt.transform_notes(straight_16ths(), {"swing": {"percent": 58, "grid": 0.25}}, 4)
    for i, s in enumerate(starts(out)):
        assert s == pytest.approx(i * 0.25 + (0.04 if i % 2 else 0.0), abs=1e-12)


def test_swing_is_absolute_and_idempotent():
    ops = {"swing": {"percent": 58, "grid": 0.25}}
    once = mt.transform_notes(straight_16ths(), ops, 4)
    twice = mt.transform_notes(once, ops, 4)
    assert twice == once
    # Changing the amount gives the new absolute value, not 58 + 66.
    re66 = mt.transform_notes(once, {"swing": {"percent": 66}}, 4)
    assert re66 == mt.transform_notes(straight_16ths(), {"swing": {"percent": 66}}, 4)
    assert re66[1]["start_time"] == 0.33
    # 50 % straightens swung notes again.
    assert starts(mt.transform_notes(once, {"swing": {"percent": 50}}, 4)) == \
        [i * 0.25 for i in range(16)]


def test_eighth_swing_leaves_straight_16ths_alone():
    out = mt.transform_notes(straight_16ths(), {"swing": {"percent": 60, "grid": 0.5}}, 4)
    assert starts(out)[:8] == [0.0, 0.25, 0.6, 0.75, 1.0, 1.25, 1.6, 1.75]


def test_scale_snapping_to_a_dorian():
    chromatic = [N(p, i * 0.25) for i, p in enumerate(range(57, 70))]
    expected = [57, 57, 59, 60, 60, 62, 62, 64, 64, 66, 67, 67, 69]   # ties snap down
    by_name = mt.transform_notes(chromatic, {"scale": {"root": 9, "name": "dorian"}}, 4)
    by_ivs = mt.transform_notes(chromatic, {"scale": {"root": "A", "intervals": [0, 2, 3, 5, 7, 9, 10]}}, 4)
    assert [n["pitch"] for n in by_name] == expected
    assert by_ivs == by_name


def test_scale_snaps_to_nearest_not_just_down():
    # C major pentatonic (C D E G A): F is 1 above E -> E; F# is 1 below G (2 above E) -> G.
    out = mt.transform_notes([N(65, 0), N(66, 1)], {"scale": {"root": 0, "name": "pentatonic_major"}}, 4)
    assert [n["pitch"] for n in out] == [64, 67]
    hijaz = mt.transform_notes([N(63, 0)], {"scale": {"root": "D", "name": "hijaz"}}, 4)
    assert hijaz[0]["pitch"] == 63   # D# is the flat 2nd of D hijaz


def test_transpose_clamps_and_sorts():
    out = mt.transform_notes([N(120, 1), N(60, 0)], {"transpose": 12}, 4)
    assert [(n["start_time"], n["pitch"]) for n in out] == [(0.0, 72), (1.0, 127)]


def test_quantize_strength():
    half = mt.transform_notes([N(60, 0.3)], {"quantize": {"grid": 0.25, "strength": 0.5}}, 4)
    full = mt.transform_notes([N(60, 0.3)], {"quantize": {"grid": 0.25}}, 4)
    assert half[0]["start_time"] == 0.275
    assert full[0]["start_time"] == 0.25


def test_negative_push_on_beat_zero_wraps_to_clip_end():
    kicks = [N(36, b, 0.25) for b in (0, 1, 2, 3)]
    out = mt.transform_notes(kicks, {"role_offsets": [{"pitches": [36], "beats": -0.02}]}, 4)
    assert starts(out) == [0.98, 1.98, 2.98, 3.98]
    assert mt.transform_notes([N(36, 0)], {"offset": -0.02}, 4)[0]["start_time"] == 3.98
    assert mt.transform_notes([N(36, 3.99)], {"offset": 0.02}, 4)[0]["start_time"] == 0.01


def test_role_offsets_per_pitch_and_range():
    notes = [N(36, 0), N(39, 1), N(42, 0.5), N(46, 1.5), N(60, 2)]
    ops = {"role_offsets": [{"pitches": [39], "beats": 0.015},
                            {"pitch_range": [42, 46], "beats": -0.005}]}
    got = {n["pitch"]: n["start_time"] for n in mt.transform_notes(notes, ops, 4)}
    assert got == {36: 0.0, 39: 1.015, 42: 0.495, 46: 1.495, 60: 2.0}


def test_accent_map_per_beat_and_per_bar():
    beat_map = mt.transform_notes(straight_16ths(vel=100),
                                  {"velocity": {"accent_map": [110, 60, 85, 60]}}, 4)
    assert [n["velocity"] for n in beat_map] == [110, 60, 85, 60] * 4
    bar16 = [120, 40, 70, 40, 100, 40, 70, 40, 110, 40, 70, 40, 100, 40, 70, 40]
    bar_map = mt.transform_notes(straight_16ths(bars=2),
                                 {"velocity": {"accent_map": bar16, "mode": "set"}}, 8)
    assert [n["velocity"] for n in bar_map] == bar16 * 2
    scaled = mt.transform_notes(straight_16ths(vel=100),
                                {"velocity": {"accent_map": [100, 50, 75, None], "mode": "scale"}}, 4)
    assert [n["velocity"] for n in scaled][:4] == [100, 50, 75, 100]


def test_accent_map_follows_the_unswung_grid_position():
    # A heavy 1/8 swing moves the off-8th from 0.5 to 0.66, nearer the "a" 16th
    # (0.75). It must still get the off-8th accent, not the "a" accent.
    eighths = [N(42, i * 0.5, 0.2, 100) for i in range(8)]
    out = mt.transform_notes(eighths, {"swing": {"percent": 66, "grid": 0.5},
                                       "velocity": {"accent_map": [110, 1, 70, 30]}}, 4)
    assert out[1]["start_time"] == 0.66
    assert [n["velocity"] for n in out] == [110, 70] * 4


def test_velocity_math_ops():
    def vel(notes, op):
        return [n["velocity"] for n in mt.transform_notes(notes, {"velocity": op}, 4)]

    two = [N(60, 0, vel=60), N(60, 1, vel=100)]
    assert vel(two, {"compress": 0.5}) == [70, 90]
    assert vel([N(60, 0, vel=100)], {"multiply": 1.1, "add": -5}) == [105]
    assert vel([N(60, 0, vel=10), N(60, 1, vel=127)], {"min": 40, "max": 110}) == [40, 110]
    assert vel([N(60, 0, vel=100)], {"add": 100}) == [127]
    assert vel([N(60, 0, vel=100)], {"add": -200}) == [1]


def test_articulation_modes():
    notes = [N(40, 0, 0.1), N(43, 1, 0.5), N(45, 2.5, 0.1)]
    stacc = mt.transform_notes(notes, {"articulation": {"mode": "staccato", "length": 0.15}}, 4)
    assert [n["duration"] for n in stacc] == [0.1, 0.15, 0.1]
    half = mt.transform_notes(notes, {"articulation": {"mode": "scale", "factor": 0.5}}, 4)
    assert [n["duration"] for n in half] == [0.05, 0.25, 0.05]
    leg = mt.transform_notes(notes, {"articulation": {"mode": "legato", "gap": 0.02}}, 4)
    # Each note ends 0.02 before the next onset; the last runs to the next loop pass.
    assert [n["duration"] for n in leg] == [0.98, 1.48, 1.48]


def test_legato_uses_pitch_lanes_for_drums_and_onsets_for_chords():
    kit = [N(36, 0, 0.1), N(36, 2, 0.1)] + [N(42, i * 0.5, 0.05) for i in range(8)]
    out = mt.transform_notes(kit, {"articulation": {"mode": "legato", "gap": 0.02, "role": "drums"}}, 4)
    durs = {(n["pitch"], n["start_time"]): n["duration"] for n in out}
    assert durs[(36, 0.0)] == 1.98 and durs[(36, 2.0)] == 1.98
    assert all(d == 0.48 for (p, _), d in durs.items() if p == 42)
    chords = [N(p, t, 0.5) for t in (0, 2) for p in (60, 64, 67)]
    out = mt.transform_notes(chords, {"articulation": {"mode": "legato", "gap": 0.02}}, 4)
    assert {n["duration"] for n in out} == {1.98}


def test_humanize_is_deterministic_bounded_and_respects_exclusions():
    kit = [N(36, b, 0.25, 100) for b in range(4)] + straight_16ths(vel=80)
    ops = {"humanize": {"timing_std": 0.01, "velocity_std": 6, "seed": 7, "exclude_pitches": [36]}}
    a = mt.transform_notes(kit, ops, 4)
    b = mt.transform_notes(kit, ops, 4)
    assert a == b
    shuffled = kit[:]
    random.Random(1).shuffle(shuffled)
    assert mt.transform_notes(shuffled, ops, 4) == a        # input order doesn't matter
    other = mt.transform_notes(kit, dict(ops, humanize=dict(ops["humanize"], seed=8)), 4)
    assert other != a
    kicks = [n for n in a if n["pitch"] == 36]
    assert [(n["start_time"], n["velocity"]) for n in kicks] == [(0.0, 100), (1.0, 100), (2.0, 100), (3.0, 100)]
    hats = [n for n in a if n["pitch"] == 42]
    moved = 0
    for h in hats:
        nearest = round(h["start_time"] / 0.25) * 0.25
        d = circular_distance(h["start_time"], nearest, 4)
        assert d <= 2.5 * 0.01 + 1e-9
        assert abs(h["velocity"] - 80) <= 15
        moved += d > 0
    assert moved >= 8


def test_transform_preserves_extra_keys_and_never_mutates_input():
    notes = [N(60, 0, note_id=11, probability=0.5), N(62, 1, note_id=12)]
    before = copy.deepcopy(notes)
    out = mt.transform_notes(notes, {"transpose": 2, "velocity": {"add": 5}}, 4)
    assert notes == before
    assert out[0]["note_id"] == 11 and out[0]["probability"] == 0.5 and out[0]["pitch"] == 62
    assert out[1]["note_id"] == 12
    json.dumps(out)


def test_durations_are_clamped():
    out = mt.transform_notes([N(60, 0, 10.0), N(62, 1, 0.001)], {}, 4)
    assert [n["duration"] for n in out] == [4.0, 0.01]


def test_invalid_ops_raise():
    with pytest.raises(ValueError):
        mt.transform_notes([N(60, 0)], {"swng": {"percent": 58}}, 4)
    with pytest.raises(ValueError):
        mt.transform_notes([N(60, 0)], {"swing": {"percent": 80}}, 4)
    with pytest.raises(ValueError):
        mt.transform_notes([N(60, 0)], {"velocity": {"accent_map": [1, 2, 3]}}, 4)
    with pytest.raises(ValueError):
        mt.transform_notes([N(60, 0)], {"scale": {"root": 0, "name": "lydianish"}}, 4)
    with pytest.raises(ValueError):
        mt.transform_notes([N(60, 0)], {"articulation": {"mode": "bouncy"}}, 4)
    with pytest.raises(ValueError):
        mt.transform_notes([N(60, 0)], {}, 0)


def test_describe_ops():
    text = mt.describe_ops({
        "transpose": 12,
        "scale": {"root": "A", "name": "dorian"},
        "swing": {"percent": 58, "grid": 0.25},
        "role_offsets": [{"pitches": [39], "beats": 0.015}],
        "velocity": {"accent_map": [110, 60, 85, 60]},
        "humanize": {"timing_std": 0.003, "velocity_std": 4, "seed": 1, "exclude_pitches": [36]},
    })
    for part in ("transpose +12", "A dorian", "swing off-1/16 notes to 58%", "D#1 +0.015",
                 "4-step accent map", "never touching C1"):
        assert part in text
    assert mt.describe_ops({}) == "no changes"


# ---------------------------------------------------------------------------
# tile_notes
# ---------------------------------------------------------------------------


def test_tile_notes_copies_and_offsets():
    pattern = [N(36, 0, note_id=1), N(42, 0.5, note_id=2)]
    before = copy.deepcopy(pattern)
    out = mt.tile_notes(pattern, 4, 3)
    assert pattern == before
    assert [(n["start_time"], n["pitch"]) for n in out] == [
        (0.0, 36), (0.5, 42), (4.0, 36), (4.5, 42), (8.0, 36), (8.5, 42)]
    assert [n.get("note_id") for n in out] == [1, 2, None, None, None, None]
    out[0]["velocity"] = 1
    assert pattern[0]["velocity"] == 100
    assert mt.tile_notes(pattern, 4, 1) == sorted(before, key=lambda n: n["start_time"])
    with pytest.raises(ValueError):
        mt.tile_notes(pattern, 4, 0)
    with pytest.raises(ValueError):
        mt.tile_notes(pattern, 0, 2)
