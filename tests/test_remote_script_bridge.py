"""Regression tests for the Live-side Remote Script's TCP surface.

Each test pins a defect this change fixes:

* the socket bound every interface, exposing an unauthenticated command
  surface to the whole network,
* each recv() chunk was decoded on its own, so a multi-byte UTF-8 character
  split across a chunk boundary desynchronised the connection,
* an incomplete command grew the buffer without bound,
* get_browser_tree never recursed and never reported a folder count,
* Live reads and failed write scheduling ran on socket workers,
* pending writes could run after their request timed out,
* capabilities omitted supported commands and snapshots had no output meters.

The script normally runs inside Live's interpreter, so ``_Framework`` is
stubbed and the class is instantiated without ``__init__`` (which would open a
socket). No Ableton, no network.
"""

import importlib.util
import json
import ast
import inspect
import socket
import threading
import textwrap
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
REPO_SCRIPT = REPO_ROOT / "AbletonMCP_Remote_Script" / "__init__.py"
BUNDLED_SCRIPT = (REPO_ROOT / "MCP_Server" / "bundled_ableton_remote_script"
                  / "AbletonMCP_init.py")


def _load_script_module(fresh=False):
    """Import the Live-side script with _Framework stubbed out.

    Each call re-executes the module, so ``fresh`` is only a readability hint
    at call sites that depend on module-level state being re-evaluated (the
    ABLETON_MCP_HOST lookup).
    """
    framework = types.ModuleType("_Framework")
    control_surface_mod = types.ModuleType("_Framework.ControlSurface")

    class _StubControlSurface(object):
        def __init__(self, *args, **kwargs):
            pass

        def update_display(self):
            pass

        def disconnect(self):
            pass

        def log_message(self, *args, **kwargs):
            pass

        def show_message(self, *args, **kwargs):
            pass

    control_surface_mod.ControlSurface = _StubControlSurface
    framework.ControlSurface = control_surface_mod
    sys.modules.setdefault("_Framework", framework)
    sys.modules.setdefault("_Framework.ControlSurface", control_surface_mod)

    spec = importlib.util.spec_from_file_location(
        "ableton_mcp_remote_script_under_test", BUNDLED_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def script_module():
    return _load_script_module()


def make_instance(script_module, application=None):
    inst = script_module.AbletonMCP.__new__(script_module.AbletonMCP)
    inst._initialize_command_dispatch()
    inst.application = lambda: application
    inst.log_message = lambda *a, **k: None
    inst.show_message = lambda *a, **k: None
    return inst


# ------------------------------------------------------------------ binding

def test_socket_binds_loopback_by_default(script_module):
    """The command surface is unauthenticated: it must not listen publicly
    unless the user opts in via ABLETON_MCP_HOST."""
    assert script_module.HOST == "127.0.0.1"


def test_bind_host_is_overridable_for_remote_setups(monkeypatch):
    """Running Live and the MCP server on separate machines stays possible,
    but only as a deliberate choice."""
    monkeypatch.setenv("ABLETON_MCP_HOST", "0.0.0.0")
    assert _load_script_module(fresh=True).HOST == "0.0.0.0"


def test_repo_and_bundled_copies_are_identical():
    """The installer ships the bundled copy; drift would install stale code."""
    assert REPO_SCRIPT.read_bytes() == BUNDLED_SCRIPT.read_bytes()


# ------------------------------------------------------------------ framing

class FakeClient(object):
    """Hands out prepared chunks, then EOF. Records what was written back."""

    def __init__(self, chunks):
        self._chunks = list(chunks)
        self.sent = []
        self.closed = False

    def settimeout(self, _timeout):
        pass

    def recv(self, _size):
        return self._chunks.pop(0) if self._chunks else b""

    def sendall(self, data):
        self.sent.append(data)

    def close(self):
        self.closed = True


def _serve(script_module, chunks):
    """Run one client session and decode whatever it wrote back."""
    inst = make_instance(script_module)
    inst.running = True
    received = []

    def _process(command, client=None):
        received.append(command)
        return {"status": "success", "result": {"echo": command.get("type")}}

    inst._process_command = _process
    client = FakeClient(chunks)
    inst._handle_client(client)
    replies = [json.loads(frame.decode("utf-8")) for frame in client.sent]
    return received, replies


def test_command_split_mid_utf8_character_still_parses(script_module):
    """Regression: decoding each chunk alone raised on the split, dropped the
    chunk, and wrote an error frame into a stream still awaiting the real
    response — leaving request and response permanently out of step.

    ensure_ascii=False is what puts raw multi-byte on the wire.
    """
    payload = json.dumps(
        {"type": "set_clip_name", "params": {"name": "café été"}},
        ensure_ascii=False,
    ).encode("utf-8")
    split = payload.index(b"\xc3") + 1  # between the two bytes of 'é'
    assert payload[:split].endswith(b"\xc3")

    received, replies = _serve(script_module, [payload[:split], payload[split:]])

    assert len(received) == 1
    assert received[0]["params"]["name"] == "café été"
    assert replies == [{"status": "success", "result": {"echo": "set_clip_name"}}]


def test_command_split_across_many_chunks_parses_once(script_module):
    payload = json.dumps({"type": "get_session_info", "params": {}}).encode("utf-8")
    chunks = [payload[i:i + 3] for i in range(0, len(payload), 3)]

    received, replies = _serve(script_module, chunks)

    assert len(received) == 1
    assert len(replies) == 1


def test_back_to_back_commands_each_get_one_reply(script_module):
    first = json.dumps({"type": "start_playback", "params": {}}).encode("utf-8")
    second = json.dumps({"type": "stop_playback", "params": {}}).encode("utf-8")

    received, replies = _serve(script_module, [first, second])

    assert [c["type"] for c in received] == ["start_playback", "stop_playback"]
    assert len(replies) == 2


def test_oversized_request_is_refused_instead_of_buffered_forever(
        script_module, monkeypatch):
    """A client that never completes a command must not grow the buffer."""
    monkeypatch.setattr(script_module, "MAX_REQUEST_BYTES", 1024)
    junk = b'{"type": "' + b"x" * 4096

    received, replies = _serve(script_module, [junk, junk])

    assert received == []
    assert len(replies) == 1
    assert replies[0]["status"] == "error"


# ------------------------------------------------------------- browser tree

class FakeBrowserItem(object):
    def __init__(self, name, children=(), loadable=False, uri=None):
        self.name = name
        self.children = list(children)
        self.is_device = False
        self.is_loadable = loadable
        self.uri = uri


class FakeBrowser(object):
    def __init__(self, instruments):
        self.instruments = instruments


class FakeApplication(object):
    def __init__(self, browser=None):
        self.browser = browser


def test_browser_tree_returns_children_and_a_truthful_folder_count(script_module):
    """Regression: process_item never recursed (children was always []) and
    total_folders was never returned, so the server's header always read
    'showing 0 folders'."""
    kits = FakeBrowserItem("Kits", [FakeBrowserItem("808 Core Kit", loadable=True)])
    browser = FakeBrowser(FakeBrowserItem("Instruments", [kits]))
    inst = make_instance(script_module, application=FakeApplication(browser=browser))

    tree = inst.get_browser_tree("instruments")

    assert tree["total_folders"] >= 2  # Instruments and Kits both have children
    category = tree["categories"][0]
    assert [child["name"] for child in category["children"]] == ["Kits"]
    # Depth is capped one level below the category, so Kits reports more.
    assert category["children"][0]["has_more"] is True


def test_browser_tree_caps_a_huge_folder_and_flags_it(script_module):
    many = [FakeBrowserItem("Preset %d" % i, loadable=True) for i in range(200)]
    browser = FakeBrowser(FakeBrowserItem("Instruments", many))
    inst = make_instance(script_module, application=FakeApplication(browser=browser))

    category = inst.get_browser_tree("instruments")["categories"][0]

    assert len(category["children"]) == 64
    assert category["has_more"] is True


# --------------------------------------------------------- main-thread handoff

def start_request(inst, command, client=None):
    """Observe queue admission without depending on thread scheduling sleeps."""
    admitted = threading.Event()
    put = inst._command_queue.put_nowait

    def observe_put(request):
        put(request)
        admitted.set()

    inst._command_queue.put_nowait = observe_put
    replies = []
    worker = threading.Thread(target=lambda: replies.append(
        inst._process_command(command, client=client)))
    worker.start()
    assert admitted.wait(1.0)
    inst._command_queue.put_nowait = put
    return worker, replies


def finish_request(worker, replies):
    worker.join(1.0)
    assert not worker.is_alive()
    assert len(replies) == 1
    return replies[0]


@pytest.mark.parametrize("command,handler,params,expected", [
    ("get_session_info", "_get_session_info", {}, ()),
    ("get_track_info", "_get_track_info", {"track_index": 3}, (3,)),
    ("get_browser_items_at_path", "get_browser_items_at_path", {"path": "Instruments"}, ("Instruments",)),
    ("start_playback", "_start_playback", {}, ()),
    ("set_current_song_time", "_set_current_song_time", {"time": 64.0}, (64.0,)),
    ("set_device_parameter", "_set_device_parameter", {
        "track_index": 1, "device_index": 2, "parameter_index": 3, "value": 0.5,
    }, (1, 2, 3, 0.5)),
])
def test_reads_and_writes_run_only_in_live_callback(
        script_module, command, handler, params, expected):
    inst = make_instance(script_module)
    calls = []

    def execute(*args):
        calls.append((threading.current_thread().ident, args))
        return {"verified": command}

    setattr(inst, handler, execute)
    # The old fallback path must never be reached, including if scheduling fails.
    def reject_scheduling(*args):
        raise AssertionError("Socket workers cannot schedule Live work")

    inst.schedule_message = reject_scheduling
    worker, replies = start_request(inst, {"type": command, "params": params})
    assert calls == []
    inst.update_display()
    response = finish_request(worker, replies)
    assert calls == [(threading.current_thread().ident, expected)]
    assert response == {"status": "success", "result": {"verified": command}}


def test_main_thread_cannot_block_waiting_for_itself(script_module):
    inst = make_instance(script_module)
    response = inst._process_command({"type": "start_playback"})
    assert response["status"] == "error"
    assert inst._command_queue.empty()


def test_timeout_cancels_pending_mutation(script_module, monkeypatch):
    monkeypatch.setattr(script_module, "COMMAND_TIMEOUT", 0.02)
    inst = make_instance(script_module)
    calls = []
    inst._start_playback = lambda: calls.append("played")
    worker, replies = start_request(inst, {"type": "start_playback"})
    response = finish_request(worker, replies)
    assert "command not executed" in response["message"]
    inst.update_display()
    assert calls == []


def test_expired_request_is_refused_before_worker_observes_timeout(script_module, monkeypatch):
    inst = make_instance(script_module)
    calls = []
    inst._start_playback = lambda: calls.append("played")
    request = script_module._CommandRequest({"type": "start_playback"}, 10.0)
    inst._command_queue.put_nowait(request)
    monkeypatch.setattr(script_module, "_command_clock", lambda: 10.0)
    inst.update_display()
    assert request.completed.is_set()
    assert "command not executed" in request.response["message"]
    assert calls == []


def test_timeout_during_execution_reports_uncertain_outcome(script_module, monkeypatch):
    monkeypatch.setattr(script_module, "COMMAND_TIMEOUT", 0.02)
    inst = make_instance(script_module)
    calls = []
    worker, replies = start_request(inst, {"type": "start_playback"})

    def execute():
        calls.append("played")
        # A running Live operation cannot be interrupted. Let its worker time out.
        worker.join(1.0)
        return {"is_playing": True}

    inst._start_playback = execute
    inst.update_display()
    response = finish_request(worker, replies)
    assert "outcome unknown" in response["message"]
    assert "do not automatically retry" in response["message"]
    inst.update_display()
    assert calls == ["played"]


def test_disconnected_client_cancels_pending_mutation(script_module):
    inst = make_instance(script_module)
    calls = []
    inst._start_playback = lambda: calls.append("played")
    client, peer = socket.socketpair()
    try:
        worker, replies = start_request(inst, {"type": "start_playback"}, client)
        peer.close()
        response = finish_request(worker, replies)
        assert "Client disconnected; command not executed" == response["message"]
        inst.update_display()
        assert calls == []
    finally:
        client.close()
        peer.close()


def test_client_eof_before_drain_cancels_even_while_worker_is_sleeping(script_module):
    inst = make_instance(script_module)
    calls = []
    inst._start_playback = lambda: calls.append("played")
    checked = threading.Event()
    release = threading.Event()
    check_connection = inst._client_disconnected

    def pause_worker_after_check(client):
        disconnected = check_connection(client)
        if threading.current_thread().ident != inst._command_thread:
            checked.set()
            assert release.wait(1.0)
        return disconnected

    inst._client_disconnected = pause_worker_after_check
    client, peer = socket.socketpair()
    try:
        worker, replies = start_request(inst, {"type": "start_playback"}, client)
        assert checked.wait(1.0)
        peer.close()
        assert check_connection(client)
        # Drain before the worker can observe EOF or mark cancellation.
        inst.update_display()
        assert calls == []
        release.set()
        assert finish_request(worker, replies)["message"] == "Client disconnected; command not executed"
    finally:
        release.set()
        client.close()
        peer.close()


def test_shutdown_wakes_pending_requests_and_rejects_new_commands(script_module):
    inst = make_instance(script_module)
    inst.running = True
    inst.server = None
    inst.server_thread = None
    inst.client_threads = []
    inst._teardown_passive_listeners = lambda: None
    calls = []
    inst._start_playback = lambda: calls.append("played")
    worker, replies = start_request(inst, {"type": "start_playback"})
    inst.disconnect()
    assert "command not executed" in finish_request(worker, replies)["message"]
    inst.update_display()
    assert calls == []
    result = []
    worker = threading.Thread(target=lambda: result.append(inst._process_command({"type": "start_playback"})))
    worker.start()
    worker.join(1.0)
    assert result == [{"status": "error", "message": "Remote Script disconnected"}]


def test_shutdown_unblocks_idle_socket_clients(script_module):
    inst = make_instance(script_module)
    inst.running = True
    client, peer = socket.socketpair()
    inst._clients.add(client)
    worker = threading.Thread(target=inst._handle_client, args=(client,))
    worker.start()
    inst.running = False
    inst._shutdown_commands()
    worker.join(1.0)
    assert not worker.is_alive()
    assert inst._clients == set()
    peer.close()


def test_queue_rejects_excess_work_without_execution(script_module, monkeypatch):
    monkeypatch.setattr(script_module, "MAX_PENDING_COMMANDS", 1)
    inst = make_instance(script_module)
    inst._command_queue.put_nowait(script_module._CommandRequest({}, 1.0))
    replies = []
    worker = threading.Thread(target=lambda: replies.append(inst._process_command({"type": "start_playback"})))
    worker.start()
    response = finish_request(worker, replies)
    assert "queue is full; command not executed" in response["message"]


def test_callback_limits_work_and_preserves_order(script_module, monkeypatch):
    monkeypatch.setattr(script_module, "MAX_COMMANDS_PER_TICK", 2)
    inst = make_instance(script_module)
    calls = []
    inst._set_current_song_time = lambda value: calls.append(value)
    for value in range(3):
        request = script_module._CommandRequest({"type": "set_current_song_time", "params": {"time": value}}, float("inf"))
        inst._command_queue.put_nowait(request)
    inst.update_display()
    assert calls == [0, 1]
    inst.update_display()
    assert calls == [0, 1, 2]


def test_worker_cannot_drain_command_queue(script_module):
    inst = make_instance(script_module)
    errors = []

    def drain():
        try:
            inst._drain_commands()
        except RuntimeError as error:
            errors.append(str(error))

    worker = threading.Thread(target=drain)
    worker.start()
    worker.join(1.0)
    assert errors == ["Command queue must be drained on Live's main thread"]


def test_handshake_advertises_every_supported_command(script_module):
    inst = make_instance(script_module)
    tree = ast.parse(textwrap.dedent(inspect.getsource(inst._execute_command)))
    supported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare) and isinstance(node.left, ast.Name) and node.left.id == "command_type":
            supported.add(node.comparators[0].value)
    info = inst._get_script_info()
    assert set(info["capabilities"]) == supported
    assert {"start_playback", "stop_playback", "set_current_song_time", "get_browser_tree"} <= supported
    assert info["script_version"] == "1.7.2"
    assert info["protocol_version"] == 1


# ---------------------------------------------------------------- output meters

def meter_track(**meters):
    """Minimal Track fixture uses the documented Live Track property names."""
    return types.SimpleNamespace(
        name="Instrument", has_audio_input=False, has_midi_input=True,
        mute=False, solo=False, can_be_armed=False,
        mixer_device=types.SimpleNamespace(
            volume=types.SimpleNamespace(value=0.75),
            panning=types.SimpleNamespace(value=0.0), sends=[]),
        clip_slots=[], devices=[], arrangement_clips=[], **meters)


def meter_song(track):
    return types.SimpleNamespace(tempo=120.0, signature_numerator=4,
        signature_denominator=4, tracks=[track], return_tracks=[track],
        master_track=track, scenes=[], cue_points=[])


def test_actual_meters_are_in_track_session_and_all_snapshot_buses(script_module):
    inst = make_instance(script_module)
    expected = {"output_meter_left": 0.25, "output_meter_right": 0.5, "output_meter_level": 0.75}
    inst._song = meter_song(meter_track(**expected))
    snapshot = inst._get_session_snapshot(include_notes=False, include_params=False)
    results = [inst._get_track_info(0), inst._get_session_info()["master_track"],
               snapshot["tracks"][0], snapshot["return_tracks"][0], snapshot["master_track"]]
    for result in results:
        assert {key: result[key] for key in expected} == expected
        json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), -0.1, 1.1, None, "unavailable"])
def test_invalid_meters_are_null_and_valid_meter_is_preserved(script_module, value):
    inst = make_instance(script_module)
    meters = inst._output_meters(meter_track(output_meter_left=value, output_meter_level=0.0))
    assert meters == {"output_meter_left": None, "output_meter_right": None, "output_meter_level": 0.0}
    json.dumps(meters, allow_nan=False)


def test_unsupported_meter_property_does_not_break_snapshot(script_module):
    class UnsupportedTrack(types.SimpleNamespace):
        @property
        def output_meter_left(self):
            raise RuntimeError("Only supported for audio output")

    track = UnsupportedTrack(**vars(meter_track()))
    inst = make_instance(script_module)
    inst._song = meter_song(track)
    snapshot = inst._get_session_snapshot()
    for result in (snapshot["tracks"][0], snapshot["master_track"]):
        assert result["output_meter_left"] is None
        assert result["output_meter_right"] is None
        assert result["output_meter_level"] is None
