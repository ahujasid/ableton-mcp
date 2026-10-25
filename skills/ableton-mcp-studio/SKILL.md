---
name: ableton-mcp-studio
description: Use when making, arranging, editing or mixing music in Ableton Live through the AbletonMCP tools: setup checks, the build pipeline, beat maths, tool quirks and handing listening calls to the user.
---

# Ableton MCP studio

You drive Ableton Live through our AbletonMCP fork (`standard-reference/ableton-mcp`, branch `studio-upgrades`, Remote Script `1.9.0+studio`). It lets you:
- write and transform notes;
- build the arrangement;
- add and set devices by name on any track, return or the master;
- draw clip automation and use the groove pool;
- render sections and measure them against reference tracks.

You still can't listen in real time. Work as a loop: **set → render → measure → compare → ask**. The user's ears have the final say.

Use alongside:
- `music-production-craft` for what to write and why;
- `bell-curve-breakers` to keep things from sounding average;
- any `genre-*` or `colour-*` skill that matches the brief.

## 0. Before the first edit

1. Load the Ableton tools in one ToolSearch `select:` call. Their names end in `AbletonMCP__toolname`.
2. Call `get_remote_script_info` and expect `1.9.0+studio`.
   - If it shows an `install_note`, or an older version, the server has already copied the new script into Live's User Library. Ask the user to restart Ableton Live.
   - If the server itself is old (tools like `render_section` are missing), the Claude Desktop config should run:

     `uvx --refresh-package ableton-mcp --from https://github.com/standard-reference/ableton-mcp/archive/refs/heads/studio-upgrades.zip ableton-mcp`

     After changing it, restart Claude Desktop, then Live.
3. Read the set:
   - `get_session_info` lists tracks, returns and the master with their devices.
   - `get_mixer_overview` gives levels, pans and sends in dB.
   - Indices shift when tracks are added or deleted, and the user edits by hand, so re-read before editing.
4. Telemetry and dataset recording are off in this fork, and the dataset tools are hidden. Leave them off. If they ever reappear, only call `set_dataset_consent` after the user has answered in their own words.

## 1. Units and conventions

| Thing | Convention |
|---|---|
| Pitch | MIDI 60 = C3 in Live's naming (36 = C1, 48 = C2, 72 = C4). Use Live's names with the user. |
| Time | Beats. In 4/4, bar n starts at beat (n − 1) × 4: bar 9 = 32, bar 17 = 64, bar 33 = 128, bar 65 = 256. |
| Notes | `{pitch, start_time, duration, velocity 1–127, mute}` |
| ms → beats | beats = ms × BPM / 60000. At 125 BPM, 0.01 beat ≈ 4.8 ms and a 16th = 0.25 beat = 120 ms. |
| Swing (MPC/Linn scale: 50 = straight, 66 = triplet) | The off-16th moves by d = (S − 50)/100 × 0.5 beat: 52 → 0.01, 54 → 0.02, 56 → 0.03, **58 → 0.04**, 62 → 0.06, 66 → 0.08. Linn: 54 % loosens the feel without sounding like swing, and 62 % can feel looser than a perfect 66 at slow tempos. House rule of thumb: 56–58 % reads as loose and natural. |
| Microtiming | Systematic and per role, the **same every bar**. Never random noise; see the defaults below. |
| Velocity | Accent maps, not noise. 16ths across a beat, e.g. 100 / 62 / 84 / 58. Ghost notes 20–45. |
| Articulation | Set durations deliberately: 0.1–0.2 beat for funk bass, plucks and stabs; legato = up to the next note minus about 0.02. |

Microtiming defaults:
- Kick and the quarter grid: 0.
- Clap or snare: +0.010 to +0.025 beat for laid-back.
- Off-beat open hat: 0 to −0.008 for urgency, or +0.010 for lazy.
- Bass: 0 (locked to the kick) or +0.01 to +0.02 (in the pocket).
- Random jitter: at most ±0.004 beat, and never on the kick or the bass note under it.

Listening studies find quantised parts groove about as well as competent human timing, and exaggerated timing grooves worse (Senn et al. 2016; Datseris et al. 2019).

Apply swing, offsets and accents with `transform_clip_notes`. Its swing is absolute, so re-applying it doesn't stack. Alternatively, use a groove from the pool (section 2F).

## 2. Build pipeline

**A. Foundation**
- `set_tempo`.
- `set_song_scale` (root plus Live's scale name, e.g. "Dorian") so scale-aware devices follow.
- MIDI tracks named by role.
- Instruments: browse with `get_browser_tree` / `get_browser_items_at_path`. Save big outputs to a file and filter them in code. `load_instrument_or_effect` on a track that already has an instrument replaces it. Clip files (.alc) don't load this way.
- Drums: `load_drum_kit`, then **always** `get_drum_pads`, and write only to the notes it lists.
- Effects: `add_device` by name ("EQ Eight", "Compressor", "Saturator", "Auto Filter", "Echo", "Reverb", "Utility", "Limiter"). It works on tracks, returns (`track_type="return"`) and the master.
- Shared space: `create_return_track`, then `add_device` on that return, then sends via `set_track_mixer`.

**B. Parts as Session clips.** Use one slot per variant (0 = A, 1 = B, 2 = break or fill).
- Write one bar and tile it with `add_notes_to_clip(repeat_every, repeat_count)`.
- Shape timing, accents, articulation, transposition or scale snapping with `transform_clip_notes`. Pass `target_clip_index` to write a variant next to the original for A/B.
- For manual edits: `get_clip_notes`, edit, `clear_notes_from_clip`, then `add_notes_to_clip`. Writes are additive, so always clear before rewriting.
- Name clips by part and role ("Bass A groove", "Keys B break").
- Before a big rewrite, `copy_clip` the original into a spare slot as a backup.

**C. Review before anyone listens.**
- `review_clip` on every part gives flat velocity, timing profile, low-interval mud, chord names, bar-to-bar variation and syncopation, each with a fix.
- `forecast_masking` on the parts that play together finds low and low-mid clashes from the notes.
- Fix the flags first. It's cheaper than a render.

**D. Arrangement.**
- Write the section map (bars, start beat, clip per track). Show it to the user if the structure is new.
- `fill_arrangement` per track per section.
- To redo a range, `delete_arrangement_clips` before re-filling it. Arrangement copies don't follow later Session edits.
- `stop_playback`, then `create_locator` per section.
- After any `fire_clip`, call `back_to_arrangement`, or those tracks stay on their Session clips.
- Finish with `switch_to_arrangement_view`.

**E. Movement: `write_clip_automation`.**
- Envelopes live in Session clips and travel with them.
- A move longer than the clip (an 8-bar sweep) needs a clip that long: make a section-length clip for that part.
- Points take display units, e.g. `[{"time":0,"display":"300 Hz"},{"time":28,"display":"8 kHz"}]`.
- Curves:
  - `exp`: filter openings that feel even.
  - `s_curve`: swells.
  - `step`: throws and switches.
- Arrangement clips can't take envelope writes, and other projects report that envelope behaviour on copy differs between Live versions. The first time in a set, render the section and check the move is there (e.g. high bands rising through a sweep).
- Device parameters are otherwise global, so use clips or separate tracks for per-section sound changes.

**F. Groove.**
- `load_groove`, then `assign_groove` per clip. Live 11+ names its swing grooves "Swing MPC 3000 16ths 54 / 57 / 61 / 64 / 68 / 71 / 74" (Core Library > Grooves > Swing > MPC) and "Swing 16ths 52 / 54 / 57 / 59 / 61 / 64 / 66 …" (Basic). There is no 56 or 58: use `transform_clip_notes` swing for exact values.
- `set_groove` sets timing, velocity and random amounts; keep random at 0 for dance music.
- Different grooves on different roles give swing contrast.
- Grooves are non-destructive. Transform swing is destructive but exact.

**G. Mix.**
- `set_track_mixer` in dB, then read back the display.
- Sidechain: `add_device` Compressor on the bass or pads, then `set_sidechain` from the kick, then `set_device_parameters`, e.g. `{"name":"Threshold","display":"-24 dB"}`, `{"name":"Ratio","display":"4"}` (Live shows e.g. "4.00 : 1"; the number is what gets matched, but check the format with `get_device_parameters` first), `{"name":"Release","display":"120 ms"}`.
- `get_device_parameters` shows each parameter's display string.

**H. Audition and measure.** For a quick listen, call `set_arrangement_loop` over the section and `start_playback`, then ask (section 4). For measurement, see section 3. Stop playback before structural edits.

## 3. The measurement loop (ears)

**Render.** `render_section(start_bar, bars, label)` records the master in real time onto a helper "MCP Render" track, which is muted afterwards so takes never play in the song. The user's loop, metronome, arms, solos, playhead and selection are restored.
- It takes as long as the music: 8 bars at 125 BPM is about 15 s plus preroll, plus a few seconds the first time while Live sets up the helper track's routing.
- Keep renders to 16 bars or fewer. Longer ones return a job for `get_render_result`.
- For stems, use `solo_tracks`, e.g. kick and bass for a low-end check.

**What the report contains.**
- Integrated LUFS, true peak, loudness range and crest factor.
- Band and octave balance, measured relative to the total so it doesn't depend on loudness.
- Stereo width per band and a low-end mono check.
- Measured swing per band and the kick's grid offset.
- Key candidates and chords per bar.
- Plain-English warnings.

**References.**
- Ask the user for 1–3 reference files on their computer.
- Run `analyze_audio_file(path, label, start_seconds, end_seconds, bpm, downbeat_seconds)` on the comparable section, e.g. the reference's drop.
- Compare like with like (drop vs drop) over 8–16 bars.

**The loop.**
1. Render the same window every time.
2. `compare_audio("drop-v2", "ref-four")` lists only differences above audible thresholds.
3. Change one thing.
4. Re-render under a new label.
5. `compare_audio("drop-v3", "drop-v2")` confirms the change did what you meant.
6. Ask the user.

**How far to trust it.**
- Numbers are evidence, not verdicts.
- Key detection on electronic dance music is roughly 60–70 % accurate (Faraldo et al. 2016), and chords per bar are approximate.
- Render loudness depends on whatever is on the master.
- Don't chase a reference's numbers past what the user likes.
- Never claim tone from a parameter value alone ("2 kHz adds warmth"). Set it, render, measure, ask.

## 4. Borrowing the user's ears

- Ask forced-choice questions with one variable, a bar number and a reference anchor: "Bar 33: A = clap +8 ms, B = clap on grid. Which sits closer to the reference?"
- Put variants in adjacent slots or render them under two labels. For device settings, Live 12.3's Device A/B is the user's quickest comparison.
- Report each change as: bars → track → change → expected effect → measured evidence.
- The user's verdict beats every rule here. Keep track of what they liked and rejected.

## 5. Still not possible through the tools

None of these can be done through the tools; say so and give the user the manual step.
- **Arrangement automation lanes:** use Session-clip envelopes instead.
- **Pitch bend and MPE:** use short grace notes, or an instrument's own glide.
- **Time-signature markers:** Live's bar lines are only visual. Shifting later clips by 2 beats makes an audible 6/4 bar; track the offset in your beat maths.
- **Tuning systems:** the user loads them from the browser's Tunings. They're stored with the Set, and each MIDI track has a Bypass Tuning switch.
- **Freeze, flatten and final export:** renders are for measurement.
- **Stem separation:** Live 12.3+ Suite, done by the user. Useful for reference forensics and self-sampling.

**Samples:**
1. Splice (when connected and subscribed): `describe_a_sound` / `prompt_to_stack`, then `download_asset`. Check where downloads land before importing.
2. `create_audio_clip` on an audio track, with a path on the user's computer.
3. `set_clip_properties` for pitch, warp mode and gain.

**Audio that must play exactly as recorded** (stems, reference mixes). Live auto-warps long files on import and moves each clip's start marker to the first transient it finds, which differs from file to file. Turning warping off keeps that offset, so stems placed at the same beat start at different points in their files (0–2.6 s apart in one set) and play smeared, like an echo or a delay. For every such clip:
1. `create_audio_clip`, then `set_clip_properties` `{"warping": false}`.
2. In a separate call, `{"start_marker": 0, "loop_start": 0}`. Unwarped markers are in seconds.
3. `duplicate_to_arrangement`. The copy can take a warp-based length (half the file, say), so on the Arrangement clip (`arrangement: true`) also set `start_marker`/`loop_start` to 0 and `end_marker`/`loop_end` to the file's length in seconds.
4. Check: in `get_session_snapshot(include_notes=false, include_params=false)` every clip should show `loop_start` 0, and in `get_arrangement_clips` every length should equal the file's seconds × BPM / 60. Save the snapshot to a file and filter it in code; it's large.

Keep a running section map and track list in your notes, but re-read the set instead of trusting them once the user has touched Live.
