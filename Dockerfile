# Multi-Arch Dockerfile for NetPulse Pro (Raspberry Pi 4 ARM64 / AMD64)
FROM python:3.10-slim-bullseye

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    NETPULSE_DOCKER=1 \
    NETPULSE_DATA_DIR=/app/data

WORKDIR /app

# Install native network utilities required for probing on Linux/Raspberry Pi
RUN apt-get update && apt-get install -y --no-install-recommends \
    iputils-ping \
    iproute2 \
    dnsutils \
    procps \
    wireless-tools \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create persistent data directory
RUN mkdir -p /app/data

# Copy application source code
COPY backend/ ./backend/
COPY frontend/ ./frontend/
COPY run.py .

# Expose Web Dashboard Port
EXPOSE 8765

# Healthcheck probe
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://127.0.0.1:8765/api/status || exit 1

# Launch NetPulse Server
CMD ["python", "run.py"]
