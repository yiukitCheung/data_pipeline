# DuckDB + S3 + RDS Batch Jobs - AWS Batch Container
# Supports: Resampler, Consolidator
FROM python:3.11-slim

# Build arguments
ARG BUILD_DATE
ARG VCS_REF
ARG JOB_TYPE=resampler

# Labels for metadata
LABEL org.label-schema.build-date=$BUILD_DATE \
    org.label-schema.name="duckdb-s3-batch-processor" \
    org.label-schema.description="Batch jobs for OHLCV data processing (resampler + consolidator)" \
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

# Environment variable to select job type (resampler or consolidator)
ENV JOB_TYPE=${JOB_TYPE}

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash app && chown -R app:app /app
USER app

# Entry point script that runs the appropriate job based on JOB_TYPE
# Default: resampler (can be overridden by passing JOB_TYPE=consolidator)
CMD ["sh", "-c", "if [ \"$JOB_TYPE\" = \"consolidator\" ]; then python consolidator.py; else python resampler.py; fi"]