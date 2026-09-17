"""Regression tests for the Live-side Remote Script's TCP surface.

Each test pins a defect this change fixes:

* the socket bound every interface, exposing an unauthenticated command
  surface to the whole network,
* each recv() chunk was decoded on its own, so a multi-byte UTF-8 character
  split across a chunk boundary desynchronised the connection,
* an incomplete command grew the buffer without bound,
* get_browser_tree never recursed and never reported a folder count.

The script normally runs inside Live's interpreter, so ``_Framework`` is
stubbed and the class is instantiated without ``__init__`` (which would open a
socket). No Ableton, no network.
"""

import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
REPO_SCRIPT = REPO_ROOT / "AbletonMCP_Remote_Script" / "__init__.py"
BUNDLED_SCRIPT = (REPO_ROOT / "MCP_Server" / "bundled_ableton_remote_script"
                  / "AbletonMCP_init.py")


def _load_script_module():
    """Import the Live-side script with _Framework stubbed out."""
    framework = types.ModuleType("_Framework")
    control_surface_mod = types.ModuleType("_Framework.ControlSurface")

    class _StubControlSurface(object):
        def __init__(self, *args, **kwargs):
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
    inst.application = lambda: application
    inst.log_message = lambda *a, **k: None
    inst.show_message = lambda *a, **k: None
    return inst


# ------------------------------------------------------------------ binding

def test_socket_binds_loopback_only(script_module):
    """The command surface is unauthenticated: it must not listen publicly."""
    assert script_module.HOST == "127.0.0.1"


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

    def _process(command):
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
