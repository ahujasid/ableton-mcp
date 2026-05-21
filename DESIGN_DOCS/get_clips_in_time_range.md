# Feature: `get_clips_in_time_range`

## Background & Problem Statement

The Ableton Live Object Model (LOM) does not expose multi-clip selection state. When a user
selects multiple clips in the Arrangement View, the Remote Script API (`song.view.detail_clip`)
only ever returns a single focused clip — or `None` if focus is ambiguous. This means the MCP
server has no way to reflect the user's visual multi-selection.

This design doc describes a lightweight, two-step workflow that allows an AI assistant to work
with a user-defined region of the Arrangement without incurring high token costs.

---

## Design Goals

- Allow the AI to discover which clips exist within a time window, across all (or a subset of) tracks.
- Keep token costs low by **returning metadata only** — no notes — in this call.
- Let the user (or AI) then selectively fetch notes for only the clips they care about, using the
  existing `get_arrangement_clip_notes` tool.
- Keep the API surface small and composable; avoid building a monolithic "get everything" tool.

---

## Non-Goals

- This tool will **not** return MIDI note data. Notes are fetched separately.
- This tool will **not** attempt to replicate Ableton's native multi-select highlight state.
- This tool will **not** modify clips.

---

## Proposed API

### Tool: `get_clips_in_time_range`

```
get_clips_in_time_range(
    start_time: float,
    end_time: float,
    track_indices: list[int]
) -> str  # JSON
```

#### Parameters

| Parameter       | Type        | Default  | Description |
|-----------------|-------------|----------|-------------|
| `start_time`    | `float`     | required | Start of the time window, in beats. |
| `end_time`      | `float`     | required | End of the time window, in beats. |
| `track_indices` | `list[int]` | required | Explicit list of track indices to scan to prevent scanning overhead. |

#### Selection Criterion

A clip is included in the result if it **overlaps** the `[start_time, end_time]` window.
Overlap is calculated as: `clip.start_time < end_time AND clip.end_time > start_time`.

> **Note:** The LOM exposes `clip.end_time` directly. Do **not** use `clip.start_time + clip.length`
> as a substitute — use `clip.end_time` directly, which is what the implementation does.

#### Response Schema

```json
{
  "start_time": 0.0,
  "end_time": 32.0,
  "clip_count": 4,
  "clips": [
    {
      "track_name": "Violin I",
      "track_index": 3,
      "clip_index": 0,
      "clip_name": "Theme A",
      "start_time": 0.0,
      "end_time": 16.0,
      "length": 16.0,
      "is_midi_clip": true,
      "is_audio_clip": false,
      "color": 16752896
    }
  ]
}
```

No `notes` field is ever present in this response.

---

## Token Cost Analysis

| Scenario                           | Approx. tokens |
|------------------------------------|----------------|
| 1 clip entry in response           | ~30            |
| 10 clips across 5 tracks           | ~300           |
| 50 clips (large orchestral project)| ~1,500         |
| Notes for a single 32-bar MIDI clip| ~2,000–10,000+ |

By separating metadata from notes, the user can review a region with 20+ clips for ~600 tokens,
then fetch notes only for the 2–3 clips they actually need to work on.

---

## Two-Step Workflow (Recommended Usage Pattern)

```
Step 1 — Cheap scan:
  get_clips_in_time_range(start_time=0, end_time=32, track_indices=[3, 4, 5])
  → Returns metadata for all matching clips. User or AI identifies which clips are relevant.

Step 2 — Targeted fetch (existing tool, unchanged):
  get_arrangement_clip_notes(track_index=3, clip_index=0)
  → Returns full note data for only the clip(s) of interest.
```

---

## Alternatives Considered

### A. `get_all_arrangement_clips` (no time filter)
Returns every clip on every track in the project. Rejected because for large orchestral projects
this could return hundreds of clip metadata entries, and gives the AI no way to scope its work
to the region the user is actually looking at.

### B. `get_clips_in_time_range` with notes included
Included notes inline. Rejected because a single 32-bar MIDI clip with dense notes can consume
thousands of tokens; returning notes for 10 clips simultaneously would be prohibitively expensive.

### C. Using Ableton's native multi-selection
The LOM does not expose this. `song.view.detail_clip` only returns one clip, and returns `None`
when the selection is ambiguous. See `selected_clips_feature.md` for full investigation.

---

## Implementation Details

### 1. `AbletonMCP_Remote_Script/__init__.py`

**`_get_clips_in_time_range(start_time, end_time, track_indices)`**

- Casts `start_time` and `end_time` to `float`; validates `track_indices` is a `list`.
- Iterates over the provided `track_indices`, skipping indices that are out of bounds.
- For each track, iterates `track.arrangement_clips` inside a `try...except Exception` block
  (see Critical LOM Gotcha below).
- Checks overlap: `clip.start_time < end_time and clip.end_time > start_time`.
- For matching clips, collects: `track_name`, `track_index`, `clip_index`, `clip_name`,
  `start_time`, `end_time`, `length`, `is_midi_clip`, `is_audio_clip`,
  and `color` via `getattr(clip, "color", None)` for version safety.
- Returns a dict with `clips`, `clip_count`, `start_time`, `end_time`.

**Routing in `_process_command()`**

- `"get_clips_in_time_range"` is routed **inline** (not via `main_thread_task`) — it is a
  read-only operation, consistent with `get_arrangement_clips`.

### 2. `MCP_Server/server.py`

- Registered with `@mcp.tool()` as a non-modifying command (no delay applied).
- Validates and forwards `start_time`, `end_time`, and `track_indices` to the Remote Script.
- Returns the JSON-serialised result string directly.

---

## Critical LOM Gotcha: `RuntimeError` on Group/Return/Master Tracks

### Problem
In Ableton's LOM, accessing `arrangement_clips` on a Group, Return, or Master track raises a
**`RuntimeError`** (not an `AttributeError`) with the message:
> `"Main, Group and Return Tracks have no arrangement clips"`

Python's `hasattr(track, 'arrangement_clips')` internally calls `getattr` and only suppresses
`AttributeError`. Because the LOM raises `RuntimeError`, `hasattr` does **not** suppress it —
the exception propagates and crashes the entire scan.

### Resolution
**Do not use `hasattr` to guard `arrangement_clips` access.** Instead, wrap the
`track.arrangement_clips` loop directly in `try...except Exception as track_err:`, so any LOM
`RuntimeError` is caught, logged, and the track is silently skipped:

```python
track = tracks[track_idx]
try:
    for i, clip in enumerate(track.arrangement_clips):
        ...
except Exception as track_err:
    self.log_message("Skipping track %d due to LOM error: %s" % (track_idx, str(track_err)))
    continue
```

### Bytecode Caching Note
Ableton caches compiled Python bytecode in memory. Toggling a Control Surface script off/on in
Preferences **does not** force a re-import from disk — it re-instantiates the cached module.
To force a full reload of a modified Remote Script, **Ableton must be fully quit and relaunched**.

---

## Installation

The active Remote Script is loaded from the User Library (not the app bundle, which is wiped on updates):

```
/Users/harrison/Music/Ableton/User Library/Remote Scripts/AbletonMCP/__init__.py
```

Copies are also maintained at:
```
/Users/harrison/Library/Preferences/Ableton/Live 12.3/User Remote Scripts/AbletonMCP/
/Users/harrison/Library/Preferences/Ableton/Live 12.4.5b1/User Remote Scripts/AbletonMCP/
```

> **Never install inside the `.app` bundle** (`/Applications/Ableton Live XX.app/...`).
> Launching or updating Live can silently wipe this directory.

---

## Design Decisions (Resolved)

1. **Should `track_indices` default to scanning all tracks, or require explicit indices?**
   **Decision:** Explicit list required. Prevents unnecessary overhead and avoids scanning an
   entire orchestral project when only a few tracks are needed.

2. **Should clip colour be included in the metadata response?**
   **Decision:** Yes. `clip.color` is returned as an integer via `getattr(clip, "color", None)`.
   This lets the AI reason about color-coded groupings and align with what the user sees in the UI.

3. **Should the tool include return tracks or the master track?**
   **Decision:** Skip them. They raise a `RuntimeError` on `arrangement_clips` access and contain
   no MIDI arrangement clips. They are silently skipped via the `try...except` guard.

---

## Verification

Verified end-to-end on 2026-05-21 against Ableton Live 12.4.5b1 with a string ensemble project
(6 tracks: 1 Group + 5 MIDI instrument tracks: Vln 1, Vln 2, Vla, Vlc, Vlb).

**Test command:**
```bash
.venv/bin/python scratch/test_time_range.py 0 32 "[0, 1, 2, 3, 4, 5]"
```

**Result:** 5 clips returned correctly. The Group track (index 0) was silently skipped without
error. All metadata fields (`track_name`, `track_index`, `clip_index`, `clip_name`,
`start_time`, `end_time`, `length`, `is_midi_clip`, `is_audio_clip`, `color`) were present and
correct. Overlap logic confirmed: clips spanning beats 0–64 were correctly included in a 0–32
scan window.

---

## Status
**Shipped.**

---

## Related Docs

- [`selected_clips_feature.md`](./selected_clips_feature.md) — original investigation into
  single-clip selection and the LOM limitation.
- [`arrangement_clips.md`](./arrangement_clips.md) — prior design for arrangement clip access tools.
