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


def _get_phoneme_category(y_segment, sr) -> int:
    """Categorizes a short segment of audio based on spectral features.

    Returns MIDI note number:
    - 60: Plosive (P/B/T/K) - Percussive hit
    - 62: Fricative (S/Sh/F) - High hat sound
    - 64: Vowel/Nasal (A/E/M/N) - Tonal body
    """
    import librosa
    import numpy as np

    if len(y_segment) < 512:
        return 64  # Default to vowel if too short

    # Zero Crossing Rate (measures 'noisiness')
    zcr = np.mean(librosa.feature.zero_crossing_rate(y=y_segment))

    # Spectral Centroid (measures 'brightness')
    centroid = np.mean(librosa.feature.spectral_centroid(y=y_segment, sr=sr))

    # Logic for categorization
    if zcr > 0.15 and centroid > 3000:
        return 62  # Fricative (S/Sh/F) - The 'High Hat'
    elif zcr < 0.05 and centroid < 1500:
        return 64  # Vowel/Nasal (A/E/M/N) - The 'Tonal Body'
    else:
        return 60  # Plosive (P/B/T/K) - The 'Percussive Hit'


def vocal_to_midi(audio_path: str, output_midi_path: str, bpm: float = 120.0) -> dict:
    """
    Convert vocal audio to MIDI based on phoneme categorization.

    Analyzes vocal onsets and categorizes them by phoneme type:
    - Plosives (P/B/T/K) → MIDI note 60 (C4) - Percussive hits
    - Fricatives (S/Sh/F) → MIDI note 62 (D4) - High hat sounds
    - Vowels/Nasals (A/E/M/N) → MIDI note 64 (E4) - Tonal body

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
    categories = {"plosive": 0, "fricative": 0, "vowel": 0}

    for i, t in enumerate(times):
        # Analyze a 50ms window after the onset
        start_sample = onsets[i] * 512  # approx frame to sample
        end_sample = start_sample + int(sr * 0.05)
        segment = y[start_sample:end_sample]

        # Get the MIDI note based on phoneme category
        midi_note = _get_phoneme_category(segment, sr)

        # Track category
        if midi_note == 60:
            categories["plosive"] += 1
        elif midi_note == 62:
            categories["fricative"] += 1
        else:
            categories["vowel"] += 1

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
