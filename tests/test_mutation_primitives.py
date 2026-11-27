"""Shared identity and rollback regressions, independent of a Live installation."""
import struct
import types
import pytest
from tests.test_remote_script_bridge import _load_script_module, make_instance

@pytest.fixture
def rs():
    return _load_script_module()


def test_float32_readback_is_accepted(rs):
    class Float32:
        _value = 0.0
        @property
        def value(self): return self._value
        @value.setter
        def value(self, v): self._value = struct.unpack('f', struct.pack('f', v))[0]
    param = Float32()
    assert rs.apply_changes([(param, 'value', 0.1)])['verified']


def test_invalid_later_field_never_mutates(rs):
    first = types.SimpleNamespace(value=1.0)
    second = types.SimpleNamespace(value=2.0)
    with pytest.raises(ValueError):
        rs.apply_changes([(first, 'value', 0.5), (second, 'value', float('nan'))])
    assert first.value == 1.0


def test_failed_setter_is_included_in_rollback(rs):
    class FailAfterWrite:
        _value = 2.0
        @property
        def value(self): return self._value
        @value.setter
        def value(self, value):
            self._value = value
            if value == 3: raise RuntimeError('after write')
    first = types.SimpleNamespace(value=1.0)
    second = FailAfterWrite()
    with pytest.raises(rs.CommandFailure) as exc:
        rs.apply_changes([(first, 'value', 2.0), (second, 'value', 3.0)])
    assert exc.value.details['rollback_complete']
    assert (first.value, second.value) == (1.0, 2.0)


def test_failed_rollback_is_reported(rs):
    class Broken:
        @property
        def value(self): return 1.0
        @value.setter
        def value(self, value): raise RuntimeError('write refused')
    with pytest.raises(rs.CommandFailure) as exc:
        rs.apply_changes([(Broken(), 'value', 2.0)])
    assert not exc.value.details['rollback_complete']
    assert exc.value.details['rollback_failures'][0]['field'] == 'value'


def test_duplicate_names_and_moved_targets_are_distinct(rs):
    class Track:
        name = 'Duplicate'
    a, b = Track(), Track()
    inst = make_instance(rs)
    inst._song = types.SimpleNamespace(tracks=[a, b])
    token = inst._get_target_identity({'track_index': 0})['target_id']
    assert token != inst._get_target_identity({'track_index': 1})['target_id']
    inst._song.tracks = [b, a]
    with pytest.raises(rs.CommandFailure, match='identity changed'):
        inst._resolve_track({'track_index': 0, 'target_id': token}, True)
    assert inst._resolve_track({'track_index': 1, 'target_id': token}, True)[0] is a


def test_equal_live_proxies_keep_identity(rs):
    class Proxy:
        def __init__(self, ptr): self.ptr = ptr
        def __eq__(self, other): return self.ptr == other.ptr
    inst = make_instance(rs)
    token = inst._identity_for(Proxy(42))
    assert inst._identity_for(Proxy(42)) == token
    inst._check_identity(Proxy(42), token, True)


@pytest.mark.parametrize('value', [True, -1, 0.5, '0'])
def test_strict_target_indices(rs, value):
    with pytest.raises(ValueError): rs.strict_index(value, 'index')


@pytest.mark.parametrize('failure', ['before', 'during', 'after', None])
def test_undo_boundaries_and_structured_errors(rs, failure):
    inst = make_instance(rs)
    events = []
    def begin():
        events.append('begin')
        if failure == 'before': raise RuntimeError('cannot begin')
    def end():
        events.append('end')
        if failure == 'after': raise RuntimeError('cannot end')
    def edit():
        events.append('edit')
        if failure == 'during': raise rs.CommandFailure('injected', 'failed', {'rollback_complete': True})
        return {'ok': True}
    inst._song = types.SimpleNamespace(begin_undo_step=begin, end_undo_step=end)
    inst._start_playback = edit
    result = inst._execute_command({'type': 'start_playback'})
    assert events == (['begin'] if failure == 'before' else ['begin', 'edit', 'end'])
    if failure:
        assert result['status'] == 'error'
        assert result['error']['command'] == 'start_playback'
    else:
        assert result['status'] == 'success'


def test_reads_do_not_open_undo_group(rs):
    inst = make_instance(rs)
    events = []
    inst._song = types.SimpleNamespace(begin_undo_step=lambda: events.append('begin'), end_undo_step=lambda: events.append('end'))
    inst._get_session_info = lambda: {}
    assert inst._execute_command({'type': 'get_session_info'})['status'] == 'success'
    assert events == []
