"""The safety switches: categories, read-only, saved-set rules, fail-closed
parsing, the CLI, and that the connection consults them before Live."""

import json

import pytest

from MCP_Server import safety


@pytest.fixture
def cfg_path(tmp_path, monkeypatch):
    path = tmp_path / "safety.json"
    monkeypatch.setenv(safety.CONFIG_ENV, str(path))
    return path


def write(path, data):
    path.write_text(json.dumps(data) if not isinstance(data, str) else data)


def unsaved():
    return False


def saved():
    return True


def unknown():
    raise RuntimeError("no answer")


def test_categories():
    assert safety.category_of("get_session_info") is None
    assert safety.category_of("delete_track") == "delete"
    assert safety.category_of("fire_clip") == "playback"
    assert safety.category_of("set_track_mixer") == "mixer"
    assert safety.category_of("set_device_routing") == "routing"
    assert safety.category_of("duplicate_track") == "structure"
    assert safety.category_of("undo") == "undo"
    assert safety.category_of("set_track_name") == "edit"
    assert safety.category_of("some_future_write") == "edit"  # unknown writes are gated


def test_every_extended_write_has_a_known_category():
    from MCP_Server.extended_tools import MODIFYING_COMMANDS
    for c in MODIFYING_COMMANDS:
        assert safety.category_of(c) is not None, c


def test_defaults_without_a_file(cfg_path):
    safety.check("delete_track", unsaved)
    safety.check("set_track_name", saved)
    with pytest.raises(safety.SafetyRefused, match="saved set"):
        safety.check("delete_track", saved)


def test_reads_are_never_refused(cfg_path):
    write(cfg_path, {"read_only": True})
    safety.check("get_session_info", unknown)


def test_read_only_refuses_every_change(cfg_path):
    write(cfg_path, {"read_only": True})
    for c in ("set_track_name", "undo", "fire_clip"):
        with pytest.raises(safety.SafetyRefused, match="read_only"):
            safety.check(c, unsaved)


def test_category_off(cfg_path):
    write(cfg_path, {"allow": {"delete": False}})
    with pytest.raises(safety.SafetyRefused, match="'delete' is switched off"):
        safety.check("delete_device", unsaved)
    safety.check("create_scene", unsaved)


def test_deny_and_allow_commands(cfg_path):
    write(cfg_path, {"allow": {"playback": False}, "allow_commands": ["stop_playback"],
                     "deny_commands": ["set_tempo"]})
    safety.check("stop_playback", unsaved)
    with pytest.raises(safety.SafetyRefused):
        safety.check("start_playback", unsaved)
    with pytest.raises(safety.SafetyRefused, match="deny_commands"):
        safety.check("set_tempo", unsaved)


def test_saved_rule_unknown_set_fails_closed(cfg_path):
    with pytest.raises(safety.SafetyRefused, match="could not tell"):
        safety.check("delete_track", unknown)


def test_saved_rule_can_be_lifted(cfg_path):
    write(cfg_path, {"saved_set_allow": {"delete": True}})
    safety.check("delete_track", saved)


def test_saved_rule_not_consulted_when_not_needed(cfg_path):
    safety.check("set_track_name", unknown)  # edit has no saved-set rule


@pytest.mark.parametrize("bad", ["{not json", "[1, 2]", json.dumps({"allow": {"dlete": False}})])
def test_broken_config_refuses_all_changes(cfg_path, bad):
    write(cfg_path, bad)
    with pytest.raises(safety.SafetyRefused, match="broken"):
        safety.check("set_track_name", unsaved)
    safety.check("get_track_info", unsaved)


def test_changes_are_picked_up_without_restart(cfg_path):
    write(cfg_path, {"read_only": True})
    with pytest.raises(safety.SafetyRefused):
        safety.check("set_tempo", unsaved)
    write(cfg_path, {"read_only": False, "allow": {"edit": True}, "deny_commands": []})
    safety.check("set_tempo", unsaved)


def test_cli_flips_switches_and_backs_up(cfg_path, capsys):
    assert safety.main(["delete", "off"]) == 0
    assert json.loads(cfg_path.read_text())["allow"]["delete"] is False
    assert safety.main(["saved", "delete", "on"]) == 0
    assert json.loads(cfg_path.read_text())["saved_set_allow"]["delete"] is True
    assert (cfg_path.parent / "safety.json.bak").exists()
    assert safety.main(["read-only", "on"]) == 0
    out = capsys.readouterr().out
    assert "ON - every change refused" in out
    with pytest.raises(SystemExit):
        safety.main(["bogus", "on"])


def test_describe_lists_categories(cfg_path):
    d = safety.describe()
    assert d["path"] == str(cfg_path) and d["exists"] is False
    assert set(d["categories"]) == set(safety.CATEGORY_HELP)
    assert "delete_track" in d["commands"]["delete"]


def test_connection_checks_safety_before_sending(cfg_path, monkeypatch):
    import MCP_Server.server as server
    write(cfg_path, {"allow": {"delete": False}})
    conn = server.AbletonConnection(host="localhost", port=1)
    sent = []
    monkeypatch.setattr(conn, "_send_command_locked", lambda c, p=None: sent.append(c) or {})
    with pytest.raises(safety.SafetyRefused):
        conn.send_command("delete_track", {"track_index": 0})
    assert sent == []
    conn.send_command("get_session_info")
    assert sent == ["get_session_info"]


def test_connection_asks_live_whether_the_set_is_saved(cfg_path, monkeypatch):
    import MCP_Server.server as server
    conn = server.AbletonConnection(host="localhost", port=1)
    sent = []

    def fake(c, p=None):
        sent.append(c)
        return {"is_saved": True} if c == "get_set_info" else {}
    monkeypatch.setattr(conn, "_send_command_locked", fake)
    with pytest.raises(safety.SafetyRefused, match="saved set"):
        conn.send_command("delete_clip", {})
    assert sent == ["get_set_info"]


def test_get_safety_config_tool(cfg_path):
    import asyncio
    import MCP_Server.server as server
    res = asyncio.run(server.mcp.call_tool("get_safety_config", {}))
    blocks = res[0] if isinstance(res, tuple) else res
    assert json.loads(blocks[0].text)["path"] == str(cfg_path)
