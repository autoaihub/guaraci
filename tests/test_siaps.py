"""Testes offline das fontes SIAPS (API DEMAS), com cliente falso."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from guaraci.opendatasus.datasource import OpenDataSUSDataSource
from guaraci.services.downloads import DownloadService, OpenDataSUSDownloadSource
from guaraci.services.sources.siaps import SIAPS_MAX_PAGES, _normalize_siaps_params

ATENDIMENTO = "atencao-primaria/siaps-atendimento-individual"
PATH = "/atencao-primaria/siaps-atendimento-individual"


class _FakeSiapsClient:
    """Serve ``total`` linhas sinteticas com offset em LINHAS, como o DEMAS."""

    mode = "demas"
    base_url = "https://apidadosabertos.saude.gov.br"

    def __init__(self, total: int) -> None:
        self.total = total
        self.calls: list[dict] = []

    def demas_get(self, path: str, params):  # noqa: ANN001
        self.calls.append({"path": path, **params})
        offset = int(params.get("offset", 0))
        limit = int(params.get("limit", 100))
        end = min(offset + limit, self.total)
        rows = [
            {
                "co_uf_ibge": 52,
                "competencia_siaps": params.get("competencia_siaps"),
                "raca_cor": "4 - PARDA",
                "tipo_de_estabelecimento": " UBS",
                "qtd_registros_atendimento": float(i),
                "qtd_pessoas_atendidas": float(i),
            }
            for i in range(offset, end)
        ]
        return {"siaps_atendimento_individual": rows}


def _read_csv(path: str) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _download(tmp_path: Path, client, **kwargs):  # noqa: ANN001
    params = _normalize_siaps_params(dict(kwargs))
    params.pop("output_dir", None)
    datasource = OpenDataSUSDataSource(output_path=str(tmp_path), client=client)
    return datasource.download(dataset=ATENDIMENTO, **params)


def test_datas_viram_competencia_e_descartam_datas() -> None:
    out = _normalize_siaps_params({"start_date": "2026-06-01", "end_date": "2026-06-30"})
    assert out["competencia_siaps"] == "202606"
    assert "start_date" not in out and "end_date" not in out


def test_competencia_explicita_tem_precedencia() -> None:
    out = _normalize_siaps_params({"competencia_siaps": "202512", "start_date": "2026-06-01"})
    assert out["competencia_siaps"] == "202512"


def test_intervalo_de_mais_de_um_mes_e_rejeitado() -> None:
    with pytest.raises(ValueError, match="same month"):
        _normalize_siaps_params({"start_date": "2026-05-01", "end_date": "2026-06-30"})


def test_competencia_malformada_e_rejeitada() -> None:
    with pytest.raises(ValueError, match="YYYYMM"):
        _normalize_siaps_params({"competencia_siaps": "2026-06"})


def test_max_pages_padrao_e_o_teto_do_coletor() -> None:
    assert _normalize_siaps_params({})["max_pages"] == SIAPS_MAX_PAGES == 200000
    assert _normalize_siaps_params({"max_pages": 1})["max_pages"] == 1


def test_pagina_ate_a_pagina_vazia_e_converte_data(tmp_path: Path) -> None:
    # 2 paginas cheias de 10 linhas; a terceira vem vazia e encerra.
    client = _FakeSiapsClient(total=20)
    payload = _download(
        tmp_path,
        client,
        start_date="2026-06-01",
        end_date="2026-06-30",
        batch_size=10,
        output_format="csv",
    )
    assert [c["offset"] for c in client.calls] == [0, 10, 20]
    assert all(c["competencia_siaps"] == "202606" for c in client.calls)
    assert all(c["path"] == PATH for c in client.calls)
    rows = _read_csv(payload["exported_files"][0])
    assert len(rows) == 20
    # sem inferencia de tipo: texto como veio (prefixo de codigo e espaco inicial)
    assert rows[0]["raca_cor"] == "4 - PARDA"
    assert rows[0]["tipo_de_estabelecimento"] == " UBS"


def test_competencia_longa_nao_trunca_em_250_paginas(tmp_path: Path) -> None:
    # 300 paginas de 10 linhas: acima dos 250 do DEFAULT_MAX_PAGES.
    total = 300 * 10 - 3
    assert OpenDataSUSDataSource.DEFAULT_MAX_PAGES == 250

    # Controle: com o padrao antigo a coleta trunca e so avisa no manifesto.
    controle_client = _FakeSiapsClient(total=total)
    controle = OpenDataSUSDataSource(
        output_path=str(tmp_path / "controle"), client=controle_client
    ).download(
        dataset=ATENDIMENTO,
        competencia_siaps="202512",
        batch_size=10,
        output_format="csv",
    )
    assert len(_read_csv(controle["exported_files"][0])) == 250 * 10

    # Com o padrao da fonte, a competencia vem inteira e sem aviso de teto.
    client = _FakeSiapsClient(total=total)
    payload = _download(
        tmp_path / "siaps",
        client,
        competencia_siaps="202512",
        batch_size=10,
        output_format="csv",
    )
    rows = _read_csv(payload["exported_files"][0])
    assert len(rows) == total
    assert len(client.calls) == 300
    assert not any("max_pages" in w for w in payload.get("warnings", []))


def test_fontes_registradas_com_chave_modo_e_esquema() -> None:
    service = DownloadService()
    for chave, extra, ausente in (
        ("atencao_primaria_siaps_atendimento_individual", "co_uf_ibge", "regiao"),
        ("atencao_primaria_siaps_cadastro_individual", "regiao", "co_uf_ibge"),
    ):
        info = service.get_source_schema(chave)
        assert info["mode"] == "siaps api"
        schema = {spec["name"]: spec for spec in info["params"]}
        assert extra in schema and ausente not in schema
        for nome in (
            "start_date",
            "end_date",
            "competencia_siaps",
            "municipio",
            "batch_size",
            "max_pages",
            "output_dir",
            "output_format",
            "keep_raw",
            "api_base_url",
        ):
            assert nome in schema
        assert schema["max_pages"]["default"] == SIAPS_MAX_PAGES
        source = service._sources[chave]  # noqa: SLF001
        assert isinstance(source, OpenDataSUSDownloadSource)
        source.validate_params({"start_date": "2026-06-01", "end_date": "2026-06-30"})


def test_endpoints_resolvem_pelo_swagger_local() -> None:
    datasource = OpenDataSUSDataSource(client=_FakeSiapsClient(total=0))
    for caminho in (
        "/atencao-primaria/siaps-atendimento-individual",
        "/atencao-primaria/siaps-cadastro-individual",
    ):
        assert caminho in datasource._demas_get_params_by_path  # noqa: SLF001
