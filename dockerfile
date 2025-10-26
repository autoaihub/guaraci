# ============================
# Dockerfile for Guaraci Platform
# ============================

FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    wget \
    git \
    curl \
    libssl-dev \
    libffi-dev \
    libxml2-dev \
    libxslt1-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy project files
COPY pyproject.toml README.md requirements.txt ./
COPY guaraci/ ./guaraci/
COPY tests/ ./tests/
COPY test_install.py ./

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Install core dependencies first (without PySUS to avoid compilation issues)
RUN pip install -e .

# Test core installation
RUN python test_install.py

# Try to install PySUS separately (may fail on some systems)
RUN pip install --no-cache-dir "pysus>=0.11.0" || echo "PySUS installation failed - SINAN functionality will be limited"

# Install development dependencies
RUN pip install --no-cache-dir \
    "pytest>=7.4.0" \
    "pytest-asyncio>=0.21.0" \
    "pytest-cov>=4.1.0" \
    "black>=23.9.0" \
    "isort>=5.12.0" \
    "flake8>=6.1.0" \
    "mypy>=1.6.0" \
    "pre-commit>=3.5.0" || echo "Some dev dependencies failed to install"

# Create data directory
RUN mkdir -p /app/data

# Set environment variables
ENV GUARACI_DATA_ROOT=/app/data
ENV GUARACI_LOG_LEVEL=INFO
ENV PYTHONPATH=/app

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import guaraci; print('Guaraci is healthy')" || exit 1

# Default command
CMD ["python", "-c", "import guaraci; print(f'Guaraci v{guaraci.__version__} ready!')"]

# Labels for metadata
LABEL maintainer="pedro.guilherme2305@usp.br"
LABEL version="0.2.0"
LABEL description="Guaraci - Brazilian Public Data Integration Platform"
