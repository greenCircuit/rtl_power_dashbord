# RTL Power Dashboard — User Guide

## Requirements

- An RTL-SDR compatible USB dongle (RTL2832U chipset)
- `rtl-sdr` package installed on the host (`sudo apt install rtl-sdr` on Debian/Ubuntu)
- Python 3.11+ with dependencies from `requirements.txt`, **or** Docker

---

## Getting started

### Option A — Run locally

```bash
pip install -r requirements.txt
python run.py
```

Open `http://localhost:8050` in a browser.

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

## Configuring bands

Bands can be managed two ways: via the web UI, or by editing `bands.yaml` before first startup.

### Via the UI

Click **+ Add Band** at the top of the dashboard. Fill in:

| Field | Description | Example |
|---|---|---|
| Name | Label shown in the dashboard | `GMRS` |
| Freq Start | Lower edge of the range | `462.5` MHz |
| Freq End | Upper edge of the range | `462.8` MHz |
| Step | Frequency resolution per bin | `12.5` kHz |
| Interval | Seconds to spend scanning this band per cycle | `5` |
| Min Power | Discard sweeps where peak power is below this (dBFS) | `-100` (keep everything), `2` (only active signals) |
| Device | Which RTL-SDR dongle to use | `Device 0` |

Hit **Save**. The band appears in the table. Click **▶ Start** to begin capturing.

### Via bands.yaml

`bands.yaml` is loaded on startup and seeds bands that don't already exist in the database. Editing it after bands have been created has no effect — use the UI to modify existing bands.

```yaml
bands:
  - id: fm-broadcast         # unique identifier
    name: FM Broadcast
    freq_start: "87.5M"      # units: k = kHz, M = MHz, G = GHz
    freq_end:   "108M"
    freq_step:  "100k"
    interval_s: 5
    min_power:  -100          # -100 = keep all data
    device_index: 0
    is_active: true           # auto-start on launch
```

---

## Dashboard walkthrough

### Band table

The table at the top shows all configured bands, their capture status, and action buttons.

- **▶ Start / ■ Stop** — toggle capture for that band
- **View** — select the band for chart viewing below
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

- **Time range buttons** (15m, 1h, 12h, 1d, 7d, All) — shortcut to set the time window to the last N minutes/hours/days relative to now
- **Freq Min / Freq Max** — zoom into a sub-range of the band
- **Time Start / Time End** — manual datetime range (overrides the range buttons)
- **Min Power slider** — hide bins below this power level in the heatmap and activity charts
- **Activity Threshold slider** — power level used to classify a bin as "active" for the activity percentage charts

Click **Clear** to remove all filters.

### Heatmap

The main heatmap shows frequency (Y axis) vs time (X axis) with power encoded as colour (plasma scale, dark = low, bright yellow = high).

- **Hover** — tooltip shows exact frequency, time, and power at the cursor
- **Click** — loads a timeseries chart below the heatmap for the clicked frequency

The heatmap is downsampled to at most 500 frequency bins × 300 time bins for rendering. The full resolution data remains in the database.

### Timeseries

Appears after clicking a frequency in the heatmap. Shows power in dBFS over time for that specific frequency bin.

### Spectrum (mean / peak)

A line chart showing mean power and peak power per frequency bin across the selected time window. Useful for identifying which channels are persistently active vs occasionally active.

### Activity

Percentage of time each frequency bin was above the activity threshold during the selected window. A flat 0% means nothing was ever heard there; 100% means the frequency was always occupied.

### Time-of-day occupancy

A 7 × 24 heatmap (day of week vs hour of day). Shows at what times of day and on which days each frequency is typically in use. Useful for spotting patterns like weekday business traffic vs weekend activity.

### Signal duration histogram

Distribution of individual signal durations in seconds. Helps distinguish short bursts (data packets, key-ups) from long continuous transmissions.

---

## Multiple devices

If you have more than one RTL-SDR dongle, each band can be assigned to a specific device via the **Device** field. The device list is populated automatically by probing `rtl_test` when the server starts. Bands on different devices capture independently and simultaneously.

---

## Tips

**Step size and database growth** — a 20 MHz band at 12.5 kHz steps produces ~1600 frequency bins per sweep. At a 5-second interval that is ~19,200 rows per minute, ~1.1 million rows per hour. Choose the coarsest step that still meets your needs to keep storage manageable.

**min_power filtering** — setting `min_power` to a value above the noise floor (e.g. `2`) prevents storing background noise rows. This can cut storage by 10–50x on quiet bands at the cost of not seeing very weak signals.

**Deleting old data** — there is no built-in data retention policy. Delete a band and recreate it to wipe its measurements, or delete rows directly in the SQLite database (`data/rtl_power.db`).

**Device conflicts** — only one process can hold the RTL-SDR device at a time. If `rtl_power` fails to start with a device-busy error, check for stale processes: `pkill rtl_power`.
