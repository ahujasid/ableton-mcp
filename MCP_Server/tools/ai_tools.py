"""AI-powered music theory and pattern generation tools for AbletonMCP.

These tools perform pure computation (no Ableton connection needed).
They generate MIDI note data for use with add_notes_to_clip.
"""
import json
import logging
import random
from typing import List, Optional
from mcp.server.fastmcp import FastMCP

logger = logging.getLogger("AbletonMCPServer")

# ---------------------------------------------------------------------------
# Music theory constants
# ---------------------------------------------------------------------------

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# Mapping for flats to their sharp equivalents
FLAT_TO_SHARP = {
    "Cb": "B", "Db": "C#", "Eb": "D#", "Fb": "E",
    "Gb": "F#", "Ab": "G#", "Bb": "A#",
}

CHORD_INTERVALS = {
    "major": [0, 4, 7],
    "minor": [0, 3, 7],
    "dim": [0, 3, 6],
    "aug": [0, 4, 8],
    "maj7": [0, 4, 7, 11],
    "min7": [0, 3, 7, 10],
    "dom7": [0, 4, 7, 10],
    "dim7": [0, 3, 6, 9],
    "half_dim7": [0, 3, 6, 10],
    "sus2": [0, 2, 7],
    "sus4": [0, 5, 7],
    "add9": [0, 4, 7, 14],
    "min9": [0, 3, 7, 10, 14],
    "maj9": [0, 4, 7, 11, 14],
    "dom9": [0, 4, 7, 10, 14],
    "6": [0, 4, 7, 9],
    "min6": [0, 3, 7, 9],
    "7sus4": [0, 5, 7, 10],
    "power": [0, 7],
    "min_maj7": [0, 3, 7, 11],
    "aug7": [0, 4, 8, 10],
    "11": [0, 4, 7, 10, 14, 17],
    "13": [0, 4, 7, 10, 14, 21],
}

SCALE_INTERVALS = {
    "major": [0, 2, 4, 5, 7, 9, 11],
    "minor": [0, 2, 3, 5, 7, 8, 10],
    "harmonic_minor": [0, 2, 3, 5, 7, 8, 11],
    "melodic_minor": [0, 2, 3, 5, 7, 9, 11],
    "dorian": [0, 2, 3, 5, 7, 9, 10],
    "phrygian": [0, 1, 3, 5, 7, 8, 10],
    "lydian": [0, 2, 4, 6, 7, 9, 11],
    "mixolydian": [0, 2, 4, 5, 7, 9, 10],
    "locrian": [0, 1, 3, 5, 6, 8, 10],
    "minor_pentatonic": [0, 3, 5, 7, 10],
    "major_pentatonic": [0, 2, 4, 7, 9],
    "blues": [0, 3, 5, 6, 7, 10],
    "chromatic": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11],
    "whole_tone": [0, 2, 4, 6, 8, 10],
    "diminished": [0, 2, 3, 5, 6, 8, 9, 11],
}

COMMON_PROGRESSIONS = {
    "pop": "I-V-vi-IV",
    "jazz_251": "ii-V-I",
    "blues": "I-I-I-I-IV-IV-I-I-V-IV-I-V",
    "rock": "I-IV-V-V",
    "sad": "vi-IV-I-V",
    "epic": "I-V-vi-iii-IV-I-IV-V",
    "reggaeton": "i-iv-VII-v",
    "andalusian": "iv-III-II-I",
}

# GM drum mapping
GM_DRUMS = {
    "kick": 36,
    "snare": 38,
    "closed_hh": 42,
    "open_hh": 46,
    "clap": 39,
    "rim": 37,
    "tom_low": 43,
    "tom_mid": 47,
    "tom_hi": 50,
    "crash": 49,
    "ride": 51,
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_note_name(note: str) -> int:
    """Parse a note name like 'C4', 'F#5', 'Bb3' into a MIDI number.

    Convention: C-1 = 0, C4 = 60 (middle C).
    """
    note = note.strip()
    if not note:
        raise ValueError("Empty note name")

    # Separate the letter+accidental part from the octave number
    i = 0
    # First character must be a letter
    if not note[0].isalpha():
        raise ValueError(f"Invalid note name: {note}")
    i = 1
    # Collect accidentals (# or b)
    while i < len(note) and note[i] in ("#", "b"):
        i += 1
    name_part = note[:i]
    octave_part = note[i:]

    if not octave_part:
        raise ValueError(f"No octave specified in note: {note}")
    # Handle negative octaves (e.g. C-1)
    try:
        octave = int(octave_part)
    except ValueError:
        raise ValueError(f"Invalid octave in note: {note}")

    # Normalize the note name
    name_upper = name_part[0].upper() + name_part[1:]

    # Handle flats
    if "b" in name_upper:
        if name_upper in FLAT_TO_SHARP:
            name_upper = FLAT_TO_SHARP[name_upper]
        else:
            raise ValueError(f"Unknown note name: {name_part}")

    if name_upper not in NOTE_NAMES:
        raise ValueError(f"Unknown note name: {name_part}")

    pitch_class = NOTE_NAMES.index(name_upper)
    # MIDI: C-1 = 0, so C4 = (4+1)*12 = 60
    midi = (octave + 1) * 12 + pitch_class
    if midi < 0 or midi > 127:
        raise ValueError(f"MIDI number {midi} out of range (0-127) for note {note}")
    return midi


def _midi_to_name(midi: int) -> str:
    """Convert a MIDI number to a note name like 'C4'."""
    if midi < 0 or midi > 127:
        raise ValueError(f"MIDI number {midi} out of range (0-127)")
    pitch_class = midi % 12
    octave = (midi // 12) - 1
    return f"{NOTE_NAMES[pitch_class]}{octave}"


def _note_name_to_pitch_class(name: str) -> int:
    """Convert a bare note name (no octave) like 'C', 'F#', 'Bb' to pitch class 0-11."""
    name = name.strip()
    name_upper = name[0].upper() + name[1:]
    if "b" in name_upper:
        if name_upper in FLAT_TO_SHARP:
            name_upper = FLAT_TO_SHARP[name_upper]
        else:
            raise ValueError(f"Unknown note name: {name}")
    if name_upper not in NOTE_NAMES:
        raise ValueError(f"Unknown note name: {name}")
    return NOTE_NAMES.index(name_upper)


def _get_scale_pitches(root_pc: int, scale_type: str, octave: int, num_octaves: int) -> List[int]:
    """Return a list of MIDI note numbers for the given scale."""
    if scale_type not in SCALE_INTERVALS:
        raise ValueError(
            f"Unknown scale type: {scale_type}. "
            f"Available: {', '.join(sorted(SCALE_INTERVALS.keys()))}"
        )
    intervals = SCALE_INTERVALS[scale_type]
    base_midi = (octave + 1) * 12 + root_pc
    notes = []
    for oct in range(num_octaves):
        for interval in intervals:
            midi = base_midi + oct * 12 + interval
            if 0 <= midi <= 127:
                notes.append(midi)
    # Add the final octave root
    final = base_midi + num_octaves * 12
    if 0 <= final <= 127:
        notes.append(final)
    return notes


# ---------------------------------------------------------------------------
# Roman-numeral progression parsing
# ---------------------------------------------------------------------------

# Scale degrees for major key (each degree: semitone offset, default chord quality)
_MAJOR_SCALE_DEGREES = {
    "I": (0, "major"),
    "ii": (2, "minor"),
    "iii": (4, "minor"),
    "IV": (5, "major"),
    "V": (7, "major"),
    "vi": (9, "minor"),
    "vii": (11, "dim"),
}

# Scale degrees for minor key
_MINOR_SCALE_DEGREES = {
    "i": (0, "minor"),
    "ii": (2, "dim"),
    "III": (3, "major"),
    "iv": (5, "minor"),
    "v": (7, "minor"),
    "VI": (8, "major"),
    "VII": (10, "major"),
}

# All possible Roman numerals (case-insensitive lookup)
_ROMAN_NUMERAL_SEMITONES = {
    "i": 0, "ii": 2, "iii": 4, "iv": 5, "v": 7, "vi": 9, "vii": 11,
}


def _parse_roman_numeral(numeral: str, key_pc: int, mode: str):
    """Parse a single Roman numeral into (root_midi_pitch_class, chord_quality)."""
    numeral = numeral.strip()
    if not numeral:
        raise ValueError("Empty Roman numeral")

    # Check for diminished marker
    is_dim = numeral.endswith("\u00b0") or numeral.endswith("o")
    clean = numeral.rstrip("\u00b0o")

    # Determine quality from case: uppercase = major, lowercase = minor
    is_upper = clean[0].isupper()

    # Lookup the degree
    degree_map = _MINOR_SCALE_DEGREES if mode == "minor" else _MAJOR_SCALE_DEGREES
    if numeral in degree_map:
        semitone_offset, quality = degree_map[numeral]
    elif clean in degree_map:
        semitone_offset, quality = degree_map[clean]
    else:
        # Fallback: compute from the numeral directly
        lower = clean.lower()
        if lower not in _ROMAN_NUMERAL_SEMITONES:
            raise ValueError(f"Unknown Roman numeral: {numeral}")
        semitone_offset = _ROMAN_NUMERAL_SEMITONES[lower]
        quality = "major" if is_upper else "minor"

    if is_dim:
        quality = "dim"

    root_pc = (key_pc + semitone_offset) % 12
    return root_pc, quality


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------


def register(mcp: FastMCP, get_connection, cache):
    """Register AI/music theory tools with the MCP server"""

    # ------------------------------------------------------------------
    # 1. note_name_to_midi
    # ------------------------------------------------------------------
    @mcp.tool()
    async def note_name_to_midi(note: str) -> str:
        """Convert a note name to its MIDI number.

        Supports sharps (#) and flats (b). Middle C is C4 = 60.

        Examples: "C4" -> 60, "A3" -> 57, "F#5" -> 78, "Bb3" -> 58.

        Args:
            note: Note name with octave, e.g. "C4", "F#5", "Bb3".
        """
        try:
            midi = _parse_note_name(note)
            return json.dumps({
                "note": note,
                "midi_number": midi,
                "normalized_name": _midi_to_name(midi),
            }, indent=2)
        except Exception as e:
            logger.error(f"Error converting note name to MIDI: {e}")
            return json.dumps({"error": str(e)})

    # ------------------------------------------------------------------
    # 2. midi_to_note_name
    # ------------------------------------------------------------------
    @mcp.tool()
    async def midi_to_note_name(midi_number: int) -> str:
        """Convert a MIDI number to its note name.

        Middle C (MIDI 60) = "C4".

        Examples: 60 -> "C4", 57 -> "A3", 78 -> "F#5".

        Args:
            midi_number: MIDI note number (0-127).
        """
        try:
            name = _midi_to_name(midi_number)
            return json.dumps({
                "midi_number": midi_number,
                "note_name": name,
                "pitch_class": NOTE_NAMES[midi_number % 12],
                "octave": (midi_number // 12) - 1,
            }, indent=2)
        except Exception as e:
            logger.error(f"Error converting MIDI to note name: {e}")
            return json.dumps({"error": str(e)})

    # ------------------------------------------------------------------
    # 3. generate_chord_notes
    # ------------------------------------------------------------------
    @mcp.tool()
    async def generate_chord_notes(
        root: str,
        chord_type: str = "major",
        octave: int = 4,
        inversion: int = 0,
    ) -> str:
        """Generate MIDI note numbers for a chord.

        Args:
            root: Root note name (e.g. "C", "F#", "Bb"). No octave needed.
            chord_type: Chord quality. Options: major, minor, dim, aug, maj7,
                min7, dom7, dim7, half_dim7, sus2, sus4, add9, min9, maj9,
                dom9, 6, min6, 7sus4, power, min_maj7, aug7, 11, 13.
            octave: MIDI octave for the root (0-8). Default 4.
            inversion: Chord inversion (0=root position, 1=first, 2=second, etc.).
        """
        try:
            if chord_type not in CHORD_INTERVALS:
                return json.dumps({
                    "error": f"Unknown chord type: {chord_type}",
                    "available_types": sorted(CHORD_INTERVALS.keys()),
                })

            root_pc = _note_name_to_pitch_class(root)
            intervals = list(CHORD_INTERVALS[chord_type])
            base_midi = (octave + 1) * 12 + root_pc

            # Build raw MIDI notes
            midi_notes = [base_midi + iv for iv in intervals]

            # Apply inversion: move the lowest N notes up an octave
            inv = inversion % len(midi_notes) if midi_notes else 0
            for i in range(inv):
                midi_notes[i] += 12
            midi_notes.sort()

            # Clamp to valid MIDI range
            midi_notes = [n for n in midi_notes if 0 <= n <= 127]

            note_names = [_midi_to_name(n) for n in midi_notes]

            root_normalized = NOTE_NAMES[root_pc]
            chord_label = f"{root_normalized}{chord_type}"
            if inversion > 0:
                chord_label += f" (inv {inversion})"

            return json.dumps({
                "chord": chord_label,
                "root": root_normalized,
                "chord_type": chord_type,
                "inversion": inversion,
                "midi_numbers": midi_notes,
                "note_names": note_names,
            }, indent=2)
        except Exception as e:
            logger.error(f"Error generating chord notes: {e}")
            return json.dumps({"error": str(e)})

    # ------------------------------------------------------------------
    # 4. generate_scale
    # ------------------------------------------------------------------
    @mcp.tool()
    async def generate_scale(
        root: str,
        scale_type: str = "major",
        octave: int = 4,
        num_octaves: int = 1,
    ) -> str:
        """Generate MIDI note numbers for a scale.

        Args:
            root: Root note name (e.g. "C", "F#", "Bb").
            scale_type: Scale type. Options: major, minor, harmonic_minor,
                melodic_minor, dorian, phrygian, lydian, mixolydian, locrian,
                minor_pentatonic, major_pentatonic, blues, chromatic,
                whole_tone, diminished.
            octave: Starting octave (0-8). Default 4.
            num_octaves: Number of octaves to generate (1-4). Default 1.
        """
        try:
            if scale_type not in SCALE_INTERVALS:
                return json.dumps({
                    "error": f"Unknown scale type: {scale_type}",
                    "available_types": sorted(SCALE_INTERVALS.keys()),
                })

            root_pc = _note_name_to_pitch_class(root)
            midi_notes = _get_scale_pitches(root_pc, scale_type, octave, num_octaves)
            note_names = [_midi_to_name(n) for n in midi_notes]

            root_normalized = NOTE_NAMES[root_pc]
            return json.dumps({
                "scale": f"{root_normalized} {scale_type}",
                "root": root_normalized,
                "scale_type": scale_type,
                "octave": octave,
                "num_octaves": num_octaves,
                "midi_numbers": midi_notes,
                "note_names": note_names,
            }, indent=2)
        except Exception as e:
            logger.error(f"Error generating scale: {e}")
            return json.dumps({"error": str(e)})

    # ------------------------------------------------------------------
    # 5. generate_chord_progression
    # ------------------------------------------------------------------
    @mcp.tool()
    async def generate_chord_progression(
        key: str,
        mode: str = "major",
        progression: str = "I-V-vi-IV",
        octave: int = 4,
    ) -> str:
        """Generate a chord progression using Roman numeral notation.

        Uppercase numerals = major chords, lowercase = minor chords.
        Append degree sign for diminished (e.g. "vii°").

        Preset progressions (pass as the progression argument):
        pop = I-V-vi-IV, jazz_251 = ii-V-I, blues = I-I-I-I-IV-IV-I-I-V-IV-I-V,
        rock = I-IV-V-V, sad = vi-IV-I-V, epic = I-V-vi-iii-IV-I-IV-V,
        reggaeton = i-iv-VII-v, andalusian = iv-III-II-I.

        Args:
            key: Root note of the key (e.g. "C", "F#", "Bb").
            mode: "major" or "minor".
            progression: Dash-separated Roman numerals (e.g. "I-V-vi-IV") or a
                preset name (e.g. "pop", "jazz_251").
            octave: MIDI octave for chord voicings. Default 4.
        """
        try:
            # Resolve preset name
            prog_str = COMMON_PROGRESSIONS.get(progression, progression)
            numerals = [n.strip() for n in prog_str.split("-") if n.strip()]

            if not numerals:
                return json.dumps({"error": "Empty progression"})

            key_pc = _note_name_to_pitch_class(key)
            key_name = NOTE_NAMES[key_pc]

            chords = []
            for beat_pos, numeral in enumerate(numerals):
                root_pc, quality = _parse_roman_numeral(numeral, key_pc, mode)
                intervals = CHORD_INTERVALS.get(quality, [0, 4, 7])
                base_midi = (octave + 1) * 12 + root_pc

                midi_notes = [base_midi + iv for iv in intervals]
                # Keep within MIDI range
                midi_notes = [n for n in midi_notes if 0 <= n <= 127]
                note_names = [_midi_to_name(n) for n in midi_notes]

                root_name = NOTE_NAMES[root_pc]
                chords.append({
                    "numeral": numeral,
                    "chord_name": f"{root_name}{quality}",
                    "root": root_name,
                    "quality": quality,
                    "midi_numbers": midi_notes,
                    "note_names": note_names,
                    "beat_position": beat_pos * 4,  # 4 beats per chord
                })

            return json.dumps({
                "key": key_name,
                "mode": mode,
                "progression": prog_str,
                "chords": chords,
                "available_presets": list(COMMON_PROGRESSIONS.keys()),
            }, indent=2)
        except Exception as e:
            logger.error(f"Error generating chord progression: {e}")
            return json.dumps({"error": str(e)})

    # ------------------------------------------------------------------
    # 6. generate_rhythm_pattern
    # ------------------------------------------------------------------
    @mcp.tool()
    async def generate_rhythm_pattern(
        style: str = "basic",
        bars: int = 1,
        time_signature: str = "4/4",
    ) -> str:
        """Generate a drum/rhythm pattern as MIDI notes ready for add_notes_to_clip.

        Uses standard General MIDI drum mapping:
        kick=36, snare=38, closed_hh=42, open_hh=46, clap=39, rim=37,
        tom_low=43, tom_mid=47, tom_hi=50, crash=49, ride=51.

        Args:
            style: Pattern style. Options: basic, rock, hiphop, trap, house,
                dnb, reggaeton, bossa_nova, jazz_swing, funk.
            bars: Number of bars to generate (1-8). Default 1.
            time_signature: Time signature as "numerator/denominator" (e.g. "4/4").
                Default "4/4".
        """
        try:
            # Parse time signature
            parts = time_signature.split("/")
            if len(parts) != 2:
                return json.dumps({"error": f"Invalid time signature: {time_signature}"})
            beats_per_bar = int(parts[0])
            beat_unit = int(parts[1])

            # 16th note grid: each step = 0.25 beats (for quarter-note-based meters)
            step_duration = 4.0 / 16  # 0.25 beats per 16th note
            steps_per_bar = int(beats_per_bar * (16 / beat_unit))

            # Define patterns as lists of (step_positions, velocity) per instrument
            # Each pattern is for one bar on a 16-step grid (when 4/4)
            patterns = _get_drum_pattern(style, steps_per_bar)

            if patterns is None:
                return json.dumps({
                    "error": f"Unknown style: {style}",
                    "available_styles": [
                        "basic", "rock", "hiphop", "trap", "house",
                        "dnb", "reggaeton", "bossa_nova", "jazz_swing", "funk",
                    ],
                })

            notes = []
            for bar in range(bars):
                bar_offset = bar * beats_per_bar
                for pitch, hits in patterns.items():
                    for step, velocity in hits:
                        start_time = bar_offset + step * step_duration
                        notes.append({
                            "pitch": pitch,
                            "start_time": round(start_time, 4),
                            "duration": round(step_duration, 4),
                            "velocity": velocity,
                            "mute": False,
                        })

            # Sort by start time for readability
            notes.sort(key=lambda n: (n["start_time"], n["pitch"]))

            return json.dumps({
                "style": style,
                "bars": bars,
                "time_signature": time_signature,
                "total_beats": beats_per_bar * bars,
                "drum_map": GM_DRUMS,
                "notes": notes,
            }, indent=2)
        except Exception as e:
            logger.error(f"Error generating rhythm pattern: {e}")
            return json.dumps({"error": str(e)})

    # ------------------------------------------------------------------
    # 7. generate_bassline
    # ------------------------------------------------------------------
    @mcp.tool()
    async def generate_bassline(
        key: str,
        scale_type: str = "minor_pentatonic",
        chord_progression: str = "i-iv-VII-v",
        bars: int = 4,
        style: str = "basic",
        octave: int = 2,
    ) -> str:
        """Generate a bassline that follows a chord progression.

        Produces MIDI notes ready for add_notes_to_clip.

        Args:
            key: Root note of the key (e.g. "C", "F#", "Bb").
            scale_type: Scale for note selection. Default "minor_pentatonic".
            chord_progression: Dash-separated Roman numerals or a preset name.
                Default "i-iv-VII-v".
            bars: Number of bars to generate. Default 4.
            style: Bassline style. Options: basic (root notes on each beat),
                walking (jazz walking bass), octave (root + octave pattern),
                arpeggiated (chord arpeggios), syncopated (offbeat rhythms).
            octave: MIDI octave for the bass (0-3). Default 2.
        """
        try:
            key_pc = _note_name_to_pitch_class(key)

            # Determine mode from progression or scale
            mode = "minor" if scale_type in (
                "minor", "harmonic_minor", "melodic_minor", "dorian",
                "phrygian", "minor_pentatonic",
            ) else "major"

            # Resolve progression
            prog_str = COMMON_PROGRESSIONS.get(chord_progression, chord_progression)
            numerals = [n.strip() for n in prog_str.split("-") if n.strip()]

            if not numerals:
                return json.dumps({"error": "Empty chord progression"})

            # Build scale pitch classes for walking/arpeggiated styles
            scale_intervals = SCALE_INTERVALS.get(scale_type, SCALE_INTERVALS["minor_pentatonic"])
            scale_pcs = set((key_pc + iv) % 12 for iv in scale_intervals)

            # Assign chords to bars (cycle if progression is shorter than bars)
            bar_chords = []
            for bar_idx in range(bars):
                numeral = numerals[bar_idx % len(numerals)]
                root_pc, quality = _parse_roman_numeral(numeral, key_pc, mode)
                chord_intervals = CHORD_INTERVALS.get(quality, [0, 4, 7])
                bar_chords.append((root_pc, quality, chord_intervals))

            rng = random.Random(42)  # Deterministic seed for reproducibility
            notes = []
            beats_per_bar = 4

            for bar_idx, (root_pc, quality, chord_ivs) in enumerate(bar_chords):
                bar_offset = bar_idx * beats_per_bar
                base_midi = (octave + 1) * 12 + root_pc

                if style == "basic":
                    # Root note on each beat
                    for beat in range(beats_per_bar):
                        notes.append({
                            "pitch": base_midi,
                            "start_time": round(bar_offset + beat, 4),
                            "duration": 1.0,
                            "velocity": 100 if beat == 0 else 80,
                            "mute": False,
                        })

                elif style == "walking":
                    # Jazz walking bass: chromatic/scalar approach to next root
                    next_bar = bar_chords[(bar_idx + 1) % len(bar_chords)]
                    next_root_midi = (octave + 1) * 12 + next_bar[0]
                    # Beat 1: root, Beat 2: chord tone, Beat 3: scale tone, Beat 4: approach note
                    chord_tone_midi = base_midi + chord_ivs[min(1, len(chord_ivs) - 1)]
                    # Find a scale tone that isn't the root or chord tone
                    scale_tones = [(base_midi + iv) for iv in scale_intervals if iv not in (0, chord_ivs[min(1, len(chord_ivs) - 1)] % 12)]
                    scale_tone = scale_tones[rng.randint(0, max(0, len(scale_tones) - 1))] if scale_tones else base_midi + 5
                    # Approach note: chromatic step toward next root
                    if next_root_midi > base_midi:
                        approach = next_root_midi - 1
                    elif next_root_midi < base_midi:
                        approach = next_root_midi + 1
                    else:
                        approach = base_midi + 11  # leading tone

                    walk = [base_midi, chord_tone_midi, scale_tone, approach]
                    for beat, pitch in enumerate(walk):
                        # Keep in range
                        while pitch > (octave + 2) * 12:
                            pitch -= 12
                        while pitch < octave * 12:
                            pitch += 12
                        pitch = max(0, min(127, pitch))
                        notes.append({
                            "pitch": pitch,
                            "start_time": round(bar_offset + beat, 4),
                            "duration": 0.9,
                            "velocity": rng.randint(85, 105),
                            "mute": False,
                        })

                elif style == "octave":
                    # Root and octave alternation
                    pattern_pitches = [base_midi, base_midi + 12, base_midi, base_midi + 12]
                    for beat, pitch in enumerate(pattern_pitches):
                        pitch = max(0, min(127, pitch))
                        notes.append({
                            "pitch": pitch,
                            "start_time": round(bar_offset + beat, 4),
                            "duration": 0.75,
                            "velocity": 100 if beat % 2 == 0 else 85,
                            "mute": False,
                        })

                elif style == "arpeggiated":
                    # Arpeggiate through chord tones in eighth notes
                    chord_midi = [base_midi + iv for iv in chord_ivs]
                    for eighth in range(8):
                        pitch = chord_midi[eighth % len(chord_midi)]
                        # Second pass goes up an octave
                        if eighth >= len(chord_midi):
                            pitch += 12
                        pitch = max(0, min(127, pitch))
                        notes.append({
                            "pitch": pitch,
                            "start_time": round(bar_offset + eighth * 0.5, 4),
                            "duration": 0.5,
                            "velocity": 95 if eighth % 2 == 0 else 75,
                            "mute": False,
                        })

                elif style == "syncopated":
                    # Offbeat/syncopated pattern on 16th note grid
                    # Typical syncopated hits: beat 1, and-of-2, beat 3, and-of-4
                    hit_times = [0.0, 1.5, 2.0, 3.5]
                    durations = [1.0, 0.5, 1.0, 0.5]
                    pitches = [base_midi, base_midi, base_midi + chord_ivs[min(1, len(chord_ivs) - 1)], base_midi]
                    for hit_t, dur, pitch in zip(hit_times, durations, pitches):
                        pitch = max(0, min(127, pitch))
                        notes.append({
                            "pitch": pitch,
                            "start_time": round(bar_offset + hit_t, 4),
                            "duration": round(dur, 4),
                            "velocity": rng.randint(85, 110),
                            "mute": False,
                        })

                else:
                    return json.dumps({
                        "error": f"Unknown bassline style: {style}",
                        "available_styles": ["basic", "walking", "octave", "arpeggiated", "syncopated"],
                    })

            notes.sort(key=lambda n: (n["start_time"], n["pitch"]))

            return json.dumps({
                "key": NOTE_NAMES[key_pc],
                "scale_type": scale_type,
                "chord_progression": prog_str,
                "style": style,
                "bars": bars,
                "total_beats": bars * beats_per_bar,
                "notes": notes,
            }, indent=2)
        except Exception as e:
            logger.error(f"Error generating bassline: {e}")
            return json.dumps({"error": str(e)})

    # ------------------------------------------------------------------
    # 8. generate_melody
    # ------------------------------------------------------------------
    @mcp.tool()
    async def generate_melody(
        key: str,
        scale_type: str = "major",
        bars: int = 4,
        octave: int = 5,
        density: str = "medium",
        style: str = "simple",
    ) -> str:
        """Generate a simple melody within a scale.

        Produces MIDI notes ready for add_notes_to_clip. Uses musical heuristics:
        stepwise motion preferred, occasional leaps, tendency to resolve to tonic.

        Args:
            key: Root note of the key (e.g. "C", "F#", "Bb").
            scale_type: Scale to use. Default "major".
            bars: Number of bars. Default 4.
            octave: MIDI octave for the melody. Default 5.
            density: Note density. Options: sparse (few long notes), medium
                (quarter/eighth mix), dense (mostly eighth/sixteenth notes).
            style: Melodic style. Options: simple (mixed rhythms), arpeggiated
                (chord-tone focused), stepwise (mostly scale steps).
        """
        try:
            if scale_type not in SCALE_INTERVALS:
                return json.dumps({
                    "error": f"Unknown scale type: {scale_type}",
                    "available_types": sorted(SCALE_INTERVALS.keys()),
                })

            key_pc = _note_name_to_pitch_class(key)
            # Build 2-octave scale for melodic range
            scale_notes = _get_scale_pitches(key_pc, scale_type, octave, 2)
            if not scale_notes:
                return json.dumps({"error": "Could not generate scale notes"})

            rng = random.Random(42)
            beats_per_bar = 4
            total_beats = bars * beats_per_bar

            # Duration pools by density
            if density == "sparse":
                duration_pool = [2.0, 2.0, 1.0, 1.0, 4.0]
            elif density == "dense":
                duration_pool = [0.25, 0.25, 0.5, 0.5, 0.5, 1.0]
            else:  # medium
                duration_pool = [0.5, 0.5, 1.0, 1.0, 0.25, 2.0]

            notes = []
            current_time = 0.0
            # Start near the middle of the scale
            current_idx = len(scale_notes) // 2

            while current_time < total_beats:
                duration = rng.choice(duration_pool)
                # Don't exceed total length
                if current_time + duration > total_beats:
                    duration = total_beats - current_time
                if duration <= 0:
                    break

                # Choose next note based on style
                if style == "stepwise":
                    # Mostly steps, rare leaps
                    step = rng.choice([-1, -1, 1, 1, -2, 2, 0])
                elif style == "arpeggiated":
                    # Larger intervals (arpeggiate through scale)
                    step = rng.choice([-2, -1, 1, 2, 2, 3, -3])
                else:  # simple
                    # Balanced mix
                    step = rng.choice([-2, -1, -1, 0, 1, 1, 2, 3, -3])

                current_idx = max(0, min(len(scale_notes) - 1, current_idx + step))

                # Tendency toward tonic on bar boundaries (resolution)
                is_bar_boundary = (current_time % beats_per_bar) == 0
                is_last_beat = (current_time + duration) >= total_beats
                if (is_bar_boundary or is_last_beat) and rng.random() < 0.4:
                    # Find nearest tonic
                    tonic_midi = (octave + 1) * 12 + key_pc
                    tonic_indices = [i for i, n in enumerate(scale_notes) if n % 12 == key_pc]
                    if tonic_indices:
                        closest = min(tonic_indices, key=lambda i: abs(i - current_idx))
                        current_idx = closest

                # Force resolve to tonic on final note
                if is_last_beat:
                    tonic_indices = [i for i, n in enumerate(scale_notes) if n % 12 == key_pc]
                    if tonic_indices:
                        current_idx = min(tonic_indices, key=lambda i: abs(i - current_idx))

                pitch = scale_notes[current_idx]

                # Add occasional rests (skip note) for musicality
                if rng.random() < 0.1 and not is_last_beat:
                    current_time += duration
                    continue

                velocity = rng.randint(70, 110)
                # Accent downbeats
                if (current_time % beats_per_bar) == 0:
                    velocity = min(127, velocity + 15)

                notes.append({
                    "pitch": pitch,
                    "start_time": round(current_time, 4),
                    "duration": round(duration * 0.9, 4),  # Slight gap for articulation
                    "velocity": velocity,
                    "mute": False,
                })
                current_time += duration

            notes.sort(key=lambda n: (n["start_time"], n["pitch"]))

            return json.dumps({
                "key": NOTE_NAMES[key_pc],
                "scale_type": scale_type,
                "style": style,
                "density": density,
                "bars": bars,
                "total_beats": total_beats,
                "notes": notes,
            }, indent=2)
        except Exception as e:
            logger.error(f"Error generating melody: {e}")
            return json.dumps({"error": str(e)})

    # ------------------------------------------------------------------
    # 9. suggest_chords_for_melody
    # ------------------------------------------------------------------
    @mcp.tool()
    async def suggest_chords_for_melody(notes: List[int]) -> str:
        """Suggest harmonizing chords for a given melody.

        Analyzes the pitch content of the melody, determines the most likely
        key, and suggests appropriate chords for harmonization.

        Args:
            notes: A list of MIDI note numbers representing the melody.
        """
        try:
            if not notes:
                return json.dumps({"error": "No notes provided"})

            # Extract pitch classes and count occurrences
            pc_counts = [0] * 12
            for n in notes:
                if 0 <= n <= 127:
                    pc_counts[n % 12] += 1

            # Determine likely key by scoring each possible key against
            # major and minor scale templates
            major_template = SCALE_INTERVALS["major"]
            minor_template = SCALE_INTERVALS["minor"]

            best_key = 0
            best_mode = "major"
            best_score = -1

            for candidate_root in range(12):
                # Score against major
                major_score = sum(
                    pc_counts[(candidate_root + iv) % 12] for iv in major_template
                )
                if major_score > best_score:
                    best_score = major_score
                    best_key = candidate_root
                    best_mode = "major"

                # Score against minor
                minor_score = sum(
                    pc_counts[(candidate_root + iv) % 12] for iv in minor_template
                )
                if minor_score > best_score:
                    best_score = minor_score
                    best_key = candidate_root
                    best_mode = "minor"

            key_name = NOTE_NAMES[best_key]
            scale_intervals = major_template if best_mode == "major" else minor_template
            scale_pcs = [(best_key + iv) % 12 for iv in scale_intervals]

            # Build diatonic triads for the detected key
            degree_names_major = ["I", "ii", "iii", "IV", "V", "vi", "vii\u00b0"]
            degree_names_minor = ["i", "ii\u00b0", "III", "iv", "v", "VI", "VII"]
            degree_names = degree_names_major if best_mode == "major" else degree_names_minor

            # Quality for each scale degree
            if best_mode == "major":
                degree_qualities = ["major", "minor", "minor", "major", "major", "minor", "dim"]
            else:
                degree_qualities = ["minor", "dim", "major", "minor", "minor", "major", "major"]

            diatonic_chords = []
            for deg_idx in range(7):
                root_pc = scale_pcs[deg_idx]
                quality = degree_qualities[deg_idx]
                intervals = CHORD_INTERVALS[quality]
                chord_midi = [(4 + 1) * 12 + root_pc + iv for iv in intervals]
                chord_midi = [m for m in chord_midi if 0 <= m <= 127]
                diatonic_chords.append({
                    "degree": degree_names[deg_idx],
                    "root": NOTE_NAMES[root_pc],
                    "quality": quality,
                    "midi_numbers": chord_midi,
                    "note_names": [_midi_to_name(m) for m in chord_midi],
                })

            # Segment melody into groups (every 4 notes or so) and suggest
            # the best-fitting chord for each segment
            segment_size = max(1, len(notes) // 4) if len(notes) >= 4 else len(notes)
            suggestions = []
            for seg_idx in range(0, len(notes), segment_size):
                segment = notes[seg_idx:seg_idx + segment_size]
                seg_pcs = set(n % 12 for n in segment if 0 <= n <= 127)

                # Score each diatonic chord
                best_chord = diatonic_chords[0]
                best_chord_score = -1
                for chord_info in diatonic_chords:
                    chord_pcs = set(m % 12 for m in chord_info["midi_numbers"])
                    # Count melody notes that are chord tones
                    score = len(seg_pcs & chord_pcs)
                    if score > best_chord_score:
                        best_chord_score = score
                        best_chord = chord_info

                suggestions.append({
                    "segment_start_index": seg_idx,
                    "segment_notes": segment,
                    "suggested_chord": f"{best_chord['root']}{best_chord['quality']}",
                    "degree": best_chord["degree"],
                    "chord_midi_numbers": best_chord["midi_numbers"],
                    "chord_note_names": best_chord["note_names"],
                })

            return json.dumps({
                "detected_key": key_name,
                "detected_mode": best_mode,
                "key_confidence_score": best_score,
                "total_melody_notes": len(notes),
                "diatonic_chords": diatonic_chords,
                "suggested_harmonization": suggestions,
            }, indent=2)
        except Exception as e:
            logger.error(f"Error suggesting chords for melody: {e}")
            return json.dumps({"error": str(e)})


# ---------------------------------------------------------------------------
# Drum pattern definitions (module-level helper)
# ---------------------------------------------------------------------------


def _get_drum_pattern(style: str, steps_per_bar: int):
    """Return drum patterns as {midi_pitch: [(step, velocity), ...]}.

    All patterns assume a 16-step grid per bar (for 4/4 time).
    If steps_per_bar differs, patterns are scaled/truncated.
    """
    kick = GM_DRUMS["kick"]
    snare = GM_DRUMS["snare"]
    closed_hh = GM_DRUMS["closed_hh"]
    open_hh = GM_DRUMS["open_hh"]
    clap = GM_DRUMS["clap"]
    rim = GM_DRUMS["rim"]
    tom_low = GM_DRUMS["tom_low"]
    tom_mid = GM_DRUMS["tom_mid"]
    tom_hi = GM_DRUMS["tom_hi"]
    crash = GM_DRUMS["crash"]
    ride = GM_DRUMS["ride"]

    # All patterns defined for 16-step grid
    raw_patterns = None

    if style == "basic":
        raw_patterns = {
            kick: [(0, 100), (8, 100)],
            snare: [(4, 100), (12, 100)],
            closed_hh: [(i, 80 if i % 4 == 0 else 60) for i in range(0, 16, 2)],
        }

    elif style == "rock":
        raw_patterns = {
            kick: [(0, 110), (6, 90), (8, 100)],
            snare: [(4, 110), (12, 110)],
            closed_hh: [(i, 90 if i % 4 == 0 else 70) for i in range(16)],
            crash: [(0, 90)],
        }

    elif style == "hiphop":
        raw_patterns = {
            kick: [(0, 110), (3, 80), (7, 90), (10, 85)],
            snare: [(4, 100), (12, 100)],
            closed_hh: [(i, 75 if i % 2 == 0 else 55) for i in range(16)],
            open_hh: [(6, 70), (14, 70)],
        }

    elif style == "trap":
        raw_patterns = {
            kick: [(0, 120), (7, 100), (11, 90)],
            snare: [(4, 110), (12, 110)],
            closed_hh: [(i, 70 + (i % 3) * 10) for i in range(16)],  # Rapid hi-hats
            open_hh: [(3, 60), (7, 60), (11, 60), (15, 60)],
            clap: [(4, 100), (12, 100)],
        }

    elif style == "house":
        raw_patterns = {
            kick: [(0, 110), (4, 110), (8, 110), (12, 110)],  # Four-on-the-floor
            clap: [(4, 100), (12, 100)],
            closed_hh: [(i, 80) for i in range(1, 16, 2)],  # Offbeat hi-hats
            open_hh: [(2, 85), (6, 85), (10, 85), (14, 85)],
        }

    elif style == "dnb":
        raw_patterns = {
            kick: [(0, 120), (10, 100)],
            snare: [(4, 110), (13, 105)],
            closed_hh: [(i, 80) for i in range(0, 16, 2)],
            ride: [(i, 70) for i in range(1, 16, 4)],
        }

    elif style == "reggaeton":
        raw_patterns = {
            kick: [(0, 110), (4, 90), (8, 110), (12, 90)],
            snare: [(3, 100), (7, 100), (11, 100), (15, 100)],  # Dembow pattern
            closed_hh: [(i, 75) for i in range(0, 16, 2)],
            rim: [(3, 85), (7, 85), (11, 85), (15, 85)],
        }

    elif style == "bossa_nova":
        raw_patterns = {
            kick: [(0, 90), (6, 80), (10, 85)],
            rim: [(2, 75), (5, 70), (8, 75), (12, 70), (15, 65)],
            closed_hh: [(i, 60) for i in range(0, 16, 2)],
        }

    elif style == "jazz_swing":
        # Swing feel on ride cymbal (tripled feel — steps 0,3,4,7,8,11,12,15)
        raw_patterns = {
            ride: [
                (0, 95), (3, 70), (4, 90), (7, 70),
                (8, 95), (11, 70), (12, 90), (15, 70),
            ],
            kick: [(0, 70), (10, 60)],  # Feathered kick
            closed_hh: [(4, 65), (12, 65)],  # Hi-hat on 2 and 4
            snare: [(7, 50), (15, 55)],  # Ghost notes
        }

    elif style == "funk":
        raw_patterns = {
            kick: [(0, 110), (3, 80), (6, 90), (10, 100), (13, 80)],
            snare: [(4, 110), (12, 110)],
            closed_hh: [(i, 85 if i % 2 == 0 else 65) for i in range(16)],
            open_hh: [(7, 80), (15, 80)],
            clap: [(4, 70)],
        }

    else:
        return None

    # Scale to actual steps_per_bar if not 16
    if steps_per_bar != 16:
        scale_factor = steps_per_bar / 16.0
        scaled = {}
        for pitch, hits in raw_patterns.items():
            scaled[pitch] = [
                (round(step * scale_factor), vel)
                for step, vel in hits
                if round(step * scale_factor) < steps_per_bar
            ]
        return scaled

    return raw_patterns
