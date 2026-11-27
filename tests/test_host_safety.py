import json
import pytest
from tests.test_remote_script_bridge import _load_script_module, make_instance

@pytest.fixture
def rs(monkeypatch, tmp_path):
    path = tmp_path / 'safety.json'
    path.write_text('{}')
    monkeypatch.setenv('ABLETON_MCP_SAFETY_CONFIG', str(path))
    return _load_script_module()

@pytest.mark.parametrize('raw', [
    {'read_only': 'false'}, {'read_only': 0}, {'allow': {'delete': 'false'}},
    {'deny_commands': 'delete_track'}, {'allow_commands': 'delete_track'},
    {'allow': []}, {'allow': {'mystery': True}}, {'unknown': True},
    {'saved_set_allow': {'delete': 1}}, {'deny_commands': [7]},
])
def test_malformed_policy_rejected(rs, raw):
    with pytest.raises(ValueError): rs.validate_safety_config(raw)


def test_false_never_enables_deletion(rs):
    cfg = rs.validate_safety_config({'allow': {'delete': False}, 'allow_commands': ['delete_clip']})
    assert cfg['allow']['delete'] is False


@pytest.mark.parametrize('raw', [
    {'read_only': True}, {'allow': {'edit': False}},
    {'deny_commands': ['set_tempo']}, {'allow': {'edit': 'false'}},
])
def test_direct_dispatch_cannot_bypass_policy(rs, monkeypatch, tmp_path, raw):
    path = tmp_path / 'direct.json'
    path.write_text(json.dumps(raw))
    monkeypatch.setenv('ABLETON_MCP_SAFETY_CONFIG', str(path))
    inst = make_instance(rs)
    writes = []
    inst._set_tempo = lambda value: writes.append(value)
    result = inst._execute_command({'type': 'set_tempo', 'params': {'tempo': 130}})
    assert result['error']['code'] == 'safety_refused'
    assert writes == []


def test_missing_explicit_policy_fails_closed(rs, monkeypatch, tmp_path):
    monkeypatch.setenv('ABLETON_MCP_SAFETY_CONFIG', str(tmp_path / 'missing.json'))
    inst = make_instance(rs)
    assert inst._execute_command({'type': 'start_playback'})['error']['code'] == 'safety_refused'
    assert inst._execute_command({'type': 'get_script_info'})['status'] == 'success'
