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
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy project files
COPY pyproject.toml README.md requirements.txt ./
COPY guaraci/ ./guaraci/
COPY tests/ ./tests/

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Install guaraci with full extras (datasus + api + dev tools)
RUN pip install --no-cache-dir -e ".[full]"

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
LABEL version="0.5.1"
LABEL description="Guaraci - Brazilian Public Data Integration Platform"
