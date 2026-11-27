import types
import pytest
from tests.test_remote_script_bridge import _load_script_module, make_instance

class Choice:
    def __init__(self, name): self.display_name = name

@pytest.fixture
def setup():
    rs = _load_script_module(); inst = make_instance(rs)
    track = types.SimpleNamespace(name='Routing')
    for _, attr in rs.ROUTING_FIELDS:
        options = [Choice('A'), Choice('B')]
        setattr(track, attr, options[0]); setattr(track, 'available_' + attr + 's', options)
    inst._song = types.SimpleNamespace(tracks=[track])
    return rs, inst, track, inst._get_target_identity({})['target_id']


def test_invalid_later_route_leaves_all_routes(setup):
    rs, inst, track, token = setup
    with pytest.raises(ValueError):
        inst._cmd_set_track_routing({'target_id': token, 'input_type': 'B', 'output_type': 'Missing'})
    assert track.input_routing_type.display_name == 'A'


def test_type_and_dependent_channel_are_rejected_before_writes(setup):
    rs, inst, track, token = setup
    with pytest.raises(ValueError, match='type first'):
        inst._cmd_set_track_routing({'target_id': token, 'input_type': 'B', 'input_channel': 'A'})
    assert track.input_routing_type.display_name == 'A'


def test_exact_localized_name_and_transaction(setup):
    rs, inst, track, token = setup
    track.available_output_routing_types[1].display_name = 'Externe Ausgabe'
    op = inst._cmd_set_track_routing({'target_id': token, 'output_type': 'Externe Ausgabe'})
    assert op.poll()['output_type'] == 'Externe Ausgabe'
    op.close()


def test_ambiguous_names_rejected(setup):
    rs, inst, track, token = setup
    track.available_output_routing_types[1].display_name = 'A'
    with pytest.raises(ValueError, match='ambiguous'):
        inst._cmd_set_track_routing({'target_id': token, 'output_type': 'A'})


def test_rollback_restores_dependent_channel(setup):
    rs, inst, track, token = setup
    old_type, old_channel = track.output_routing_type, track.output_routing_channel
    op = inst._cmd_set_track_routing({'target_id': token, 'output_type': 'B'})
    track.output_routing_type = Choice('Host refusal')
    track.output_routing_channel = Choice('Host changed channel')
    assert op.poll() is rs._WAIT_FOR_TICK
    with pytest.raises(rs.CommandFailure) as exc: op.poll()
    assert exc.value.details['rollback_complete']
    assert track.output_routing_type is old_type and track.output_routing_channel is old_channel
    op.close(failed=True)
