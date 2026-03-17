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

__version__ = "0.4.1"
__author__ = (
    "Luis Felipe Vogel Lopes, "
    "Pedro Guilherme dos Reis Teixeira, "
    "Robson Parmezan Bonidia, "
    "André Carlos Ponce de Leon Ferreira de Carvalho"
)
__email__ = "vogel@usp.br"

# Core imports for easy access
from guaraci.core.config import GuaraciConfig
from guaraci.core.datasource import DataSource
from guaraci.core.results import JobResult

# Optional imports
try:
    from guaraci.datasus.sinan import SinanDataSource

    _SINAN_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    _SINAN_AVAILABLE = False
    SinanDataSource = None  # type: ignore

try:
    from guaraci.datasus.sim import SimDataSource

    _SIM_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    _SIM_AVAILABLE = False
    SimDataSource = None  # type: ignore

try:
    from guaraci.datasus.sih import SihDataSource

    _SIH_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    _SIH_AVAILABLE = False
    SihDataSource = None  # type: ignore

try:
    from guaraci.snis import SnisDataSource

    _SNIS_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    _SNIS_AVAILABLE = False
    SnisDataSource = None  # type: ignore

try:
    from guaraci.snis import SinisaDataSource

    _SINISA_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    _SINISA_AVAILABLE = False
    SinisaDataSource = None  # type: ignore

try:
    from guaraci.opendatasus import OpenDataSUSDataSource

    _OPENDATASUS_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    _OPENDATASUS_AVAILABLE = False
    OpenDataSUSDataSource = None  # type: ignore

__all__ = [
    "DataSource",
    "GuaraciConfig",
    "JobResult",
    "__version__",
]

if _SINAN_AVAILABLE:
    __all__.append("SinanDataSource")
if _SIM_AVAILABLE:
    __all__.append("SimDataSource")
if _SIH_AVAILABLE:
    __all__.append("SihDataSource")
if _SNIS_AVAILABLE:
    __all__.append("SnisDataSource")
if _SINISA_AVAILABLE:
    __all__.append("SinisaDataSource")
if _OPENDATASUS_AVAILABLE:
    __all__.append("OpenDataSUSDataSource")
