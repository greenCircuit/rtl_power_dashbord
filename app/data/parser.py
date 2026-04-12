"""
High-level query interface — converts raw DB rows into chart-ready dicts.
"""

import math
from datetime import datetime

import numpy as np
import pandas as pd
from pathlib import Path

from app.data import db


# ── Float sanitization ────────────────────────────────────────────────────────

def _safe_float(v, default=None):
    """Return v as a finite float, or *default* for None / NaN / Inf values."""
    if v is None:
        return default
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return f if math.isfinite(f) else default


# ── Heatmap builder ───────────────────────────────────────────────────────────

def build_heatmap_arrays(
    df: pd.DataFrame,
    max_time_bins: int = 300,
    max_freq_bins: int = 500,
) -> dict:
    pivot = df.pivot_table(
        index="timestamp",
        columns="frequency_mhz",
        values="power_db",
        aggfunc="mean",
    )
    if len(pivot) > max_time_bins:
        step = len(pivot) // max_time_bins
        pivot = pivot.iloc[::step]
    if pivot.shape[1] > max_freq_bins:
        step = pivot.shape[1] // max_freq_bins
        pivot = pivot.iloc[:, ::step]

    z = pivot.T.values
    z_json = [
        [_safe_float(v) for v in row]
        for row in z.tolist()
    ]
    return {
        "x":        [str(t) for t in pivot.index],
        "y":        list(pivot.columns.astype(float)),
        "z":        z_json,
        "freq_min": float(df["frequency_mhz"].min()),
        "freq_max": float(df["frequency_mhz"].max()),
        "time_min": str(df["timestamp"].min()),
        "time_max": str(df["timestamp"].max()),
    }


# ── Band query functions ──────────────────────────────────────────────────────

def get_band_data(band_id: str, filters: dict | None = None) -> dict | None:
    rows = db.fetch_band_measurements(band_id, filters)
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=["timestamp", "frequency_mhz", "power_db"])
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return build_heatmap_arrays(df)


def get_band_stats(band_id: str, filters: dict | None = None) -> dict | None:
    rows = db.fetch_band_stats(band_id, filters)
    if not rows:
        return None
    freqs, means, peaks = [], [], []
    for r in rows:
        f = _safe_float(r["frequency_mhz"])
        m = _safe_float(r["mean_db"])
        p = _safe_float(r["peak_db"])
        if f is None or m is None or p is None:
            continue
        freqs.append(f)
        means.append(m)
        peaks.append(p)
    if not freqs:
        return None
    return {"frequency_mhz": freqs, "mean_db": means, "peak_db": peaks}


def get_band_activity(band_id: str, threshold_db: float,
                      filters: dict | None = None) -> dict | None:
    rows = db.fetch_band_activity(band_id, threshold_db, filters)
    if not rows:
        return None
    freqs, pcts = [], []
    for r in rows:
        f = _safe_float(r["frequency_mhz"])
        if f is None:
            continue
        pct = round(r["active"] / r["total"] * 100, 2) if r["total"] else 0.0
        freqs.append(f)
        pcts.append(pct)
    if not freqs:
        return None
    return {"frequency_mhz": freqs, "activity_pct": pcts}


def get_band_timeseries(band_id: str, target_freq_mhz: float,
                        filters: dict | None = None) -> dict | None:
    actual_freq = db.fetch_band_closest_freq(band_id, target_freq_mhz)
    if actual_freq is None:
        return None
    rows = db.fetch_band_timeseries(band_id, actual_freq, filters)
    if not rows:
        return None
    timestamps, powers = [], []
    for r in rows:
        p = _safe_float(r["power_db"])
        if p is None:
            continue
        timestamps.append(r["timestamp"])
        powers.append(p)
    if not timestamps:
        return None
    return {
        "frequency_mhz": round(actual_freq, 4),
        "timestamps":    timestamps,
        "power_db":      powers,
    }


def get_band_tod_activity(band_id: str, threshold_db: float,
                          filters: dict | None = None) -> dict | None:
    """Return time-of-day occupancy as a 7×24 grid.

    Frontend expects ``{ z: number[][], x: number[], y: string[] }`` where
    z[day][hour] is activity percentage (0–100).
    Days with no data stay at 0 so the grid is always fully populated.
    """
    rows = db.fetch_band_tod_activity(band_id, threshold_db, filters)
    if not rows:
        return None

    # Build 7×24 grid indexed by [dow][hour]
    grid = [[0.0] * 24 for _ in range(7)]
    for r in rows:
        d, h = r["dow"], r["hour"]
        if 0 <= d <= 6 and 0 <= h <= 23 and r["total"]:
            grid[d][h] = round(r["active"] / r["total"] * 100, 2)

    return {
        "z": grid,
        "x": list(range(24)),
        "y": ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
    }


def get_all_bands_activity_timeline(
    band_ids: list[str],
    threshold_db: float,
    filters: dict | None = None,
) -> dict | None:
    """Return per-band hourly activity timeline.

    Returns ``{band_id: {"buckets": [...], "pcts": [...]}}`` or ``None``.
    """
    result = {}
    for bid in band_ids:
        rows = db.fetch_band_activity_timeline(bid, threshold_db, filters)
        if not rows:
            continue
        buckets, pcts = [], []
        for r in rows:
            buckets.append(r["bucket"])
            pct = round(r["active"] / r["total"] * 100, 2) if r["total"] else 0.0
            pcts.append(pct)
        result[bid] = {"buckets": buckets, "pcts": pcts}
    return result if result else None


def get_band_signal_durations(band_id: str, threshold_db: float,
                               filters: dict | None = None) -> dict | None:
    """Return signal on-durations in seconds by scanning per-frequency time series."""
    rows = db.fetch_band_signal_raw(band_id, threshold_db, filters)
    if not rows:
        return None

    # Group by frequency, find contiguous above-threshold runs
    by_freq: dict[float, list] = {}
    for r in rows:
        by_freq.setdefault(r["frequency_mhz"], []).append(
            (r["timestamp"], r["power_db"])
        )

    durations: list[float] = []
    for freq_rows in by_freq.values():
        freq_rows.sort(key=lambda x: x[0])
        run_start: datetime | None = None
        prev_ts:   datetime | None = None
        for ts_str, pwr in freq_rows:
            try:
                ts = datetime.fromisoformat(str(ts_str).replace(" ", "T"))
            except ValueError:
                continue
            active = pwr >= threshold_db
            if active:
                if run_start is None:
                    run_start = ts
                prev_ts = ts
            else:
                if run_start is not None and prev_ts is not None:
                    dur = (prev_ts - run_start).total_seconds()
                    if dur > 0:
                        durations.append(dur)
                run_start = None
                prev_ts   = None
        # flush trailing run
        if run_start is not None and prev_ts is not None:
            dur = (prev_ts - run_start).total_seconds()
            if dur > 0:
                durations.append(dur)

    return {"durations_s": durations} if durations else None


# ── Legacy CSV migration ──────────────────────────────────────────────────────

def _parse_csv_row(parts: list) -> tuple | None:
    """Parse pre-split CSV parts into (timestamp, hz_low, hz_high, db_values) or None."""
    if len(parts) < 7:
        return None
    try:
        timestamp = f"{parts[0]} {parts[1]}"
        hz_low    = float(parts[2])
        hz_high   = float(parts[3])
        db_values = [float(v) for v in parts[6:] if v]
    except (ValueError, IndexError):
        return None
    if not db_values:
        return None
    return timestamp, hz_low, hz_high, db_values


def _parse_rtl_power_csv(filepath: Path) -> pd.DataFrame | None:
    rows = []
    with open(filepath, errors="replace") as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line:
                continue
            parsed = _parse_csv_row([p.strip() for p in line.split(",")])
            if parsed is None:
                continue
            timestamp, hz_low, hz_high, db_values = parsed
            freqs_mhz = np.linspace(hz_low, hz_high, len(db_values)) / 1e6
            for freq, db_val in zip(freqs_mhz, db_values):
                rows.append((timestamp, float(freq), float(db_val)))
    if not rows:
        return None
    return pd.DataFrame(rows, columns=["timestamp", "frequency_mhz", "power_db"])
