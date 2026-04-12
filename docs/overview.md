# RTL Power Dashboard — Project Overview

## Purpose

RTL Power Dashboard is a self-hosted RF spectrum monitoring tool. It uses a cheap RTL-SDR USB dongle and the `rtl_power` command-line tool to continuously scan user-defined frequency bands, store the measurements in a local SQLite database, and present them as interactive charts in a web browser.

The primary use case is long-running, unattended monitoring — leaving the dongle running overnight and then exploring what was transmitting, when, and at what power level. It is not a real-time receiver or decoder; it is a spectrum occupancy recorder and visualiser.

---

## What it does

- **Band capture** — for each configured band, `rtl_power` is invoked as a subprocess. It scans the frequency range at the configured step size on a repeating interval and emits CSV lines to stdout. The dashboard parses this stream and writes measurements into the database.

- **Multi-band scheduling** — an RTL-SDR device can only scan one range at a time. When multiple bands are assigned to the same device, the manager cycles through them: band A runs for its configured interval, then band B, then band C, and so on. Each band is served; it just scans every `(n_bands × interval_s)` seconds instead of every `interval_s`.

- **Persistent storage** — all measurements are stored in a SQLite database (`data/rtl_power.db`). Data survives restarts and accumulates indefinitely until a band is deleted.

- **Web dashboard** — a Flask application serves a single-page dashboard. Charts are rendered in the browser using Chart.js and a custom canvas-based heatmap renderer. No external services or internet connection are required at runtime.

---

## Architecture

```
RTL-SDR dongle
      │
      ▼
  rtl_power (subprocess)
      │  stdout CSV stream
      ▼
 RTLPowerCapture          ← app/capture/rtl_power.py
  parse → filter → batch insert
      │
      ▼
  SQLite (WAL mode)       ← data/rtl_power.db
      │
      ▼
  Flask API               ← app/api/routes.py
  (query + aggregate)
      │
      ▼
  Browser (Chart.js)      ← app/static/js/dashboard.js
```

### Key components

| File | Responsibility |
|---|---|
| `app/capture/rtl_power.py` | Spawns `rtl_power`, reads stdout line-by-line, routes CSV rows to the correct band, batch-inserts into SQLite |
| `app/capture/manager.py` | Tracks active bands per device, cycles them, manages `threading.Timer` scheduling |
| `app/data/db.py` | All SQLite queries — schema init, CRUD for bands, time-series queries, aggregations |
| `app/data/parser.py` | Post-query processing — pivot tables (pandas), activity percentages, signal duration extraction |
| `app/api/routes.py` | Flask blueprints — 15 REST endpoints consumed by the browser |
| `app/templates/index.html` | Single HTML page — layout, Bootstrap 5, inline CSS |
| `app/static/js/dashboard.js` | All frontend logic — chart rendering, heatmap canvas, band CRUD, filters |
| `bands.yaml` | Seed configuration — bands defined here are loaded on first startup if they don't already exist in the DB |

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
| `min_power` | REAL | Rows with peak power below this value are discarded at ingest |
| `device_index` | INTEGER | Which RTL-SDR dongle to use (0-indexed) |
| `is_active` | INTEGER | 1 = auto-start on server launch |

### `band_measurements` table

One row per frequency bin per sweep.

| Column | Type | Description |
|---|---|---|
| `band_id` | TEXT | Foreign key → `bands.id` |
| `timestamp` | TEXT | `"YYYY-MM-DD HH:MM:SS"` |
| `frequency_mhz` | REAL | Centre frequency of this bin |
| `power_db` | REAL | Power in dBFS |

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `DATA_DIR` | `<project>/data` | Directory for the SQLite DB and log file |
| `DB_PATH` | `$DATA_DIR/rtl_power.db` | Explicit DB path override |
| `BANDS_CONFIG` | `<project>/bands.yaml` | Path to the seed YAML |
| `LOG_PATH` | `<project>/log.log` | Log file location |
| `LOG_LEVEL` | `INFO` | Python logging level |
| `PORT` | `8050` | HTTP port |
| `FLASK_DEBUG` | `false` | Enable Flask dev server with reloader |
