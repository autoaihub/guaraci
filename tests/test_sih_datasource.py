from pathlib import Path
from types import SimpleNamespace

from guaraci.datasus import sih as sih_module
from guaraci.datasus.sih import SihDataSource


class _DummyFtpFile:
    def __init__(self, *, group: str, state: str, year: int, month: int, basename: str):
        self.group = SimpleNamespace(name=group)
        self.state = state
        self.year = year
        self.month = month
        self.basename = basename

    def __str__(self) -> str:
        return self.basename


class _DummySihCatalog:
    def __init__(self, client):  # noqa: ANN001
        self.client = client

    async def _fetch_content(self):
        return [
            _DummyFtpFile(group="RD", state="SP", year=2021, month=1, basename="RDSP2101.dbc"),
            _DummyFtpFile(group="RD", state="RJ", year=2021, month=1, basename="RDRJ2101.dbc"),
            _DummyFtpFile(group="RJ", state="SP", year=2021, month=1, basename="RJSP2101.dbc"),
            object(),
        ]


class _DummyFtpClient:
    async def connect(self):
        return None

    async def close(self):
        return None


class _DummyPySUS:
    downloaded = []

    async def __aenter__(self):
        type(self).downloaded = []
        return self

    async def __aexit__(self, exc_type, exc, tb):  # noqa: ANN001
        return None

    async def get_ftp(self):
        return object()

    async def download_to_parquet(self, file_record):  # noqa: ANN001
        type(self).downloaded.append(file_record.basename)
        return SimpleNamespace(path=Path("/cache") / file_record.basename.replace(".dbc", ".parquet"))


def test_sih_download_discovers_files_from_ftp_catalog(monkeypatch, tmp_path) -> None:  # noqa: ANN001
    monkeypatch.setattr(sih_module, "PYSUS_AVAILABLE", True)
    monkeypatch.setattr(sih_module, "PySUS", _DummyPySUS)
    monkeypatch.setattr(sih_module, "PySUSFtpClient", _DummyFtpClient)
    monkeypatch.setattr(sih_module, "PySUSFtpSIH", _DummySihCatalog)
    monkeypatch.setattr(sih_module, "PySUSFtpFile", _DummyFtpFile)

    datasource = SihDataSource(output_path=str(tmp_path))

    result = datasource.download(
        start_year=2021,
        end_year=2021,
        groups=["RD"],
        states=["SP"],
        months=[1],
    )

    assert result["total_files"] == 1
    assert result["successful_downloads"] == 1
    assert result["failed_downloads"] == []
    assert _DummyPySUS.downloaded == ["RDSP2101.dbc"]
    assert [Path(item).name for item in datasource.data["RD"]] == ["RDSP2101.parquet"]
