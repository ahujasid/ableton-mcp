#!/usr/bin/env python3
"""Ableton Live track meter analyzer.

Samples output meters multiple times and reports levels with fader dB
from Ableton's own volume parameter.

IMPORTANT: Ableton's output_meter values are on a nonlinear scale.
They are NOT linear amplitude and 20*log10(value) gives WRONG results.
The fader dB values (from Ableton's volume_db) ARE accurate.
Use the meter values only for relative comparison between tracks.

Usage:
    python3 meter.py                    # Default: 20 samples over 5 seconds
    python3 meter.py -n 40 -t 10       # 40 samples over 10 seconds
    python3 meter.py --tracks 7,8,9    # Specific tracks only
    python3 meter.py --json            # JSON output for piping
"""

import argparse
import json
import math
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "MCP_Server"))
from connection import AbletonConnection


def parse_volume_db(db_str):
    """Parse Ableton's volume dB string like '-4.0 dB' to float."""
    if not db_str:
        return 0.0
    try:
        return float(db_str.replace("dB", "").strip())
    except (ValueError, AttributeError):
        return 0.0


def sample_meters(conn, track_indices=None, include_returns=True, include_master=True):
    """Take a single meter snapshot with fader data."""
    params = {
        "track_indices": track_indices,
        "include_returns": include_returns,
        "include_master": include_master,
    }
    result = conn.send_command("get_track_meters", params)
    if not result or "meters" not in result:
        return []
    return result["meters"]


def collect_samples(conn, num_samples, duration, track_indices=None):
    """Collect multiple meter samples over a time window."""
    interval = duration / max(num_samples - 1, 1)
    all_samples = {}

    for i in range(num_samples):
        meters = sample_meters(conn, track_indices)
        for m in meters:
            key = (m["type"], m["index"])
            peak = max(m["left"], m["right"])
            if key not in all_samples:
                all_samples[key] = {
                    "name": m["name"],
                    "type": m["type"],
                    "index": m["index"],
                    "volume": m.get("volume", 0.85),
                    "volume_db": m.get("volume_db", "0.0 dB"),
                    "mute": m.get("mute", False),
                    "values": [],
                }
            all_samples[key]["values"].append(peak)
            all_samples[key]["volume"] = m.get("volume", all_samples[key]["volume"])
            all_samples[key]["volume_db"] = m.get("volume_db", all_samples[key]["volume_db"])

        if i < num_samples - 1:
            time.sleep(interval)

    return all_samples


def analyze(all_samples):
    """Compute statistics for each track."""
    results = []
    for key, data in all_samples.items():
        values = data["values"]
        fader_db = parse_volume_db(data["volume_db"])
        is_muted = data.get("mute", False)

        if not any(v > 0 for v in values) or is_muted:
            results.append({
                "name": data["name"],
                "type": data["type"],
                "index": data["index"],
                "fader": data["volume"],
                "fader_db": fader_db,
                "fader_db_str": data["volume_db"],
                "meter_peak": 0.0,
                "meter_avg": 0.0,
                "silent": True,
                "mute": is_muted,
            })
            continue

        peak = max(values)
        avg = sum(values) / len(values)

        results.append({
            "name": data["name"],
            "type": data["type"],
            "index": data["index"],
            "fader": data["volume"],
            "fader_db": fader_db,
            "fader_db_str": data["volume_db"],
            "meter_peak": peak,
            "meter_avg": avg,
            "samples": len(values),
            "silent": False,
            "mute": is_muted,
        })

    type_order = {"track": 0, "return": 1, "master": 2}
    results.sort(key=lambda r: (type_order.get(r["type"], 9), r["index"]))
    return results


def clean_name(name):
    """Remove emoji from track names."""
    for ch in "\U0001f941\U0001f3b8\U0001f39a\U0001f3a4\U0001f3b9\U0001f30a":
        name = name.replace(ch, "")
    return name.strip()


def meter_bar(value, width=20):
    """ASCII meter bar for visual level comparison."""
    filled = int(value * width)
    return "\u2588" * filled + "\u2591" * (width - filled)


def print_report(results, num_samples, duration):
    """Print a formatted level report."""
    print(f"\nMETER ANALYSIS ({num_samples} samples over {duration:.1f}s)")
    print("=" * 90)
    print(f"{'Track':<16} {'Fader':>8} {'Meter(peak)':>11} {'Meter(avg)':>10} {'Level Bar'}")
    print("-" * 90)

    for r in results:
        if r["silent"]:
            continue
        name = clean_name(r["name"])
        fader = r.get("fader_db_str", "0 dB")
        peak = r["meter_peak"]
        avg = r["meter_avg"]
        bar = meter_bar(peak)
        print(f"{name:<16} {fader:>8} {peak:>11.3f} {avg:>10.3f} {bar}")

    print("-" * 90)

    # Hierarchy check using meter peaks (relative comparison)
    kick = drums_grp = bass_track = bass_grp = master = None
    for r in results:
        if r["silent"]:
            continue
        if r["type"] == "track" and r["index"] == 7:
            kick = r
        if r["type"] == "track" and r["index"] == 6:
            drums_grp = r
        if r["type"] == "track" and r["index"] == 23:
            bass_track = r
        if r["type"] == "track" and r["index"] == 22:
            bass_grp = r
        if r["type"] == "master":
            master = r

    print("\nFADER LEVELS (from Ableton — accurate):")
    if drums_grp:
        print(f"  DRUMS group:  {drums_grp['fader_db_str']}")
    if kick:
        print(f"  KICK:         {kick['fader_db_str']}")
    if bass_track:
        print(f"  BASS:         {bass_track['fader_db_str']}")
    if bass_grp:
        print(f"  BASS group:   {bass_grp['fader_db_str']}")
    if master:
        print(f"  Master:       {master['fader_db_str']}")

    print("\nMETER PEAKS (relative — higher = louder, scale is nonlinear):")
    active = [(r, r["meter_peak"]) for r in results if not r["silent"]]
    active.sort(key=lambda x: -x[1])
    for r, peak in active[:10]:
        name = clean_name(r["name"])
        print(f"  {name:<16} {peak:.3f}  {meter_bar(peak, 25)}")

    print("\nNOTE: For accurate dBFS, check Ableton's peak hold display.")
    print("      Meter values are for relative comparison only.")


def main():
    parser = argparse.ArgumentParser(description="Ableton Live meter analyzer")
    parser.add_argument("-n", "--samples", type=int, default=20, help="Number of samples (default: 20)")
    parser.add_argument("-t", "--time", type=float, default=5.0, help="Duration in seconds (default: 5.0)")
    parser.add_argument("--tracks", type=str, help="Comma-separated track indices (default: all)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--no-returns", action="store_true", help="Exclude return tracks")
    parser.add_argument("--no-master", action="store_true", help="Exclude master track")
    args = parser.parse_args()

    track_indices = None
    if args.tracks:
        track_indices = [int(x) for x in args.tracks.split(",")]

    conn = AbletonConnection(host="localhost", port=9877)
    if not conn.connect():
        print("Error: Could not connect to Ableton.", file=sys.stderr)
        sys.exit(1)

    try:
        all_samples = collect_samples(conn, args.samples, args.time, track_indices)
        results = analyze(all_samples)

        if args.json:
            for r in results:
                for k in list(r.keys()):
                    if isinstance(r[k], float) and math.isinf(r[k]):
                        r[k] = None
            print(json.dumps(results, indent=2))
        else:
            print_report(results, args.samples, args.time)
    finally:
        conn.disconnect()


if __name__ == "__main__":
    main()
