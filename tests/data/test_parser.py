"""Unit tests for app/data/parser.py"""

import json

import pandas as pd
import pytest

from app.data.parser import build_heatmap_arrays


# ── build_heatmap_arrays ──────────────────────────────────────────────────────

def _make_df(n_times=5, n_freqs=4):
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
    rows = [
        {"timestamp": pd.Timestamp("2024-01-01 12:00:00"), "frequency_mhz": 144.0, "power_db": -55.0},
        {"timestamp": pd.Timestamp("2024-01-01 12:00:10"), "frequency_mhz": 145.0, "power_db": -60.0},
    ]
    result = build_heatmap_arrays(pd.DataFrame(rows))
    # allow_nan=False raises ValueError if NaN/Inf would be emitted
    serialised = json.dumps(result, allow_nan=False)
    recovered = json.loads(serialised)
    assert recovered["z"] is not None
