"""
Audio analysis module for Ableton MCP.

Provides integration with:
- Music Flamingo (via Replicate) for advanced music understanding
- Replicate API for song structure analysis (segments, beats, downbeats)
- Local librosa-based analysis for onsets, energy, and key detection
"""

import os
import json
import logging
import time
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# Supported audio formats
SUPPORTED_FORMATS = {'.wav', '.mp3', '.aiff', '.aac', '.ogg', '.flac', '.m4a'}


def validate_audio_file(file_path: str) -> tuple[bool, str]:
    """Validate that the file exists and is a supported audio format."""
    path = Path(file_path)

    if not path.exists():
        return False, f"File not found: {file_path}"

    if not path.is_file():
        return False, f"Not a file: {file_path}"

    ext = path.suffix.lower()
    if ext not in SUPPORTED_FORMATS:
        return False, f"Unsupported format: {ext}. Supported: {', '.join(SUPPORTED_FORMATS)}"

    return True, ""


class AudioFlamingoClient:
    """Client for Music Flamingo on Replicate - advanced music understanding."""

    # Using explicit version to avoid 404 errors from version lookup API
    MODEL_NAME = "jhurliman/music-flamingo:0fa8fa07084102b5ebeeee377ea6311f32fc856f8f95fadbede43f69329acb47"

    def __init__(self, api_token: Optional[str] = None):
        self.api_token = api_token or os.environ.get('REPLICATE_API_TOKEN')
        if not self.api_token:
            raise ValueError(
                "Replicate API token not found. Set REPLICATE_API_TOKEN environment variable "
                "or pass api_token parameter."
            )
        self._client = None

    def _get_client(self):
        """Lazy initialization of Replicate client."""
        if self._client is None:
            try:
                import replicate
            except ImportError:
                raise ImportError(
                    "replicate package not installed. "
                    "Run: pip install replicate"
                )
            self._client = replicate.Client(api_token=self.api_token)
        return self._client

    def analyze(self, file_path: str, prompt: str, max_new_tokens: int = 512) -> str:
        """
        Ask a question about an audio file using Music Flamingo.

        Music Flamingo is a state-of-the-art Large Audio-Language Model for music
        understanding, with theory-aware Q&A (harmony, structure, timbre, lyrics,
        cultural context), chain-of-thought reasoning, and support for long-form
        song reasoning (up to ~10 minutes).

        Args:
            file_path: Path to the audio file (max ~10 minutes)
            prompt: Question or instruction about the audio
            max_new_tokens: Maximum tokens in response (default: 512)

        Returns:
            Text response describing the audio
        """
        valid, error = validate_audio_file(file_path)
        if not valid:
            raise ValueError(error)

        client = self._get_client()

        logger.info(f"Submitting {file_path} to Music Flamingo...")

        with open(file_path, 'rb') as f:
            input_params = {
                "audio": f,
                "prompt": prompt,
                "max_new_tokens": max_new_tokens,
                "temperature": 0.7,
            }

            output = client.run(
                self.MODEL_NAME,
                input=input_params
            )

        if not output:
            raise Exception("No output received from Music Flamingo")

        # Output is a string with the model's analysis
        if isinstance(output, str):
            return output

        # Handle iterator output (some Replicate models stream)
        if hasattr(output, '__iter__'):
            return "".join(output)

        return str(output)


class ReplicateMusicAnalyzer:
    """Client for Replicate's All-In-One Music Structure Analyzer."""

    # Custom model with BPM constraint support (fork of all-in-one)
    # Using explicit version to avoid 404 errors from version lookup API
    MODEL_NAME = "jhurliman/allinone-targetbpm:f8657cff598c47c2c2dc2f5cdabfc26e25d099d62e9458119c16c716b0cfe259"

    def __init__(self, api_token: Optional[str] = None):
        self.api_token = api_token or os.environ.get('REPLICATE_API_TOKEN')
        if not self.api_token:
            raise ValueError(
                "Replicate API token not found. Set REPLICATE_API_TOKEN environment variable "
                "or pass api_token parameter."
            )
        self._client = None

    def _get_client(self):
        """Lazy initialization of Replicate client."""
        if self._client is None:
            try:
                import replicate
            except ImportError:
                raise ImportError(
                    "replicate package not installed. "
                    "Run: pip install replicate"
                )
            self._client = replicate.Client(api_token=self.api_token)
        return self._client

    def analyze(self, file_path: str, include_beats: bool = True, target_bpm: Optional[float] = None) -> dict:
        """
        Analyze song structure using Replicate's All-In-One model.

        Args:
            file_path: Path to the audio file
            include_beats: Include beat/downbeat arrays in output
            target_bpm: Lock BPM detection to this value (±1 BPM). Use when tempo is
                       misdetected (e.g., 140 BPM track detected as 81 BPM).

        Returns:
            Dict with:
            - bpm: float
            - segments: list of {start, end, label}
            - beats: list of beat timestamps (if include_beats)
            - downbeats: list of downbeat timestamps (if include_beats)
        """
        valid, error = validate_audio_file(file_path)
        if not valid:
            raise ValueError(error)

        client = self._get_client()

        # Run the model with file input
        if target_bpm:
            logger.info(f"Submitting {file_path} to Replicate with target_bpm={target_bpm}...")
        else:
            logger.info(f"Submitting {file_path} to Replicate for structure analysis...")

        with open(file_path, 'rb') as f:
            input_params = {"audio": f}
            if target_bpm is not None:
                input_params["target_bpm"] = target_bpm

            output = client.run(
                self.MODEL_NAME,
                input=input_params
            )

        # Output format depends on model version:
        # - New model (jhurliman/allinone-targetbpm): Returns JSON string directly
        # - Old model: Returns list of URLs to result files
        if not output:
            raise Exception("No output received from Replicate")

        # Handle direct JSON string output (new model)
        if isinstance(output, str):
            import json as json_module
            result = json_module.loads(output)
        # Handle URL-based output (old model compatibility)
        elif isinstance(output, list):
            json_url = None
            for url in output:
                if isinstance(url, str) and url.endswith('.json'):
                    json_url = url
                    break
            if not json_url:
                json_url = output[0] if output else None
            if not json_url:
                raise Exception(f"No JSON result in output: {output}")
            logger.info(f"Fetching analysis result from {json_url}")
            response = requests.get(json_url, timeout=60)
            response.raise_for_status()
            result = response.json()
        else:
            raise Exception(f"Unexpected output format: {type(output)}")

        # Format the output
        formatted = {
            "file": file_path,
            "bpm": result.get("bpm"),
            "segments": result.get("segments", []),
        }

        if include_beats:
            formatted["beats"] = result.get("beats", [])
            formatted["downbeats"] = result.get("downbeats", [])
            formatted["beat_positions"] = result.get("beat_positions", [])

        return formatted


def detect_key(file_path: str) -> dict:
    """
    Detect the musical key of an audio file using librosa.

    Uses chroma feature analysis with Krumhansl-Schmuckler key profiles
    to determine the most likely key.

    Args:
        file_path: Path to the audio file

    Returns:
        Dict with:
        - key: str (e.g., "C major", "A minor")
        - key_name: str (e.g., "C", "A")
        - mode: str ("major" or "minor")
        - confidence: float (0-1, correlation strength)
        - all_keys: list of all keys ranked by correlation
    """
    import librosa
    import numpy as np

    valid, error = validate_audio_file(file_path)
    if not valid:
        raise ValueError(error)

    logger.info(f"Detecting key for: {file_path}")

    # Load audio
    y, sr = librosa.load(file_path, sr=22050)

    # Compute chroma features (pitch class energy)
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)

    # Sum chroma over time to get pitch class distribution
    chroma_sum = np.sum(chroma, axis=1)
    chroma_sum = chroma_sum / np.max(chroma_sum)  # Normalize

    # Krumhansl-Schmuckler key profiles
    # Major key profile (starting from C)
    major_profile = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
    # Minor key profile (starting from C)
    minor_profile = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])

    # Normalize profiles
    major_profile = major_profile / np.linalg.norm(major_profile)
    minor_profile = minor_profile / np.linalg.norm(minor_profile)
    chroma_norm = chroma_sum / np.linalg.norm(chroma_sum)

    # Note names
    notes = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

    # Test all 24 keys (12 major + 12 minor)
    correlations = []

    for i in range(12):
        # Rotate chroma to align with this root note
        rotated_chroma = np.roll(chroma_norm, -i)

        # Correlate with major and minor profiles
        major_corr = np.corrcoef(rotated_chroma, major_profile)[0, 1]
        minor_corr = np.corrcoef(rotated_chroma, minor_profile)[0, 1]

        correlations.append({
            "key": f"{notes[i]} major",
            "key_name": notes[i],
            "mode": "major",
            "correlation": float(major_corr)
        })
        correlations.append({
            "key": f"{notes[i]} minor",
            "key_name": notes[i],
            "mode": "minor",
            "correlation": float(minor_corr)
        })

    # Sort by correlation (highest first)
    correlations.sort(key=lambda x: x["correlation"], reverse=True)

    # Best match
    best = correlations[0]

    logger.info(f"Detected key: {best['key']} (confidence: {best['correlation']:.2f})")

    return {
        "key": best["key"],
        "key_name": best["key_name"],
        "mode": best["mode"],
        "confidence": round(best["correlation"], 3),
        "all_keys": correlations[:6]  # Top 6 candidates
    }


def analyze_song_structure(file_path: str, include_beats: bool = True, target_bpm: Optional[float] = None, include_key: bool = True) -> dict:
    """
    Analyze song structure to identify sections (intro, verse, chorus, etc.).

    Uses Replicate's All-In-One Music Structure Analyzer which provides:
    - BPM detection
    - Beat and downbeat tracking
    - Functional segment boundaries and labels

    Also detects musical key locally using librosa (free, no API cost).

    Args:
        file_path: Path to the audio file
        include_beats: Include beat/downbeat arrays (can be large)
        target_bpm: Lock BPM detection to this value (±1 BPM). Use when tempo is
                   misdetected (e.g., 140 BPM track detected as 81 BPM).
        include_key: Run local key detection (default True)

    Returns:
        Dict with bpm, segments, beats, downbeats, key
    """
    client = ReplicateMusicAnalyzer()
    result = client.analyze(file_path, include_beats, target_bpm=target_bpm)

    # Add key detection (local, free)
    if include_key:
        try:
            key_result = detect_key(file_path)
            result["key"] = key_result["key"]
            result["key_confidence"] = key_result["confidence"]
            result["key_alternatives"] = [k["key"] for k in key_result["all_keys"][1:4]]  # Top 3 alternatives
        except Exception as e:
            logger.warning(f"Key detection failed: {e}")
            result["key"] = None
            result["key_error"] = str(e)

    return result


def analyze_audio_describe(file_path: str, prompt: str) -> str:
    """
    Ask a question about an audio file using AI (Music Flamingo via Replicate).

    Music Flamingo is a state-of-the-art Large Audio-Language Model for music
    understanding with deep music theory awareness.

    Args:
        file_path: Path to the audio file
        prompt: Question or instruction about the audio

    Returns:
        Text response describing the audio
    """
    client = AudioFlamingoClient()
    return client.analyze(file_path, prompt)


# Standard drum rack MIDI note mappings (General MIDI)
DRUM_KICK = 36       # C1 - Bass Drum
DRUM_SNARE = 38      # D1 - Snare
DRUM_HIHAT = 42      # F#1 - Closed Hi-Hat


def _get_phoneme_category(y_segment, sr) -> int:
    """Categorizes a short segment of audio based on spectral features.

    Returns MIDI note number for standard drum rack:
    - 38 (D1): Plosive (P/B/T/K) - Snare hit
    - 42 (F#1): Fricative (S/Sh/F) - Closed hi-hat
    - 36 (C1): Vowel/Nasal (A/E/M/N) - Kick drum
    """
    import librosa
    import numpy as np

    if len(y_segment) < 512:
        return DRUM_KICK  # Default to kick if too short

    # Zero Crossing Rate (measures 'noisiness')
    zcr = np.mean(librosa.feature.zero_crossing_rate(y=y_segment))

    # Spectral Centroid (measures 'brightness')
    centroid = np.mean(librosa.feature.spectral_centroid(y=y_segment, sr=sr))

    # Logic for categorization
    if zcr > 0.15 and centroid > 3000:
        return DRUM_HIHAT  # Fricative (S/Sh/F) - Closed hi-hat
    elif zcr < 0.05 and centroid < 1500:
        return DRUM_KICK   # Vowel/Nasal (A/E/M/N) - Kick drum
    else:
        return DRUM_SNARE  # Plosive (P/B/T/K) - Snare


def vocal_to_midi(audio_path: str, output_midi_path: str, bpm: float = 120.0) -> dict:
    """
    Convert vocal audio to MIDI based on phoneme categorization.

    Analyzes vocal onsets and categorizes them by phoneme type,
    outputting standard drum rack MIDI notes (General MIDI):
    - Plosives (P/B/T/K) → MIDI note 38 (D1) - Snare
    - Fricatives (S/Sh/F) → MIDI note 42 (F#1) - Closed hi-hat
    - Vowels/Nasals (A/E/M/N) → MIDI note 36 (C1) - Kick drum

    Args:
        audio_path: Path to the vocal audio file
        output_midi_path: Path to save the output MIDI file
        bpm: Tempo in BPM (default: 120)

    Returns:
        Dict with onset count, categories, and output path
    """
    import librosa
    import numpy as np
    from mido import Message, MidiFile, MidiTrack

    valid, error = validate_audio_file(audio_path)
    if not valid:
        raise ValueError(error)

    # Load audio
    y, sr = librosa.load(audio_path, sr=44100)

    # Onset detection
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    onsets = librosa.onset.onset_detect(onset_envelope=onset_env, sr=sr, backtrack=True)
    times = librosa.frames_to_time(onsets, sr=sr)

    # Create MIDI file
    mid = MidiFile()
    track = MidiTrack()
    mid.tracks.append(track)

    ticks_per_second = 480 * (bpm / 60.0)
    last_tick = 0

    # Track statistics - phoneme categories mapping to drum sounds
    # Plosives (P/B/T/K) → Snare (D1/38) - percussive attacks
    # Fricatives (S/Sh/F) → HiHat (F#1/42) - high frequency content
    # Vowels/Nasals (A/E/M/N) → Kick (C1/36) - tonal body
    categories = {"plosive": 0, "fricative": 0, "vowel": 0}

    # Also collect notes in Ableton-compatible format (beats, not ticks)
    ableton_notes = []
    note_duration_beats = 0.1  # Short drum hit duration

    for i, t in enumerate(times):
        # Analyze a 50ms window after the onset
        start_sample = onsets[i] * 512  # approx frame to sample
        end_sample = start_sample + int(sr * 0.05)
        segment = y[start_sample:end_sample]

        # Get the MIDI note based on phoneme category
        midi_note = _get_phoneme_category(segment, sr)

        # Track category
        if midi_note == DRUM_SNARE:
            categories["plosive"] += 1
        elif midi_note == DRUM_HIHAT:
            categories["fricative"] += 1
        else:
            categories["vowel"] += 1

        # Convert time to beats for Ableton
        start_beat = t * bpm / 60.0
        ableton_notes.append({
            "pitch": midi_note,
            "start_time": round(start_beat, 4),
            "duration": note_duration_beats,
            "velocity": 100,
            "mute": False
        })

        current_tick = int(t * ticks_per_second)
        delta = current_tick - last_tick

        track.append(Message('note_on', note=midi_note, velocity=100, time=max(0, delta)))
        track.append(Message('note_off', note=midi_note, velocity=0, time=20))

        last_tick = current_tick + 20

    mid.save(output_midi_path)
    logger.info(f"Vocal MIDI saved to {output_midi_path}")

    return {
        "output_path": output_midi_path,
        "onset_count": len(times),
        "categories": categories,
        "bpm": bpm,
        "duration": len(y) / sr,
        "notes": ableton_notes  # Notes in Ableton-compatible format
    }


def analyze_vocal_onsets(file_path: str, bpm: float = None) -> dict:
    """
    Detect vocal onsets using librosa.

    Args:
        file_path: Path to vocal audio file
        bpm: BPM for beat conversion (detects from audio if not provided)

    Returns:
        dict with file, bpm, onset_count, onset_times (seconds), onset_beats
    """
    import librosa

    valid, error = validate_audio_file(file_path)
    if not valid:
        raise ValueError(error)

    logger.info(f"Analyzing vocal onsets: {file_path}")
    y, sr = librosa.load(file_path)

    # Detect onsets
    onset_frames = librosa.onset.onset_detect(y=y, sr=sr, units='frames')
    onset_times = librosa.frames_to_time(onset_frames, sr=sr).tolist()

    # Get BPM if not provided
    if bpm is None:
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        bpm = float(tempo) if hasattr(tempo, '__float__') else float(tempo[0])

    # Convert to beats
    onset_beats = [t * bpm / 60 for t in onset_times]

    logger.info(f"Detected {len(onset_times)} onsets at {bpm:.1f} BPM")

    return {
        "file": file_path,
        "bpm": round(bpm, 2),
        "onset_count": len(onset_times),
        "onset_times": [round(t, 4) for t in onset_times],
        "onset_beats": [round(b, 4) for b in onset_beats]
    }


def analyze_groove_timing(
    vocal_onsets: list,
    drum_hits: list,
    bpm: float = 170.0
) -> dict:
    """
    Compare timing feel between vocal onsets and drum groove.

    Args:
        vocal_onsets: List of onset beat positions (from analyze_vocal_onsets)
        drum_hits: List of drum hit beat positions (kick/snare from MIDI)
        bpm: Session tempo for ms calculations

    Returns:
        - vocal_grid_offset_ms: How far vocals are from grid
        - drum_grid_offset_ms: How far drums are from grid
        - recommended_shift_ms: How much to shift vocals to match drums
        - recommended_shift_beats: Same in beats
    """
    import statistics

    def grid_offset(beats):
        """Calculate average offset from nearest quarter note for on-beat notes"""
        offsets = []
        for b in beats:
            nearest = round(b)
            offset = b - nearest
            if abs(offset) < 0.25:  # Only consider "on-beat" notes
                offsets.append(offset)
        return offsets

    vocal_offsets = grid_offset(vocal_onsets)
    drum_offsets = grid_offset(drum_hits)

    vocal_mean = statistics.mean(vocal_offsets) if vocal_offsets else 0
    drum_mean = statistics.mean(drum_offsets) if drum_offsets else 0

    ms_per_beat = 60000 / bpm

    vocal_ms = vocal_mean * ms_per_beat
    drum_ms = drum_mean * ms_per_beat
    shift_ms = drum_ms - vocal_ms
    shift_beats = shift_ms / ms_per_beat

    return {
        "vocal_grid_offset_ms": round(vocal_ms, 1),
        "drum_grid_offset_ms": round(drum_ms, 1),
        "recommended_shift_ms": round(shift_ms, 1),
        "recommended_shift_beats": round(shift_beats, 4),
        "vocal_onsets_analyzed": len(vocal_offsets),
        "drum_hits_analyzed": len(drum_offsets),
        "bpm": bpm
    }


# ============================================
# GROOVE ALIGNMENT TOOLS
# ============================================

def groove_align_analyze(
    source_notes: list,
    target_notes: list,
    source_offset: float = 0.0,
    bpm: float = 120.0,
    match_by_pitch: bool = True
) -> dict:
    """
    Analyze alignment between source MIDI (e.g., vocal rhythm) and target MIDI (e.g., drums).

    Args:
        source_notes: List of note dicts with 'pitch' and 'start_time' keys
        target_notes: List of note dicts with 'pitch' and 'start_time' keys
        source_offset: Beat offset to add to source times (e.g., clip start position)
        bpm: Tempo for ms calculations
        match_by_pitch: If True, prefer matching same pitch types

    Returns:
        Dict with alignment analysis including per-note offsets and statistics
    """
    import numpy as np

    # Build target lookup by pitch
    target_by_pitch = {}
    for n in target_notes:
        p = n['pitch']
        if p not in target_by_pitch:
            target_by_pitch[p] = []
        target_by_pitch[p].append(n['start_time'])

    for p in target_by_pitch:
        target_by_pitch[p] = sorted(target_by_pitch[p])

    all_target_times = sorted([n['start_time'] for n in target_notes])

    # Analyze each source note
    alignments = []
    for sn in source_notes:
        s_time = sn['start_time'] + source_offset
        pitch = sn['pitch']

        # Find candidates
        if match_by_pitch and pitch in target_by_pitch:
            candidates = target_by_pitch[pitch]
        else:
            candidates = all_target_times

        if not candidates:
            continue

        # Find closest target
        closest = min(candidates, key=lambda x: abs(x - s_time))
        offset_beats = s_time - closest
        offset_ms = offset_beats * 60 / bpm * 1000

        alignments.append({
            "source_time": round(s_time, 4),
            "target_time": round(closest, 4),
            "offset_beats": round(offset_beats, 4),
            "offset_ms": round(offset_ms, 1),
            "pitch": pitch
        })

    # Calculate statistics
    offsets_beats = [a['offset_beats'] for a in alignments]
    offsets_ms = [a['offset_ms'] for a in alignments]

    stats = {
        "total_notes": len(alignments),
        "mean_offset_beats": round(float(np.mean(offsets_beats)), 4) if offsets_beats else 0,
        "mean_offset_ms": round(float(np.mean(offsets_ms)), 1) if offsets_ms else 0,
        "std_offset_beats": round(float(np.std(offsets_beats)), 4) if offsets_beats else 0,
        "std_offset_ms": round(float(np.std(offsets_ms)), 1) if offsets_ms else 0,
        "max_offset_ms": round(float(max(offsets_ms)), 1) if offsets_ms else 0,
        "min_offset_ms": round(float(min(offsets_ms)), 1) if offsets_ms else 0,
    }

    return {
        "alignments": alignments,
        "statistics": stats,
        "bpm": bpm,
        "source_offset": source_offset
    }


def groove_align_quantize(
    source_notes: list,
    target_notes: list,
    source_offset: float = 0.0,
    max_snap_beats: float = 1.0,
    match_by_pitch: bool = True
) -> list:
    """
    Quantize source notes to snap to nearest target notes (groove alignment).

    Args:
        source_notes: List of note dicts to quantize
        target_notes: List of target note dicts (the groove to snap to)
        source_offset: Beat offset for source times
        max_snap_beats: Maximum distance to snap (notes further away keep original time)
        match_by_pitch: If True, prefer matching same pitch types

    Returns:
        List of quantized note dicts with adjusted start_time values
    """
    # Build target lookup
    target_by_pitch = {}
    for n in target_notes:
        p = n['pitch']
        if p not in target_by_pitch:
            target_by_pitch[p] = []
        target_by_pitch[p].append(n['start_time'])

    for p in target_by_pitch:
        target_by_pitch[p] = sorted(target_by_pitch[p])

    all_target_times = sorted([n['start_time'] for n in target_notes])

    quantized = []
    for sn in source_notes:
        s_time_abs = sn['start_time'] + source_offset
        pitch = sn['pitch']

        # Find candidates
        if match_by_pitch and pitch in target_by_pitch:
            candidates = target_by_pitch[pitch]
        else:
            candidates = all_target_times

        if candidates:
            closest = min(candidates, key=lambda x: abs(x - s_time_abs))
            distance = abs(s_time_abs - closest)

            if distance <= max_snap_beats:
                # Snap to target
                new_time = closest - source_offset
            else:
                # Keep original
                new_time = sn['start_time']
        else:
            new_time = sn['start_time']

        quantized.append({
            "pitch": pitch,
            "start_time": round(new_time, 4),
            "duration": sn.get('duration', 0.25),
            "velocity": sn.get('velocity', 100),
            "mute": sn.get('mute', False)
        })

    return quantized


def generate_warp_markers(
    source_notes: list,
    target_notes: list,
    source_offset: float = 0.0,
    bpm: float = 120.0,
    min_offset_ms: float = 20.0,
    match_by_pitch: bool = True,
    min_spacing_beats: float = 0.0,
    pitch_filter: list = None,
    max_markers: int = 0,
    quantize_targets_to: float = 0.0,
    markers_per_bar: float = 0.0
) -> list:
    """
    Generate warp marker data for aligning source audio to target groove.

    Args:
        source_notes: Source rhythm notes (from vocal_to_midi)
        target_notes: Target groove notes (from drums)
        source_offset: Beat offset for source clip start
        bpm: Tempo in BPM
        min_offset_ms: Minimum offset to create a warp marker (ignore smaller adjustments)
        match_by_pitch: Prefer matching same pitch types
        min_spacing_beats: Minimum spacing between warp markers in beats (e.g., 2.0 = half note minimum)
        pitch_filter: Only include markers for these pitches (e.g., [36, 38] for kick/snare only)
        max_markers: Maximum number of markers to generate (0 = unlimited)
        quantize_targets_to: Round target beats to this grid (e.g., 1.0 = quarter notes, 4.0 = bars)
        markers_per_bar: Target density in markers per bar (0 = use min_spacing instead)
                        e.g., 1.0 = ~1 marker per bar, 2.0 = ~2 markers per bar, 0.5 = ~1 marker every 2 bars

    Returns:
        List of warp marker dicts with original_time, target_time, and offset info
    """
    analysis = groove_align_analyze(
        source_notes, target_notes, source_offset, bpm, match_by_pitch
    )

    # Filter by pitch if specified
    alignments = analysis['alignments']
    if pitch_filter:
        alignments = [a for a in alignments if a['pitch'] in pitch_filter]

    # Filter by minimum offset
    alignments = [a for a in alignments if abs(a['offset_ms']) >= min_offset_ms]

    # Sort by offset magnitude (prioritize largest adjustments)
    alignments.sort(key=lambda a: abs(a['offset_ms']), reverse=True)

    # Apply max_markers limit before spacing filter
    if max_markers > 0:
        alignments = alignments[:max_markers]

    # Re-sort by time for spacing filter
    alignments.sort(key=lambda a: a['source_time'])

    # Calculate effective spacing from markers_per_bar if specified
    effective_spacing = min_spacing_beats
    if markers_per_bar > 0:
        # 4 beats per bar, so spacing = 4 / markers_per_bar
        effective_spacing = 4.0 / markers_per_bar

    # Apply minimum spacing filter
    if effective_spacing > 0:
        filtered = []
        last_beat = -float('inf')
        for a in alignments:
            if a['source_time'] - last_beat >= effective_spacing:
                filtered.append(a)
                last_beat = a['source_time']
        alignments = filtered

    warp_markers = []
    for a in alignments:
        # Convert to seconds for warp markers
        original_sec = a['source_time'] * 60 / bpm

        # Optionally quantize target beat to grid
        target_beat = a['target_time']
        if quantize_targets_to > 0:
            target_beat = round(target_beat / quantize_targets_to) * quantize_targets_to

        target_sec = target_beat * 60 / bpm

        warp_markers.append({
            "original_beat": a['source_time'],
            "target_beat": target_beat,
            "original_seconds": round(original_sec, 4),
            "target_seconds": round(target_sec, 4),
            "offset_ms": a['offset_ms'],
            "pitch": a['pitch']
        })

    # Final sort by original beat time
    warp_markers.sort(key=lambda m: m['original_beat'])

    return warp_markers


def export_warp_markers_to_file(warp_markers: list, output_path: str, format: str = "json") -> str:
    """
    Export warp markers to a file for use in Ableton or Max for Live.

    Args:
        warp_markers: List of warp marker dicts from generate_warp_markers
        output_path: Path to save the file
        format: "json" or "csv"

    Returns:
        Path to the saved file
    """
    import json
    import csv

    if format == "json":
        with open(output_path, 'w') as f:
            json.dump(warp_markers, f, indent=2)
    elif format == "csv":
        with open(output_path, 'w', newline='') as f:
            if warp_markers:
                writer = csv.DictWriter(f, fieldnames=warp_markers[0].keys())
                writer.writeheader()
                writer.writerows(warp_markers)
    else:
        raise ValueError(f"Unknown format: {format}")

    logger.info(f"Exported {len(warp_markers)} warp markers to {output_path}")
    return output_path


# ============================================
# ENERGY ANALYSIS TOOLS
# ============================================

# Frequency band definitions for energy analysis
ENERGY_BANDS = [
    (20, 60),      # Sub-bass
    (60, 250),     # Bass
    (250, 500),    # Low-mid
    (500, 2000),   # High-mid
    (2000, 20000), # High
]

ENERGY_BAND_NAMES = ['sub', 'bass', 'low_mid', 'high_mid', 'high']


def extract_energy_features(file_path: str, bpm: float) -> dict:
    """
    Extract 8 energy features per sixteenth note.

    Features (all normalized 0.0-1.0):
    - rms: RMS Energy (overall loudness)
    - centroid: Spectral Centroid (brightness, normalized to 0-1)
    - flux: Spectral Flux (rate of spectral change)
    - bands[0-4]: Sub/Bass/LowMid/HighMid/High energy

    Band frequency ranges:
    - bands[0] sub: 20-60 Hz
    - bands[1] bass: 60-250 Hz
    - bands[2] low_mid: 250-500 Hz
    - bands[3] high_mid: 500-2000 Hz
    - bands[4] high: 2000-20000 Hz

    Args:
        file_path: Path to audio file
        bpm: Tempo in BPM (used to calculate hop length for 16th notes)

    Returns:
        Struct-of-arrays format:
        {
            "bpm": float,
            "count": int,
            "times": [float, ...],      # seconds per 16th note
            "rms": [float, ...],
            "centroid": [float, ...],
            "flux": [float, ...],
            "bands": [[float, ...], ...],  # 5 arrays
            "global_stats": {median_rms, std_rms}
        }
    """
    import librosa
    import numpy as np

    valid, error = validate_audio_file(file_path)
    if not valid:
        raise ValueError(error)

    # Load audio at standard sample rate
    sr = 22050
    y, _ = librosa.load(file_path, sr=sr)

    # Calculate hop length for sixteenth notes
    # At BPM, one beat = 60/BPM seconds, one 16th = beat/4
    sixteenth_duration = 60.0 / bpm / 4.0
    hop_length = int(sixteenth_duration * sr)

    # Ensure hop_length is at least 512 for stable analysis
    hop_length = max(hop_length, 512)

    # Frame length should be 2x hop for good overlap
    frame_length = hop_length * 2

    # RMS Energy
    rms = librosa.feature.rms(y=y, frame_length=frame_length, hop_length=hop_length)[0]

    # Spectral Centroid (brightness) - normalize to 0-1 range
    centroid = librosa.feature.spectral_centroid(y=y, sr=sr, hop_length=hop_length)[0]
    # Typical range is 0 to sr/2, normalize
    centroid_normalized = centroid / (sr / 2)

    # Spectral Flux (onset strength as proxy for spectral change)
    flux = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop_length)

    # Band-limited energy using STFT
    n_fft = 2048
    S = np.abs(librosa.stft(y, n_fft=n_fft, hop_length=hop_length))
    freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)

    band_energies = []
    for low, high in ENERGY_BANDS:
        mask = (freqs >= low) & (freqs < high)
        if mask.sum() > 0:
            band_energy = np.mean(S[mask, :] ** 2, axis=0)
        else:
            band_energy = np.zeros(S.shape[1])
        band_energies.append(band_energy)

    band_energies = np.array(band_energies)

    # Normalize all features to 0-1
    def normalize(arr):
        arr = np.array(arr)
        if arr.max() > 0:
            return arr / arr.max()
        return arr

    rms_norm = normalize(rms)
    centroid_norm = np.clip(centroid_normalized, 0, 1)
    flux_norm = normalize(flux)
    bands_norm = [normalize(b) for b in band_energies]

    # Align all arrays to same length (minimum)
    min_len = min(len(rms_norm), len(centroid_norm), len(flux_norm), min(len(b) for b in bands_norm))
    rms_norm = rms_norm[:min_len]
    centroid_norm = centroid_norm[:min_len]
    flux_norm = flux_norm[:min_len]
    bands_norm = [b[:min_len] for b in bands_norm]

    # Generate time array
    times = librosa.frames_to_time(np.arange(min_len), sr=sr, hop_length=hop_length)

    # Calculate global stats for classification
    global_stats = {
        "median_rms": float(np.median(rms_norm)),
        "std_rms": float(np.std(rms_norm)),
        "median_centroid": float(np.median(centroid_norm)),
        "median_flux": float(np.median(flux_norm)),
    }

    return {
        "bpm": bpm,
        "hop_length_samples": hop_length,
        "count": min_len,
        "times": [round(float(t), 4) for t in times],
        "rms": [round(float(v), 4) for v in rms_norm],
        "centroid": [round(float(v), 4) for v in centroid_norm],
        "flux": [round(float(v), 4) for v in flux_norm],
        "bands": [[round(float(v), 4) for v in b] for b in bands_norm],
        "global_stats": global_stats,
    }


def classify_segment_energy(
    segments: list,
    energy_data: dict,
    bpm: float
) -> list:
    """
    Classify each segment with energy level and direction.

    Energy level (relative to track baseline):
    - hi: segment mean RMS > global median RMS
    - lo: segment mean RMS <= global median RMS

    Energy direction (relative to previous segment):
    - up: this segment's mean > previous segment's mean
    - down: this segment's mean < previous segment's mean
    - same: first segment or negligible change (<5% difference)

    Args:
        segments: List of segment dicts with start_beat, end_beat, label
        energy_data: Output from extract_energy_features()
        bpm: Tempo in BPM

    Returns:
        List of segments with added energy_level and energy_direction fields
    """
    import numpy as np

    times = np.array(energy_data['times'])
    rms = np.array(energy_data['rms'])
    global_median = energy_data['global_stats']['median_rms']

    annotated = []
    prev_mean = None

    for seg in segments:
        # Convert beat positions to time
        start_time = seg['start_beat'] * 60.0 / bpm / 4.0  # start_beat is in quarter notes
        end_time = seg['end_beat'] * 60.0 / bpm / 4.0

        # Actually, start_beat from analyze_song_structure is already in beats
        # Let me check the segment format - it should have start (seconds) and start_beat
        if 'start' in seg:
            start_time = seg['start']
            end_time = seg['end']
        else:
            # Convert beats to seconds (assuming quarter note beats)
            start_time = seg['start_beat'] * 60.0 / bpm
            end_time = seg['end_beat'] * 60.0 / bpm

        # Find frames within this segment
        mask = (times >= start_time) & (times < end_time)
        segment_rms = rms[mask]

        if len(segment_rms) > 0:
            seg_mean = float(np.mean(segment_rms))
        else:
            seg_mean = global_median

        # Classify level
        energy_level = "hi" if seg_mean > global_median else "lo"

        # Classify direction
        if prev_mean is None:
            energy_direction = "same"
        else:
            diff_pct = (seg_mean - prev_mean) / max(prev_mean, 0.001)
            if diff_pct > 0.05:
                energy_direction = "up"
            elif diff_pct < -0.05:
                energy_direction = "down"
            else:
                energy_direction = "same"

        prev_mean = seg_mean

        # Create annotated segment
        annotated_seg = dict(seg)
        annotated_seg['energy_level'] = energy_level
        annotated_seg['energy_direction'] = energy_direction
        annotated_seg['mean_rms'] = round(seg_mean, 4)

        annotated.append(annotated_seg)

    return annotated


# ============================================
# FREQUENCY CLASH ANALYSIS
# ============================================

def analyze_frequency_clash(
    file_a: str,
    file_b: str,
    time_range: tuple = None,
    n_bands: int = 8
) -> dict:
    """
    Analyze frequency clashes between two audio files.

    Identifies frequency bands where both tracks have significant energy,
    which can cause masking and muddy mixes.

    Args:
        file_a: Path to first audio file (e.g., instrumental)
        file_b: Path to second audio file (e.g., vocals)
        time_range: Optional (start_sec, end_sec) to analyze a specific section
        n_bands: Number of frequency bands to analyze (default 8)

    Returns:
        dict with:
        - bands: List of frequency band analyses
        - clash_bands: Bands with significant overlap (clash score > 0.5)
        - recommendations: Suggested EQ adjustments
    """
    import librosa
    import numpy as np

    # Validate files
    valid_a, error_a = validate_audio_file(file_a)
    if not valid_a:
        raise ValueError(f"File A: {error_a}")

    valid_b, error_b = validate_audio_file(file_b)
    if not valid_b:
        raise ValueError(f"File B: {error_b}")

    # Load audio files
    y_a, sr = librosa.load(file_a, sr=22050)
    y_b, _ = librosa.load(file_b, sr=22050)

    # Trim to time range if specified
    if time_range:
        start_sample = int(time_range[0] * sr)
        end_sample = int(time_range[1] * sr)
        y_a = y_a[start_sample:end_sample]
        y_b = y_b[start_sample:end_sample]

    # Make same length (pad shorter one)
    max_len = max(len(y_a), len(y_b))
    if len(y_a) < max_len:
        y_a = np.pad(y_a, (0, max_len - len(y_a)))
    if len(y_b) < max_len:
        y_b = np.pad(y_b, (0, max_len - len(y_b)))

    # Compute mel spectrograms
    n_mels = n_bands * 4  # More resolution for better band splitting
    S_a = librosa.feature.melspectrogram(y=y_a, sr=sr, n_mels=n_mels)
    S_b = librosa.feature.melspectrogram(y=y_b, sr=sr, n_mels=n_mels)

    # Convert to dB
    S_a_db = librosa.power_to_db(S_a, ref=np.max)
    S_b_db = librosa.power_to_db(S_b, ref=np.max)

    # Define frequency band edges (in Hz)
    # Using perceptually meaningful bands that map to EQ Eight bands 1-8
    band_edges = [20, 60, 150, 400, 1000, 2500, 6000, 12000, 20000]
    band_names = ["Sub", "Bass", "Low Mid", "Mid", "Upper Mid", "Presence", "Brilliance", "Air"]
    band_centers = [40, 125, 350, 1000, 3000, 5000, 8500, 15000]  # Center frequencies for EQ

    # Get mel frequencies
    mel_freqs = librosa.mel_frequencies(n_mels=n_mels, fmin=0, fmax=sr/2)

    bands = []
    clash_bands = []

    for i in range(min(n_bands, len(band_names))):
        low_freq = band_edges[i]
        high_freq = band_edges[i + 1]
        band_name = band_names[i]

        # Find mel bins for this frequency range
        low_bin = np.searchsorted(mel_freqs, low_freq)
        high_bin = np.searchsorted(mel_freqs, high_freq)

        if low_bin >= high_bin:
            continue

        # Average energy in this band for each track
        energy_a = np.mean(S_a_db[low_bin:high_bin, :])
        energy_b = np.mean(S_b_db[low_bin:high_bin, :])

        # Normalize to 0-1 scale (assuming -80 to 0 dB range)
        norm_a = (energy_a + 80) / 80
        norm_b = (energy_b + 80) / 80
        norm_a = max(0, min(1, norm_a))
        norm_b = max(0, min(1, norm_b))

        # Clash score: geometric mean of both energies
        # High when both tracks have significant energy in this band
        clash_score = np.sqrt(norm_a * norm_b)

        # Correlation in this band over time
        band_a = S_a_db[low_bin:high_bin, :].mean(axis=0)
        band_b = S_b_db[low_bin:high_bin, :].mean(axis=0)
        if np.std(band_a) > 0 and np.std(band_b) > 0:
            correlation = np.corrcoef(band_a, band_b)[0, 1]
        else:
            correlation = 0

        band_info = {
            "name": band_name,
            "freq_range": f"{low_freq}-{high_freq} Hz",
            "center_freq": band_centers[i],
            "eq_band": i + 1,  # EQ Eight band number (1-8)
            "energy_a": round(float(norm_a), 3),
            "energy_b": round(float(norm_b), 3),
            "clash_score": round(float(clash_score), 3),
            "correlation": round(float(correlation), 3)
        }

        bands.append(band_info)

        if clash_score > 0.5:
            clash_bands.append(band_info)

    # Generate recommendations
    recommendations = []
    for band in clash_bands:
        # Recommend cutting the track with less energy in this band
        if band["energy_a"] > band["energy_b"]:
            cut_track = "B"
            cut_amount = round((band["clash_score"] - 0.5) * 6, 1)  # 0-3 dB
        else:
            cut_track = "A"
            cut_amount = round((band["clash_score"] - 0.5) * 6, 1)

        recommendations.append({
            "band": band["name"],
            "eq_band": band["eq_band"],
            "center_freq": band["center_freq"],
            "freq_range": band["freq_range"],
            "cut_db": cut_amount,
            "cut_track": cut_track,
            "action": f"Cut {cut_amount}dB on track {cut_track}",
            "reason": f"Both tracks compete in {band['name']} range (clash score: {band['clash_score']})"
        })

    return {
        "file_a": file_a,
        "file_b": file_b,
        "bands": bands,
        "clash_bands": clash_bands,
        "clash_count": len(clash_bands),
        "recommendations": recommendations
    }
