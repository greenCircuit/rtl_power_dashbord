"""Integration tests for GET /api/status"""

import json

import pytest


def _ok(response):
    assert response.status_code == 200, response.data
    return json.loads(response.data)


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
