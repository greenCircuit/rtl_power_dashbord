"""Tests for app/api/routes/bands.py — CRUD routes and input validation."""

import json
from unittest.mock import MagicMock, patch

import pytest
import app.data.db as db_module


# ── helpers ───────────────────────────────────────────────────────────────────

VALID_BODY = {
    "name":         "Test Band",
    "freq_start":   "144M",
    "freq_end":     "146M",
    "freq_step":    "25k",
    "interval_s":   10,
    "min_power":    2.0,
    "device_index": 0,
    "is_active":    False,
}


def _post(client, body):
    return client.post(
        "/api/bands",
        data=json.dumps(body),
        content_type="application/json",
    )


def _put(client, band_id, body):
    return client.put(
        f"/api/bands/{band_id}",
        data=json.dumps(body),
        content_type="application/json",
    )


def _create_band(client, overrides=None):
    """POST a valid band and return its id."""
    body = {**VALID_BODY, **(overrides or {})}
    r = _post(client, body)
    assert r.status_code == 201, r.data
    return json.loads(r.data)["id"]


# Patch band_manager for all tests in this module so no real capture runs.
@pytest.fixture(autouse=True)
def mock_band_manager():
    mgr = MagicMock()
    mgr.all_statuses.return_value = {}
    mgr.get_status.return_value = "idle"
    mgr.get_error.return_value = None
    with patch("app.api.routes.bands.band_manager", mgr):
        yield mgr


# ── GET /api/bands ────────────────────────────────────────────────────────────

class TestListBands:

    def test_200_empty(self, flask_client):
        r = flask_client.get("/api/bands")
        assert r.status_code == 200
        assert json.loads(r.data)["bands"] == []

    def test_200_returns_created_bands(self, flask_client):
        _create_band(flask_client, {"name": "Alpha"})
        _create_band(flask_client, {"name": "Beta"})
        data = json.loads(flask_client.get("/api/bands").data)
        names = [b["name"] for b in data["bands"]]
        assert "Alpha" in names
        assert "Beta" in names

    def test_200_includes_status_field(self, flask_client):
        _create_band(flask_client)
        data = json.loads(flask_client.get("/api/bands").data)
        assert all("status" in b for b in data["bands"])


# ── POST /api/bands ───────────────────────────────────────────────────────────

class TestCreateBand:

    def test_201_valid(self, flask_client):
        r = _post(flask_client, VALID_BODY)
        assert r.status_code == 201
        assert "id" in json.loads(r.data)

    def test_400_missing_name(self, flask_client):
        body = {k: v for k, v in VALID_BODY.items() if k != "name"}
        assert _post(flask_client, body).status_code == 400

    def test_400_missing_freq_start(self, flask_client):
        body = {k: v for k, v in VALID_BODY.items() if k != "freq_start"}
        assert _post(flask_client, body).status_code == 400

    def test_400_missing_freq_end(self, flask_client):
        body = {k: v for k, v in VALID_BODY.items() if k != "freq_end"}
        assert _post(flask_client, body).status_code == 400

    def test_400_missing_freq_step(self, flask_client):
        body = {k: v for k, v in VALID_BODY.items() if k != "freq_step"}
        assert _post(flask_client, body).status_code == 400

    def test_400_interval_s_not_integer(self, flask_client):
        r = _post(flask_client, {**VALID_BODY, "interval_s": "abc"})
        assert r.status_code == 400
        assert "interval_s" in json.loads(r.data)["error"]

    def test_400_interval_s_zero(self, flask_client):
        r = _post(flask_client, {**VALID_BODY, "interval_s": 0})
        assert r.status_code == 400
        assert "interval_s" in json.loads(r.data)["error"]

    def test_400_interval_s_negative(self, flask_client):
        r = _post(flask_client, {**VALID_BODY, "interval_s": -5})
        assert r.status_code == 400

    def test_400_min_power_not_number(self, flask_client):
        r = _post(flask_client, {**VALID_BODY, "min_power": "strong"})
        assert r.status_code == 400
        assert "min_power" in json.loads(r.data)["error"]

    def test_400_device_index_not_integer(self, flask_client):
        r = _post(flask_client, {**VALID_BODY, "device_index": "first"})
        assert r.status_code == 400
        assert "device_index" in json.loads(r.data)["error"]

    def test_400_device_index_negative(self, flask_client):
        r = _post(flask_client, {**VALID_BODY, "device_index": -1})
        assert r.status_code == 400

    def test_400_is_active_bad_string(self, flask_client):
        r = _post(flask_client, {**VALID_BODY, "is_active": "yes_please"})
        assert r.status_code == 400
        assert "is_active" in json.loads(r.data)["error"]

    def test_is_active_string_true_accepted(self, flask_client):
        r = _post(flask_client, {**VALID_BODY, "is_active": "true"})
        assert r.status_code == 201

    def test_is_active_string_false_accepted(self, flask_client):
        r = _post(flask_client, {**VALID_BODY, "is_active": "false"})
        assert r.status_code == 201

    def test_201_defaults_applied_when_optional_fields_omitted(self, flask_client):
        body = {k: v for k, v in VALID_BODY.items()
                if k in ("name", "freq_start", "freq_end", "freq_step")}
        r = _post(flask_client, body)
        assert r.status_code == 201
        band_id = json.loads(r.data)["id"]
        band = db_module.get_band(band_id)
        assert band["interval_s"] == 10
        assert band["min_power"] == 2.0
        assert band["device_index"] == 0


# ── PUT /api/bands/<id> ───────────────────────────────────────────────────────

class TestUpdateBand:

    def test_404_unknown_band(self, flask_client):
        r = _put(flask_client, "no_such_band", {"name": "New"})
        assert r.status_code == 404

    def test_200_valid_update(self, flask_client):
        band_id = _create_band(flask_client)
        r = _put(flask_client, band_id, {"name": "Renamed"})
        assert r.status_code == 200
        assert db_module.get_band(band_id)["name"] == "Renamed"

    def test_200_partial_update_preserves_other_fields(self, flask_client):
        band_id = _create_band(flask_client)
        original = db_module.get_band(band_id)
        _put(flask_client, band_id, {"name": "Only Name Changed"})
        updated = db_module.get_band(band_id)
        assert updated["freq_start"] == original["freq_start"]
        assert updated["interval_s"] == original["interval_s"]

    def test_400_bad_interval_s(self, flask_client):
        band_id = _create_band(flask_client)
        r = _put(flask_client, band_id, {"interval_s": "not_a_number"})
        assert r.status_code == 400
        assert "interval_s" in json.loads(r.data)["error"]

    def test_400_interval_s_zero(self, flask_client):
        band_id = _create_band(flask_client)
        assert _put(flask_client, band_id, {"interval_s": 0}).status_code == 400

    def test_400_bad_device_index(self, flask_client):
        band_id = _create_band(flask_client)
        r = _put(flask_client, band_id, {"device_index": -2})
        assert r.status_code == 400

    def test_400_bad_min_power(self, flask_client):
        band_id = _create_band(flask_client)
        r = _put(flask_client, band_id, {"min_power": "loud"})
        assert r.status_code == 400

    def test_400_bad_is_active(self, flask_client):
        band_id = _create_band(flask_client)
        r = _put(flask_client, band_id, {"is_active": "maybe"})
        assert r.status_code == 400


# ── DELETE /api/bands/<id> ────────────────────────────────────────────────────

class TestDeleteBand:

    def test_200_deletes_band(self, flask_client):
        band_id = _create_band(flask_client)
        r = flask_client.delete(f"/api/bands/{band_id}")
        assert r.status_code == 200
        assert db_module.get_band(band_id) is None

    def test_200_delete_nonexistent_is_idempotent(self, flask_client):
        # stop_band on a non-existent band should not raise; delete is a no-op
        r = flask_client.delete("/api/bands/ghost")
        assert r.status_code == 200


# ── POST /api/bands/<id>/start ────────────────────────────────────────────────

class TestStartBand:

    def test_409_band_not_found(self, flask_client, mock_band_manager):
        mock_band_manager.start_band.side_effect = ValueError("Band not found")
        r = flask_client.post("/api/bands/no_such_band/start")
        assert r.status_code == 409
        assert "error" in json.loads(r.data)

    def test_409_already_running(self, flask_client, mock_band_manager):
        mock_band_manager.start_band.side_effect = RuntimeError("already capturing")
        r = flask_client.post("/api/bands/some_band/start")
        assert r.status_code == 409

    def test_200_start_success(self, flask_client, mock_band_manager):
        mock_band_manager.start_band.return_value = None
        r = flask_client.post("/api/bands/some_band/start")
        assert r.status_code == 200
        assert json.loads(r.data)["status"] == "running"


# ── POST /api/bands/<id>/stop ─────────────────────────────────────────────────

class TestStopBand:

    def test_200_stop(self, flask_client, mock_band_manager):
        mock_band_manager.get_status.return_value = "idle"
        r = flask_client.post("/api/bands/some_band/stop")
        assert r.status_code == 200
        assert json.loads(r.data)["status"] == "idle"


# ── GET /api/bands/<id>/status ────────────────────────────────────────────────

class TestBandStatus:

    def test_200_returns_status_and_error(self, flask_client, mock_band_manager):
        mock_band_manager.get_status.return_value = "running"
        mock_band_manager.get_error.return_value = None
        data = json.loads(flask_client.get("/api/bands/some_band/status").data)
        assert data["status"] == "running"
        assert data["error"] is None
