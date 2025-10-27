"""
Tests for Guaraci SINAN integration via PySUS.
"""

import pytest

# Skip this entire test file if PySUS is not available
pytestmark = pytest.mark.skipif(
    not hasattr(__import__('builtins'), 'pysus'),
    reason="Requires PySUS to be installed"
)

from guaraci.datasus.sinan import SinanDataSource


class TestSinanDataSource:
    """Test SINAN data source functionality."""

    def test_initialization(self):
        """Test that the SinanDataSource initializes correctly."""
        sinan = SinanDataSource()
        assert sinan.name == "sinan"
        assert hasattr(sinan, "output_path")

    def test_download_method_exists(self):
        """Ensure download() method is defined."""
        sina
