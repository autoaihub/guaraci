"""Smoke opt-in das fontes novas do Pacote A, turno 2 (rede real).

Desligado por padrão; ``GUARACI_ARQUIVOS_EXT2_SMOKE=1`` liga. Usa o menor recorte de cada
fonte: Ligue 180 1S2020 (50 MB), agregados do Censo 2022 por município (alfabetização) e
renda do responsável por setor (9 MB), projeções tab4 e tab1, IDEB ensino médio 2019 e 2023
e MUNIC 2024 (25 MB, cerca de 3 min). MapBiomas (56 e 78 MB, cerca de 2 min por planilha)
só roda com ``GUARACI_ARQUIVOS_EXT2_SMOKE_GRANDE=1``.
"""

from __future__ import annotations

import os
from pathlib import Path

import polars as pl
import pytest

from guaraci.arquivos import ibge_ftp, inep_ideb, mapbiomas, seguranca
from guaraci.arquivos.http_files import datasource_for_spec

SMOKE = os.environ.get("GUARACI_ARQUIVOS_EXT2_SMOKE") == "1"
GRANDE = os.environ.get("GUARACI_ARQUIVOS_EXT2_SMOKE_GRANDE") == "1"
pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(
        not SMOKE, reason="Set GUARACI_ARQUIVOS_EXT2_SMOKE=1 to enable the live file smoke test"
    ),
]


def _run(source, tmp_path: Path, **kwargs):
    out = tmp_path / "out"
    payload = source.download(output_dir=str(out), output_format="csv", **kwargs)
    return payload, [Path(p) for p in payload["exported_files"]]


def _columns(path: Path):
    return pl.scan_csv(path, infer_schema=False).collect_schema().names()


def test_ligue180_primeiro_semestre_2020(tmp_path: Path) -> None:
    spec = seguranca.MDHC_LIGUE180
    source = datasource_for_spec(spec)(output_path=str(tmp_path / "out"))
    _payload, files = _run(source, tmp_path, anos=[2020], meses=["S1"])
    cols = _columns(files[0])
    assert len(files) == 1 and len(cols) == 34


def test_censo_municipios_alfabetizacao(tmp_path: Path) -> None:
    source = ibge_ftp.IbgeCensoSetoresDataSource(output_path=str(tmp_path / "out"))
    _payload, files = _run(source, tmp_path, indicadores=["alfabetizacao"], nivel="municipio")
    assert files[0].name == "ibge_censo2022_setores_municipio_alfabetizacao.csv"
    assert _columns(files[0])[:2] == ["CD_MUN", "NM_MUN"]


def test_censo_renda_responsavel_setor(tmp_path: Path) -> None:
    source = ibge_ftp.IbgeCensoRendaDataSource(output_path=str(tmp_path / "out"))
    _payload, files = _run(source, tmp_path)
    assert _columns(files[0])[0] == "CD_SETOR" and len(_columns(files[0])) == 7


def test_projecoes_tab4_e_tab1(tmp_path: Path) -> None:
    source = datasource_for_spec(ibge_ftp.IBGE_PROJECOES_POPULACAO_2024)(
        output_path=str(tmp_path / "out")
    )
    _payload, files = _run(source, tmp_path, indicadores=["tab4", "tab1"])
    by_name = {f.name: f for f in files}
    assert _columns(by_name["ibge_projecoes_populacao_2024_tab4.csv"])[:4] == [
        "ANO", "CÓD.", "SIGLA", "LOCAL",
    ]
    assert _columns(by_name["ibge_projecoes_populacao_2024_tab1.csv"])[:5] == [
        "IDADE", "SEXO", "CÓD.", "SIGLA", "LOCAL",
    ]


@pytest.mark.parametrize("ano", [2019, 2023])
def test_ideb_ensino_medio(tmp_path: Path, ano: int) -> None:
    source = datasource_for_spec(inep_ideb.INEP_IDEB_MUNICIPIOS)(output_path=str(tmp_path / "out"))
    _payload, files = _run(source, tmp_path, anos=[ano], meses=["EM"])
    assert _columns(files[0])[:3] == ["SG_UF", "CO_MUNICIPIO", "NO_MUNICIPIO"]


def test_munic_2024_todas_as_abas(tmp_path: Path) -> None:
    source = datasource_for_spec(ibge_ftp.IBGE_MUNIC)(output_path=str(tmp_path / "out"))
    _payload, files = _run(source, tmp_path)
    assert len(files) == 10


@pytest.mark.skipif(not GRANDE, reason="Set GUARACI_ARQUIVOS_EXT2_SMOKE_GRANDE=1 (56 e 78 MB)")
@pytest.mark.parametrize("spec", mapbiomas.SPECS, ids=lambda s: s.key)
def test_mapbiomas(tmp_path: Path, spec) -> None:
    source = datasource_for_spec(spec)(output_path=str(tmp_path / "out"))
    _payload, files = _run(source, tmp_path)
    cols = _columns(files[0])
    assert len(files) == 1 and "geocode" in cols and len(cols) >= 52
