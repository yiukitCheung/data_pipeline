# Dockerfile for Batch Layer Data Pipeline
# Optimized for AWS Batch + Fargate Spot

FROM python:3.10-slim

# Metadata
LABEL maintainer="condvest-data-team"
LABEL version="1.0.0"
LABEL description="Batch Layer Data Pipeline: Resample ohlcv data into fibonacci intervals"

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN groupadd -r batchprocessor && useradd -r -g batchprocessor batchprocessor

# Set working directory
WORKDIR /app

# Copy requirements first (for better caching)
COPY data_processor/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared utilities (from parent directory)
COPY shared/ ./shared/

# Copy application code
COPY data_processor/resampler.py .
COPY data_processor/config/ ./config/

# Set Python path for shared modules
ENV PYTHONPATH=/app:/opt/python
ENV PYTHONUNBUFFERED=1

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import sys; sys.exit(0)" || exit 1

# Switch to non-root user
USER batchprocessor

# Entry point
CMD ["python", "resampler.py"]
