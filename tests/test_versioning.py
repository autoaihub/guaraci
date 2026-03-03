"""Version consistency checks across project metadata."""

from __future__ import annotations

import tomllib
from pathlib import Path

import guaraci


def test_package_version_matches_pyproject() -> None:
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    assert guaraci.__version__ == data["project"]["version"]
