"""
Shared fixtures for performance benchmarks.

The `large_db` fixture seeds ~800k rows (7 days × 81 freq points × 60s sweeps)
into a temp SQLite file once per module, then tears it down after all tests
in the module complete.
"""

import random
import sqlite3
import time
from datetime import datetime, timedelta, timezone

import pytest

import app.data.db._engine as _eng
from app.data.db import create_band, init_db
from app.data.db.rollup import compute_rollup

PERF_BAND_ID   = "perf-wide"
FREQ_START_MHZ = 144.0
FREQ_END_MHZ   = 146.0
FREQ_STEP_MHZ  = 0.025   # 25 kHz → 81 bins
HISTORY_DAYS   = 7
SWEEP_INTERVAL = 60       # seconds

_INSERT = """
    INSERT INTO band_measurements (band_id, timestamp, frequency_mhz, power_db)
    VALUES (?, ?, ?, ?)
"""
_BATCH = 10_000


def _freq_bins() -> list[float]:
    bins, f = [], FREQ_START_MHZ
    while f <= FREQ_END_MHZ + FREQ_STEP_MHZ * 0.01:
        bins.append(round(f, 6))
        f += FREQ_STEP_MHZ
    return bins


@pytest.fixture(scope="module")
def large_db(tmp_path_factory):
    """Seed a large temp DB; patch the engine module for the duration of the module."""
    db_path = tmp_path_factory.mktemp("perf") / "perf.db"

    # Save and redirect engine module state
    saved = (_eng.DB_PATH, _eng._engine, _eng._session_factory)
    _eng.DB_PATH          = db_path
    _eng._engine          = None
    _eng._session_factory = None

    init_db()
    create_band(
        band_id=PERF_BAND_ID,
        name="Perf Wide Band",
        freq_start="144M",
        freq_end="146M",
        freq_step="25k",
        interval_s=SWEEP_INTERVAL,
        min_power=-100.0,   # keep every row so queries see full volume
        device_index=0,
        is_active=True,
    )

    freqs     = _freq_bins()
    sig_freqs = {freqs[len(freqs) // 4], freqs[len(freqs) // 2], freqs[3 * len(freqs) // 4]}
    now       = datetime.now(timezone.utc)
    start_ts  = now - timedelta(days=HISTORY_DAYS)
    n_sweeps  = int(HISTORY_DAYS * 86400 / SWEEP_INTERVAL)
    rng       = random.Random(42)

    t0   = time.perf_counter()
    rows: list[tuple] = []

    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("PRAGMA synchronous=OFF")   # safe for bulk seed, not normal ops
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA cache_size=-32768")

        for i in range(n_sweeps):
            epoch = start_ts.timestamp() + i * SWEEP_INTERVAL
            ts    = datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            for f in freqs:
                pwr = (-2.0 if f in sig_freqs else -15.0) + rng.gauss(0, 1.5)
                rows.append((PERF_BAND_ID, ts, f, pwr))

            if len(rows) >= _BATCH:
                conn.executemany(_INSERT, rows)
                rows.clear()

        if rows:
            conn.executemany(_INSERT, rows)
        conn.commit()

    total   = n_sweeps * len(freqs)
    elapsed = time.perf_counter() - t0
    print(f"\n  [perf fixture] {total:,} raw rows seeded in {elapsed:.1f}s")

    # Pre-compute rollup tiers so rollup-routing benchmarks have data to read.
    t1 = time.perf_counter()
    for bucket_minutes in (15, 60):
        n = compute_rollup(PERF_BAND_ID, bucket_minutes)
        print(f"  [perf fixture] rollup {bucket_minutes}m: {n:,} rows in {time.perf_counter()-t1:.1f}s")

    yield db_path

    # Restore engine module to its pre-fixture state
    _eng.DB_PATH, _eng._engine, _eng._session_factory = saved
