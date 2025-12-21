"""
Audio analysis module for Ableton MCP.

Provides integration with:
- ChordMini API for technical music analysis (BPM, beats, chords)
- Google Gemini for natural language audio understanding
"""

import os
import json
import logging
import mimetypes
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# ChordMini API configuration
CHORDMINI_BASE_URL = "https://chordmini-backend-191567167632.us-central1.run.app"

# Supported audio formats
SUPPORTED_FORMATS = {'.wav', '.mp3', '.aiff', '.aac', '.ogg', '.flac', '.m4a'}


def get_mime_type(file_path: str) -> str:
    """Get MIME type for an audio file."""
    ext = Path(file_path).suffix.lower()
    mime_types = {
        '.wav': 'audio/wav',
        '.mp3': 'audio/mpeg',
        '.aiff': 'audio/aiff',
        '.aac': 'audio/aac',
        '.ogg': 'audio/ogg',
        '.flac': 'audio/flac',
        '.m4a': 'audio/mp4',
    }
    return mime_types.get(ext, 'audio/mpeg')


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


class ChordMiniClient:
    """Client for ChordMini API - technical music analysis."""

    def __init__(self):
        self.base_url = CHORDMINI_BASE_URL

    def detect_beats(self, file_path: str) -> dict:
        """
        Analyze audio file for beats, BPM, and time signature.

        Returns dict with:
        - bpm: float
        - time_signature: str (e.g., "4/4")
        - beats: list of beat timestamps
        - downbeats: list of downbeat timestamps
        """
        valid, error = validate_audio_file(file_path)
        if not valid:
            raise ValueError(error)

        url = f"{self.base_url}/api/detect-beats"

        with open(file_path, 'rb') as f:
            files = {'file': (Path(file_path).name, f, get_mime_type(file_path))}
            response = requests.post(url, files=files, timeout=120)

        if response.status_code == 429:
            raise Exception("Rate limited. ChordMini allows 2 requests/minute for beat detection.")

        response.raise_for_status()
        return response.json()

    def recognize_chords(self, file_path: str) -> dict:
        """
        Analyze audio file for chord progression.

        Returns dict with:
        - chords: list of {chord: str, start: float, end: float}
        """
        valid, error = validate_audio_file(file_path)
        if not valid:
            raise ValueError(error)

        url = f"{self.base_url}/api/recognize-chords"

        with open(file_path, 'rb') as f:
            files = {'file': (Path(file_path).name, f, get_mime_type(file_path))}
            response = requests.post(url, files=files, timeout=120)

        if response.status_code == 429:
            raise Exception("Rate limited. ChordMini allows 2 requests/minute for chord recognition.")

        response.raise_for_status()
        return response.json()


class GeminiAudioClient:
    """Client for Google Gemini API - natural language audio understanding."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get('GOOGLE_API_KEY')
        if not self.api_key:
            raise ValueError(
                "Gemini API key not found. Set GOOGLE_API_KEY environment variable "
                "or pass api_key parameter."
            )
        self._client = None
        self._model = None

    def _get_client(self):
        """Lazy initialization of Gemini client."""
        if self._client is None:
            try:
                import google.generativeai as genai
            except ImportError:
                raise ImportError(
                    "google-generativeai package not installed. "
                    "Run: pip install google-generativeai"
                )

            genai.configure(api_key=self.api_key)
            self._client = genai
            self._model = genai.GenerativeModel('gemini-2.0-flash')
        return self._client, self._model

    def analyze(self, file_path: str, prompt: str) -> str:
        """
        Ask a question about an audio file using Gemini.

        Args:
            file_path: Path to the audio file
            prompt: Question or instruction about the audio

        Returns:
            Text response from Gemini
        """
        valid, error = validate_audio_file(file_path)
        if not valid:
            raise ValueError(error)

        genai, model = self._get_client()

        # Check file size - use File API for files > 20MB
        file_size = Path(file_path).stat().st_size

        if file_size > 20 * 1024 * 1024:  # 20MB
            # Use File API for large files
            logger.info(f"File size {file_size / 1024 / 1024:.1f}MB > 20MB, using File API")
            uploaded_file = genai.upload_file(file_path)

            # Wait for file to be processed
            import time
            while uploaded_file.state.name == "PROCESSING":
                time.sleep(2)
                uploaded_file = genai.get_file(uploaded_file.name)

            if uploaded_file.state.name == "FAILED":
                raise Exception(f"File upload failed: {uploaded_file.state.name}")

            response = model.generate_content([uploaded_file, prompt])
        else:
            # Inline audio for smaller files
            with open(file_path, 'rb') as f:
                audio_data = f.read()

            response = model.generate_content([
                {
                    "mime_type": get_mime_type(file_path),
                    "data": audio_data
                },
                prompt
            ])

        return response.text


def analyze_audio_technical(file_path: str) -> dict:
    """
    Perform technical analysis of an audio file.

    Returns BPM, time signature, beats, and chord progression.
    """
    client = ChordMiniClient()

    results = {
        "file": file_path,
        "beats": None,
        "chords": None,
        "errors": []
    }

    # Get beat analysis
    try:
        results["beats"] = client.detect_beats(file_path)
    except Exception as e:
        logger.error(f"Beat detection failed: {e}")
        results["errors"].append(f"Beat detection: {str(e)}")

    # Get chord analysis
    try:
        results["chords"] = client.recognize_chords(file_path)
    except Exception as e:
        logger.error(f"Chord recognition failed: {e}")
        results["errors"].append(f"Chord recognition: {str(e)}")

    return results


def analyze_audio_describe(file_path: str, prompt: str) -> str:
    """
    Ask a question about an audio file using AI.

    Args:
        file_path: Path to the audio file
        prompt: Question or instruction about the audio

    Returns:
        Text response describing the audio
    """
    client = GeminiAudioClient()
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

    # Track statistics
    categories = {"snare": 0, "hihat": 0, "kick": 0}

    for i, t in enumerate(times):
        # Analyze a 50ms window after the onset
        start_sample = onsets[i] * 512  # approx frame to sample
        end_sample = start_sample + int(sr * 0.05)
        segment = y[start_sample:end_sample]

        # Get the MIDI note based on phoneme category
        midi_note = _get_phoneme_category(segment, sr)

        # Track category
        if midi_note == DRUM_SNARE:
            categories["snare"] += 1
        elif midi_note == DRUM_HIHAT:
            categories["hihat"] += 1
        else:
            categories["kick"] += 1

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
        "duration": len(y) / sr
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
