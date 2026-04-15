"""Unit tests for app/data/db — band seeding from YAML"""

import logging
import textwrap

from app.data.db import (
    _seed_one_band,
    create_band,
    get_band,
    seed_bands_from_yaml,
)


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


# ── Bug #8 regression: malformed entries must not crash the whole seed ────────

def test_seed_from_yaml_skips_entry_missing_required_key(tmp_db, tmp_path, caplog):
    """An entry missing a required key (e.g. 'name') must be skipped with a
    warning — the valid entries before and after it must still be inserted."""
    yaml_file = tmp_path / "bands.yaml"
    yaml_file.write_text(textwrap.dedent("""
        bands:
          - id: good1
            name: Good One
            freq_start: "144M"
            freq_end: "146M"
            freq_step: "25k"
          - id: bad_entry
            freq_start: "430M"
            freq_end: "440M"
            freq_step: "12.5k"
            # 'name' is intentionally absent — required field
          - id: good2
            name: Good Two
            freq_start: "462M"
            freq_end: "463M"
            freq_step: "12.5k"
    """))
    with caplog.at_level(logging.WARNING, logger="app.data.db.bands"):
        seed_bands_from_yaml(yaml_file)

    assert get_band("good1") is not None, "valid entry before malformed one must be inserted"
    assert get_band("good2") is not None, "valid entry after malformed one must be inserted"
    assert get_band("bad_entry") is None, "malformed entry must not be inserted"
    assert any("malformed" in r.message.lower() or "missing" in r.message.lower()
               for r in caplog.records), "must emit a warning for the skipped entry"


def test_seed_from_yaml_skips_entry_with_bad_value_type(tmp_db, tmp_path, caplog):
    """An entry whose optional value cannot be coerced (e.g. interval_s='abc')
    must be skipped with a warning rather than raising an uncaught exception."""
    yaml_file = tmp_path / "bands.yaml"
    yaml_file.write_text(textwrap.dedent("""
        bands:
          - id: broken
            name: Broken
            freq_start: "144M"
            freq_end: "146M"
            freq_step: "25k"
            interval_s: not_a_number
          - id: ok
            name: OK
            freq_start: "144M"
            freq_end: "146M"
            freq_step: "25k"
    """))
    with caplog.at_level(logging.WARNING, logger="app.data.db.bands"):
        seed_bands_from_yaml(yaml_file)

    assert get_band("broken") is None, "entry with bad interval_s must be skipped"
    assert get_band("ok") is not None, "valid entry after broken one must still be inserted"
    assert any("broken" in r.message or "error" in r.message.lower()
               for r in caplog.records)
