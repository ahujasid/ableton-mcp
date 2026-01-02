# Arrangement View Features Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add comprehensive arrangement view support enabling playhead control, cue point navigation, and arrangement clip operations.

**Architecture:** Commands flow from MCP Server tools → TCP socket → Remote Script handlers → Ableton LOM. All state-modifying operations use `schedule_message(0, callback)` for main thread safety. Times are in beats.

**Tech Stack:** Python (MCP Server with FastMCP + anyio), Python 2/3 compatible Remote Script, pytest for testing.

---

## Phase 1: Navigation & Playback

### Task 1: Add `get_arrangement_info` to Remote Script

**Files:**
- Modify: `AbletonMCP_Remote_Script/__init__.py:232-246` (add to read commands routing)
- Modify: `AbletonMCP_Remote_Script/__init__.py:940` (add handler after `_get_scene_info`)

**Step 1: Add command routing**

In `_process_command`, add to the read commands section (around line 239):

```python
elif command_type == "get_arrangement_info":
    response["result"] = self._get_arrangement_info()
```

**Step 2: Add handler method**

After `_get_scene_info` method, add:

```python
def _get_arrangement_info(self):
    """Get arrangement view information"""
    try:
        result = {
            "current_song_time": self._song.current_song_time,
            "loop_start": self._song.loop_start,
            "loop_length": self._song.loop_length,
            "loop_enabled": self._song.loop,
            "is_playing": self._song.is_playing,
            "record_mode": self._song.record_mode,
            "arrangement_overdub": self._song.arrangement_overdub,
            "signature_numerator": self._song.signature_numerator,
            "signature_denominator": self._song.signature_denominator
        }
        return result
    except Exception as e:
        self.log_message("Error getting arrangement info: " + str(e))
        raise
```

**Step 3: Commit**

```bash
git add AbletonMCP_Remote_Script/__init__.py
git commit -m "feat(remote): add get_arrangement_info command"
```

---

### Task 2: Add `get_arrangement_info` MCP tool + test

**Files:**
- Modify: `MCP_Server/server.py:813` (add after `get_scene_info` tool)
- Create: `tests/test_arrangement_navigation.py`

**Step 1: Write the failing test**

Create `tests/test_arrangement_navigation.py`:

```python
"""Tests for arrangement view navigation features."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_ableton_connection():
    """Create a mock Ableton connection."""
    with patch("MCP_Server.server.get_ableton_connection") as mock_get_conn:
        mock_conn = MagicMock()
        mock_conn.send_command_async = AsyncMock()
        mock_get_conn.return_value = mock_conn
        yield mock_conn


class TestGetArrangementInfo:
    """Tests for get_arrangement_info tool."""

    async def test_returns_arrangement_state(self, mock_ableton_connection):
        """Test that get_arrangement_info returns arrangement state."""
        from MCP_Server.server import get_arrangement_info

        mock_ableton_connection.send_command_async.return_value = {
            "current_song_time": 32.0,
            "loop_start": 16.0,
            "loop_length": 16.0,
            "loop_enabled": True,
            "is_playing": False,
            "record_mode": False,
            "arrangement_overdub": False,
            "signature_numerator": 4,
            "signature_denominator": 4,
        }

        result = await get_arrangement_info(MagicMock())

        mock_ableton_connection.send_command_async.assert_called_once_with(
            "get_arrangement_info"
        )
        parsed = json.loads(result)
        assert parsed["current_song_time"] == 32.0
        assert parsed["loop_enabled"] is True

    async def test_handles_error(self, mock_ableton_connection):
        """Test error handling."""
        from MCP_Server.server import get_arrangement_info

        mock_ableton_connection.send_command_async.side_effect = Exception(
            "Connection lost"
        )

        result = await get_arrangement_info(MagicMock())

        assert "Error" in result
```

**Step 2: Run test to verify it fails**

```bash
cd /Users/jdelsman/Projects/ableton-mcp/.worktrees/arrangement-view
uv run pytest tests/test_arrangement_navigation.py -v
```

Expected: FAIL with "cannot import name 'get_arrangement_info'"

**Step 3: Add MCP tool**

In `MCP_Server/server.py`, after `get_scene_info` tool (around line 813):

```python
@mcp.tool()
async def get_arrangement_info(ctx: Context) -> str:
    """Get arrangement view information including playhead position, loop settings, and transport state."""
    try:
        ableton = get_ableton_connection()
        result = await ableton.send_command_async("get_arrangement_info")
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting arrangement info: {str(e)}")
        return f"Error getting arrangement info: {str(e)}"
```

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_arrangement_navigation.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add MCP_Server/server.py tests/test_arrangement_navigation.py
git commit -m "feat: add get_arrangement_info MCP tool with tests"
```

---

### Task 3: Add `set_song_time` to Remote Script

**Files:**
- Modify: `AbletonMCP_Remote_Script/__init__.py:247-254` (add to modifying commands list)
- Modify: `AbletonMCP_Remote_Script/__init__.py:259` (add handler call in main_thread_task)

**Step 1: Add to modifying commands list**

In `_process_command`, add `"set_song_time"` to the list around line 247:

```python
elif command_type in ["create_midi_track", "create_audio_track", "set_track_name",
                     "create_clip", "add_notes_to_clip", "set_clip_name",
                     "set_tempo", "fire_clip", "stop_clip",
                     "start_playback", "stop_playback", "load_browser_item",
                     "undo", "redo", "delete_track", "delete_clip",
                     "set_metronome", "fire_scene",
                     "set_track_mute", "set_track_solo", "set_track_arm",
                     "set_track_volume", "set_track_panning",
                     "set_song_time"]:
```

**Step 2: Add handler call in main_thread_task**

Inside `main_thread_task` function, add after the track panning handler:

```python
elif command_type == "set_song_time":
    time = params.get("time", 0.0)
    result = self._set_song_time(time)
```

**Step 3: Add handler method**

After `_get_arrangement_info` method:

```python
def _set_song_time(self, time):
    """Set the song playhead position"""
    try:
        self._song.current_song_time = max(0.0, float(time))
        return {
            "current_song_time": self._song.current_song_time
        }
    except Exception as e:
        self.log_message("Error setting song time: " + str(e))
        raise
```

**Step 4: Commit**

```bash
git add AbletonMCP_Remote_Script/__init__.py
git commit -m "feat(remote): add set_song_time command"
```

---

### Task 4: Add `set_song_time` MCP tool + test

**Files:**
- Modify: `MCP_Server/server.py:925` (after `get_arrangement_info` tool)
- Modify: `MCP_Server/server.py:112-137` (add to modifying commands list)
- Modify: `tests/test_arrangement_navigation.py`

**Step 1: Write the failing test**

Add to `tests/test_arrangement_navigation.py`:

```python
class TestSetSongTime:
    """Tests for set_song_time tool."""

    async def test_sets_playhead_position(self, mock_ableton_connection):
        """Test that set_song_time moves playhead."""
        from MCP_Server.server import set_song_time

        mock_ableton_connection.send_command_async.return_value = {
            "current_song_time": 64.0
        }

        result = await set_song_time(MagicMock(), time=64.0)

        mock_ableton_connection.send_command_async.assert_called_once_with(
            "set_song_time", {"time": 64.0}
        )
        assert "64.0" in result

    async def test_handles_error(self, mock_ableton_connection):
        """Test error handling."""
        from MCP_Server.server import set_song_time

        mock_ableton_connection.send_command_async.side_effect = Exception(
            "Invalid time"
        )

        result = await set_song_time(MagicMock(), time=-5.0)

        assert "Error" in result
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_arrangement_navigation.py::TestSetSongTime -v
```

Expected: FAIL with "cannot import name 'set_song_time'"

**Step 3: Add to modifying commands list**

In `MCP_Server/server.py`, add `"set_song_time"` to `is_modifying_command` list (around line 137):

```python
"set_track_panning",
"set_song_time",
```

**Step 4: Add MCP tool**

After `get_arrangement_info` tool:

```python
@mcp.tool()
async def set_song_time(ctx: Context, time: float) -> str:
    """
    Set the song playhead position.

    Parameters:
    - time: Position in beats (e.g., 32.0 = bar 9 in 4/4 time)
    """
    try:
        ableton = get_ableton_connection()
        result = await ableton.send_command_async("set_song_time", {"time": time})
        return f"Moved playhead to beat {result.get('current_song_time', time)}"
    except Exception as e:
        logger.error(f"Error setting song time: {str(e)}")
        return f"Error setting song time: {str(e)}"
```

**Step 5: Run test to verify it passes**

```bash
uv run pytest tests/test_arrangement_navigation.py::TestSetSongTime -v
```

Expected: PASS

**Step 6: Commit**

```bash
git add MCP_Server/server.py tests/test_arrangement_navigation.py
git commit -m "feat: add set_song_time MCP tool with tests"
```

---

### Task 5: Add `set_loop_region` to Remote Script

**Files:**
- Modify: `AbletonMCP_Remote_Script/__init__.py` (add to modifying commands + handler)

**Step 1: Add to modifying commands list**

Add `"set_loop_region"` to the command list.

**Step 2: Add handler call**

```python
elif command_type == "set_loop_region":
    start = params.get("start", 0.0)
    length = params.get("length", 4.0)
    result = self._set_loop_region(start, length)
```

**Step 3: Add handler method**

```python
def _set_loop_region(self, start, length):
    """Set the arrangement loop region"""
    try:
        self._song.loop_start = max(0.0, float(start))
        self._song.loop_length = max(0.0, float(length))
        return {
            "loop_start": self._song.loop_start,
            "loop_length": self._song.loop_length
        }
    except Exception as e:
        self.log_message("Error setting loop region: " + str(e))
        raise
```

**Step 4: Commit**

```bash
git add AbletonMCP_Remote_Script/__init__.py
git commit -m "feat(remote): add set_loop_region command"
```

---

### Task 6: Add `set_loop_region` MCP tool + test

**Files:**
- Modify: `MCP_Server/server.py`
- Modify: `tests/test_arrangement_navigation.py`

**Step 1: Write the failing test**

Add to `tests/test_arrangement_navigation.py`:

```python
class TestSetLoopRegion:
    """Tests for set_loop_region tool."""

    async def test_sets_loop_region(self, mock_ableton_connection):
        """Test that set_loop_region sets loop start and length."""
        from MCP_Server.server import set_loop_region

        mock_ableton_connection.send_command_async.return_value = {
            "loop_start": 16.0,
            "loop_length": 16.0,
        }

        result = await set_loop_region(MagicMock(), start=16.0, length=16.0)

        mock_ableton_connection.send_command_async.assert_called_once_with(
            "set_loop_region", {"start": 16.0, "length": 16.0}
        )
        assert "16.0" in result
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_arrangement_navigation.py::TestSetLoopRegion -v
```

**Step 3: Add MCP tool**

```python
@mcp.tool()
async def set_loop_region(ctx: Context, start: float, length: float) -> str:
    """
    Set the arrangement loop region.

    Parameters:
    - start: Loop start position in beats
    - length: Loop length in beats
    """
    try:
        ableton = get_ableton_connection()
        result = await ableton.send_command_async(
            "set_loop_region", {"start": start, "length": length}
        )
        return f"Set loop region: start={result.get('loop_start')}, length={result.get('loop_length')}"
    except Exception as e:
        logger.error(f"Error setting loop region: {str(e)}")
        return f"Error setting loop region: {str(e)}"
```

**Step 4: Run tests and commit**

```bash
uv run pytest tests/test_arrangement_navigation.py::TestSetLoopRegion -v
git add MCP_Server/server.py tests/test_arrangement_navigation.py
git commit -m "feat: add set_loop_region MCP tool with tests"
```

---

### Task 7: Add `set_loop_enabled` to Remote Script

**Files:**
- Modify: `AbletonMCP_Remote_Script/__init__.py`

**Step 1: Add command routing and handler**

```python
elif command_type == "set_loop_enabled":
    enabled = params.get("enabled", True)
    result = self._set_loop_enabled(enabled)
```

```python
def _set_loop_enabled(self, enabled):
    """Enable or disable the arrangement loop"""
    try:
        self._song.loop = bool(enabled)
        return {
            "loop_enabled": self._song.loop
        }
    except Exception as e:
        self.log_message("Error setting loop enabled: " + str(e))
        raise
```

**Step 2: Commit**

```bash
git add AbletonMCP_Remote_Script/__init__.py
git commit -m "feat(remote): add set_loop_enabled command"
```

---

### Task 8: Add `set_loop_enabled` MCP tool + test

**Files:**
- Modify: `MCP_Server/server.py`
- Modify: `tests/test_arrangement_navigation.py`

**Step 1: Write the failing test**

```python
class TestSetLoopEnabled:
    """Tests for set_loop_enabled tool."""

    async def test_enables_loop(self, mock_ableton_connection):
        """Test that set_loop_enabled enables/disables loop."""
        from MCP_Server.server import set_loop_enabled

        mock_ableton_connection.send_command_async.return_value = {
            "loop_enabled": True
        }

        result = await set_loop_enabled(MagicMock(), enabled=True)

        mock_ableton_connection.send_command_async.assert_called_once_with(
            "set_loop_enabled", {"enabled": True}
        )
        assert "enabled" in result.lower()
```

**Step 2: Add MCP tool**

```python
@mcp.tool()
async def set_loop_enabled(ctx: Context, enabled: bool) -> str:
    """
    Enable or disable the arrangement loop.

    Parameters:
    - enabled: True to enable loop, False to disable
    """
    try:
        ableton = get_ableton_connection()
        result = await ableton.send_command_async(
            "set_loop_enabled", {"enabled": enabled}
        )
        state = "enabled" if result.get("loop_enabled") else "disabled"
        return f"Arrangement loop {state}"
    except Exception as e:
        logger.error(f"Error setting loop enabled: {str(e)}")
        return f"Error setting loop enabled: {str(e)}"
```

**Step 3: Run tests and commit**

```bash
uv run pytest tests/test_arrangement_navigation.py::TestSetLoopEnabled -v
git add MCP_Server/server.py tests/test_arrangement_navigation.py
git commit -m "feat: add set_loop_enabled MCP tool with tests"
```

---

### Task 9: Add `continue_playing` to Remote Script

**Files:**
- Modify: `AbletonMCP_Remote_Script/__init__.py`

**Step 1: Add command routing and handler**

```python
elif command_type == "continue_playing":
    result = self._continue_playing()
```

```python
def _continue_playing(self):
    """Continue playing from current position"""
    try:
        self._song.continue_playing()
        return {
            "is_playing": self._song.is_playing,
            "current_song_time": self._song.current_song_time
        }
    except Exception as e:
        self.log_message("Error continuing playback: " + str(e))
        raise
```

**Step 2: Commit**

```bash
git add AbletonMCP_Remote_Script/__init__.py
git commit -m "feat(remote): add continue_playing command"
```

---

### Task 10: Add `continue_playing` MCP tool + test

**Files:**
- Modify: `MCP_Server/server.py`
- Modify: `tests/test_arrangement_navigation.py`

**Step 1: Write the failing test**

```python
class TestContinuePlaying:
    """Tests for continue_playing tool."""

    async def test_continues_playback(self, mock_ableton_connection):
        """Test that continue_playing resumes from current position."""
        from MCP_Server.server import continue_playing

        mock_ableton_connection.send_command_async.return_value = {
            "is_playing": True,
            "current_song_time": 32.0,
        }

        result = await continue_playing(MagicMock())

        mock_ableton_connection.send_command_async.assert_called_once_with(
            "continue_playing"
        )
        assert "32.0" in result or "playing" in result.lower()
```

**Step 2: Add MCP tool**

```python
@mcp.tool()
async def continue_playing(ctx: Context) -> str:
    """Continue playing from the current playhead position (no quantization)."""
    try:
        ableton = get_ableton_connection()
        result = await ableton.send_command_async("continue_playing")
        return f"Continuing playback from beat {result.get('current_song_time', 0)}"
    except Exception as e:
        logger.error(f"Error continuing playback: {str(e)}")
        return f"Error continuing playback: {str(e)}"
```

**Step 3: Run tests and commit**

```bash
uv run pytest tests/test_arrangement_navigation.py::TestContinuePlaying -v
git add MCP_Server/server.py tests/test_arrangement_navigation.py
git commit -m "feat: add continue_playing MCP tool with tests"
```

---

### Task 11: Add `jump_by_bars` to Remote Script

**Files:**
- Modify: `AbletonMCP_Remote_Script/__init__.py`

**Step 1: Add command routing and handler**

```python
elif command_type == "jump_by_bars":
    bars = params.get("bars", 1)
    result = self._jump_by_bars(bars)
```

```python
def _jump_by_bars(self, bars):
    """Jump playhead forward or backward by N bars"""
    try:
        beats_per_bar = self._song.signature_numerator
        jump_beats = bars * beats_per_bar
        new_time = max(0.0, self._song.current_song_time + jump_beats)
        self._song.current_song_time = new_time
        return {
            "current_song_time": self._song.current_song_time,
            "bars_jumped": bars
        }
    except Exception as e:
        self.log_message("Error jumping by bars: " + str(e))
        raise
```

**Step 2: Commit**

```bash
git add AbletonMCP_Remote_Script/__init__.py
git commit -m "feat(remote): add jump_by_bars command"
```

---

### Task 12: Add `jump_by_bars` MCP tool + test

**Files:**
- Modify: `MCP_Server/server.py`
- Modify: `tests/test_arrangement_navigation.py`

**Step 1: Write the failing test**

```python
class TestJumpByBars:
    """Tests for jump_by_bars tool."""

    async def test_jumps_forward(self, mock_ableton_connection):
        """Test that jump_by_bars moves playhead by bars."""
        from MCP_Server.server import jump_by_bars

        mock_ableton_connection.send_command_async.return_value = {
            "current_song_time": 48.0,
            "bars_jumped": 4,
        }

        result = await jump_by_bars(MagicMock(), bars=4)

        mock_ableton_connection.send_command_async.assert_called_once_with(
            "jump_by_bars", {"bars": 4}
        )
        assert "4" in result

    async def test_jumps_backward(self, mock_ableton_connection):
        """Test that negative bars jumps backward."""
        from MCP_Server.server import jump_by_bars

        mock_ableton_connection.send_command_async.return_value = {
            "current_song_time": 16.0,
            "bars_jumped": -4,
        }

        result = await jump_by_bars(MagicMock(), bars=-4)

        assert "-4" in result or "backward" in result.lower()
```

**Step 2: Add MCP tool**

```python
@mcp.tool()
async def jump_by_bars(ctx: Context, bars: int) -> str:
    """
    Jump the playhead forward or backward by a number of bars.

    Parameters:
    - bars: Number of bars to jump (positive = forward, negative = backward)
    """
    try:
        ableton = get_ableton_connection()
        result = await ableton.send_command_async("jump_by_bars", {"bars": bars})
        direction = "forward" if bars > 0 else "backward"
        return f"Jumped {abs(bars)} bars {direction} to beat {result.get('current_song_time', 0)}"
    except Exception as e:
        logger.error(f"Error jumping by bars: {str(e)}")
        return f"Error jumping by bars: {str(e)}"
```

**Step 3: Run tests and commit**

```bash
uv run pytest tests/test_arrangement_navigation.py::TestJumpByBars -v
git add MCP_Server/server.py tests/test_arrangement_navigation.py
git commit -m "feat: add jump_by_bars MCP tool with tests"
```

---

### Task 13: Run full Phase 1 tests + lint

**Step 1: Run all navigation tests**

```bash
uv run pytest tests/test_arrangement_navigation.py -v
```

Expected: All tests pass

**Step 2: Run linter**

```bash
uv run ruff check MCP_Server/server.py AbletonMCP_Remote_Script/__init__.py
uv run ruff format --check MCP_Server/server.py
```

Expected: No errors

**Step 3: Format if needed**

```bash
uv run ruff format MCP_Server/server.py
```

**Step 4: Final commit for Phase 1**

```bash
git add -A
git commit -m "feat: complete Phase 1 arrangement navigation features"
```

---

## Phase 2: Markers & Structure

### Task 14: Add `get_cue_points` to Remote Script

**Files:**
- Modify: `AbletonMCP_Remote_Script/__init__.py`

**Step 1: Add command routing (read command, no main thread)**

```python
elif command_type == "get_cue_points":
    response["result"] = self._get_cue_points()
```

**Step 2: Add handler method**

```python
def _get_cue_points(self):
    """Get all cue points in the arrangement"""
    try:
        cue_points = []
        for i, cue_point in enumerate(self._song.cue_points):
            cue_points.append({
                "index": i,
                "name": cue_point.name,
                "time": cue_point.time
            })
        return {
            "cue_points": cue_points,
            "count": len(cue_points)
        }
    except Exception as e:
        self.log_message("Error getting cue points: " + str(e))
        raise
```

**Step 3: Commit**

```bash
git add AbletonMCP_Remote_Script/__init__.py
git commit -m "feat(remote): add get_cue_points command"
```

---

### Task 15: Add `get_cue_points` MCP tool + test

**Files:**
- Modify: `MCP_Server/server.py`
- Create: `tests/test_arrangement_markers.py`

**Step 1: Write the failing test**

Create `tests/test_arrangement_markers.py`:

```python
"""Tests for arrangement marker/cue point features."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_ableton_connection():
    """Create a mock Ableton connection."""
    with patch("MCP_Server.server.get_ableton_connection") as mock_get_conn:
        mock_conn = MagicMock()
        mock_conn.send_command_async = AsyncMock()
        mock_get_conn.return_value = mock_conn
        yield mock_conn


class TestGetCuePoints:
    """Tests for get_cue_points tool."""

    async def test_returns_cue_points(self, mock_ableton_connection):
        """Test that get_cue_points returns all cue points."""
        from MCP_Server.server import get_cue_points

        mock_ableton_connection.send_command_async.return_value = {
            "cue_points": [
                {"index": 0, "name": "Intro", "time": 0.0},
                {"index": 1, "name": "Verse", "time": 32.0},
            ],
            "count": 2,
        }

        result = await get_cue_points(MagicMock())

        mock_ableton_connection.send_command_async.assert_called_once_with(
            "get_cue_points"
        )
        parsed = json.loads(result)
        assert len(parsed["cue_points"]) == 2
        assert parsed["cue_points"][0]["name"] == "Intro"
```

**Step 2: Add MCP tool**

```python
@mcp.tool()
async def get_cue_points(ctx: Context) -> str:
    """Get all cue points (markers) in the arrangement."""
    try:
        ableton = get_ableton_connection()
        result = await ableton.send_command_async("get_cue_points")
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting cue points: {str(e)}")
        return f"Error getting cue points: {str(e)}"
```

**Step 3: Run tests and commit**

```bash
uv run pytest tests/test_arrangement_markers.py -v
git add MCP_Server/server.py tests/test_arrangement_markers.py
git commit -m "feat: add get_cue_points MCP tool with tests"
```

---

### Task 16: Add `jump_to_cue_point` to Remote Script

**Files:**
- Modify: `AbletonMCP_Remote_Script/__init__.py`

**Step 1: Add command routing (modifying command)**

```python
elif command_type == "jump_to_cue_point":
    index = params.get("index", 0)
    result = self._jump_to_cue_point(index)
```

**Step 2: Add handler method**

```python
def _jump_to_cue_point(self, index):
    """Jump to a cue point by index"""
    try:
        cue_points = list(self._song.cue_points)
        if index < 0 or index >= len(cue_points):
            raise IndexError("Cue point index out of range")
        cue_point = cue_points[index]
        cue_point.jump()
        return {
            "jumped_to": cue_point.name,
            "time": cue_point.time
        }
    except Exception as e:
        self.log_message("Error jumping to cue point: " + str(e))
        raise
```

**Step 3: Commit**

```bash
git add AbletonMCP_Remote_Script/__init__.py
git commit -m "feat(remote): add jump_to_cue_point command"
```

---

### Task 17: Add `jump_to_cue_point` MCP tool + test

**Files:**
- Modify: `MCP_Server/server.py`
- Modify: `tests/test_arrangement_markers.py`

**Step 1: Write the failing test**

```python
class TestJumpToCuePoint:
    """Tests for jump_to_cue_point tool."""

    async def test_jumps_to_cue_point(self, mock_ableton_connection):
        """Test that jump_to_cue_point navigates to marker."""
        from MCP_Server.server import jump_to_cue_point

        mock_ableton_connection.send_command_async.return_value = {
            "jumped_to": "Chorus",
            "time": 64.0,
        }

        result = await jump_to_cue_point(MagicMock(), index=2)

        mock_ableton_connection.send_command_async.assert_called_once_with(
            "jump_to_cue_point", {"index": 2}
        )
        assert "Chorus" in result
```

**Step 2: Add MCP tool**

```python
@mcp.tool()
async def jump_to_cue_point(ctx: Context, index: int) -> str:
    """
    Jump to a cue point by its index.

    Parameters:
    - index: The index of the cue point to jump to
    """
    try:
        ableton = get_ableton_connection()
        result = await ableton.send_command_async(
            "jump_to_cue_point", {"index": index}
        )
        return f"Jumped to '{result.get('jumped_to')}' at beat {result.get('time')}"
    except Exception as e:
        logger.error(f"Error jumping to cue point: {str(e)}")
        return f"Error jumping to cue point: {str(e)}"
```

**Step 3: Run tests and commit**

```bash
uv run pytest tests/test_arrangement_markers.py::TestJumpToCuePoint -v
git add MCP_Server/server.py tests/test_arrangement_markers.py
git commit -m "feat: add jump_to_cue_point MCP tool with tests"
```

---

### Task 18: Add `create_cue_point` to Remote Script

**Files:**
- Modify: `AbletonMCP_Remote_Script/__init__.py`

**Step 1: Add handler**

```python
elif command_type == "create_cue_point":
    time = params.get("time", 0.0)
    name = params.get("name", "")
    result = self._create_cue_point(time, name)
```

```python
def _create_cue_point(self, time, name):
    """Create a new cue point at the specified time"""
    try:
        # Move to position and create cue point
        self._song.current_song_time = float(time)
        self._song.set_or_delete_cue()

        # Find and rename the new cue point
        cue_points = list(self._song.cue_points)
        for cp in cue_points:
            if abs(cp.time - time) < 0.001:
                if name:
                    cp.name = name
                return {
                    "created": True,
                    "name": cp.name,
                    "time": cp.time
                }
        return {"created": True, "time": time, "name": name}
    except Exception as e:
        self.log_message("Error creating cue point: " + str(e))
        raise
```

**Step 2: Commit**

```bash
git add AbletonMCP_Remote_Script/__init__.py
git commit -m "feat(remote): add create_cue_point command"
```

---

### Task 19: Add `create_cue_point` MCP tool + test

**Files:**
- Modify: `MCP_Server/server.py`
- Modify: `tests/test_arrangement_markers.py`

**Step 1: Write test and add tool**

```python
class TestCreateCuePoint:
    """Tests for create_cue_point tool."""

    async def test_creates_cue_point(self, mock_ableton_connection):
        """Test that create_cue_point adds a marker."""
        from MCP_Server.server import create_cue_point

        mock_ableton_connection.send_command_async.return_value = {
            "created": True,
            "name": "Bridge",
            "time": 96.0,
        }

        result = await create_cue_point(MagicMock(), time=96.0, name="Bridge")

        mock_ableton_connection.send_command_async.assert_called_once_with(
            "create_cue_point", {"time": 96.0, "name": "Bridge"}
        )
        assert "Bridge" in result
```

```python
@mcp.tool()
async def create_cue_point(ctx: Context, time: float, name: str = "") -> str:
    """
    Create a new cue point at the specified position.

    Parameters:
    - time: Position in beats
    - name: Name for the cue point
    """
    try:
        ableton = get_ableton_connection()
        result = await ableton.send_command_async(
            "create_cue_point", {"time": time, "name": name}
        )
        return f"Created cue point '{result.get('name', name)}' at beat {result.get('time', time)}"
    except Exception as e:
        logger.error(f"Error creating cue point: {str(e)}")
        return f"Error creating cue point: {str(e)}"
```

**Step 2: Run tests and commit**

```bash
uv run pytest tests/test_arrangement_markers.py::TestCreateCuePoint -v
git add MCP_Server/server.py tests/test_arrangement_markers.py
git commit -m "feat: add create_cue_point MCP tool with tests"
```

---

### Task 20: Add `delete_cue_point` to Remote Script + MCP tool + test

**Files:**
- Modify: `AbletonMCP_Remote_Script/__init__.py`
- Modify: `MCP_Server/server.py`
- Modify: `tests/test_arrangement_markers.py`

**Step 1: Add Remote Script handler**

```python
elif command_type == "delete_cue_point":
    index = params.get("index", 0)
    result = self._delete_cue_point(index)
```

```python
def _delete_cue_point(self, index):
    """Delete a cue point by index"""
    try:
        cue_points = list(self._song.cue_points)
        if index < 0 or index >= len(cue_points):
            raise IndexError("Cue point index out of range")
        cue_point = cue_points[index]
        name = cue_point.name
        time = cue_point.time
        # Jump to cue point and toggle it off
        self._song.current_song_time = time
        self._song.set_or_delete_cue()
        return {
            "deleted": True,
            "name": name,
            "time": time
        }
    except Exception as e:
        self.log_message("Error deleting cue point: " + str(e))
        raise
```

**Step 2: Add test**

```python
class TestDeleteCuePoint:
    """Tests for delete_cue_point tool."""

    async def test_deletes_cue_point(self, mock_ableton_connection):
        """Test that delete_cue_point removes a marker."""
        from MCP_Server.server import delete_cue_point

        mock_ableton_connection.send_command_async.return_value = {
            "deleted": True,
            "name": "Old Marker",
            "time": 48.0,
        }

        result = await delete_cue_point(MagicMock(), index=1)

        assert "deleted" in result.lower() or "Old Marker" in result
```

**Step 3: Add MCP tool**

```python
@mcp.tool()
async def delete_cue_point(ctx: Context, index: int) -> str:
    """
    Delete a cue point by its index.

    Parameters:
    - index: The index of the cue point to delete
    """
    try:
        ableton = get_ableton_connection()
        result = await ableton.send_command_async(
            "delete_cue_point", {"index": index}
        )
        return f"Deleted cue point '{result.get('name')}' at beat {result.get('time')}"
    except Exception as e:
        logger.error(f"Error deleting cue point: {str(e)}")
        return f"Error deleting cue point: {str(e)}"
```

**Step 4: Commit**

```bash
git add AbletonMCP_Remote_Script/__init__.py MCP_Server/server.py tests/test_arrangement_markers.py
git commit -m "feat: add delete_cue_point command and MCP tool with tests"
```

---

### Task 21: Add `jump_to_next_cue_point` and `jump_to_prev_cue_point`

**Files:**
- Modify: `AbletonMCP_Remote_Script/__init__.py`
- Modify: `MCP_Server/server.py`
- Modify: `tests/test_arrangement_markers.py`

**Step 1: Add Remote Script handlers**

```python
elif command_type == "jump_to_next_cue_point":
    result = self._jump_to_next_cue_point()
elif command_type == "jump_to_prev_cue_point":
    result = self._jump_to_prev_cue_point()
```

```python
def _jump_to_next_cue_point(self):
    """Jump to the next cue point from current position"""
    try:
        current_time = self._song.current_song_time
        cue_points = sorted(self._song.cue_points, key=lambda cp: cp.time)
        for cp in cue_points:
            if cp.time > current_time + 0.001:
                cp.jump()
                return {"jumped_to": cp.name, "time": cp.time}
        return {"jumped_to": None, "message": "No next cue point"}
    except Exception as e:
        self.log_message("Error jumping to next cue point: " + str(e))
        raise

def _jump_to_prev_cue_point(self):
    """Jump to the previous cue point from current position"""
    try:
        current_time = self._song.current_song_time
        cue_points = sorted(self._song.cue_points, key=lambda cp: cp.time, reverse=True)
        for cp in cue_points:
            if cp.time < current_time - 0.001:
                cp.jump()
                return {"jumped_to": cp.name, "time": cp.time}
        return {"jumped_to": None, "message": "No previous cue point"}
    except Exception as e:
        self.log_message("Error jumping to previous cue point: " + str(e))
        raise
```

**Step 2: Add tests**

```python
class TestJumpToNextPrevCuePoint:
    """Tests for jump_to_next_cue_point and jump_to_prev_cue_point tools."""

    async def test_jump_to_next(self, mock_ableton_connection):
        """Test jumping to next cue point."""
        from MCP_Server.server import jump_to_next_cue_point

        mock_ableton_connection.send_command_async.return_value = {
            "jumped_to": "Chorus",
            "time": 64.0,
        }

        result = await jump_to_next_cue_point(MagicMock())

        assert "Chorus" in result

    async def test_jump_to_prev(self, mock_ableton_connection):
        """Test jumping to previous cue point."""
        from MCP_Server.server import jump_to_prev_cue_point

        mock_ableton_connection.send_command_async.return_value = {
            "jumped_to": "Intro",
            "time": 0.0,
        }

        result = await jump_to_prev_cue_point(MagicMock())

        assert "Intro" in result
```

**Step 3: Add MCP tools**

```python
@mcp.tool()
async def jump_to_next_cue_point(ctx: Context) -> str:
    """Jump to the next cue point from the current playhead position."""
    try:
        ableton = get_ableton_connection()
        result = await ableton.send_command_async("jump_to_next_cue_point")
        if result.get("jumped_to"):
            return f"Jumped to '{result['jumped_to']}' at beat {result['time']}"
        return result.get("message", "No next cue point")
    except Exception as e:
        logger.error(f"Error jumping to next cue point: {str(e)}")
        return f"Error jumping to next cue point: {str(e)}"


@mcp.tool()
async def jump_to_prev_cue_point(ctx: Context) -> str:
    """Jump to the previous cue point from the current playhead position."""
    try:
        ableton = get_ableton_connection()
        result = await ableton.send_command_async("jump_to_prev_cue_point")
        if result.get("jumped_to"):
            return f"Jumped to '{result['jumped_to']}' at beat {result['time']}"
        return result.get("message", "No previous cue point")
    except Exception as e:
        logger.error(f"Error jumping to previous cue point: {str(e)}")
        return f"Error jumping to previous cue point: {str(e)}"
```

**Step 4: Commit**

```bash
git add AbletonMCP_Remote_Script/__init__.py MCP_Server/server.py tests/test_arrangement_markers.py
git commit -m "feat: add jump_to_next/prev_cue_point commands with tests"
```

---

### Task 22: Run full Phase 2 tests + lint

```bash
uv run pytest tests/test_arrangement_markers.py -v
uv run ruff check MCP_Server/server.py AbletonMCP_Remote_Script/__init__.py
uv run ruff format MCP_Server/server.py
git add -A
git commit -m "feat: complete Phase 2 arrangement markers features"
```

---

## Phase 3: Clip Operations & Recording

### Task 23: Add `get_arrangement_clips` to Remote Script + MCP tool + test

**Files:**
- Modify: `AbletonMCP_Remote_Script/__init__.py`
- Modify: `MCP_Server/server.py`
- Create: `tests/test_arrangement_clips.py`

**Step 1: Add Remote Script handler**

```python
elif command_type == "get_arrangement_clips":
    track_index = params.get("track_index", 0)
    response["result"] = self._get_arrangement_clips(track_index)
```

```python
def _get_arrangement_clips(self, track_index):
    """Get all clips in the arrangement for a track"""
    try:
        if track_index < 0 or track_index >= len(self._song.tracks):
            raise IndexError("Track index out of range")

        track = self._song.tracks[track_index]
        clips = []

        if hasattr(track, 'arrangement_clips'):
            for i, clip in enumerate(track.arrangement_clips):
                clips.append({
                    "id": i,
                    "name": clip.name,
                    "start_time": clip.start_time,
                    "end_time": clip.end_time,
                    "length": clip.length,
                    "is_midi_clip": clip.is_midi_clip if hasattr(clip, 'is_midi_clip') else False
                })

        return {
            "track_index": track_index,
            "track_name": track.name,
            "clips": clips,
            "count": len(clips)
        }
    except Exception as e:
        self.log_message("Error getting arrangement clips: " + str(e))
        raise
```

**Step 2: Create test file**

Create `tests/test_arrangement_clips.py`:

```python
"""Tests for arrangement clip features."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_ableton_connection():
    """Create a mock Ableton connection."""
    with patch("MCP_Server.server.get_ableton_connection") as mock_get_conn:
        mock_conn = MagicMock()
        mock_conn.send_command_async = AsyncMock()
        mock_get_conn.return_value = mock_conn
        yield mock_conn


class TestGetArrangementClips:
    """Tests for get_arrangement_clips tool."""

    async def test_returns_clips(self, mock_ableton_connection):
        """Test that get_arrangement_clips returns arrangement clips."""
        from MCP_Server.server import get_arrangement_clips

        mock_ableton_connection.send_command_async.return_value = {
            "track_index": 0,
            "track_name": "Bass",
            "clips": [
                {"id": 0, "name": "Bass 1", "start_time": 0.0, "end_time": 16.0},
                {"id": 1, "name": "Bass 2", "start_time": 32.0, "end_time": 48.0},
            ],
            "count": 2,
        }

        result = await get_arrangement_clips(MagicMock(), track_index=0)

        parsed = json.loads(result)
        assert len(parsed["clips"]) == 2
```

**Step 3: Add MCP tool**

```python
@mcp.tool()
async def get_arrangement_clips(ctx: Context, track_index: int) -> str:
    """
    Get all clips in the arrangement view for a track.

    Parameters:
    - track_index: The index of the track
    """
    try:
        ableton = get_ableton_connection()
        result = await ableton.send_command_async(
            "get_arrangement_clips", {"track_index": track_index}
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting arrangement clips: {str(e)}")
        return f"Error getting arrangement clips: {str(e)}"
```

**Step 4: Commit**

```bash
git add AbletonMCP_Remote_Script/__init__.py MCP_Server/server.py tests/test_arrangement_clips.py
git commit -m "feat: add get_arrangement_clips command with tests"
```

---

### Task 24: Add `duplicate_clip_to_arrangement` + test

**Step 1: Add Remote Script handler**

```python
elif command_type == "duplicate_clip_to_arrangement":
    track_index = params.get("track_index", 0)
    clip_index = params.get("clip_index", 0)
    time = params.get("time", 0.0)
    result = self._duplicate_clip_to_arrangement(track_index, clip_index, time)
```

```python
def _duplicate_clip_to_arrangement(self, track_index, clip_index, time):
    """Duplicate a session clip to the arrangement at specified time"""
    try:
        if track_index < 0 or track_index >= len(self._song.tracks):
            raise IndexError("Track index out of range")

        track = self._song.tracks[track_index]

        if clip_index < 0 or clip_index >= len(track.clip_slots):
            raise IndexError("Clip index out of range")

        clip_slot = track.clip_slots[clip_index]

        if not clip_slot.has_clip:
            raise Exception("No clip in slot")

        clip_name = clip_slot.clip.name
        track.duplicate_clip_to_arrangement(clip_slot, float(time))

        return {
            "duplicated": True,
            "source_clip": clip_name,
            "destination_time": time,
            "track_name": track.name
        }
    except Exception as e:
        self.log_message("Error duplicating clip to arrangement: " + str(e))
        raise
```

**Step 2: Add test**

```python
class TestDuplicateClipToArrangement:
    """Tests for duplicate_clip_to_arrangement tool."""

    async def test_duplicates_clip(self, mock_ableton_connection):
        """Test duplicating session clip to arrangement."""
        from MCP_Server.server import duplicate_clip_to_arrangement

        mock_ableton_connection.send_command_async.return_value = {
            "duplicated": True,
            "source_clip": "Bass Loop",
            "destination_time": 64.0,
            "track_name": "Bass",
        }

        result = await duplicate_clip_to_arrangement(
            MagicMock(), track_index=0, clip_index=0, time=64.0
        )

        assert "Bass Loop" in result
        assert "64.0" in result
```

**Step 3: Add MCP tool**

```python
@mcp.tool()
async def duplicate_clip_to_arrangement(
    ctx: Context, track_index: int, clip_index: int, time: float
) -> str:
    """
    Duplicate a session clip to the arrangement at a specified time.

    Parameters:
    - track_index: The track containing the source clip
    - clip_index: The clip slot index of the source clip
    - time: Position in beats where the clip should be placed
    """
    try:
        ableton = get_ableton_connection()
        result = await ableton.send_command_async(
            "duplicate_clip_to_arrangement",
            {"track_index": track_index, "clip_index": clip_index, "time": time},
        )
        return (
            f"Duplicated '{result.get('source_clip')}' to arrangement "
            f"at beat {result.get('destination_time')} on track '{result.get('track_name')}'"
        )
    except Exception as e:
        logger.error(f"Error duplicating clip to arrangement: {str(e)}")
        return f"Error duplicating clip to arrangement: {str(e)}"
```

**Step 4: Commit**

```bash
git add AbletonMCP_Remote_Script/__init__.py MCP_Server/server.py tests/test_arrangement_clips.py
git commit -m "feat: add duplicate_clip_to_arrangement command with tests"
```

---

### Task 25: Add recording controls (`set_arrangement_overdub`, `set_punch_in`, `set_punch_out`, `set_record_mode`)

**Step 1: Add Remote Script handlers**

```python
elif command_type == "set_arrangement_overdub":
    enabled = params.get("enabled", False)
    result = self._set_arrangement_overdub(enabled)
elif command_type == "set_punch_in":
    enabled = params.get("enabled", False)
    result = self._set_punch_in(enabled)
elif command_type == "set_punch_out":
    enabled = params.get("enabled", False)
    result = self._set_punch_out(enabled)
elif command_type == "set_record_mode":
    enabled = params.get("enabled", False)
    result = self._set_record_mode(enabled)
```

```python
def _set_arrangement_overdub(self, enabled):
    """Set arrangement overdub mode"""
    try:
        self._song.arrangement_overdub = bool(enabled)
        return {"arrangement_overdub": self._song.arrangement_overdub}
    except Exception as e:
        self.log_message("Error setting arrangement overdub: " + str(e))
        raise

def _set_punch_in(self, enabled):
    """Set punch-in state"""
    try:
        self._song.punch_in = bool(enabled)
        return {"punch_in": self._song.punch_in}
    except Exception as e:
        self.log_message("Error setting punch in: " + str(e))
        raise

def _set_punch_out(self, enabled):
    """Set punch-out state"""
    try:
        self._song.punch_out = bool(enabled)
        return {"punch_out": self._song.punch_out}
    except Exception as e:
        self.log_message("Error setting punch out: " + str(e))
        raise

def _set_record_mode(self, enabled):
    """Set global record mode"""
    try:
        self._song.record_mode = bool(enabled)
        return {"record_mode": self._song.record_mode}
    except Exception as e:
        self.log_message("Error setting record mode: " + str(e))
        raise
```

**Step 2: Add tests**

Add to `tests/test_arrangement_clips.py`:

```python
class TestRecordingControls:
    """Tests for recording control tools."""

    async def test_set_arrangement_overdub(self, mock_ableton_connection):
        """Test setting arrangement overdub."""
        from MCP_Server.server import set_arrangement_overdub

        mock_ableton_connection.send_command_async.return_value = {
            "arrangement_overdub": True
        }

        result = await set_arrangement_overdub(MagicMock(), enabled=True)

        assert "enabled" in result.lower()

    async def test_set_punch_in(self, mock_ableton_connection):
        """Test setting punch-in."""
        from MCP_Server.server import set_punch_in

        mock_ableton_connection.send_command_async.return_value = {"punch_in": True}

        result = await set_punch_in(MagicMock(), enabled=True)

        assert "enabled" in result.lower()

    async def test_set_punch_out(self, mock_ableton_connection):
        """Test setting punch-out."""
        from MCP_Server.server import set_punch_out

        mock_ableton_connection.send_command_async.return_value = {"punch_out": True}

        result = await set_punch_out(MagicMock(), enabled=True)

        assert "enabled" in result.lower()

    async def test_set_record_mode(self, mock_ableton_connection):
        """Test setting record mode."""
        from MCP_Server.server import set_record_mode

        mock_ableton_connection.send_command_async.return_value = {"record_mode": True}

        result = await set_record_mode(MagicMock(), enabled=True)

        assert "enabled" in result.lower()
```

**Step 3: Add MCP tools**

```python
@mcp.tool()
async def set_arrangement_overdub(ctx: Context, enabled: bool) -> str:
    """
    Enable or disable arrangement overdub mode.

    Parameters:
    - enabled: True to enable overdub, False to disable
    """
    try:
        ableton = get_ableton_connection()
        result = await ableton.send_command_async(
            "set_arrangement_overdub", {"enabled": enabled}
        )
        state = "enabled" if result.get("arrangement_overdub") else "disabled"
        return f"Arrangement overdub {state}"
    except Exception as e:
        logger.error(f"Error setting arrangement overdub: {str(e)}")
        return f"Error setting arrangement overdub: {str(e)}"


@mcp.tool()
async def set_punch_in(ctx: Context, enabled: bool) -> str:
    """
    Enable or disable punch-in recording.

    Parameters:
    - enabled: True to enable punch-in, False to disable
    """
    try:
        ableton = get_ableton_connection()
        result = await ableton.send_command_async("set_punch_in", {"enabled": enabled})
        state = "enabled" if result.get("punch_in") else "disabled"
        return f"Punch-in {state}"
    except Exception as e:
        logger.error(f"Error setting punch-in: {str(e)}")
        return f"Error setting punch-in: {str(e)}"


@mcp.tool()
async def set_punch_out(ctx: Context, enabled: bool) -> str:
    """
    Enable or disable punch-out recording.

    Parameters:
    - enabled: True to enable punch-out, False to disable
    """
    try:
        ableton = get_ableton_connection()
        result = await ableton.send_command_async("set_punch_out", {"enabled": enabled})
        state = "enabled" if result.get("punch_out") else "disabled"
        return f"Punch-out {state}"
    except Exception as e:
        logger.error(f"Error setting punch-out: {str(e)}")
        return f"Error setting punch-out: {str(e)}"


@mcp.tool()
async def set_record_mode(ctx: Context, enabled: bool) -> str:
    """
    Enable or disable global arrangement recording.

    Parameters:
    - enabled: True to enable recording, False to disable
    """
    try:
        ableton = get_ableton_connection()
        result = await ableton.send_command_async(
            "set_record_mode", {"enabled": enabled}
        )
        state = "enabled" if result.get("record_mode") else "disabled"
        return f"Record mode {state}"
    except Exception as e:
        logger.error(f"Error setting record mode: {str(e)}")
        return f"Error setting record mode: {str(e)}"
```

**Step 4: Update modifying commands list**

Add to `is_modifying_command` list in `MCP_Server/server.py`:

```python
"set_arrangement_overdub",
"set_punch_in",
"set_punch_out",
"set_record_mode",
"duplicate_clip_to_arrangement",
```

**Step 5: Commit**

```bash
git add AbletonMCP_Remote_Script/__init__.py MCP_Server/server.py tests/test_arrangement_clips.py
git commit -m "feat: add recording control commands with tests"
```

---

### Task 26: Run all tests + lint + final commit

**Step 1: Run all tests**

```bash
uv run pytest -v
```

Expected: All tests pass

**Step 2: Run linter and format**

```bash
uv run ruff check MCP_Server/server.py AbletonMCP_Remote_Script/__init__.py --fix
uv run ruff format MCP_Server/server.py
```

**Step 3: Final commit**

```bash
git add -A
git commit -m "feat: complete arrangement view features - all phases"
```

---

## Summary

| Phase | Tasks | Commands Added |
|-------|-------|----------------|
| 1 | 1-13 | `get_arrangement_info`, `set_song_time`, `set_loop_region`, `set_loop_enabled`, `continue_playing`, `jump_by_bars` |
| 2 | 14-22 | `get_cue_points`, `jump_to_cue_point`, `create_cue_point`, `delete_cue_point`, `jump_to_next_cue_point`, `jump_to_prev_cue_point` |
| 3 | 23-26 | `get_arrangement_clips`, `duplicate_clip_to_arrangement`, `set_arrangement_overdub`, `set_punch_in`, `set_punch_out`, `set_record_mode` |
