# 🐳 Guaraci Docker Workflow

This document outlines the complete Docker-based workflow for the Guaraci platform.

## Why Docker-Only?

After extensive testing and optimization, Guaraci has adopted a Docker-first approach for several critical reasons:

1. **Dependency Hell Elimination**: PySUS and related packages have complex C dependencies that often fail on different systems
2. **Consistent Environments**: Same behavior across Windows, Mac, and Linux
3. **Scientific Reproducibility**: Ensures identical results across different machines and time periods
4. **Zero Local Installation**: No need to manage Python environments or system dependencies
5. **Easy Updates**: Simply rebuild the Docker image for updates

## Complete Workflow

### Initial Setup

```bash
# 1. Clone the repository
git clone https://github.com/autoaihub/guaraci.git
cd guaraci

# 2. Build the Docker image (one-time setup)
docker build -t guaraci .

# 3. Verify installation
docker run --rm guaraci python test_install.py
```

### Daily Usage

```bash
# Download SINAN data
docker run --rm -it -v "$(pwd):/app" guaraci \ python -m guaraci.cli.sinan_cli download 2020 2020 --diseases RAIV --format csv

# Interactive Python session
docker run --rm -it -v "$(pwd):/app" guaraci python

# Run tests
docker run --rm guaraci python -m pytest tests/ -v

# Development shell
docker run --rm -it -v "$(pwd):/app" guaraci bash
```

### Data Management

All data is automatically saved to your local directory through Docker volume mounting:

```
your-project/
├── data/
│   ├── datasus/
│   │   └── sinan/
│   │       ├── RAIV_2020_2020.csv
│   │       ├── DENG_2018_2020.parquet
│   │       └── ...
│   └── .cache/          # Processed data cache
│       └── sinan/
└── ...
```

### Platform-Specific Commands

#### Windows (PowerShell)

```powershell
docker run --rm -it -v "C:\Users\YourName\Documents\guaraci:/app" guaraci `
  python -m guaraci.cli.sinan_cli download 2020 2020 --diseases RAIV --format csv
```

#### Linux/Mac (Bash)

```bash
docker run --rm -it -v "$(pwd):/app" guaraci \
  python -m guaraci.cli.sinan_cli download 2020 2020 --diseases RAIV --format csv
```

## Available Commands

### CLI Commands

```bash
# Show platform info
docker run --rm guaraci python -m guaraci.cli.main info

# Download data
docker run --rm -it -v "$(pwd):/app" guaraci \
  python -m guaraci.cli.sinan_cli download START_YEAR END_YEAR --diseases DISEASE_CODES --format FORMAT

# Filter data
docker run --rm -it -v "$(pwd):/app" guaraci \
  python -m guaraci.cli.sinan_cli filter DISEASE --uf STATE --output OUTPUT_NAME

# Generate summaries
docker run --rm -it -v "$(pwd):/app" guaraci \
  python -m guaraci.cli.sinan_cli summary DISEASE --by COLUMN --metric METRIC

# Show field information
docker run --rm -it -v "$(pwd):/app" guaraci \
  python -m guaraci.cli.sinan_cli info DISEASE
```

### Python API

```python
# Start interactive session
docker run --rm -it -v "$(pwd):/app" guaraci python

# Then in Python:
from guaraci.datasus import SinanDataSource

# Initialize
sinan = SinanDataSource()

# Download
sinan.download(2020, 2020, diseases=['RAIV'])

# Load and process
df = sinan.load_dataframe('RAIV')
filtered = sinan.filter(df, uf='SP')
sinan.export(filtered, format='csv', name='raiva_sp')
```

## Configuration

### Environment Variables

```bash
# Custom configuration
docker run --rm -it -v "$(pwd):/app" \
  -e GUARACI_LOG_LEVEL=DEBUG \
  -e GUARACI_MAX_CONCURRENT_DOWNLOADS=10 \
  -e GUARACI_MEMORY_LIMIT_GB=8 \
  guaraci python -m guaraci.cli.sinan_cli download 2020 2020 --diseases DENG
```

### Available Environment Variables

- `GUARACI_DATA_ROOT`: Data output directory (default: `/app/data`)
- `GUARACI_LOG_LEVEL`: Logging level (DEBUG, INFO, WARNING, ERROR)
- `GUARACI_MAX_CONCURRENT_DOWNLOADS`: Concurrent download limit (default: 5)
- `GUARACI_MEMORY_LIMIT_GB`: Memory limit in GB (default: 4.0)
- `GUARACI_CACHE_DIR`: Cache directory (default: `data/.cache`)

## Development Workflow

### Code Changes

```bash
# 1. Make changes to code
# 2. Rebuild image
docker build -t guaraci .

# 3. Test changes
docker run --rm guaraci python -m pytest tests/ -v

# 4. Test functionality
docker run --rm -it -v "$(pwd):/app" guaraci python test_install.py
```

### Testing

```bash
# Run all tests
docker run --rm guaraci python -m pytest tests/ -v

# Run specific tests
docker run --rm guaraci python -m pytest tests/test_utils.py -v

# Run with coverage
docker run --rm guaraci python -m pytest tests/ --cov=guaraci --cov-report=term-missing
```

### Code Quality

```bash
# Format code
docker run --rm -v "$(pwd):/app" guaraci python -m black guaraci/

# Sort imports
docker run --rm -v "$(pwd):/app" guaraci python -m isort guaraci/

# Type checking
docker run --rm -v "$(pwd):/app" guaraci python -m mypy guaraci/

# Linting
docker run --rm -v "$(pwd):/app" guaraci python -m flake8 guaraci/
```

## Troubleshooting

### Common Issues

1. **Volume Mount Problems**

   ```bash
   # Ensure correct path format
   # Windows: Use forward slashes
   docker run --rm -it -v "C:/Users/Name/project:/app" guaraci

   # Linux/Mac: Use $(pwd)
   docker run --rm -it -v "$(pwd):/app" guaraci
   ```

2. **Memory Issues**

   ```bash
   # Increase container memory
   docker run --rm -it --memory=8g -v "$(pwd):/app" guaraci
   ```

3. **Permission Issues**

   ```bash
   # Check directory permissions
   chmod 755 $(pwd)
   ```

4. **Build Issues**
   ```bash
   # Clean rebuild
   docker build --no-cache -t guaraci .
   ```

### Debug Mode

```bash
# Run with debug logging
docker run --rm -it -v "$(pwd):/app" \
  -e GUARACI_LOG_LEVEL=DEBUG \
  guaraci python -m guaraci.cli.sinan_cli download 2020 2020 --diseases RAIV
```

## Future Enhancements

### Docker Compose (Planned)

```bash
# Future: Multi-service setup
docker-compose up

# Future: Web API
docker-compose up api

# Future: Background processing
docker-compose up worker
```

### Kubernetes (Planned)

```bash
# Future: Scalable deployment
kubectl apply -f k8s/

# Future: Distributed processing
kubectl scale deployment guaraci-worker --replicas=5
```

## Best Practices

1. **Always use volume mounts** to persist data
2. **Use environment variables** for configuration
3. **Rebuild images** after code changes
4. **Use specific tags** for production deployments
5. **Monitor resource usage** for large datasets
6. **Clean up containers** regularly with `docker system prune`

This Docker-first approach ensures that Guaraci works consistently across all platforms while eliminating the complexity of local Python environment management.
