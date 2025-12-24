#!/usr/bin/env python3
"""
ALS Automation Injector

Injects energy automation envelopes into Ableton Live Set (.als) files.
ALS files are gzip-compressed XML.

This module injects MIDI CC clip envelopes (CC 20-27) for 8 energy features:
- CC 20: RMS Energy (overall loudness)
- CC 21: Spectral Centroid (brightness)
- CC 22: Spectral Flux (rate of change)
- CC 23: Band Sub (20-60 Hz)
- CC 24: Band Bass (60-250 Hz)
- CC 25: Band Low-Mid (250-500 Hz)
- CC 26: Band High-Mid (500-2000 Hz)
- CC 27: Band High (2000-20000 Hz)

MIDI CC automation in Ableton is stored as clip-level envelopes inside
<MidiClip> -> <Envelopes> -> <ClipEnvelope> elements.
"""

import gzip
import json
import logging
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# CC mapping for energy features
# Note: Ableton displays CC numbers with a -2 offset from ControllerTargets index
# So we target CC 22-29 in the file to get CC 20-27 in Ableton's UI
ENERGY_CC_MAP = {
    'rms': 22,        # displays as CC 20
    'centroid': 23,   # displays as CC 21
    'flux': 24,       # displays as CC 22
    'band_sub': 25,   # displays as CC 23
    'band_bass': 26,  # displays as CC 24
    'band_low_mid': 27,   # displays as CC 25
    'band_high_mid': 28,  # displays as CC 26
    'band_high': 29,      # displays as CC 27
}

ENERGY_CC_NAMES = {
    22: 'RMS Energy',
    23: 'Brightness',
    24: 'Flux',
    25: 'Sub',
    26: 'Bass',
    27: 'Low-Mid',
    28: 'High-Mid',
    29: 'High',
}

# Special initial time marker used by Ableton
INITIAL_TIME_MARKER = -63072000


def decompress_als(als_path: str) -> str:
    """Decompress ALS file and return XML string."""
    with gzip.open(als_path, 'rb') as f:
        return f.read().decode('utf-8')


def compress_als(xml_content: str, als_path: str):
    """Compress XML string and write to ALS file."""
    with gzip.open(als_path, 'wb') as f:
        f.write(xml_content.encode('utf-8'))


def find_midi_track_by_name(root: ET.Element, track_name: str) -> Optional[ET.Element]:
    """Find a MIDI track by name."""
    for track in root.iter('MidiTrack'):
        name_elem = track.find('.//EffectiveName')
        if name_elem is not None:
            name = name_elem.get('Value', '')
            if track_name.lower() in name.lower():
                return track
    return None


def get_controller_target_ids(track: ET.Element, cc_numbers: list[int]) -> dict[int, str]:
    """
    Extract PointeeIds for the specified CC numbers from the track's MidiControllers section.

    The MidiControllers section contains ControllerTargets.N elements where N is the CC number.
    Each element has an Id attribute that serves as the PointeeId for clip envelopes.

    Returns:
        Dict mapping CC number to its PointeeId
    """
    cc_to_pointee = {}

    # Find the MidiControllers section
    midi_controllers = track.find('.//MidiControllers')
    if midi_controllers is None:
        logger.warning("No MidiControllers section found in track")
        return cc_to_pointee

    for cc_num in cc_numbers:
        # Look for ControllerTargets.N element
        target_elem = midi_controllers.find(f'ControllerTargets.{cc_num}')
        if target_elem is not None:
            pointee_id = target_elem.get('Id')
            if pointee_id:
                cc_to_pointee[cc_num] = pointee_id
                logger.debug(f"CC {cc_num} -> PointeeId {pointee_id}")
        else:
            logger.warning(f"ControllerTargets.{cc_num} not found in MidiControllers")

    return cc_to_pointee


def generate_clip_envelope_xml(
    envelope_id: int,
    pointee_id: str,
    times: list[float],
    values: list[float],
    bpm: float,
    clip_start_beat: float,
    clip_end_beat: float,
    indent: str = "\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t"
) -> str:
    """
    Generate XML for a single ClipEnvelope.

    Args:
        envelope_id: Unique ID for this envelope within the clip
        pointee_id: ID of the CC target (from ControllerTargets.N)
        times: List of timestamps in seconds
        values: List of values (0-1 range, will be scaled to 0-127 for CC)
        bpm: Tempo for converting times to beats
        clip_start_beat: Start beat of the clip in the arrangement
        clip_end_beat: End beat of the clip in the arrangement
        indent: Base indentation for the XML
    """
    # Filter and convert times/values to clip-relative beats
    events = []
    event_id = 0

    # Add initial value marker
    if values:
        initial_value = values[0] * 127.0
        events.append(f'{indent}\t\t\t<FloatEvent Id="{event_id}" Time="{INITIAL_TIME_MARKER}" Value="{initial_value:.6f}" />')
        event_id += 1

    # Add events within the clip range
    for t, v in zip(times, values):
        # Convert time (seconds) to absolute beat position
        abs_beat = t * bpm / 60.0

        # Check if this point falls within the clip
        if clip_start_beat <= abs_beat < clip_end_beat:
            # Convert to clip-relative beat time
            rel_beat = abs_beat - clip_start_beat
            # Scale value to 0-127
            scaled_value = max(0.0, min(127.0, v * 127.0))
            events.append(f'{indent}\t\t\t<FloatEvent Id="{event_id}" Time="{rel_beat:.6f}" Value="{scaled_value:.6f}" />')
            event_id += 1

    events_xml = '\n'.join(events)

    # Calculate clip length for ScrollerTimePreserver
    clip_length = clip_end_beat - clip_start_beat

    return f'''{indent}<ClipEnvelope Id="{envelope_id}">
{indent}\t<EnvelopeTarget>
{indent}\t\t<PointeeId Value="{pointee_id}" />
{indent}\t</EnvelopeTarget>
{indent}\t<Automation>
{indent}\t\t<Events>
{events_xml}
{indent}\t\t</Events>
{indent}\t\t<AutomationTransformViewState>
{indent}\t\t\t<IsTransformPending Value="false" />
{indent}\t\t\t<TimeAndValueTransforms />
{indent}\t\t</AutomationTransformViewState>
{indent}\t</Automation>
{indent}\t<LoopSlot>
{indent}\t\t<Value />
{indent}\t</LoopSlot>
{indent}\t<ScrollerTimePreserver>
{indent}\t\t<LeftTime Value="0" />
{indent}\t\t<RightTime Value="{clip_length:.6f}" />
{indent}\t</ScrollerTimePreserver>
{indent}</ClipEnvelope>'''


def get_clip_info(clip: ET.Element) -> dict:
    """Extract clip timing information from a MidiClip element."""
    time = float(clip.get('Time', 0))

    current_start = clip.find('CurrentStart')
    current_end = clip.find('CurrentEnd')

    start = float(current_start.get('Value', 0)) if current_start is not None else time
    end = float(current_end.get('Value', 0)) if current_end is not None else start

    name_elem = clip.find('Name')
    name = name_elem.get('Value', 'Unknown') if name_elem is not None else 'Unknown'

    return {
        'time': time,
        'start': start,
        'end': end,
        'name': name,
        'length': end - start
    }


def inject_envelopes_into_clip(
    xml_content: str,
    clip_time: float,
    clip_start: float,
    clip_end: float,
    cc_to_pointee: dict[int, str],
    feature_data: dict[str, list[float]],
    times: list[float],
    bpm: float,
    features: list[str]
) -> str:
    """
    Inject ClipEnvelope elements into a specific MidiClip's Envelopes section.

    Uses regex-based text manipulation for reliability (following als_warp_injector pattern).

    Note: Ableton uses a nested structure:
        <Envelopes>
            <Envelopes>  <!-- Inner container holds ClipEnvelope elements -->
                <ClipEnvelope>...</ClipEnvelope>
            </Envelopes>
        </Envelopes>
    """
    # Build the new envelopes XML
    envelope_xmls = []
    envelope_id = 0

    for feature in features:
        if feature not in ENERGY_CC_MAP:
            continue

        cc_num = ENERGY_CC_MAP[feature]
        if cc_num not in cc_to_pointee:
            logger.warning(f"No PointeeId for CC {cc_num} ({feature})")
            continue

        values = feature_data.get(feature, [])
        if not values:
            continue

        pointee_id = cc_to_pointee[cc_num]
        envelope_xml = generate_clip_envelope_xml(
            envelope_id=envelope_id,
            pointee_id=pointee_id,
            times=times,
            values=values,
            bpm=bpm,
            clip_start_beat=clip_start,
            clip_end_beat=clip_end
        )
        envelope_xmls.append(envelope_xml)
        envelope_id += 1

    if not envelope_xmls:
        return xml_content

    # Combine all envelope XML
    all_envelopes_xml = '\n'.join(envelope_xmls)

    clip_time_int = int(clip_time)

    # Ableton uses nested <Envelopes><Envelopes>...</Envelopes></Envelopes> structure
    # We need to inject into the INNER <Envelopes> container

    # Pattern for empty inner Envelopes: <Envelopes><Envelopes /></Envelopes>
    # Or: <Envelopes>\n...<Envelopes />\n...</Envelopes>
    pattern_empty_inner = rf'(<MidiClip[^>]+Time="{clip_time_int}"[^>]*>.*?<Envelopes>\s*)<Envelopes\s*/>'

    def replace_empty_inner(match):
        prefix = match.group(1)
        indent = "\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t"
        return f'{prefix}<Envelopes>\n{all_envelopes_xml}\n{indent}</Envelopes>'

    modified_xml = re.sub(pattern_empty_inner, replace_empty_inner, xml_content, flags=re.DOTALL, count=1)

    if modified_xml != xml_content:
        logger.debug("Injected into empty inner Envelopes")
        return modified_xml

    # Pattern for populated inner Envelopes: <Envelopes><Envelopes>...</Envelopes></Envelopes>
    # Match: outer <Envelopes>, then inner <Envelopes>content</Envelopes>
    pattern_populated_inner = rf'(<MidiClip[^>]+Time="{clip_time_int}"[^>]*>.*?<Envelopes>\s*<Envelopes>)(.*?)(</Envelopes>\s*</Envelopes>)'

    def replace_populated_inner(match):
        prefix = match.group(1)  # Up to and including inner <Envelopes>
        existing = match.group(2)  # Existing ClipEnvelope elements
        suffix = match.group(3)  # </Envelopes></Envelopes>
        indent = "\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t"
        # Append new envelopes after existing ones
        return f'{prefix}{existing}\n{all_envelopes_xml}\n{indent}{suffix}'

    modified_xml = re.sub(pattern_populated_inner, replace_populated_inner, xml_content, flags=re.DOTALL, count=1)

    if modified_xml != xml_content:
        logger.debug("Injected into populated inner Envelopes")
        return modified_xml

    # Fallback: Try single-level Envelopes structure (older format or empty clip)
    pattern_empty_single = rf'(<MidiClip[^>]+Time="{clip_time_int}"[^>]*>.*?)<Envelopes\s*/>'

    def replace_empty_single(match):
        clip_section = match.group(1)
        indent = "\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t"
        # Create both outer and inner Envelopes structure
        return f'{clip_section}<Envelopes>\n{indent}\t<Envelopes>\n{all_envelopes_xml}\n{indent}\t</Envelopes>\n{indent}</Envelopes>'

    modified_xml = re.sub(pattern_empty_single, replace_empty_single, xml_content, flags=re.DOTALL, count=1)

    if modified_xml != xml_content:
        logger.debug("Injected into empty single-level Envelopes")

    return modified_xml


def inject_energy_automation(
    als_path: str,
    energy_data: dict,
    track_name: str = "Structure",
    output_path: str = None,
    features: list = None
) -> dict:
    """
    Inject energy automation envelopes into MIDI clips in an ALS file.

    Args:
        als_path: Path to the input ALS file
        energy_data: Output from extract_energy_features() with times, rms, centroid, flux, bands
        track_name: Name of the MIDI track to add automation to
        output_path: Path for output ALS file (default: overwrites input)
        features: List of features to inject (default: all 8). Options:
                  'rms', 'centroid', 'flux', 'band_sub', 'band_bass',
                  'band_low_mid', 'band_high_mid', 'band_high'

    Returns:
        Dict with status and details of injected envelopes
    """
    if output_path is None:
        output_path = als_path

    if features is None:
        features = list(ENERGY_CC_MAP.keys())

    logger.info(f"Decompressing {als_path}...")
    xml_content = decompress_als(als_path)

    # Parse XML to find track and clips
    root = ET.fromstring(xml_content)

    # Find the target MIDI track
    track = find_midi_track_by_name(root, track_name)
    if track is None:
        return {
            "success": False,
            "error": f"MIDI track '{track_name}' not found in ALS file"
        }

    track_id = track.get('Id')
    logger.info(f"Found track '{track_name}' with ID {track_id}")

    # Get CC to PointeeId mapping
    cc_numbers = [ENERGY_CC_MAP[f] for f in features if f in ENERGY_CC_MAP]
    cc_to_pointee = get_controller_target_ids(track, cc_numbers)

    if not cc_to_pointee:
        return {
            "success": False,
            "error": "Could not find ControllerTargets for requested CC numbers"
        }

    logger.info(f"Found PointeeIds for {len(cc_to_pointee)} CC numbers")

    # Extract data from energy_data
    times = energy_data.get('times', [])
    bpm = energy_data.get('bpm', 120.0)

    if not times:
        return {
            "success": False,
            "error": "No time data in energy_data"
        }

    # Map feature names to their data arrays
    feature_data = {
        'rms': energy_data.get('rms', []),
        'centroid': energy_data.get('centroid', []),
        'flux': energy_data.get('flux', []),
    }

    # Add band data
    bands = energy_data.get('bands', [])
    band_names = ['band_sub', 'band_bass', 'band_low_mid', 'band_high_mid', 'band_high']
    for i, band_name in enumerate(band_names):
        if i < len(bands):
            feature_data[band_name] = bands[i]
        else:
            feature_data[band_name] = []

    # Find all MidiClips in the arrangement
    clips_info = []
    for clip in track.iter('MidiClip'):
        info = get_clip_info(clip)
        clips_info.append(info)
        logger.info(f"  Found clip: {info['name']} at beats {info['start']}-{info['end']}")

    if not clips_info:
        return {
            "success": False,
            "error": f"No MIDI clips found in track '{track_name}'"
        }

    # Inject envelopes into each clip
    modified_xml = xml_content
    clips_modified = 0

    for clip_info in clips_info:
        logger.info(f"Injecting envelopes into clip at {clip_info['start']}-{clip_info['end']}...")

        modified_xml = inject_envelopes_into_clip(
            xml_content=modified_xml,
            clip_time=clip_info['time'],
            clip_start=clip_info['start'],
            clip_end=clip_info['end'],
            cc_to_pointee=cc_to_pointee,
            feature_data=feature_data,
            times=times,
            bpm=bpm,
            features=features
        )

        if modified_xml != xml_content:
            clips_modified += 1
            xml_content = modified_xml

    # Write the modified ALS file
    logger.info(f"Compressing and writing to {output_path}...")
    compress_als(modified_xml, output_path)

    # Build summary of what was injected
    envelopes_created = []
    for feature in features:
        if feature in ENERGY_CC_MAP:
            cc_num = ENERGY_CC_MAP[feature]
            if cc_num in cc_to_pointee:
                values = feature_data.get(feature, [])
                if values:
                    envelopes_created.append({
                        "feature": feature,
                        "cc": cc_num,
                        "cc_name": ENERGY_CC_NAMES[cc_num],
                        "point_count": len(values),
                        "pointee_id": cc_to_pointee[cc_num]
                    })

    return {
        "success": True,
        "track_name": track_name,
        "clips_modified": clips_modified,
        "envelopes_per_clip": len(envelopes_created),
        "envelopes": envelopes_created,
        "output_path": output_path
    }


def export_energy_for_m4l(
    energy_data: dict,
    output_path: str,
    features: list = None
) -> str:
    """
    Export energy data as JSON for use by a Max for Live device.

    The M4L device can read this JSON and draw automation curves.

    Args:
        energy_data: Output from extract_energy_features()
        output_path: Path to save the JSON file
        features: List of features to include (default: all)

    Returns:
        Path to the saved JSON file
    """
    if features is None:
        features = list(ENERGY_CC_MAP.keys())

    times = energy_data.get('times', [])
    bpm = energy_data.get('bpm', 120.0)

    # Build feature data
    feature_values = {
        'rms': energy_data.get('rms', []),
        'centroid': energy_data.get('centroid', []),
        'flux': energy_data.get('flux', []),
    }

    bands = energy_data.get('bands', [])
    band_names = ['band_sub', 'band_bass', 'band_low_mid', 'band_high_mid', 'band_high']
    for i, band_name in enumerate(band_names):
        if i < len(bands):
            feature_values[band_name] = bands[i]

    # Build output structure
    output = {
        "bpm": bpm,
        "sample_rate": energy_data.get('hop_length_samples', 512),
        "count": len(times),
        "times": times,
        "features": {}
    }

    for feature in features:
        if feature in feature_values and feature_values[feature]:
            output["features"][feature] = {
                "cc": ENERGY_CC_MAP.get(feature, 0),
                "name": ENERGY_CC_NAMES.get(ENERGY_CC_MAP.get(feature, 0), feature),
                "values": feature_values[feature]
            }

    with open(output_path, 'w') as f:
        json.dump(output, f)

    logger.info(f"Exported energy data for M4L to {output_path}")
    return output_path


if __name__ == '__main__':
    import argparse

    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(
        description='Inject energy automation into Ableton Live Set files'
    )
    parser.add_argument('als_file', help='Input ALS file path')
    parser.add_argument('energy_json', help='Energy data JSON file (from analyze_energy)')
    parser.add_argument('-o', '--output', help='Output ALS file (default: overwrite input)')
    parser.add_argument('-t', '--track', default='Structure',
                        help='MIDI track name to add automation to')
    parser.add_argument('--features', nargs='+',
                        help='Features to inject (default: all)')

    args = parser.parse_args()

    # Load energy data
    with open(args.energy_json, 'r') as f:
        energy_data = json.load(f)

    result = inject_energy_automation(
        args.als_file,
        energy_data,
        args.track,
        args.output,
        args.features
    )

    print(json.dumps(result, indent=2))
