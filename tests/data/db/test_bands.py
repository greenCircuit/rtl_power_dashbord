"""Unit tests for app/data/db — band CRUD operations"""

import pytest

import app.data.db as db_module
from app.data.db import (
    create_band,
    delete_band,
    get_band,
    init_db,
    insert_band_measurements,
    list_bands,
    update_band,
)


# ── helpers ───────────────────────────────────────────────────────────────────

BAND = dict(
    band_id="b1",
    name="Test Band",
    freq_start="144M",
    freq_end="146M",
    freq_step="25k",
    interval_s=10,
    min_power=2.0,
    device_index=0,
)


def _create(overrides=None):
    kw = {**BAND, **(overrides or {})}
    create_band(**kw)
    return kw["band_id"]


# ── init_db ───────────────────────────────────────────────────────────────────

def test_init_db_creates_bands_table(tmp_db):
    from sqlalchemy import inspect
    inspector = inspect(db_module.get_engine())
    tables = set(inspector.get_table_names())
    assert "bands" in tables
    assert "band_measurements" in tables


# ── create / get / list ───────────────────────────────────────────────────────

def test_create_and_get_band(tmp_db):
    _create()
    band = get_band("b1")
    assert band is not None
    assert band["name"] == "Test Band"
    assert band["freq_start"] == "144M"
    assert band["freq_end"] == "146M"
    assert band["freq_step"] == "25k"
    assert band["interval_s"] == 10
    assert band["min_power"] == 2.0
    assert band["device_index"] == 0


def test_get_band_missing_returns_none(tmp_db):
    assert get_band("nope") is None


def test_list_bands_empty(tmp_db):
    assert list_bands() == []


def test_list_bands_returns_all(tmp_db):
    _create({"band_id": "b1", "name": "Alpha"})
    _create({"band_id": "b2", "name": "Beta"})
    names = [b["name"] for b in list_bands()]
    assert "Alpha" in names
    assert "Beta" in names


def test_list_bands_ordered_by_name(tmp_db):
    _create({"band_id": "b1", "name": "Zebra"})
    _create({"band_id": "b2", "name": "Alpha"})
    names = [b["name"] for b in list_bands()]
    assert names == sorted(names)


# ── update ────────────────────────────────────────────────────────────────────

def test_update_band(tmp_db):
    _create()
    update_band("b1", "Updated", "430M", "440M", "12.5k", 30, 5.0, 1)
    band = get_band("b1")
    assert band["name"] == "Updated"
    assert band["freq_start"] == "430M"
    assert band["interval_s"] == 30
    assert band["min_power"] == 5.0
    assert band["device_index"] == 1


# ── delete ────────────────────────────────────────────────────────────────────

def test_delete_band_removes_band(tmp_db):
    _create()
    delete_band("b1")
    assert get_band("b1") is None


def test_delete_band_removes_measurements(tmp_db):
    _create()
    with db_module.get_engine().connect() as conn:
        insert_band_measurements(conn, "b1", [("2024-01-01 00:00:00", 144.5, -60.0)])
        conn.commit()
    delete_band("b1")
    rows = db_module.fetch_band_measurements("b1")
    assert rows == []
