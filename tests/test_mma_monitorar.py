"""MonitorAr (MMA) sem rede: zip fake em cp1252 e recursos de mentira."""

from __future__ import annotations

import zipfile
from pathlib import Path

import polars as pl

from guaraci.mma import MonitorArDataSource, MonitorArResource
from guaraci.services.downloads import DownloadService

_COLUMNS = (
    "no_fonte_dados,dh_medicao,nu_iqar,nu_concentracao,st_situacao,cd_flag,ds_flag,"
    "st_situacao_iqar,no_item_monitorado,cd_normalizado,id_estacao,cod_estacao,"
    "no_estacao,nu_latitude,nu_longitude,st_estacao,id_municipio,no_municipio,sg_uf"
)
_CSV = (
    _COLUMNS + "\r\n"
    '"Rede, SP","2025-01-01 00:00:00.000",12,"0,5",A,,,V,Ozônio,O3,1,E1,"Estação Sé",'
    "-23.5,-46.6,A,3550308,São Paulo,SP\r\n"
    '"Rede, SP","2025-01-01 01:00:00.000",,1013.2,A,,,,Pressão,PRESS,1,E1,"Estação Sé",'
    "-23.5,-46.6,A,3550308,São Paulo,SP\r\n"
    '"Rede, PR","2025-01-01 02:00:00.000",005,3.0,A,,,V,Monóxido,CO,2,E2,Curitiba,'
    "-25.4,-49.2,A,4106902,Curitiba,PR\r\n"
).encode("cp1252")


class _Client:
    def __init__(self, tmp: Path, years=(2022, 2024, 2025)) -> None:
        self.tmp = tmp
        self.years = years
        self.downloaded: list = []

    def package_url(self) -> str:
        return "https://x/package_show?id=ar-puro-monitorar"

    def list_resources(self):
        return [MonitorArResource(y, f"Dados - {y}", f"https://x/{y}.zip", None) for y in self.years]

    def download(self, resource, destination: Path, **_kwargs) -> int:
        self.downloaded.append(resource.year)
        with zipfile.ZipFile(destination, "w") as archive:
            archive.writestr(f"dados_monitorar_{resource.year}.csv", _CSV)
        return destination.stat().st_size


def test_zip_cp1252_vira_csv_utf8_com_19_colunas(tmp_path):
    source = MonitorArDataSource(output_path=str(tmp_path), client=_Client(tmp_path))
    payload = source.download(start_year=2025, output_format="csv")
    assert payload["failed_count"] == 0
    (path,) = payload["exported_files"]
    assert Path(path).name == "mma_monitorar_2025.csv"
    frame = pl.read_csv(path, infer_schema=False)
    assert len(frame.columns) == 19
    assert frame.height == 3
    assert frame["no_fonte_dados"][0] == "Rede, SP"
    assert frame["no_item_monitorado"][0] == "Ozônio"
    assert frame["nu_iqar"][2] == "005"  # zero à esquerda preservado
    assert frame["nu_iqar"][1] is None  # meteorologia sem IQAr
    assert frame["cd_normalizado"][1] == "PRESS"
    assert not (tmp_path / "dados_monitorar_2025.zip").exists()


def test_utf8_e_detectado_sem_corromper_acentos(tmp_path):
    from guaraci.mma.monitorar import zip_to_utf8

    archive_path = tmp_path / "a.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("x.csv", _CSV.decode("cp1252").encode("utf-8"))
    out = tmp_path / "out.csv"
    zip_to_utf8(archive_path, out)
    assert "Estação Sé" in out.read_text(encoding="utf-8")


def test_filtro_de_ano_descarta_recursos_fora_da_janela(tmp_path):
    client = _Client(tmp_path)
    source = MonitorArDataSource(output_path=str(tmp_path), client=client)
    payload = source.download(start_year=2023, end_year=2025, output_format="csv")
    assert client.downloaded == [2024, 2025]
    assert payload["years"] == [2024, 2025]
    assert len(payload["exported_files"]) == 2


def test_sem_formato_guarda_o_zip(tmp_path):
    source = MonitorArDataSource(output_path=str(tmp_path), client=_Client(tmp_path))
    payload = source.download(start_year=2022)
    assert (tmp_path / "dados_monitorar_2022.zip").exists()
    assert payload["exported_files"] == []
    assert payload["export_warning"]


def test_fonte_registrada_com_schema():
    schema = DownloadService().get_source_schema("mma_monitorar")
    assert schema is not None
    assert "start_year" in str(schema) and "output_format" in str(schema)


def test_lista_recursos_por_format_zip_ou_url_com_query(monkeypatch):
    import json

    from guaraci.mma import MonitorArClient

    items = [
        {"name": "Dados - 2022", "url": "https://x/a/download", "format": "ZIP"},
        {"name": "Dados - 2023", "url": "https://x/b.ZIP?token=1", "format": ""},
        {"name": "Dados - 2024", "url": "https://x/c.zip", "format": "zip"},
        {"name": "Dicionário - 2024", "url": "https://x/d.pdf", "format": "PDF"},
        {"name": "Dados - 2025", "url": "https://x/e.csv", "format": "CSV"},
    ]
    body = json.dumps({"result": {"resources": items}}).encode()

    class Resp:
        def read(self):
            return body

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr("guaraci.mma.monitorar.urlopen", lambda *_a, **_k: Resp())
    years = [r.year for r in MonitorArClient(max_attempts=1).list_resources()]
    assert years == [2022, 2023, 2024]


def test_anos_pedidos_sem_recurso_viram_aviso(tmp_path):
    source = MonitorArDataSource(output_path=str(tmp_path), client=_Client(tmp_path))
    payload = source.download(start_year=2022, end_year=2025, output_format="csv")
    assert payload["years"] == [2022, 2024, 2025]
    assert "2023" in payload["export_warning"]


def test_sem_anos_pedidos_nao_ha_aviso_de_ano_faltando(tmp_path):
    source = MonitorArDataSource(output_path=str(tmp_path), client=_Client(tmp_path))
    payload = source.download(output_format="csv")
    assert payload["export_warning"] is None


def test_linha_cp1252_depois_do_primeiro_bloco_sai_com_acento(tmp_path):
    # Primeiro MB em ASCII e uma linha cp1252 adiante: a decisão é por linha.
    filler = ("a" * 99 + "\n") * 11000
    body = ("col\n" + filler).encode("utf-8") + b"Esta\xe7\xe3o\n"
    assert len(body) > (1 << 20)

    class Cp1252Client(_Client):
        def download(self, resource, destination: Path, **_kwargs) -> int:
            with zipfile.ZipFile(destination, "w") as archive:
                archive.writestr("dados.csv", body)
            return destination.stat().st_size

    source = MonitorArDataSource(output_path=str(tmp_path), client=Cp1252Client(tmp_path))
    payload = source.download(start_year=2025, output_format="csv")
    assert payload["failed_count"] == 0 and len(payload["exported_files"]) == 1
    assert not payload["export_warning"]
    assert "Estação" in Path(payload["exported_files"][0]).read_text(encoding="utf-8")


def test_u_fffd_que_ja_vem_da_origem_e_avisado_como_da_origem(tmp_path):
    body = "col\nEsta��o\n".encode("utf-8")

    class OriginClient(_Client):
        def download(self, resource, destination: Path, **_kwargs) -> int:
            with zipfile.ZipFile(destination, "w") as archive:
                archive.writestr("dados.csv", body)
            return destination.stat().st_size

    source = MonitorArDataSource(output_path=str(tmp_path), client=OriginClient(tmp_path))
    payload = source.download(start_year=2025, output_format="csv")
    assert "já traz 2 caracteres" in payload["export_warning"]
    assert "na conversão para UTF-8" not in payload["export_warning"]


class _FakeResponse:
    def __init__(self, body: bytes, length: int) -> None:
        self.headers = {"Content-Length": str(length)}
        self._body = body

    def read(self, size=-1):
        body, self._body = self._body, b""
        return body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _resource() -> MonitorArResource:
    return MonitorArResource(2025, "Dados - 2025", "https://x/2025.zip", None)


def test_download_truncado_contra_content_length_e_erro_retentavel_sem_part(tmp_path, monkeypatch):
    import pytest

    from guaraci.mma import MonitorArClient, MonitorArClientError

    monkeypatch.setattr(
        "guaraci.mma.monitorar.urlopen", lambda *_a, **_k: _FakeResponse(b"PK\x03\x04", 100)
    )
    destination = tmp_path / "a.zip"
    with pytest.raises(MonitorArClientError, match="truncated: 4 of 100") as info:
        MonitorArClient(max_attempts=1).download(_resource(), destination)
    assert info.value.retryable is True
    assert not destination.exists()
    assert list(tmp_path.glob("*.part")) == []


def test_download_que_nao_e_zip_valido_falha_mesmo_com_tamanho_completo(tmp_path, monkeypatch):
    import pytest

    from guaraci.mma import MonitorArClient, MonitorArClientError

    body = b"<html>pagina de erro</html>"
    monkeypatch.setattr(
        "guaraci.mma.monitorar.urlopen", lambda *_a, **_k: _FakeResponse(body, len(body))
    )
    destination = tmp_path / "a.zip"
    with pytest.raises(MonitorArClientError, match="not a valid zip") as info:
        MonitorArClient(max_attempts=1).download(_resource(), destination)
    assert info.value.retryable is True
    assert not destination.exists()
    assert list(tmp_path.glob("*.part")) == []


def test_exportacao_com_falha_nao_deixa_arquivo_final_nem_part(tmp_path, monkeypatch):
    import pytest

    def boom(self, dest, *_a, **_k):
        Path(dest).write_text("parcial")  # o sink já começou a gravar quando quebra
        raise RuntimeError("disco cheio")

    monkeypatch.setattr(pl.LazyFrame, "sink_csv", boom)
    source = MonitorArDataSource(output_path=str(tmp_path), client=_Client(tmp_path))
    with pytest.raises(RuntimeError, match="disco cheio"):
        source.download(start_year=2025, output_format="csv")
    assert not (tmp_path / "mma_monitorar_2025.csv").exists()
    assert list(tmp_path.glob("*.part")) == []
