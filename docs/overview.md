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
  Flask API                       ← app/api/routes.py
  (query + aggregate via parser)
      │
      ▼
  React SPA (Vite build)          ← ui/src/
  Chart.js + canvas heatmap
```

### Key components

| File | Responsibility |
|---|---|
| `app/capture/rtl_power.py` | Spawns `rtl_power`, reads stdout line-by-line, filters per-reading by `min_power`, routes CSV rows to the correct band, batch-inserts via SQLAlchemy |
| `app/capture/manager.py` | Tracks active bands per device, cycles them, manages `threading.Timer` scheduling |
| `app/data/db.py` | SQLAlchemy ORM models, schema init, band CRUD, all measurement queries and aggregations. Heatmap queries auto-downsample in SQL when data exceeds 300 time buckets |
| `app/data/parser.py` | Post-query processing — pivot tables (pandas), activity percentages, signal duration extraction, time-of-day grids |
| `app/api/routes.py` | Flask blueprints — REST endpoints consumed by the React frontend. Device list is cached and included in the `/api/status` response |
| `app/cleanup.py` | Background cleanup scheduler — reads config each cycle, deletes old rows and trims DB size |
| `app/config.py` | Reads `config.yaml` and environment variables; exposes paths and cleanup/logging settings |
| `ui/src/hooks/useChart.ts` | Shared React hook — creates a Chart.js instance once on first data, then updates it in-place on subsequent data changes to avoid expensive destroy/recreate cycles |
| `ui/src/` | React + TypeScript SPA — Chart.js charts, canvas heatmap, band management UI, filter panel |
| `config.yaml` | Main configuration — bands seed, cleanup policy, logging, chart poll intervals |

---

## Data model

### `bands` table

Each row is a named frequency range with capture parameters.

| Column | Type | Description |
|---|---|---|
| `id` | TEXT | Short unique identifier (8 hex chars or custom from YAML) |
| `name` | TEXT | Human-readable label |
| `freq_start` | TEXT | rtl_power notation: `"144M"`, `"462.5M"`, `"1.2G"` |
| `freq_end` | TEXT | Same notation |
| `freq_step` | TEXT | Resolution: `"12.5k"`, `"25k"`, `"100k"` |
| `interval_s` | INTEGER | How long to scan this band per cycle (seconds) |
| `min_power` | REAL | Individual readings below this value are discarded at ingest |
| `device_index` | INTEGER | Which SDR device to use (0-indexed) |
| `is_active` | INTEGER | 1 = auto-start on server launch |

### `band_measurements` table

One row per frequency bin per sweep where power ≥ band's `min_power`.

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER | Auto-increment primary key |
| `band_id` | TEXT | Foreign key → `bands.id` |
| `timestamp` | TEXT | `"YYYY-MM-DD HH:MM:SS"` |
| `frequency_mhz` | REAL | Centre frequency of this bin |
| `power_db` | REAL | Power in dBFS |

Indexes: `(band_id, timestamp)` and `(band_id, frequency_mhz)`.

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
    ...
```

Cleanup rules are **OR** — whichever condition is met first triggers a delete pass. The job re-reads `config.yaml` each cycle so changes take effect without a server restart.

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `DATA_DIR` | `<project>/data` | Directory for the SQLite DB |
| `BANDS_CONFIG` | `<project>/config.yaml` | Path to the main config YAML |
| `LOG_PATH` | `<project>/log.log` | Log file location (only used when `logs.enabled = true`) |
| `LOG_LEVEL` | `INFO` | Python logging level |
| `DEMO_MODE` | `false` | Replay seed data without hardware |
| `PORT` | `8050` | HTTP port |
| `FLASK_DEBUG` | `false` | Enable Flask dev server with reloader |
