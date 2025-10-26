"""
Tests for Guaraci utility functions.
"""

import pytest
import numpy as np
import pandas as pd
from guaraci.utils.mapping import (
    utility_mapping, validate_uf, get_state_name, get_region, UF_DICT
)


class TestUtilityMapping:
    """Test utility mapping functions."""
    
    def test_numeric_code_mapping(self):
        """Test mapping of numeric UF codes."""
        assert utility_mapping(35) == 'SP'
        assert utility_mapping(33) == 'RJ'
        assert utility_mapping(11) == 'RO'
        
    def test_string_code_mapping(self):
        """Test mapping of string numeric codes."""
        assert utility_mapping('35') == 'SP'
        assert utility_mapping('33') == 'RJ'
        assert utility_mapping(' 11 ') == 'RO'  # with spaces
        
    def test_uf_abbreviation_passthrough(self):
        """Test that valid UF abbreviations pass through unchanged."""
        assert utility_mapping('SP') == 'SP'
        assert utility_mapping('RJ') == 'RJ'
        assert utility_mapping('sp') == 'SP'  # case insensitive
        assert utility_mapping(' SP ') == 'SP'  # with spaces
        
    def test_invalid_inputs(self):
        """Test handling of invalid inputs."""
        assert utility_mapping(None) is None
        assert utility_mapping(np.nan) is None
        assert utility_mapping('') is None
        assert utility_mapping('invalid') is None
        assert utility_mapping(999) is None
        assert utility_mapping('NaN') is None
        
    def test_float_inputs(self):
        """Test handling of float inputs."""
        assert utility_mapping(35.0) == 'SP'
        assert utility_mapping(35.5) == 'SP'  # Should truncate
        assert utility_mapping(float('nan')) is None


class TestValidateUF:
    """Test UF validation function."""
    
    def test_valid_ufs(self):
        """Test validation of valid UF codes."""
        for uf in UF_DICT.values():
            assert validate_uf(uf) is True
            assert validate_uf(uf.lower()) is True
            
    def test_invalid_ufs(self):
        """Test validation of invalid UF codes."""
        assert validate_uf('XX') is False
        assert validate_uf('') is False
        assert validate_uf(None) is False
        assert validate_uf(123) is False


class TestGetStateName:
    """Test state name retrieval function."""
    
    def test_valid_state_names(self):
        """Test retrieval of valid state names."""
        assert get_state_name('SP') == 'São Paulo'
        assert get_state_name('RJ') == 'Rio de Janeiro'
        assert get_state_name('sp') == 'São Paulo'  # case insensitive
        
    def test_invalid_state_names(self):
        """Test handling of invalid UF codes."""
        assert get_state_name('XX') is None
        assert get_state_name('') is None
        assert get_state_name(None) is None


class TestGetRegion:
    """Test region retrieval function."""
    
    def test_valid_regions(self):
        """Test retrieval of valid regions."""
        assert get_region('SP') == 'Sudeste'
        assert get_region('AM') == 'Norte'
        assert get_region('BA') == 'Nordeste'
        assert get_region('RS') == 'Sul'
        assert get_region('GO') == 'Centro-Oeste'
        
    def test_invalid_regions(self):
        """Test handling of invalid UF codes."""
        assert get_region('XX') is None
        assert get_region('') is None
        assert get_region(None) is None