"""RAIS 1985-2022 e CAGED antigo do MTE, sem rede: FTP, download e extrator falsos.

Os casos que valem teste dariam dado plausível e errado: UF filtrada em ano regional,
ano fora da faixa baixado como se existisse, ajuste anual de 2002-2009 buscado como mensal
e Estb de 2003 (zip) tratado como 7z.
"""

from __future__ import annotations

import contextlib
import io
import zipfile
from pathlib import Path
from typing import Dict, List

import pytest

from guaraci.mte import (
    CAGED_ANTIGO_FILES,
    RAIS_HISTORICO_FILES,
    caged_antigo_datasource_for,
    rais_historico_datasource_for,
)
from guaraci.mte.sevenzip import SevenZipExtractor
from guaraci.services.downloads import DownloadService
from guaraci.services.sources import mte_historico

RAIS = "/pdet/microdados/RAIS"
CAGED = "/pdet/microdados/CAGED"
AJUSTES = "/pdet/microdados/CAGED_AJUSTES"
TEXT = "Município;Sexo;Dup;Dup\r\n120040;01;a;b\r\n".encode("latin-1")


class _Lister:
    def __init__(self, tree: Dict[str, List[str]]) -> None:
        self.tree = tree

    def names(self, path: str) -> List[str]:
        return self.tree.get(path, [])

    def stat(self, path: str):
        return 111, "2016-04-25T14:33:55"


class _Client:
    def __init__(self, as_zip: bool = False) -> None:
        self.urls: List[str] = []
        self.as_zip = as_zip

    def download(self, url: str, destination: Path, **_kwargs) -> int:
        self.urls.append(url)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if self.as_zip and url.lower().endswith(".zip"):
            with zipfile.ZipFile(destination, "w") as handle:
                handle.writestr("ESTB.txt", TEXT)
        else:
            destination.write_bytes(b"7z:" + url.encode())
        return 3


class _Extractor(SevenZipExtractor):
    def __init__(self) -> None:
        super().__init__(binary="/fake/7z")

    @contextlib.contextmanager
    def open(self, archive: Path):
        yield io.BytesIO(TEXT)


def _rais(tmp_path: Path, key: str, tree, client=None):
    return rais_historico_datasource_for(key)(
        output_path=str(tmp_path),
        lister=_Lister(tree),
        client=client or _Client(),
        extractor=_Extractor(),
    )


def test_registra_quatro_chaves_com_schema() -> None:
    service = DownloadService(sources=mte_historico.build_sources())
    assert list(RAIS_HISTORICO_FILES) + list(CAGED_ANTIGO_FILES) == [
        "mte_rais_vinculos_historico",
        "mte_rais_estabelecimentos_historico",
        "mte_caged_antigo",
        "mte_caged_antigo_ajustes",
    ]
    names = {p["name"] for p in service.get_source_schema("mte_rais_vinculos_historico")["params"]}
    assert {"anos", "ufs", "regioes", "output_format"} <= names


def test_ate_2017_filtra_uf_e_agrupa_ignorados(tmp_path: Path) -> None:
    tree = {f"{RAIS}/2010": ["AC2010.7z", "RR2010.7z", "IGNORADOS2010.7z", "ESTB2010.7z"]}
    client = _Client()
    payload = _rais(tmp_path, "mte_rais_vinculos_historico", tree, client).download(
        anos=[2010], ufs=["rr", "ignorados"], output_format="csv"
    )
    assert [Path(p).name for p in payload["exported_files"]] == [
        "mte_rais_vinculos_historico_2010_IGNORADOS.csv",
        "mte_rais_vinculos_historico_2010_RR.csv",
    ]
    assert not any("AC2010" in u or "ESTB" in u for u in client.urls)
    text = Path(payload["exported_files"][1]).read_text(encoding="utf-8")
    assert "Município" in text.splitlines()[0]  # latin-1 virou UTF-8 sem lixo


def test_de_2018_usa_regiao_e_avisa_que_uf_nao_se_aplica(tmp_path: Path) -> None:
    tree = {f"{RAIS}/2018": ["RAIS_VINC_PUB_SUL.7z", "RAIS_VINC_PUB_NORTE.7z", "RAIS_ESTAB_PUB.7z"]}
    payload = _rais(tmp_path, "mte_rais_vinculos_historico", tree).download(
        anos=[2018], regioes=["SUL"], output_format="csv"
    )
    assert [Path(p).name for p in payload["exported_files"]] == [
        "mte_rais_vinculos_historico_2018_SUL.csv"
    ]
    payload = _rais(tmp_path, "mte_rais_vinculos_historico", tree).download(
        anos=[2018], ufs=["AC"], output_format="csv"
    )
    assert payload["downloaded_count"] == 2  # ufs ignorado, as duas regiões vieram


def test_estabelecimentos_2003_vem_em_zip(tmp_path: Path) -> None:
    tree = {f"{RAIS}/2003": ["Estb2003.zip"]}
    payload = _rais(
        tmp_path, "mte_rais_estabelecimentos_historico", tree, _Client(as_zip=True)
    ).download(anos=[2003], output_format="csv")
    assert [Path(p).name for p in payload["exported_files"]] == [
        "mte_rais_estabelecimentos_historico_2003.csv"
    ]


@pytest.mark.parametrize("anos", [[1984], [2023], []])
def test_rais_recusa_ano_fora_da_faixa_ou_sem_ano(tmp_path: Path, anos) -> None:
    with pytest.raises(ValueError):
        _rais(tmp_path, "mte_rais_vinculos_historico", {}).download(anos=anos)


def test_ano_sem_pasta_vira_aviso(tmp_path: Path) -> None:
    payload = _rais(tmp_path, "mte_rais_vinculos_historico", {}).download(
        anos=[1990], output_format="csv"
    )
    assert payload["downloaded_count"] == 0
    assert "1990" in str(payload.get("warnings") or payload.get("export_warning") or payload)


def _caged(tmp_path: Path, key: str, tree, client=None):
    return caged_antigo_datasource_for(key)(
        output_path=str(tmp_path),
        lister=_Lister(tree),
        client=client or _Client(),
        extractor=_Extractor(),
    )


def test_caged_antigo_mensal_e_ajustes_anual_e_mensal(tmp_path: Path) -> None:
    client = _Client()
    tree = {
        f"{CAGED}/2010": ["CAGEDEST_032010.7z"],
        f"{AJUSTES}/2002a2009": ["CAGEDEST_AJUSTES_2005.7z"],
        f"{AJUSTES}/2012": ["CAGEDEST_AJUSTES_052012.7z"],
    }
    got = _caged(tmp_path, "mte_caged_antigo", tree, client).download(
        anos=[2010], meses=[3], output_format="csv"
    )
    assert [Path(p).name for p in got["exported_files"]] == ["mte_caged_antigo_201003.csv"]
    got = _caged(tmp_path, "mte_caged_antigo_ajustes", tree, client).download(
        anos=[2005], output_format="csv"
    )
    assert [Path(p).name for p in got["exported_files"]] == ["mte_caged_antigo_ajustes_2005.csv"]
    assert got["downloaded_count"] == 1  # 12 meses pedidos, 1 arquivo anual
    got = _caged(tmp_path, "mte_caged_antigo_ajustes", tree, client).download(
        anos=[2012], meses=[5], output_format="csv"
    )
    assert [Path(p).name for p in got["exported_files"]] == [
        "mte_caged_antigo_ajustes_201205.csv"
    ]


@pytest.mark.parametrize(
    "kwargs", [{"anos": [2006]}, {"anos": [2020]}, {}], ids=["antes", "novo_caged", "vazio"]
)
def test_caged_antigo_recusa_fora_da_faixa(tmp_path: Path, kwargs) -> None:
    with pytest.raises(ValueError):
        _caged(tmp_path, "mte_caged_antigo", {}).download(**kwargs)
