# Mashup Production Workflow

## Prerequisites
- Ableton Live with AbletonMCP remote script installed
- MCP server running
- Source files: instrumental + vocal stems

---

## Phase 1: Analysis & Setup

### 1.1 Analyze Instrumental
```
Tools: analyze_song_structure, analyze_audio_technical
```
- Get BPM (use target_bpm if detection is wrong due to half-time feel)
- Identify song sections (intro, verse, chorus, bridge, outro)
- Note key/chord progression if needed

### 1.2 Analyze Vocals
```
Tools: analyze_song_structure (may fail on isolated vocals)
```
- Structure analysis for section boundaries
- Use instrumental BPM as reference since vocal BPM detection often fails

### 1.3 Set Session Tempo
```
Tools: set_tempo
```
- Match the instrumental's BPM (or target mashup BPM)

### 1.4 Create Structure Track (Optional)
```
Tools: create_structure_track
```
- Creates annotation MIDI track with section markers
- Adds cue points at section boundaries

---

## Phase 2: Arrangement

### 2.1 Import Audio
- Drag instrumental to track 1
- Drag vocal stem to track 2
- Let Ableton warp both to session tempo

### 2.2 Place Vocal Clips
- Cut vocal into sections matching song structure
- Place clips at appropriate arrangement positions
- Use session view to audition combinations

### 2.3 Document Clip Mapping
```
Tools: get_arrangement_clips (with loop_start/loop_end)
```
- Record source file positions for each clip
- This is needed for timing analysis later

---

## Phase 3: Timing Alignment

### 3.1 Detect Vocal Onsets
```python
# Using librosa (outside MCP)
import librosa
y, sr = librosa.load(vocal_file)
onset_frames = librosa.onset.onset_detect(y=y, sr=sr, units='time')
onset_beats = [t * bpm / 60 for t in onset_frames]
```

### 3.2 Get Drum/Groove Reference
```
Tools: get_arrangement_clip_notes (for MIDI drums)
       or analyze with librosa for audio drums
```
- Extract kick/snare hits as timing reference
- Filter to pitch 36 (kick) and 38 (snare) for standard GM mapping

### 3.3 Map Vocal Onsets to Arrangement
```python
# For each onset in source file beats:
for src_beat in vocal_onset_beats:
    for clip in vocal_clips:
        if clip.loop_start <= src_beat < clip.loop_end:
            arr_position = clip.arr_start + (src_beat - clip.loop_start)
```

### 3.4 Analyze Timing Offset
```python
# Compare vocal grid timing vs drum grid timing
vocal_grid_offset = mean([onset % 1 for onset in vocal_onsets])  # deviation from quarter notes
drum_grid_offset = mean([hit % 1 for hit in drum_hits])
timing_difference = vocal_grid_offset - drum_grid_offset
```

Key insight: Different songs have different "feels"
- Tight/quantized vocals: ~0ms grid offset
- Laid-back groove: +30-50ms behind grid
- Pushed/urgent feel: -20-40ms ahead of grid

### 3.5 Apply Timing Correction
```
Tools: move_arrangement_clip
```
- Shift all vocal clips by the timing difference
- Example: If drums are +45ms and vocals are +2ms, shift vocals +43ms later

---

## Phase 4: Frequency Separation

### 4.1 Sidechain Compression
- Add Compressor to instrumental track
- Set sidechain input to vocal track
- Typical settings:
  - Ratio: 3:1 to 6:1
  - Attack: 1-10ms (fast for ducking)
  - Release: 50-150ms
  - Threshold: adjust until 3-6dB reduction on vocal hits

### 4.2 EQ Carving (Alternative/Additional)
- Cut 2-4kHz on instrumental (vocal presence range)
- Or use dynamic EQ that ducks only when vocals present

### 4.3 Multiband Approach (Advanced)
- Use multiband compressor for surgical frequency ducking
- Only duck the frequencies where vocals live

---

## Phase 5: Polish

### 5.1 Get AI Feedback
```
Tools: analyze_audio_describe (Music Flamingo)
```
- Export mix and analyze
- Ask specific questions about timing, frequency balance, arrangement

### 5.2 Iterate
- Address feedback
- Re-analyze if significant changes made

---

## Automation Opportunities

### Fully Automatable via MCP:
- [x] Song structure analysis
- [x] Tempo setting
- [x] Structure track creation
- [x] Getting clip positions and MIDI notes
- [x] Moving clips for timing correction
- [x] AI audio analysis/feedback

### Partially Automatable:
- [ ] Onset detection (needs librosa, could add to MCP)
- [ ] Timing offset calculation (Python script, could add to MCP)
- [ ] Sidechain setup (can create compressor, but can't set sidechain input via API)

### Manual Only:
- [ ] Initial clip placement decisions (creative choice)
- [ ] Sidechain parameter tuning (API limitation)
- [ ] Final mix decisions

---

## Template Structure

```
Track 1: INSTRUMENTAL     [Audio] - Main instrumental
Track 2: INSTRUMENTAL_DRUMS [Audio/MIDI] - Isolated drums or drum MIDI (for groove reference)
Track 3: VOCALS           [Audio] - Vocal clips
Track 4: STRUCTURE        [MIDI] - Section annotations
Return A: VOCALS_REVERB   - Vocal reverb send
Return B: VOCALS_DELAY    - Vocal delay send
Master: Reference limiter
```

### Pre-configured Devices:
- Track 1: Compressor (ready for sidechain), EQ Eight
- Track 3: Audio Effect Rack (Clean/Processed chains), Glue Compressor
- Master: Limiter, Spectrum analyzer
