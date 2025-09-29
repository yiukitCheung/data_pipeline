# Fibonacci Resampler - AWS Batch Container
FROM python:3.11-slim

# Build arguments
ARG BUILD_DATE
ARG VCS_REF

# Labels for metadata
LABEL org.label-schema.build-date=$BUILD_DATE \
      org.label-schema.name="fibonacci-resampler" \
      org.label-schema.description="Batch job for resampling OHLCV data using Fibonacci intervals" \
      org.label-schema.vcs-ref=$VCS_REF \
      org.label-schema.vcs-url="https://github.com/your-org/condvest" \
      org.label-schema.schema-version="1.0"

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY processing/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared modules
COPY shared/ ./shared/

# Copy batch job files
COPY processing/batch_jobs/ ./

# Set Python path
ENV PYTHONPATH=/app

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash app && chown -R app:app /app
USER app

# Default command (can be overridden)
CMD ["python", "resampler.py"]