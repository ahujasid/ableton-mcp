"""Install / update the AbletonMCP MIDI Remote Script into Live's User Library.

Since Live 10.1.13, third-party control surface scripts are loaded from
``<User Library>/Remote Scripts/``. The similarly named
``Preferences/User Remote Scripts/`` folder is for legacy instant-mapping
configurations (UserConfiguration.txt) and is NOT scanned for Python control
surfaces — installing there is supported only as an opt-in (``--legacy``).
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import shutil
import sys
from pathlib import Path

logger = logging.getLogger("ableton-mcp-remote-script")

# Must match SCRIPT_VERSION in AbletonMCP_Remote_Script/__init__.py
EXPECTED_REMOTE_SCRIPT_VERSION = "1.7.0"
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


def _live_version_key(live_dir: Path) -> list[int]:
    return [int(n) for n in re.findall(r"\d+", live_dir.name)]


def _live_preference_dirs() -> list[Path]:
    """Ableton preference folders (``…/Ableton/Live x.x.x``), newest first."""
    home = Path.home()
    bases: list[Path] = []

    if sys.platform == "darwin":
        bases.append(home / "Library" / "Preferences" / "Ableton")
    elif sys.platform == "win32":
        roaming = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
        bases.append(roaming / "Ableton")
    else:
        bases.append(home / ".config" / "ableton")
        bases.append(home / ".local" / "share" / "Ableton")

    dirs: list[Path] = []
    for base in bases:
        if base.exists():
            dirs.extend(d for d in base.glob("Live *") if d.is_dir())
    return sorted(dirs, key=_live_version_key, reverse=True)


def _user_library_from_library_cfg(cfg: Path) -> Path | None:
    """Best-effort read of the (relocatable) User Library path from Library.cfg.

    Live 10–12 store it under <UserLibrary><LibraryProject> as
    <ProjectPath Value="…parent dir"/> + <ProjectName Value="User Library"/>;
    the library folder is their join. Unknown layouts fall back to any
    absolute existing-directory value found inside the UserLibrary block.
    """
    try:
        import xml.etree.ElementTree as ET

        root = ET.parse(cfg).getroot()
    except Exception:
        return None
    for elem in root.iter():
        if "userlibrary" not in elem.tag.lower():
            continue
        project_path = project_name = None
        fallback: Path | None = None
        for sub in elem.iter():
            value = sub.attrib.get("Value")
            if value is None:
                continue
            tag = sub.tag.lower()
            if "projectpath" in tag:
                project_path = value
            elif "projectname" in tag:
                project_name = value
            elif fallback is None:
                p = Path(value).expanduser()
                if p.is_absolute() and p.is_dir():
                    fallback = p
        if project_path and project_name:
            candidate = Path(project_path).expanduser() / project_name
            if candidate.is_dir():
                return candidate
        if fallback is not None:
            return fallback
    return None


def discover_user_library_remote_script_dirs() -> list[Path]:
    """Find ``<User Library>/Remote Scripts`` dirs — where Live (≥10.1.13)
    actually loads third-party control surface scripts from.

    Reads the configured User Library location from each installed Live
    version's Library.cfg, then falls back to the platform defaults. Only
    libraries that already exist are returned, so the installer never invents
    profile folders for Live versions that aren't installed.
    """
    home = Path.home()
    libraries: list[Path] = []

    for pref_dir in _live_preference_dirs():
        for cfg in (pref_dir / "Library.cfg", pref_dir / "Preferences" / "Library.cfg"):
            if cfg.is_file():
                lib = _user_library_from_library_cfg(cfg)
                if lib is not None:
                    libraries.append(lib)

    default_libraries = [
        home / "Music" / "Ableton" / "User Library",
        home / "Documents" / "Ableton" / "User Library",
    ]
    libraries.extend(lib for lib in default_libraries if lib.is_dir())

    seen: set[str] = set()
    unique: list[Path] = []
    for lib in libraries:
        target = lib / "Remote Scripts"
        key = str(target)
        if key not in seen:
            seen.add(key)
            unique.append(target)
    return unique


def discover_user_remote_script_dirs() -> list[Path]:
    """Find legacy 'User Remote Scripts' directories that already exist.

    Live has not loaded control surface scripts from these since 10.1.13 —
    they hold instant-mapping configs. Kept for ``--legacy`` opt-in only, and
    limited to existing directories so no stale profile folders get created.
    """
    found: list[Path] = []
    for live_dir in _live_preference_dirs():
        for candidate in (
            live_dir / "User Remote Scripts",
            live_dir / "Preferences" / "User Remote Scripts",
        ):
            if candidate.is_dir():
                found.append(candidate)

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
    include_legacy: bool = False,
) -> list[dict]:
    """Copy the bundled Remote Script into the User Library's Remote Scripts.

    Returns a list of result dicts: {path, status, detail}.
    """
    skip = os.environ.get("ABLETON_MCP_SKIP_SCRIPT_INSTALL", "").strip().lower()
    if skip in {"1", "true", "yes", "on"} and not force:
        return [{"path": None, "status": "skipped", "detail": "ABLETON_MCP_SKIP_SCRIPT_INSTALL set"}]

    src = bundled_remote_script_init()
    if target_root:
        targets = [target_root]
    else:
        targets = discover_user_library_remote_script_dirs()
        if include_legacy:
            targets = targets + discover_user_remote_script_dirs()
    if not targets:
        return [{
            "path": None,
            "status": "error",
            "detail": (
                "No Ableton User Library found. Create the 'Remote Scripts' folder in "
                "your User Library (default: ~/Music/Ableton/User Library on macOS, "
                "%USERPROFILE%\\Documents\\Ableton\\User Library on Windows) "
                "or pass --target <dir>."
            ),
        }]

    src_bytes = src.read_bytes()
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
            elif dest.read_bytes() == src_bytes:
                status = "unchanged"
            else:
                # Existing file differs — may be a user's own edit, so back it up
                backup = dest.with_suffix(".py.bak")
                shutil.copy2(dest, backup)
                shutil.copy2(src, dest)
                status = "updated"

            if dest.read_bytes() != src_bytes:
                raise OSError("verification failed: destination does not match bundled script")

            detail = f"script_version={EXPECTED_REMOTE_SCRIPT_VERSION}"
            if backup is not None:
                detail += f"; previous version backed up to {backup.name}"
            if "User Remote Scripts" in root.parts:
                detail += "; legacy location — not scanned by Live 10.1.13+"

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
        description=(
            "Install/update AbletonMCP MIDI Remote Script into Live's "
            "User Library (Remote Scripts)"
        )
    )
    parser.add_argument(
        "--target",
        type=str,
        default=None,
        help="Explicit Remote Scripts directory (optional)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite even if ABLETON_MCP_SKIP_SCRIPT_INSTALL is set",
    )
    parser.add_argument(
        "--legacy",
        action="store_true",
        help=(
            "Also install into legacy 'User Remote Scripts' preference folders "
            "(not scanned by Live 10.1.13+; existing folders only)"
        ),
    )
    parser.add_argument(
        "--list-targets",
        action="store_true",
        help="Print discovered Remote Scripts dirs and exit",
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
        targets = discover_user_library_remote_script_dirs()
        if args.legacy:
            targets += discover_user_remote_script_dirs()
        for p in targets:
            print(p)
        return 0

    target = Path(args.target).expanduser() if args.target else None
    results = install_remote_script(target, force=args.force, include_legacy=args.legacy)
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
