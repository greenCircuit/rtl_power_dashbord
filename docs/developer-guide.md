# RTL Power Dashboard — Developer Guide

## Project structure

```
rtl_power_dashbord/
├── app/
│   ├── api/
│   │   └── routes.py          # Flask REST API (all /api/* endpoints)
│   ├── capture/
│   │   ├── manager.py         # Band scheduling, per-device cycling
│   │   └── rtl_power.py       # rtl_power subprocess, CSV parsing, DB insert
│   ├── data/
│   │   ├── db.py              # SQLAlchemy ORM, all queries and aggregations
│   │   └── parser.py          # Post-query processing (pandas, numpy)
│   ├── cleanup.py             # Background data retention scheduler
│   └── config.py              # Config file + env var loading
├── ui/
│   └── src/
│       ├── components/
│       │   ├── charts/        # One file per Chart.js chart
│       │   └── ...            # Heatmap, BandTable, BandModal, FilterPanel, etc.
│       ├── hooks/
│       │   ├── useBandData.ts # Data-fetching hooks (one per chart)
│       │   └── useChart.ts    # Shared Chart.js lifecycle hook
│       ├── api.ts             # All API types and fetch functions
│       ├── store.ts           # Zustand global state
│       ├── chartConfig.ts     # Shared Chart.js base options and scale factory
│       └── colors.ts          # Plasma and YlOrRd colour map functions
├── tests/                     # pytest test suite
├── docs/                      # This documentation
├── config.yaml                # Band seed config + runtime settings
├── run.py                     # Entry point — starts Flask + background threads
├── Dockerfile                 # Production image
├── Dockerfile.sandbox         # Dev sandbox image (bind-mounts source)
└── docker-compose.yml         # Single-service compose for production
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
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cd ui && npm install
```

Run backend and frontend separately as above.

---

## Backend

### Entry point (`run.py`)

Starts three things:
1. Flask HTTP server (dev server or gunicorn depending on `FLASK_DEBUG`)
2. Band manager — restores `is_active` bands from the database on startup
3. Cleanup scheduler — background thread that enforces data retention policy

### Capture pipeline (`app/capture/`)

**`rtl_power.py` — `RTLPowerCapture`**

Spawns `rtl_power` as a subprocess and reads stdout line-by-line. Each line is a CSV row:

```
date, time, hz_low, hz_high, hz_step, samples, db_values...
```

The parser computes the centre frequency of each bin as:
```
freq_mhz = linspace(hz_low, hz_high, len(db_values)) / 1e6
```

Only bins where `power_db >= band.min_power` are kept. Accepted readings are accumulated into a batch and inserted in bulk via SQLAlchemy to reduce transaction overhead.

**`manager.py` — `BandManager`**

Maintains a dict of active capture threads keyed by `band_id`. When multiple bands share a device, they are cycled sequentially using `threading.Timer`: band A runs for `interval_s`, then band B, then C, wrapping around. Bands on different devices run truly in parallel.

### Database layer (`app/data/db.py`)

SQLAlchemy ORM with WAL mode enabled for concurrent reads during writes.

**Heatmap query — adaptive downsampling**

`fetch_band_measurements` uses a two-step approach to avoid loading large datasets into Python:

1. A cheap metadata query counts distinct timestamps and gets the time range.
2. If distinct timestamps ≤ 300: return all raw rows (full resolution).
3. If distinct timestamps > 300: `GROUP BY` time bucket with `AVG(power_db)` in SQL, returning at most 300 buckets. Bucket width is calculated as `(max_ts - min_ts) / 300` seconds.

This means the heatmap always delivers at most 300 × N_freq rows to Python regardless of how much data is stored. Zooming into a short time window that fits within 300 buckets always shows full resolution.

**Device probing**

`_get_devices()` runs `rtl_test` once on first call and caches the result for the lifetime of the process. Device info is included in the `/api/status` response so the frontend does not need a separate `/api/devices` request when opening the status panel.

**Aggregated queries**

Most analysis endpoints (`fetch_band_stats`, `fetch_band_activity`, `fetch_band_tod_activity`, `fetch_band_activity_trend`, `fetch_band_top_channels`) push all aggregation into SQLite with `GROUP BY`. They return small result sets regardless of total row count and scale well into tens of millions of rows.

### Parser (`app/data/parser.py`)

Converts DB result sets into chart-ready dicts. Handles:
- Heatmap pivot tables via pandas (after DB-level downsampling the dataset is small)
- Activity percentages (`active / total * 100`)
- Signal duration detection (Python-level contiguous-run scan per frequency)
- Time-of-day 7×24 grid construction

### API (`app/api/routes.py`)

All routes are in a single Flask blueprint registered at `/api`. Filters (time range, frequency range, power min) are parsed from query string parameters and passed through to the DB layer via `_parse_filters()`.

Key endpoints:

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/status` | Backend health, DB stats, device list, per-band row counts |
| `GET` | `/api/devices` | Available SDR devices (index + name) |
| `GET` | `/api/bands` | All bands with live capture status |
| `POST` | `/api/bands` | Create a band |
| `PUT` | `/api/bands/<id>` | Update a band |
| `DELETE` | `/api/bands/<id>` | Delete a band and all its data |
| `POST` | `/api/bands/<id>/start` | Start capture |
| `POST` | `/api/bands/<id>/stop` | Stop capture |
| `GET` | `/api/bands/<id>/heatmap` | Heatmap data (time × freq × power) |
| `GET` | `/api/bands/<id>/spectrum` | Mean + peak power per frequency |
| `GET` | `/api/bands/<id>/activity` | Activity % per frequency |
| `GET` | `/api/bands/<id>/timeseries` | Power over time for a single frequency |
| `GET` | `/api/bands/<id>/tod-activity` | Time-of-day 7×24 occupancy grid |
| `GET` | `/api/bands/<id>/signal-durations` | Signal on-duration histogram |
| `GET` | `/api/bands/<id>/power-histogram` | Power level distribution histogram |
| `GET` | `/api/bands/<id>/top-channels` | Most active frequency bins |
| `GET` | `/api/bands/<id>/activity-trend` | Activity % bucketed over time |

All data endpoints accept these optional query parameters:

| Parameter | Type | Description |
|---|---|---|
| `freq_min` | float | Lower frequency filter (MHz) |
| `freq_max` | float | Upper frequency filter (MHz) |
| `time_min` | string | Start of time window (`YYYY-MM-DD HH:MM:SS`) |
| `time_max` | string | End of time window |
| `power_min` | float | Minimum power filter (dBFS) |
| `threshold` | float | Activity threshold for analysis endpoints |

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

Chart.js instances are expensive to create. All six Chart.js charts use the `useChart` hook to avoid the destroy/recreate cycle on every data poll:

```ts
useChart(data, canvasRef, create, update)
```

- **`create(canvas, data) → Chart`** — called once on first data arrival, builds the full Chart.js config
- **`update(chart, data) → void`** — called on every subsequent data change, mutates `chart.data` and `chart.options` in-place, then the hook calls `chart.update('none')` (no animation)

Both functions are closures over the component's render scope, so they always see current state (threshold, granularity, etc.) at the time data changes — no stale closure issues.

The canvas is shown only when data is non-null (`style={{ display: data ? 'block' : 'none' }}`), so `create` is only called when the canvas has real dimensions.

The two raw-canvas charts (`Heatmap`, `TodHeatmap`) do not use Chart.js and already follow this pattern natively via `drawHeatmap()` / `drawTod()` called directly on data change.

### Adding a new chart

1. Add a backend endpoint in `app/api/routes.py`
2. Add a DB query function in `app/data/db.py`
3. Add a parser function in `app/data/parser.py` if post-processing is needed
4. Add the API type and fetch function in `ui/src/api.ts`
5. Add a hook in `ui/src/hooks/useBandData.ts` using `useBandFetch`
6. Create `ui/src/components/charts/MyChart.tsx` using `useChart`
7. Add the component to `App.tsx`

---

## Testing

```bash
pytest
```

Tests live in `tests/`. They cover API endpoints and the data layer. The test suite uses a real SQLite in-memory database — no mocking of the DB layer.

---

## Configuration reference

See [overview.md](overview.md) for the full `config.yaml` schema and environment variable reference.
