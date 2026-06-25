"""Install / update the AbletonMCP MIDI Remote Script into Live's User Remote Scripts."""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import sys
from pathlib import Path

logger = logging.getLogger("ableton-mcp-remote-script")

# Must match SCRIPT_VERSION in AbletonMCP_Remote_Script/__init__.py
EXPECTED_REMOTE_SCRIPT_VERSION = "1.6.0"
REMOTE_SCRIPT_FOLDER_NAME = "AbletonMCP"


def bundled_remote_script_init() -> Path:
    """Path to the __init__.py shipped with this package (or repo checkout).

    Does not import the Live script (it depends on Ableton's ``_Framework``).
    """
    here = Path(__file__).resolve().parent
    candidates = [
        here / "bundled_ableton_remote_script" / "AbletonMCP_init.py",
        here.parent / "AbletonMCP_Remote_Script" / "__init__.py",
    ]
    for p in candidates:
        if p.exists():
            return p
    raise FileNotFoundError(
        "Could not locate AbletonMCP Remote Script __init__.py "
        f"(tried: {', '.join(str(c) for c in candidates)})"
    )


def discover_user_remote_script_dirs() -> list[Path]:
    """Find Ableton Live 'User Remote Scripts' directories for this machine."""
    home = Path.home()
    found: list[Path] = []

    if sys.platform == "darwin":
        prefs = home / "Library" / "Preferences" / "Ableton"
        if prefs.exists():
            for live_dir in sorted(prefs.glob("Live *")):
                found.append(live_dir / "User Remote Scripts")
    elif sys.platform == "win32":
        roaming = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
        ableton = roaming / "Ableton"
        if ableton.exists():
            for live_dir in sorted(ableton.glob("Live *")):
                for candidate in (
                    live_dir / "Preferences" / "User Remote Scripts",
                    live_dir / "User Remote Scripts",
                ):
                    found.append(candidate)
    else:
        for base in (
            home / ".config" / "ableton",
            home / ".local" / "share" / "Ableton",
        ):
            if base.exists():
                for live_dir in sorted(base.glob("Live *")):
                    found.append(live_dir / "User Remote Scripts")

    seen: set[str] = set()
    unique: list[Path] = []
    for p in found:
        key = str(p)
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return unique


def install_remote_script(
    target_root: Path | None = None,
    *,
    force: bool = False,
) -> list[dict]:
    """Copy the bundled Remote Script into User Remote Scripts.

    Returns a list of result dicts: {path, status, detail}.
    """
    skip = os.environ.get("ABLETON_MCP_SKIP_SCRIPT_INSTALL", "").strip().lower()
    if skip in {"1", "true", "yes", "on"} and not force:
        return [{"path": None, "status": "skipped", "detail": "ABLETON_MCP_SKIP_SCRIPT_INSTALL set"}]

    src = bundled_remote_script_init()
    targets = [target_root] if target_root else discover_user_remote_script_dirs()
    if not targets:
        return [{
            "path": None,
            "status": "error",
            "detail": "No Ableton User Remote Scripts directory found",
        }]

    results = []
    for root in targets:
        try:
            root.mkdir(parents=True, exist_ok=True)
            dest_dir = root / REMOTE_SCRIPT_FOLDER_NAME
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / "__init__.py"

            backup: Path | None = None
            if not dest.exists():
                shutil.copy2(src, dest)
                status = "installed"
            elif dest.read_bytes() == src.read_bytes():
                status = "unchanged"
            else:
                # Existing file differs — may be a user's own edit, so back it up
                backup = dest.with_suffix(".py.bak")
                shutil.copy2(dest, backup)
                shutil.copy2(src, dest)
                status = "updated"

            detail = f"script_version={EXPECTED_REMOTE_SCRIPT_VERSION}"
            if backup is not None:
                detail += f"; previous version backed up to {backup.name}"

            results.append({
                "path": str(dest),
                "status": status,
                "detail": detail,
                "script_version": EXPECTED_REMOTE_SCRIPT_VERSION,
                "backup": str(backup) if backup else None,
            })
            logger.info("Remote Script %s → %s", status, dest)
        except Exception as e:
            results.append({
                "path": str(root / REMOTE_SCRIPT_FOLDER_NAME / "__init__.py"),
                "status": "error",
                "detail": str(e),
            })
            logger.warning("Failed to install Remote Script into %s: %s", root, e)

    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Install/update AbletonMCP MIDI Remote Script into Live User Remote Scripts"
    )
    parser.add_argument(
        "--target",
        type=str,
        default=None,
        help="Explicit User Remote Scripts directory (optional)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite even if ABLETON_MCP_SKIP_SCRIPT_INSTALL is set",
    )
    parser.add_argument(
        "--list-targets",
        action="store_true",
        help="Print discovered User Remote Scripts dirs and exit",
    )
    parser.add_argument(
        "--sync-bundle",
        action="store_true",
        help="Dev only: copy repo AbletonMCP_Remote_Script into package bundle",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.sync_bundle:
        repo = Path(__file__).resolve().parent.parent / "AbletonMCP_Remote_Script" / "__init__.py"
        dest = Path(__file__).resolve().parent / "bundled_ableton_remote_script" / "AbletonMCP_init.py"
        if not repo.exists():
            print(f"Missing {repo}")
            return 1
        shutil.copy2(repo, dest)
        print(f"Synced {repo} → {dest}")
        return 0

    if args.list_targets:
        for p in discover_user_remote_script_dirs():
            print(p)
        return 0

    target = Path(args.target).expanduser() if args.target else None
    results = install_remote_script(target, force=args.force)
    for r in results:
        print(f"{r.get('status')}: {r.get('path') or '-'} ({r.get('detail')})")

    if any(r.get("status") == "error" for r in results) and not any(
        r.get("status") in {"installed", "updated", "unchanged"} for r in results
    ):
        return 1

    print(
        "\nIf Ableton was already open: restart Live, or re-select AbletonMCP "
        "under Preferences → Link/Tempo/MIDI → Control Surface."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
