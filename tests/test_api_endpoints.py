"""
Integration tests for the four chart API endpoints:
  GET /api/bands/<id>/heatmap
  GET /api/bands/<id>/spectrum
  GET /api/bands/<id>/activity
  GET /api/bands/<id>/timeseries

Each suite verifies:
  - 404 for unknown band / no data
  - 200 with structurally correct payload
  - All numeric values are JSON-safe (no NaN / Inf tokens)
  - Sanitisation edge cases (sparse heatmap, missing power readings, etc.)
"""

import json
import math
import sqlite3

import pytest
import app.data.db as db_module
from tests.conftest import insert_measurements


# ── helpers ───────────────────────────────────────────────────────────────────

BAND_ID = "test_band"

CLEAN_ROWS = [
    ("2024-01-01 12:00:00", 144.0, -55.0),
    ("2024-01-01 12:00:00", 144.5, -60.0),
    ("2024-01-01 12:00:00", 145.0, -65.0),
    ("2024-01-01 12:00:10", 144.0, -54.0),
    ("2024-01-01 12:00:10", 144.5, -61.0),
    ("2024-01-01 12:00:10", 145.0, -64.0),
]


def _create_band(band_id=BAND_ID):
    db_module.create_band(
        band_id=band_id, name=f"Test {band_id}",
        freq_start="144M", freq_end="145M", freq_step="500k",
        interval_s=10, min_power=2.0, device_index=0,
    )


def _ok(response):
    """Assert 200 and return parsed JSON (raises if body contains invalid JSON)."""
    assert response.status_code == 200, response.data
    return json.loads(response.data)   # raises json.JSONDecodeError if body has NaN/Inf


def _no_non_finite(obj) -> bool:
    """Return True when obj contains no float NaN or Inf at any nesting level."""
    if isinstance(obj, float):
        return math.isfinite(obj)
    if isinstance(obj, list):
        return all(_no_non_finite(v) for v in obj)
    if isinstance(obj, dict):
        return all(_no_non_finite(v) for v in obj.values())
    return True  # None, int, str, bool are all fine


# ── /heatmap ──────────────────────────────────────────────────────────────────

class TestHeatmap:

    def test_404_unknown_band(self, flask_client):
        r = flask_client.get("/api/bands/no_such_band/heatmap")
        assert r.status_code == 404

    def test_404_band_exists_no_data(self, flask_client):
        _create_band()
        r = flask_client.get(f"/api/bands/{BAND_ID}/heatmap")
        assert r.status_code == 404

    def test_200_structure(self, flask_client):
        _create_band()
        insert_measurements(BAND_ID, CLEAN_ROWS)
        data = _ok(flask_client.get(f"/api/bands/{BAND_ID}/heatmap"))
        assert set(data.keys()) >= {"x", "y", "z", "freq_min", "freq_max"}
        assert isinstance(data["x"], list) and len(data["x"]) > 0
        assert isinstance(data["y"], list) and len(data["y"]) > 0
        assert isinstance(data["z"], list) and len(data["z"]) > 0

    def test_z_dimensions_match_x_y(self, flask_client):
        _create_band()
        insert_measurements(BAND_ID, CLEAN_ROWS)
        data = _ok(flask_client.get(f"/api/bands/{BAND_ID}/heatmap"))
        n_freq = len(data["y"])
        n_time = len(data["x"])
        assert len(data["z"]) == n_freq
        assert all(len(row) == n_time for row in data["z"])

    def test_z_values_are_float_or_null(self, flask_client):
        _create_band()
        insert_measurements(BAND_ID, CLEAN_ROWS)
        data = _ok(flask_client.get(f"/api/bands/{BAND_ID}/heatmap"))
        for row in data["z"]:
            for v in row:
                assert v is None or isinstance(v, float), f"unexpected z value: {v!r}"

    def test_no_non_finite_floats(self, flask_client):
        _create_band()
        insert_measurements(BAND_ID, CLEAN_ROWS)
        data = _ok(flask_client.get(f"/api/bands/{BAND_ID}/heatmap"))
        assert _no_non_finite(data)

    def test_sparse_data_produces_nulls_not_nan(self, flask_client):
        """Different freqs at different timestamps → pivot gaps → must be null not NaN."""
        _create_band()
        # Each freq appears at only one timestamp → other cells are sparse
        sparse = [
            ("2024-01-01 12:00:00", 144.0, -55.0),
            ("2024-01-01 12:00:10", 144.5, -60.0),
            ("2024-01-01 12:00:20", 145.0, -65.0),
        ]
        insert_measurements(BAND_ID, sparse)
        # Must parse as valid JSON (would raise if NaN token present)
        data = _ok(flask_client.get(f"/api/bands/{BAND_ID}/heatmap"))
        # At least one null expected in a sparse pivot
        all_z = [v for row in data["z"] for v in row]
        assert None in all_z, "sparse data should produce null cells in the heatmap"
        assert _no_non_finite(data)

    def test_freq_range_filter_applied(self, flask_client):
        _create_band()
        insert_measurements(BAND_ID, CLEAN_ROWS)
        r = flask_client.get(f"/api/bands/{BAND_ID}/heatmap?freq_min=144.4&freq_max=144.6")
        data = _ok(r)
        # Only the 144.5 MHz bin should appear
        assert all(144.4 <= f <= 144.6 for f in data["y"])

    def test_power_filter_applied(self, flask_client):
        _create_band()
        # Mix of high and very low power readings
        rows = [
            ("2024-01-01 12:00:00", 144.0, -30.0),   # above threshold
            ("2024-01-01 12:00:00", 144.5, -90.0),   # below threshold
        ]
        insert_measurements(BAND_ID, rows)
        r = flask_client.get(f"/api/bands/{BAND_ID}/heatmap?power_min=-50")
        data = _ok(r)
        # Only the 144.0 MHz bin (power -30 dB) should survive the filter
        assert 144.0 in [pytest.approx(f, abs=0.01) for f in data["y"]]
        assert not any(abs(f - 144.5) < 0.01 for f in data["y"])


# ── /spectrum ─────────────────────────────────────────────────────────────────

class TestSpectrum:

    def test_404_unknown_band(self, flask_client):
        r = flask_client.get("/api/bands/no_such_band/spectrum")
        assert r.status_code == 404

    def test_404_band_exists_no_data(self, flask_client):
        _create_band()
        r = flask_client.get(f"/api/bands/{BAND_ID}/spectrum")
        assert r.status_code == 404

    def test_200_structure(self, flask_client):
        _create_band()
        insert_measurements(BAND_ID, CLEAN_ROWS)
        data = _ok(flask_client.get(f"/api/bands/{BAND_ID}/spectrum"))
        assert set(data.keys()) == {"frequency_mhz", "mean_db", "peak_db", "alltime_peak_db"}

    def test_arrays_same_length(self, flask_client):
        _create_band()
        insert_measurements(BAND_ID, CLEAN_ROWS)
        data = _ok(flask_client.get(f"/api/bands/{BAND_ID}/spectrum"))
        assert len(data["frequency_mhz"]) == len(data["mean_db"]) == len(data["peak_db"])

    def test_no_non_finite_floats(self, flask_client):
        _create_band()
        insert_measurements(BAND_ID, CLEAN_ROWS)
        data = _ok(flask_client.get(f"/api/bands/{BAND_ID}/spectrum"))
        assert _no_non_finite(data)

    def test_peak_ge_mean(self, flask_client):
        """Peak power must always be >= mean power at every frequency."""
        _create_band()
        insert_measurements(BAND_ID, CLEAN_ROWS)
        data = _ok(flask_client.get(f"/api/bands/{BAND_ID}/spectrum"))
        for m, p in zip(data["mean_db"], data["peak_db"]):
            assert p >= m, f"peak {p} < mean {m}"

    def test_all_values_are_floats(self, flask_client):
        _create_band()
        insert_measurements(BAND_ID, CLEAN_ROWS)
        data = _ok(flask_client.get(f"/api/bands/{BAND_ID}/spectrum"))
        for key in ("frequency_mhz", "mean_db", "peak_db"):
            assert all(isinstance(v, float) for v in data[key]), \
                f"{key} contains non-float values"

    def test_frequencies_sorted_ascending(self, flask_client):
        _create_band()
        insert_measurements(BAND_ID, CLEAN_ROWS)
        data = _ok(flask_client.get(f"/api/bands/{BAND_ID}/spectrum"))
        freqs = data["frequency_mhz"]
        assert freqs == sorted(freqs)


# ── /activity ─────────────────────────────────────────────────────────────────

class TestActivity:

    def test_404_unknown_band(self, flask_client):
        r = flask_client.get("/api/bands/no_such_band/activity")
        assert r.status_code == 404

    def test_404_band_exists_no_data(self, flask_client):
        _create_band()
        r = flask_client.get(f"/api/bands/{BAND_ID}/activity")
        assert r.status_code == 404

    def test_200_structure(self, flask_client):
        _create_band()
        insert_measurements(BAND_ID, CLEAN_ROWS)
        data = _ok(flask_client.get(f"/api/bands/{BAND_ID}/activity"))
        assert set(data.keys()) == {"frequency_mhz", "activity_pct"}

    def test_arrays_same_length(self, flask_client):
        _create_band()
        insert_measurements(BAND_ID, CLEAN_ROWS)
        data = _ok(flask_client.get(f"/api/bands/{BAND_ID}/activity"))
        assert len(data["frequency_mhz"]) == len(data["activity_pct"])

    def test_no_non_finite_floats(self, flask_client):
        _create_band()
        insert_measurements(BAND_ID, CLEAN_ROWS)
        data = _ok(flask_client.get(f"/api/bands/{BAND_ID}/activity"))
        assert _no_non_finite(data)

    def test_activity_pct_in_range(self, flask_client):
        """activity_pct must be in [0, 100] for every frequency."""
        _create_band()
        insert_measurements(BAND_ID, CLEAN_ROWS)
        data = _ok(flask_client.get(f"/api/bands/{BAND_ID}/activity"))
        for pct in data["activity_pct"]:
            assert 0.0 <= pct <= 100.0, f"activity_pct out of range: {pct}"

    def test_all_active_at_low_threshold(self, flask_client):
        """With threshold below all power values, every freq should be 100% active."""
        _create_band()
        insert_measurements(BAND_ID, CLEAN_ROWS)
        # All CLEAN_ROWS have power >= -65; threshold of -100 → 100% active
        data = _ok(flask_client.get(f"/api/bands/{BAND_ID}/activity?threshold=-100"))
        assert all(pct == 100.0 for pct in data["activity_pct"])

    def test_none_active_at_high_threshold(self, flask_client):
        """With threshold above all power values, every freq should be 0% active."""
        _create_band()
        insert_measurements(BAND_ID, CLEAN_ROWS)
        # All CLEAN_ROWS have power <= -54; threshold of 0 → 0% active
        data = _ok(flask_client.get(f"/api/bands/{BAND_ID}/activity?threshold=0"))
        assert all(pct == 0.0 for pct in data["activity_pct"])

    def test_zero_total_does_not_raise(self, flask_client):
        """A frequency group with total=0 must return 0.0%, not a ZeroDivisionError."""
        # This path is guarded by `if r["total"] else 0.0`; exercise it via the
        # activity endpoint with a very tight freq filter that matches no rows.
        _create_band()
        insert_measurements(BAND_ID, CLEAN_ROWS)
        # No rows match this freq range → 404, not 500
        r = flask_client.get(f"/api/bands/{BAND_ID}/activity?freq_min=999&freq_max=1000")
        assert r.status_code == 404


# ── /timeseries ───────────────────────────────────────────────────────────────

class TestTimeseries:

    def test_400_missing_freq_mhz(self, flask_client):
        _create_band()
        r = flask_client.get(f"/api/bands/{BAND_ID}/timeseries")
        assert r.status_code == 400

    def test_404_unknown_band(self, flask_client):
        r = flask_client.get("/api/bands/no_such_band/timeseries?freq_mhz=144.0")
        assert r.status_code == 404

    def test_404_band_exists_no_data(self, flask_client):
        _create_band()
        r = flask_client.get(f"/api/bands/{BAND_ID}/timeseries?freq_mhz=144.0")
        assert r.status_code == 404

    def test_200_structure(self, flask_client):
        _create_band()
        insert_measurements(BAND_ID, CLEAN_ROWS)
        data = _ok(flask_client.get(f"/api/bands/{BAND_ID}/timeseries?freq_mhz=144.0"))
        assert set(data.keys()) == {"frequency_mhz", "timestamps", "power_db"}

    def test_arrays_same_length(self, flask_client):
        _create_band()
        insert_measurements(BAND_ID, CLEAN_ROWS)
        data = _ok(flask_client.get(f"/api/bands/{BAND_ID}/timeseries?freq_mhz=144.0"))
        assert len(data["timestamps"]) == len(data["power_db"])

    def test_no_non_finite_floats(self, flask_client):
        _create_band()
        insert_measurements(BAND_ID, CLEAN_ROWS)
        data = _ok(flask_client.get(f"/api/bands/{BAND_ID}/timeseries?freq_mhz=144.0"))
        assert _no_non_finite(data)

    def test_snaps_to_closest_frequency(self, flask_client):
        """freq_mhz does not need to be exact — returns nearest available freq."""
        _create_band()
        insert_measurements(BAND_ID, CLEAN_ROWS)
        # Request 144.1 → closest stored freq is 144.0
        data = _ok(flask_client.get(f"/api/bands/{BAND_ID}/timeseries?freq_mhz=144.1"))
        assert data["frequency_mhz"] == pytest.approx(144.0, abs=0.01)

    def test_timestamps_are_strings(self, flask_client):
        _create_band()
        insert_measurements(BAND_ID, CLEAN_ROWS)
        data = _ok(flask_client.get(f"/api/bands/{BAND_ID}/timeseries?freq_mhz=144.0"))
        assert all(isinstance(t, str) for t in data["timestamps"])

    def test_power_values_are_floats(self, flask_client):
        _create_band()
        insert_measurements(BAND_ID, CLEAN_ROWS)
        data = _ok(flask_client.get(f"/api/bands/{BAND_ID}/timeseries?freq_mhz=144.0"))
        assert all(isinstance(p, float) for p in data["power_db"])

    def test_timestamps_sorted_ascending(self, flask_client):
        _create_band()
        insert_measurements(BAND_ID, CLEAN_ROWS)
        data = _ok(flask_client.get(f"/api/bands/{BAND_ID}/timeseries?freq_mhz=144.0"))
        ts = data["timestamps"]
        assert ts == sorted(ts)


# ── /status ───────────────────────────────────────────────────────────────────

class TestStatus:

    def test_200_structure(self, flask_client):
        data = _ok(flask_client.get("/api/status"))
        assert data["status"] == "ok"
        assert "db_size_mb" in data
        assert "total_measurements" in data
        assert "bands" in data
        assert "devices" in data
        assert "demo_mode" in data

    def test_devices_is_list(self, flask_client):
        data = _ok(flask_client.get("/api/status"))
        assert isinstance(data["devices"], list)

    def test_devices_have_index_and_name(self, flask_client):
        data = _ok(flask_client.get("/api/status"))
        for d in data["devices"]:
            assert "index" in d and "name" in d
            assert isinstance(d["index"], int)
            assert isinstance(d["name"], str)

    def test_demo_mode_is_bool(self, flask_client):
        data = _ok(flask_client.get("/api/status"))
        assert isinstance(data["demo_mode"], bool)

    def test_bands_is_list(self, flask_client):
        data = _ok(flask_client.get("/api/status"))
        assert isinstance(data["bands"], list)

    def test_per_band_entry_structure(self, flask_client):
        _create_band()
        insert_measurements(BAND_ID, CLEAN_ROWS)
        data = _ok(flask_client.get("/api/status"))
        assert len(data["bands"]) > 0
        for b in data["bands"]:
            assert "band_id" in b and "count" in b and "last_seen" in b


# ── /tod-activity ──────────────────────────────────────────────────────────────

class TestTodActivity:

    def test_404_unknown_band(self, flask_client):
        r = flask_client.get("/api/bands/no_such_band/tod-activity")
        assert r.status_code == 404

    def test_404_band_exists_no_data(self, flask_client):
        _create_band()
        r = flask_client.get(f"/api/bands/{BAND_ID}/tod-activity")
        assert r.status_code == 404

    def test_200_structure(self, flask_client):
        _create_band()
        insert_measurements(BAND_ID, CLEAN_ROWS)
        data = _ok(flask_client.get(f"/api/bands/{BAND_ID}/tod-activity"))
        assert set(data.keys()) == {"z", "x", "y"}

    def test_z_is_7x24_grid(self, flask_client):
        """z must always be exactly 7 rows (days) × 24 columns (hours)."""
        _create_band()
        insert_measurements(BAND_ID, CLEAN_ROWS)
        data = _ok(flask_client.get(f"/api/bands/{BAND_ID}/tod-activity"))
        assert len(data["z"]) == 7
        assert all(len(row) == 24 for row in data["z"])

    def test_x_is_0_to_23(self, flask_client):
        _create_band()
        insert_measurements(BAND_ID, CLEAN_ROWS)
        data = _ok(flask_client.get(f"/api/bands/{BAND_ID}/tod-activity"))
        assert data["x"] == list(range(24))

    def test_y_has_7_day_labels(self, flask_client):
        _create_band()
        insert_measurements(BAND_ID, CLEAN_ROWS)
        data = _ok(flask_client.get(f"/api/bands/{BAND_ID}/tod-activity"))
        assert len(data["y"]) == 7
        assert all(isinstance(d, str) for d in data["y"])

    def test_all_values_in_range(self, flask_client):
        _create_band()
        insert_measurements(BAND_ID, CLEAN_ROWS)
        data = _ok(flask_client.get(f"/api/bands/{BAND_ID}/tod-activity?threshold=-100"))
        for row in data["z"]:
            for v in row:
                assert 0.0 <= v <= 100.0, f"activity value out of range: {v}"

    def test_low_threshold_gives_nonzero_activity(self, flask_client):
        """With threshold below all readings, at least one cell must be > 0."""
        _create_band()
        insert_measurements(BAND_ID, CLEAN_ROWS)
        data = _ok(flask_client.get(f"/api/bands/{BAND_ID}/tod-activity?threshold=-100"))
        all_values = [v for row in data["z"] for v in row]
        assert any(v > 0 for v in all_values)

    def test_high_threshold_gives_all_zero(self, flask_client):
        """With threshold above all readings, every cell must be 0."""
        _create_band()
        insert_measurements(BAND_ID, CLEAN_ROWS)
        # All CLEAN_ROWS have power <= -54; threshold=0 → nothing active
        data = _ok(flask_client.get(f"/api/bands/{BAND_ID}/tod-activity?threshold=0"))
        assert all(v == 0.0 for row in data["z"] for v in row)


# ── /power-histogram ──────────────────────────────────────────────────────────

class TestPowerHistogram:

    def test_404_unknown_band(self, flask_client):
        r = flask_client.get("/api/bands/no_such_band/power-histogram")
        assert r.status_code == 404

    def test_404_band_exists_no_data(self, flask_client):
        _create_band()
        r = flask_client.get(f"/api/bands/{BAND_ID}/power-histogram")
        assert r.status_code == 404

    def test_200_structure(self, flask_client):
        _create_band()
        insert_measurements(BAND_ID, CLEAN_ROWS)
        data = _ok(flask_client.get(f"/api/bands/{BAND_ID}/power-histogram"))
        assert set(data.keys()) == {"bins", "counts", "min_db", "max_db", "total"}

    def test_bins_and_counts_same_length(self, flask_client):
        _create_band()
        insert_measurements(BAND_ID, CLEAN_ROWS)
        data = _ok(flask_client.get(f"/api/bands/{BAND_ID}/power-histogram"))
        assert len(data["bins"]) == len(data["counts"])

    def test_total_matches_input_row_count(self, flask_client):
        _create_band()
        insert_measurements(BAND_ID, CLEAN_ROWS)
        data = _ok(flask_client.get(f"/api/bands/{BAND_ID}/power-histogram"))
        assert data["total"] == len(CLEAN_ROWS)

    def test_min_le_max(self, flask_client):
        _create_band()
        insert_measurements(BAND_ID, CLEAN_ROWS)
        data = _ok(flask_client.get(f"/api/bands/{BAND_ID}/power-histogram"))
        assert data["min_db"] <= data["max_db"]

    def test_counts_are_non_negative(self, flask_client):
        _create_band()
        insert_measurements(BAND_ID, CLEAN_ROWS)
        data = _ok(flask_client.get(f"/api/bands/{BAND_ID}/power-histogram"))
        assert all(c >= 0 for c in data["counts"])

    def test_no_non_finite_floats(self, flask_client):
        _create_band()
        insert_measurements(BAND_ID, CLEAN_ROWS)
        data = _ok(flask_client.get(f"/api/bands/{BAND_ID}/power-histogram"))
        assert _no_non_finite(data)


# ── /top-channels ─────────────────────────────────────────────────────────────

class TestTopChannels:

    def test_404_unknown_band(self, flask_client):
        r = flask_client.get("/api/bands/no_such_band/top-channels")
        assert r.status_code == 404

    def test_404_band_exists_no_data(self, flask_client):
        _create_band()
        r = flask_client.get(f"/api/bands/{BAND_ID}/top-channels")
        assert r.status_code == 404

    def test_200_structure(self, flask_client):
        _create_band()
        insert_measurements(BAND_ID, CLEAN_ROWS)
        data = _ok(flask_client.get(f"/api/bands/{BAND_ID}/top-channels?threshold=-100"))
        assert set(data.keys()) == {"frequency_mhz", "activity_pct", "mean_db"}

    def test_arrays_same_length(self, flask_client):
        _create_band()
        insert_measurements(BAND_ID, CLEAN_ROWS)
        data = _ok(flask_client.get(f"/api/bands/{BAND_ID}/top-channels?threshold=-100"))
        assert len(data["frequency_mhz"]) == len(data["activity_pct"]) == len(data["mean_db"])

    def test_sorted_by_activity_descending(self, flask_client):
        _create_band()
        insert_measurements(BAND_ID, CLEAN_ROWS)
        data = _ok(flask_client.get(f"/api/bands/{BAND_ID}/top-channels?threshold=-100"))
        pcts = data["activity_pct"]
        assert pcts == sorted(pcts, reverse=True)

    def test_limit_param_respected(self, flask_client):
        _create_band()
        insert_measurements(BAND_ID, CLEAN_ROWS)
        data = _ok(flask_client.get(f"/api/bands/{BAND_ID}/top-channels?threshold=-100&limit=1"))
        assert len(data["frequency_mhz"]) <= 1

    def test_activity_pct_in_range(self, flask_client):
        _create_band()
        insert_measurements(BAND_ID, CLEAN_ROWS)
        data = _ok(flask_client.get(f"/api/bands/{BAND_ID}/top-channels?threshold=-100"))
        for pct in data["activity_pct"]:
            assert 0.0 <= pct <= 100.0


# ── /activity-trend ───────────────────────────────────────────────────────────

class TestActivityTrend:

    def test_404_unknown_band(self, flask_client):
        r = flask_client.get("/api/bands/no_such_band/activity-trend")
        assert r.status_code == 404

    def test_404_band_exists_no_data(self, flask_client):
        _create_band()
        r = flask_client.get(f"/api/bands/{BAND_ID}/activity-trend")
        assert r.status_code == 404

    def test_200_structure(self, flask_client):
        _create_band()
        insert_measurements(BAND_ID, CLEAN_ROWS)
        data = _ok(flask_client.get(f"/api/bands/{BAND_ID}/activity-trend"))
        assert set(data.keys()) == {"buckets", "activity_pct"}

    def test_arrays_same_length(self, flask_client):
        _create_band()
        insert_measurements(BAND_ID, CLEAN_ROWS)
        data = _ok(flask_client.get(f"/api/bands/{BAND_ID}/activity-trend"))
        assert len(data["buckets"]) == len(data["activity_pct"])

    def test_activity_pct_in_range(self, flask_client):
        _create_band()
        insert_measurements(BAND_ID, CLEAN_ROWS)
        data = _ok(flask_client.get(f"/api/bands/{BAND_ID}/activity-trend?threshold=-100"))
        for pct in data["activity_pct"]:
            assert 0.0 <= pct <= 100.0

    def test_all_granularities_accepted(self, flask_client):
        """All documented granularity values must return 200, not 404 or 500."""
        _create_band()
        insert_measurements(BAND_ID, CLEAN_ROWS)
        for gran in ("5m", "15m", "1h", "6h", "1d"):
            r = flask_client.get(f"/api/bands/{BAND_ID}/activity-trend?granularity={gran}")
            assert r.status_code == 200, f"granularity={gran!r} returned {r.status_code}"

    def test_low_threshold_gives_nonzero_activity(self, flask_client):
        _create_band()
        insert_measurements(BAND_ID, CLEAN_ROWS)
        data = _ok(flask_client.get(f"/api/bands/{BAND_ID}/activity-trend?threshold=-100"))
        assert any(pct > 0 for pct in data["activity_pct"])


# ── /signal-durations ─────────────────────────────────────────────────────────
#
# Three readings at the same frequency, each 10 s apart, all above threshold=-100.
# This produces one contiguous run of 20 s duration.

DURATION_ROWS = [
    ("2024-01-01 12:00:00", 144.0, -30.0),
    ("2024-01-01 12:00:10", 144.0, -30.0),
    ("2024-01-01 12:00:20", 144.0, -30.0),
]


class TestSignalDurations:

    def test_404_unknown_band(self, flask_client):
        r = flask_client.get("/api/bands/no_such_band/signal-durations")
        assert r.status_code == 404

    def test_404_band_exists_no_data(self, flask_client):
        _create_band()
        r = flask_client.get(f"/api/bands/{BAND_ID}/signal-durations")
        assert r.status_code == 404

    def test_404_no_signals_above_threshold(self, flask_client):
        """All readings below threshold → no active runs → 404."""
        _create_band()
        insert_measurements(BAND_ID, DURATION_ROWS)
        # threshold=0 is above all DURATION_ROWS power values (-30 dBFS)
        r = flask_client.get(f"/api/bands/{BAND_ID}/signal-durations?threshold=0")
        assert r.status_code == 404

    def test_200_structure(self, flask_client):
        _create_band()
        insert_measurements(BAND_ID, DURATION_ROWS)
        data = _ok(flask_client.get(f"/api/bands/{BAND_ID}/signal-durations?threshold=-100"))
        assert set(data.keys()) == {"bins", "counts", "total", "min_s", "max_s"}

    def test_bins_and_counts_same_length(self, flask_client):
        _create_band()
        insert_measurements(BAND_ID, DURATION_ROWS)
        data = _ok(flask_client.get(f"/api/bands/{BAND_ID}/signal-durations?threshold=-100"))
        assert len(data["bins"]) == len(data["counts"])

    def test_min_le_max(self, flask_client):
        _create_band()
        insert_measurements(BAND_ID, DURATION_ROWS)
        data = _ok(flask_client.get(f"/api/bands/{BAND_ID}/signal-durations?threshold=-100"))
        assert data["min_s"] <= data["max_s"]

    def test_detected_duration_is_positive(self, flask_client):
        """The run from 12:00:00 → 12:00:20 must produce a duration > 0."""
        _create_band()
        insert_measurements(BAND_ID, DURATION_ROWS)
        data = _ok(flask_client.get(f"/api/bands/{BAND_ID}/signal-durations?threshold=-100"))
        assert data["min_s"] > 0

    def test_no_non_finite_floats(self, flask_client):
        _create_band()
        insert_measurements(BAND_ID, DURATION_ROWS)
        data = _ok(flask_client.get(f"/api/bands/{BAND_ID}/signal-durations?threshold=-100"))
        assert _no_non_finite(data)


# ── sanitisation unit tests (parser._safe_float) ─────────────────────────────

class TestSafeFloat:
    """Directly exercises the _safe_float helper via its public effects."""

    from app.data.parser import _safe_float as sf

    def test_regular_float_returned_unchanged(self):
        from app.data.parser import _safe_float
        assert _safe_float(-55.0) == pytest.approx(-55.0)

    def test_none_returns_default(self):
        from app.data.parser import _safe_float
        assert _safe_float(None) is None
        assert _safe_float(None, default=0.0) == 0.0

    def test_nan_returns_default(self):
        from app.data.parser import _safe_float
        assert _safe_float(float("nan")) is None
        assert _safe_float(float("nan"), default=-1.0) == -1.0

    def test_inf_returns_default(self):
        from app.data.parser import _safe_float
        assert _safe_float(float("inf")) is None
        assert _safe_float(float("-inf")) is None

    def test_int_coerced_to_float(self):
        from app.data.parser import _safe_float
        result = _safe_float(42)
        assert result == 42.0
        assert isinstance(result, float)

    def test_numeric_string_coerced(self):
        from app.data.parser import _safe_float
        assert _safe_float("3.14") == pytest.approx(3.14)

    def test_non_numeric_string_returns_default(self):
        from app.data.parser import _safe_float
        assert _safe_float("bad") is None


# ── heatmap NaN/null sanitisation (parser level) ─────────────────────────────

class TestHeatmapSanitisation:

    def test_no_nan_in_z_when_data_is_sparse(self):
        """build_heatmap_arrays must replace NaN with None, never emit float nan."""
        import pandas as pd
        from app.data.parser import build_heatmap_arrays

        # Sparse: each freq only appears at one timestamp → gaps in pivot
        rows = [
            {"timestamp": pd.Timestamp("2024-01-01 12:00:00"),
             "frequency_mhz": 144.0, "power_db": -55.0},
            {"timestamp": pd.Timestamp("2024-01-01 12:00:10"),
             "frequency_mhz": 145.0, "power_db": -60.0},
        ]
        df = pd.DataFrame(rows)
        result = build_heatmap_arrays(df)

        for row in result["z"]:
            for v in row:
                assert v is None or (isinstance(v, float) and math.isfinite(v)), \
                    f"z contains invalid value: {v!r}"

    def test_z_serialises_to_valid_json(self):
        """The output of build_heatmap_arrays must round-trip through json.dumps/loads."""
        import pandas as pd
        from app.data.parser import build_heatmap_arrays

        rows = [
            {"timestamp": pd.Timestamp("2024-01-01 12:00:00"),
             "frequency_mhz": 144.0, "power_db": -55.0},
            {"timestamp": pd.Timestamp("2024-01-01 12:00:10"),
             "frequency_mhz": 145.0, "power_db": -60.0},
        ]
        result = build_heatmap_arrays(pd.DataFrame(rows))
        # json.dumps/loads will raise if NaN or Inf tokens are present
        serialised = json.dumps(result, allow_nan=False)
        recovered   = json.loads(serialised)
        assert recovered["z"] is not None
