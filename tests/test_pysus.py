"""Tests for Guaraci DATASUS integrations when PySUS is available."""

from __future__ import annotations

import importlib.util

import pytest

from guaraci.datasus.sinan import SinanDataSource

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("pysus") is None,
    reason="Requires PySUS to be installed",
)


class TestSinanDataSource:
    """Test SINAN datasource contracts that do not require live downloads."""

    def test_initialization(self) -> None:
        sinan = SinanDataSource()
        assert sinan.name == "sinan"
        assert hasattr(sinan, "output_path")

    def test_download_method_exists(self) -> None:
        sinan = SinanDataSource()
        assert callable(sinan.download)
