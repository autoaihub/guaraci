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
