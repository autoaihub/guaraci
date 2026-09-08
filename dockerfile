# ============================
# Dockerfile for Guaraci Platform
# ============================

FROM python:3.13-slim

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
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy project files
COPY pyproject.toml README.md ./
COPY guaraci/ ./guaraci/
COPY tests/ ./tests/

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Install guaraci with the extras the default paths actually use: direct FTP
# for DATASUS, the web API, and the test tooling that README.md invokes from
# inside the container. The legacy extras (pysus, BigQuery) stay out on
# purpose: they add ~30 transitive packages that no default path imports, and
# pysus caps loguru below 0.7.
RUN pip install --no-cache-dir -e ".[datasus,api,dev]"

# Smoke test basic import/cli
RUN python -m pytest tests/test_install.py

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
LABEL maintainer="vogel@usp.br"
# tests/test_versioning.py mantém este rótulo casado com guaraci.__version__.
LABEL version="0.7.0"
LABEL description="Guaraci - Brazilian Public Data Integration Platform"
