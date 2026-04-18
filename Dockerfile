FROM docker.io/node:22-slim AS ui-builder

WORKDIR /ui

COPY ui/ ./
RUN npm i
RUN npm run build

FROM docker.io/python:3.13-slim

# rtl-sdr provides rtl_power and the kernel USB driver bindings
RUN apt-get update && apt-get install -y --no-install-recommends \
        rtl-sdr \
        udev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies (layer-cached before source copy)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY app/     ./app/
COPY run.py   .
COPY config.yaml .

# Copy built frontend from stage 1
COPY --from=ui-builder /ui/dist ./ui/dist

# Runtime defaults — override in docker-compose or with -e flags
ENV DATA_DIR=/app/data \
    BANDS_CONFIG=/app/config.yaml \
    LOG_PATH=/app/data/app.log \
    PORT=8050 \
    FLASK_DEBUG=false

EXPOSE 8050

# Single worker (RTL-SDR device can only be owned by one process at a time);
# multiple threads handle concurrent HTTP requests and background captures.
CMD ["gunicorn", \
     "--bind", "0.0.0.0:8050", \
     "--workers", "1", \
     "--threads", "4", \
     "--timeout", "120", \
     "run:app"]
