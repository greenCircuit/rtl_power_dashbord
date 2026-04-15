# RTL Power Dashboard — Developer Guide

## Project structure

```
rtl_power_dashbord/
├── app/
│   ├── api/
│   │   └── routes/
│   │       ├── _helpers.py        # Shared validation helpers, filter parsing, device probe
│   │       ├── bands.py           # Band CRUD + start/stop endpoints
│   │       ├── measurements.py    # Per-band data endpoints (heatmap, spectrum, …)
│   │       ├── analysis.py        # Advanced analysis endpoints
│   │       └── status.py          # /api/status
│   ├── capture/
│   │   ├── manager.py             # Band scheduling, per-device cycling, thread safety
│   │   └── rtl_power.py           # rtl_power subprocess, CSV parsing, DB insert
│   ├── data/
│   │   ├── db/
│   │   │   ├── __init__.py        # Re-exports all public symbols — import surface
│   │   │   ├── _engine.py         # ORM models, engine, session factory
│   │   │   ├── bands.py           # Band CRUD and YAML seed
│   │   │   ├── measurements.py    # Measurement insert + fetch queries
│   │   │   ├── analysis.py        # Time-bucketed queries, GRANULARITY_SECONDS
│   │   │   └── maintenance.py     # Cleanup and DB status queries
│   │   └── parser.py              # Post-query processing (pandas, numpy)
│   ├── demo/
│   │   └── player.py              # DemoBandPlayer — drop-in for BandCaptureManager
│   ├── cleanup.py                 # Background data retention scheduler
│   ├── config.py                  # Config file + env var loading
│   └── __init__.py                # create_app() — Flask factory
├── ui/
│   └── src/
│       ├── components/
│       │   ├── charts/            # One file per Chart.js chart
│       │   └── ...                # Heatmap, BandTable, BandModal, FilterPanel, etc.
│       ├── hooks/
│       │   ├── useBandData.ts     # Data-fetching hooks (one per chart)
│       │   └── useChart.ts        # Shared Chart.js lifecycle hook
│       ├── api.ts                 # All API types and fetch functions
│       ├── store.ts               # Zustand global state
│       ├── chartConfig.ts         # Shared Chart.js base options and scale factory
│       └── colors.ts              # Plasma and YlOrRd colour map functions
├── tests/
│   ├── conftest.py                # Shared fixtures (tmp_db, flask_client)
│   ├── test_config.py             # load_cleanup_config tests
│   ├── api/                       # Route-level integration tests
│   │   ├── test_bands_routes.py
│   │   ├── test_analysis.py
│   │   ├── test_advanced_analysis.py
│   │   └── test_status.py
│   ├── capture/                   # BandCaptureManager and rtl_power parser tests
│   │   ├── test_manager.py
│   │   └── test_rtl_power.py
│   └── data/
│       ├── db/                    # DB-layer unit tests
│       │   ├── test_bands.py
│       │   ├── test_measurements.py
│       │   └── test_seeding.py
│       └── test_parser.py         # build_heatmap_arrays tests
├── docs/                          # This documentation
├── config.yaml                    # Band seed config + runtime settings
├── run.py                         # Entry point
├── Dockerfile
└── docker-compose.yml
```

---

## Development setup

### Sandbox (recommended)

The sandbox image has all dependencies pre-installed and bind-mounts the repo at `/app`, so edits on the host are immediately live inside the container.

```bash
# Build once
podman build -f Dockerfile.sandbox -t localhost/rtl-sandbox .

# Start detached container
./scripts/sandbox-run.sh

# Open a shell in the running container
./scripts/sandbox-exec.sh
```

Inside the container:

```bash
# Run backend
python run.py

# Run frontend dev server with HMR (proxies /api to Flask)
cd ui && npm run dev

# Run tests
pytest
```

### Local without Docker

```bash
python -m venv vevn && source vevn/bin/activate
pip install -r requirements.txt
cd ui && npm install
```

> **Note:** the virtual environment directory is `vevn/` (not the conventional `venv/`). Always use `vevn/bin/pytest`, `vevn/bin/python`, etc.

---

## Backend

### Entry point (`run.py` → `create_app()`)

`app/__init__.py` contains `create_app()`, the Flask application factory. On startup it:

1. Initialises the database schema (`init_db()`)
2. Seeds bands from `config.yaml` — skips bands that already exist
3. Auto-starts any band with `is_active = true`
4. Starts the cleanup scheduler background thread
5. Registers the API blueprint and static file routes

When `FLASK_DEBUG=true` the Werkzeug reloader spawns a child process; auto-start is suppressed in the parent to avoid double-starting captures and causing device contention. Look for `WERKZEUG_RUN_MAIN` to understand the guard.

### Session lifecycle (`app/data/db/_engine.py`)

All DB operations use the `_session()` context manager, which behaves differently depending on context:

- **Inside a Flask request**: reuses a single `Session` stored on `flask.g._db_session`. All DB calls within one request share one connection and one transaction. The session is closed (and rolled back on error) by the `teardown_appcontext` hook in `create_app()`.
- **Outside a Flask request** (startup, background threads, unit tests without `flask_client`): opens a fresh `Session`, yields it, and closes it on exit.

This means:
- You do not need to manually call `sess.close()` in route handlers.
- Background threads (cleanup, capture monitor) each get their own session.
- Unit tests that do not use `flask_client` also get isolated sessions — no leakage between tests.

### Capture pipeline (`app/capture/`)

**`rtl_power.py` — `RTLPowerCapture`**

Spawns `rtl_power` as a subprocess and reads stdout line-by-line. Each CSV line:

```
date, time, hz_low, hz_high, hz_step, samples, db_values...
```

The parser computes bin frequencies as:
```python
freq_mhz = np.linspace(hz_low, hz_high, len(db_values)) / 1e6
```

Only bins where `power_db >= band.min_power` are stored. Rows are accumulated in a per-band dict keyed by timestamp and flushed in bulk at each sweep boundary (when the timestamp changes). This reduces commit rate from ~1 commit per CSV line to 1 commit per complete sweep.

**`manager.py` — `BandCaptureManager`**

Manages one `RTLPowerCapture` per device at a time. Multiple bands on the same device are cycled sequentially using `threading.Timer`.

All state (`_active`, `_captures`, `_timers`, `_cycle_idx`) is guarded by `self._lock`. The lock discipline is:

| Method | Lock behaviour |
|---|---|
| `start_band`, `stop_band`, `start_active_bands` | Acquire lock, call `_restart_device` (lock-held helper) |
| `get_status`, `get_error`, `all_statuses` | Acquire lock for the full read |
| `_restart_device`, `_next_band` | Must be called with lock held |
| `_run_band` (timer callback) | Acquires lock, pops stale `_captures`/`_timers` entries **before releasing**, then calls `_start_capture` lock-free |
| `_start_capture` | Called without lock; writes `_captures[device]` and `_timers[device]` atomically as the final step |

> **Caveat:** `_run_band` clears `_captures[device]` and `_timers[device]` under the lock before releasing it. This prevents `_restart_device` (which runs under the lock) from observing a half-replaced capture. Any new code that reads or writes `_captures` or `_timers` must hold `self._lock`.

### Database layer (`app/data/db/`)

The package re-exports all public symbols from its sub-modules via `__init__.py`, so all existing `from app.data.db import X` and `import app.data.db as db` call-sites work without knowing the internal layout.

**Sub-module responsibilities:**

| Module | Contents |
|---|---|
| `_engine.py` | `Band`, `BandMeasurement` ORM models; `get_engine()`, `_session()`, `init_db()`, `_apply_filters()` |
| `bands.py` | `create_band`, `update_band`, `delete_band`, `list_bands`, `get_band`, `seed_bands_from_yaml`, `_seed_one_band` |
| `measurements.py` | `insert_band_measurements`, `fetch_band_measurements` (with adaptive downsampling), all per-band stat/activity queries |
| `analysis.py` | `GRANULARITY_SECONDS` (single source of truth), `fetch_band_tod_activity`, `fetch_band_activity_timeline`, `fetch_band_activity_trend`, `fetch_band_power_envelope` |
| `maintenance.py` | `cleanup_old_data`, `fetch_db_status` |

**Heatmap query — adaptive downsampling**

`fetch_band_measurements` uses a two-pass approach to avoid loading large datasets into Python:

1. A cheap metadata query counts distinct timestamps and gets the time range.
2. If distinct timestamps ≤ 300: return all raw rows (full resolution).
3. If distinct timestamps > 300: `GROUP BY` time bucket with `AVG(power_db)` in SQL, returning at most 300 buckets. Bucket width is `(max_ts − min_ts) / 300` seconds.

This means the heatmap always delivers at most 300 × N_freq rows to Python regardless of how much data is stored.

**`GRANULARITY_SECONDS` — single source of truth**

Valid granularity strings (`"15m"`, `"30m"`, `"1h"`, `"6h"`, `"1d"`) and their bucket widths are defined once in `app/data/db/analysis.py`. The API helper `_helpers.py` derives `VALID_GRANULARITIES = frozenset(GRANULARITY_SECONDS)` at import time. To add a new granularity, add it to `GRANULARITY_SECONDS` only — validation and SQL bucket arithmetic will pick it up automatically.

**Device probing**

`_get_devices()` (in `_helpers.py`) runs `rtl_test` once on first call and caches the result for the lifetime of the process. Device info is included in the `/api/status` response.

### API (`app/api/routes/`)

All routes are registered under the `api_bp` Blueprint at `/api`. Routes are split by concern across four files:

| File | Endpoints |
|---|---|
| `bands.py` | `GET/POST /bands`, `PUT/DELETE /bands/<id>`, `/bands/<id>/start`, `/bands/<id>/stop`, `/bands/<id>/status` |
| `measurements.py` | `/bands/<id>/heatmap`, `/spectrum`, `/activity`, `/timeseries`, `/noise-floor` |
| `analysis.py` | `/bands/<id>/tod-activity`, `/signal-durations`, `/power-histogram`, `/top-channels`, `/activity-trend`, `/crossband-timeline`, `/overview` |
| `status.py` | `/status` |

**Input validation**

All routes validate query parameters and request body values at the HTTP boundary using helpers from `_helpers.py`:

- `_parse_float_arg(args, name, default)` — raises `ValueError` on non-numeric input
- `_parse_int_arg(args, name, default, min_val, max_val)` — raises `ValueError` on non-integer or out-of-range
- `_parse_granularity(args, default)` — raises `ValueError` for unknown granularity strings
- `_parse_filters(args)` — parses the common `freq_min`, `freq_max`, `time_min`, `time_max`, `power_min` params

All routes wrap param parsing in `try/except ValueError → return jsonify({"error": str(exc)}), 400`. Do not add new routes without following this pattern.

`bands.py` uses a dedicated `_parse_band_body()` helper that:
- Validates `interval_s` is an integer ≥ 1
- Validates `device_index` is an integer ≥ 0
- Validates `min_power` is a float
- Handles `is_active` as a bool **or** the strings `"true"` / `"false"` / `"1"` / `"0"`. Any other string raises `ValueError`. Do not use `bool("false")` — it evaluates to `True` because any non-empty string is truthy in Python.

Full API endpoint reference:

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/status` | Backend health, DB stats, device list, per-band row counts |
| `GET` | `/api/bands` | All bands with live capture status |
| `POST` | `/api/bands` | Create a band |
| `PUT` | `/api/bands/<id>` | Update a band |
| `DELETE` | `/api/bands/<id>` | Delete a band and all its data |
| `POST` | `/api/bands/<id>/start` | Start capture |
| `POST` | `/api/bands/<id>/stop` | Stop capture |
| `GET` | `/api/bands/<id>/status` | Current capture status and last error for a band |
| `GET` | `/api/bands/<id>/heatmap` | Heatmap data (time × freq × power) |
| `GET` | `/api/bands/<id>/spectrum` | Mean + peak power per frequency |
| `GET` | `/api/bands/<id>/activity` | Activity % per frequency |
| `GET` | `/api/bands/<id>/timeseries` | Power over time for a single frequency |
| `GET` | `/api/bands/<id>/noise-floor` | Min/mean/max power over time buckets |
| `GET` | `/api/bands/<id>/tod-activity` | Time-of-day 7×24 occupancy grid |
| `GET` | `/api/bands/<id>/signal-durations` | Signal on-duration histogram |
| `GET` | `/api/bands/<id>/power-histogram` | Power level distribution histogram |
| `GET` | `/api/bands/<id>/top-channels` | Most active frequency bins |
| `GET` | `/api/bands/<id>/activity-trend` | Activity % bucketed over time |
| `GET` | `/api/crossband-timeline` | Per-band hourly activity timeline |
| `GET` | `/api/overview` | Summary across all bands |

Common optional query parameters accepted by all data endpoints:

| Parameter | Type | Description |
|---|---|---|
| `freq_min` | float | Lower frequency filter (MHz) |
| `freq_max` | float | Upper frequency filter (MHz) |
| `time_min` | string | Start of time window — **must use space separator**: `2024-01-15 12:00:00` |
| `time_max` | string | End of time window — same format |
| `power_min` | float | Minimum power filter (dBFS) |
| `threshold` | float | Activity threshold for analysis endpoints |
| `granularity` | string | Time bucket width: `15m`, `30m`, `1h`, `6h`, `1d` |

### Parser (`app/data/parser.py`)

Converts DB result sets into chart-ready dicts. Handles:
- Heatmap pivot tables via pandas (after DB-level downsampling, the in-memory dataset is small)
- Activity percentages (`active / total * 100`)
- Signal duration detection (Python-level contiguous-run scan per frequency)
- Time-of-day 7×24 grid construction
- Float sanitisation via `_safe_float()` — converts `NaN` and `Inf` to `None` so output is always valid JSON

### Demo mode (`app/demo/player.py`)

`DemoBandPlayer` is a drop-in replacement for `BandCaptureManager`. When `DEMO_MODE=true`, it is instantiated instead at the bottom of `manager.py` and assigned to `band_manager`. It replays sweeps from `demo/seed.db` in a continuous loop, writing rows with current timestamps so all API endpoints keep working unchanged.

Demo timestamps are written in the same `"YYYY-MM-DD HH:MM:SS"` space-separated format as real captures — **not** ISO 8601 `T`-separator format.

### Config loading (`app/config.py`)

`load_cleanup_config()` reads the `clean_up` section from `config.yaml`. If the file is missing or any value fails to parse, it logs a `WARNING` and returns built-in defaults. It does not raise — the scheduler continues running on defaults. The `_log_file_enabled()` helper follows the same pattern.

Seeding (`seed_bands_from_yaml`) skips any entry that is missing a required key (`id`, `name`, `freq_start`, `freq_end`, `freq_step`) or has a value that cannot be coerced to the expected type. Each bad entry logs a `WARNING` and is skipped; the remaining entries are still processed.

---

## Frontend

### State management (`store.ts`)

Zustand store holds:
- `bands` — list of all configured bands
- `bandId` — currently selected band for chart display
- `filters` — active time/frequency/power filters
- `threshold` — activity threshold slider value
- `refreshTick` / `analysisTick` — increment-only counters that trigger data refetch
- `heatmapLayout` — shared layout computed by the heatmap canvas for the timeseries overlay
- `selectedFreq` — frequency clicked on the heatmap (triggers timeseries load)

### Data fetching (`hooks/useBandData.ts`)

One hook per chart (`useHeatmap`, `useSpectrum`, `useActivity`, etc.). All are thin wrappers around `useBandFetch`, which:
- Cancels in-flight requests when `bandId` changes (stale result guard)
- Automatically refetches when `bandId`, `filters`, `threshold`, or the poll tick changes

### Chart lifecycle (`hooks/useChart.ts`)

Chart.js instances are expensive to create. All Chart.js charts use the `useChart` hook to avoid the destroy/recreate cycle on every data poll:

```ts
useChart(data, canvasRef, create, update)
```

- **`create(canvas, data) → Chart`** — called once on first data arrival
- **`update(chart, data) → void`** — called on subsequent changes; mutates `chart.data` in-place and calls `chart.update('none')`

The canvas is shown only when data is non-null, so `create` is only called when the canvas has real dimensions.

### Adding a new chart

1. Add a backend endpoint in the appropriate `app/api/routes/*.py` file
2. Add a DB query function in the appropriate `app/data/db/*.py` module
3. Add a parser function in `app/data/parser.py` if post-processing is needed
4. Add the API type and fetch function in `ui/src/api.ts`
5. Add a hook in `ui/src/hooks/useBandData.ts` using `useBandFetch`
6. Create `ui/src/components/charts/MyChart.tsx` using `useChart`
7. Add the component to `App.tsx`

---

## Testing

```bash
vevn/bin/pytest
```

The test suite mirrors the source layout:

```
tests/
├── conftest.py              # tmp_db, flask_client fixtures; insert_measurements helper
├── test_config.py           # load_cleanup_config — error logging, defaults, valid config
├── api/                     # Route integration tests via Flask test client
├── capture/                 # BandCaptureManager unit tests; rtl_power CSV parser tests
└── data/
    ├── db/                  # Per-module DB layer tests
    └── test_parser.py       # build_heatmap_arrays — dimensions, NaN safety, downsampling
```

### Test isolation

- All DB tests use the `tmp_db` or `flask_client` fixture from `conftest.py`.
- Both fixtures monkeypatch `app.data.db._engine.DB_PATH` to a temp file and reset `_engine` and `_session_factory` to `None` so the next `get_engine()` call creates a fresh engine pointed at the temp path.
- The `flask_client` fixture also patches `seed_bands_from_yaml` to a no-op so tests control all data.
- `BandCaptureManager` tests patch `RTLPowerCapture` with a `MagicMock` so no real subprocess is spawned.

### Key test categories

| File | What it covers |
|---|---|
| `test_manager.py` | Deadlock regression (non-reentrant lock), band cycling, locking correctness for `get_status`/`get_error`/`all_statuses`, `_run_band` atomicity |
| `test_rtl_power.py` | `_parse_csv_line` and `_build_measurement_rows` pure-function tests |
| `test_bands.py` | Band CRUD round-trips |
| `test_measurements.py` | Insert/fetch, T-separator timestamp bug regression, adaptive bucketing |
| `test_seeding.py` | YAML seed, duplicate skipping, malformed entry handling (Bug #8 regression) |
| `test_parser.py` | Heatmap pivot dimensions, NaN→None sanitisation, downsampling |
| `test_bands_routes.py` | Full CRUD HTTP contract; all `400` validation paths for `interval_s`, `min_power`, `device_index`, `is_active` string coercion |
| `test_analysis.py` | `200`/`404` contracts; filter validation `400`s; NaN-free JSON |
| `test_advanced_analysis.py` | `threshold`, `limit`, `granularity` validation; `200` shape checks |
| `test_config.py` | `load_cleanup_config` — bad YAML logs warning and returns defaults, not raises |

---

## Caveats and known constraints

### Timestamp format
Timestamps in `band_measurements` are stored as `"YYYY-MM-DD HH:MM:SS"` (space separator). All comparison logic — including `WHERE timestamp >= ?` filters in SQLite — depends on this format being lexicographically sortable. Never write `T`-separated timestamps into the DB (the old demo player had this bug; it has been fixed). The frontend must normalise datetime-local input with `.replace("T", " ")` before use as a filter.

### `BandCaptureManager` lock rules
`self._lock` is a plain non-reentrant `threading.Lock`. Any method that acquires it must not call another method that also acquires it, or the thread will deadlock permanently. The invariant:
- `_restart_device` and `_next_band` are lock-required helpers — call only while holding the lock.
- `_start_capture` is lock-free — call only after releasing the lock.
- `_run_band` (timer callback) acquires the lock, does its work, releases the lock, then calls `_start_capture`. It clears `_captures[device]` and `_timers[device]` under the lock so `_restart_device` never sees an inconsistent mid-swap state.

### `rtl_power` limitation — one range per process
`rtl_power` only reliably outputs data for the **last** `-f` range when multiple non-contiguous ranges are given. The manager works around this by spawning one process per band. This is why the cycling architecture exists — it is not a performance choice.

### SQLite WAL mode
WAL mode is enabled via a `PRAGMA` on every new connection (the `_set_pragmas` event listener in `_engine.py`). This allows concurrent reads during writes and is important for the capture threads inserting rows while the Flask API is reading. Do not disable WAL mode or change to `PRAGMA synchronous=FULL` without understanding the performance impact on high-frequency bands (e.g. a 12.5 kHz step VHF scan produces ~1 680 rows per sweep).

### `GRANULARITY_SECONDS` — single source of truth
Valid granularity values and their SQL bucket widths live in `app/data/db/analysis.py`. The API validator derives its allowed-set from this dict at import time. To add a new granularity, add it here only. Do not hardcode granularity strings anywhere else.

### Demo mode replays, not real-time
`DemoBandPlayer` replays sweeps as fast as the configured `interval_s` allows. It does not simulate RF physics or inject realistic noise. The seed DB (`demo/seed.db`) must contain data for the band IDs configured in `config.yaml`; a band with no seed data will log a warning and produce no chart output.

### `bool("false") == True`
Python's `bool()` treats any non-empty string as `True`. The `_parse_band_body()` helper handles this by explicitly checking string values against `("true", "1")` and `("false", "0")`. Do not use `bool(value)` on values that might arrive as the string `"false"` from JSON.
