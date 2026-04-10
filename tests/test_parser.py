"""Unit tests for app/data/parser.py"""

import pandas as pd
import pytest

from app.data.parser import _parse_csv_row, build_heatmap_arrays


# ── _parse_csv_row ────────────────────────────────────────────────────────────

def _parts(line: str) -> list:
    return [p.strip() for p in line.split(",")]


def test_parse_csv_row_valid():
    line = "2024-01-15, 12:00:00, 144000000, 146000000, 25000, 1, -55.0, -60.0, -65.0"
    result = _parse_csv_row(_parts(line))
    assert result is not None
    timestamp, hz_low, hz_high, db_values = result
    assert timestamp == "2024-01-15 12:00:00"
    assert hz_low == 144_000_000.0
    assert hz_high == 146_000_000.0
    assert db_values == [-55.0, -60.0, -65.0]


def test_parse_csv_row_too_few_parts():
    assert _parse_csv_row(["2024-01-15", "12:00:00", "144000000"]) is None


def test_parse_csv_row_bad_float():
    parts = ["2024-01-15", "12:00:00", "NOTAFREQ", "146000000", "25000", "1", "-55.0"]
    assert _parse_csv_row(parts) is None


def test_parse_csv_row_empty_db_values():
    parts = ["2024-01-15", "12:00:00", "144000000", "146000000", "25000", "1", "", ""]
    assert _parse_csv_row(parts) is None


def test_parse_csv_row_timestamp_concatenated():
    parts = ["2024-06-01", "09:30:00", "462500000", "462800000", "12500", "1", "-42.0"]
    result = _parse_csv_row(parts)
    assert result[0] == "2024-06-01 09:30:00"


# ── build_heatmap_arrays ──────────────────────────────────────────────────────

def _make_df(n_times=5, n_freqs=4):
    import numpy as np
    times = [f"2024-01-01 12:00:{i:02d}" for i in range(n_times)]
    freqs = [144.0 + i * 0.5 for i in range(n_freqs)]
    rows = []
    for t in times:
        for f in freqs:
            rows.append({"timestamp": pd.Timestamp(t),
                         "frequency_mhz": f,
                         "power_db": -60.0})
    return pd.DataFrame(rows)


def test_build_heatmap_arrays_keys():
    df = _make_df()
    result = build_heatmap_arrays(df)
    assert set(result.keys()) == {"x", "y", "z", "freq_min", "freq_max", "time_min", "time_max"}


def test_build_heatmap_arrays_dimensions():
    df = _make_df(n_times=5, n_freqs=4)
    result = build_heatmap_arrays(df)
    # z shape: (n_freqs, n_times)
    assert len(result["z"]) == 4
    assert len(result["z"][0]) == 5


def test_build_heatmap_arrays_freq_range():
    df = _make_df(n_freqs=4)
    result = build_heatmap_arrays(df)
    assert result["freq_min"] == pytest.approx(144.0)
    assert result["freq_max"] == pytest.approx(145.5)


def test_build_heatmap_arrays_time_strings():
    df = _make_df(n_times=3)
    result = build_heatmap_arrays(df)
    assert len(result["x"]) == 3
    assert all(isinstance(t, str) for t in result["x"])


def test_build_heatmap_arrays_downsamples_time(monkeypatch):
    # When rows > max_time_bins it should downsample
    df = _make_df(n_times=20, n_freqs=2)
    result = build_heatmap_arrays(df, max_time_bins=5)
    assert len(result["x"]) <= 5


def test_build_heatmap_arrays_downsamples_freq(monkeypatch):
    df = _make_df(n_times=2, n_freqs=20)
    result = build_heatmap_arrays(df, max_freq_bins=5)
    assert len(result["y"]) <= 5


def test_build_heatmap_arrays_z_no_nan_in_dense_data():
    """Dense data (every freq at every time) must produce no None in z."""
    df = _make_df(n_times=3, n_freqs=3)
    result = build_heatmap_arrays(df)
    for row in result["z"]:
        assert all(v is not None for v in row)


def test_build_heatmap_arrays_z_nulls_for_sparse_data():
    """Sparse pivot table (missing time/freq combos) must emit None, not NaN."""
    rows = [
        {"timestamp": pd.Timestamp("2024-01-01 12:00:00"), "frequency_mhz": 144.0, "power_db": -55.0},
        {"timestamp": pd.Timestamp("2024-01-01 12:00:10"), "frequency_mhz": 145.0, "power_db": -60.0},
    ]
    df = pd.DataFrame(rows)
    result = build_heatmap_arrays(df)
    all_values = [v for row in result["z"] for v in row]
    assert None in all_values, "sparse data must produce None cells"
    for v in all_values:
        assert v is None or (isinstance(v, float) and not (v != v)), \
            f"z contains float NaN: {v!r}"


def test_build_heatmap_arrays_z_valid_json():
    """Output must serialise to valid JSON (no NaN/Inf tokens)."""
    import json
    rows = [
        {"timestamp": pd.Timestamp("2024-01-01 12:00:00"), "frequency_mhz": 144.0, "power_db": -55.0},
        {"timestamp": pd.Timestamp("2024-01-01 12:00:10"), "frequency_mhz": 145.0, "power_db": -60.0},
    ]
    result = build_heatmap_arrays(pd.DataFrame(rows))
    # allow_nan=False raises ValueError if NaN/Inf would be emitted
    serialised = json.dumps(result, allow_nan=False)
    recovered = json.loads(serialised)
    assert recovered["z"] is not None
