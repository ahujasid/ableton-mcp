# Mashup Production Workflow

A collaborative journey between human creativity and AI-assisted technical execution.

---

## Philosophy

**You (Human):** Creative direction, final decisions, ears on the mix, artistic vision
**LLM (Assistant):** Technical execution, analysis, knowledge, insight, creative suggestions

The best mashups come from this partnership. You bring the vision of what songs could work together and make the creative calls. The LLM handles the tedious technical work, provides data-driven insights, and offers creative sparks you might not have considered.

---

## Prerequisites

- Ableton Live 12 (with AbletonMCP remote script installed and running)
- MCP server connected
- Source audio files ready:
  - Instrumental track (or full song you'll use instrumentally)
  - Vocal track (isolated acapella preferred)

---

## Phase 1: Discovery & Analysis

*Goal: Understand both source tracks deeply before making any arrangement decisions.*

### 1.1 Initial Conversation

**You:** Share your mashup concept with the LLM. What drew you to combine these tracks? What's the vibe you're going for?

**LLM:** Asks clarifying questions about your vision, mood, and any reference mashups you admire.

### 1.2 Discover True BPM of Both Tracks

```
Tools: analyze_song_structure
```

**Important:** Don't trust internet databases or metadata - they're often wrong! Always analyze the actual audio to get the true BPM.

**LLM actions:**
1. `analyze_song_structure(instrumental_path)` - Gets detected BPM, sections, beat grid
2. `analyze_song_structure(vocal_path)` - Same for vocals (may need the original song if acapella detection fails)

**Common BPM issues:**
- Half-time detection: 140 BPM track detected as 70 BPM (use `target_bpm=140`)
- Double-time detection: 85 BPM track detected as 170 BPM (use `target_bpm=85`)
- Tempo drift: Live recordings may vary ±2 BPM throughout

**You:** Confirm the detected tempos make sense. If the instrumental is 170 BPM and vocals are 85 BPM, that's a 2:1 ratio - workable!

### 1.3 Deep Analysis of Both Tracks

```
Tools: analyze_song_structure, analyze_audio_describe, analyze_vocal_onsets
```

**Important:** `analyze_audio_describe` is how the LLM actually "hears" the music. Without it, there's no creative insight - just numbers. Always call it for both tracks. Combine all questions into one call per track to minimize cost.

**LLM actions:**

1. `analyze_song_structure(instrumental_path, target_bpm=X)` - BPM, sections, beat grid, **and key** (key detection is free/local)

2. `analyze_song_structure(vocal_path, target_bpm=X)` - Same for vocals

3. `analyze_audio_describe(instrumental_path, "Listen to this instrumental and analyze:
   1. What's the groove feel - tight/quantized, laid-back behind the beat, or pushed ahead?
   2. Describe the energy arc through the song - where does it build, peak, drop?
   3. What frequencies dominate each section (bass-heavy, bright, mid-focused)?
   4. What's the mood, vibe, and emotional character?
   5. What kind of vocals would complement this track?
   6. Any production issues or notable characteristics?")`

4. `analyze_audio_describe(vocal_path, "Listen to these vocals and analyze:
   1. What's the rhythmic feel - tight and quantized, laid back behind the beat, or pushed ahead?
   2. What's the energy and emotional character throughout?
   3. Which sections are most powerful/impactful (verses, chorus, hook)?
   4. What frequency range do the vocals occupy?
   5. Any issues with the recording (sibilance, noise, phase problems)?
   6. What kind of instrumental would complement these vocals?")`

5. `analyze_vocal_onsets(vocal_path, bpm=X)` - Precise onset positions for timing alignment later

**What you learn:**
- **BPM:** True tempo of both tracks (not from unreliable databases)
- **Key:** Musical key with confidence score and alternatives
- **Structure:** Section boundaries (intro, verse, chorus, etc.)
- **Groove:** Timing feel of each track (crucial for alignment decisions)
- **Energy:** Where each track builds, peaks, drops
- **Character:** Mood, vibe, emotional tone
- **Issues:** Any problems that might affect the mashup
- **Creative direction:** AI suggestions for pairing

**Key compatibility quick reference:**
| Relationship | Example | Compatibility |
|--------------|---------|---------------|
| Same key | Both in Am | Perfect |
| Relative major/minor | Am + C major | Excellent |
| Perfect 5th apart | Am + Em | Good |
| Semitone apart | Am + Bbm | Needs pitch shift |

**You:** Review the analysis. Do the keys work? Do the grooves match or need alignment?

### 1.4 Compatibility Assessment

**You:** Review all analysis. Do the keys work? Do the energies complement each other? Which vocal sections might work over which instrumental sections?

**LLM:** Synthesizes the analysis into creative suggestions:
- "The vocal chorus is in A minor with high energy - it could work over the instrumental drop (G minor) with a +2 semitone pitch shift"
- "The verse vocals are sparse and laid-back - they'd contrast nicely with the busy instrumental verse"
- "Both tracks have laid-back grooves (+30-40ms behind grid) - timing alignment should be smooth"

**Decision point:** You decide if these tracks can work together and sketch out the rough arrangement.

---

## Phase 2: Session Setup

*Goal: Create the Ableton session structure for your mashup.*

### 2.1 Set Session Tempo

```
Tools: set_tempo, get_session_info
```

**You:** Confirm the target BPM (usually the instrumental's tempo, unless you're doing a tempo change mashup)

**LLM actions:**
1. `set_tempo(bpm)` - Sets session tempo
2. `get_session_info()` - Confirms tempo is set

### 2.2 Create Track Structure

```
Tools: create_audio_track, create_midi_track, set_track_name
```

**LLM actions:**
```
Track 0: "INSTRUMENTAL"   [Audio] - Main instrumental
Track 1: "DRUMS_REF"      [MIDI]  - Extracted drum MIDI for groove reference
Track 2: "VOCALS"         [Audio] - Vocal clips
Track 3: "VOCAL_RHYTHM"   [MIDI]  - Extracted vocal rhythm for alignment
Track 4: "STRUCTURE"      [MIDI]  - Section annotations
```

1. `create_audio_track()` and `set_track_name(0, "INSTRUMENTAL")`
2. `create_midi_track()` and `set_track_name(1, "DRUMS_REF")`
3. `create_audio_track()` and `set_track_name(2, "VOCALS")`
4. `create_midi_track()` and `set_track_name(3, "VOCAL_RHYTHM")`
5. `create_midi_track()` and `set_track_name(4, "STRUCTURE")`

### 2.3 Import Audio (Manual Step)

**You:** Drag the instrumental and vocal files onto their respective tracks in Ableton's arrangement view.

*Note: File import isn't available via API - this is one of the few manual steps.*

**LLM:** Confirms tracks are populated by checking `get_arrangement_clips(0)` and `get_arrangement_clips(2)`.

### 2.4 Extract Drum MIDI from Instrumental

```
Tools: vocal_to_midi (works on any audio for onset detection)
```

**Why this matters:** The drum hits in the instrumental define the groove. We need these as MIDI to compare against vocal timing.

**LLM actions:**
1. `vocal_to_midi(instrumental_path, "/tmp/drums.mid", bpm=X, create_track=False)` - Extract rhythmic onsets
2. Add the resulting MIDI to the DRUMS_REF track

**What you get:** MIDI notes at every drum transient, categorized by frequency:
- Pitch 36 (C1): Low frequency hits (kicks)
- Pitch 38 (D1): Mid frequency hits (snares)
- Pitch 42 (F#1): High frequency hits (hats)

**Alternative:** If you have isolated drums or a drum MIDI file, import that directly - it's more accurate.

### 2.5 Create Structure Annotations

```
Tools: create_structure_track
```

**LLM actions:**
`create_structure_track(instrumental_path, audio_track_index=0)` - Creates a MIDI track with:
- Clips named by section (INTRO, VERSE, CHORUS, etc.)
- Energy level visualization (MIDI notes show hi/lo energy)
- Cue points at section boundaries for easy navigation

**Why this helps:** Visual map of the song structure. Essential for planning where vocals go.

---

## Phase 3: Arrangement

*Goal: Place vocal sections over the instrumental. This is the most creative phase.*

### 3.1 Plan the Arrangement

**You:** Looking at both structures, decide which vocal sections go where. Common approaches:
- Verse vocals over instrumental verses, chorus over chorus (parallel structure)
- Verse vocals over instrumental chorus for energy contrast
- Only use certain vocal sections that work best

**LLM:** Provides suggestions based on analysis:
- "The vocal chorus has high energy - it might work over the instrumental drop at bar 65"
- "The verse vocals are sparse - they'd sit well over the busy instrumental verse without clashing"

### 3.2 Split and Position Vocal Clips

```
Tools: split_arrangement_clip, move_arrangement_clip, batch_move_clips
```

**You:** Describe where you want vocal sections placed.

**LLM actions:**
1. `get_arrangement_clips(2)` - See current vocal clip positions
2. `split_arrangement_clip(2, 0, split_time)` - Cut vocals at section boundaries
3. `move_arrangement_clip(2, clip_index, new_start_beat)` - Move sections to new positions
4. Or `batch_move_clips([...])` - Move multiple clips at once

### 3.3 Track Vocal Source Positions

```
Tools: get_arrangement_clips
```

**Critical for timing alignment:** When you move vocal clips around, you need to know where each clip came from in the original vocal file.

**LLM actions:**
`get_arrangement_clips(2)` - Returns clip info including:
- `start_time`: Where the clip sits in the arrangement (beats)
- `loop_start`: Where this clip starts in the source audio file (beats)
- `loop_end`: Where this clip ends in the source audio file (beats)

**Why this matters:** A vocal clip at bar 33 might be playing bars 17-24 from the original file. When we analyze timing, we need to map the original vocal onsets to their arrangement positions.

**LLM:** Maintains a mapping table:
```
Arrangement Position | Source Start | Source End | Notes
--------------------|--------------|------------|-------
Bar 33 (beat 128)   | Beat 64      | Beat 96    | Chorus vocals
Bar 49 (beat 192)   | Beat 0       | Beat 32    | Verse 1 vocals
```

### 3.4 Audition and Iterate

```
Tools: start_playback, stop_playback, set_track_solo, set_track_mute
```

**You:** Listen to the arrangement. What works? What doesn't?

**LLM actions:**
- `start_playback()` / `stop_playback()` - Control playback
- `set_track_solo(2, True)` - Solo vocals to hear them alone
- `set_track_mute(0, True)` - Mute instrumental to focus on vocals

**Iterate:** Move clips, try different combinations, delete sections that don't work.

### 3.5 Fine-tune Clip Boundaries

```
Tools: set_arrangement_clip_file_position, split_arrangement_clip_multi
```

**You:** "The vocal clip starts a beat too early" or "I want to loop just the hook"

**LLM actions:**
- `set_arrangement_clip_file_position(track, clip, loop_start=X, loop_end=Y)` - Adjust which part of the source audio plays
- `split_arrangement_clip_multi(track, clip, [beat1, beat2, beat3])` - Create multiple cuts for surgical editing

---

## Phase 4: Timing Alignment

*Goal: Make the vocals lock in rhythmically with the instrumental groove.*

### 4.1 Understand the Problem

Different songs have different "feels":
- **Tight/quantized:** Notes land exactly on the grid (~0ms offset)
- **Laid-back:** Notes land behind the grid (+20-50ms, common in R&B/hip-hop)
- **Pushed/urgent:** Notes land ahead of the grid (-10-30ms, common in punk/EDM)

If your vocal has a different feel than your instrumental, they'll sound "off" even when technically in time.

### 4.2 Extract Vocal Rhythm to MIDI

```
Tools: vocal_to_midi
```

**LLM actions:**
`vocal_to_midi(vocal_path, "/tmp/vocal_rhythm.mid", bpm=X, create_track=True, track_name="VOCAL_RHYTHM")`

**What you get:** MIDI representation of every vocal onset, categorized by phoneme type:
- Pitch 38 (D1): Plosives (P, B, T, K) - percussive consonants
- Pitch 42 (F#1): Fricatives (S, Sh, F) - sibilant sounds
- Pitch 36 (C1): Vowels/Nasals (A, E, M, N) - tonal content

**Why this matters:** These MIDI notes let us compare vocal timing to drum timing with precision.

### 4.3 Macro Alignment: Global Groove Shift

```
Tools: groove_analyze, align_clips_to_groove
```

First, get the big picture - how does the overall vocal feel compare to the drums?

**LLM actions:**
1. `groove_analyze(source_track_index=3, source_clip_index=0, target_track_index=1, target_clip_index=0, source_offset=X)`
   - source = vocal rhythm MIDI
   - target = drum reference MIDI
   - source_offset = arrangement position of the vocal clip (from our mapping table)

**What you learn:**
- `mean_offset_ms`: Average timing difference (e.g., +42ms = vocals are 42ms behind drums)
- `std_offset_ms`: Consistency (low = consistent feel, high = variable timing)

**You:** Review the recommendation. "+42ms shift" means the vocals will be pushed later to match the drums' laid-back feel.

**LLM actions:**
`align_clips_to_groove(track_index=2, shift_beats=0.12)` - Shifts ALL vocal clips

**Listen:** Does it feel tighter? The vocals should now groove with the instrumental.

### 4.4 Micro Alignment: Per-Phoneme Adjustments

```
Tools: groove_analyze, groove_export_warp_markers
```

For surgical precision, align individual vocal attacks to specific drum hits.

**LLM actions:**
1. `groove_analyze(...)` with detailed output showing per-note offsets
2. `groove_export_warp_markers(source_track_index=3, source_clip_index=0, target_track_index=1, target_clip_index=0, source_offset=X, pitch_filter="36,38", min_offset_ms=20, min_spacing_beats=2.0)`

**Parameters explained:**
- `pitch_filter="36,38"`: Only create markers for kick (36) and snare (38) aligned phonemes
- `min_offset_ms=20`: Ignore tiny adjustments under 20ms
- `min_spacing_beats=2.0`: No more than one marker every half note (prevents over-warping)

**What you get:** A JSON file with warp marker data:
```json
[
  {"original_beat": 128.5, "target_beat": 128.0, "offset_ms": -42},
  {"original_beat": 132.25, "target_beat": 132.0, "offset_ms": -21},
  ...
]
```

**You:** Apply these warp markers manually in Ableton:
1. Double-click the vocal clip to open it
2. Enable Warp mode
3. Create warp markers at the `original_beat` positions
4. Drag each marker to its `target_beat` position

**Result:** Vocal plosives and attacks now land exactly with kick and snare hits.

### 4.5 Section-Specific Timing (Optional)

Different sections might need different timing. The verse might need +30ms shift, the chorus +50ms.

**LLM actions:**
Repeat the groove analysis for each vocal clip section, comparing against the corresponding drum section.

```
Verse clip (bars 49-64):   mean_offset = +28ms
Chorus clip (bars 33-48):  mean_offset = +51ms
```

**You:** Apply different shifts to different clips, or use warp markers for smooth transitions.

---

## Phase 5: Frequency Separation

*Goal: Make space for both tracks to be heard clearly without muddiness.*

### 5.1 Analyze Frequency Clashes

```
Tools: analyze_frequency_clash, audio_capture
```

**LLM actions:**
1. `audio_capture(start_beat, duration_seconds)` - Capture a section of the mix (if needed)
2. `analyze_frequency_clash(instrumental_path, vocal_path)` - Identify frequency bands where both compete

**What you learn:**
- Which frequency bands have clashing energy
- Recommended EQ cuts for each track
- Clash severity scores

### 5.2 Apply EQ Carving

```
Tools: load_instrument_or_effect, set_eq_bands, get_device_parameters
```

**You:** Decide which track should "win" in each frequency band (usually: vocals win in presence range 2-5kHz)

**LLM actions:**
1. `load_instrument_or_effect(0, "Audio Effects/EQ Eight")` - Add EQ to instrumental
2. `set_eq_bands(0, device_index, [{"band": 5, "gain_db": -3.0, "freq_hz": 3000, "q": 1.0}])` - Cut presence frequencies

**Common cuts:**
| Track | Frequency | Why |
|-------|-----------|-----|
| Instrumental | 2-5kHz | Make room for vocal presence |
| Instrumental | 200-400Hz | Reduce mud if vocals have body there |
| Vocals | Below 100Hz | Remove rumble/proximity effect |

### 5.3 Set Up Sidechain Compression

```
Tools: load_instrument_or_effect, setup_sidechain, set_device_parameter
```

Sidechain compression ducks the instrumental when vocals are present - the secret weapon of professional mashups.

**LLM actions:**
1. `load_instrument_or_effect(0, "Audio Effects/Compressor")` - Add compressor to instrumental
2. `get_track_devices(0)` - Find the compressor's device index
3. `setup_sidechain(target_track=0, target_device=X, source_track=2)` - Route vocals as sidechain input

**You:** Adjust threshold/ratio/attack/release by ear. Typical starting points:
- Ratio: 3:1 to 6:1
- Attack: 1-10ms (fast)
- Release: 50-150ms
- Threshold: Until you see 3-6dB reduction on vocal hits

### 5.4 Monitor the Mix

```
Tools: set_track_volume, set_track_pan
```

**You:** Listen to the full mix. Adjust levels.

**LLM actions:**
- `set_track_volume(0, 0.75)` - Lower instrumental if it's overpowering vocals
- `set_track_volume(2, 0.85)` - Adjust vocal level

---

## Phase 6: Polish & Effects

*Goal: Add creative touches and ensure professional quality.*

### 6.1 Vocal Processing

```
Tools: load_instrument_or_effect, get_browser_items_at_path
```

**LLM actions:**
1. `get_browser_items_at_path("Audio Effects")` - Browse available effects
2. Add processing chain to vocal track:
   - Reverb (use send/return for parallel processing)
   - Delay (rhythmic delays can enhance groove)
   - Compression (even out dynamics)

**You:** Dial in effect amounts by ear.

### 6.2 Create Variations (Optional)

```
Tools: duplicate_arrangement_clip_to_time, add_notes_to_arrangement_clip
```

For interest, create variations of vocal sections:

**LLM actions:**
- `duplicate_arrangement_clip_to_time(2, 0, beat_64)` - Copy a section for variation
- Different processing, filtering, or effects on the duplicate

### 6.3 Arrangement Flow

```
Tools: create_cue_point, get_cue_points
```

**LLM actions:**
`create_cue_point(beat)` - Mark important moments for easy navigation:
- Drop hits
- Vocal entries
- Breakdown starts

**You:** Review the full arrangement. Does it flow? Build? Release tension?

---

## Phase 7: AI Review & Iteration

*Goal: Get objective feedback and refine.*

### 7.1 Capture and Analyze Mix

```
Tools: audio_capture, analyze_audio_describe
```

**LLM actions:**
1. `audio_capture(0, 30)` - Capture 30 seconds of the mix from the start
2. `analyze_audio_describe(captured_file, "As a professional mastering engineer, critique this mashup mix. Focus on: 1) How well do the vocal and instrumental groove together? 2) Is there frequency masking? 3) Do the energy levels match? 4) Are the keys harmonically compatible?")`

**What you get:** Objective AI feedback on timing, frequency balance, energy matching, and harmonic compatibility.

### 7.2 Address Feedback

**You:** Review the AI's critique. Which points resonate with your ears?

**LLM:** Makes adjustments based on agreed feedback:
- More EQ cuts if there's masking
- Timing adjustments if groove is off
- Level changes if energy doesn't match
- Pitch shift if key clash is noted

### 7.3 Final Listen

**You:** Full playback. Trust your ears. The AI provides data, but you make the final call.

---

## Tool Reference

### Analysis Tools
| Tool | Purpose | Cost |
|------|---------|------|
| `analyze_song_structure` | BPM, sections, beats, downbeats, key | ~$0.10/track |
| `analyze_audio_describe` | AI description: groove, energy, creative suggestions | ~$0.05/call |
| `analyze_vocal_onsets` | Detect vocal attack positions | Free (local) |
| `analyze_groove_timing` | Compare timing feel between sources | Free (local) |
| `analyze_frequency_clash` | Identify frequency masking between tracks | Free (local) |
| `analyze_energy` | Per-16th-note energy features | Free (local) |

**Cost optimization:** Combine multiple questions into single `analyze_audio_describe` calls. One call with 5 questions costs the same as one call with 1 question.

### Groove Alignment Tools
| Tool | Purpose |
|------|---------|
| `vocal_to_midi` | Convert audio rhythm to MIDI (works on vocals or drums) |
| `groove_analyze` | Compare two MIDI clips, per-note timing offsets |
| `groove_export_warp_markers` | Generate warp marker data for manual application |
| `align_clips_to_groove` | Shift all clips on a track by a fixed amount |

### Arrangement Tools
| Tool | Purpose |
|------|---------|
| `get_arrangement_clips` | List clips with source positions (loop_start/loop_end) |
| `move_arrangement_clip` | Move a clip to new position |
| `split_arrangement_clip` | Cut a clip at a point |
| `split_arrangement_clip_multi` | Multiple cuts in one operation |
| `batch_move_clips` | Move multiple clips atomically |
| `set_arrangement_clip_file_position` | Adjust loop points within clip |
| `duplicate_arrangement_clip_to_time` | Copy clip to new position |
| `delete_arrangement_clip` | Remove a clip |

### Mixing Tools
| Tool | Purpose |
|------|---------|
| `set_track_volume` | Adjust track level (0.0-1.0) |
| `set_track_pan` | Adjust stereo position (-1.0 to 1.0) |
| `set_track_mute` / `set_track_solo` | Monitor controls |
| `load_instrument_or_effect` | Add devices to tracks |
| `set_device_parameter` | Adjust any device parameter |
| `set_eq_bands` | Efficiently control EQ Eight |
| `setup_sidechain` | Configure sidechain routing |

### Structure Tools
| Tool | Purpose |
|------|---------|
| `create_structure_track` | Create visual section map with energy |
| `create_cue_point` | Add arrangement locators |
| `get_cue_points` | List all locators |

### Session Tools
| Tool | Purpose |
|------|---------|
| `set_tempo` | Set session BPM |
| `start_playback` / `stop_playback` | Transport control |
| `audio_capture` | Record mix output to file |

---

## Common Issues & Solutions

### BPM detection is wrong
**Cause:** Half-time or double-time groove, or internet database was wrong
**Solution:** Always analyze with `analyze_song_structure`. Use `target_bpm` if you know the correct tempo.

### Vocals sound "off" even though they're on beat
**Cause:** Different groove feels between sources
**Solution:** Extract drum MIDI, extract vocal rhythm MIDI, use `groove_analyze` to measure offset, apply `align_clips_to_groove`

### Individual syllables are still off after global shift
**Cause:** Variable timing in the vocal performance
**Solution:** Use `groove_export_warp_markers` for per-phoneme micro adjustments, apply manually in Ableton

### Mix sounds muddy
**Cause:** Frequency clashing
**Solution:** Use `analyze_frequency_clash` and `set_eq_bands` to carve space

### Instrumental overpowers vocals
**Cause:** Missing sidechain or wrong levels
**Solution:** `setup_sidechain` and/or `set_track_volume`

### Keys clash audibly
**Cause:** Incompatible keys between tracks
**Solution:** Use `analyze_audio_describe` to identify keys, pitch shift one track in Ableton (usually vocals)

### Vocal sections don't align with instrumental sections
**Cause:** Different song structures
**Solution:** Creative cutting - you don't have to use parallel structure. Try verse vocals over instrumental chorus.

---

## The Human-LLM Partnership

The magic of this workflow is the collaboration:

**What the LLM does well:**
- Precise measurements (BPM, timing offsets, frequency analysis, key detection)
- Tedious operations (splitting clips at exact beats, moving multiple clips, extracting MIDI)
- Remembering details (track indices, device parameters, clip source positions)
- Suggesting options you might not have considered
- Executing complex multi-step operations reliably

**What you do better:**
- Hearing if something "feels" right (no algorithm beats trained ears)
- Making creative decisions (which sections to combine, how to arrange)
- Judging emotional impact (does this mashup tell a story?)
- Knowing when to break the rules (sometimes "wrong" sounds right)
- Final quality control (you sign off on the finished product)

**The workflow:** LLM proposes, you approve. LLM executes, you evaluate. LLM suggests, you decide.

---

## Example Session

```
You: I want to mash up "Savage" by Megan Thee Stallion with "Octo" by Deft & Lewis James

LLM: Let me analyze both tracks...
     [runs analyze_song_structure on instrumental - gets BPM, structure, AND key]
     [runs analyze_song_structure on vocals - gets BPM, structure, AND key]

     Results from structure analysis (includes free local key detection):
     - Instrumental "Octo": 170 BPM, D# minor (confidence: 0.66)
       Sections: intro (0-32), verse (32-96), drop (96-160), outro (160-192)
     - Vocals "Savage": 97 BPM, D# minor (confidence: 0.67)
       Sections: intro, verse1, chorus, verse2, chorus, outro

     Great news - both tracks are in the same key (D# minor)! No pitch shift needed.

     Tempo relationship: 170 and 97 have a ~1.75:1 ratio. The vocals at
     original speed would work as a half-time feel over the instrumental.

     Want me to get more detailed groove/energy analysis? (costs ~$0.05)

You: No, let's just try it. Put the "I'm a savage" hook over the drop.

LLM: Setting up the session...
     [creates tracks, sets tempo to 170]
     [extracts drum MIDI from instrumental]
     [creates structure track with sections]

     I've imported the files. The drop starts at bar 33. Drag the vocal
     file to the VOCALS track, then tell me and I'll position the hook.

You: Done, vocal is on the track

LLM: [splits vocal at section boundaries]
     [moves chorus hook to bar 33]
     [tracks source position: arrangement bar 33 = source beats 64-96]

     Hook is positioned. Let me extract the vocal rhythm and analyze
     groove alignment...

     [runs vocal_to_midi, then groove_analyze]

     Analysis complete:
     - Drum groove: +45ms behind grid (very laid back)
     - Vocal groove: +5ms (almost on grid)
     - Recommended shift: +40ms (0.11 beats at 170 BPM)

     Should I apply the global shift?

You: Yes

LLM: [align_clips_to_groove with shift_beats=0.11]
     Done. Playing from bar 31 so you hear the build...

You: Better! But some syllables still feel early

LLM: Let me do micro-alignment on the plosive consonants...
     [groove_export_warp_markers with pitch_filter="36,38"]

     Generated 12 warp markers for the hook section. The biggest
     adjustments are:
     - Beat 132.5 needs -35ms (vocal "SA-" lands before snare)
     - Beat 140.25 needs -28ms (vocal "CLASSY" early)

     I've saved the markers to /tmp/warp_markers.json. To apply:
     1. Double-click the vocal clip
     2. Add warp markers at the listed positions
     3. Drag each to its target position

     Or I can walk you through each one.

You: Walk me through the first one

LLM: First marker: The "SA" of "SAVAGE" at beat 132.5
     - Currently lands 35ms before the snare hit
     - Create a warp marker at 132.5
     - Drag it right to 132.71 (that's +0.21 beats = +35ms)

     This will push that syllable later to land with the snare.

You: Done, sounds tighter! But the instrumental is drowning out the vocals

LLM: Setting up sidechain compression...
     [loads compressor, setup_sidechain]

     Sidechain is routed from the vocal track. Adjust the compressor:
     - Threshold: start around -20dB
     - Ratio: 4:1
     - Attack: 5ms
     - Release: 100ms

     You should hear the instrumental "breathe" with the vocals.

You: Perfect. Let's hear the whole thing.

LLM: [start_playback from beat 0]
```

---

*This workflow evolves as we discover new techniques.*
