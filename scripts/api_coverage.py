#!/usr/bin/env python3
"""Report which Live Object Model members the Remote Script already touches.

Parses the LOM reference pages (one text file per class, as saved from
https://docs.cycling74.com/apiref/lom/<class>/) into children, properties and
functions, and marks a member "used" when its name appears as an attribute or
call (``.name``) anywhere in the Remote Script. Matching is by name only, so a
member that shares a name with one on another class counts as used: treat the
output as a map of what is untouched, not a proof of coverage.

usage: python3 scripts/api_coverage.py [--lom DIR] [--markdown] [--unused-only]
"""
import argparse
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(REPO, "AbletonMCP_Remote_Script", "__init__.py")
DEFAULT_LOM = os.path.expanduser("~/.claude/skills/ableton/lom")

# Classes an MCP agent has no use for: Max-only objects and hardware surfaces.
SKIP = {"this_device", "controlsurface", "maxdevice"}
MEMBER = re.compile(r"^([a-z_][a-z0-9_]*)(?: (.+))?$")


def parse(path):
    """Return {'title', 'children', 'properties', 'functions'} for one LOM page."""
    lines = [l.rstrip() for l in open(path, encoding="utf-8")]
    out = {"title": lines[0].strip(), "children": [], "properties": [], "functions": []}
    section = None
    for i, line in enumerate(lines):
        head = line.rstrip("[]").strip()
        if line.endswith("[]") and head in ("Children", "Properties", "Functions"):
            section = head.lower()
            continue
        if line.endswith("[]"):
            section = None
            continue
        if section is None:
            continue
        m = MEMBER.match(line.strip())
        if not m or line != line.lstrip():
            continue
        name, typ = m.group(1), (m.group(2) or "")
        nxt = next((l for l in lines[i + 1:i + 4] if l.strip()), "")
        if section in ("children", "properties"):
            if nxt.startswith("Access:"):
                access = nxt.split(":", 1)[1].strip()
                out[section].append((name, typ, access))
        else:
            # A function name stands alone on its line, followed by a blank line.
            if not typ and i + 1 < len(lines) and not lines[i + 1].strip():
                out["functions"].append((name, "", "call"))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lom", default=DEFAULT_LOM)
    ap.add_argument("--markdown", action="store_true")
    ap.add_argument("--unused-only", action="store_true")
    args = ap.parse_args()

    source = open(SCRIPT, encoding="utf-8").read()
    # Attribute access, plus names used as strings (getattr tables, meter field lists).
    used_names = set(re.findall(r"\.([a-z_][a-z0-9_]*)", source))
    used_names |= set(re.findall(r"[\"']([a-z_][a-z0-9_]*)[\"']", source))

    files = sorted(f for f in os.listdir(args.lom) if f.endswith(".txt") and not f.startswith("_"))
    total = used = 0
    rows = []
    for f in files:
        key = f[:-4]
        if key in SKIP:
            continue
        page = parse(os.path.join(args.lom, f))
        members = [(kind, *m) for kind in ("children", "properties", "functions") for m in page[kind]]
        if not members:
            continue
        hit = [m for m in members if m[1] in used_names]
        total += len(members)
        used += len(hit)
        rows.append((page["title"], members, hit))

    for title, members, hit in rows:
        hit_names = {m[1] for m in hit}
        if args.markdown:
            print(f"\n### {title} ({len(hit)}/{len(members)})\n")
        else:
            print(f"\n{title}: {len(hit)}/{len(members)} used")
        for kind, name, typ, access in members:
            mark = name in hit_names
            if args.unused_only and mark:
                continue
            flag = "x" if mark else " "
            kind_s = {"children": "child", "properties": "prop", "functions": "fn"}[kind]
            if args.markdown:
                print(f"- [{flag}] `{name}` {kind_s} {typ} ({access})".rstrip())
            else:
                print(f"  [{flag}] {kind_s:5} {name:40} {access:16} {typ}")
    print(f"\nTotal: {used}/{total} LOM members referenced by the Remote Script", file=sys.stderr)


if __name__ == "__main__":
    main()
