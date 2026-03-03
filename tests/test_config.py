"""
Tests for Guaraci configuration system.
"""

from guaraci.core.config import GuaraciConfig


class TestGuaraciConfig:
    """Test configuration management."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = GuaraciConfig()
        
        # Check that data_root is set (may be different in Docker vs local)
        assert config.data_root.name == "data" or str(config.data_root).endswith("/data")
        assert config.default_format == "csv"
        assert config.log_level == "INFO"
        assert config.max_concurrent_downloads == 5
        
    def test_path_creation(self):
        """Test that paths are created automatically."""
        config = GuaraciConfig()
        
        # Paths should be created during initialization
        assert config.data_root.exists()
        assert config.temp_dir.exists()
        
    def test_get_datasus_path(self):
        """Test DATASUS path generation."""
        config = GuaraciConfig()
        
        sinan_path = config.get_datasus_path("sinan")
        expected_path = config.data_root / "datasus" / "sinan"
        
        assert sinan_path == expected_path
        assert sinan_path.exists()

    def test_get_datasus_path_uses_default_download_root(self, tmp_path, monkeypatch):
        """When configured, source outputs should use the user download root."""
        custom_root = tmp_path / "Guaraci Downloads"
        monkeypatch.setenv("GUARACI_DEFAULT_DOWNLOAD_ROOT", str(custom_root))

        config = GuaraciConfig()
        sinan_path = config.get_datasus_path("sinan")

        assert sinan_path == custom_root / "sinan"
        assert sinan_path.exists()

    def test_get_datasus_path_accepts_legacy_default_output_root_env(self, tmp_path, monkeypatch):
        """Backwards compatibility for launcher env var name."""
        legacy_root = tmp_path / "Legacy Downloads"
        monkeypatch.setenv("GUARACI_DEFAULT_OUTPUT_ROOT", str(legacy_root))
        monkeypatch.delenv("GUARACI_DEFAULT_DOWNLOAD_ROOT", raising=False)

        config = GuaraciConfig()
        sim_path = config.get_datasus_path("sim")

        assert sim_path == legacy_root / "sim"
        assert sim_path.exists()
        
