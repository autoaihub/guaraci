# 🇧🇷 Guaraci: Brazilian Public Data Integration Platform

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

A comprehensive toolkit for accessing, integrating, and analyzing Brazilian public data, with initial focus on public health and Neglected Tropical Diseases (NTDs).

## 🎯 Overview

Guaraci addresses a critical gap in Brazilian public health data accessibility. While databases exist for high-visibility diseases like COVID-19 and tuberculosis, Neglected Tropical Diseases (NTDs) remain underrepresented in computational epidemiology. Guaraci provides:

- **Unified Access**: Single interface to multiple Brazilian health databases (DATASUS, SINAN, SIH, SIM, SIA)
- **Scientific Reproducibility**: Standardized, versioned datasets with complete metadata
- **Performance Optimized**: Concurrent downloads and memory-efficient processing
- **Multiple Interfaces**: Both Python API and CLI for different use cases

## 🚀 Quick Start

### Instalação via pip

Escolha conforme a necessidade:

- Núcleo (sem DATASUS nem API): `pip install guaraci`
- DATASUS (PySUS: SINAN/SIM/SIH): `pip install "guaraci[datasus]"`
- API (FastAPI/uvicorn/httpx): `pip install "guaraci[api]"`
- Completo (todos os extras): `pip install "guaraci[full]"`

### Docker Setup (Recommended)

```bash
# Clone the repository
git clone https://github.com/autoaihub/guaraci.git
cd guaraci

# Build the Docker image
docker build -t guaraci .

# Run Guaraci commands
docker run --rm -it -v "$(pwd):/app" guaraci python -m guaraci.cli.main --help
```

### Download SINAN Data (Docker)

```bash
# Download data for specific diseases and years
docker run --rm -it -v "$(pwd):/app" guaraci \
  python -m guaraci.cli.sinan_cli download 2020 2022 \
  --diseases DENG ZIKA --format csv

# Download single disease for one year
docker run --rm -it -v "$(pwd):/app" guaraci \
  python -m guaraci.cli.sinan_cli download 2020 2020 \
  --diseases RAIV --format csv
```

### Python API (Inside Docker)

```bash
# Interactive Python session
docker run --rm -it -v "$(pwd):/app" guaraci python

# Then in Python:
from guaraci.datasus import SinanDataSource

# Initialize SINAN data source
sinan = SinanDataSource()

# Download data
sinan.download(start_year=2020, end_year=2020, diseases=['RAIV'])

# Load as DataFrame
df = sinan.load_dataframe('RAIV')

# Apply filters
filtered = sinan.filter(df, uf='SP')

# Export results
sinan.export(filtered, format='csv', name='raiva_sp')
```

### Available CLI Commands

```bash
# Show platform information
docker run --rm guaraci python -m guaraci.cli.main info

# Download SINAN data
docker run --rm -it -v "$(pwd):/app" guaraci \
  python -m guaraci.cli.sinan_cli download 2020 2020 --diseases DENG --format csv

# Filter existing data (after download)
docker run --rm -it -v "$(pwd):/app" guaraci \
  python -m guaraci.cli.sinan_cli filter DENG --uf SP --output filtered_dengue

# Generate summary statistics
docker run --rm -it -v "$(pwd):/app" guaraci \
  python -m guaraci.cli.sinan_cli summary DENG --by UF --metric count

# Get information about available fields
docker run --rm -it -v "$(pwd):/app" guaraci \
  python -m guaraci.cli.sinan_cli info DENG
```

## 📊 Supported Data Sources

### SINAN (Sistema de Informação de Agravos de Notificação)
- **Focus**: Notifiable diseases surveillance
- **Coverage**: 2007-present
- **Diseases**: All SINAN diseases with emphasis on NTDs
- **Format**: Parquet, CSV, SQLite

#### Supported Neglected Tropical Diseases
- `ANIM` - Acidentes por Animais Peçonhentos
- `CHAG` - Doença de Chagas  
- `CHIK` - Chikungunya
- `DENG` - Dengue
- `ESQU` - Esquistossomose
- `HANS` - Hanseníase
- `LEIV` - Leishmaniose Visceral
- `LTAN` - Leishmaniose Tegumentar
- `RAIV` - Raiva Humana

## 🛠 Development Setup

### Docker-Based Development (Recommended)

```bash
# Clone repository
git clone https://github.com/autoaihub/guaraci.git
cd guaraci

# Build the Docker image
docker build -t guaraci .

# Run tests
docker run --rm guaraci python -m pytest tests/ -v

# Interactive development shell
docker run --rm -it -v "$(pwd):/app" guaraci bash

# Run specific commands
docker run --rm -it -v "$(pwd):/app" guaraci python -c "import guaraci; print(guaraci.__version__)"
```

### Windows Users

```powershell
# Use full paths for volume mounting
docker run --rm -it -v "C:\path\to\guaraci:/app" guaraci python -m guaraci.cli.main info

# Example with actual path (single line)
docker run --rm -it -v "C:\Users\username\Documents\guaraci:/app" guaraci python -m guaraci.cli.sinan_cli download 2020 2020 --diseases RAIV --format csv

# Multi-line with PowerShell backtick continuation
docker run --rm -it -v "C:\Users\username\Documents\guaraci:/app" guaraci `
  python -m guaraci.cli.sinan_cli download 2020 2020 --diseases RAIV --format csv
```

## 📖 Documentation

### Configuration

Guaraci can be configured using environment variables in Docker:

```bash
# Run with custom configuration
docker run --rm -it -v "$(pwd):/app" \
  -e GUARACI_DATA_ROOT=/app/data \
  -e GUARACI_LOG_LEVEL=DEBUG \
  -e GUARACI_MAX_CONCURRENT_DOWNLOADS=10 \
  guaraci python -m guaraci.cli.sinan_cli download 2020 2020 --diseases DENG
```

### Advanced Usage (Python API in Docker)

```bash
# Start interactive Python session
docker run --rm -it -v "$(pwd):/app" guaraci python

# Then in Python:
from guaraci.datasus import SinanDataSource
from guaraci.core.config import config

# View current configuration
print(f"Data root: {config.data_root}")
print(f"Max downloads: {config.max_concurrent_downloads}")

# Initialize with custom settings
sinan = SinanDataSource()

# Download with specific parameters
sinan.download(2020, 2021, diseases=['DENG'])

# Load and process data
df = sinan.load_dataframe('DENG')

# Advanced filtering
filtered = sinan.filter(
    df,
    uf='SP',
    municipio='São Paulo',
    ano=2021
)

# Generate summary statistics
summary = sinan.summary(filtered, by='CS_SEXO', metric='count')
print(summary)

# Export results
sinan.export(filtered, format='csv', name='dengue_sp_2021')
```

## 🧪 Testing

All testing is done within Docker containers:

```bash
# Run all tests
docker run --rm guaraci python -m pytest tests/ -v

# Run with coverage
docker run --rm guaraci python -m pytest tests/ --cov=guaraci --cov-report=term-missing

# Run specific test file
docker run --rm guaraci python -m pytest tests/test_utils.py -v

# Test installation
docker run --rm guaraci python test_install.py
```

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guidelines](CONTRIBUTING.md) for details.

### Development Workflow

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Add tests for new functionality
5. Run the test suite (`pytest`)
6. Commit your changes (`git commit -m 'Add amazing feature'`)
7. Push to the branch (`git push origin feature/amazing-feature`)
8. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 👥 Authors & Contributors

- **Luis Felipe Vogel Lopes** – *Lead Developer (v0.2 and ongoing)* – vogel@usp.br  
  Responsible for the full modernization of Guaraci, including modular architecture, Docker-first workflow, Pydantic configuration system, enhanced CLI, and full testing suite.

- **Pedro Guilherme dos Reis Teixeira** – *Original Author (v0.1)* – pedro.guilherme2305@usp.br  
  Created the initial Guaraci prototype and early SINAN integration.

- **Prof. Robson Parmezan Bonidia** – *Scientific Advisor* – ICMC/USP  
- **Prof. André Carlos Ponce de Leon Ferreira de Carvalho** – *Scientific Advisor* – ICMC/USP

## 🙏 Acknowledgments

- [PySUS](https://github.com/AlertaDengue/PySUS) - Foundation for DATASUS integration
- [Polars](https://pola.rs/) - High-performance DataFrame library
- [ICMC/USP](https://www.icmc.usp.br/) - Institutional support
- Brazilian Ministry of Health - Data provision through DATASUS

## 📚 Citation

If you use Guaraci in your research, please cite:

```bibtex
@software{guaraci2025,
  title     = {Guaraci: Brazilian Public Data Integration Platform},
  author    = {Lopes, Luis Felipe Vogel and Teixeira, Pedro Guilherme dos Reis and Bonidia, Robson Parmezan and Carvalho, André Carlos Ponce de Leon Ferreira de},
  year      = {2025},
  version   = {0.2},
  url       = {https://github.com/autoaihub/guaraci}
}
```

## 🔗 Links

- [Documentation](https://guaraci.readthedocs.io) (Coming Soon)
- [PyPI Package](https://pypi.org/project/guaraci) (Coming Soon)
- [Issue Tracker](https://github.com/autoaihub/guaraci/issues)
- [DATASUS](https://datasus.saude.gov.br/)
- [PySUS Documentation](https://pysus.readthedocs.io/)
## 📝 Changelog

Veja `CHANGELOG.md` para histórico de versões e novidades.
