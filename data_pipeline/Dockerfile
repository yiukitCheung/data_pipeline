# Use a lightweight Python base image
FROM python:3.10-slim

# Set environment variables to avoid Python buffering issues
ENV PYTHONUNBUFFERED=1 \
    TZ=America/New_York

# Set working directory in the container
WORKDIR /app

# Install OS dependencies (adjust as needed)
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    libpq-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy local project files to container
COPY . /app

# Install Python dependencies
RUN pip install --upgrade pip && pip install -r requirements.txt

# Set the entrypoint
CMD ["python", "daily_flows/daily_pipeline.py"]