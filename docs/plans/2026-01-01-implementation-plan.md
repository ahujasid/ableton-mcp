# AbletonMCP Performance & Features Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix 4 performance issues and add high-value LOM features to AbletonMCP.

**Architecture:** MCP Server (Python/FastMCP) communicates via TCP socket with Ableton Remote Script. Changes touch both components. Remote Script must remain Python 2/3 compatible.

**Tech Stack:** Python 3.10+, FastMCP, asyncio/anyio, Ableton Live Object Model

---

## Phase 1: Performance Fixes

### Task 1: Remove Hardcoded Delays

**Files:**
- Modify: `MCP_Server/server.py:118-142`

**Step 1: Remove pre-send delay**

In `send_command()`, delete lines 118-121:

```python
# DELETE THIS BLOCK:
            # For state-modifying commands, add a small delay to give Ableton time to process
            if is_modifying_command:
                import time
                time.sleep(0.1)  # 100ms delay
```

**Step 2: Remove post-receive delay**

Delete lines 139-142 (after your previous deletion, around line 135):

```python
# DELETE THIS BLOCK:
            # For state-modifying commands, add another small delay after receiving response
            if is_modifying_command:
                import time
                time.sleep(0.1)  # 100ms delay
```

**Step 3: Remove unused is_modifying_command check**

The `is_modifying_command` variable is now only used for timeout selection. Keep the timeout logic but remove the variable if desired, or leave it for clarity.

**Step 4: Verify syntax**

Run: `cd /Users/jdelsman/Projects/ableton-mcp/.worktrees/perf-and-features && python -m py_compile MCP_Server/server.py`
Expected: No output (success)

**Step 5: Commit**

```bash
git add MCP_Server/server.py
git commit -m "perf: remove 200ms hardcoded delays from send_command"
```

---

### Task 2: Add Ping Command to Remote Script

**Files:**
- Modify: `AbletonMCP_Remote_Script/__init__.py:221-231`

**Step 1: Add ping handler in _process_command**

Find the command routing section (around line 221) and add ping as the first command check:

```python
        try:
            # Route the command to the appropriate handler
            if command_type == "ping":
                response["result"] = {"status": "ok"}
            elif command_type == "get_session_info":
```

**Step 2: Verify syntax (Python 2 compatible)**

Run: `cd /Users/jdelsman/Projects/ableton-mcp/.worktrees/perf-and-features && python -m py_compile AbletonMCP_Remote_Script/__init__.py`
Expected: No output (success)

**Step 3: Commit**

```bash
git add AbletonMCP_Remote_Script/__init__.py
git commit -m "feat(remote): add ping command for health checks"
```

---

### Task 3: Update Health Check to Use Ping

**Files:**
- Modify: `MCP_Server/server.py:200-214`

**Step 1: Replace empty byte check with ping command**

Replace the health check logic in `get_ableton_connection()`:

```python
    if _ableton_connection is not None:
        try:
            # Test the connection with a lightweight ping command
            _ableton_connection.sock.settimeout(2.0)
            ping_cmd = json.dumps({"type": "ping", "params": {}}).encode('utf-8')
            _ableton_connection.sock.sendall(ping_cmd)
            response = _ableton_connection.receive_full_response(_ableton_connection.sock)
            result = json.loads(response.decode('utf-8'))
            if result.get("status") == "success":
                return _ableton_connection
            else:
                raise Exception("Ping failed")
        except Exception as e:
            logger.warning(f"Existing connection is no longer valid: {str(e)}")
            try:
                _ableton_connection.disconnect()
            except:
                pass
            _ableton_connection = None
```

**Step 2: Verify syntax**

Run: `cd /Users/jdelsman/Projects/ableton-mcp/.worktrees/perf-and-features && python -m py_compile MCP_Server/server.py`
Expected: No output (success)

**Step 3: Commit**

```bash
git add MCP_Server/server.py
git commit -m "perf: use ping command for connection health check"
```

---

### Task 4: Add Browser URI Cache to Remote Script

**Files:**
- Modify: `AbletonMCP_Remote_Script/__init__.py`

**Step 1: Add cache instance variable in __init__**

Find `__init__` method (around line 28) and add after `self._song = self.song()`:

```python
        # Cache for browser URIs to avoid repeated tree traversal
        self._browser_uri_cache = {}
```

**Step 2: Create cache population method**

Add new method after `_find_browser_item_by_uri` (around line 800):

```python
    def _populate_browser_cache(self, browser_or_item, max_depth=10, current_depth=0):
        """Populate the URI cache from browser tree"""
        try:
            if current_depth >= max_depth:
                return

            # Add this item to cache if it has a URI
            if hasattr(browser_or_item, 'uri') and browser_or_item.uri:
                self._browser_uri_cache[browser_or_item.uri] = browser_or_item

            # Check if this is a browser with root categories
            if hasattr(browser_or_item, 'instruments'):
                categories = [
                    browser_or_item.instruments,
                    browser_or_item.sounds,
                    browser_or_item.drums,
                    browser_or_item.audio_effects,
                    browser_or_item.midi_effects
                ]
                for category in categories:
                    self._populate_browser_cache(category, max_depth, current_depth + 1)
                return

            # Recurse into children
            if hasattr(browser_or_item, 'children') and browser_or_item.children:
                for child in browser_or_item.children:
                    self._populate_browser_cache(child, max_depth, current_depth + 1)
        except Exception as e:
            self.log_message("Error populating browser cache: {0}".format(str(e)))
```

**Step 3: Modify _find_browser_item_by_uri to use cache**

Replace the existing method:

```python
    def _find_browser_item_by_uri(self, browser_or_item, uri, max_depth=10, current_depth=0):
        """Find a browser item by its URI, using cache for O(1) lookup"""
        try:
            # Check cache first
            if uri in self._browser_uri_cache:
                return self._browser_uri_cache[uri]

            # Cache miss - populate cache if empty
            if not self._browser_uri_cache and hasattr(browser_or_item, 'instruments'):
                self.log_message("Populating browser URI cache...")
                self._populate_browser_cache(browser_or_item)
                self.log_message("Browser cache populated with {0} items".format(len(self._browser_uri_cache)))

                # Try cache again
                if uri in self._browser_uri_cache:
                    return self._browser_uri_cache[uri]

            # Fall back to original traversal for items not in cache
            if hasattr(browser_or_item, 'uri') and browser_or_item.uri == uri:
                return browser_or_item

            if current_depth >= max_depth:
                return None

            if hasattr(browser_or_item, 'instruments'):
                categories = [
                    browser_or_item.instruments,
                    browser_or_item.sounds,
                    browser_or_item.drums,
                    browser_or_item.audio_effects,
                    browser_or_item.midi_effects
                ]
                for category in categories:
                    item = self._find_browser_item_by_uri(category, uri, max_depth, current_depth + 1)
                    if item:
                        self._browser_uri_cache[uri] = item  # Cache the find
                        return item
                return None

            if hasattr(browser_or_item, 'children') and browser_or_item.children:
                for child in browser_or_item.children:
                    item = self._find_browser_item_by_uri(child, uri, max_depth, current_depth + 1)
                    if item:
                        self._browser_uri_cache[uri] = item  # Cache the find
                        return item

            return None
        except Exception as e:
            self.log_message("Error finding browser item by URI: {0}".format(str(e)))
            return None
```

**Step 4: Add cache clear method**

Add method to clear cache (useful if browser changes):

```python
    def _clear_browser_cache(self):
        """Clear the browser URI cache"""
        self._browser_uri_cache = {}
        self.log_message("Browser URI cache cleared")
```

**Step 5: Verify syntax**

Run: `cd /Users/jdelsman/Projects/ableton-mcp/.worktrees/perf-and-features && python -m py_compile AbletonMCP_Remote_Script/__init__.py`
Expected: No output (success)

**Step 6: Commit**

```bash
git add AbletonMCP_Remote_Script/__init__.py
git commit -m "perf(remote): add browser URI cache for O(1) lookups"
```

---

### Task 5: Convert Socket to Async with anyio

**Files:**
- Modify: `MCP_Server/server.py`

**Step 1: Add anyio import**

Add at top of file after existing imports:

```python
import anyio
```

**Step 2: Create async wrapper for send_command**

Add new async method to `AbletonConnection` class:

```python
    async def send_command_async(self, command_type: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Async wrapper for send_command using anyio thread pool"""
        return await anyio.to_thread.run_sync(
            lambda: self.send_command(command_type, params)
        )
```

**Step 3: Update MCP tools to use async**

Convert each tool from sync to async. Example for `get_session_info`:

```python
@mcp.tool()
async def get_session_info(ctx: Context) -> str:
    """Get detailed information about the current Ableton session"""
    try:
        ableton = get_ableton_connection()
        result = await ableton.send_command_async("get_session_info")
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting session info from Ableton: {str(e)}")
        return f"Error getting session info: {str(e)}"
```

**Step 4: Repeat for all other tools**

Apply the same pattern to all `@mcp.tool()` functions:
- Add `async` keyword to function definition
- Change `send_command` to `await ableton.send_command_async`

Tools to update:
- `get_track_info`
- `create_midi_track`
- `set_track_name`
- `create_clip`
- `add_notes_to_clip`
- `set_clip_name`
- `set_tempo`
- `load_instrument_or_effect`
- `fire_clip`
- `stop_clip`
- `start_playback`
- `stop_playback`
- `get_browser_tree`
- `get_browser_items_at_path`
- `load_drum_kit`

**Step 5: Verify syntax**

Run: `cd /Users/jdelsman/Projects/ableton-mcp/.worktrees/perf-and-features && python -m py_compile MCP_Server/server.py`
Expected: No output (success)

**Step 6: Commit**

```bash
git add MCP_Server/server.py
git commit -m "perf: convert MCP tools to async using anyio thread pool"
```

---

## Phase 2: Features - Group 1 (Simple Additions)

### Task 6: Add Undo/Redo Commands

**Files:**
- Modify: `AbletonMCP_Remote_Script/__init__.py`
- Modify: `MCP_Server/server.py`

**Step 1: Add undo/redo to Remote Script command routing**

In `_process_command`, add to the state-modifying commands list (around line 229):

```python
            elif command_type in ["create_midi_track", "create_audio_track", "set_track_name",
                                 "create_clip", "add_notes_to_clip", "set_clip_name",
                                 "set_tempo", "fire_clip", "stop_clip",
                                 "start_playback", "stop_playback", "load_browser_item",
                                 "undo", "redo", "delete_track", "delete_clip",
                                 "set_metronome", "fire_scene"]:
```

**Step 2: Add undo/redo handlers in main_thread_task**

Inside the `main_thread_task` function, add:

```python
                        elif command_type == "undo":
                            result = self._undo()
                        elif command_type == "redo":
                            result = self._redo()
```

**Step 3: Add _undo and _redo methods to Remote Script**

```python
    def _undo(self):
        """Undo the last action"""
        try:
            if self._song.can_undo:
                self._song.undo()
                return {"undone": True}
            else:
                return {"undone": False, "message": "Nothing to undo"}
        except Exception as e:
            self.log_message("Error in undo: " + str(e))
            raise

    def _redo(self):
        """Redo the last undone action"""
        try:
            if self._song.can_redo:
                self._song.redo()
                return {"redone": True}
            else:
                return {"redone": False, "message": "Nothing to redo"}
        except Exception as e:
            self.log_message("Error in redo: " + str(e))
            raise
```

**Step 4: Add MCP tools for undo/redo**

In `server.py`, add after `stop_playback`:

```python
@mcp.tool()
async def undo(ctx: Context) -> str:
    """Undo the last action in Ableton."""
    try:
        ableton = get_ableton_connection()
        result = await ableton.send_command_async("undo")
        if result.get("undone"):
            return "Undid last action"
        else:
            return result.get("message", "Nothing to undo")
    except Exception as e:
        logger.error(f"Error undoing: {str(e)}")
        return f"Error undoing: {str(e)}"

@mcp.tool()
async def redo(ctx: Context) -> str:
    """Redo the last undone action in Ableton."""
    try:
        ableton = get_ableton_connection()
        result = await ableton.send_command_async("redo")
        if result.get("redone"):
            return "Redid last action"
        else:
            return result.get("message", "Nothing to redo")
    except Exception as e:
        logger.error(f"Error redoing: {str(e)}")
        return f"Error redoing: {str(e)}"
```

**Step 5: Verify syntax for both files**

Run:
```bash
cd /Users/jdelsman/Projects/ableton-mcp/.worktrees/perf-and-features
python -m py_compile MCP_Server/server.py
python -m py_compile AbletonMCP_Remote_Script/__init__.py
```
Expected: No output (success)

**Step 6: Commit**

```bash
git add MCP_Server/server.py AbletonMCP_Remote_Script/__init__.py
git commit -m "feat: add undo/redo commands"
```

---

### Task 7: Add Delete Track Command

**Files:**
- Modify: `AbletonMCP_Remote_Script/__init__.py`
- Modify: `MCP_Server/server.py`

**Step 1: Add handler in Remote Script main_thread_task**

```python
                        elif command_type == "delete_track":
                            track_index = params.get("track_index", 0)
                            result = self._delete_track(track_index)
```

**Step 2: Add _delete_track method**

```python
    def _delete_track(self, track_index):
        """Delete a track at the specified index"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track_name = self._song.tracks[track_index].name
            self._song.delete_track(track_index)

            return {"deleted": True, "track_name": track_name}
        except Exception as e:
            self.log_message("Error deleting track: " + str(e))
            raise
```

**Step 3: Add MCP tool**

```python
@mcp.tool()
async def delete_track(ctx: Context, track_index: int) -> str:
    """
    Delete a track from the Ableton session.

    Parameters:
    - track_index: The index of the track to delete
    """
    try:
        ableton = get_ableton_connection()
        result = await ableton.send_command_async("delete_track", {"track_index": track_index})
        return f"Deleted track: {result.get('track_name', 'unknown')}"
    except Exception as e:
        logger.error(f"Error deleting track: {str(e)}")
        return f"Error deleting track: {str(e)}"
```

**Step 4: Verify and commit**

```bash
cd /Users/jdelsman/Projects/ableton-mcp/.worktrees/perf-and-features
python -m py_compile MCP_Server/server.py
python -m py_compile AbletonMCP_Remote_Script/__init__.py
git add MCP_Server/server.py AbletonMCP_Remote_Script/__init__.py
git commit -m "feat: add delete_track command"
```

---

### Task 8: Add Create Audio Track Command

**Files:**
- Modify: `AbletonMCP_Remote_Script/__init__.py`
- Modify: `MCP_Server/server.py`

**Step 1: Add handler in Remote Script main_thread_task**

```python
                        elif command_type == "create_audio_track":
                            index = params.get("index", -1)
                            result = self._create_audio_track(index)
```

**Step 2: Add _create_audio_track method**

```python
    def _create_audio_track(self, index):
        """Create a new audio track at the specified index"""
        try:
            self._song.create_audio_track(index)

            new_track_index = len(self._song.tracks) - 1 if index == -1 else index
            new_track = self._song.tracks[new_track_index]

            return {
                "index": new_track_index,
                "name": new_track.name
            }
        except Exception as e:
            self.log_message("Error creating audio track: " + str(e))
            raise
```

**Step 3: Add MCP tool**

```python
@mcp.tool()
async def create_audio_track(ctx: Context, index: int = -1) -> str:
    """
    Create a new audio track in the Ableton session.

    Parameters:
    - index: The index to insert the track at (-1 = end of list)
    """
    try:
        ableton = get_ableton_connection()
        result = await ableton.send_command_async("create_audio_track", {"index": index})
        return f"Created new audio track: {result.get('name', 'unknown')}"
    except Exception as e:
        logger.error(f"Error creating audio track: {str(e)}")
        return f"Error creating audio track: {str(e)}"
```

**Step 4: Verify and commit**

```bash
cd /Users/jdelsman/Projects/ableton-mcp/.worktrees/perf-and-features
python -m py_compile MCP_Server/server.py
python -m py_compile AbletonMCP_Remote_Script/__init__.py
git add MCP_Server/server.py AbletonMCP_Remote_Script/__init__.py
git commit -m "feat: add create_audio_track command"
```

---

### Task 9: Add Delete Clip Command

**Files:**
- Modify: `AbletonMCP_Remote_Script/__init__.py`
- Modify: `MCP_Server/server.py`

**Step 1: Add handler in Remote Script main_thread_task**

```python
                        elif command_type == "delete_clip":
                            track_index = params.get("track_index", 0)
                            clip_index = params.get("clip_index", 0)
                            result = self._delete_clip(track_index, clip_index)
```

**Step 2: Add _delete_clip method**

```python
    def _delete_clip(self, track_index, clip_index):
        """Delete a clip from a clip slot"""
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
            clip_slot.delete_clip()

            return {"deleted": True, "clip_name": clip_name}
        except Exception as e:
            self.log_message("Error deleting clip: " + str(e))
            raise
```

**Step 3: Add MCP tool**

```python
@mcp.tool()
async def delete_clip(ctx: Context, track_index: int, clip_index: int) -> str:
    """
    Delete a clip from a clip slot.

    Parameters:
    - track_index: The index of the track containing the clip
    - clip_index: The index of the clip slot containing the clip
    """
    try:
        ableton = get_ableton_connection()
        result = await ableton.send_command_async("delete_clip", {
            "track_index": track_index,
            "clip_index": clip_index
        })
        return f"Deleted clip: {result.get('clip_name', 'unknown')}"
    except Exception as e:
        logger.error(f"Error deleting clip: {str(e)}")
        return f"Error deleting clip: {str(e)}"
```

**Step 4: Verify and commit**

```bash
cd /Users/jdelsman/Projects/ableton-mcp/.worktrees/perf-and-features
python -m py_compile MCP_Server/server.py
python -m py_compile AbletonMCP_Remote_Script/__init__.py
git add MCP_Server/server.py AbletonMCP_Remote_Script/__init__.py
git commit -m "feat: add delete_clip command"
```

---

### Task 10: Add Set Metronome Command

**Files:**
- Modify: `AbletonMCP_Remote_Script/__init__.py`
- Modify: `MCP_Server/server.py`

**Step 1: Add handler in Remote Script main_thread_task**

```python
                        elif command_type == "set_metronome":
                            enabled = params.get("enabled", True)
                            result = self._set_metronome(enabled)
```

**Step 2: Add _set_metronome method**

```python
    def _set_metronome(self, enabled):
        """Enable or disable the metronome"""
        try:
            self._song.metronome = enabled
            return {"metronome": self._song.metronome}
        except Exception as e:
            self.log_message("Error setting metronome: " + str(e))
            raise
```

**Step 3: Add MCP tool**

```python
@mcp.tool()
async def set_metronome(ctx: Context, enabled: bool) -> str:
    """
    Enable or disable the metronome.

    Parameters:
    - enabled: True to enable, False to disable
    """
    try:
        ableton = get_ableton_connection()
        result = await ableton.send_command_async("set_metronome", {"enabled": enabled})
        state = "enabled" if result.get("metronome") else "disabled"
        return f"Metronome {state}"
    except Exception as e:
        logger.error(f"Error setting metronome: {str(e)}")
        return f"Error setting metronome: {str(e)}"
```

**Step 4: Verify and commit**

```bash
cd /Users/jdelsman/Projects/ableton-mcp/.worktrees/perf-and-features
python -m py_compile MCP_Server/server.py
python -m py_compile AbletonMCP_Remote_Script/__init__.py
git add MCP_Server/server.py AbletonMCP_Remote_Script/__init__.py
git commit -m "feat: add set_metronome command"
```

---

### Task 11: Add Fire Scene Command

**Files:**
- Modify: `AbletonMCP_Remote_Script/__init__.py`
- Modify: `MCP_Server/server.py`

**Step 1: Add handler in Remote Script main_thread_task**

```python
                        elif command_type == "fire_scene":
                            scene_index = params.get("scene_index", 0)
                            result = self._fire_scene(scene_index)
```

**Step 2: Add _fire_scene method**

```python
    def _fire_scene(self, scene_index):
        """Fire a scene (trigger all clips in a row)"""
        try:
            if scene_index < 0 or scene_index >= len(self._song.scenes):
                raise IndexError("Scene index out of range")

            scene = self._song.scenes[scene_index]
            scene.fire()

            return {"fired": True, "scene_name": scene.name, "scene_index": scene_index}
        except Exception as e:
            self.log_message("Error firing scene: " + str(e))
            raise
```

**Step 3: Add MCP tool**

```python
@mcp.tool()
async def fire_scene(ctx: Context, scene_index: int) -> str:
    """
    Fire a scene (trigger all clips in a row).

    Parameters:
    - scene_index: The index of the scene to fire
    """
    try:
        ableton = get_ableton_connection()
        result = await ableton.send_command_async("fire_scene", {"scene_index": scene_index})
        scene_name = result.get("scene_name", f"Scene {scene_index}")
        return f"Fired scene: {scene_name}"
    except Exception as e:
        logger.error(f"Error firing scene: {str(e)}")
        return f"Error firing scene: {str(e)}"
```

**Step 4: Verify and commit**

```bash
cd /Users/jdelsman/Projects/ableton-mcp/.worktrees/perf-and-features
python -m py_compile MCP_Server/server.py
python -m py_compile AbletonMCP_Remote_Script/__init__.py
git add MCP_Server/server.py AbletonMCP_Remote_Script/__init__.py
git commit -m "feat: add fire_scene command"
```

---

## Phase 3: Features - Group 2 (Track Property Setters)

### Task 12: Add Track Mute/Solo/Arm Setters

**Files:**
- Modify: `AbletonMCP_Remote_Script/__init__.py`
- Modify: `MCP_Server/server.py`

**Step 1: Add handlers in Remote Script**

Add to command routing:
```python
                        elif command_type == "set_track_mute":
                            track_index = params.get("track_index", 0)
                            muted = params.get("muted", False)
                            result = self._set_track_mute(track_index, muted)
                        elif command_type == "set_track_solo":
                            track_index = params.get("track_index", 0)
                            solo = params.get("solo", False)
                            result = self._set_track_solo(track_index, solo)
                        elif command_type == "set_track_arm":
                            track_index = params.get("track_index", 0)
                            armed = params.get("armed", False)
                            result = self._set_track_arm(track_index, armed)
```

**Step 2: Add implementation methods**

```python
    def _set_track_mute(self, track_index, muted):
        """Set track mute state"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            track = self._song.tracks[track_index]
            track.mute = muted
            return {"mute": track.mute, "track_name": track.name}
        except Exception as e:
            self.log_message("Error setting track mute: " + str(e))
            raise

    def _set_track_solo(self, track_index, solo):
        """Set track solo state"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            track = self._song.tracks[track_index]
            track.solo = solo
            return {"solo": track.solo, "track_name": track.name}
        except Exception as e:
            self.log_message("Error setting track solo: " + str(e))
            raise

    def _set_track_arm(self, track_index, armed):
        """Set track arm state"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            track = self._song.tracks[track_index]
            if track.can_be_armed:
                track.arm = armed
                return {"arm": track.arm, "track_name": track.name}
            else:
                return {"arm": False, "track_name": track.name, "message": "Track cannot be armed"}
        except Exception as e:
            self.log_message("Error setting track arm: " + str(e))
            raise
```

**Step 3: Add MCP tools**

```python
@mcp.tool()
async def set_track_mute(ctx: Context, track_index: int, muted: bool) -> str:
    """
    Mute or unmute a track.

    Parameters:
    - track_index: The index of the track
    - muted: True to mute, False to unmute
    """
    try:
        ableton = get_ableton_connection()
        result = await ableton.send_command_async("set_track_mute", {
            "track_index": track_index, "muted": muted
        })
        state = "muted" if result.get("mute") else "unmuted"
        return f"Track '{result.get('track_name')}' {state}"
    except Exception as e:
        logger.error(f"Error setting track mute: {str(e)}")
        return f"Error setting track mute: {str(e)}"

@mcp.tool()
async def set_track_solo(ctx: Context, track_index: int, solo: bool) -> str:
    """
    Solo or unsolo a track.

    Parameters:
    - track_index: The index of the track
    - solo: True to solo, False to unsolo
    """
    try:
        ableton = get_ableton_connection()
        result = await ableton.send_command_async("set_track_solo", {
            "track_index": track_index, "solo": solo
        })
        state = "soloed" if result.get("solo") else "unsoloed"
        return f"Track '{result.get('track_name')}' {state}"
    except Exception as e:
        logger.error(f"Error setting track solo: {str(e)}")
        return f"Error setting track solo: {str(e)}"

@mcp.tool()
async def set_track_arm(ctx: Context, track_index: int, armed: bool) -> str:
    """
    Arm or disarm a track for recording.

    Parameters:
    - track_index: The index of the track
    - armed: True to arm, False to disarm
    """
    try:
        ableton = get_ableton_connection()
        result = await ableton.send_command_async("set_track_arm", {
            "track_index": track_index, "armed": armed
        })
        if "message" in result:
            return result["message"]
        state = "armed" if result.get("arm") else "disarmed"
        return f"Track '{result.get('track_name')}' {state}"
    except Exception as e:
        logger.error(f"Error setting track arm: {str(e)}")
        return f"Error setting track arm: {str(e)}"
```

**Step 4: Verify and commit**

```bash
cd /Users/jdelsman/Projects/ableton-mcp/.worktrees/perf-and-features
python -m py_compile MCP_Server/server.py
python -m py_compile AbletonMCP_Remote_Script/__init__.py
git add MCP_Server/server.py AbletonMCP_Remote_Script/__init__.py
git commit -m "feat: add track mute/solo/arm setters"
```

---

### Task 13: Add Track Volume/Pan Setters

**Files:**
- Modify: `AbletonMCP_Remote_Script/__init__.py`
- Modify: `MCP_Server/server.py`

**Step 1: Add handlers in Remote Script**

```python
                        elif command_type == "set_track_volume":
                            track_index = params.get("track_index", 0)
                            volume = params.get("volume", 0.85)
                            result = self._set_track_volume(track_index, volume)
                        elif command_type == "set_track_panning":
                            track_index = params.get("track_index", 0)
                            pan = params.get("pan", 0.0)
                            result = self._set_track_panning(track_index, pan)
```

**Step 2: Add implementation methods**

```python
    def _set_track_volume(self, track_index, volume):
        """Set track volume (0.0 to 1.0)"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            track = self._song.tracks[track_index]
            # Clamp volume to valid range
            volume = max(0.0, min(1.0, volume))
            track.mixer_device.volume.value = volume
            return {"volume": track.mixer_device.volume.value, "track_name": track.name}
        except Exception as e:
            self.log_message("Error setting track volume: " + str(e))
            raise

    def _set_track_panning(self, track_index, pan):
        """Set track panning (-1.0 to 1.0)"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            track = self._song.tracks[track_index]
            # Clamp pan to valid range
            pan = max(-1.0, min(1.0, pan))
            track.mixer_device.panning.value = pan
            return {"panning": track.mixer_device.panning.value, "track_name": track.name}
        except Exception as e:
            self.log_message("Error setting track panning: " + str(e))
            raise
```

**Step 3: Add MCP tools**

```python
@mcp.tool()
async def set_track_volume(ctx: Context, track_index: int, volume: float) -> str:
    """
    Set track volume.

    Parameters:
    - track_index: The index of the track
    - volume: Volume level from 0.0 (silent) to 1.0 (full)
    """
    try:
        ableton = get_ableton_connection()
        result = await ableton.send_command_async("set_track_volume", {
            "track_index": track_index, "volume": volume
        })
        return f"Track '{result.get('track_name')}' volume set to {result.get('volume'):.2f}"
    except Exception as e:
        logger.error(f"Error setting track volume: {str(e)}")
        return f"Error setting track volume: {str(e)}"

@mcp.tool()
async def set_track_panning(ctx: Context, track_index: int, pan: float) -> str:
    """
    Set track panning.

    Parameters:
    - track_index: The index of the track
    - pan: Panning from -1.0 (left) to 1.0 (right), 0.0 is center
    """
    try:
        ableton = get_ableton_connection()
        result = await ableton.send_command_async("set_track_panning", {
            "track_index": track_index, "pan": pan
        })
        pan_val = result.get('panning', 0)
        if pan_val < -0.01:
            pos = f"{abs(pan_val):.0%} left"
        elif pan_val > 0.01:
            pos = f"{pan_val:.0%} right"
        else:
            pos = "center"
        return f"Track '{result.get('track_name')}' panned to {pos}"
    except Exception as e:
        logger.error(f"Error setting track panning: {str(e)}")
        return f"Error setting track panning: {str(e)}"
```

**Step 4: Verify and commit**

```bash
cd /Users/jdelsman/Projects/ableton-mcp/.worktrees/perf-and-features
python -m py_compile MCP_Server/server.py
python -m py_compile AbletonMCP_Remote_Script/__init__.py
git add MCP_Server/server.py AbletonMCP_Remote_Script/__init__.py
git commit -m "feat: add track volume/pan setters"
```

---

## Phase 4: Features - Group 3 (Data Retrieval)

### Task 14: Add Get Notes From Clip

**Files:**
- Modify: `AbletonMCP_Remote_Script/__init__.py`
- Modify: `MCP_Server/server.py`

**Step 1: Add handler in Remote Script command routing (non-modifying)**

Add to the non-modifying commands section:

```python
            elif command_type == "get_notes_from_clip":
                track_index = params.get("track_index", 0)
                clip_index = params.get("clip_index", 0)
                response["result"] = self._get_notes_from_clip(track_index, clip_index)
```

**Step 2: Add implementation method**

```python
    def _get_notes_from_clip(self, track_index, clip_index):
        """Get all notes from a clip"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]

            if clip_index < 0 or clip_index >= len(track.clip_slots):
                raise IndexError("Clip index out of range")

            clip_slot = track.clip_slots[clip_index]

            if not clip_slot.has_clip:
                raise Exception("No clip in slot")

            clip = clip_slot.clip

            # Get notes from the entire clip
            # get_notes(start_time, start_pitch, time_span, pitch_span)
            notes_tuple = clip.get_notes(0.0, 0, clip.length, 128)

            notes = []
            for note in notes_tuple:
                notes.append({
                    "pitch": note[0],
                    "start_time": note[1],
                    "duration": note[2],
                    "velocity": note[3],
                    "mute": note[4]
                })

            return {
                "clip_name": clip.name,
                "clip_length": clip.length,
                "note_count": len(notes),
                "notes": notes
            }
        except Exception as e:
            self.log_message("Error getting notes from clip: " + str(e))
            raise
```

**Step 3: Add MCP tool**

```python
@mcp.tool()
async def get_notes_from_clip(ctx: Context, track_index: int, clip_index: int) -> str:
    """
    Get all MIDI notes from a clip.

    Parameters:
    - track_index: The index of the track containing the clip
    - clip_index: The index of the clip slot containing the clip
    """
    try:
        ableton = get_ableton_connection()
        result = await ableton.send_command_async("get_notes_from_clip", {
            "track_index": track_index,
            "clip_index": clip_index
        })
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting notes from clip: {str(e)}")
        return f"Error getting notes from clip: {str(e)}"
```

**Step 4: Verify and commit**

```bash
cd /Users/jdelsman/Projects/ableton-mcp/.worktrees/perf-and-features
python -m py_compile MCP_Server/server.py
python -m py_compile AbletonMCP_Remote_Script/__init__.py
git add MCP_Server/server.py AbletonMCP_Remote_Script/__init__.py
git commit -m "feat: add get_notes_from_clip command"
```

---

### Task 15: Add Get Scene Info

**Files:**
- Modify: `AbletonMCP_Remote_Script/__init__.py`
- Modify: `MCP_Server/server.py`

**Step 1: Add handler in Remote Script command routing (non-modifying)**

```python
            elif command_type == "get_scene_info":
                scene_index = params.get("scene_index", 0)
                response["result"] = self._get_scene_info(scene_index)
```

**Step 2: Add implementation method**

```python
    def _get_scene_info(self, scene_index):
        """Get information about a scene"""
        try:
            if scene_index < 0 or scene_index >= len(self._song.scenes):
                raise IndexError("Scene index out of range")

            scene = self._song.scenes[scene_index]

            # Count clips in this scene
            clip_count = 0
            clips = []
            for track_index, track in enumerate(self._song.tracks):
                if scene_index < len(track.clip_slots):
                    slot = track.clip_slots[scene_index]
                    if slot.has_clip:
                        clip_count += 1
                        clips.append({
                            "track_index": track_index,
                            "track_name": track.name,
                            "clip_name": slot.clip.name
                        })

            return {
                "index": scene_index,
                "name": scene.name,
                "tempo": scene.tempo if hasattr(scene, 'tempo') else None,
                "color": scene.color if hasattr(scene, 'color') else None,
                "clip_count": clip_count,
                "clips": clips
            }
        except Exception as e:
            self.log_message("Error getting scene info: " + str(e))
            raise
```

**Step 3: Add MCP tool**

```python
@mcp.tool()
async def get_scene_info(ctx: Context, scene_index: int) -> str:
    """
    Get information about a scene.

    Parameters:
    - scene_index: The index of the scene
    """
    try:
        ableton = get_ableton_connection()
        result = await ableton.send_command_async("get_scene_info", {"scene_index": scene_index})
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting scene info: {str(e)}")
        return f"Error getting scene info: {str(e)}"
```

**Step 4: Verify and commit**

```bash
cd /Users/jdelsman/Projects/ableton-mcp/.worktrees/perf-and-features
python -m py_compile MCP_Server/server.py
python -m py_compile AbletonMCP_Remote_Script/__init__.py
git add MCP_Server/server.py AbletonMCP_Remote_Script/__init__.py
git commit -m "feat: add get_scene_info command"
```

---

## Final Task: Update Command List and Documentation

### Task 16: Update is_modifying_command List

**Files:**
- Modify: `MCP_Server/server.py`

**Step 1: Update the command list in send_command**

Update the `is_modifying_command` check to include all new modifying commands:

```python
        is_modifying_command = command_type in [
            "create_midi_track", "create_audio_track", "set_track_name",
            "create_clip", "add_notes_to_clip", "set_clip_name",
            "set_tempo", "fire_clip", "stop_clip", "set_device_parameter",
            "start_playback", "stop_playback", "load_instrument_or_effect",
            "undo", "redo", "delete_track", "delete_clip",
            "set_metronome", "fire_scene",
            "set_track_mute", "set_track_solo", "set_track_arm",
            "set_track_volume", "set_track_panning"
        ]
```

**Step 2: Verify and commit**

```bash
cd /Users/jdelsman/Projects/ableton-mcp/.worktrees/perf-and-features
python -m py_compile MCP_Server/server.py
git add MCP_Server/server.py
git commit -m "chore: update is_modifying_command list with new commands"
```

---

## Summary

| Phase | Tasks | Features Added |
|-------|-------|----------------|
| 1 | 1-5 | Remove delays, ping, health check, browser cache, async |
| 2 | 6-11 | undo, redo, delete_track, create_audio_track, delete_clip, set_metronome, fire_scene |
| 3 | 12-13 | set_track_mute/solo/arm, set_track_volume/panning |
| 4 | 14-15 | get_notes_from_clip, get_scene_info |
| Final | 16 | Update command lists |

Total: 16 tasks, ~20 commits
