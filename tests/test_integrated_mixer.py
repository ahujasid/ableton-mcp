import json
import types
import pytest
from tests.test_remote_script_bridge import _load_script_module, make_instance

class Param:
    def __init__(self, value, low=0, high=1, display=None):
        self.value, self.min, self.max = value, low, high
        self.display = display
    def str_for_value(self, value):
        return self.display or ('-inf dB' if value == 0 else '%s dB' % (-60 + value * 66))

@pytest.fixture
def setup():
    rs = _load_script_module()
    inst = make_instance(rs)
    track = types.SimpleNamespace(name='T', mute=False, solo=False, arm=False, can_be_armed=True,
        mixer_device=types.SimpleNamespace(volume=Param(.5), panning=Param(.25, -1, 1, '25R'), sends=[Param(.2)]))
    inst._song = types.SimpleNamespace(tracks=[track], return_tracks=[], master_track=track)
    return rs, inst, track, inst._get_target_identity({})['target_id']


def test_pan_is_not_db_and_silence_is_json(setup):
    rs, inst, track, token = setup
    track.mixer_device.volume.value = 0
    result = inst._cmd_get_mixer_state({})
    assert result['panning']['pan_percent'] == 25 and 'db' not in result['panning']
    assert result['volume']['db'] is None and result['volume']['silence']
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize('fields', [{'volume': .3, 'panning': 2}, {'volume': .3, 'sends': {'1': .5}}, {'volume': .3, 'mute': 'false'}])
def test_invalid_later_field_prevents_mixer_write(setup, fields):
    rs, inst, track, token = setup
    with pytest.raises((ValueError, IndexError)):
        inst._cmd_set_track_mixer(dict(fields, target_id=token))
    assert track.mixer_device.volume.value == .5


def test_mixer_requires_identity_and_handles_complete_transaction(setup):
    rs, inst, track, token = setup
    with pytest.raises(rs.CommandFailure): inst._cmd_set_track_mixer({'volume': .3})
    op = inst._cmd_set_track_mixer({'target_id': token, 'volume': .3, 'panning': -.5, 'mute': True})
    result = op.poll(); op.close()
    assert result['volume']['value'] == .3 and track.mute


def test_master_rejects_sends_before_other_writes(setup):
    rs, inst, track, token = setup
    with pytest.raises(ValueError):
        inst._cmd_set_track_mixer({'track_type': 'master', 'target_id': token, 'volume': .3, 'sends': {'0': .5}})
    assert track.mixer_device.volume.value == .5


def test_db_conversion_is_pure_and_rejects_nonmonotonic(setup):
    rs, inst, track, token = setup
    p = track.mixer_device.volume
    assert abs(inst._value_for_db(p, -6) - 54 / 66) < 1e-6
    assert p.value == .5
    p.str_for_value = lambda v: '%s dB' % (v if v < .5 else -v)
    with pytest.raises(ValueError, match='Nonmonotonic'): inst._value_for_db(p, -.2)
