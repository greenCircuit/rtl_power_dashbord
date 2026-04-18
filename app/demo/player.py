"""
DemoBandPlayer — drop-in replacement for BandCaptureManager when DEMO_MODE=true.

On startup it seeds a set of demo-specific bands into demo.db and generates
synthetic sweep data for both those bands and any active config.yaml bands.
No seed.db or real SDR hardware required.

Demo bands have explicit signal definitions for predictable chart output.
Config.yaml bands receive signals placed at 25/50/75 % of their frequency range.
"""

import logging
import random
import sqlite3
import threading
import time as _time
from datetime import datetime, timedelta, timezone

from app.config import DB_PATH

log = logging.getLogger(__name__)

_INSERT = """
    INSERT INTO band_measurements (band_id, timestamp, frequency_mhz, power_db)
    VALUES (?, ?, ?, ?)
"""

_NOISE_FLOOR_DB  = -15   # baseline noise across all bands
_MIN_POWER_DB    = -2    # discard threshold: 10 dB above noise floor (noise reliably filtered)
_SIGNAL_DB       = -2    # base signal power: 3 dB above threshold
_JITTER_DB       = 1.5   # random noise added per sample



# ── Demo band definitions ─────────────────────────────────────────────────────

DEMO_BANDS: list[dict] = [
    {
        "id":           "demo-noise",
        "name":         "Demo: Noise Floor",
        "freq_start":   "144M",
        "freq_end":     "146M",
        "freq_step":    "50k",
        "interval_s":   5,
        "min_power":    _MIN_POWER_DB,
        "device_index": 0,
        "is_active":    True,
    },
    {
        "id":           "demo-active",
        "name":         "Demo: Active Channels",
        "freq_start":   "462.5M",
        "freq_end":     "462.8M",
        "freq_step":    "50k",
        "interval_s":   5,
        "min_power":    _MIN_POWER_DB,
        "device_index": 0,
        "is_active":    True,
        "_signals": [
            {"freq_mhz": 462.625, "power_db": _SIGNAL_DB + 3, "period_s": 1, "duty": 1.0},
            {"freq_mhz": 462.750, "power_db": _SIGNAL_DB,     "period_s": 1, "duty": 1.0},
        ],
    },
    {
        "id":           "demo-periodic",
        "name":         "Demo: Periodic Signals",
        "freq_start":   "156M",
        "freq_end":     "158M",
        "freq_step":    "50k",
        "interval_s":   5,
        "min_power":    _MIN_POWER_DB,
        "device_index": 0,
        "is_active":    True,
        "_signals": [
            {"freq_mhz": 156.300, "power_db": _SIGNAL_DB + 3, "period_s": 60,  "duty": 0.50},
            {"freq_mhz": 156.800, "power_db": _SIGNAL_DB,     "period_s": 30,  "duty": 0.40},
            {"freq_mhz": 157.100, "power_db": _SIGNAL_DB + 5, "period_s": 120, "duty": 0.25},
        ],
    },
]


# ── Frequency utilities ───────────────────────────────────────────────────────

def _parse_mhz(s: str) -> float:
    """Parse an rtl_power frequency string to MHz (e.g. "144M", "25k", "1.2G")."""
    s = s.strip()
    if s.endswith("G"):
        return float(s[:-1]) * 1000.0
    if s.endswith("M"):
        return float(s[:-1])
    if s.endswith("k"):
        return float(s[:-1]) / 1000.0
    return float(s) / 1_000_000.0  # assume Hz


def _freq_list(band: dict) -> list[float]:
    """Return the list of MHz values covering the band's frequency range."""
    start = _parse_mhz(band["freq_start"])
    end   = _parse_mhz(band["freq_end"])
    step  = _parse_mhz(band["freq_step"])
    freqs = []
    f = start
    while f <= end + step * 0.01:
        freqs.append(round(f, 6))
        f += step
    return freqs


# ── Mock signal placement ─────────────────────────────────────────────────────

# Signals placed at these fractional positions within the frequency list.
# Each entry: (position fraction, power dBm, period seconds, duty cycle)
_SIGNAL_TEMPLATES = [
    (0.25, _SIGNAL_DB + 3,  60, 0.50),
    (0.50, _SIGNAL_DB,      30, 0.40),
    (0.75, _SIGNAL_DB + 5, 120, 0.30),
]


def _mock_signals(freqs: list[float]) -> list[dict]:
    """Return signal descriptors placed at fixed fractional positions."""
    if len(freqs) < 4:
        return []
    signals = []
    for frac, power_db, period_s, duty in _SIGNAL_TEMPLATES:
        idx = int(frac * (len(freqs) - 1))
        signals.append({
            "freq_mhz": freqs[idx],
            "power_db": power_db,
            "period_s": period_s,
            "duty":     duty,
        })
    return signals


# ── Synthetic sweep generator ─────────────────────────────────────────────────

def _generate_sweep(band: dict, epoch: float) -> list[tuple[float, float]]:
    """Return (freq_mhz, power_db) pairs for one synthetic sweep.

    Uses a seeded RNG so the same epoch always produces the same noise pattern,
    making chart output reproducible across test runs.

    Signal source priority:
      1. band["_signals"] — explicit definitions (demo bands)
      2. _mock_signals()  — positional fallback (config.yaml bands)
    """
    rng   = random.Random(int(epoch * 10))   # 0.1 s resolution seed
    freqs = _freq_list(band)
    power = {f: _NOISE_FLOOR_DB + rng.gauss(0, _JITTER_DB) for f in freqs}

    signals = band.get("_signals") or _mock_signals(freqs)
    for sig in signals:
        period = sig["period_s"]
        duty   = sig["duty"]
        if (epoch % period) / period < duty:
            nearest = min(freqs, key=lambda f: abs(f - sig["freq_mhz"]))
            power[nearest] = sig["power_db"] + rng.gauss(0, _JITTER_DB)

    return [(f, power[f]) for f in freqs]


# ── Replay thread ─────────────────────────────────────────────────────────────

def _replay(band: dict, interval_s: float, stop_event: threading.Event) -> None:
    """Thread target: generate a sweep each tick and write it to the live DB."""
    while not stop_event.is_set():
        epoch = _time.time()
        sweep = _generate_sweep(band, epoch)
        ts    = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        rows  = [(band["id"], ts, freq, pwr) for freq, pwr in sweep
                 if pwr >= band.get("min_power", _MIN_POWER_DB)]
        try:
            with sqlite3.connect(str(DB_PATH), check_same_thread=False) as conn:
                conn.executemany(_INSERT, rows)
            log.debug(
                "Demo: wrote %d rows for band %r at %s",
                len(rows), band["id"], ts,
            )
        except Exception as exc:
            log.warning("Demo write error for band %r: %s", band["id"], exc)

        stop_event.wait(interval_s)


_HISTORY_DAYS     = 5
_HISTORY_INTERVAL = 60   # seconds between historical sweep points
_INSERT_BATCH     = 5_000


def seed_historical_data(bands: list[dict]) -> None:
    """Back-fill 7 days of synthetic sweep data for all demo bands.

    Skips seeding if data older than 1 day already exists for any demo band,
    so restarts don't duplicate rows.
    """
    now       = datetime.now(timezone.utc)
    cutoff_ts = (now - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")

    try:
        with sqlite3.connect(str(DB_PATH), check_same_thread=False) as conn:
            row = conn.execute(
                "SELECT 1 FROM band_measurements WHERE timestamp < ? LIMIT 1",
                (cutoff_ts,),
            ).fetchone()
    except Exception as exc:
        log.warning("Demo: could not check for existing history: %s", exc)
        return

    if row:
        log.info("Demo: historical data already present — skipping seed")
        return

    start_epoch = (now - timedelta(days=_HISTORY_DAYS)).timestamp()
    end_epoch   = now.timestamp()
    total_steps = int((end_epoch - start_epoch) / _HISTORY_INTERVAL)

    log.info(
        "Demo: seeding %d days of history (%d sweeps per band) …",
        _HISTORY_DAYS, total_steps,
    )

    for band in bands:
        bid      = band["id"]
        min_pwr  = band.get("min_power", _MIN_POWER_DB)
        rows: list[tuple] = []

        for i in range(total_steps):
            epoch = start_epoch + i * _HISTORY_INTERVAL
            ts    = datetime.fromtimestamp(epoch, tz=timezone.utc).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            for freq, pwr in _generate_sweep(band, epoch):
                if pwr >= min_pwr:
                    rows.append((bid, ts, freq, pwr))

            if len(rows) >= _INSERT_BATCH:
                try:
                    with sqlite3.connect(str(DB_PATH), check_same_thread=False) as conn:
                        conn.executemany(_INSERT, rows)
                except Exception as exc:
                    log.warning("Demo: history insert error for band %r: %s", bid, exc)
                rows = []

        if rows:
            try:
                with sqlite3.connect(str(DB_PATH), check_same_thread=False) as conn:
                    conn.executemany(_INSERT, rows)
            except Exception as exc:
                log.warning("Demo: history insert error for band %r: %s", bid, exc)

        log.info("Demo: historical data seeded for band %r", bid)

    log.info("Demo: history seed complete")


# ── Demo band seeding (called explicitly from create_app) ────────────────────

def seed_demo_bands() -> None:
    """Insert DEMO_BANDS into the DB if they don't exist yet.

    Called directly from create_app() after init_db() so the timing is
    guaranteed — not as a side-effect of DemoBandPlayer instantiation.
    """
    from app.data import db as live_db
    for band in DEMO_BANDS:
        bid = band["id"]
        try:
            if live_db.get_band(bid) is None:
                live_db.create_band(
                    band_id=bid,
                    name=band["name"],
                    freq_start=band["freq_start"],
                    freq_end=band["freq_end"],
                    freq_step=band["freq_step"],
                    interval_s=band["interval_s"],
                    min_power=band["min_power"],
                    device_index=band["device_index"],
                    is_active=band["is_active"],
                )
                log.info("Demo: seeded band %r (%s)", bid, band["name"])
            else:
                # If a config.yaml band has the same ID as a demo band, the config
                # version is already in the DB. The demo's _signals definitions won't
                # be used — synthetic data will fall back to _mock_signals() placement.
                log.warning(
                    "Demo: band %r already exists (seeded from config.yaml) — "
                    "demo signal definitions will not be used; "
                    "rename the config band to avoid this collision",
                    bid,
                )
        except Exception as exc:
            log.error("Demo: failed to seed band %r: %s", bid, exc)

    # Build full band list (DEMO_BANDS have _signals; config bands fall back to _mock_signals)
    config_bands = [b for b in live_db.list_bands() if b["id"] not in {d["id"] for d in DEMO_BANDS}]
    all_bands = list(DEMO_BANDS) + config_bands
    seed_historical_data(all_bands)


# ── DemoBandPlayer ────────────────────────────────────────────────────────────

class DemoBandPlayer:
    """Same public interface as BandCaptureManager; generates synthetic data.

    Bands come from config.yaml (seeded into the DB by the normal startup path).
    The player just synthesises sweep data for whatever bands are passed to it.
    """

    def __init__(self) -> None:
        self._active:   dict[str, dict]             = {}
        self._threads:  dict[str, threading.Thread] = {}
        self._stops:    dict[str, threading.Event]  = {}
        self._statuses: dict[str, str]              = {}  # terminal status after thread exits
        self._lock      = threading.Lock()
        log.info("Demo mode active — synthetic data for demo + config bands")

    # ── public API (mirrors BandCaptureManager) ───────────────────────────────

    def start_band(self, band_id: str) -> None:
        from app.data import db as live_db
        band = live_db.get_band(band_id)
        if not band:
            raise ValueError(f"Band {band_id!r} not found")
        with self._lock:
            if band_id in self._active:
                raise RuntimeError(f"'{band['name']}' is already playing")
            self._active[band_id] = band
            self._start_thread(band)

    def stop_band(self, band_id: str) -> None:
        with self._lock:
            if band_id not in self._active:
                return
            del self._active[band_id]
            self._statuses[band_id] = "stopped"
            self._stop_thread(band_id)

    def start_active_bands(self, bands: list[dict]) -> None:
        """Start threads for config.yaml bands AND demo-specific bands.

        DEMO_BANDS entries take priority over the DB-returned dicts for demo
        band IDs so that _signals definitions are preserved for sweep generation.
        """
        # Start with config bands from DB, then overlay DEMO_BANDS (keeps _signals)
        all_bands = {b["id"]: b for b in bands}
        for demo_band in DEMO_BANDS:
            all_bands[demo_band["id"]] = demo_band
        with self._lock:
            for band in all_bands.values():
                self._active[band["id"]] = band
                self._start_thread(band)

    def get_status(self, band_id: str) -> str:
        with self._lock:
            if band_id not in self._active:
                # Return a terminal status if we recorded one (e.g. "stopped")
                return self._statuses.get(band_id, "idle")
            t = self._threads.get(band_id)
            return "running" if (t and t.is_alive()) else "idle"

    def get_error(self, band_id: str) -> str | None:
        return None  # demo never errors

    def all_statuses(self) -> dict[str, str]:
        with self._lock:
            result = {}
            for bid in self._active:
                t = self._threads.get(bid)
                result[bid] = "running" if (t and t.is_alive()) else "idle"
            return result

    # ── internal ──────────────────────────────────────────────────────────────

    def _start_thread(self, band: dict) -> None:
        band_id    = band["id"]
        interval_s = band.get("interval_s", 5)
        stop       = threading.Event()
        self._stops[band_id] = stop
        t = threading.Thread(
            target=_replay,
            args=(band, interval_s, stop),
            daemon=True,
            name=f"demo-{band_id}",
        )
        self._threads[band_id] = t
        t.start()
        log.info(
            "Demo: started synthetic thread for band %r (interval=%.1fs)",
            band_id, interval_s,
        )

    def _stop_thread(self, band_id: str) -> None:
        stop = self._stops.pop(band_id, None)
        if stop:
            stop.set()
        self._threads.pop(band_id, None)
        log.info("Demo: stopped thread for band %r", band_id)
