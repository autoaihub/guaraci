
"""
Guaraci Utility Mappings
========================

Utility functions and dictionaries for data processing and standardization.
"""

import numpy as np
import pandas as pd
from typing import Union, Optional


# Brazilian state codes mapping (IBGE codes to UF abbreviations)
UF_DICT = {
    11: 'RO', 12: 'AC', 13: 'AM', 14: 'RR', 15: 'PA', 16: 'AP', 17: 'TO',
    21: 'MA', 22: 'PI', 23: 'CE', 24: 'RN', 25: 'PB', 26: 'PE', 27: 'AL',
    28: 'SE', 29: 'BA', 31: 'MG', 32: 'ES', 33: 'RJ', 35: 'SP', 41: 'PR',
    42: 'SC', 43: 'RS', 50: 'MS', 51: 'MT', 52: 'GO', 53: 'DF'
}

# Reverse mapping for validation
UF_TO_CODE = {v: k for k, v in UF_DICT.items()}

# Full state names for reference
STATE_NAMES = {
    'RO': 'Rondônia', 'AC': 'Acre', 'AM': 'Amazonas', 'RR': 'Roraima',
    'PA': 'Pará', 'AP': 'Amapá', 'TO': 'Tocantins', 'MA': 'Maranhão',
    'PI': 'Piauí', 'CE': 'Ceará', 'RN': 'Rio Grande do Norte',
    'PB': 'Paraíba', 'PE': 'Pernambuco', 'AL': 'Alagoas', 'SE': 'Sergipe',
    'BA': 'Bahia', 'MG': 'Minas Gerais', 'ES': 'Espírito Santo',
    'RJ': 'Rio de Janeiro', 'SP': 'São Paulo', 'PR': 'Paraná',
    'SC': 'Santa Catarina', 'RS': 'Rio Grande do Sul', 'MS': 'Mato Grosso do Sul',
    'MT': 'Mato Grosso', 'GO': 'Goiás', 'DF': 'Distrito Federal'
}


def utility_mapping(uf_value: Union[str, int, float, None]) -> Optional[str]:
    """
    Convert UF codes to standardized state abbreviations.
    
    Parameters
    ----------
    uf_value : str, int, float, or None
        UF value to be mapped (can be numeric code or string abbreviation)
        
    Returns
    -------
    str or None
        Standardized UF abbreviation or None if invalid
        
    Examples
    --------
    >>> utility_mapping(35)
    'SP'
    >>> utility_mapping('35')
    'SP'
    >>> utility_mapping('SP')
    'SP'
    >>> utility_mapping(None)
    None
    """
    if uf_value is None or pd.isna(uf_value):
        return None
    
    # Handle string inputs
    if isinstance(uf_value, str):
        uf_clean = uf_value.strip().upper()
        
        # Empty or invalid strings
        if not uf_clean or uf_clean in ['NAN', 'NONE', 'NULL', '0', '']:
            return None
            
        # Already a valid UF abbreviation
        if uf_clean in UF_DICT.values():
            return uf_clean
            
        # Try to convert string to numeric
        try:
            numeric_value = int(float(uf_clean))
            return UF_DICT.get(numeric_value)
        except (ValueError, TypeError):
            return None
    
    # Handle numeric inputs
    elif isinstance(uf_value, (int, float, np.integer, np.floating)):
        if np.isnan(float(uf_value)):
            return None
        try:
            numeric_code = int(uf_value)
            return UF_DICT.get(numeric_code)
        except (ValueError, TypeError):
            return None
    
    return None


def validate_uf(uf: str) -> bool:
    """
    Validate if a string is a valid UF abbreviation.
    
    Parameters
    ----------
    uf : str
        UF abbreviation to validate
        
    Returns
    -------
    bool
        True if valid UF, False otherwise
    """
    if not isinstance(uf, str):
        return False
    return uf.upper().strip() in UF_DICT.values()


def get_state_name(uf: str) -> Optional[str]:
    """
    Get full state name from UF abbreviation.
    
    Parameters
    ----------
    uf : str
        UF abbreviation
        
    Returns
    -------
    str or None
        Full state name or None if invalid UF
    """
    if validate_uf(uf):
        return STATE_NAMES.get(uf.upper().strip())
    return None


def get_region(uf: str) -> Optional[str]:
    """
    Get Brazilian region from UF abbreviation.
    
    Parameters
    ----------
    uf : str
        UF abbreviation
        
    Returns
    -------
    str or None
        Brazilian region name or None if invalid UF
    """
    if not validate_uf(uf):
        return None
        
    uf_upper = uf.upper().strip()
    
    regions = {
        'Norte': ['RO', 'AC', 'AM', 'RR', 'PA', 'AP', 'TO'],
        'Nordeste': ['MA', 'PI', 'CE', 'RN', 'PB', 'PE', 'AL', 'SE', 'BA'],
        'Centro-Oeste': ['MS', 'MT', 'GO', 'DF'],
        'Sudeste': ['MG', 'ES', 'RJ', 'SP'],
        'Sul': ['PR', 'SC', 'RS']
    }
    
    for region, states in regions.items():
        if uf_upper in states:
            return region
    
    return None
