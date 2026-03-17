"""Version consistency checks across project metadata."""

from __future__ import annotations

import tomllib
from pathlib import Path

import guaraci

EXPECTED_AUTHORS = [
    "Luis Felipe Vogel Lopes",
    "Pedro Guilherme dos Reis Teixeira",
    "Robson Parmezan Bonidia",
    "André Carlos Ponce de Leon Ferreira de Carvalho",
]

EXPECTED_CITATION_AUTHORS = [
    ('given-names: "Luis Felipe"\n    family-names: "Vogel Lopes"'),
    ('given-names: "Pedro Guilherme"\n    family-names: "dos Reis Teixeira"'),
    ('given-names: "Robson Parmezan"\n    family-names: "Bonidia"'),
    (
        'given-names: "André Carlos Ponce de Leon Ferreira"\n'
        '    family-names: "de Carvalho"'
    ),
]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_pyproject() -> dict:
    pyproject = _repo_root() / "pyproject.toml"
    return tomllib.loads(pyproject.read_text(encoding="utf-8"))


def test_package_version_matches_pyproject() -> None:
    data = _load_pyproject()
    assert guaraci.__version__ == data["project"]["version"]


def test_pyproject_authors_are_in_expected_order() -> None:
    data = _load_pyproject()
    authors = [author["name"] for author in data["project"]["authors"]]
    assert authors == EXPECTED_AUTHORS


def test_citation_metadata_matches_current_version_and_author_order() -> None:
    data = _load_pyproject()
    citation = (_repo_root() / "CITATION.cff").read_text(encoding="utf-8")

    assert f'version: "{data["project"]["version"]}"' in citation

    previous_index = -1
    for author_block in EXPECTED_CITATION_AUTHORS:
        current_index = citation.find(author_block)
        assert current_index > previous_index
        previous_index = current_index


def test_readme_mentions_current_version() -> None:
    data = _load_pyproject()
    readme = (_repo_root() / "README.md").read_text(encoding="utf-8")
    assert f'Current version: `{data["project"]["version"]}`' in readme


def test_dockerfile_version_label_matches_pyproject() -> None:
    data = _load_pyproject()
    dockerfile = (_repo_root() / "dockerfile").read_text(encoding="utf-8")
    assert f'LABEL version="{data["project"]["version"]}"' in dockerfile
