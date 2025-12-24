# Proposed MCP Tools for Mashup Workflow

## High Priority

### 1. `analyze_vocal_onsets`
Detect vocal transients and return onset positions.

```python
def analyze_vocal_onsets(file_path: str, bpm: float = None) -> dict:
    """
    Returns:
        {
            "onset_count": 534,
            "onset_times": [0.02, 0.28, ...],  # seconds
            "onset_beats": [0.06, 0.79, ...],  # at specified BPM
            "bpm_used": 170.0
        }
    """
```

### 2. `analyze_groove_timing`
Compare timing feel between two audio/MIDI sources.

```python
def analyze_groove_timing(
    source_file: str,      # vocal or other audio
    target_track: int,     # track with groove reference (drums)
    target_clip: int,
    source_clips: list     # clip mappings from get_arrangement_clips
) -> dict:
    """
    Returns:
        {
            "source_grid_offset_ms": 2.3,
            "target_grid_offset_ms": 44.8,
            "recommended_shift_ms": 42.5,
            "recommended_shift_beats": 0.119,
            "alignment_score": 0.73  # 0-1, how well aligned
        }
    """
```

### 3. `align_clips_to_groove`
Apply timing correction to all clips on a track.

```python
def align_clips_to_groove(
    track_index: int,
    shift_beats: float
) -> dict:
    """
    Shifts all arrangement clips on track by specified amount.
    Returns list of moved clips with old/new positions.
    """
```

### 4. `create_mashup_template`
Set up standard mashup session structure.

```python
def create_mashup_template(
    instrumental_path: str = None,
    vocal_path: str = None,
    target_bpm: float = None
) -> dict:
    """
    Creates:
    - INSTRUMENTAL track with sidechain-ready compressor
    - DRUMS track (muted, for reference)
    - VOCALS track with processing rack
    - STRUCTURE annotation track
    - Standard return tracks

    Optionally imports and analyzes provided files.
    """
```

## Medium Priority

### 5. `setup_sidechain`
Configure sidechain routing (if API supports it).

```python
def setup_sidechain(
    target_track: int,      # track to compress
    target_device: int,     # compressor device index
    source_track: int       # sidechain input track
) -> dict:
```

Note: May require M4L device if native API doesn't support sidechain routing.

### 6. `export_timing_report`
Generate detailed timing analysis report.

```python
def export_timing_report(
    vocal_track: int,
    drum_track: int,
    output_path: str
) -> dict:
    """
    Creates JSON/markdown report with:
    - Per-clip timing analysis
    - Section-by-section breakdown
    - Worst offenders list
    - Recommended corrections
    """
```

### 7. `batch_move_clips`
Move multiple clips with a single call.

```python
def batch_move_clips(
    moves: list  # [{track: int, clip: int, new_start: float}, ...]
) -> dict:
```

## Lower Priority / Nice to Have

### 8. `analyze_frequency_clash`
Identify frequency conflicts between tracks.

```python
def analyze_frequency_clash(
    track_a: int,
    track_b: int,
    time_range: tuple = None
) -> dict:
    """
    Returns frequency bands with high correlation/masking.
    Suggests EQ cuts or sidechain bands.
    """
```

### 9. `create_drum_midi_from_audio`
Convert audio drums to MIDI for analysis.

```python
def create_drum_midi_from_audio(
    audio_track: int,
    clip_index: int,
    output_track: int = -1  # new track if -1
) -> dict:
    """
    Uses onset detection + frequency analysis to create
    kick/snare/hat MIDI from audio drums.
    """
```

---

## Implementation Notes

### For librosa-based tools:
- Add librosa to MCP server dependencies
- Cache analysis results to avoid re-processing

### For sidechain setup:
- Native API may not support sidechain routing
- Consider M4L device that accepts OSC/MIDI for configuration
- Or document manual step in workflow

### For template creation:
- Could save .als template file
- Or programmatically create tracks/devices each time
- Template file approach is more reliable for complex setups
