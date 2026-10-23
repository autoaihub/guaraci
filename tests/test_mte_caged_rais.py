"""Novo CAGED e RAIS do MTE, sem rede: FTP, download e extrator falsos.

Os casos que valem teste dariam dado plausível e errado: mês ou região trocados,
ano de leiaute antigo exportado como se fosse o atual, texto em latin-1 virando
lixo, cabeçalho lido como dado e 7z mantido quando se pediu CSV.
"""

from __future__ import annotations

import contextlib
import io
from pathlib import Path
from typing import Dict, List

import polars as pl
import pytest

from guaraci.core.http import ApiClientError
from guaraci.mte import (
    CAGED_FILES,
    RAIS_FILES,
    SevenZipUnavailable,
    caged_datasource_for,
    rais_datasource_for,
)
from guaraci.mte.pdet import ftp_url
from guaraci.mte.sevenzip import SevenZipExtractor
from guaraci.services.downloads import DownloadService
from guaraci.services.sources import mte as mte_sources

BASE = "/pdet/microdados/NOVO CAGED"
RAIS = "/pdet/microdados/RAIS"
EOL = "\r\n"

_MOV_HEADER = ";".join(f"c{i}" for i in range(28))
_EXC_HEADER = ";".join(f"c{i}" for i in range(30))
_RAIS_HEADER = ",".join(f'"v{i} - Código"' for i in range(62))
_ESTAB_HEADER = ",".join(f'"e{i} - Código"' for i in range(23))


class _Lister:
    def __init__(self, tree: Dict[str, List[str]]) -> None:
        self.tree = tree

    def names(self, path: str) -> List[str]:
        return self.tree.get(path, [])

    def stat(self, path: str):
        return 111, "2026-09-29T17:42:33"


class _Client:
    """Grava a URL como conteúdo do '7z' e conta os downloads."""

    def __init__(self, fail: tuple = ()) -> None:
        self.urls: List[str] = []
        self.fail = fail

    def download(self, url: str, destination: Path, **_kwargs) -> int:
        if any(url.endswith(f) for f in self.fail):
            raise ApiClientError("boom", category="http_error", retryable=False)
        self.urls.append(url)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"7z:" + url.encode())
        return 3

    @property
    def downloads(self) -> int:
        return len(self.urls)


class _Extractor(SevenZipExtractor):
    """Devolve o texto escolhido pela URL que o cliente falso gravou no arquivo."""

    def __init__(self, text_for) -> None:
        super().__init__(binary="/fake/7z")
        self.text_for = text_for

    @contextlib.contextmanager
    def open(self, archive: Path):
        url = Path(archive).read_bytes().decode()[3:]
        yield io.BytesIO(self.text_for(url))


class _NoExtractor(SevenZipExtractor):
    def backend(self) -> str:
        raise SevenZipUnavailable("Instale o 7-Zip")


def _caged_tree(months=("202607", "202608"), files=("MOV", "FOR", "EXC")) -> Dict[str, List[str]]:
    tree: Dict[str, List[str]] = {f"{BASE}/2026": list(months)}
    for month in months:
        tree[f"{BASE}/2026/{month}"] = [f"CAGED{f}{month}.7z" for f in files]
    return tree


def _row(n: int, first: str, last: str = "SÃO") -> str:
    return ";".join([first] + ["0"] * (n - 2) + [last])


def _caged_text(url: str) -> bytes:
    header, n = (_EXC_HEADER, 30) if "CAGEDEXC" in url else (_MOV_HEADER, 28)
    month = url.rsplit(".", 1)[0][-6:]
    return f"{header}{EOL}{_row(n, month)}{EOL}".encode("utf-8")


def _caged(tmp_path: Path, key: str, tree=None, client=None, extractor=None):
    return caged_datasource_for(key)(
        output_path=str(tmp_path),
        lister=_Lister(tree if tree is not None else _caged_tree()),
        client=client or _Client(),
        extractor=extractor or _Extractor(_caged_text),
    )


def test_registra_as_cinco_chaves_com_o_schema_esperado() -> None:
    service = DownloadService(sources=mte_sources.build_sources())
    keys = [
        "mte_novo_caged_movimentacoes",
        "mte_novo_caged_fora_prazo",
        "mte_novo_caged_exclusoes",
        "mte_rais_vinculos",
        "mte_rais_estabelecimentos",
    ]
    assert list(CAGED_FILES) + list(RAIS_FILES) == keys
    for key in keys:
        schema = service.get_source_schema(key)
        names = {p["name"] for p in schema["params"]}
        assert {"output_format", "output_dir", "keep_raw", "timeout", "anos"} <= names
    rais = {p["name"] for p in service.get_source_schema("mte_rais_vinculos")["params"]}
    assert "regioes" in rais
    caged = {p["name"] for p in service.get_source_schema("mte_novo_caged_movimentacoes")["params"]}
    assert {"start_date", "end_date", "meses"} <= caged


def test_url_ftp_codifica_o_espaco_da_pasta() -> None:
    assert ftp_url(f"{BASE}/2026/202608/CAGEDEXC202608.7z") == (
        "ftp://ftp.mtps.gov.br/pdet/microdados/NOVO%20CAGED/2026/202608/CAGEDEXC202608.7z"
    )


def test_sem_pedido_baixa_so_o_ultimo_mes_publicado(tmp_path: Path) -> None:
    client = _Client()
    source = _caged(tmp_path, "mte_novo_caged_exclusoes", client=client)
    payload = source.download(output_dir=str(tmp_path), output_format="csv")
    assert client.urls == [ftp_url(f"{BASE}/2026/202608/CAGEDEXC202608.7z")]
    assert [Path(p).name for p in payload["exported_files"]] == [
        "mte_novo_caged_exclusoes_202608.csv"
    ]
    assert not list(tmp_path.glob("*.7z"))  # raw apagado


def test_exporta_utf8_com_30_colunas_sem_aviso_de_leiaute(tmp_path: Path) -> None:
    source = _caged(tmp_path, "mte_novo_caged_exclusoes")
    payload = source.download(output_dir=str(tmp_path), output_format="csv", anos=[2026], meses=[8])
    frame = pl.read_csv(payload["exported_files"][0], infer_schema=False)
    assert frame.width == 30
    assert frame.row(0)[0] == "202608"
    assert frame.row(0)[-1] == "SÃO"
    assert payload["export_warning"] is None


def test_janela_por_data_vira_meses_e_mes_nao_publicado_vira_aviso(tmp_path: Path) -> None:
    client = _Client()
    source = _caged(tmp_path, "mte_novo_caged_movimentacoes", client=client)
    payload = source.download(
        output_dir=str(tmp_path),
        output_format="csv",
        start_date="2026-07-15",
        end_date="30/09/2026",
    )
    assert client.downloads == 2
    assert payload["documents_found"] == 2
    assert "202609: mês ainda não publicado" in payload["export_warning"]


def test_ano_anterior_ao_piso_e_erro(tmp_path: Path) -> None:
    source = _caged(tmp_path, "mte_novo_caged_movimentacoes")
    with pytest.raises(ValueError, match="2020"):
        source.download(output_dir=str(tmp_path), anos=[2019])


def test_arquivo_ausente_no_mes_vira_aviso_sem_baixar(tmp_path: Path) -> None:
    tree = _caged_tree(months=("202607", "202608"), files=("MOV",))
    client = _Client()
    source = _caged(tmp_path, "mte_novo_caged_fora_prazo", tree=tree, client=client)
    payload = source.download(
        output_dir=str(tmp_path), output_format="csv", anos=[2026], meses=[7, 8]
    )
    assert client.downloads == 0
    assert "sem CAGEDFOR202607.7z" in payload["export_warning"]


def test_numero_de_colunas_diferente_vira_aviso(tmp_path: Path) -> None:
    def text(url: str) -> bytes:  # EXC deveria ter 30 colunas
        return f"{_MOV_HEADER}{EOL}{_row(28, '202608')}{EOL}".encode()

    source = _caged(tmp_path, "mte_novo_caged_exclusoes", extractor=_Extractor(text))
    payload = source.download(output_dir=str(tmp_path), output_format="csv")
    assert "28 colunas, esperadas 30" in payload["export_warning"]


def test_sem_formato_mantem_o_7z_e_nao_exige_extrator(tmp_path: Path) -> None:
    source = _caged(tmp_path, "mte_novo_caged_movimentacoes", extractor=_NoExtractor())
    payload = source.download(output_dir=str(tmp_path))
    assert payload["exported_files"] == []
    assert (tmp_path / "mte_novo_caged_movimentacoes_202608.7z").exists()


def test_sem_extrator_falha_antes_de_baixar(tmp_path: Path) -> None:
    client = _Client()
    source = _caged(tmp_path, "mte_novo_caged_movimentacoes", client=client, extractor=_NoExtractor())
    with pytest.raises(SevenZipUnavailable, match="7-Zip"):
        source.download(output_dir=str(tmp_path), output_format="csv")
    assert client.downloads == 0


def test_arquivo_ja_baixado_com_mesmo_tamanho_nao_baixa_de_novo(tmp_path: Path) -> None:
    client = _Client()
    source = _caged(tmp_path, "mte_novo_caged_movimentacoes", client=client)
    (tmp_path / "mte_novo_caged_movimentacoes_202608.7z").write_bytes(b"x" * 111)
    payload = source.download(output_dir=str(tmp_path), output_format="csv")
    assert client.downloads == 0
    assert payload["skipped_count"] == 1


def test_falha_de_um_mes_e_isolada_quando_ha_varios(tmp_path: Path) -> None:
    client = _Client(fail=("CAGEDMOV202607.7z",))
    source = _caged(tmp_path, "mte_novo_caged_movimentacoes", client=client)
    payload = source.download(
        output_dir=str(tmp_path), output_format="csv", anos=[2026], meses=[7, 8]
    )
    assert payload["failed_count"] == 1
    assert payload["downloaded_count"] == 1
    assert "202607" in payload["export_warning"]


def test_falha_de_mes_unico_sobe(tmp_path: Path) -> None:
    client = _Client(fail=("CAGEDMOV202608.7z",))
    source = _caged(tmp_path, "mte_novo_caged_movimentacoes", client=client)
    with pytest.raises(ApiClientError):
        source.download(output_dir=str(tmp_path), output_format="csv")


def _rais_tree(year: int = 2024) -> Dict[str, List[str]]:
    return {
        f"{RAIS}/{year}": [
            "Comunicado - Microdados RAIS 2024 \x97 Ministério.htm",
            "RAIS_ESTAB_PUB.7z",
            "RAIS_VINC_PUB_CENTRO_OESTE.7z",
            "RAIS_VINC_PUB_NI.7z",
            "RAIS_VINC_PUB_SP.7z",
        ]
    }


def _rais_text(url: str) -> bytes:
    header, n = (_ESTAB_HEADER, 23) if "ESTAB" in url else (_RAIS_HEADER, 62)
    row = ",".join(['" 52117"'] + ["0"] * (n - 2) + ['"Código ç"'])
    return f"{header}{EOL}{row}{EOL}".encode("cp1252")


def _rais(tmp_path: Path, key: str, client=None):
    return rais_datasource_for(key)(
        output_path=str(tmp_path),
        lister=_Lister(_rais_tree()),
        client=client or _Client(),
        extractor=_Extractor(_rais_text),
    )


def test_rais_sem_ano_e_erro_e_ano_antigo_nao_exporta(tmp_path: Path) -> None:
    source = _rais(tmp_path, "mte_rais_vinculos")
    with pytest.raises(ValueError, match="informe 'anos'"):
        source.download(output_dir=str(tmp_path))
    with pytest.raises(ValueError, match="2023"):
        source.download(output_dir=str(tmp_path), anos=[2022])


def test_rais_vinculos_um_csv_por_regiao_e_filtra_regioes(tmp_path: Path) -> None:
    source = _rais(tmp_path, "mte_rais_vinculos")
    payload = source.download(output_dir=str(tmp_path), output_format="csv", anos=[2024])
    assert sorted(Path(p).name for p in payload["exported_files"]) == [
        "mte_rais_vinculos_2024_CENTRO_OESTE.csv",
        "mte_rais_vinculos_2024_NI.csv",
        "mte_rais_vinculos_2024_SP.csv",
    ]
    assert payload["export_warning"] is None
    only = _rais(tmp_path / "b", "mte_rais_vinculos").download(
        output_dir=str(tmp_path / "b"), output_format="csv", start_year=2024, regioes=["sp"]
    )
    assert [Path(p).name for p in only["exported_files"]] == ["mte_rais_vinculos_2024_SP.csv"]


def test_rais_regiao_desconhecida_e_erro(tmp_path: Path) -> None:
    source = _rais(tmp_path, "mte_rais_vinculos")
    with pytest.raises(ValueError, match="Unknown regioes"):
        source.download(output_dir=str(tmp_path), anos=[2024], regioes=["XX"])


def test_rais_le_virgula_aspas_e_latin1_sem_aviso_de_colunas(tmp_path: Path) -> None:
    source = _rais(tmp_path, "mte_rais_estabelecimentos")
    payload = source.download(output_dir=str(tmp_path), output_format="csv", anos=[2024])
    assert [Path(p).name for p in payload["exported_files"]] == [
        "mte_rais_estabelecimentos_2024.csv"
    ]
    frame = pl.read_csv(payload["exported_files"][0], infer_schema=False)
    assert frame.width == 23
    assert frame.columns[0] == "e0 - Código"
    assert frame.row(0)[0] == " 52117"  # espaço à esquerda como publicado
    assert frame.row(0)[-1] == "Código ç"
    assert payload["export_warning"] is None


def test_rais_ano_nao_publicado_vira_aviso(tmp_path: Path) -> None:
    source = _rais(tmp_path, "mte_rais_estabelecimentos")
    payload = source.download(output_dir=str(tmp_path), output_format="csv", anos=[2025])
    assert payload["documents_found"] == 0
    assert "2025: pasta da RAIS ainda não publicada" in payload["export_warning"]
