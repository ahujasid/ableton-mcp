# Integration test — get_notes_from_clip against a live Set

The unit tests (`tests/`) mock Ableton and prove the server's logic. This
procedure proves the part they can't: that the real Live Object Model calls
(`get_notes_extended`, `is_midi_clip`, `set_notes`) behave as the handler
assumes. Run it once against a real Set; it's pass/fail, not vibes.

## Prerequisites

- Ableton Live open with the **patched** AbletonMCP Remote Script loaded
  (control surface selected; if notes read back at all, you're loaded).
- The MCP server running from the patched clone, connected to your assistant.
- One MIDI track with an **empty clip slot** you don't mind using as scratch.
  The steps below assume track index `T` and empty slot index `S` — substitute
  your own. (Track/slot indices are 0-based.)

## Read-back quirks to expect (NOT failures)

- **Order isn't preserved.** Live may return notes sorted by time/pitch, not in
  the order you wrote them. Compare as an unordered set of notes.
- **Ints come back as floats.** Velocity `100` may read as `100.0`; same for
  start/duration. Compare numerically, not by type.
- **Extra fields appear.** Each read note may carry `note_id`, `probability`,
  `velocity_deviation`, `release_velocity`. Expected — ignore them. They ride
  back through `add_notes_to_clip` harmlessly.

---

## Step 1 — create an empty clip and read it (zero notes)

Ask the assistant to create a 4-beat MIDI clip at track `T`, slot `S`, then
read its notes.

**Expected:** read reports the clip name and `0 note(s)`, notes list `[]`.
**Pass:** no error; empty note list on a freshly created clip.

## Step 2 — write a known pattern, then read it back

Write exactly these three notes to track `T`, slot `S`:

| pitch | start_time | duration | velocity | mute  |
|------:|-----------:|---------:|---------:|-------|
| 36    | 0.0        | 0.25     | 100      | false |
| 38    | 1.0        | 0.25     | 90       | false |
| 42    | 0.5        | 0.25     | 80       | true  |

Then read the clip.

**Expected:** read reports `3 note(s)`. Ignoring order/float/extra-field quirks
above, the three notes match the table exactly — including `mute: true` on
pitch 42 and the three distinct velocities.
**Pass:** all three notes present with correct pitch/start/duration/velocity/
mute. This is the core proof: what Live returns equals what you wrote.

## Step 3 — read → modify → clear → write → read (the real replace loop)

Take the notes from Step 2 and transpose every pitch up 7 semitones
(36→43, 38→45, 42→49). Then, in order: **clear** the clip
(`clear_notes_from_clip`), **write** the transposed notes
(`add_notes_to_clip`), and read again.

**Expected:** read reports exactly **3** notes — pitches `43, 45, 49`, other
fields unchanged.
**Pass:** the clip holds *only* the modified notes.

> Why the clear step matters: `add_notes_to_clip` is **additive** — it appends,
> it doesn't replace. Skip the clear and you'd read back 6 notes (the original
> three plus the transposed three). Clearing first is what turns "add" into a
> genuine read → modify → write loop. This is exactly the gap
> `clear_notes_from_clip` exists to close.

## Step 4 — error path: empty slot

Read notes from a slot you know is **empty** (no clip).

**Expected:** an error message containing `No clip in slot` (not a crash, not
an empty success).
**Pass:** clean, descriptive error.

## Step 5 — error path: audio clip (optional)

If you have an audio track with a clip, read its notes.

**Expected:** an error containing `not a MIDI clip`.
**Pass:** clean, descriptive error — the `is_midi_clip` guard works.

> `clear_notes_from_clip` shares the same guards (`No clip in slot`,
> `not a MIDI clip`), so Steps 4–5 cover it too; no separate steps needed.

---

## Cleanup

Delete the scratch clip (or leave it — it's disposable). Nothing else to undo.

## Recording the result for the PR

Note Live version, OS, and which steps passed, e.g.:

> Verified on Live 12.4.2 / macOS: steps 1–5 pass. Notes round-trip exactly
> (order differs and ints return as floats, as documented).

That line in the PR tells a reviewer the LOM half was checked on real hardware,
which the unit tests can't assert.
