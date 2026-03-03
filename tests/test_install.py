"""Basic installation and import smoke tests."""

from __future__ import annotations

import guaraci
from guaraci.core.config import GuaraciConfig
from guaraci.core.results import JobResult
from guaraci.datasus import SinanDataSource
from guaraci.services import DownloadService
from guaraci.utils.mapping import utility_mapping


def test_imports_and_basic_wiring() -> None:
    assert isinstance(guaraci.__version__, str)
    assert guaraci.__version__

    config = GuaraciConfig()
    assert config.data_root.exists()

    assert utility_mapping(35) == "SP"

    sinan = SinanDataSource()
    assert sinan.name == "sinan"
    assert hasattr(sinan, "download")

    service = DownloadService()
    assert any(source.source == "snis" for source in service.list_sources())

    result = JobResult(source="test")
    assert result.status == "success"
