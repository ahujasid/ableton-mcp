import types
import pytest
from tests.test_remote_script_bridge import _load_script_module, make_instance
from tests.test_integrated_mixer import Param

@pytest.fixture
def setup():
    rs = _load_script_module(); inst = make_instance(rs)
    p = Param(.5, 0, 2); p.name = 'Frequency'; p.is_quantized = False
    p.str_for_value = lambda value: '%s kHz' % value
    dev = types.SimpleNamespace(name='Filter', class_name='AutoFilter', parameters=[p], can_have_chains=False)
    track = types.SimpleNamespace(name='T', devices=[dev])
    inst._song = types.SimpleNamespace(tracks=[track])
    args = {'target_id': inst._identity_for(track), 'device_id': inst._identity_for(dev), 'parameter_id': inst._identity_for(p), 'parameter_index': 0}
    return rs, inst, dev, p, args


def test_hz_khz_ms_seconds_conversion_without_writes(setup):
    rs, inst, dev, p, args = setup
    assert abs(inst._value_for_display(p, '1000 Hz') - 1) < 1e-6
    p.str_for_value = lambda value: '%s ms' % (value * 1000)
    assert abs(inst._value_for_display(p, '0.25 s') - .25) < 1e-6
    assert p.value == .5


@pytest.mark.parametrize('text', ['25R', '1 bananas', 'NaN Hz', '1 dB'])
def test_ambiguous_units_rejected_without_write(setup, text):
    rs, inst, dev, p, args = setup
    with pytest.raises(ValueError): inst._value_for_display(p, text)
    assert p.value == .5


def test_nonmonotonic_mapping_rejected(setup):
    rs, inst, dev, p, args = setup
    p.str_for_value = lambda value: '%s Hz' % (value if value < 1 else 2-value)
    with pytest.raises(ValueError, match='Nonmonotonic'): inst._value_for_display(p, '.5 Hz')


def test_discovery_has_no_writes_and_parameter_edit_requires_identity(setup):
    rs, inst, dev, p, args = setup
    result = inst._cmd_get_device_chain({})
    assert result['devices'][0]['parameters'][0]['parameter_id'] == args['parameter_id']
    assert p.value == .5
    bad = dict(args, device_id='stale', value=.2)
    with pytest.raises(rs.CommandFailure): inst._cmd_set_device_parameter_value(bad)
    op = inst._cmd_set_device_parameter_value(dict(args, display_value='1000 Hz'))
    assert abs(op.poll()['value'] - 1) < 1e-6; op.close()


def test_simpler_class_and_all_fields_preflight(setup):
    rs, inst, dev, p, args = setup
    with pytest.raises(ValueError, match='not Simpler'): inst._cmd_get_simpler({})
    dev.class_name = 'OriginalSimpler'; dev.voices=4; dev.retrigger=False; dev.playback_mode=0; dev.sample=None
    selector = {key: args[key] for key in ('target_id','device_id')}
    with pytest.raises(ValueError): inst._cmd_edit_simpler(dict(selector, voices=8, retrigger='false'))
    assert dev.voices == 4
    op = inst._cmd_edit_simpler(dict(selector, voices=8, retrigger=True))
    assert op.poll()['voices'] == 8; op.close()


def test_nested_rack_paths_and_bounds(setup):
    rs, inst, dev, p, args = setup
    child = types.SimpleNamespace(name='Child', class_name='Utility', parameters=[], can_have_chains=False)
    chain = types.SimpleNamespace(name='Chain', devices=[child])
    dev.can_have_chains=True; dev.chains=[chain]
    assert inst._resolve_device({'device_path':[0,0,0]})[1] is child
    with pytest.raises(ValueError): inst._resolve_device({'device_path':[0]*11})
    result=inst._cmd_get_rack({})
    assert result['chains'][0]['devices'][0]['device_path']==[0,0,0]
