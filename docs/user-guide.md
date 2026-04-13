# RTL Power Dashboard — User Guide

This guide walks you through using the dashboard for the first time — from opening the app to understanding what the charts are telling you.

For installation and setup see the [README](../README.md). For configuration file reference see [overview.md](overview.md).

---

## What this app does

The dashboard continuously scans frequency bands using a USB SDR receiver and records what power levels it sees at each frequency. You can then explore that data: which frequencies are active, when they're active, how long signals last, and how busy a band is over time.

It is a **spectrum recorder and analyser**, not a receiver or decoder. It tells you that something is transmitting on 462.550 MHz and how often — not what it's saying.

---

## First launch

When you open the app for the first time you'll see an empty band table and no charts. That's expected — you need to tell the app which frequency ranges to monitor.

The **⚙ Status** button in the top-right corner is a good first stop. It shows whether the backend is running, which SDR devices the app has detected, and the current database size. If your device isn't listed there, check that `rtl-sdr` tools are installed and the device is plugged in before proceeding.

---

## Setting up your first band

A **band** is a frequency range you want to monitor. Click **+ Add Band** to create one.

### Choosing a frequency range

Enter the start and end frequency of the range you're interested in. Use the unit suffix that makes sense for the frequency — `M` for MHz, `k` for kHz, `G` for GHz. For example, the GMRS radio range would be `462.5M` to `462.8M`.

Keep the range tight at first. A 300 MHz range scanned at fine resolution will fill the database much faster than a 1 MHz range, and the charts will be harder to read.

### Step size

The step size controls how many frequency bins fit inside your range. A smaller step gives finer frequency resolution but produces more data and more processing.

As a starting point:
- Narrow bands (< 5 MHz) — `12.5k` or `25k`
- Medium bands (5–50 MHz) — `25k` or `100k`
- Wide survey scans (> 50 MHz) — `100k` or coarser

### Interval

How many seconds the app spends scanning this band each cycle. Lower values mean more frequent sweeps and more data. `5` to `30` seconds is a reasonable starting range.

If you have multiple bands on the same device, each gets `interval_s` seconds per cycle in rotation — so two bands at 10 seconds each means each band is swept every 20 seconds.

### Min Power

This is a noise gate applied at capture time. Any reading below this power level is discarded and never stored. It is measured in dBFS (decibels relative to full scale — negative numbers).

- `-100` — keep everything including noise. Good when first exploring a band to see the noise floor.
- `-2` to `5` — discard noise, keep only signals above the ambient floor. Good for long-running monitoring to keep storage under control.

If you set this too high you'll miss weak signals. If you set it too low your database fills quickly with noise. You can always adjust it later via **Edit** — the change applies from the next sweep onward; historical data is unaffected.

### Device

If you have more than one SDR device connected, choose which one scans this band. The dropdown shows each device by its index and hardware name as detected by the driver.

### Saving and starting

Click **Save**. The band appears in the table with status `idle`. Click **▶ Start** to begin capturing.

The status changes to `running` within a few seconds. If it shows `error` instead, open **⚙ Status** and check the logs — the most common cause is another process holding the device.

---

## Viewing data

### Selecting a band

Use the **Viewing band** dropdown below the band table to pick which band's data the charts display. The header shows **Capturing [band name]** to confirm your selection.

Charts update automatically every 30 seconds (or 60 seconds for the analysis charts). You don't need to refresh the page.

### How long until I see data?

After starting capture, wait one full interval cycle. If you set `interval_s` to 10, you'll see your first data within about 10–15 seconds. With `min_power` set conservatively high on a quiet band it's possible the first few sweeps produce no stored readings — lower `min_power` temporarily if you're not seeing anything.

---

## Understanding the charts

### Heatmap

The heatmap is the main view. It shows:
- **Y axis** — frequency (bottom = low end of your band, top = high end)
- **X axis** — time (left = oldest, right = most recent)
- **Colour** — power level (dark/purple = weak or no signal, yellow/white = strong signal)

A horizontal bright streak means something was transmitting on that frequency continuously. A vertical column means a brief moment when many frequencies lit up at once. Individual bright dots are short transmissions.

**Hover** over any point to see the exact frequency, time, and power reading in a tooltip.

**Click** on any frequency to load a timeseries chart for that frequency directly below the heatmap.

### Timeseries

Appears after you click a frequency on the heatmap. Shows power level over time for that one frequency bin. Useful for seeing the exact timing and power envelope of a signal.

### Spectrum — Mean & Peak Power

A line chart of power vs frequency across your selected time window. Three lines:

- **Mean power** — average power seen at each frequency over the window. Frequencies with persistent signals sit high; quiet frequencies sit near the noise floor.
- **Peak (window)** — the strongest reading seen at each frequency within the selected time range. A channel that transmitted only briefly will still show up as a peak.
- **Peak (all time)** — the strongest reading ever recorded at each frequency, regardless of the time filter. Useful as a reference to see if current conditions are unusual.

### Activity

Shows what percentage of the time each frequency was above the **activity threshold**. A bar at 0% means nothing was ever heard there. A bar at 80% means that frequency was active for 80% of all sweeps.

This chart responds to the **Activity Threshold** slider in the filter bar. Adjust the slider to set what counts as "active" — set it just above the noise floor to ignore background noise.

### Activity Trend

Shows how busy the whole band has been over time as a single percentage line. Use the granularity buttons (`5m`, `15m`, `1h`, `6h`, `1d`) to zoom in or out on the time axis.

Useful for spotting patterns — does activity spike at certain times of day? Is the band getting busier over weeks?

### Time-of-Day Occupancy

A 7×24 grid showing day of week vs hour of day. Each cell's colour represents how active the band was during that day/hour combination on average, from dark (0% activity) to bright red/orange (heavily used).

Hover over any cell to see the exact percentage.

This chart is best read after a few days of data. It's particularly good at revealing scheduled or routine activity — automated systems that transmit at fixed times, business hours traffic, weekend vs weekday patterns.

### Top Active Channels

A ranked list of the individual frequencies that were most active. Sorted by activity percentage, with mean power shown alongside.

If you have a busy band and want to know which specific channels are actually being used, this is the chart to look at.

### Signal Duration Histogram

Shows how long individual transmissions last. Short bars on the left mean brief bursts; bars further right mean longer continuous transmissions.

A band full of very short spikes (< 1 second) is likely digital data bursts. Longer durations suggest voice or continuous carriers. A mix of both is common on shared bands.

### Power Distribution

A histogram of all power readings in the selected window. The noise floor shows up as a tall cluster of low-power readings on the left. Actual signals appear as a flatter tail or second peak to the right.

Use this to set your **Activity Threshold** — find the gap between the noise cluster and the signal region, and place the threshold there.

---

## Filtering data

The filter bar below the band selector applies to all charts at the same time.

### Time range

The quick-select buttons (**15m**, **1h**, **12h**, **1d**, **7d**, **All**) set a rolling window ending at the current time. Use the **Time Start** and **Time End** fields to pin an exact range instead — useful for going back to investigate a specific event you noticed on the heatmap.

Zooming into a short time window always shows full detail. When looking at a long window (days or weeks) the heatmap automatically groups data into buckets for display — the underlying data in the database is unchanged.

### Frequency range

**Freq Min** and **Freq Max** zoom into a sub-range of your band. Useful when your band is wide and you want to focus the heatmap and spectrum on a specific portion.

### Activity Threshold

The slider (−60 to +30 dBFS) controls what the app considers "active" for the activity-related charts. It does not affect the heatmap or spectrum — those always show raw power.

A good starting point: open the **Power Distribution** chart with the time filter set to **All**, find the right edge of the noise floor cluster, and set the threshold just above that value.

### Clearing filters

Click **Clear** to remove all filters and return the threshold to its default.

---

## Common workflows

### "I want to know what's active on a band"

1. Add the band, start capture, wait a few minutes.
2. Select the band and look at the heatmap — bright horizontal streaks show active frequencies.
3. Switch to **Activity** to see percentages per frequency.
4. Check **Top Active Channels** to get a ranked list.
5. Click a busy frequency on the heatmap to load its timeseries.

### "I want to see when a frequency is used"

1. Let the band run for at least a day.
2. Open **Time-of-Day Occupancy** — cells with high percentages tell you when that activity happens.
3. Use **Activity Trend** with `1h` granularity to see the pattern over recent days.

### "I want to investigate a signal I noticed"

1. On the heatmap, identify the time and frequency of the event.
2. Use **Time Start** / **Time End** to zoom into the window around it.
3. Click the frequency on the heatmap to see the timeseries — exact power and timing.
4. Check the **Signal Duration** chart to see how long the transmission lasted.

### "I want to run long-term unattended monitoring"

1. Set `min_power` to just above the noise floor — this keeps only meaningful readings and dramatically reduces storage.
2. In `config.yaml`, set `max_time_hrs` and `db_max_size_mb` based on how much history you want and how much disk you have. The cleanup scheduler enforces these automatically.
3. Mark the band as `is_active: true` in `config.yaml` so it auto-starts when the server reboots.
4. Come back later and use **7d** or **All** time range to see long-term patterns in the time-of-day and activity trend charts.

---

## Troubleshooting

**Band shows `error` status**
The most common cause is another process holding the SDR device. Run `pkill rtl_power` on the host to clear any stale processes, then start the band again.

**No data appearing after starting a band**
Check that `min_power` isn't set too high. Try setting it to `-100` temporarily to capture everything — if data appears, your noise floor is above your previous `min_power` setting.

**Charts show "No data yet" even after waiting**
Make sure you have a band selected in the **Viewing band** dropdown. Also confirm the band is in `running` state in the band table.

**The device isn't listed in Status**
The app probes devices at startup using `rtl_test`. If you plugged in the device after starting the server, restart the server. Also verify `rtl-sdr` tools are installed: `rtl_test` should run from the command line without error.

**Database growing too fast**
Reduce `min_power` to filter out more noise, increase `freq_step` to reduce the number of bins per sweep, increase `interval_s` to sweep less often, or tighten `max_time_hrs` in `config.yaml`.
