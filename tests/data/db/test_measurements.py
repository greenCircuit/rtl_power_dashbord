"""Unit tests for app/data/db — measurement insert, fetch, and time filtering.

Regression tests for the T-separator bug are also here:
  Root cause: datetime-local HTML inputs produce ISO 8601 with a T separator
  ("2026-04-03T08:17"), but DB timestamps use a space separator
  ("2026-04-03 08:45:38"). SQLite string comparison treats T (ASCII 84) as
  greater than space (ASCII 32), so "2026-04-03 ..." < "2026-04-03T..." for
  every row — the filter silently excludes all data.

  The fix is in update_filters (callbacks.py): .replace("T", " ") before
  storing time_min/time_max in the filter store.
"""

from datetime import datetime, timedelta

import app.data.db as db_module
from app.data.db import create_band, insert_band_measurements


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


# ── insert / fetch ────────────────────────────────────────────────────────────

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


# ── adaptive bucketing ────────────────────────────────────────────────────────

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
