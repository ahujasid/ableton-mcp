#!/usr/bin/env python3
"""Check the audio path between Ableton Live (Wine, PipeASIO) and the Scarlett
4i4 from the Linux side: the part Live's API can't see.

  1. links   Live's out_1..4 -> Scarlett playback FL, FR, AUX0, AUX1 (Line Out 1-4)
             Scarlett capture AUX0..3 (Inputs 1-4) -> Live's in_1..4.
             PipeASIO only links outputs 1/2 by itself; 3/4 vanish when Live restarts.
  2. mixer   what feeds the Scarlett's Line Outs 1-4 (Analogue Output 0N Playback
             Enum). For a hardware loop (reamping, pedals), Line Out 3/4 must be
             "PCM 3"/"PCM 4"; "Mix A"/"Mix B" mirrors the monitors instead.
  3. stream  the kernel's view: is the USB playback/capture stream RUNNING and
             is its hardware pointer moving.
  4. levels  (--listen SECONDS) record what PipeWire sends to the Scarlett (the
             sink's monitor) and what comes back from it, and report peak and
             RMS in dBFS per jack: "is signal leaving Line Out 3, is anything
             arriving on Input 3/4".

Only reads, except --fix, which creates the missing Live <-> Scarlett links
(the same pw-link commands done by hand). Never touches the mixer.

Exit: 0 all good, 1 a problem was found, 3 something could not be checked
(never reported as fine).

usage: ableton-io-check [--listen SECONDS] [--fix] [--json]
"""
import argparse
import json
import math
import os
import re
import struct
import subprocess
import sys
import tempfile
import time
import wave

LIVE_PREFIX = "Ableton Live"
SCARLETT = "Scarlett_4i4"
CARD = "Gen"
SIGNAL_DBFS = -60.0

OUT_LABELS = ["Line Out 1", "Line Out 2", "Line Out 3", "Line Out 4", "Headphones L", "Headphones R"]
IN_LABELS = ["Input 1", "Input 2", "Input 3", "Input 4", "Loopback L", "Loopback R"]
# Live port -> Scarlett port suffix
EXPECTED_OUT = [("out_1", "playback_FL"), ("out_2", "playback_FR"),
                ("out_3", "playback_AUX0"), ("out_4", "playback_AUX1")]
EXPECTED_IN = [("capture_AUX0", "in_1"), ("capture_AUX1", "in_2"),
               ("capture_AUX2", "in_3"), ("capture_AUX3", "in_4")]


def run(cmd, timeout=15):
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError("%s failed: %s" % (" ".join(cmd), (p.stderr or p.stdout).strip()))
    return p.stdout


class Report(object):
    def __init__(self):
        self.items = []

    def add(self, section, status, what, detail="", fix=None):
        """status: ok | problem | unknown | info"""
        self.items.append({"section": section, "status": status, "what": what, "detail": detail, "fix": fix})

    def exit_code(self):
        if any(i["status"] == "problem" for i in self.items):
            return 1
        if any(i["status"] == "unknown" for i in self.items):
            return 3
        return 0


def parse_links(text):
    """pw-link -l output -> set of (output_port, input_port)."""
    links = set()
    current = None
    for line in text.splitlines():
        if not line.strip():
            continue
        if not line.startswith(" "):
            current = line.strip()
            continue
        m = re.match(r"\s+\|->\s+(.*)$", line)
        if m and current:
            links.add((current, m.group(1).strip()))
            continue
        m = re.match(r"\s+\|<-\s+(.*)$", line)
        if m and current:
            links.add((m.group(1).strip(), current))
    return links


def find_ports():
    outs = run(["pw-link", "-o"]).splitlines()
    ins = run(["pw-link", "-i"]).splitlines()
    live_out = [p for p in outs if p.startswith(LIVE_PREFIX) and re.search(r":out_\d+$", p)]
    live_in = [p for p in ins if p.startswith(LIVE_PREFIX) and re.search(r":in_\d+$", p)]
    sc_play = [p for p in ins if SCARLETT in p and ":playback_" in p]
    sc_cap = [p for p in outs if SCARLETT in p and ":capture_" in p]
    return live_out, live_in, sc_play, sc_cap


def check_links(rep, fix):
    try:
        live_out, live_in, sc_play, sc_cap = find_ports()
        links = parse_links(run(["pw-link", "-l"]))
    except Exception as e:
        rep.add("links", "unknown", "could not read the PipeWire graph", str(e))
        return
    if not live_out:
        rep.add("links", "unknown", "Live has no PipeWire ports (is Live running with PipeASIO?)")
        return
    if not sc_play or not sc_cap:
        rep.add("links", "unknown", "Scarlett ports not found (unplugged, or not on the pro-audio profile?)",
                "run audio-check")
        return
    client = live_out[0].split(":")[0]

    def port(ports, suffix):
        return next((p for p in ports if p.endswith(":" + suffix)), None)

    pairs = [("Live %s -> %s" % (a, OUT_LABELS[i]), client + ":" + a, port(sc_play, b))
             for i, (a, b) in enumerate(EXPECTED_OUT)]
    pairs += [("%s -> Live %s" % (IN_LABELS[i], b), port(sc_cap, a), client + ":" + b)
              for i, (a, b) in enumerate(EXPECTED_IN)]
    for label, src, dst in pairs:
        if src is None or dst is None or src not in live_out + sc_cap:
            rep.add("links", "unknown", label, "port missing: %s" % (src if src not in live_out + sc_cap else dst))
            continue
        if (src, dst) in links:
            rep.add("links", "ok", label)
            continue
        cmd = ["pw-link", src, dst]
        if fix:
            try:
                run(cmd)
                rep.add("links", "ok", label, "was missing; linked by --fix")
            except Exception as e:
                rep.add("links", "problem", label, "missing, and --fix failed: %s" % e, " ".join(map(repr, cmd)))
        else:
            rep.add("links", "problem", label, "not linked (PipeASIO drops 3/4 on every Live restart)",
                    "pw-link %r %r   (or rerun with --fix)" % (src, dst))
    # Other things Live sends to: not an error, but worth seeing.
    stray = sorted(d for s, d in links if s.startswith(client + ":out_") and SCARLETT not in d)
    if stray:
        rep.add("links", "info", "Live outputs also go to", ", ".join(stray))


def check_mixer(rep):
    for n in (1, 2, 3, 4):
        name = "Analogue Output %02d Playback Enum" % n
        try:
            out = run(["amixer", "-c", CARD, "cget", "name=%s" % name])
        except Exception as e:
            rep.add("mixer", "unknown", "Line Out %d source" % n, str(e))
            continue
        items = dict(re.findall(r"Item #(\d+) '([^']*)'", out))
        m = re.search(r": values=(\d+)", out)
        if not m:
            rep.add("mixer", "unknown", "Line Out %d source" % n, "no value in amixer output")
            continue
        src = items.get(m.group(1), "item %s" % m.group(1))
        if src == "Off":
            rep.add("mixer", "problem", "Line Out %d source" % n, "Off: nothing reaches this jack")
        elif n >= 3 and src != "PCM %d" % n:
            rep.add("mixer", "problem", "Line Out %d source" % n,
                    "%s, not PCM %d: the jack carries the monitor mix, not Live's output %d "
                    "(fine for mirroring, wrong for a pedal/reamp loop)" % (src, n, n),
                    "amixer -c %s cset name='%s' 'PCM %d'   (back up first; see audio.md)" % (CARD, name, n))
        else:
            rep.add("mixer", "ok", "Line Out %d source" % n, src)


def check_stream(rep):
    for kind, label in (("p", "playback (to the Scarlett)"), ("c", "capture (from the Scarlett)")):
        path = "/proc/asound/%s/pcm0%s/sub0/status" % (CARD, kind)
        try:
            first = open(path).read()
            if "closed" in first:
                rep.add("stream", "problem", "USB %s" % label, "closed: nothing is using the device")
                continue
            time.sleep(0.25)
            second = open(path).read()
        except Exception as e:
            rep.add("stream", "unknown", "USB %s" % label, str(e))
            continue
        state = re.search(r"state:\s*(\S+)", first)
        p1, p2 = (re.search(r"hw_ptr\s*:\s*(\d+)", t) for t in (first, second))
        moving = bool(p1 and p2 and p1.group(1) != p2.group(1))
        st = state.group(1) if state else "?"
        if st == "RUNNING" and moving:
            rep.add("stream", "ok", "USB %s" % label, "RUNNING, hw_ptr advancing")
        else:
            rep.add("stream", "problem", "USB %s" % label, "state %s, hw_ptr %s" % (st, "moving" if moving else "stuck"),
                    "run audio-check; audio-relink if the device re-enumerated")


def node_names():
    dump = json.loads(run(["pw-dump"], timeout=20))
    sink = source = None
    for o in dump:
        props = (o.get("info") or {}).get("props") or {}
        name = props.get("node.name", "")
        if SCARLETT in name and ".pro-output" in name:
            sink = name
        if SCARLETT in name and ".pro-input" in name:
            source = name
    return sink, source


def record(target, seconds, channels, monitor):
    fd, path = tempfile.mkstemp(prefix="ableton-io-", suffix=".wav", dir=_tmpdir())
    os.close(fd)
    cmd = ["pw-record", "--target", target, "--channels", str(channels), "--format", "s16", "--rate", "48000"]
    if monitor:
        cmd += ["-P", "{ stream.capture.sink = true }"]
    cmd.append(path)
    p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    return p, path


def _tmpdir():
    d = "/tmp/claude"
    os.makedirs(d, exist_ok=True)
    return d


def levels(path, channels):
    with wave.open(path, "rb") as w:
        n = w.getnframes()
        raw = w.readframes(n)
        ch = w.getnchannels()
    if ch != channels or n == 0:
        raise RuntimeError("recorded %d frames, %d channels" % (n, ch))
    vals = struct.unpack("<%dh" % (len(raw) // 2), raw)
    out = []
    for c in range(ch):
        s = vals[c::ch]
        peak = max(abs(v) for v in s) / 32768.0
        rms = math.sqrt(sum(v * v for v in s) / len(s)) / 32768.0
        out.append((_db(peak), _db(rms)))
    return out, n


def _db(x):
    return -math.inf if x <= 0 else 20 * math.log10(x)


def check_levels(rep, seconds):
    try:
        sink, source = node_names()
    except Exception as e:
        rep.add("levels", "unknown", "could not find the Scarlett nodes", str(e))
        return
    if not sink or not source:
        rep.add("levels", "unknown", "Scarlett pro-audio nodes not found")
        return
    procs = [("out", record(sink, seconds, 6, True)), ("in", record(source, seconds, 6, False))]
    time.sleep(seconds)
    for _side, (p, _path) in procs:
        p.terminate()
    for side, (p, path) in procs:
        try:
            p.wait(timeout=5)
            vals, frames = levels(path, 6)
        except Exception as e:
            rep.add("levels", "unknown", "recording %s" % side, str(e))
            continue
        finally:
            if os.path.exists(path):
                os.remove(path)
        labels = OUT_LABELS if side == "out" else IN_LABELS
        for label, (peak, rms) in zip(labels, vals):
            has = peak > SIGNAL_DBFS
            rep.add("levels", "info", label, "%s  peak %s dBFS, rms %s dBFS (%.1f s)" % (
                "SIGNAL" if has else "silent", _fmt(peak), _fmt(rms), frames / 48000.0))
    rep.add("levels", "info", "how to read this",
            "Line Out 3 has signal but Input 3/4 is silent: the break is outside the computer (cable from "
            "Line Out 3, pedal power/order, cable back into Input 3/4). Line Out 3 silent while Live plays: "
            "Live isn't sending there (track Audio To, link, or the Line Out 3 source above). Note: the "
            "monitor shows what PipeWire sends; the Line Out source setting decides what reaches the jack.")


def _fmt(x):
    return "-inf" if x == -math.inf else "%.1f" % x


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--listen", type=float, default=0, metavar="SECONDS",
                    help="also measure levels for this long (play audio in Live meanwhile)")
    ap.add_argument("--fix", action="store_true", help="create missing Live <-> Scarlett links")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    rep = Report()
    check_links(rep, args.fix)
    check_mixer(rep)
    check_stream(rep)
    if args.listen > 0:
        check_levels(rep, min(args.listen, 30.0))
    code = rep.exit_code()
    if args.json:
        print(json.dumps({"exit": code, "items": rep.items}, indent=2))
        return code
    marks = {"ok": "ok  ", "problem": "FAIL", "unknown": "??  ", "info": "    "}
    section = None
    for i in rep.items:
        if i["section"] != section:
            section = i["section"]
            print("\n[%s]" % section)
        print("  %s %s%s" % (marks[i["status"]], i["what"], (": " + i["detail"]) if i["detail"] else ""))
        if i["fix"]:
            print("         fix: %s" % i["fix"])
    print("\n%s" % {0: "All checks passed.", 1: "Problems found (FAIL above).",
                     3: "Some checks could not run (?? above); that is not the same as fine."}[code])
    return code


if __name__ == "__main__":
    sys.exit(main())
