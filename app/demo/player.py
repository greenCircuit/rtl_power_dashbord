"""
DemoBandPlayer — drop-in replacement for BandCaptureManager when DEMO_MODE=true.

Replays sweeps from demo/seed.db in a continuous loop, writing rows with
current timestamps so all the normal API endpoints keep working unchanged.
"""

import logging
import sqlite3
import threading
from datetime import datetime, timezone

from app.config import DB_PATH, DEMO_SEED_DB
from app.data import db as live_db

log = logging.getLogger(__name__)

_INSERT = """
    INSERT INTO band_measurements (band_id, timestamp, frequency_mhz, power_db)
    VALUES (?, ?, ?, ?)
"""


def _load_sweeps(band_id: str) -> list[list[tuple[float, float]]]:
    """Return list of sweeps; each sweep is a list of (freq_mhz, power_db) tuples."""
    if not DEMO_SEED_DB.exists():
        log.warning("Demo seed DB not found at %s — band %s will have no data", DEMO_SEED_DB, band_id)
        return []
    with sqlite3.connect(str(DEMO_SEED_DB)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT timestamp, frequency_mhz, power_db FROM band_measurements "
            "WHERE band_id = ? ORDER BY timestamp, frequency_mhz",
            (band_id,),
        ).fetchall()
    if not rows:
        log.warning("No seed data for band %r in %s", band_id, DEMO_SEED_DB)
        return []

    sweeps: list[list[tuple[float, float]]] = []
    current_ts = None
    current_sweep: list[tuple[float, float]] = []
    for row in rows:
        if row["timestamp"] != current_ts:
            if current_sweep:
                sweeps.append(current_sweep)
            current_sweep = []
            current_ts = row["timestamp"]
        current_sweep.append((row["frequency_mhz"], row["power_db"]))
    if current_sweep:
        sweeps.append(current_sweep)

    log.info("Demo: loaded %d sweeps for band %r from seed DB", len(sweeps), band_id)
    return sweeps


def _replay(band_id: str, interval_s: float, stop_event: threading.Event) -> None:
    """Thread target: write sweeps to the live DB in a loop."""
    sweeps = _load_sweeps(band_id)
    if not sweeps:
        return

    idx = 0
    while not stop_event.is_set():
        sweep = sweeps[idx % len(sweeps)]
        idx += 1
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        rows = [(band_id, ts, freq, power) for freq, power in sweep]
        try:
            with sqlite3.connect(str(DB_PATH), check_same_thread=False) as conn:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.executemany(_INSERT, rows)
            log.debug("Demo: wrote %d rows for band %r at %s", len(rows), band_id, ts)
        except Exception as exc:
            log.warning("Demo write error for band %r: %s", band_id, exc)

        stop_event.wait(interval_s)


class DemoBandPlayer:
    """Same public interface as BandCaptureManager; plays back seed data."""

    def __init__(self) -> None:
        self._active: dict[str, dict] = {}   # band_id -> band dict
        self._threads: dict[str, threading.Thread] = {}
        self._stops: dict[str, threading.Event] = {}
        self._lock = threading.Lock()
        log.info("Demo mode active — replaying from %s", DEMO_SEED_DB)

    # ── public API (mirrors BandCaptureManager) ───────────────────────────────

    def start_band(self, band_id: str) -> None:
        band = live_db.get_band(band_id)
        if not band:
            raise ValueError(f"Band {band_id!r} not found")
        with self._lock:
            if band_id in self._active:
                raise RuntimeError(f"'{band['name']}' is already playing")
            self._active[band_id] = band
            self._start_thread(band_id, band["interval_s"])

    def stop_band(self, band_id: str) -> None:
        with self._lock:
            if band_id not in self._active:
                return
            del self._active[band_id]
            self._stop_thread(band_id)

    def start_active_bands(self, bands: list[dict]) -> None:
        with self._lock:
            for band in bands:
                bid = band["id"]
                self._active[bid] = band
                self._start_thread(bid, band["interval_s"])

    def get_status(self, band_id: str) -> str:
        with self._lock:
            if band_id not in self._active:
                return "idle"
            t = self._threads.get(band_id)
            return "running" if (t and t.is_alive()) else "idle"

    def get_error(self, band_id: str) -> str | None:
        return None  # demo never errors

    def all_statuses(self) -> dict[str, str]:
        with self._lock:
            return {bid: self.get_status(bid) for bid in self._active}

    # ── internal ──────────────────────────────────────────────────────────────

    def _start_thread(self, band_id: str, interval_s: float) -> None:
        stop = threading.Event()
        self._stops[band_id] = stop
        t = threading.Thread(
            target=_replay,
            args=(band_id, interval_s, stop),
            daemon=True,
            name=f"demo-{band_id}",
        )
        self._threads[band_id] = t
        t.start()
        log.info("Demo: started replay thread for band %r (interval=%.1fs)", band_id, interval_s)

    def _stop_thread(self, band_id: str) -> None:
        stop = self._stops.pop(band_id, None)
        if stop:
            stop.set()
        self._threads.pop(band_id, None)
        log.info("Demo: stopped replay thread for band %r", band_id)
