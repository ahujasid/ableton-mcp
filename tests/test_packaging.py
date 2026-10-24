"""Every Python package under MCP_Server must ship in the wheel.

pyproject lists packages explicitly, so a new subpackage that isn't added
there installs fine from a checkout but is missing from `uvx --from <zip>`.
"""

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_all_subpackages_are_listed():
    listed = set(tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["setuptools"]["packages"])
    found = {
        ".".join(p.parent.relative_to(ROOT).parts)
        for p in (ROOT / "MCP_Server").rglob("__init__.py")
        if "__pycache__" not in p.parts
    }
    assert found <= listed, f"missing from pyproject packages: {sorted(found - listed)}"
