# RTL Power Dashboard — Project Overview

## Purpose

RTL Power Dashboard is a self-hosted RF spectrum monitoring tool. It uses a USB SDR receiver and the `rtl_power` command-line tool to continuously scan user-defined frequency bands, store the measurements in a local SQLite database, and present them as interactive charts in a web browser.

The primary use case is long-running, unattended monitoring — leaving the receiver running overnight and then exploring what was transmitting, when, and at what power level. It is not a real-time receiver or decoder; it is a spectrum occupancy recorder and visualiser.

---

## What it does

- **Band capture** — for each configured band, `rtl_power` is invoked as a subprocess. It scans the frequency range at the configured step size on a repeating interval and emits CSV lines to stdout. The dashboard parses this stream and writes measurements into the database. Only individual readings at or above the band's `min_power` are stored.

- **Multi-band scheduling** — a single SDR device can only scan one range at a time. When multiple bands are assigned to the same device, the manager cycles through them: band A runs for its configured interval, then band B, then band C. Each band is served; it just scans every `(n_bands × interval_s)` seconds instead of every `interval_s`. Bands on different devices capture independently and simultaneously.

- **Persistent storage** — all measurements are stored in a SQLite database (`data/rtl_power.db`) via SQLAlchemy. Data survives restarts and is pruned automatically by the cleanup scheduler.

- **Automatic cleanup** — a background job runs on a configurable interval and deletes data that is too old or when the database exceeds a size limit, keeping storage under control for long-running deployments.

- **Web dashboard** — a Flask application serves a React single-page application. Charts are rendered using Chart.js and a custom canvas-based heatmap renderer. No external services or internet connection are required at runtime.

- **Demo mode** — set `DEMO_MODE=true` to replay pre-recorded sweeps from a seed database without any SDR hardware. All API endpoints keep working unchanged.

---

## Architecture

```
USB SDR receiver
      │
      ▼
  rtl_power (subprocess)
      │  stdout CSV stream
      ▼
 RTLPowerCapture                  ← app/capture/rtl_power.py
  parse → filter → batch insert
      │
      ▼
  SQLite via SQLAlchemy (WAL)     ← data/rtl_power.db
      │                   ▲
      │                   │ cleanup scheduler (background thread)
      │               app/cleanup.py
      ▼
  Flask API                       ← app/api/routes/
  (query + aggregate via parser)
      │
      ▼
  React SPA (Vite build)          ← ui/src/
  Chart.js + canvas heatmap
```

### Key components

| File / package | Responsibility |
|---|---|
| `app/capture/rtl_power.py` | Spawns `rtl_power`, reads stdout line-by-line, filters per-reading by `min_power`, routes CSV rows to the correct band, batch-inserts via SQLAlchemy |
| `app/capture/manager.py` | Tracks active bands per device, cycles them, manages `threading.Timer` scheduling. Thread-safe: all state mutations hold `self._lock` |
| `app/data/db/` | Database package — ORM models, engine/session factory, band CRUD, measurement queries and aggregations |
| `app/data/db/_engine.py` | SQLAlchemy engine, session factory, per-request session via `flask.g`, ORM models |
| `app/data/db/bands.py` | Band CRUD and YAML seed functions |
| `app/data/db/measurements.py` | Measurement insert, fetch, and aggregation queries |
| `app/data/db/analysis.py` | Time-bucketed queries; defines `GRANULARITY_SECONDS` (single source of truth for valid granularity values) |
| `app/data/db/maintenance.py` | Cleanup and DB status queries |
| `app/data/parser.py` | Post-query processing — pivot tables (pandas), activity percentages, signal duration extraction, time-of-day grids |
| `app/api/routes/bands.py` | Band CRUD and capture control endpoints |
| `app/api/routes/measurements.py` | Per-band data endpoints (heatmap, spectrum, activity, timeseries, noise-floor) |
| `app/api/routes/analysis.py` | Advanced analysis endpoints (tod-activity, signal-durations, top-channels, etc.) |
| `app/api/routes/status.py` | `/api/status` — backend health, DB stats, device list |
| `app/api/routes/_helpers.py` | Shared validation helpers and filter parsing; derives `VALID_GRANULARITIES` from `GRANULARITY_SECONDS` |
| `app/cleanup.py` | Background cleanup scheduler — reads config each cycle, deletes old rows, trims DB size |
| `app/config.py` | Reads `config.yaml` and environment variables; exposes paths and cleanup/logging settings |
| `app/demo/player.py` | Demo mode — replays seed data in a continuous loop, writing rows with current timestamps |
| `ui/src/hooks/useChart.ts` | Shared React hook — creates a Chart.js instance once on first data, then updates it in-place |
| `ui/src/` | React + TypeScript SPA — Chart.js charts, canvas heatmap, band management UI, filter panel |
| `config.yaml` | Main configuration — bands seed, cleanup policy, logging, chart poll intervals |

---

## Data model

### `bands` table

Each row is a named frequency range with capture parameters.

| Column | Type | Description |
|---|---|---|
| `id` | TEXT | Short unique identifier (8 hex chars, or custom from YAML) |
| `name` | TEXT | Human-readable label |
| `freq_start` | TEXT | rtl_power notation: `"144M"`, `"462.5M"`, `"1.2G"` |
| `freq_end` | TEXT | Same notation |
| `freq_step` | TEXT | Resolution: `"12.5k"`, `"25k"`, `"100k"` |
| `interval_s` | INTEGER | How long to scan this band per cycle (seconds, ≥ 1) |
| `min_power` | REAL | Readings below this dBFS value are discarded at ingest |
| `device_index` | INTEGER | Which SDR device to use (0-indexed, ≥ 0) |
| `is_active` | INTEGER | 1 = auto-start on server launch |

### `band_measurements` table

One row per frequency bin per sweep where power ≥ band's `min_power`.

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER | Auto-increment primary key |
| `band_id` | TEXT | Foreign key → `bands.id` |
| `timestamp` | TEXT | `"YYYY-MM-DD HH:MM:SS"` (space separator, **not** `T`) |
| `frequency_mhz` | REAL | Centre frequency of this bin |
| `power_db` | REAL | Power in dBFS |

Indexes: `(band_id, timestamp)` and `(band_id, frequency_mhz)`.

**Timestamp format caveat** — timestamps are stored and filtered as plain strings using a space separator (`2024-01-15 12:34:56`), not ISO 8601 `T` separator. SQLite string comparison works correctly for the space format because it is lexicographically sortable. If `T` is used anywhere in a filter it will silently exclude all data because `T` (ASCII 84) > space (ASCII 32). The frontend must normalise datetime-local input values with `.replace("T", " ")` before sending them as filter parameters.

---

## Configuration file (`config.yaml`)

```yaml
clean_up:
  enabled: true
  interval_mins: 30       # how often the cleanup job runs
  db_max_size_mb: 1024    # delete oldest rows if DB exceeds this size
  max_time_hrs: 72        # delete rows older than this many hours

logs:
  enabled: false          # false = stdout only; true = stdout + log file

charts:
  main_poll_interval_s: 30
  analytics_poll_interval_s: 60

bands:
  - id: my-band
    name: "My Band"
    freq_start: "144M"
    freq_end: "146M"
    freq_step: "25k"
    interval_s: 10
    min_power: -20.0
    device_index: 0
    is_active: true
```

Cleanup rules are **OR** — whichever condition is met first triggers a delete pass. The job re-reads `config.yaml` each cycle so changes take effect without a server restart. If the file is malformed or a value cannot be parsed, a warning is logged and built-in defaults are used — the scheduler continues running.

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `DATA_DIR` | `<project>/data` | Directory for the SQLite DB |
| `BANDS_CONFIG` | `<project>/config.yaml` | Path to the main config YAML |
| `LOG_PATH` | `<project>/log.log` | Log file location (only used when `logs.enabled = true`) |
| `LOG_LEVEL` | `INFO` | Python logging level |
| `DEMO_MODE` | `false` | Replay seed data without hardware (`true`/`false`) |
| `DEMO_SEED_DB` | `<project>/demo/seed.db` | Path to the demo seed database |
| `PORT` | `8050` | HTTP port |
| `FLASK_DEBUG` | `false` | Enable Flask dev server with reloader |
