"""Regressão: resultado vazio de fonte FTP precisa explicar a cobertura.

Vários sistemas do DATASUS foram descontinuados, e pedir um ano fora da série
devolvia zero arquivos sem motivo, o que é indistinguível de uma falha de
coleta. Verificado ao vivo: CIH publica de 2008 a 2011, SISCAN de 2006 a 2015
e SISPRENATAL de 2012 a 2014.
"""

from __future__ import annotations

import asyncio

import pytest

from guaraci.datasus.ftp import FtpEntry, generic_backend, specs
from guaraci.datasus.ftp.discovery import (
    build_coverage_warning,
    discover_available_years,
)


class FakeClient:
    """Cliente FTP falso servindo uma listagem fixa por diretório."""

    def __init__(self, listings: dict[str, list[str]]) -> None:
        self.listings = listings

    async def __aenter__(self) -> "FakeClient":
        return self

    async def __aexit__(self, *exc) -> None:
        return None

    async def list_dir(self, path: str) -> list[FtpEntry]:
        return [FtpEntry(name=name) for name in self.listings.get(path, [])]

    async def size(self, path: str) -> int:
        return 1234


def _listagem_sisprenatal() -> dict[str, list[str]]:
    root = specs.SISPRENATAL.roots[0]
    return {root: ["PNSP1202.dbc", "PNSP1301.dbc", "PNRJ1402.dbc"]}


def test_available_years_reads_what_the_origin_publishes() -> None:
    client = FakeClient(_listagem_sisprenatal())
    anos = asyncio.run(discover_available_years(client, specs.SISPRENATAL))
    assert anos == [2012, 2013, 2014]


def test_coverage_warning_names_the_published_range() -> None:
    mensagem = build_coverage_warning("cih", [2008, 2009, 2010, 2011])
    assert "cih" in mensagem
    assert "2008-2011" in mensagem


def test_coverage_warning_handles_a_single_year() -> None:
    assert "2012" in build_coverage_warning("sisprenatal", [2012])


def test_coverage_warning_when_nothing_could_be_listed() -> None:
    mensagem = build_coverage_warning("cih", [])
    assert "no published year" in mensagem


def test_empty_discovery_explains_itself(tmp_path) -> None:
    """O ano pedido está fora da série: o vazio vem acompanhado do motivo."""
    summary = generic_backend.discover_summary(
        specs.SISPRENATAL,
        years=[2022],
        client_factory=lambda: FakeClient(_listagem_sisprenatal()),
        fetch_sizes=False,
    )

    assert summary["documents_found"] == 0
    assert summary["warnings"]
    assert "2012-2014" in summary["warnings"][0]


def test_successful_discovery_carries_no_warning() -> None:
    summary = generic_backend.discover_summary(
        specs.SISPRENATAL,
        years=[2012],
        client_factory=lambda: FakeClient(_listagem_sisprenatal()),
        fetch_sizes=False,
    )

    assert summary["documents_found"] == 1
    assert summary["warnings"] == []
