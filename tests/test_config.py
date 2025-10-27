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
        
