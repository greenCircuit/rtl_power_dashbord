FROM python:3.12-slim

# Install rtl-sdr and udev rules so the container can access the USB dongle
RUN apt-get update && apt-get install -y --no-install-recommends \
        rtl-sdr \
        udev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV DATA_DIR=/app/data

# Install Python dependencies first (layer-cached)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Persistent data volume mount point
VOLUME ["/app/data"]

EXPOSE 8050

CMD ["python", "run.py"]
