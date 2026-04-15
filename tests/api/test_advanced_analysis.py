"""Tests for app/api/routes/analysis.py — advanced analysis endpoints.

Covers input validation (400s) for all routes that accept threshold, limit, or
granularity query params.  Data-shape / 200 tests are kept minimal here since
the data layer is tested separately; the focus is on the HTTP contract.
"""

import json

import app.data.db as db_module
from tests.conftest import insert_measurements


# ── helpers ───────────────────────────────────────────────────────────────────

BAND_ID = "adv_band"

ROWS = [
    ("2024-01-01 08:00:00", 144.0, -50.0),
    ("2024-01-01 08:00:00", 144.5, -55.0),
    ("2024-01-01 12:00:00", 144.0, -52.0),
    ("2024-01-01 12:00:00", 144.5, -58.0),
]


def _create_band():
    db_module.create_band(
        band_id=BAND_ID, name="Adv Band",
        freq_start="144M", freq_end="145M", freq_step="500k",
        interval_s=10, min_power=2.0, device_index=0,
    )


def _status(client, path, **params):
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"/api/bands/{BAND_ID}/{path}?{qs}" if qs else f"/api/bands/{BAND_ID}/{path}"
    return client.get(url).status_code


# ── /tod-activity ─────────────────────────────────────────────────────────────

class TestTodActivity:

    def test_404_no_data(self, flask_client):
        _create_band()
        assert _status(flask_client, "tod-activity") == 404

    def test_400_threshold_non_numeric(self, flask_client):
        _create_band()
        r = flask_client.get(f"/api/bands/{BAND_ID}/tod-activity?threshold=abc")
        assert r.status_code == 400
        assert "threshold" in json.loads(r.data)["error"]

    def test_400_freq_min_non_numeric(self, flask_client):
        _create_band()
        r = flask_client.get(f"/api/bands/{BAND_ID}/tod-activity?freq_min=bad")
        assert r.status_code == 400


# ── /power-histogram ──────────────────────────────────────────────────────────

class TestPowerHistogram:

    def test_404_no_data(self, flask_client):
        _create_band()
        assert _status(flask_client, "power-histogram") == 404

    def test_400_freq_min_non_numeric(self, flask_client):
        _create_band()
        r = flask_client.get(f"/api/bands/{BAND_ID}/power-histogram?freq_min=bad")
        assert r.status_code == 400

    def test_400_power_min_non_numeric(self, flask_client):
        _create_band()
        r = flask_client.get(f"/api/bands/{BAND_ID}/power-histogram?power_min=loud")
        assert r.status_code == 400


# ── /top-channels ─────────────────────────────────────────────────────────────

class TestTopChannels:

    def test_404_no_data(self, flask_client):
        _create_band()
        assert _status(flask_client, "top-channels") == 404

    def test_400_threshold_non_numeric(self, flask_client):
        _create_band()
        r = flask_client.get(f"/api/bands/{BAND_ID}/top-channels?threshold=abc")
        assert r.status_code == 400
        assert "threshold" in json.loads(r.data)["error"]

    def test_400_limit_non_integer(self, flask_client):
        _create_band()
        r = flask_client.get(f"/api/bands/{BAND_ID}/top-channels?limit=many")
        assert r.status_code == 400
        assert "limit" in json.loads(r.data)["error"]

    def test_400_limit_zero(self, flask_client):
        _create_band()
        r = flask_client.get(f"/api/bands/{BAND_ID}/top-channels?limit=0")
        assert r.status_code == 400

    def test_400_limit_negative(self, flask_client):
        _create_band()
        r = flask_client.get(f"/api/bands/{BAND_ID}/top-channels?limit=-5")
        assert r.status_code == 400

    def test_400_limit_exceeds_maximum(self, flask_client):
        _create_band()
        r = flask_client.get(f"/api/bands/{BAND_ID}/top-channels?limit=101")
        assert r.status_code == 400

    def test_limit_at_boundary_accepted(self, flask_client):
        """limit=1 and limit=100 are the valid boundaries — must not be rejected."""
        _create_band()
        for limit in (1, 100):
            r = flask_client.get(f"/api/bands/{BAND_ID}/top-channels?limit={limit}")
            assert r.status_code in (200, 404), f"limit={limit} gave unexpected {r.status_code}"


# ── /activity-trend ───────────────────────────────────────────────────────────

class TestActivityTrend:

    def test_404_no_data(self, flask_client):
        _create_band()
        assert _status(flask_client, "activity-trend") == 404

    def test_400_threshold_non_numeric(self, flask_client):
        _create_band()
        r = flask_client.get(f"/api/bands/{BAND_ID}/activity-trend?threshold=abc")
        assert r.status_code == 400

    def test_400_invalid_granularity(self, flask_client):
        _create_band()
        r = flask_client.get(f"/api/bands/{BAND_ID}/activity-trend?granularity=1week")
        assert r.status_code == 400
        assert "granularity" in json.loads(r.data)["error"]

    def test_valid_granularities_accepted(self, flask_client):
        _create_band()
        for gran in ("15m", "30m", "1h", "6h", "1d"):
            r = flask_client.get(f"/api/bands/{BAND_ID}/activity-trend?granularity={gran}")
            assert r.status_code in (200, 404), f"granularity={gran!r} rejected unexpectedly"


# ── /signal-durations ─────────────────────────────────────────────────────────

class TestSignalDurations:

    def test_404_no_data(self, flask_client):
        _create_band()
        assert _status(flask_client, "signal-durations") == 404

    def test_400_threshold_non_numeric(self, flask_client):
        _create_band()
        r = flask_client.get(f"/api/bands/{BAND_ID}/signal-durations?threshold=abc")
        assert r.status_code == 400
        assert "threshold" in json.loads(r.data)["error"]


# ── /analysis/crossband-timeline ─────────────────────────────────────────────

class TestCrossbandTimeline:

    def test_404_no_bands(self, flask_client):
        r = flask_client.get("/api/analysis/crossband-timeline")
        assert r.status_code == 404

    def test_400_threshold_non_numeric(self, flask_client):
        r = flask_client.get("/api/analysis/crossband-timeline?threshold=abc")
        assert r.status_code == 400
        assert "threshold" in json.loads(r.data)["error"]

    def test_400_freq_min_non_numeric(self, flask_client):
        r = flask_client.get("/api/analysis/crossband-timeline?freq_min=bad")
        assert r.status_code == 400


# ── /analysis/overview ────────────────────────────────────────────────────────

class TestBandsOverview:

    def test_200_empty_bands(self, flask_client):
        r = flask_client.get("/api/analysis/overview")
        assert r.status_code == 200
        assert json.loads(r.data)["bands"] == []

    def test_400_threshold_non_numeric(self, flask_client):
        r = flask_client.get("/api/analysis/overview?threshold=abc")
        assert r.status_code == 400
        assert "threshold" in json.loads(r.data)["error"]

    def test_200_returns_band_entries(self, flask_client):
        _create_band()
        insert_measurements(BAND_ID, ROWS)
        data = json.loads(flask_client.get("/api/analysis/overview").data)
        ids = [b["id"] for b in data["bands"]]
        assert BAND_ID in ids

    def test_200_activity_pct_in_range(self, flask_client):
        _create_band()
        insert_measurements(BAND_ID, ROWS)
        data = json.loads(flask_client.get("/api/analysis/overview").data)
        for b in data["bands"]:
            assert 0.0 <= b["activity_pct"] <= 100.0
