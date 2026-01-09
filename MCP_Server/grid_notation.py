"""
Grid Notation - ASCII notation that compiles to MIDI

Write drum patterns like a human:

    KK|o---o---|o---o-o-|
    SN|----o---|----o---|
    HC|x-x-x-x-|x-x-x-x-|

And this module converts it to MIDI note events, or vice versa.

"Notation is compression. Good notation is lossy in the right places."
"""

import re
from typing import Optional


# =============================================================================
# DRUM CHANNEL MAPPINGS
# =============================================================================

# Row labels -> GM Drum MIDI pitch
DRUM_LABELS = {
    # Kicks
    'KK': 36, 'KICK': 36, 'BD': 36, 'K': 36,
    # Snares
    'SN': 38, 'SNARE': 38, 'SD': 38, 'S': 38,
    # Clap
    'CL': 39, 'CLAP': 39, 'CP': 39,
    # Sidestick
    'SS': 37, 'STICK': 37, 'RS': 37,
    # Hi-hat
    'HC': 42, 'HH': 42, 'CHH': 42,  # Closed
    'HO': 46, 'OHH': 46, 'OH': 46,  # Open
    'HP': 44, 'PHH': 44,             # Pedal
    # Toms
    'LT': 45, 'LTOM': 45,  # Low tom
    'MT': 47, 'MTOM': 47,  # Mid tom
    'HT': 50, 'HTOM': 50,  # High tom
    'FT': 41, 'FTOM': 41,  # Floor tom
    # Cymbals
    'CR': 49, 'CRASH': 49, 'CC': 49,
    'RD': 51, 'RIDE': 51, 'RC': 51,
    'RB': 53, 'BELL': 53,
    # Latin percussion
    'CB': 56, 'COWBELL': 56,
    'CG': 62, 'CONGA': 62,
    'CGH': 63, 'CONGAH': 63,
    'CGL': 64, 'CONGAL': 64,
    'TH': 65, 'TIMB': 65,
    'TL': 66, 'TIMBL': 66,
    'AH': 67, 'AGOGO': 67,
    'AL': 68, 'AGOGOL': 68,
    'CA': 69, 'CABASA': 69,
    'MA': 70, 'MARACAS': 70,
    'SH': 82, 'SHAKER': 82,
    # Rimshot
    'RM': 40, 'RIM': 40,
}

# Note symbols and their velocity mappings
DRUM_SYMBOLS = {
    # Hits at various velocities
    'o': 100,   # Normal hit
    'O': 127,   # Accent (loud)
    '.': 50,    # Ghost note (quiet)
    '+': 85,    # Medium accent
    '*': 110,   # Strong accent

    # Hi-hat specific
    'x': 90,    # Closed hi-hat hit
    'X': 120,   # Open hi-hat / accent

    # Rests / sustain
    '-': 0,     # Rest (no hit)
    ' ': 0,     # Space = rest
    '_': 0,     # Underscore = rest
}

# Preferred labels for output (2-letter, consistent)
PREFERRED_LABELS = {
    36: 'KK', 35: 'KK',  # Kicks
    38: 'SN', 40: 'SN',  # Snares
    37: 'SS',            # Sidestick
    39: 'CL',            # Clap
    42: 'HC', 44: 'HC',  # Hi-hat closed
    46: 'HO',            # Hi-hat open
    45: 'LT', 47: 'LT',  # Low tom
    48: 'MT',            # Mid tom
    50: 'HT',            # High tom
    41: 'FT', 43: 'FT',  # Floor tom
    49: 'CR', 57: 'CR',  # Crash
    51: 'RD', 59: 'RD',  # Ride
    53: 'RB',            # Ride bell
    56: 'CB',            # Cowbell
}

# Melodic note names
NOTE_NAMES = {
    'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11,
}
ACCIDENTALS = {'#': 1, 'b': -1, '': 0}


# =============================================================================
# GRID PARSER - DRUMS
# =============================================================================

def parse_drum_grid(grid: str, steps_per_beat: int = 4) -> list[dict]:
    """
    Parse ASCII drum grid to MIDI note events.

    Input format:
        KK|o---o---|o---o-o-|
        SN|--o---o-|--o---o-|
        HC|x-x-x-x-|x-x-x-x-|

    Args:
        grid: Multi-line ASCII grid string
        steps_per_beat: How many grid cells per beat (4 = 16th notes)

    Returns:
        List of note dicts: {"pitch", "start_time", "duration", "velocity"}
    """
    notes = []
    lines = grid.strip().split('\n')

    for line in lines:
        line = line.strip()
        if not line or line.startswith('#'):
            continue

        # Parse "LABEL|pattern|pattern|..."
        match = re.match(r'^([A-Z]+)\s*\|(.+)', line, re.IGNORECASE)
        if not match:
            continue

        label = match.group(1).upper()
        pattern_str = match.group(2)

        # Get MIDI pitch for this drum
        pitch = DRUM_LABELS.get(label)
        if pitch is None:
            continue

        # Parse pattern
        step = 0
        for char in pattern_str:
            if char == '|':
                continue  # Bar separator

            velocity = DRUM_SYMBOLS.get(char, 0)

            if velocity > 0:
                start_time = step / steps_per_beat
                duration = 1 / steps_per_beat

                notes.append({
                    'pitch': pitch,
                    'start_time': start_time,
                    'duration': duration,
                    'velocity': velocity
                })

            step += 1

    return notes


def parse_melodic_grid(grid: str, base_octave: int = 4, steps_per_beat: int = 4) -> list[dict]:
    """
    Parse melodic ASCII grid (piano roll style) to MIDI notes.

    Input format:
        G4|----o---|--------|
        E4|--o-----|oooo----|
        C4|o-------|----oooo|

    Args:
        grid: Multi-line ASCII grid
        base_octave: Default octave if not specified in label
        steps_per_beat: Grid resolution

    Returns:
        List of note dicts
    """
    notes = []
    lines = grid.strip().split('\n')

    for line in lines:
        line = line.strip()
        if not line or line.startswith('#') or line.startswith(' '):
            continue

        # Parse label: "C4|..." or "C|..." or "60|..."
        match = re.match(r'^([A-Ga-g][#b]?)(\d+)?\s*\|(.+)', line)
        if not match:
            # Try numeric pitch
            match = re.match(r'^(\d+)\s*\|(.+)', line)
            if match:
                pitch = int(match.group(1))
                pattern_str = match.group(2)
            else:
                continue
        else:
            note_name = match.group(1).upper()
            octave = int(match.group(2)) if match.group(2) else base_octave
            pattern_str = match.group(3)

            # Convert to MIDI pitch
            semitone = NOTE_NAMES.get(note_name[0], 0)
            if len(note_name) > 1:
                semitone += ACCIDENTALS.get(note_name[1], 0)
            pitch = semitone + (octave + 1) * 12

        # Parse pattern
        step = 0
        note_start = None
        velocity = 90

        for char in pattern_str:
            if char == '|':
                continue

            is_note = char in ('o', 'O', '.', 'x', '*')

            if is_note:
                if note_start is None:
                    note_start = step
                    if char in ('O', '*'):
                        velocity = 110
                    elif char == '.':
                        velocity = 60
                    else:
                        velocity = 90
            else:
                if note_start is not None:
                    start_time = note_start / steps_per_beat
                    duration = (step - note_start) / steps_per_beat

                    notes.append({
                        'pitch': pitch,
                        'start_time': start_time,
                        'duration': duration,
                        'velocity': velocity
                    })
                    note_start = None

            step += 1

        # Handle note extending to end
        if note_start is not None:
            start_time = note_start / steps_per_beat
            duration = (step - note_start) / steps_per_beat
            notes.append({
                'pitch': pitch,
                'start_time': start_time,
                'duration': duration,
                'velocity': velocity
            })

    return notes


# =============================================================================
# NOTES -> GRID (for display)
# =============================================================================

def notes_to_drum_grid(
    notes: list[dict],
    steps_per_beat: int = 4,
    num_bars: int = None
) -> str:
    """
    Convert MIDI notes to ASCII drum grid.

    Args:
        notes: List of note dicts from Ableton
        steps_per_beat: Grid resolution
        num_bars: Number of bars (auto-detect if None)

    Returns:
        ASCII grid string
    """
    if not notes:
        return "(empty)"

    # Find clip length
    max_time = max(n.get('start_time', 0) + n.get('duration', 0.25) for n in notes)
    if num_bars is None:
        num_bars = max(1, int((max_time + 3.9) // 4))

    total_steps = num_bars * 4 * steps_per_beat

    # Group notes by pitch
    pitch_notes = {}
    for note in notes:
        pitch = note.get('pitch', 36)
        if pitch not in pitch_notes:
            pitch_notes[pitch] = []
        pitch_notes[pitch].append(note)

    # Standard drum order for display
    display_order = ['HC', 'HO', 'RD', 'CR', 'SN', 'CL', 'RM', 'KK', 'HT', 'MT', 'LT', 'FT']
    pitch_order = [DRUM_LABELS.get(label, 0) for label in display_order]

    # Build grid lines
    lines = []

    for pitch in sorted(pitch_notes.keys(), key=lambda p: pitch_order.index(p) if p in pitch_order else 99):
        label = PREFERRED_LABELS.get(pitch, f'{pitch:02d}')

        # Initialize row
        row = ['-'] * total_steps

        for note in pitch_notes[pitch]:
            step = int(note.get('start_time', 0) * steps_per_beat)
            if step < total_steps:
                vel = note.get('velocity', 100)
                if vel > 110:
                    row[step] = 'O'
                elif vel > 70:
                    row[step] = 'o'
                else:
                    row[step] = '.'

        # Format with bar separators
        formatted = f"{label}|"
        for i, char in enumerate(row):
            formatted += char
            if (i + 1) % (4 * steps_per_beat) == 0:
                formatted += '|'

        lines.append(formatted)

    # Add beat markers
    beat_line = "  |"
    for bar in range(num_bars):
        for beat in range(1, 5):
            beat_line += str(beat)
            beat_line += ' ' * (steps_per_beat - 1)
        beat_line += '|'
    lines.append(beat_line)

    return '\n'.join(lines)


def notes_to_melodic_grid(
    notes: list[dict],
    steps_per_beat: int = 4,
    num_bars: int = None
) -> str:
    """
    Convert MIDI notes to ASCII melodic grid.

    Args:
        notes: List of note dicts
        steps_per_beat: Grid resolution
        num_bars: Number of bars (auto-detect if None)

    Returns:
        ASCII grid string
    """
    if not notes:
        return "(empty)"

    # Find clip length
    max_time = max(n.get('start_time', 0) + n.get('duration', 0.25) for n in notes)
    if num_bars is None:
        num_bars = max(1, int((max_time + 3.9) // 4))

    total_steps = num_bars * 4 * steps_per_beat

    # Group notes by pitch
    pitch_notes = {}
    for note in notes:
        pitch = note.get('pitch', 60)
        if pitch not in pitch_notes:
            pitch_notes[pitch] = []
        pitch_notes[pitch].append(note)

    # Build grid lines (highest pitch first)
    lines = []
    note_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

    for pitch in sorted(pitch_notes.keys(), reverse=True):
        # Convert pitch to note name
        octave = (pitch // 12) - 1
        note_idx = pitch % 12
        note_name = note_names[note_idx]
        label = f"{note_name}{octave}".ljust(3)

        # Initialize row
        row = ['-'] * total_steps

        for note in pitch_notes[pitch]:
            start_step = int(note.get('start_time', 0) * steps_per_beat)
            dur_steps = max(1, int(note.get('duration', 0.25) * steps_per_beat))
            vel = note.get('velocity', 100)

            # Fill in the note
            symbol = 'O' if vel > 110 else ('.' if vel < 70 else 'o')
            for i in range(dur_steps):
                if start_step + i < total_steps:
                    row[start_step + i] = symbol

        # Format with bar separators
        formatted = f"{label}|"
        for i, char in enumerate(row):
            formatted += char
            if (i + 1) % (4 * steps_per_beat) == 0:
                formatted += '|'

        lines.append(formatted)

    # Add beat markers
    beat_line = "   |"
    for bar in range(num_bars):
        for beat in range(1, 5):
            beat_line += str(beat)
            beat_line += ' ' * (steps_per_beat - 1)
        beat_line += '|'
    lines.append(beat_line)

    return '\n'.join(lines)


# =============================================================================
# AUTO-DETECTION
# =============================================================================

def is_drum_track(notes: list[dict]) -> bool:
    """
    Detect if notes are likely from a drum track.
    Drum tracks typically use pitches 35-81 (GM drum map range).
    """
    if not notes:
        return False

    pitches = set(n.get('pitch', 60) for n in notes)
    drum_pitches = sum(1 for p in pitches if 35 <= p <= 81)

    # If most pitches are in drum range and there are multiple distinct pitches
    # clustered in that range, it's likely drums
    return drum_pitches >= len(pitches) * 0.8 and len(pitches) > 1


def notes_to_grid(notes: list[dict], is_drums: bool = None, steps_per_beat: int = 4) -> str:
    """
    Convert notes to appropriate grid format.

    Args:
        notes: List of note dicts
        is_drums: Force drum mode (auto-detect if None)
        steps_per_beat: Grid resolution

    Returns:
        ASCII grid string
    """
    if is_drums is None:
        is_drums = is_drum_track(notes)

    if is_drums:
        return notes_to_drum_grid(notes, steps_per_beat)
    else:
        return notes_to_melodic_grid(notes, steps_per_beat)


def parse_grid(grid: str, is_drums: bool = None, steps_per_beat: int = 4) -> list[dict]:
    """
    Parse grid notation to notes.

    Args:
        grid: ASCII grid string
        is_drums: Force drum mode (auto-detect if None)
        steps_per_beat: Grid resolution

    Returns:
        List of note dicts
    """
    # Auto-detect based on labels
    if is_drums is None:
        lines = grid.strip().split('\n')
        for line in lines:
            match = re.match(r'^([A-Z]+)\s*\|', line, re.IGNORECASE)
            if match:
                label = match.group(1).upper()
                if label in DRUM_LABELS:
                    is_drums = True
                    break
        if is_drums is None:
            is_drums = False

    if is_drums:
        return parse_drum_grid(grid, steps_per_beat)
    else:
        return parse_melodic_grid(grid, steps_per_beat)
