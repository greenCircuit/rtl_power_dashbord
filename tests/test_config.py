"""Tests for app/config.py — load_cleanup_config."""

import logging

import yaml

import app.config as config_module
from app.config import load_cleanup_config


# ── helpers ───────────────────────────────────────────────────────────────────

def _write_config(path, data):
    with open(path, "w") as fh:
        yaml.dump(data, fh)


DEFAULTS = {
    "enabled":        False,
    "interval_mins":  30,
    "db_max_size_mb": 1024,
    "max_time_hrs":   72,
}


# ── Bug #7 regression: exception must be logged, not silently swallowed ───────

def test_load_cleanup_config_logs_warning_on_bad_file(tmp_path, monkeypatch, caplog):
    """A YAML file that can't be parsed must emit a warning, not silently return defaults."""
    bad_yaml = tmp_path / "config.yaml"
    bad_yaml.write_text("clean_up:\n  interval_mins: [unclosed list\n")

    monkeypatch.setattr(config_module, "BANDS_CONFIG", bad_yaml)

    with caplog.at_level(logging.WARNING, logger="app.config"):
        result = load_cleanup_config()

    assert result == DEFAULTS, "should still return defaults after parse error"
    assert any("Failed to load cleanup config" in r.message for r in caplog.records), (
        "expected a warning log message but got none"
    )


def test_load_cleanup_config_logs_warning_on_bad_value(tmp_path, monkeypatch, caplog):
    """A config with a non-integer value where int() is expected must warn, not silently fail."""
    bad_yaml = tmp_path / "config.yaml"
    # interval_mins: "not-a-number" will cause int() to raise ValueError
    bad_yaml.write_text("clean_up:\n  interval_mins: not-a-number\n")

    monkeypatch.setattr(config_module, "BANDS_CONFIG", bad_yaml)

    with caplog.at_level(logging.WARNING, logger="app.config"):
        result = load_cleanup_config()

    assert result == DEFAULTS
    assert any("Failed to load cleanup config" in r.message for r in caplog.records)


# ── normal / happy-path ───────────────────────────────────────────────────────

def test_load_cleanup_config_returns_defaults_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(config_module, "BANDS_CONFIG", tmp_path / "nonexistent.yaml")
    assert load_cleanup_config() == DEFAULTS


def test_load_cleanup_config_reads_valid_section(tmp_path, monkeypatch):
    cfg_path = tmp_path / "config.yaml"
    _write_config(cfg_path, {
        "clean_up": {
            "enabled": True,
            "interval_mins": 15,
            "db_max_size_mb": 512,
            "max_time_hrs": 24,
        }
    })
    monkeypatch.setattr(config_module, "BANDS_CONFIG", cfg_path)
    result = load_cleanup_config()
    assert result == {
        "enabled": True,
        "interval_mins": 15,
        "db_max_size_mb": 512,
        "max_time_hrs": 24,
    }


def test_load_cleanup_config_partial_section_uses_defaults(tmp_path, monkeypatch):
    """Keys absent from the section should fall back to defaults."""
    cfg_path = tmp_path / "config.yaml"
    _write_config(cfg_path, {"clean_up": {"enabled": True}})
    monkeypatch.setattr(config_module, "BANDS_CONFIG", cfg_path)
    result = load_cleanup_config()
    assert result["enabled"] is True
    assert result["interval_mins"] == DEFAULTS["interval_mins"]
    assert result["db_max_size_mb"] == DEFAULTS["db_max_size_mb"]


def test_load_cleanup_config_missing_clean_up_key(tmp_path, monkeypatch):
    """A valid YAML file with no clean_up key must return defaults without logging."""
    cfg_path = tmp_path / "config.yaml"
    _write_config(cfg_path, {"bands": []})
    monkeypatch.setattr(config_module, "BANDS_CONFIG", cfg_path)
    assert load_cleanup_config() == DEFAULTS
