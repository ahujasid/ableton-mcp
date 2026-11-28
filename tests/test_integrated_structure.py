import types
import pytest
from tests.test_remote_script_bridge import _load_script_module, make_instance

class Slot:
    has_clip = False
    clip = None
    def create_clip(self, length): raise RuntimeError('clip create failed')
    def duplicate_clip_to(self, other):
        if other.has_clip: raise AssertionError('overwrite')
        other.clip = types.SimpleNamespace(name='copy')
        other.has_clip = True
    def delete_clip(self):
        self.clip = None; self.has_clip = False

class Track:
    def __init__(self, name): self.name = name; self.clip_slots = [Slot(), Slot()]

class Song:
    file_path = ''
    def __init__(self): self.tracks = [Track('Existing')]; self.scenes = [object()]; self.deleted = []
    def create_midi_track(self, index): self.tracks.append(Track('New'))
    def delete_track(self, index): self.deleted.append(self.tracks.pop(index))

@pytest.fixture
def setup(monkeypatch, tmp_path):
    path = tmp_path/'safety.json'; path.write_text('{}')
    monkeypatch.setenv('ABLETON_MCP_SAFETY_CONFIG', str(path))
    rs = _load_script_module(); inst = make_instance(rs); inst._song = Song()
    return rs, inst


def test_compound_create_failure_removes_only_owned_track(setup):
    rs, inst = setup; existing = inst._song.tracks[0]
    with pytest.raises(rs.CommandFailure, match='clip create failed'):
        inst._cmd_edit_structure({'action': 'create_track', 'clip_length': 4})
    assert inst._song.tracks == [existing]
    assert inst._song.deleted[0] is not existing


def test_duplicate_names_and_reordering_do_not_authorize_rename(setup):
    rs, inst = setup
    token = inst._identity_for(inst._song.tracks[0])
    other = Track('Existing'); inst._song.tracks.insert(0, other)
    with pytest.raises(rs.CommandFailure):
        inst._cmd_edit_structure({'action': 'rename_track', 'target_id': token, 'track_index': 0, 'name': 'Wrong'})
    assert other.name == 'Existing'


def test_occupied_destination_is_preserved(setup):
    rs, inst = setup; track = inst._song.tracks[0]
    source, dest = track.clip_slots
    source.clip = object(); source.has_clip = True
    dest.clip = object(); dest.has_clip = True; old = dest.clip
    with pytest.raises(ValueError, match='occupied'):
        inst._cmd_edit_structure({'action': 'duplicate_clip', 'target_id': inst._identity_for(track), 'clip_index': 0,
          'clip_id': inst._identity_for(source.clip), 'destination_index': 1, 'destination_slot_id': inst._identity_for(dest)})
    assert dest.clip is old


def test_deletion_policy_applies_to_compound_api(setup):
    rs, inst = setup; track = inst._song.tracks[0]
    with pytest.raises(rs.CommandFailure, match='refuses delete'):
        inst._cmd_edit_structure({'action': 'delete_track', 'target_id': inst._identity_for(track)})
    assert inst._song.tracks == [track]


def test_unknown_structural_fields_and_invalid_length_write_nothing(setup):
    rs, inst = setup
    for params in [{'action': 'create_track', 'clip_length': float('nan')}, {'action': 'create_track', 'arbitrary': 1}]:
        with pytest.raises(ValueError): inst._cmd_edit_structure(params)
    assert len(inst._song.tracks) == 1


def test_host_create_raises_after_write_cleans_owned_object(setup):
    rs, inst = setup; existing = inst._song.tracks[0]
    def create(index):
        inst._song.tracks.append(Track('Partially created'))
        raise RuntimeError('host failure after write')
    inst._song.create_midi_track = create
    with pytest.raises(rs.CommandFailure) as exc:
        inst._cmd_edit_structure({'action': 'create_track'})
    assert exc.value.details['rollback_complete']
    assert inst._song.tracks == [existing]
