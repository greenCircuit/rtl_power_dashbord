FROM python:3.13-slim

# rtl-sdr provides rtl_power and the kernel USB driver bindings
RUN apt-get update && apt-get install -y --no-install-recommends \
        rtl-sdr \
        udev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (layer-cached before source copy)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source (see .dockerignore for exclusions)
COPY . .

# Runtime defaults — override in docker-compose or with -e flags
ENV DATA_DIR=/app/data \
    BANDS_CONFIG=/app/bands.yaml \
    LOG_PATH=/app/data/app.log \
    PORT=8050 \
    FLASK_DEBUG=false

# /app/data holds the SQLite DB, CSV captures, and log file
VOLUME ["/app/data"]

EXPOSE 8050

# Single worker (RTL-SDR device can only be owned by one process at a time);
# multiple threads handle concurrent HTTP requests and background captures.
CMD ["gunicorn", \
     "--bind", "0.0.0.0:8050", \
     "--workers", "1", \
     "--threads", "4", \
     "--timeout", "120", \
     "run:app"]
