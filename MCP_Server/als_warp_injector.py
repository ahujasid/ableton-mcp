#!/usr/bin/env python3
"""
ALS Warp Marker Injector

Injects warp markers from JSON file into Ableton Live Set (.als) files.
ALS files are gzip-compressed XML.
"""

import gzip
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional


def load_warp_markers(json_path: str) -> list[dict]:
    """Load warp markers from JSON file."""
    with open(json_path, 'r') as f:
        return json.load(f)


def decompress_als(als_path: str) -> str:
    """Decompress ALS file and return XML string."""
    with gzip.open(als_path, 'rb') as f:
        return f.read().decode('utf-8')


def compress_als(xml_content: str, als_path: str):
    """Compress XML string and write to ALS file."""
    with gzip.open(als_path, 'wb') as f:
        f.write(xml_content.encode('utf-8'))


def find_audio_clips(root: ET.Element, track_name_pattern: str) -> list[ET.Element]:
    """Find all AudioClip elements in tracks matching the name pattern."""
    clips = []

    # Find all tracks
    for track in root.iter('AudioTrack'):
        name_elem = track.find('.//EffectiveName')
        if name_elem is not None:
            name = name_elem.get('Value', '')
            if track_name_pattern.lower() in name.lower():
                print(f"Found track: {name}")
                # Find all AudioClips in arrangement
                for clip in track.iter('AudioClip'):
                    clips.append(clip)

    return clips


def get_clip_info(clip: ET.Element) -> dict:
    """Extract clip timing information."""
    time = float(clip.get('Time', 0))

    current_start = clip.find('CurrentStart')
    current_end = clip.find('CurrentEnd')

    start = float(current_start.get('Value', 0)) if current_start is not None else time
    end = float(current_end.get('Value', 0)) if current_end is not None else start

    name_elem = clip.find('Name')
    name = name_elem.get('Value', 'Unknown') if name_elem is not None else 'Unknown'

    # Get Loop info - LoopStart tells us which beat in the audio file
    # corresponds to the start of this clip
    loop_start = 0.0
    loop_elem = clip.find('Loop')
    if loop_elem is not None:
        loop_start_elem = loop_elem.find('LoopStart')
        if loop_start_elem is not None:
            loop_start = float(loop_start_elem.get('Value', 0))

    # Get sample info for calculating time conversion
    sample_rate = 44100  # Default
    sample_ref = clip.find('.//DefaultSampleRate')
    if sample_ref is not None:
        sample_rate = int(sample_ref.get('Value', 44100))

    return {
        'time': time,
        'start': start,  # Project beat where clip starts
        'end': end,      # Project beat where clip ends
        'name': name,
        'sample_rate': sample_rate,
        'length': end - start,
        'loop_start': loop_start  # Audio file beat that aligns to clip start
    }


def generate_warp_marker_xml(warp_markers: list[dict], clip_info: dict,
                             bpm: float = 88.0, markers_per_bar: float = 0.0,
                             max_offset_ms: float = 0.0) -> str:
    """
    Generate WarpMarkers XML content.

    The warp markers JSON has:
    - original_beat: where the transient currently is (in project beats)
    - target_beat: where we want it to play (in project beats)
    - original_seconds: time in audio file (absolute seconds from start)

    Ableton warp markers have:
    - SecTime: position in audio file (seconds)
    - BeatTime: beat position in the audio file's timeline

    The clip's LoopStart defines which audio beat aligns to the clip's start position.
    For example, if LoopStart=28.75 and clip starts at project beat 104:
    - Audio beat 28.75 plays at project beat 104
    - To place a transient at project beat 105, we need audio beat 29.75

    To align audio to target groove:
    - SecTime = original_seconds (where the sound is in the audio file)
    - BeatTime = loop_start + (target_beat - clip_start)
               = where in audio timeline we want it to play

    Args:
        markers_per_bar: Target density (0 = use all markers, 1 = ~1/bar, 2 = ~2/bar, etc.)
        max_offset_ms: Maximum timing adjustment in ms (0 = no limit). Skip markers that
                      would stretch audio too much - better to be off-beat than distorted.
    """
    clip_start = clip_info['start']  # e.g., 104 (project beat)
    clip_end = clip_info['end']
    loop_start = clip_info['loop_start']  # e.g., 28.75 (audio beat)

    # Filter markers relevant to this clip
    relevant_markers = []
    skipped_too_large = 0
    for m in warp_markers:
        target_beat = m['target_beat']
        if clip_start <= target_beat < clip_end:
            # Skip markers with offsets too large (would cause distortion)
            if max_offset_ms > 0 and abs(m.get('offset_ms', 0)) > max_offset_ms:
                skipped_too_large += 1
                continue
            relevant_markers.append(m)

    if skipped_too_large > 0:
        print(f"    Skipped {skipped_too_large} markers with offset > {max_offset_ms}ms")

    if not relevant_markers:
        return None

    # Apply density filter if specified
    if markers_per_bar > 0:
        # Sort by offset magnitude first (prioritize biggest adjustments)
        relevant_markers.sort(key=lambda x: abs(x.get('offset_ms', 0)), reverse=True)

        # Calculate minimum spacing from density
        min_spacing = 4.0 / markers_per_bar  # 4 beats per bar

        # Re-sort by time
        relevant_markers.sort(key=lambda x: x['target_beat'])

        # Apply spacing filter
        filtered = []
        last_beat = -float('inf')
        for m in relevant_markers:
            if m['target_beat'] - last_beat >= min_spacing:
                filtered.append(m)
                last_beat = m['target_beat']
        relevant_markers = filtered

    # Sort by target beat
    relevant_markers.sort(key=lambda x: x['target_beat'])

    # Generate XML
    xml_lines = ['<WarpMarkers>']

    for i, m in enumerate(relevant_markers):
        # SecTime = where the transient is in the audio file
        sec_time = m['original_seconds']

        # BeatTime = audio beat position where we want this transient to play
        # Convert from project beats to audio beats using loop_start offset
        beat_time = loop_start + (m['target_beat'] - clip_start)

        # Ensure beat_time is positive
        if beat_time < 0:
            continue

        xml_lines.append(f'\t<WarpMarker Id="{i}" SecTime="{sec_time}" BeatTime="{beat_time}" />')

    xml_lines.append('</WarpMarkers>')

    return '\n'.join(xml_lines)


def inject_warp_markers_text(xml_content: str, warp_markers: list[dict],
                             track_name_pattern: str, bpm: float = 88.0,
                             markers_per_bar: float = 0.0,
                             density_map: dict = None,
                             max_offset_ms: float = 0.0) -> str:
    """
    Inject warp markers into ALS XML using text manipulation.
    This is more reliable than ElementTree for preserving formatting.

    Args:
        density_map: Optional dict mapping clip start beats to markers_per_bar values.
                    e.g., {104: 1.0, 137: 1.0, 161: 2.0} for different densities per clip.
                    If not specified, uses markers_per_bar for all clips.
        max_offset_ms: Maximum timing adjustment in ms. Skip markers that exceed this
                      to avoid audio distortion. 0 = no limit.
    """
    # Find all AudioClips in tracks matching the pattern
    # First, find the track section

    # Parse to find clip positions
    root = ET.fromstring(xml_content)
    clips_info = []

    for track in root.iter('AudioTrack'):
        name_elem = track.find('.//EffectiveName')
        if name_elem is not None:
            name = name_elem.get('Value', '')
            if track_name_pattern.lower() in name.lower():
                print(f"Found track: {name}")
                for clip in track.iter('AudioClip'):
                    info = get_clip_info(clip)
                    clips_info.append(info)
                    print(f"  Clip: {info['name']} at project beats {info['start']}-{info['end']} (audio LoopStart={info['loop_start']})")

    if not clips_info:
        print(f"No clips found matching pattern: {track_name_pattern}")
        return xml_content

    # For each clip, generate new warp markers and replace in XML
    modified_xml = xml_content

    for clip_info in clips_info:
        # Determine density for this clip
        clip_density = markers_per_bar
        if density_map:
            # Find matching density by clip start beat (allow some tolerance)
            for start_beat, density in density_map.items():
                if abs(clip_info['start'] - start_beat) < 1.0:
                    clip_density = density
                    break

        new_markers_xml = generate_warp_marker_xml(warp_markers, clip_info, bpm, clip_density, max_offset_ms)
        if new_markers_xml is None:
            print(f"  No relevant markers for clip at {clip_info['start']}-{clip_info['end']}")
            continue

        # Count markers
        marker_count = new_markers_xml.count('<WarpMarker ')
        density_str = f" (density={clip_density}/bar)" if clip_density > 0 else ""
        print(f"  Injecting {marker_count} markers into clip at {clip_info['start']}{density_str}")

        # Find and replace the WarpMarkers section for this clip
        # We need to find the specific clip by its timing
        # Look for pattern: <AudioClip Id="X" Time="CLIP_TIME">....<WarpMarkers>...</WarpMarkers>

        clip_time = clip_info['time']

        # Build a regex pattern to find this clip's warp markers
        # This is tricky - we need to match the clip by Time attribute, then find its WarpMarkers
        pattern = rf'(<AudioClip[^>]+Time="{int(clip_time)}"[^>]*>.*?)<WarpMarkers>.*?</WarpMarkers>'

        def replace_markers(match):
            clip_section = match.group(1)
            return clip_section + new_markers_xml.replace('\n', '\n\t\t\t\t\t\t\t\t\t\t\t\t\t\t')

        modified_xml = re.sub(pattern, replace_markers, modified_xml, flags=re.DOTALL)

    return modified_xml


def inject_warp_markers(als_path: str, json_path: str, output_path: Optional[str] = None,
                       track_pattern: str = "Vocals", bpm: float = 88.0,
                       markers_per_bar: float = 0.0, density_map: dict = None,
                       max_offset_ms: float = 0.0):
    """
    Main function to inject warp markers into an ALS file.

    Args:
        als_path: Path to input ALS file
        json_path: Path to warp markers JSON file
        output_path: Path for output ALS file (default: overwrites input)
        track_pattern: Pattern to match track names (e.g., "Vocals")
        bpm: Project tempo in BPM
        markers_per_bar: Default marker density (0 = use all markers)
        density_map: Per-clip densities {clip_start_beat: markers_per_bar}
        max_offset_ms: Maximum timing adjustment (0 = no limit). Skip large adjustments
                      to avoid distortion - better off-beat than stretched.
    """
    if output_path is None:
        output_path = als_path

    print(f"Loading warp markers from {json_path}...")
    warp_markers = load_warp_markers(json_path)
    print(f"Loaded {len(warp_markers)} warp markers")

    print(f"Decompressing {als_path}...")
    xml_content = decompress_als(als_path)
    print(f"Decompressed {len(xml_content)} bytes")

    print(f"Injecting warp markers for tracks matching '{track_pattern}'...")
    if density_map:
        print(f"Using per-clip density map: {density_map}")
    elif markers_per_bar > 0:
        print(f"Using density: {markers_per_bar} markers/bar")
    if max_offset_ms > 0:
        print(f"Max offset: {max_offset_ms}ms (larger adjustments will be skipped)")

    modified_xml = inject_warp_markers_text(
        xml_content, warp_markers, track_pattern, bpm,
        markers_per_bar, density_map, max_offset_ms
    )

    print(f"Compressing and writing to {output_path}...")
    compress_als(modified_xml, output_path)
    print("Done!")


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Inject warp markers into Ableton Live Set files')
    parser.add_argument('als_file', help='Input ALS file path')
    parser.add_argument('warp_markers', help='Warp markers JSON file path')
    parser.add_argument('-o', '--output', help='Output ALS file (default: overwrite input)')
    parser.add_argument('-t', '--track', default='Vocals', help='Track name pattern to match')
    parser.add_argument('-b', '--bpm', type=float, default=88.0, help='Project tempo in BPM')
    parser.add_argument('-d', '--density', type=float, default=0.0,
                       help='Markers per bar (0=all, 1=1/bar, 2=2/bar, etc.)')
    parser.add_argument('--density-map', type=str, default='',
                       help='Per-clip densities as "beat:density,beat:density" e.g. "104:1,161:2"')
    parser.add_argument('--max-offset', type=float, default=0.0,
                       help='Max timing adjustment in ms (0=no limit). Skip larger adjustments to avoid distortion.')

    args = parser.parse_args()

    # Parse density map if provided
    density_map = None
    if args.density_map:
        density_map = {}
        for pair in args.density_map.split(','):
            beat, density = pair.split(':')
            density_map[float(beat)] = float(density)

    inject_warp_markers(
        args.als_file,
        args.warp_markers,
        args.output,
        args.track,
        args.bpm,
        args.density,
        density_map,
        args.max_offset
    )
