# RTL Power Dashboard — User Guide

## Requirements

- A USB SDR receiver compatible with `rtl_power` (RTL-SDR, Nooelec, AirSpy, etc.)
- `rtl-sdr` tools installed on the host (`sudo apt install rtl-sdr` on Debian/Ubuntu)
- Python 3.11+ with dependencies from `requirements.txt`, **or** Docker

---

## Getting started

### Option A — Docker (recommended)

Build the image:

```bash
docker build -t localhost/rtl-app:latest .
```

Run:

```bash
docker compose up
```

Open `http://localhost:8050` in a browser. The SQLite database is persisted in `./data` on the host. USB devices are passed through automatically.

### Option B — Run locally

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

### Option C — Docker development sandbox

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
  analytics_poll_interval_s: 60   # time-of-day, signal durations, top channels
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
| Device | Which SDR device to use | shown by index and name |

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
| `running` | `rtl_power` is actively scanning |
| `idle` | band exists but capture is not started |
| `stopped` | capture was manually stopped |
| `error` | `rtl_power` exited with an error — check logs |

### Band selector

Below the band table, select which band's data to view in the charts. Once a band is selected, the header shows **Capturing [band name]** to confirm which band's data is being displayed.

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
- When the dataset is large, the heatmap automatically aggregates into up to 300 time buckets in SQL before sending data to the browser — zooming into a short time window always shows full resolution

### Timeseries

Appears after clicking a frequency in the heatmap. Shows power in dBFS over time for that specific frequency bin.

### Spectrum (mean / peak)

Line chart showing mean power and peak power per frequency bin across the selected time window. Useful for identifying which channels are persistently active vs occasionally active.

### Activity

Percentage of time each frequency bin was above the activity threshold during the selected window. A flat 0% means nothing was ever heard there; 100% means the frequency was always occupied.

### Time-of-day occupancy

A 7 × 24 heatmap (day of week vs hour of day). Each cell shows what percentage of measurements in that day/hour combination exceeded the activity threshold.

- **Hover** — tooltip shows day name, hour range, and exact activity percentage
- Days with no data show as dark (0%)

Useful for spotting patterns such as weekday business traffic vs weekend activity, or scheduled automated transmissions.

### Signal duration histogram

Distribution of individual signal on-durations in seconds. Helps distinguish short bursts (data packets, PTT key-ups) from long continuous transmissions.

### Activity trend

Line chart of overall band activity percentage over time, with selectable granularity (5m, 15m, 1h, 6h, 1d). Useful for seeing how busy a band is over days or weeks.

### Top active channels

Horizontal bar chart of the most active frequency bins, sorted by activity percentage. Quickly shows which specific channels within a band are most used.

### Power distribution

Histogram of all power readings across the selected window. Useful for calibrating the activity threshold — the noise floor appears as a cluster of low-power readings; signals appear as a tail or secondary peak.

### Fullscreen mode

Every chart has a **⛶** button that appears when hovering over it. Clicking it expands the chart to fill the entire screen. Press **Esc** or click **✕** to return to the normal view.

### Backend status

Click the **⚙ Status** button in the top-right corner to open the status panel. It shows:

- Whether the backend is reachable
- Total database size (MB)
- Total measurement count
- Live vs Demo mode
- Database file path
- Available SDR devices (index and name as reported by the driver)
- Per-band row count, last capture timestamp, and how long ago that was

---

## Multiple devices

If you have more than one SDR device connected, each band can be assigned to a specific device via the **Device** field. The device list is probed automatically on server startup using `rtl_test` and shown in the band modal and the status panel. Bands on different devices capture independently and simultaneously.

---

## Tips

**Step size and database growth** — a 20 MHz band at 12.5 kHz steps produces ~1600 frequency bins per sweep. At a 5-second interval that is ~19,200 rows per minute per band. Choose the coarsest step that still meets your needs, and enable the cleanup scheduler to keep storage under control.

**min_power filtering** — set `min_power` to a value just above the noise floor (e.g. `2`) to prevent storing background noise readings. Only individual frequency bins above this level are written to the database. This can cut storage by 10–50× on quiet bands at the cost of not recording very weak signals.

**Activity threshold vs min_power** — these are independent controls with different scopes:
- `min_power` (band setting) = gate applied at capture time; data below is never stored
- Activity threshold (UI slider) = applied at analysis time; affects activity %, ToD, and duration charts only

**Cleanup tuning** — for continuous 24/7 monitoring, set `max_time_hrs` and `db_max_size_mb` conservatively. The cleanup job runs every `interval_mins` and re-reads config each cycle, so you can tighten limits without restarting the server.

**Device conflicts** — only one process can hold an SDR device at a time. If `rtl_power` fails to start with a device-busy error, check for stale processes: `pkill rtl_power`.

**Demo mode** — set `DEMO_MODE=true` to replay pre-recorded data from `demo/seed.db` without any hardware. Useful for development and UI testing.
