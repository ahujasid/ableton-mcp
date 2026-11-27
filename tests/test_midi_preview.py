"""Focused preview regressions extracted from PR #146."""
import copy
import json
import random

import pytest

from MCP_Server import midi_preview as mt


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
    assert vel([N(60, 0, vel=100)], {"add": -200}) == [0]


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


@pytest.mark.parametrize('ops', [{'offset': float('inf')}, {'humanize': {'timing_std': float('nan')}}, {'role_offsets': [{'pitch':60,'beats':0}]*129}])
def test_preview_rejects_unbounded_operations(ops):
    with pytest.raises(ValueError): mt.transform_notes([N(60,0)],ops,4)


def test_preview_bounds_before_processing_and_keeps_zero_velocity():
    with pytest.raises(ValueError,match='10000'): mt.transform_notes([N(60,0)]*10001,{},4)
    note=N(60,0,vel=0,note_id=9,probability=.2,release_velocity=30)
    result=mt.transform_notes([note],{},4)
    assert result[0]['velocity']==0 and result[0]['note_id']==9 and result[0]['probability']==.2
    assert note['release_velocity']==30
