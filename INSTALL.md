# � Guaaraci Docker Installation Guide

Guaraci is designed to run exclusively in Docker containers to ensure consistent environments and avoid dependency conflicts. This approach eliminates the need for local Python environment management.

## Prerequisites

- **Docker Desktop** (Windows/Mac) or **Docker Engine** (Linux)
- **Git** for cloning the repository

### Install Docker

- **Windows/Mac**: Download [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- **Linux**: Follow the [official Docker installation guide](https://docs.docker.com/engine/install/)

## Quick Start

### 1. Clone and Build

```bash
# Clone the repository
git clone https://github.com/autoaihub/guaraci.git
cd guaraci

# Build the Docker image (this may take a few minutes)
docker build -t guaraci .
```

### 2. Verify Installation

```bash
# Test the installation
docker run --rm guaraci python test_install.py

# Check version
docker run --rm guaraci python -c "import guaraci; print(f'Guaraci v{guaraci.__version__}')"

# Run tests
docker run --rm guaraci python -m pytest tests/ -v
```

### 3. Basic Usage

```bash
# Show help
docker run --rm guaraci python -m guaraci.cli.main --help

# Download SINAN data (replace path with your actual directory)
docker run --rm -it -v "$(pwd):/app" guaraci \
  python -m guaraci.cli.sinan_cli download 2020 2020 --diseases RAIV --format csv
```

## Platform-Specific Instructions

### Windows (PowerShell)

```powershell
# Clone repository
git clone https://github.com/autoaihub/guaraci.git
cd guaraci

# Build image
docker build -t guaraci .

# Run with full path (replace with your actual path) - single line recommended
docker run --rm -it -v "C:\Users\YourUsername\Documents\guaraci:/app" guaraci python -m guaraci.cli.sinan_cli download 2020 2020 --diseases RAIV --format csv

# Alternative: Multi-line with PowerShell backtick continuation
docker run --rm -it -v "C:\Users\YourUsername\Documents\guaraci:/app" guaraci `
  python -m guaraci.cli.sinan_cli download 2020 2020 --diseases RAIV --format csv
```

### Linux/Mac (Bash)

```bash
# Clone repository
git clone https://github.com/autoaihub/guaraci.git
cd guaraci

# Build image
docker build -t guaraci .

# Run with current directory mounted
docker run --rm -it -v "$(pwd):/app" guaraci \
  python -m guaraci.cli.sinan_cli download 2020 2020 --diseases RAIV --format csv
```

## Common Usage Patterns

### Data Download

```bash
# Download single disease for one year
docker run --rm -it -v "$(pwd):/app" guaraci \
  python -m guaraci.cli.sinan_cli download 2020 2020 --diseases RAIV --format csv

# Download multiple diseases for multiple years
docker run --rm -it -v "$(pwd):/app" guaraci \
  python -m guaraci.cli.sinan_cli download 2018 2020 --diseases DENG ZIKA CHIK --format csv

# Download with different output format
docker run --rm -it -v "$(pwd):/app" guaraci \
  python -m guaraci.cli.sinan_cli download 2020 2020 --diseases HANS --format parquet
```

### Interactive Development

```bash
# Start interactive Python session
docker run --rm -it -v "$(pwd):/app" guaraci python

# Start bash shell for development
docker run --rm -it -v "$(pwd):/app" guaraci bash

# Run specific Python script
docker run --rm -it -v "$(pwd):/app" guaraci python your_script.py
```

### Configuration

```bash
# Run with custom environment variables
docker run --rm -it -v "$(pwd):/app" \
  -e GUARACI_LOG_LEVEL=DEBUG \
  -e GUARACI_MAX_CONCURRENT_DOWNLOADS=10 \
  guaraci python -m guaraci.cli.sinan_cli download 2020 2020 --diseases DENG
```

## Data Output

All downloaded data will be saved to the `data/` directory in your project folder:

```
your-project/
├── data/
│   └── datasus/
│       └── sinan/
│           ├── RAIV_2020_2020.csv
│           ├── DENG_2018_2020.csv
│           └── ...
└── ...
```

## Troubleshooting

### Docker Build Issues

```bash
# Clean build (if you encounter caching issues)
docker build --no-cache -t guaraci .

# Check Docker version
docker --version

# Ensure Docker is running
docker ps
```

### Volume Mount Issues

```bash
# Windows: Use full paths with forward slashes
docker run --rm -it -v "C:/Users/YourName/Documents/guaraci:/app" guaraci

# Linux/Mac: Ensure directory permissions
chmod 755 $(pwd)
```

### PowerShell Line Continuation Issues

```powershell
# ❌ Wrong: Using bash-style backslash (will fail)
docker run --rm -it -v "C:\Users\Name\guaraci:/app" guaraci \
  python -m guaraci.cli.sinan_cli download 2020 2020 --diseases RAIV

# ✅ Correct: Single line
docker run --rm -it -v "C:\Users\Name\guaraci:/app" guaraci python -m guaraci.cli.sinan_cli download 2020 2020 --diseases RAIV

# ✅ Correct: PowerShell backtick continuation
docker run --rm -it -v "C:\Users\Name\guaraci:/app" guaraci `
  python -m guaraci.cli.sinan_cli download 2020 2020 --diseases RAIV
```

### Memory Issues

```bash
# Run with increased memory limit
docker run --rm -it --memory=4g -v "$(pwd):/app" guaraci \
  python -m guaraci.cli.sinan_cli download 2015 2020 --diseases DENG
```

## Development Setup

### For Contributors

```bash
# Clone and build
git clone https://github.com/autoaihub/guaraci.git
cd guaraci
docker build -t guaraci .

# Run tests
docker run --rm guaraci python -m pytest tests/ -v

# Code formatting (if you modify code)
docker run --rm -v "$(pwd):/app" guaraci python -m black guaraci/
docker run --rm -v "$(pwd):/app" guaraci python -m isort guaraci/

# Type checking
docker run --rm -v "$(pwd):/app" guaraci python -m mypy guaraci/
```

### Rebuilding After Changes

```bash
# After modifying code, rebuild the image
docker build -t guaraci .

# Or use a different tag for testing
docker build -t guaraci:dev .
docker run --rm guaraci:dev python test_install.py
```

## Getting Help

### Check Logs

```bash
# Run with verbose logging
docker run --rm -it -v "$(pwd):/app" \
  -e GUARACI_LOG_LEVEL=DEBUG \
  guaraci python -m guaraci.cli.sinan_cli download 2020 2020 --diseases RAIV
```

### Common Issues

1. **"No such file or directory"**: Check your volume mount path
2. **"Permission denied"**: Ensure Docker has access to your directory
3. **"Out of memory"**: Use `--memory` flag to increase container memory
4. **"Build failed"**: Try `docker build --no-cache -t guaraci .`

### Support

If you encounter issues:

1. Check the [Issues](https://github.com/autoaihub/guaraci/issues) page
2. Create a new issue with:
   - Your operating system
   - Docker version (`docker --version`)
   - Full error message
   - Command you were trying to run

## Why Docker-Only?

- **Consistent Environment**: Same setup across Windows, Mac, and Linux
- **No Dependency Conflicts**: All dependencies are managed within the container
- **Easy Updates**: Simply rebuild the Docker image
- **Isolation**: Doesn't affect your local Python environment
- **Reproducibility**: Ensures scientific reproducibility across different machines