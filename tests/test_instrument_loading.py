"""Grep-based tests verifying instrument loading correctness and health-check version.

These tests read actual source files on disk to confirm:
- Instrument loading uses same-callback pattern (selected_track + load_item)
- Verification step exists with retry logic
- Load success reports device chain
- Ping returns Ableton version via get_major_version
- Health-check tool surfaces Ableton version
"""

import re
import pytest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_load_browser_item_same_callback(remote_script_source: str) -> None:
    """Verify selected_track and load_item occur in the same callback body."""
    # Find a function body (do_load or _load_browser_item) that contains BOTH
    # selected_track assignment AND load_item call.
    # Look for do_load inner function or the _load_browser_item method.
    match = re.search(
        r"def do_load\(.*?\).*?(?=\n    def |\n        def |\Z)",
        remote_script_source,
        re.DOTALL,
    )
    if not match:
        # Fall back to looking inside _load_browser_item body
        match = re.search(
            r"def _load_browser_item\(self.*?\).*?(?=\n    def |\nclass |\Z)",
            remote_script_source,
            re.DOTALL,
        )
    assert match, "Could not find do_load or _load_browser_item method"
    body = match.group(0)

    assert "selected_track" in body, (
        "Missing 'selected_track' in load callback -- "
        "track selection must happen in the same callback as load_item"
    )
    assert "load_item" in body, (
        "Missing 'load_item' in load callback -- "
        "load_item must happen in the same callback as selected_track"
    )


def test_verify_load_has_retry(remote_script_source: str) -> None:
    """Verify _verify_load function exists with retries_remaining parameter."""
    assert re.search(r"def _verify_load\(", remote_script_source), (
        "Missing _verify_load function -- load verification with retry must exist"
    )
    # Find _verify_load body and check for retries_remaining
    match = re.search(
        r"def _verify_load\(.*?\).*?(?=\n    def |\nclass |\Z)",
        remote_script_source,
        re.DOTALL,
    )
    assert match, "Could not extract _verify_load body"
    body = match.group(0)
    assert "retries_remaining" in body, (
        "Missing 'retries_remaining' in _verify_load -- "
        "load verification must support automatic retry"
    )


def test_load_success_reports_device_chain(remote_script_source: str) -> None:
    """Verify load success path reports device chain info."""
    match = re.search(
        r"def _verify_load\(.*?\).*?(?=\n    def |\nclass |\Z)",
        remote_script_source,
        re.DOTALL,
    )
    assert match, "Could not extract _verify_load body"
    body = match.group(0)

    # Check for device list comprehension or device name access
    assert re.search(r"d\.name\s+for\s+d\s+in", body), (
        "Missing device name list comprehension in _verify_load -- "
        "load results must report actual device names"
    )
    # Check for 'devices' key in response
    assert '"devices"' in body, (
        "Missing 'devices' key in _verify_load response -- "
        "load results must include device chain info"
    )


def test_ping_returns_ableton_version(remote_script_source: str) -> None:
    """Verify _ping returns ableton_version via get_major_version."""
    match = re.search(
        r"def _ping\(self.*?\).*?(?=\n    def |\nclass |\Z)",
        remote_script_source,
        re.DOTALL,
    )
    assert match, "Could not find _ping method"
    body = match.group(0)

    assert "ableton_version" in body, (
        "Missing 'ableton_version' key in _ping response -- "
        "ping must return the Ableton application version"
    )
    assert "get_major_version" in body, (
        "Missing 'get_major_version' call in _ping -- "
        "ping must read real Ableton version, not hardcode it"
    )


def test_get_connection_status_includes_ableton_version(server_source: str) -> None:
    """Verify get_connection_status surfaces ableton_version from ping."""
    match = re.search(
        r"def get_connection_status\(.*?\).*?(?=\n@|\ndef |\Z)",
        server_source,
        re.DOTALL,
    )
    assert match, "Could not find get_connection_status function"
    body = match.group(0)

    assert "ableton_version" in body, (
        "Missing 'ableton_version' in get_connection_status -- "
        "health-check must surface Ableton version from ping response"
    )
