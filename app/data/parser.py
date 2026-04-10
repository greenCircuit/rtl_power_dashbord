"""
Public query interface for band data.
Legacy CSV migration helpers are kept at the bottom.
"""

import math
import numpy as np
import pandas as pd
from pathlib import Path

from app.data import db


# ── Float sanitization ────────────────────────────────────────────────────────

def _safe_float(v, default=None):
    """Return v as a finite float, or default for None / NaN / Inf values.

    Keeps JSON output well-formed: Python's json encoder serialises float('nan')
    as the bare token ``NaN`` which is not valid JSON.  Any non-finite value is
    replaced with *default* (``None`` → JSON ``null``) instead.
    """
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
    # pivot_table fills missing time/freq combinations with NaN; replace with
    # None so the output is valid JSON (NaN is not a JSON token).
    z_json = [
        [_safe_float(v) for v in row]
        for row in z.tolist()
    ]
    return {
        "x": [str(t) for t in pivot.index],
        "y": list(pivot.columns.astype(float)),
        "z": z_json,
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
            continue  # skip rows with non-finite aggregates
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
            continue  # skip non-finite power readings
        timestamps.append(r["timestamp"])
        powers.append(p)
    if not timestamps:
        return None
    return {
        "frequency_mhz": round(actual_freq, 4),
        "timestamps":    timestamps,
        "power_db":      powers,
    }


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


def migrate_csv_sessions(csv_dir: Path) -> None:
    """Import legacy CSV files into the sessions/measurements tables. Safe to call repeatedly."""
    import sqlite3
    from app.config import DB_PATH

    existing = {s["id"] for s in db.list_sessions()}
    for csv_file in sorted(csv_dir.glob("*.csv")):
        session_id = csv_file.stem
        if session_id in existing:
            continue
        df = _parse_rtl_power_csv(csv_file)
        if df is None or df.empty:
            continue
        db.create_session(session_id, session_id)
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        rows = list(df.itertuples(index=False, name=None))
        conn.executemany(
            "INSERT INTO measurements (session_id, timestamp, frequency_mhz, power_db)"
            " VALUES (?, ?, ?, ?)",
            [(session_id, ts, freq, pwr) for ts, freq, pwr in rows],
        )
        conn.commit()
        conn.close()
        print(f"[migration] imported {csv_file.name} ({len(rows)} rows)")
