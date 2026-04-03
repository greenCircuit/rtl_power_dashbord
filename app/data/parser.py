"""
Parse rtl_power CSV output.

rtl_power CSV row format:
  date, time, hz_low, hz_high, hz_step, num_samples, db0, db1, ..., dbN
"""

import numpy as np
import pandas as pd
from pathlib import Path

from app.config import DATA_DIR


def list_sessions() -> list[dict]:
    """Return metadata for every recorded session (newest first)."""
    sessions = []
    for csv_file in sorted(DATA_DIR.glob("*.csv"), reverse=True):
        size = csv_file.stat().st_size
        sessions.append({
            "id": csv_file.stem,
            "filename": csv_file.name,
            "size_bytes": size,
        })
    return sessions


def parse_rtl_power_csv(filepath: Path) -> pd.DataFrame | None:
    """
    Read an rtl_power CSV and return a tidy DataFrame with columns:
      timestamp (datetime64), frequency_mhz (float64), power_db (float64)
    """
    rows = []
    with open(filepath, errors="replace") as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line:
                continue
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 7:
                continue
            try:
                date_str = parts[0]
                time_str = parts[1]
                hz_low = float(parts[2])
                hz_high = float(parts[3])
                hz_step = float(parts[4])
                db_values = [float(v) for v in parts[6:] if v]
            except (ValueError, IndexError):
                continue

            if not db_values:
                continue

            timestamp = pd.Timestamp(f"{date_str} {time_str}")
            n = len(db_values)
            # rtl_power centres bins between hz_low and hz_high
            freqs_mhz = np.linspace(hz_low, hz_high, n) / 1e6

            for freq, db in zip(freqs_mhz, db_values):
                rows.append((timestamp, freq, db))

    if not rows:
        return None

    df = pd.DataFrame(rows, columns=["timestamp", "frequency_mhz", "power_db"])
    return df


def build_heatmap_arrays(
    df: pd.DataFrame,
    max_time_bins: int = 300,
    max_freq_bins: int = 500,
) -> dict:
    """
    Pivot the tidy DataFrame into 2-D arrays suitable for go.Heatmap.
    Down-samples if the data is very large.

    Returns:
        {
          "x": list of ISO timestamp strings  (time axis),
          "y": list of frequency values in MHz (freq axis),
          "z": 2-D list [freq_index][time_index] of power dB values,
          "freq_min": float,
          "freq_max": float,
          "time_min": str,
          "time_max": str,
        }
    """
    pivot = df.pivot_table(
        index="timestamp",
        columns="frequency_mhz",
        values="power_db",
        aggfunc="mean",
    )

    # Down-sample time axis
    if len(pivot) > max_time_bins:
        step = len(pivot) // max_time_bins
        pivot = pivot.iloc[::step]

    # Down-sample frequency axis
    if pivot.shape[1] > max_freq_bins:
        step = pivot.shape[1] // max_freq_bins
        pivot = pivot.iloc[:, ::step]

    # Fill any gaps with NaN (plotly renders them as blank)
    z = pivot.T.values  # shape: (n_freq, n_time)
    x = [str(t) for t in pivot.index]
    y = list(pivot.columns.astype(float))

    return {
        "x": x,
        "y": y,
        "z": z.tolist(),
        "freq_min": float(df["frequency_mhz"].min()),
        "freq_max": float(df["frequency_mhz"].max()),
        "time_min": str(df["timestamp"].min()),
        "time_max": str(df["timestamp"].max()),
    }


def get_session_data(session_id: str) -> dict | None:
    """High-level helper used by both the API and Dash callbacks."""
    filepath = DATA_DIR / f"{session_id}.csv"
    if not filepath.exists():
        return None
    df = parse_rtl_power_csv(filepath)
    if df is None or df.empty:
        return None
    return build_heatmap_arrays(df)


def get_frequency_stats(session_id: str) -> dict | None:
    """
    Return per-frequency statistics across all time:
      - mean_db: average power per frequency bin
      - peak_db: max power per frequency bin
    """
    filepath = DATA_DIR / f"{session_id}.csv"
    if not filepath.exists():
        return None
    df = parse_rtl_power_csv(filepath)
    if df is None or df.empty:
        return None

    stats = (
        df.groupby("frequency_mhz")["power_db"]
        .agg(mean_db="mean", peak_db="max")
        .reset_index()
        .sort_values("frequency_mhz")
    )
    return {
        "frequency_mhz": stats["frequency_mhz"].tolist(),
        "mean_db": stats["mean_db"].tolist(),
        "peak_db": stats["peak_db"].tolist(),
    }


def get_frequency_activity(session_id: str, threshold_db: float) -> dict | None:
    """
    Return per-frequency activity: % of time power exceeds threshold_db.
    """
    filepath = DATA_DIR / f"{session_id}.csv"
    if not filepath.exists():
        return None
    df = parse_rtl_power_csv(filepath)
    if df is None or df.empty:
        return None

    total_per_freq = df.groupby("frequency_mhz")["power_db"].count()
    active_per_freq = (
        df[df["power_db"] >= threshold_db]
        .groupby("frequency_mhz")["power_db"]
        .count()
    )
    activity_pct = (active_per_freq / total_per_freq * 100).fillna(0).reset_index()
    activity_pct.columns = ["frequency_mhz", "activity_pct"]
    activity_pct = activity_pct.sort_values("frequency_mhz")
    return {
        "frequency_mhz": activity_pct["frequency_mhz"].tolist(),
        "activity_pct": activity_pct["activity_pct"].tolist(),
    }


def get_frequency_timeseries(session_id: str, target_freq_mhz: float) -> dict | None:
    """Return power over time for the frequency bin closest to target_freq_mhz."""
    filepath = DATA_DIR / f"{session_id}.csv"
    if not filepath.exists():
        return None
    df = parse_rtl_power_csv(filepath)
    if df is None or df.empty:
        return None

    # Find closest frequency bin
    closest = df["frequency_mhz"].sub(target_freq_mhz).abs().idxmin()
    actual_freq = df.at[closest, "frequency_mhz"]

    series = (
        df[df["frequency_mhz"] == actual_freq]
        .sort_values("timestamp")[["timestamp", "power_db"]]
    )
    return {
        "frequency_mhz": round(float(actual_freq), 4),
        "timestamps": [str(t) for t in series["timestamp"]],
        "power_db": series["power_db"].tolist(),
    }
