"""Unit tests for the pure parsing helpers in app/capture/rtl_power.py"""

import pytest
from app.capture.rtl_power import _parse_csv_line, _build_measurement_rows


# ── _parse_csv_line ───────────────────────────────────────────────────────────

VALID_LINE = "2024-01-15, 12:00:00, 144000000, 146000000, 25000, 1, -55.0, -60.0, -65.0"


def test_parse_csv_line_valid():
    result = _parse_csv_line(VALID_LINE)
    assert result is not None
    date_str, time_str, hz_low, hz_high, db_values = result
    assert date_str == "2024-01-15"
    assert time_str == "12:00:00"
    assert hz_low == 144_000_000.0
    assert hz_high == 146_000_000.0
    assert db_values == [-55.0, -60.0, -65.0]


def test_parse_csv_line_too_few_parts():
    assert _parse_csv_line("2024-01-15, 12:00:00, 144000000") is None


def test_parse_csv_line_bad_float_in_freq():
    bad = "2024-01-15, 12:00:00, NOTAFREQ, 146000000, 25000, 1, -55.0"
    assert _parse_csv_line(bad) is None


def test_parse_csv_line_empty_db_values():
    # Parts ≥7 but all db value fields are empty strings
    line = "2024-01-15, 12:00:00, 144000000, 146000000, 25000, 1, , , "
    assert _parse_csv_line(line) is None


def test_parse_csv_line_single_db_value():
    line = "2024-01-15, 12:00:00, 144000000, 146000000, 25000, 1, -42.5"
    result = _parse_csv_line(line)
    assert result is not None
    assert result[4] == [-42.5]


def test_parse_csv_line_whitespace_stripped():
    line = "  2024-01-15  ,  12:00:00  , 144000000 , 146000000 , 25000 , 1 , -55.0 "
    result = _parse_csv_line(line)
    assert result is not None
    assert result[0] == "2024-01-15"
    assert result[1] == "12:00:00"


# ── _build_measurement_rows ───────────────────────────────────────────────────

def test_build_measurement_rows_count():
    rows = _build_measurement_rows("2024-01-15", "12:00:00",
                                   144_000_000, 146_000_000,
                                   [-55.0, -60.0, -65.0])
    assert len(rows) == 3


def test_build_measurement_rows_timestamp_format():
    rows = _build_measurement_rows("2024-01-15", "12:00:00",
                                   144_000_000, 146_000_000, [-55.0])
    assert rows[0][0] == "2024-01-15 12:00:00"


def test_build_measurement_rows_freq_in_mhz():
    rows = _build_measurement_rows("2024-01-15", "12:00:00",
                                   144_000_000, 146_000_000,
                                   [-55.0, -60.0, -65.0])
    freqs = [r[1] for r in rows]
    assert freqs[0] == pytest.approx(144.0)
    assert freqs[-1] == pytest.approx(146.0)


def test_build_measurement_rows_power_values():
    db_values = [-55.0, -60.0, -65.0]
    rows = _build_measurement_rows("2024-01-15", "12:00:00",
                                   144_000_000, 146_000_000, db_values)
    powers = [r[2] for r in rows]
    assert powers == pytest.approx(db_values)


def test_build_measurement_rows_single_point():
    rows = _build_measurement_rows("2024-01-15", "12:00:00",
                                   462_500_000, 462_500_000, [-42.0])
    assert len(rows) == 1
    assert rows[0][1] == pytest.approx(462.5)
    assert rows[0][2] == -42.0
