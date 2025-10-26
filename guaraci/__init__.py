"""
Guaraci: Brazilian Public Data Integration Platform
==================================================

A comprehensive toolkit for accessing, integrating, and analyzing Brazilian public data,
with initial focus on public health and Neglected Tropical Diseases (NTDs).

Key Features:
- Automated data collection from DATASUS (SINAN, SIH, SIM, SIA)
- Standardized data processing and harmonization
- Scientific-grade reproducible datasets
- CLI and Python API interfaces
- Support for multiple output formats (CSV, Parquet, SQLite)

Quick Start:
-----------
```python
from guaraci.datasus import SinanDataSource

# Initialize SINAN data source
sinan = SinanDataSource()

# Download data for specific diseases and years
sinan.download(start_year=2020, end_year=2022, diseases=['DENG', 'ZIKA'])

# Load as DataFrame
df = sinan.load_dataframe('DENG')

# Apply filters
filtered = sinan.filter(df, uf='SP', sexo='M')

# Export results
sinan.export(filtered, format='csv', name='dengue_sp_male')
```

CLI Usage:
----------
```bash
guaraci sinan download 2020 2022 --diseases DENG ZIKA --format csv
guaraci sinan filter --uf SP --sexo M --input dengue.csv --output filtered.csv
```
"""

__version__ = "0.2.0"
__author__ = "Pedro Guilherme dos Reis Teixeira, Luis"
__email__ = "pedro.guilherme2305@usp.br"

# Core imports for easy access
from guaraci.core.datasource import DataSource
from guaraci.core.config import GuaraciConfig

# Optional imports
try:
    from guaraci.datasus.sinan import SinanDataSource
    _SINAN_AVAILABLE = True
except ImportError:
    _SINAN_AVAILABLE = False
    SinanDataSource = None

__all__ = [
    "DataSource", 
    "GuaraciConfig",
    "__version__"
]

if _SINAN_AVAILABLE:
    __all__.append("SinanDataSource")