import types
import pytest
from tests.test_remote_script_bridge import _load_script_module, make_instance

class Group:
    name='Group'; has_audio_input=False; has_midi_input=False; can_be_armed=False
    mute=False;solo=False;clip_slots=[];devices=[];arrangement_clips=[]
    @property
    def arm(self): raise RuntimeError('groups have no arm state')


def test_group_overview_uses_safe_arm():
    rs=_load_script_module();inst=make_instance(rs);inst._song=types.SimpleNamespace(tempo=120,tracks=[Group()])
    out=inst._cmd_get_tracks_overview({})
    assert out['tracks'][0]['arm'] is False


@pytest.mark.parametrize('bar',[0,-1,True,float('inf'),float('nan'),'4'])
def test_invalid_bar_size_rejected(bar):
    rs=_load_script_module();inst=make_instance(rs)
    with pytest.raises(ValueError): inst._cmd_check_arrangement_sync({'bar_beats':bar})


def test_nested_overlaps_use_maximum_end_and_never_mutate():
    rs=_load_script_module();inst=make_instance(rs);track=Group()
    track.arrangement_clips=[types.SimpleNamespace(name='a',start_time=0.,end_time=16.),types.SimpleNamespace(name='b',start_time=4.,end_time=8.),types.SimpleNamespace(name='c',start_time=12.,end_time=20.)]
    inst._song=types.SimpleNamespace(tracks=[track])
    op=inst._cmd_check_arrangement_sync({})
    assert op.poll() is rs._WAIT_FOR_TICK
    result=op.poll()
    assert result['overlaps']==2 and result['in_sync'] is False
    assert track.arrangement_clips[0].end_time==16.
