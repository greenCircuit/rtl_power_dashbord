"""
Performance benchmarks for DB query functions.

See PERFORMANCE.md for expected timings, bottleneck analysis, and the full
workflow for saving baselines and detecting regressions.

Quick reference:
    pytest tests/perf/ --benchmark-save=baseline
    pytest tests/perf/ --benchmark-compare=baseline --benchmark-compare-fail=mean:20%
"""

from datetime import datetime, timedelta, timezone

import pytest

import app.data.db._engine as _eng
from app.data.db import (
    fetch_band_activity,
    fetch_band_alltime_peak,
    fetch_band_measurements,
    fetch_band_power_histogram,
    fetch_band_signal_raw,
    fetch_band_stats,
    fetch_band_timeseries,
    fetch_band_top_channels,
    fetch_rollup_measurements,
    fetch_rollup_timeseries,
    fetch_rollup_stats,
    fetch_rollup_activity,
    fetch_rollup_histogram,
    fetch_rollup_signal_raw,
)
from app.data.db.measurements import _MAX_TIME_BUCKETS
from tests.perf.conftest import FREQ_START_MHZ, PERF_BAND_ID

# Filters that put time_min 3 days in the past — forces rollup routing because
# raw_hours default is 2 h; the large_db fixture pre-computes 15m and 60m tiers.
_OLD_FILTERS = {
    "time_min": (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S"),
}

# Performance budgets (seconds).  Set at ~2× the expected mean after
# downsampling was applied, so CI variance doesn't cause false failures.
# Tighten as queries improve further.
_BUDGET = {
    "fast":   4.0,   # timeseries — now includes a meta scan before the indexed read
    "medium": 4.0,   # full-band GROUP BY aggregations (unchanged)
    "slow":   4.0,   # histogram / signal_raw — now downsampled, expected ~2× faster
}


@pytest.fixture(autouse=True)
def _use_large_db(large_db, monkeypatch):
    """Re-point the SQLAlchemy engine at the large_db for each test."""
    monkeypatch.setattr(_eng, "DB_PATH",         large_db)
    monkeypatch.setattr(_eng, "_engine",          None)
    monkeypatch.setattr(_eng, "_session_factory", None)


# ── heatmap ───────────────────────────────────────────────────────────────────

def test_fetch_measurements(benchmark):
    """Heatmap (avg) — buckets 10,080 raw sweeps down to ~300 time slots in SQL.

    Expected: ~1.9 s  |  Budget: < 4 s
    Full table scan before GROUP BY is the bottleneck; a covering index on
    (band_id, timestamp, frequency_mhz, power_db) would eliminate it.
    """
    result = benchmark(fetch_band_measurements, PERF_BAND_ID)
    # Bucketing must reduce 10,080 raw sweeps to roughly 300 time slots.
    # Allow a few extra from ceil() rounding.
    assert len({r[0] for r in result}) <= 310
    assert benchmark.stats["mean"] < _BUDGET["medium"]


def test_fetch_measurements_max_hold(benchmark):
    """Heatmap (max-hold) — same bucketing logic, MAX aggregator instead of AVG.

    Expected: ~1.9 s  |  Budget: < 4 s
    """
    result = benchmark(fetch_band_measurements, PERF_BAND_ID, None, "max")
    assert len({r[0] for r in result}) <= 310
    assert benchmark.stats["mean"] < _BUDGET["medium"]


# ── per-frequency aggregates ──────────────────────────────────────────────────

def test_fetch_stats(benchmark):
    """Mean + peak per frequency bin — GROUP BY frequency_mhz, ~81 rows returned.

    Expected: ~1.7 s  |  Budget: < 4 s
    Scans all rows for the band; no time filter applied.
    """
    result = benchmark(fetch_band_stats, PERF_BAND_ID)
    assert len(result) > 0
    assert benchmark.stats["mean"] < _BUDGET["medium"]


def test_fetch_activity(benchmark):
    """Active-vs-total counts per frequency bin — conditional SUM over full band.

    Expected: ~1.8 s  |  Budget: < 4 s
    """
    result = benchmark(fetch_band_activity, PERF_BAND_ID, threshold_db=-3.0)
    assert len(result) > 0
    assert benchmark.stats["mean"] < _BUDGET["medium"]


def test_fetch_alltime_peak(benchmark):
    """Max power per frequency — intentionally scans all time (no time filter).

    Expected: ~1.7 s  |  Budget: < 4 s
    """
    result = benchmark(fetch_band_alltime_peak, PERF_BAND_ID)
    assert len(result) > 0
    assert benchmark.stats["mean"] < _BUDGET["medium"]


def test_fetch_top_channels(benchmark):
    """N most active frequencies sorted by activity % — GROUP BY + ORDER BY + LIMIT.

    Expected: ~1.9 s  |  Budget: < 4 s
    """
    result = benchmark(fetch_band_top_channels, PERF_BAND_ID, threshold_db=-3.0)
    assert len(result) > 0
    assert benchmark.stats["mean"] < _BUDGET["medium"]


# ── time-series (single frequency) ───────────────────────────────────────────

def test_fetch_timeseries(benchmark):
    """Power over time for one frequency — downsampled to ≤300 time buckets.

    Expected: ~2 s (meta scan + bucketed read)  |  Budget: < 4 s
    The extra meta scan is the price for downsampling; raw path was ~150 ms
    but would return 10,080 raw rows on a 7-day dataset.
    """
    result = benchmark(fetch_band_timeseries, PERF_BAND_ID, FREQ_START_MHZ)
    assert 0 < len(result) <= _MAX_TIME_BUCKETS + 10
    assert benchmark.stats["mean"] < _BUDGET["fast"]


# ── raw dumps (known bottlenecks — tracked to detect future regressions) ──────

def test_fetch_power_histogram(benchmark):
    """Power values for histogram — downsampled via time-bucketing.

    Expected: ~2 s (was ~2.7 s raw)  |  Budget: < 4 s
    Returns AVG(power_db) per time-bucket×freq instead of every raw value,
    reducing output from ~816k floats to ~24k while preserving distribution shape.
    """
    result = benchmark(fetch_band_power_histogram, PERF_BAND_ID)
    assert 0 < len(result) <= (_MAX_TIME_BUCKETS + 10) * 81
    assert benchmark.stats["mean"] < _BUDGET["slow"]


def test_fetch_signal_raw(benchmark):
    """Signal rows above threshold — downsampled to peak per time-bucket×freq.

    Expected: ~2 s (was ~4.5 s raw)  |  Budget: < 4 s
    Uses MAX(power_db) per bucket with a HAVING clause so only buckets where
    the peak crossed the threshold are returned.
    """
    result = benchmark(fetch_band_signal_raw, PERF_BAND_ID, threshold_db=-3.0)
    assert len(result) > 0
    assert benchmark.stats["mean"] < _BUDGET["slow"]


# ── rollup routing (time_min 3 days old → reads pre-aggregated tiers) ─────────
# These benchmarks verify that queries routed to the rollup table are
# substantially faster than the equivalent raw-table scans above, because they
# read ~288 15-min buckets × 81 freq bins ≈ 23k rows instead of 864k raw rows.
# Budgets are intentionally tighter (2 s) to catch regressions in the fast path.

_ROLLUP_BUDGET = 2.0


def test_rollup_measurements(benchmark):
    """Heatmap routed to 15 m rollup — expected ~0.05 s vs ~1.9 s raw.

    Expected: < 0.1 s  |  Budget: < 2 s
    """
    result = benchmark(fetch_rollup_measurements, PERF_BAND_ID, 15, _OLD_FILTERS)
    assert len(result) > 0
    assert benchmark.stats["mean"] < _ROLLUP_BUDGET


def test_rollup_timeseries(benchmark):
    """Single-frequency timeseries from 15 m rollup — downsampled to ≤300 pts.

    Expected: < 0.1 s  |  Budget: < 2 s
    """
    result = benchmark(fetch_rollup_timeseries, PERF_BAND_ID, 15, FREQ_START_MHZ, _OLD_FILTERS)
    assert 0 < len(result) <= _MAX_TIME_BUCKETS + 10
    assert benchmark.stats["mean"] < _ROLLUP_BUDGET


def test_rollup_stats(benchmark):
    """Per-frequency stats from 15 m rollup.

    Expected: < 0.05 s  |  Budget: < 2 s
    """
    result = benchmark(fetch_rollup_stats, PERF_BAND_ID, 15, _OLD_FILTERS)
    assert len(result) > 0
    assert benchmark.stats["mean"] < _ROLLUP_BUDGET


def test_rollup_activity(benchmark):
    """Per-frequency activity counts from 15 m rollup.

    Expected: < 0.05 s  |  Budget: < 2 s
    """
    result = benchmark(fetch_rollup_activity, PERF_BAND_ID, 15, -3.0, _OLD_FILTERS)
    assert len(result) > 0
    assert benchmark.stats["mean"] < _ROLLUP_BUDGET


def test_rollup_histogram(benchmark):
    """Power histogram from 15 m rollup — far fewer rows than raw.

    Expected: < 0.05 s  |  Budget: < 2 s
    """
    result = benchmark(fetch_rollup_histogram, PERF_BAND_ID, 15, _OLD_FILTERS)
    assert len(result) > 0
    assert benchmark.stats["mean"] < _ROLLUP_BUDGET


def test_rollup_signal_raw(benchmark):
    """Signal rows above threshold from 15 m rollup.

    Expected: < 0.05 s  |  Budget: < 2 s
    """
    result = benchmark(fetch_rollup_signal_raw, PERF_BAND_ID, 15, -3.0, _OLD_FILTERS)
    assert len(result) > 0
    assert benchmark.stats["mean"] < _ROLLUP_BUDGET


def test_rollup_vs_raw_speedup(large_db, monkeypatch):
    """Sanity-check: rollup query must be at least 5× faster than the raw scan.

    This is not a benchmark (no ``benchmark`` fixture) — it just asserts the
    routing delivers a meaningful speedup, so a future regression that routes
    back to raw is caught immediately.
    """
    import time

    monkeypatch.setattr(_eng, "DB_PATH",         large_db)
    monkeypatch.setattr(_eng, "_engine",          None)
    monkeypatch.setattr(_eng, "_session_factory", None)

    t0 = time.perf_counter()
    raw_result = fetch_band_stats(PERF_BAND_ID)
    raw_time = time.perf_counter() - t0

    t0 = time.perf_counter()
    rollup_result = fetch_rollup_stats(PERF_BAND_ID, 15, _OLD_FILTERS)
    rollup_time = time.perf_counter() - t0

    assert len(raw_result) > 0
    assert len(rollup_result) > 0
    speedup = raw_time / max(rollup_time, 1e-6)
    # Rollup should be meaningfully faster; 5× is a conservative threshold.
    assert speedup >= 5, (
        f"Rollup speedup too low: {speedup:.1f}× "
        f"(raw={raw_time:.3f}s rollup={rollup_time:.3f}s)"
    )
