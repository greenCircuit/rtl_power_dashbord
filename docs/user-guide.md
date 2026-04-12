# RTL Power Dashboard — User Guide

## Requirements

- An RTL-SDR compatible USB dongle (RTL2832U chipset)
- `rtl-sdr` package installed on the host (`sudo apt install rtl-sdr` on Debian/Ubuntu)
- Python 3.11+ with dependencies from `requirements.txt`, **or** Docker

---

## Getting started

### Option A — Run locally

```bash
# Create and activate a virtual environment
python -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt

# Build the React frontend
cd ui && npm install && npm run build && cd ..

# Start the server
python run.py
```

Open `http://localhost:8050` in a browser.

For frontend development with hot-reload, run Flask and Vite separately:

```bash
# Terminal 1 — Flask API
python run.py

# Terminal 2 — Vite dev server (proxies /api to Flask)
cd ui && npm run dev
```

Open the Vite URL shown in the terminal (typically `http://localhost:5173`).

### Option B — Docker (production)

```bash
docker compose up
```

Uses the `Dockerfile` image. The SQLite database is persisted in `./data` on the host.

### Option C — Docker (development sandbox)

Build the sandbox image once:

```bash
podman build -f Dockerfile.sandbox -t localhost/rtl-sandbox .
```

Start the container (runs detached, source bind-mounted):

```bash
./scripts/sandbox-run.sh
```

Exec into it from any terminal:

```bash
./scripts/sandbox-exec.sh
```

Inside the container run whatever you need (`python run.py`, `pytest`, `npm run dev`, etc.). Your edits on the host are immediately visible inside because the repo is bind-mounted at `/app`.

---

## Configuration (`config.yaml`)

All server-side settings live in `config.yaml`. Changes to the `clean_up` section take effect on the next cleanup cycle without restarting the server.

### Cleanup

```yaml
clean_up:
  enabled: true
  interval_mins: 30       # how often the cleanup job runs
  db_max_size_mb: 1024    # trigger cleanup if DB exceeds this size (MB)
  max_time_hrs: 72        # delete data older than this many hours
```

The two rules are **OR** — cleanup runs if either condition is met:
1. Any row is older than `max_time_hrs`
2. The database file exceeds `db_max_size_mb`

After deleting rows, SQLite's `VACUUM` is run to reclaim disk space.

### Logging

```yaml
logs:
  enabled: false   # false = stdout only; true = stdout + log file
```

When `false` (default), logs go to stdout only. Set to `true` to also write to `LOG_PATH` (default `log.log` in the project root).

### Chart polling

```yaml
charts:
  main_poll_interval_s: 30        # heatmap, spectrum, activity, timeseries
  analytics_poll_interval_s: 60   # time-of-day, signal durations
```

---

## Configuring bands

Bands can be managed two ways: via the web UI, or by editing `config.yaml` before first startup.

### Via the UI

Click **+ Add Band** at the top of the dashboard. Fill in:

| Field | Description | Example |
|---|---|---|
| Name | Label shown in the dashboard | `GMRS` |
| Freq Start | Lower edge of the range | `462.5` MHz |
| Freq End | Upper edge of the range | `462.8` MHz |
| Step | Frequency resolution per bin | `12.5` kHz |
| Interval | Seconds to spend scanning this band per cycle | `5` |
| Min Power | Discard individual readings below this level (dBFS) | `-100` (keep everything), `2` (only active signals) |
| Device | Which RTL-SDR dongle to use | `Device 0` |

Hit **Save**. The band appears in the table. Click **▶ Start** to begin capturing.

### Via config.yaml

Bands listed under `bands:` in `config.yaml` are seeded on startup if they don't already exist in the database. Editing the file after a band has been created has no effect — use the UI to modify existing bands.

```yaml
bands:
  - id: fm-broadcast         # unique identifier
    name: FM Broadcast
    freq_start: "87.5M"      # units: k = kHz, M = MHz, G = GHz
    freq_end:   "108M"
    freq_step:  "100k"
    interval_s: 5
    min_power:  -100          # -100 = keep all data; higher = noise gate
    device_index: 0
    is_active: true           # auto-start on launch
```

---

## Dashboard walkthrough

### Band table

The table at the top shows all configured bands, their capture status, and action buttons.

- **▶ Start / ■ Stop** — toggle capture for that band
- **View** — select the band for chart viewing and scroll to charts
- **Edit** — change any parameter (takes effect on next start)
- **Delete** — removes the band and **all its measurements permanently**

Status badges:

| Badge | Meaning |
|---|---|
| `running` | rtl_power is actively scanning |
| `idle` | band exists but capture is not started |
| `stopped` | capture was manually stopped |
| `error` | rtl_power exited with an error — check logs |

### Filters

The sticky filter bar applies to all charts simultaneously.

- **Time range buttons** (15m, 1h, 12h, 1d, 7d, All) — shortcut to set the time window relative to now
- **Freq Min / Freq Max** — zoom into a sub-range of the band
- **Time Start / Time End** — manual datetime range (overrides the range buttons)
- **Activity Threshold slider** (−60 to +30 dBFS) — power level used to classify a reading as "active" in the activity, time-of-day, and signal duration charts. Set it just above the noise floor of the band. Does not filter raw data from the heatmap or spectrum charts.

Click **Clear** to remove all filters and reset the threshold.

> **Note:** `Min Power` in band settings controls what gets saved to the database at capture time. The activity threshold is a separate, analysis-only parameter that applies after the fact. You can set the threshold lower than the band's `min_power` to analyse historical data captured with an older, lower setting.

### Heatmap

The main heatmap shows frequency (Y axis) vs time (X axis) with power encoded as colour (plasma scale: dark = low power, bright yellow = high power).

- **Hover** — tooltip shows exact frequency, time, and power at the cursor
- **Click** — loads a timeseries chart below the heatmap for the clicked frequency
- The heatmap is downsampled to at most 500 frequency bins × 300 time bins for rendering; the full-resolution data remains in the database

### Timeseries

Appears after clicking a frequency in the heatmap. Shows power in dBFS over time for that specific frequency bin.

### Spectrum (mean / peak)

Line chart showing mean power and peak power per frequency bin across the selected time window. Useful for identifying which channels are persistently active vs occasionally active.

### Activity

Percentage of time each frequency bin was above the activity threshold during the selected window. A flat 0% means nothing was ever heard there; 100% means the frequency was always occupied.

### Time-of-day occupancy

A 7 × 24 heatmap (day of week vs hour of day). Each cell shows what percentage of measurements in that day/hour combination exceeded the activity threshold. Colour scale: light yellow = rarely active, dark red = heavily used.

- **Hover** — tooltip shows day name, hour range, and exact activity percentage
- Days with no data show as dark (0%)

Useful for spotting patterns such as weekday business traffic vs weekend activity, or scheduled automated transmissions.

### Signal duration histogram

Distribution of individual signal on-durations in seconds. Helps distinguish short bursts (data packets, PTT key-ups) from long continuous transmissions.

### Fullscreen mode

Every chart has a **⛶** button that appears when hovering over it. Clicking it expands the chart to fill the entire screen. Press **Esc** or click **✕** to return to the normal view.

### Backend status

Click the **⚙ Status** button in the top-right corner to open the status panel. It shows:

- Whether the backend is reachable
- Total database size (MB)
- Total measurement count
- Per-band row count and last capture timestamp
- Live vs Demo mode
- Database file path

---

## Multiple devices

If you have more than one RTL-SDR dongle, each band can be assigned to a specific device via the **Device** field. The device list is populated automatically by probing `rtl_test` when the server starts. Bands on different devices capture independently and simultaneously.

---

## Tips

**Step size and database growth** — a 20 MHz band at 12.5 kHz steps produces ~1600 frequency bins per sweep. At a 5-second interval that is ~19,200 rows per minute per band. Choose the coarsest step that still meets your needs, and enable the cleanup scheduler to keep storage under control.

**min_power filtering** — set `min_power` to a value just above the noise floor (e.g. `2`) to prevent storing background noise readings. Only individual frequency bins above this level are written to the database. This can cut storage by 10–50× on quiet bands at the cost of not recording very weak signals.

**Activity threshold vs min_power** — these are independent controls with different scopes:
- `min_power` (band setting) = gate applied at capture time; data below is never stored
- Activity threshold (UI slider) = applied at analysis time; affects activity %, ToD, and duration charts only

**Cleanup tuning** — for continuous 24/7 monitoring, set `max_time_hrs` and `db_max_size_mb` conservatively. The cleanup job runs every `interval_mins` and re-reads config each cycle, so you can tighten limits without restarting the server.

**Device conflicts** — only one process can hold the RTL-SDR device at a time. If `rtl_power` fails to start with a device-busy error, check for stale processes: `pkill rtl_power`.

**Demo mode** — set `DEMO_MODE=true` to replay pre-recorded data from `demo/seed.db` without any hardware. Useful for development and UI testing.
