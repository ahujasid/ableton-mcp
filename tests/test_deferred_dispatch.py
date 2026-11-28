import types
import pytest
from tests.test_remote_script_bridge import _load_script_module, make_instance, start_request, finish_request

@pytest.fixture
def rs(): return _load_script_module()


def test_deferred_owns_undo_until_completion_and_blocks_unrelated_work(rs):
    inst = make_instance(rs)
    events = []
    inst._song = types.SimpleNamespace(begin_undo_step=lambda: events.append('begin'), end_undo_step=lambda: events.append('end'))
    polls = []
    def step():
        polls.append(1)
        return rs._WAIT_FOR_TICK if len(polls) == 1 else {'done': True}
    inst._start_playback = lambda: rs.DeferredOperation(step, lambda failed: events.append(('cleanup', failed)))
    inst._stop_playback = lambda: events.append('stop')
    first, first_replies = start_request(inst, {'type': 'start_playback'})
    inst.update_display()
    second, second_replies = start_request(inst, {'type': 'stop_playback'})
    inst.update_display()
    assert events == ['begin']
    inst.update_display()
    assert finish_request(first, first_replies)['result'] == {'done': True}
    assert events == ['begin', ('cleanup', False), 'end']
    inst.update_display()
    finish_request(second, second_replies)
    assert events[-3:] == ['begin', 'stop', 'end']


def test_cancelled_deferred_never_calls_late_step(rs):
    inst = make_instance(rs)
    calls = []
    inst._start_playback = lambda: rs.DeferredOperation(lambda: calls.append('late'), lambda failed: calls.append(('cleanup', failed)))
    worker, replies = start_request(inst, {'type': 'start_playback'})
    inst.update_display()
    request, _ = inst._active_deferred
    request.cancel('deadline')
    assert 'outcome unknown' in finish_request(worker, replies)['message']
    inst.update_display()
    inst.update_display()
    assert calls == [('cleanup', True)]


def test_shutdown_closes_deferred_and_invalidates_old_identity(rs):
    inst = make_instance(rs)
    calls = []
    obj = object()
    token = inst._identity_for(obj)
    inst._start_playback = lambda: rs.DeferredOperation(lambda: calls.append('late'), lambda failed: calls.append(('cleanup', failed)))
    worker, replies = start_request(inst, {'type': 'start_playback'})
    inst.update_display()
    inst._shutdown_commands()
    assert 'outcome unknown' in finish_request(worker, replies)['message']
    inst.update_display()
    assert calls == [('cleanup', True)]
    with pytest.raises(rs.CommandFailure): inst._check_identity(obj, token, True)


def test_poll_budget_is_bounded(rs):
    inst = make_instance(rs)
    cleanup = []
    inst._start_playback = lambda: rs.DeferredOperation(lambda: rs._WAIT_FOR_TICK, lambda failed: cleanup.append(failed), max_ticks=2)
    worker, replies = start_request(inst, {'type': 'start_playback'})
    for _ in range(4): inst.update_display()
    result = finish_request(worker, replies)
    assert result['error']['code'] == 'completion_timeout'
    assert cleanup == [True]


class Song:
    is_playing = False
    current_song_time = 8.0
    def __init__(self):
        self.cue_points = []
        self.toggles = []
    def set_or_delete_cue(self):
        self.toggles.append(self.current_song_time)
        matches = [c for c in self.cue_points if c.time == self.current_song_time]
        if matches: self.cue_points.remove(matches[0])
        else: self.cue_points.append(types.SimpleNamespace(time=self.current_song_time, name=''))


def test_locator_phases_and_restore(rs):
    inst = make_instance(rs)
    inst._song = Song()
    worker, replies = start_request(inst, {'type': 'create_locator', 'params': {'name': 'A', 'time': 16.0}})
    inst.update_display()
    assert inst._song.toggles == []
    inst.update_display()
    assert inst._song.toggles == [16.0]
    assert not replies
    inst.update_display()
    assert finish_request(worker, replies)['result']['name'] == 'A'
    assert inst._song.current_song_time == 8.0


def test_existing_locator_is_not_toggled(rs):
    inst = make_instance(rs)
    inst._song = Song()
    cue = types.SimpleNamespace(time=16.0, name='Existing')
    inst._song.cue_points = [cue]
    assert inst._create_locator('Renamed', 16)['created'] is False
    assert inst._song.toggles == [] and cue.name == 'Renamed'


def test_load_requires_observed_change_and_restores_selection(rs):
    class Device: pass
    old = Device(); old.name = 'A'; old.parameters = []
    selected = object()
    track = types.SimpleNamespace(name='T', devices=[old])
    view = types.SimpleNamespace(selected_track=selected)
    inst = make_instance(rs)
    inst._song = types.SimpleNamespace(tracks=[track], view=view)
    loaded = []
    item = types.SimpleNamespace(name='A', is_loadable=True)
    inst.application = lambda: types.SimpleNamespace(browser=types.SimpleNamespace(load_item=lambda i: loaded.append(i)))
    inst._find_browser_item_by_uri = lambda *a: item
    op = inst._load_browser_item(0, 'uri')
    assert op.poll() is rs._WAIT_FOR_TICK
    fresh = Device(); fresh.name = 'A'; fresh.parameters = []
    track.devices = [fresh]
    assert op.poll()['settled']
    op.close()
    assert view.selected_track is selected and loaded == [item]


def test_transaction_waits_for_async_readback(rs):
    class AsyncValue:
        value = 1.0
        def __setattr__(self, key, value):
            if key == 'value': object.__setattr__(self, 'pending', value)
            else: object.__setattr__(self, key, value)
        def tick(self): object.__setattr__(self, 'value', self.pending)
    inst = make_instance(rs)
    value = AsyncValue()
    op = inst._transaction([(value, 'value', 0.1)])
    value.tick()
    assert op.poll()['verified']
    op.close()


def test_transaction_verifies_rollback_on_later_tick(rs):
    inst = make_instance(rs)
    value = types.SimpleNamespace(value=1.0)
    op = inst._transaction([(value, 'value', 0.1)])
    value.value = 0.5  # simulate host rejecting/clamping desired value
    assert op.poll() is rs._WAIT_FOR_TICK
    assert value.value == 1.0
    with pytest.raises(rs.CommandFailure) as exc: op.poll()
    assert exc.value.details['rollback_complete']
    op.close(failed=True)


def test_locator_cancel_after_toggle_removes_only_created_cue(rs):
    inst = make_instance(rs); inst._song = Song()
    existing = types.SimpleNamespace(time=4, name='Keep')
    inst._song.cue_points = [existing]
    op = inst._create_locator('Cancel', 16)
    assert op.poll() is rs._WAIT_FOR_TICK
    assert len(inst._song.cue_points) == 2
    op.close(failed=True)
    assert inst._song.cue_points == [existing]
    assert inst._song.current_song_time == 8


def test_locator_cancel_does_not_toggle_at_changed_playhead(rs):
    inst = make_instance(rs); inst._song = Song()
    op = inst._create_locator('Cancel', 16); op.poll()
    inst._song.current_song_time = 32
    with pytest.raises(rs.CommandFailure, match='safely removed'): op.close(failed=True)
    assert inst._song.current_song_time == 32
    assert inst._song.toggles == [16]
