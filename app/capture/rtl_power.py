import logging
import subprocess
import threading
from typing import Optional

import numpy as np

from app.config import DATA_DIR
from app.data.db import get_engine, insert_band_measurements

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
    return [(timestamp, f.item(), d) for f, d in zip(freqs_mhz, db_values)]


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
        # Sort bands low-to-high so rtl_power scans in ascending frequency order
        sorted_bands = sorted(bands, key=lambda b: _freq_to_hz(b["freq_start"]))
        cmd = ["rtl_power", "-d", str(device_index)]
        for b in sorted_bands:
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

        conn = get_engine().connect()

        lines_parsed = 0
        rows_stored  = 0
        unmatched    = 0

        # Buffer rows by timestamp so we commit once per complete sweep instead
        # of once per CSV line.  A VHF scan at 12.5 kHz steps produces ~1680
        # lines per sweep; batching cuts commit rate from ~1680/sweep to 1/sweep.
        pending:    dict[str, list] = {}  # band_id -> row list
        per_band:   dict[str, int]  = {}  # band_id -> lines routed (for diagnostics)
        current_ts: str | None      = None
        sweeps      = 0

        def _flush():
            nonlocal rows_stored, sweeps
            sweeps += 1
            for bid, rows in pending.items():
                insert_band_measurements(conn, bid, rows)
                rows_stored += len(rows)
            conn.commit()
            pending.clear()
            if sweeps % 10 == 0:
                log.info("sweep #%d — routed: %s — unmatched: %d",
                         sweeps, dict(per_band), unmatched)

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
                ts = f"{date_str} {time_str}"

                # New timestamp → previous sweep is complete, flush to DB
                if current_ts is not None and ts != current_ts:
                    _flush()
                current_ts = ts

                # Route by overlap: assign to the band whose range overlaps this
                # CSV chunk.  Overlap is more robust than midpoint containment —
                # rtl_power may extend hz_high beyond the requested range when
                # the narrow band is smaller than one FFT window.
                band_id = min_power = None
                for r_low, r_high, r_id, r_min in routes:
                    if hz_low <= r_high and hz_high >= r_low:
                        band_id, min_power = r_id, r_min
                        break

                if band_id is None:
                    unmatched += 1
                    continue

                per_band[band_id] = per_band.get(band_id, 0) + 1
                if max(db_values) < min_power:
                    continue

                rows = _build_measurement_rows(date_str, time_str, hz_low, hz_high, db_values)
                # Drop individual readings below min_power — the sweep-level check
                # above only gates whole lines; without this, quiet frequencies
                # within an active sweep still get stored with negative values.
                rows = [(ts, freq, pwr) for ts, freq, pwr in rows if pwr >= min_power]
                pending.setdefault(band_id, []).extend(rows)
        finally:
            if pending:
                try:
                    _flush()
                except Exception as exc:
                    log.warning("Final flush failed, %d row(s) may be lost: %s",
                                sum(len(r) for r in pending.values()), exc)
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
