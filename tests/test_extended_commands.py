"""Remote Script side of the extended commands (undo/redo, delete_track),
run against fake Live objects through the real _process_command entry point.
No Ableton, no network."""

import pytest

from live_fakes import FakeSong, load_script_module, make_script


@pytest.fixture(scope="module")
def script_module():
    return load_script_module()


@pytest.fixture
def song():
    return FakeSong()


@pytest.fixture
def script(script_module, song):
    return make_script(script_module, song)


def run(script, command, **params):
    return script._process_command({"type": command, "params": params})


def ok(script, command, **params):
    reply = run(script, command, **params)
    assert reply["status"] == "success", reply
    return reply["result"]


def err(script, command, **params):
    reply = run(script, command, **params)
    assert reply["status"] == "error", reply
    return reply["message"]


# ------------------------------------------------------------------ registry

def test_every_extended_command_is_advertised(script_module):
    for name in script_module.EXTENDED_COMMANDS:
        assert name in script_module.SCRIPT_CAPABILITIES


def test_every_extended_handler_exists(script_module):
    for name, (handler, _main) in script_module.EXTENDED_COMMANDS.items():
        assert callable(getattr(script_module.AbletonMCP, handler, None)), name


def test_server_expects_the_script_version(script_module):
    from MCP_Server.remote_script_install import EXPECTED_REMOTE_SCRIPT_VERSION
    assert script_module.SCRIPT_VERSION == EXPECTED_REMOTE_SCRIPT_VERSION


def test_server_marks_every_writing_command_as_modifying(script_module):
    from MCP_Server.extended_tools import MODIFYING_COMMANDS
    writers = {n for n, (_h, main) in script_module.EXTENDED_COMMANDS.items() if main}
    assert writers == set(MODIFYING_COMMANDS)


def test_writes_run_on_the_main_thread_and_reads_do_not(script, song):
    ok(script, "get_undo_state")
    assert script.scheduled == []
    song.undo_depth = 1
    ok(script, "undo")
    assert len(script.scheduled) == 1


def test_main_thread_error_comes_back_as_an_error_reply(script):
    assert "Nothing to undo" in err(script, "undo")


# ------------------------------------------------------------------ undo/redo

def test_undo_state_reports_both_directions(script, song):
    assert ok(script, "get_undo_state") == {"can_undo": False, "can_redo": False}
    song.undo_depth = 2
    assert ok(script, "get_undo_state") == {"can_undo": True, "can_redo": False}


def test_undo_then_redo(script, song):
    song.undo_depth = 1
    assert ok(script, "undo") == {"can_undo": False, "can_redo": True, "undone": True}
    assert ok(script, "redo") == {"can_undo": True, "can_redo": False, "redone": True}
    assert song.history == ["undo", "redo"]


def test_redo_with_nothing_to_redo_is_refused(script, song):
    assert "Nothing to redo" in err(script, "redo")
    assert song.history == []


# ------------------------------------------------------------------ delete_track

def test_delete_track_needs_the_matching_name(script, song):
    result = ok(script, "delete_track", track_index=1, expected_name="2-MIDI")
    assert result == {"deleted": "track", "index": 1, "name": "2-MIDI", "remaining": 1}
    assert [t.name for t in song.tracks] == ["1-Audio"]


@pytest.mark.parametrize("expected", ["1-Audio", "2-midi", "", None])
def test_delete_track_with_a_wrong_or_missing_name_deletes_nothing(script, song, expected):
    params = {"track_index": 1}
    if expected is not None:
        params["expected_name"] = expected
    assert "does not match" in err(script, "delete_track", **params)
    assert len(song.tracks) == 2 and song.history == []


def test_delete_track_out_of_range_deletes_nothing(script, song):
    assert "out of range" in err(script, "delete_track", track_index=5, expected_name="x")
    assert song.history == []


def test_delete_the_last_track_is_refused(script_module):
    song = FakeSong(track_names=("Only",))
    script = make_script(script_module, song)
    assert "at least one track" in err(script, "delete_track", track_index=0, expected_name="Only")
    assert song.history == []


def test_delete_return_track(script, song):
    result = ok(script, "delete_track", track_index=0, expected_name="A-Reverb", track_type="return")
    assert result["deleted"] == "return"
    assert [t.name for t in song.return_tracks] == ["B-Delay"]
    assert len(song.tracks) == 2


def test_master_cannot_be_deleted(script, song):
    assert "master" in err(script, "delete_track", expected_name="Main", track_type="master")
    assert song.history == []


def test_unknown_track_type_is_refused(script, song):
    assert "track_type" in err(script, "delete_track", track_index=0, expected_name="1-Audio",
                               track_type="group")
    assert song.history == []
