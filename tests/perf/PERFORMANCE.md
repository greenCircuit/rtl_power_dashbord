# Performance Benchmarks

## Overview

The `tests/perf/` suite measures query latency against a realistic dataset
(~816k rows — 7 days × 81 frequency bins × 60-second sweeps for one band).
It uses [pytest-benchmark](https://pytest-benchmark.readthedocs.io/) to collect
timing statistics and detect regressions against a saved baseline.

---

## Running the benchmarks

```bash
# One-off run — see timings, nothing saved
pytest tests/perf/ -v

# Save a new baseline (do this after a confirmed improvement)
pytest tests/perf/ --benchmark-save=baseline

# Regression check — fails if any query mean is >20% slower than baseline
pytest tests/perf/ --benchmark-compare=baseline --benchmark-compare-fail=mean:20%

# Exclude from the normal test suite (CI fast path)
pytest tests/ --ignore=tests/perf/
```

Baselines are stored in `.benchmarks/Linux-CPython-3.10-64bit/`.
Commit the baseline JSON alongside any change that intentionally alters performance.

---

## Dataset

| Parameter | Value |
|---|---|
| Band | 144–146 MHz, 25 kHz step → **81 frequency bins** |
| History | 7 days at 60-second sweep interval → **10,080 sweeps** |
| Total rows | **816,480** |
| Signal frequencies | 3 bins with signal power (~−2 dBm); rest are noise (~−15 dBm) |

All rows are kept (no `min_power` filter on the perf band) so queries see
maximum volume.

---

## Expected performance (baseline — SQLite, single machine)

### Raw-table queries (recent data, last 2 h window)

| Query | Expected mean | Budget | Notes |
|---|---|---|---|
| `fetch_timeseries` | ~70 ms | **< 4 s** | Downsampled to ≤300 time buckets; meta scan + indexed read |
| `fetch_stats` | ~1.7 s | **< 4 s** | `GROUP BY frequency_mhz` full-band scan |
| `fetch_activity` | ~1.8 s | **< 4 s** | Same pattern as stats with conditional sum |
| `fetch_alltime_peak` | ~1.7 s | **< 4 s** | `MAX(power_db) GROUP BY freq` — scans all time by design |
| `fetch_top_channels` | ~1.9 s | **< 4 s** | Adds `ORDER BY activity% DESC LIMIT 10` |
| `fetch_measurements` (heatmap avg) | ~1.9 s | **< 4 s** | Buckets 10,080 sweeps → ≤ 310 time slots in SQL |
| `fetch_measurements` (heatmap max-hold) | ~1.9 s | **< 4 s** | Same bucketing, `MAX` aggregator |
| `fetch_power_histogram` | ~1.8 s | **< 4 s** | Time-bucketed downsampling; was ~2.7 s raw |
| `fetch_signal_raw` | ~1.8 s | **< 4 s** | Downsampled peak-per-bucket; was ~4.5 s raw |

### Rollup-table queries (historical data, `time_min` > 2 h old → routes to pre-aggregated tier)

Rollup tiers are pre-computed at startup and updated every 15 minutes.
A 3-day query window hits the **15-minute tier** (~23k rows) instead of the raw table (~816k rows).

| Query | Expected mean | Budget | Speedup vs raw |
|---|---|---|---|
| `fetch_rollup_timeseries` | ~6 ms | **< 2 s** | ~300× |
| `fetch_rollup_stats` | ~19 ms | **< 2 s** | ~90× |
| `fetch_rollup_activity` | ~20 ms | **< 2 s** | ~90× |
| `fetch_rollup_signal_raw` | ~12 ms | **< 2 s** | ~150× |
| `fetch_rollup_histogram` | ~55 ms | **< 2 s** | ~30× |
| `fetch_rollup_measurements` | ~75 ms | **< 2 s** | ~25× |

> **Routing rule:** a query is routed to the rollup tier when `time_min` is
> present AND older than `raw_hours` (default: 2 h) AND the rollup tier has
> data for that band.  Queries with no `time_min` always hit the raw table.

> **Budgets** are set at 2× the current baseline mean to give headroom for CI
> variance while still catching significant regressions.  Tighten them as
> query performance improves.

---

## Known bottlenecks

### `fetch_measurements` / raw GROUP-BY queries (~1.7–1.9 s)
All full-band aggregations (`stats`, `activity`, `alltime_peak`, `top_channels`,
`measurements`) perform a full table scan over all rows for the band before
grouping.  For queries on historical data the rollup routing path bypasses this
entirely.  For recent-data queries a covering index on `(band_id, timestamp,
frequency_mhz, power_db)` would allow the scan to stay on index pages.

### First startup / empty rollup
`run_rollup_once()` is called at startup to pre-compute rollup tiers from
existing raw data.  On the very first run (or after the rollup table is cleared)
historical queries briefly fall back to the raw table until the rollup
computation completes.  Computation time scales with the amount of raw data
(~4 s per tier for 816k rows on a laptop).

---

## Adding a new benchmark

1. Add a test function in `test_db_queries.py` that accepts the `benchmark`
   fixture.
2. Call `benchmark(fn, *args)` — pytest-benchmark handles warmup and rounds
   automatically.
3. Add an assertion that verifies correctness (not just timing).
4. Run with `--benchmark-save=baseline` to update the baseline.
