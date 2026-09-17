"""What the consent notice promises must actually hold.

consent.CONSENT_NOTICE tells the user "Email addresses and file paths are
stripped first". These tests pin that promise to the three places data leaves
the machine: session snapshots, intent text, and recorded action params.
"""
import json

import pytest

from MCP_Server.dataset import snapshot as snapshot_mod
from MCP_Server.dataset.recorder import scrub_text
from MCP_Server.dataset.trajectory_decorator import _extract_params

WINDOWS_PATH = r"C:\Users\ariadne\Music\Ableton\User Library\Samples\kick.wav"
POSIX_PATH = "/Users/ariadne/Music/Samples/kick.wav"
UNC_PATH = r"\\studio-nas\shared\ariadne\stems\vocal take 3.aif"


def _leaks(payload, needle="ariadne"):
    """True if the fake username survived anywhere in the payload."""
    return needle in json.dumps(payload, default=str).lower()


# ── Snapshots ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("path", [WINDOWS_PATH, POSIX_PATH, UNC_PATH])
def test_snapshot_strips_clip_file_paths(path):
    """Every audio clip carries file_path; it embeds the OS username."""
    raw = {"tracks": [{"clip_slots": [{"clip": {"name": "kick", "file_path": path}}]}]}
    cleaned = snapshot_mod.scrub_snapshot(raw)
    assert not _leaks(cleaned)
    assert cleaned["tracks"][0]["clip_slots"][0]["clip"]["file_path"].startswith("<path:")


def test_snapshot_path_keeps_shape_not_content():
    cleaned = snapshot_mod.scrub_snapshot({"file_path": POSIX_PATH})
    # 5 segments (Users/ariadne/Music/Samples/kick.wav), .wav extension
    assert cleaned["file_path"] == "<path:5.wav>"


@pytest.mark.parametrize("filename, expected", [
    ("kick.wav", "<path:1.wav>"),
    ("KICK.AIFF", "<path:1.aiff>"),
    # Only a real extension survives; anything else is not one, so it is dropped
    # rather than carried out with the placeholder.
    ("take.na!me", "<path:1>"),
    ("ariadne's mix.v2 final", "<path:1>"),
    (".hidden", "<path:1>"),          # no stem, so no extension
    ("no-extension", "<path:1>"),
    ("stem.reallylongextension", "<path:1>"),
])
def test_snapshot_path_extension_is_an_extension_or_nothing(filename, expected):
    cleaned = snapshot_mod.scrub_snapshot({"file_path": filename})
    assert cleaned["file_path"] == expected
    assert not _leaks(cleaned, "ariadne")
    assert "!" not in cleaned["file_path"]


def test_snapshot_redacts_user_authored_names_but_keeps_live_defaults():
    raw = {"tracks": [
        {"name": "Audio Track 3"},
        {"name": "Kick"},
        {"name": "chorus for ariadne's wedding"},
    ]}
    cleaned = snapshot_mod.scrub_snapshot(raw)
    assert cleaned["tracks"][0]["name"] == "Audio Track 3"
    assert cleaned["tracks"][1]["name"] == "Kick"
    assert cleaned["tracks"][2]["name"].startswith("<name:")
    assert not _leaks(cleaned)


def test_snapshot_scrubs_paths_at_any_depth():
    raw = {"a": [{"b": {"c": [{"path": UNC_PATH}]}}]}
    assert not _leaks(snapshot_mod.scrub_snapshot(raw))


def test_snapshot_leaves_non_string_and_numeric_state_alone():
    raw = {"tempo": 128.0, "notes": [[60, 0.0, 0.25, 100]], "mute": False, "file_path": None}
    assert snapshot_mod.scrub_snapshot(raw) == raw


# ── Free text ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text", [
    "render to " + WINDOWS_PATH,
    "compare against " + POSIX_PATH,
    "send the stems to ariadne@example.com",
])
def test_scrub_text_removes_paths_and_emails(text):
    assert not _leaks(scrub_text(text))


def test_scrub_text_keeps_the_musical_content():
    cleaned = scrub_text("make the chorus hit harder, reference " + POSIX_PATH)
    assert "make the chorus hit harder" in cleaned


# ── Recorded action params ───────────────────────────────────────────────────

def test_extract_params_reduces_a_file_path_to_its_extension():
    params = _extract_params({"path": WINDOWS_PATH})
    assert not _leaks(params)
    assert params == {"file_extension": ".wav", "has_path": True}


def test_extract_params_keeps_browser_paths_which_name_only_lives_tree():
    params = _extract_params({"path": "Drums/Kits/808 Core Kit"})
    assert params["browser_path"] == "Drums/Kits/808 Core Kit"


@pytest.mark.parametrize("key", ["text", "note", "search_query"])
def test_extract_params_scrubs_free_text_fields(key):
    assert not _leaks(_extract_params({key: "like " + POSIX_PATH + " but warmer"}))


def test_extract_params_redacts_user_authored_names():
    assert not _leaks(_extract_params({"name": "ariadne demo v4"}))


def test_extract_params_keeps_indices_and_note_data():
    params = _extract_params({
        "track_index": 2,
        "clip_index": 0,
        "notes": [{"pitch": 60, "start_time": 0.0, "duration": 0.25, "velocity": 100}],
    })
    assert params["track_index"] == 2
    assert params["notes_count"] == 1
    assert params["notes"] == [[60, 0.0, 0.25, 100]]


# ── Intent text reaches the scrubber through both entry points ───────────────

@pytest.fixture
def recorder():
    """A real recorder. Rows only reach its in-memory queue: the worker checks
    dataset_enabled() before writing, and these tests never grant consent."""
    from MCP_Server.dataset.recorder import SessionRecorder

    return SessionRecorder(session_id="sess_test", customer_uuid="uuid_test")


def test_submit_intent_text_is_scrubbed(recorder):
    """submit_intent reaches set_intent directly, bypassing observe_prompt."""
    event = recorder.set_intent("bounce it next to " + WINDOWS_PATH, level=5)
    assert not _leaks(event.text)
    assert not _leaks(recorder._active_intent_text)


def test_observed_prompt_is_scrubbed(recorder):
    event = recorder.observe_prompt("open " + POSIX_PATH + " and warm it up")
    assert not _leaks(event.text)


def test_intent_of_nothing_but_a_path_records_only_its_placeholder(recorder):
    event = recorder.set_intent(POSIX_PATH)
    assert not _leaks(event.text)
    assert "<path>" in event.text


def test_empty_intent_is_refused(recorder):
    with pytest.raises(ValueError):
        recorder.set_intent("   ")


def test_recorded_action_error_is_scrubbed(recorder):
    event = recorder.record_action(
        tool="create_audio_clip",
        params={"track_index": 0},
        success=False,
        error="Error creating audio clip: no such file " + WINDOWS_PATH,
    )
    assert not _leaks(event.error)
