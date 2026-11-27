import types
import pytest
from tests.test_remote_script_bridge import _load_script_module, make_instance

@pytest.fixture
def setup():
    rs=_load_script_module();inst=make_instance(rs)
    inst._song=types.SimpleNamespace(tempo=120.,signature_numerator=4,signature_denominator=4,metronome=False,is_playing=False,current_song_time=0.)
    return rs,inst

@pytest.mark.parametrize('params',[{'tempo':130,'signature_denominator':3},{'tempo':float('nan')},{'metronome':'false'},{'tempo':130,'scale_mode':True},{'tempo':130,'loop':True}])
def test_invalid_or_unsupported_settings_preflight_all(setup,params):
    rs,inst=setup
    with pytest.raises(ValueError):inst._cmd_set_song_settings(params)
    assert inst._song.tempo==120.


def test_song_settings_verify_after_tick(setup):
    rs,inst=setup
    op=inst._cmd_set_song_settings({'tempo':130,'signature_numerator':3,'metronome':True})
    result=op.poll();op.close()
    assert result['tempo']==130 and result['signature_numerator']==3 and result['metronome']
    assert result['scale_mode'] is None and 'scale_mode' not in result['supported_settings']


def test_seek_range_and_playback_gate(setup):
    rs,inst=setup
    with pytest.raises(ValueError):inst._set_current_song_time(float('inf'))
    inst._song.is_playing=True
    with pytest.raises(ValueError):inst._set_current_song_time(16)
    assert inst._song.current_song_time==0
