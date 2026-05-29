"""Tests for the shared DATASUS backend selector.

:mod:`guaraci.datasus.backend` is the dependency-free leaf that SIH, SIM
and SINAN all consult to choose between the legacy PySUS path and the new
direct-FTP layer. The per-source switch tests verify *dispatch*; this file
pins the selector *contract* in one place so the Phase 4 default flip is a
single-line change here (plus :data:`DEFAULT_BACKEND` itself).
"""

from __future__ import annotations

from guaraci.datasus import backend


def test_default_backend_value_is_pysus_in_phase_3() -> None:
    # Phase 4 (PLANO_DATASUS_FTP_DIRETO §6) flips this to BACKEND_FTP.
    assert backend.DEFAULT_BACKEND == backend.BACKEND_PYSUS


def test_get_returns_default_when_env_unset(monkeypatch) -> None:
    monkeypatch.delenv("GUARACI_DATASUS_BACKEND", raising=False)
    assert backend.get_datasus_backend() == backend.DEFAULT_BACKEND


def test_get_returns_ftp_when_env_set_to_ftp(monkeypatch) -> None:
    monkeypatch.setenv("GUARACI_DATASUS_BACKEND", "ftp")
    assert backend.get_datasus_backend() == "ftp"


def test_get_returns_pysus_when_env_set_to_pysus(monkeypatch) -> None:
    monkeypatch.setenv("GUARACI_DATASUS_BACKEND", "pysus")
    assert backend.get_datasus_backend() == "pysus"


def test_unknown_value_falls_back_to_default(monkeypatch) -> None:
    monkeypatch.setenv("GUARACI_DATASUS_BACKEND", "nonsense")
    assert backend.get_datasus_backend() == backend.DEFAULT_BACKEND


def test_value_is_case_insensitive_and_stripped(monkeypatch) -> None:
    monkeypatch.setenv("GUARACI_DATASUS_BACKEND", "  FTP  ")
    assert backend.get_datasus_backend() == "ftp"


def test_explicit_default_arg_is_honoured_when_env_unset(monkeypatch) -> None:
    monkeypatch.delenv("GUARACI_DATASUS_BACKEND", raising=False)
    assert backend.get_datasus_backend(default="ftp") == "ftp"
