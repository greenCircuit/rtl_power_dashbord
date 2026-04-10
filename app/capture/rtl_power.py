import logging
import sqlite3
import subprocess
import threading
from typing import Optional

import numpy as np

from app.config import DATA_DIR, DB_PATH
from app.data.db import insert_band_measurements

log = logging.getLogger(__name__)


def _freq_to_hz(freq_str: str) -> float:
    """Convert rtl_power frequency string (e.g. '144M', '12.5k', '1.2G') to Hz."""
    s = freq_str.strip()
    for suffix, mult in (("G", 1e9), ("M", 1e6), ("k", 1e3)):
        if s.endswith(suffix):
            return float(s[:-1]) * mult
    return float(s)


def _parse_csv_line(line: str) -> Optional[tuple]:
    """Parse one rtl_power CSV line.

    Returns (date_str, time_str, hz_low, hz_high, db_values) or None on failure.
    """
    parts = [p.strip() for p in line.split(",")]
    if len(parts) < 7:
        return None
    try:
        date_str  = parts[0]
        time_str  = parts[1]
        hz_low    = float(parts[2])
        hz_high   = float(parts[3])
        db_values = [float(v) for v in parts[6:] if v]
    except (ValueError, IndexError):
        return None
    if not db_values:
        return None
    return date_str, time_str, hz_low, hz_high, db_values


def _build_measurement_rows(date_str: str, time_str: str,
                            hz_low: float, hz_high: float,
                            db_values: list) -> list:
    """Convert parsed line data into (timestamp, freq_mhz, power_db) tuples."""
    timestamp = f"{date_str} {time_str}"
    freqs_mhz = np.linspace(hz_low, hz_high, len(db_values)) / 1e6
    return [(timestamp, float(f), float(d)) for f, d in zip(freqs_mhz, db_values)]


class RTLPowerCapture:
    """Manages one rtl_power process scanning multiple bands on one device."""

    def __init__(self):
        self._process = None
        self._thread = None
        self._status = "idle"
        self._error = None
        self._stopped = False

    @property
    def status(self) -> str:
        return self._status

    @property
    def error(self) -> str | None:
        return self._error

    def start(self, bands: list[dict], device_index: int = 0) -> None:
        """Start scanning all given bands on device_index in a single rtl_power process."""
        if self._process and self._process.poll() is None:
            raise RuntimeError("Capture already running")

        DATA_DIR.mkdir(parents=True, exist_ok=True)

        interval = min(b["interval_s"] for b in bands)
        cmd = ["rtl_power", "-d", str(device_index)]
        for b in bands:
            cmd += ["-f", f"{b['freq_start']}:{b['freq_end']}:{b['freq_step']}"]
        cmd += ["-i", str(interval), "/dev/stdout"]

        self._error = None
        self._stopped = False
        log.debug("rtl_power cmd: %s", " ".join(cmd))
        try:
            self._process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
        except FileNotFoundError:
            self._status = "error"
            self._error = "rtl_power not found — install: sudo apt install rtl-sdr"
            log.error(self._error)
            raise RuntimeError(self._error)

        log.info("rtl_power process started (pid %d) — %d band(s) on device %d",
                 self._process.pid, len(bands), device_index)
        self._status = "running"
        self._thread = threading.Thread(
            target=self._monitor,
            args=(bands,),
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stopped = True
        if self._process and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()

    def _monitor(self, bands: list[dict]) -> None:
        # Build routing table: (hz_low, hz_high, band_id, min_power)
        routes = [
            (_freq_to_hz(b["freq_start"]), _freq_to_hz(b["freq_end"]),
             b["id"], b["min_power"])
            for b in bands
        ]

        conn = sqlite3.connect(str(DB_PATH))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        lines_parsed = 0
        rows_stored = 0
        try:
            for raw_line in self._process.stdout:
                line = raw_line.decode(errors="replace").strip()
                if not line:
                    continue
                parsed = _parse_csv_line(line)
                if parsed is None:
                    log.warning("unparseable line: %s", line[:80])
                    continue
                date_str, time_str, hz_low, hz_high, db_values = parsed
                lines_parsed += 1

                # Route line to band by checking which band's range the midpoint falls in
                mid_hz = (hz_low + hz_high) / 2
                band_id = min_power = None
                for r_low, r_high, r_id, r_min in routes:
                    if r_low <= mid_hz <= r_high:
                        band_id, min_power = r_id, r_min
                        break

                if band_id is None:
                    log.debug("No band match for %.3f–%.3f MHz", hz_low / 1e6, hz_high / 1e6)
                    continue

                peak = max(db_values)
                if peak < min_power:
                    log.debug("[%s] below threshold (%.1f dB), skipping", band_id, peak)
                    continue

                rows = _build_measurement_rows(date_str, time_str, hz_low, hz_high, db_values)
                insert_band_measurements(conn, band_id, rows)
                conn.commit()
                rows_stored += len(rows)
                log.debug("[%s] stored %d points @ %s %s (%.3f–%.3f MHz, peak %.1f dB)",
                          band_id, len(rows), date_str, time_str,
                          hz_low / 1e6, hz_high / 1e6, peak)
        finally:
            conn.close()
            self._process.wait()
            self._finalize(lines_parsed, rows_stored)

    def _finalize(self, lines_parsed: int, rows_stored: int) -> None:
        if self._stopped:
            self._status = "stopped"
            log.info("Capture stopped. parsed=%d stored=%d rows", lines_parsed, rows_stored)
        elif self._process.returncode == 0:
            self._status = "completed"
            log.info("Capture completed. parsed=%d stored=%d rows", lines_parsed, rows_stored)
        else:
            stderr = self._process.stderr.read().decode(errors="replace").strip()
            self._status = "error"
            self._error = stderr
            log.error("rtl_power exited with error (rc=%d): %s",
                      self._process.returncode, stderr)
