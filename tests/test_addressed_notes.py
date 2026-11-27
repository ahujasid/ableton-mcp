import copy
import types
import pytest
from tests.test_remote_script_bridge import _load_script_module, make_instance

class Clip:
    is_midi_clip = True
    name = 'Notes'
    def __init__(self):
        self.notes=[types.SimpleNamespace(note_id=i,pitch=60,start_time=0.,duration=1.,velocity=100.,mute=False,probability=.4,velocity_deviation=2.,release_velocity=30.) for i in (1,2)]
        self.applied=0
    def get_all_notes_extended(self): return copy.deepcopy(self.notes)
    def apply_note_modifications(self, notes): self.applied+=1; self.notes=copy.deepcopy(notes)

@pytest.fixture
def setup():
    rs=_load_script_module();inst=make_instance(rs);session=Clip();arrangement=Clip()
    track=types.SimpleNamespace(name='T',clip_slots=[types.SimpleNamespace(has_clip=True,clip=session)],arrangement_clips=[arrangement])
    inst._song=types.SimpleNamespace(tracks=[track])
    params={'track_index':0,'target_id':inst._identity_for(track),'location':'arrangement','clip_index':0,'clip_id':inst._identity_for(arrangement)}
    return rs,inst,session,arrangement,params


def test_arrangement_edit_preserves_duplicate_note_ids_and_metadata(setup):
    rs,inst,session,clip,params=setup
    op=inst._cmd_modify_notes(dict(params,notes=[{'note_id':2,'velocity':0}]))
    assert op.poll()['modified_ids']==[2];op.close()
    assert [n.velocity for n in clip.notes]==[100,0]
    assert [n.note_id for n in clip.notes]==[1,2]
    assert clip.notes[1].probability==.4 and clip.notes[1].release_velocity==30
    assert session.applied==0


@pytest.mark.parametrize('edits', [[{'note_id':3,'velocity':4}], [{'note_id':1,'velocity':4},{'note_id':2,'pitch':128}], [{'note_id':1,'velocity':4},{'note_id':1,'pitch':61}]])
def test_stale_duplicate_or_invalid_ids_never_apply(setup,edits):
    rs,inst,session,clip,params=setup
    with pytest.raises(ValueError): inst._cmd_modify_notes(dict(params,notes=edits))
    assert clip.applied==0


def test_explicit_location_and_host_capability_required(setup):
    rs,inst,session,clip,params=setup
    with pytest.raises(ValueError,match='explicit location'): inst._cmd_get_notes({'track_index':0,'clip_index':0})
    del inst._song.tracks[0].arrangement_clips
    with pytest.raises(ValueError,match='unsupported'): inst._cmd_get_notes(params)
    assert session.applied==0


def test_wrong_clip_identity_cannot_touch_session(setup):
    rs,inst,session,clip,params=setup
    with pytest.raises(rs.CommandFailure): inst._cmd_modify_notes(dict(params,location='session',notes=[{'note_id':1,'pitch':61}]))
    assert session.applied==clip.applied==0


def test_edit_limit_rejected_before_host_read(setup):
    rs,inst,session,clip,params=setup
    clip.get_all_notes_extended=lambda: pytest.fail('must not allocate host notes')
    with pytest.raises(ValueError,match='10000'): inst._cmd_modify_notes(dict(params,notes=[{'note_id':1}]*10001))
