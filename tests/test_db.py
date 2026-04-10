"""Unit tests for app/data/db.py"""

import sqlite3
import textwrap
import pytest

import app.data.db as db_module
from app.data.db import (
    _filter_clauses,
    _seed_one_band,
    create_band,
    delete_band,
    get_band,
    init_db,
    insert_band_measurements,
    list_bands,
    seed_bands_from_yaml,
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
    conn = sqlite3.connect(str(tmp_db))
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    conn.close()
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
    conn = sqlite3.connect(str(tmp_db))
    conn.execute("PRAGMA journal_mode=WAL")
    insert_band_measurements(conn, "b1", [("2024-01-01 00:00:00", 144.5, -60.0)])
    conn.commit()
    conn.close()
    delete_band("b1")
    conn2 = sqlite3.connect(str(tmp_db))
    rows = conn2.execute("SELECT * FROM band_measurements WHERE band_id='b1'").fetchall()
    conn2.close()
    assert rows == []


# ── insert_band_measurements ──────────────────────────────────────────────────

def test_insert_band_measurements(tmp_db):
    _create()
    conn = sqlite3.connect(str(tmp_db))
    conn.execute("PRAGMA journal_mode=WAL")
    measurements = [
        ("2024-01-01 12:00:00", 144.0, -55.0),
        ("2024-01-01 12:00:00", 144.5, -60.0),
        ("2024-01-01 12:00:00", 145.0, -65.0),
    ]
    insert_band_measurements(conn, "b1", measurements)
    conn.commit()
    rows = conn.execute("SELECT * FROM band_measurements WHERE band_id='b1'").fetchall()
    conn.close()
    assert len(rows) == 3


# ── _filter_clauses ───────────────────────────────────────────────────────────

def test_filter_clauses_empty():
    sql, params = _filter_clauses(None)
    assert sql == ""
    assert params == []


def test_filter_clauses_empty_dict():
    sql, params = _filter_clauses({})
    assert sql == ""
    assert params == []


def test_filter_clauses_freq_min():
    sql, params = _filter_clauses({"freq_min": 144.0})
    assert "frequency_mhz >= ?" in sql
    assert params == [144.0]


def test_filter_clauses_freq_max():
    sql, params = _filter_clauses({"freq_max": 146.0})
    assert "frequency_mhz <= ?" in sql
    assert params == [146.0]


def test_filter_clauses_time_range():
    sql, params = _filter_clauses({"time_min": "2024-01-01", "time_max": "2024-01-02"})
    assert "timestamp >= ?" in sql
    assert "timestamp <= ?" in sql
    assert "2024-01-01" in params
    assert "2024-01-02" in params


def test_filter_clauses_power_min():
    sql, params = _filter_clauses({"power_min": -80.0})
    assert "power_db >= ?" in sql
    assert params == [-80.0]


def test_filter_clauses_multiple_joined_with_and():
    sql, params = _filter_clauses({"freq_min": 144.0, "freq_max": 146.0})
    assert sql.startswith(" AND ")
    assert "frequency_mhz >= ?" in sql
    assert "frequency_mhz <= ?" in sql
    assert len(params) == 2


# ── time filter format bug regression ────────────────────────────────────────
#
# Root cause: datetime-local HTML inputs produce ISO 8601 format with a T
# separator ("2026-04-03T08:17"), but DB timestamps use a space separator
# ("2026-04-03 08:45:38"). SQLite string comparison treats T (ASCII 84) as
# greater than space (ASCII 32), so "2026-04-03 ..." < "2026-04-03T..." for
# every row — the filter silently excludes all data.
#
# The fix is in update_filters (callbacks.py): .replace("T", " ") before
# storing time_min/time_max in the filter store.

def test_t_separator_excludes_all_rows_demonstrating_the_bug(tmp_db):
    """T-separated filter should fail to match space-separated DB timestamps."""
    _create()
    conn = sqlite3.connect(str(tmp_db))
    conn.execute("PRAGMA journal_mode=WAL")
    insert_band_measurements(conn, "b1", [
        ("2026-04-03 08:00:00", 144.0, -55.0),
        ("2026-04-03 10:00:00", 144.0, -55.0),
        ("2026-04-03 12:00:00", 144.0, -55.0),
    ])
    conn.commit()
    conn.close()
    # T-separator as produced by datetime-local input — this was the bug
    rows = db_module.fetch_band_measurements("b1", {"time_min": "2026-04-03T00:00"})
    assert rows == [], (
        "T-separated timestamp must NOT match space-separated DB rows — "
        "this test documents the root cause of the bug"
    )


def test_space_separator_matches_db_timestamps(tmp_db):
    """Space-separated filter (after .replace('T', ' ') fix) matches correctly."""
    _create()
    conn = sqlite3.connect(str(tmp_db))
    conn.execute("PRAGMA journal_mode=WAL")
    insert_band_measurements(conn, "b1", [
        ("2026-04-03 08:00:00", 144.0, -55.0),
        ("2026-04-03 10:00:00", 144.0, -55.0),
        ("2026-04-03 12:00:00", 144.0, -55.0),
    ])
    conn.commit()
    conn.close()
    # Space-separator as produced by the fix: .replace("T", " ")
    rows = db_module.fetch_band_measurements("b1", {"time_min": "2026-04-03 00:00"})
    assert len(rows) == 3


def test_time_filter_excludes_rows_outside_range(tmp_db):
    """Time filter correctly excludes rows outside the requested window."""
    _create()
    conn = sqlite3.connect(str(tmp_db))
    conn.execute("PRAGMA journal_mode=WAL")
    insert_band_measurements(conn, "b1", [
        ("2026-04-03 07:00:00", 144.0, -55.0),   # before window
        ("2026-04-03 10:00:00", 144.0, -55.0),   # inside window
        ("2026-04-03 23:00:00", 144.0, -55.0),   # after window
    ])
    conn.commit()
    conn.close()
    rows = db_module.fetch_band_measurements("b1", {
        "time_min": "2026-04-03 08:00",
        "time_max": "2026-04-03 12:00",
    })
    assert len(rows) == 1
    assert rows[0][0] == "2026-04-03 10:00:00"


# ── _seed_one_band ────────────────────────────────────────────────────────────

def test_seed_one_band_inserts(tmp_db):
    conn = sqlite3.connect(str(tmp_db))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    b = dict(id="gmrs", name="GMRS", freq_start="462.5M",
             freq_end="462.8M", freq_step="12.5k")
    inserted = _seed_one_band(conn, b)
    conn.commit()
    conn.close()
    assert inserted is True
    assert get_band("gmrs") is not None


def test_seed_one_band_skips_duplicate(tmp_db):
    _create({"band_id": "gmrs", "name": "GMRS"})
    conn = sqlite3.connect(str(tmp_db))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    b = dict(id="gmrs", name="GMRS", freq_start="462.5M",
             freq_end="462.8M", freq_step="12.5k")
    inserted = _seed_one_band(conn, b)
    conn.commit()
    conn.close()
    assert inserted is False


# ── seed_bands_from_yaml ──────────────────────────────────────────────────────

def test_seed_from_yaml_inserts_bands(tmp_db, tmp_path):
    yaml_file = tmp_path / "bands.yaml"
    yaml_file.write_text(textwrap.dedent("""
        bands:
          - id: gmrs
            name: GMRS
            freq_start: "462.5M"
            freq_end: "462.8M"
            freq_step: "12.5k"
            interval_s: 10
            min_power: 1.0
            device_index: 0
    """))
    seed_bands_from_yaml(yaml_file)
    band = get_band("gmrs")
    assert band is not None
    assert band["name"] == "GMRS"
    assert band["freq_start"] == "462.5M"


def test_seed_from_yaml_skips_existing(tmp_db, tmp_path):
    _create({"band_id": "gmrs", "name": "GMRS"})
    yaml_file = tmp_path / "bands.yaml"
    yaml_file.write_text(textwrap.dedent("""
        bands:
          - id: gmrs
            name: GMRS Modified
            freq_start: "462.5M"
            freq_end: "462.8M"
            freq_step: "12.5k"
    """))
    seed_bands_from_yaml(yaml_file)
    # name must not be overwritten
    assert get_band("gmrs")["name"] == "GMRS"


def test_seed_from_yaml_missing_file_does_not_raise(tmp_db, tmp_path):
    seed_bands_from_yaml(tmp_path / "nonexistent.yaml")  # must not raise


def test_seed_from_yaml_uses_defaults(tmp_db, tmp_path):
    yaml_file = tmp_path / "bands.yaml"
    yaml_file.write_text(textwrap.dedent("""
        bands:
          - id: vhf
            name: VHF
            freq_start: "144M"
            freq_end: "165M"
            freq_step: "25k"
    """))
    seed_bands_from_yaml(yaml_file)
    band = get_band("vhf")
    assert band["interval_s"] == 10
    assert band["min_power"] == 2.0
    assert band["device_index"] == 0
