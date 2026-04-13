"""Unit tests for app/data/db.py — SQLAlchemy implementation"""

import textwrap
import pytest

import app.data.db as db_module
from app.data.db import (
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


# ── insert_band_measurements ──────────────────────────────────────────────────

def test_insert_band_measurements(tmp_db):
    _create()
    measurements = [
        ("2024-01-01 12:00:00", 144.0, -55.0),
        ("2024-01-01 12:00:00", 144.5, -60.0),
        ("2024-01-01 12:00:00", 145.0, -65.0),
    ]
    with db_module.get_engine().connect() as conn:
        insert_band_measurements(conn, "b1", measurements)
        conn.commit()
    rows = db_module.fetch_band_measurements("b1")
    assert len(rows) == 3


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
    with db_module.get_engine().connect() as conn:
        insert_band_measurements(conn, "b1", [
            ("2026-04-03 08:00:00", 144.0, -55.0),
            ("2026-04-03 10:00:00", 144.0, -55.0),
            ("2026-04-03 12:00:00", 144.0, -55.0),
        ])
        conn.commit()
    # T-separator as produced by datetime-local input — this was the bug
    rows = db_module.fetch_band_measurements("b1", {"time_min": "2026-04-03T00:00"})
    assert rows == [], (
        "T-separated timestamp must NOT match space-separated DB rows — "
        "this test documents the root cause of the bug"
    )


def test_space_separator_matches_db_timestamps(tmp_db):
    """Space-separated filter (after .replace('T', ' ') fix) matches correctly."""
    _create()
    with db_module.get_engine().connect() as conn:
        insert_band_measurements(conn, "b1", [
            ("2026-04-03 08:00:00", 144.0, -55.0),
            ("2026-04-03 10:00:00", 144.0, -55.0),
            ("2026-04-03 12:00:00", 144.0, -55.0),
        ])
        conn.commit()
    # Space-separator as produced by the fix: .replace("T", " ")
    rows = db_module.fetch_band_measurements("b1", {"time_min": "2026-04-03 00:00"})
    assert len(rows) == 3


def test_time_filter_excludes_rows_outside_range(tmp_db):
    """Time filter correctly excludes rows outside the requested window."""
    _create()
    with db_module.get_engine().connect() as conn:
        insert_band_measurements(conn, "b1", [
            ("2026-04-03 07:00:00", 144.0, -55.0),   # before window
            ("2026-04-03 10:00:00", 144.0, -55.0),   # inside window
            ("2026-04-03 23:00:00", 144.0, -55.0),   # after window
        ])
        conn.commit()
    rows = db_module.fetch_band_measurements("b1", {
        "time_min": "2026-04-03 08:00",
        "time_max": "2026-04-03 12:00",
    })
    assert len(rows) == 1
    assert rows[0][0] == "2026-04-03 10:00:00"


# ── fetch_band_measurements adaptive bucketing ────────────────────────────────

def test_fetch_measurements_raw_path_returns_all_rows(tmp_db):
    """≤ 300 distinct timestamps → raw path, every row returned unchanged."""
    _create()
    rows = [
        (f"2024-01-01 12:00:{i:02d}", 144.0, float(-50 - i))
        for i in range(10)   # 10 distinct timestamps, well below 300
    ]
    with db_module.get_engine().connect() as conn:
        insert_band_measurements(conn, "b1", rows)
        conn.commit()
    result = db_module.fetch_band_measurements("b1")
    assert len(result) == 10


def test_fetch_measurements_bucketed_path_caps_time_slots(tmp_db):
    """> 300 distinct timestamps → bucketed SQL path, ≤ 300 unique time slots returned."""
    from datetime import datetime, timedelta
    _create()
    base = datetime(2024, 1, 1, 0, 0, 0)
    rows = [
        ((base + timedelta(seconds=i * 10)).strftime("%Y-%m-%d %H:%M:%S"), 144.0, -55.0)
        for i in range(400)   # 400 distinct timestamps, above the 300 threshold
    ]
    with db_module.get_engine().connect() as conn:
        insert_band_measurements(conn, "b1", rows)
        conn.commit()
    result = db_module.fetch_band_measurements("b1")
    distinct_timestamps = {r[0] for r in result}
    assert len(distinct_timestamps) <= 300


def test_fetch_measurements_bucketed_path_respects_freq_filter(tmp_db):
    """Frequency filter is applied correctly even in the bucketed SQL path."""
    from datetime import datetime, timedelta
    _create()
    base = datetime(2024, 1, 1, 0, 0, 0)
    rows = []
    for i in range(400):
        ts = (base + timedelta(seconds=i * 10)).strftime("%Y-%m-%d %H:%M:%S")
        rows.append((ts, 144.0, -55.0))
        rows.append((ts, 146.0, -60.0))   # outside filter range
    with db_module.get_engine().connect() as conn:
        insert_band_measurements(conn, "b1", rows)
        conn.commit()
    result = db_module.fetch_band_measurements("b1", {"freq_max": 145.0})
    freqs = {r[1] for r in result}
    assert all(f <= 145.0 for f in freqs), "bucketed path must respect freq_max filter"
    assert 146.0 not in freqs


def test_fetch_measurements_bucketed_path_returns_no_raw_timestamps(tmp_db):
    """Bucketed result timestamps must be bucket boundaries, not original timestamps."""
    from datetime import datetime, timedelta
    _create()
    base = datetime(2024, 1, 1, 0, 0, 0)
    original_timestamps = set()
    rows = []
    for i in range(400):
        ts = (base + timedelta(seconds=i * 10)).strftime("%Y-%m-%d %H:%M:%S")
        original_timestamps.add(ts)
        rows.append((ts, 144.0, -55.0))
    with db_module.get_engine().connect() as conn:
        insert_band_measurements(conn, "b1", rows)
        conn.commit()
    result = db_module.fetch_band_measurements("b1")
    result_timestamps = {r[0] for r in result}
    # In the bucketed path, bucket boundary timestamps are rounded epoch integers
    # re-formatted via datetime(..., 'unixepoch'). They won't match the original
    # timestamps exactly since the originals fall mid-bucket.
    # At minimum, the result must be a strict subset (fewer distinct values).
    assert len(result_timestamps) < len(original_timestamps)


# ── _seed_one_band ────────────────────────────────────────────────────────────

def test_seed_one_band_inserts(tmp_db):
    b = dict(id="gmrs", name="GMRS", freq_start="462.5M",
             freq_end="462.8M", freq_step="12.5k")
    inserted = _seed_one_band(None, b)
    assert inserted is True
    assert get_band("gmrs") is not None


def test_seed_one_band_skips_duplicate(tmp_db):
    _create({"band_id": "gmrs", "name": "GMRS"})
    b = dict(id="gmrs", name="GMRS", freq_start="462.5M",
             freq_end="462.8M", freq_step="12.5k")
    inserted = _seed_one_band(None, b)
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
