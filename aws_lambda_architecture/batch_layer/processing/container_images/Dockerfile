# DuckDB + S3 + RDS Resampler - AWS Batch Container
FROM python:3.11-slim

# Build arguments
ARG BUILD_DATE
ARG VCS_REF

# Labels for metadata
LABEL org.label-schema.build-date=$BUILD_DATE \
    org.label-schema.name="duckdb-s3-rds-resampler" \
    org.label-schema.description="Batch job for resampling OHLCV data using DuckDB + S3 + RDS" \
    org.label-schema.vcs-ref=$VCS_REF \
    org.label-schema.vcs-url="https://github.com/your-org/condvest" \
    org.label-schema.schema-version="1.0"

# Set working directory
WORKDIR /app

# Install system dependencies for DuckDB and PostgreSQL
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY processing/batch_jobs/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared modules (copied by build script to processing/shared/)
COPY processing/shared/ ./shared/

# Copy batch job files
COPY processing/batch_jobs/ ./

# Set Python path
ENV PYTHONPATH=/app

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash app && chown -R app:app /app
USER app

# Default command (can be overridden)
CMD ["python", "resampler.py"]