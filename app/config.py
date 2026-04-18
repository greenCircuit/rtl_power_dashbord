import json
import logging
import os
from pathlib import Path

import yaml

# In Docker the env var is not set and /app/data is used via the volume.
# Locally it defaults to <project_root>/data so no extra setup is needed.
_default = Path(__file__).resolve().parent.parent / "data"
DATA_DIR = Path(os.environ.get("DATA_DIR", _default))

# Main config file — override with BANDS_CONFIG env var (e.g. in Docker)
_default_config = Path(__file__).resolve().parent.parent / "config.yaml"
BANDS_CONFIG = Path(os.environ.get("BANDS_CONFIG", _default_config))


def _read_demo_mode() -> bool:
    """Return DEMO_MODE: env var wins; falls back to DEMO_MODE key in config.yaml."""
    env = os.environ.get("DEMO_MODE")
    if env is not None:
        return env.lower() == "true"
    try:
        with open(BANDS_CONFIG) as fh:
            cfg = yaml.safe_load(fh) or {}
        return str(cfg.get("DEMO_MODE", "false")).lower() == "true"
    except Exception:
        logging.getLogger(__name__).warning(
            "Failed to read DEMO_MODE from %s — defaulting to False", BANDS_CONFIG
        )
        return False


# Demo mode — enable via DEMO_MODE=true env var or DEMO_MODE: true in config.yaml.
# Uses a separate database (demo.db) so live data is never touched.
DEMO_MODE = _read_demo_mode()
_db_name  = "demo.db" if DEMO_MODE else "rtl_power.db"
DB_PATH   = DATA_DIR / _db_name

# Legacy seed DB used by demo/export_seed.py
_default_seed = Path(__file__).resolve().parent.parent / "demo" / "seed.db"
DEMO_SEED_DB = Path(os.environ.get("DEMO_SEED_DB", _default_seed))

# Logging
_project_root = Path(__file__).resolve().parent.parent
LOG_PATH  = Path(os.environ.get("LOG_PATH", _project_root / "log.log"))
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()


def load_cleanup_config() -> dict:
    """Read clean_up section from config.yaml.

    Returns dict with keys: enabled, interval_mins, db_max_size_mb, max_time_hrs.
    """
    defaults = {
        "enabled":        False,
        "interval_mins":  30,
        "db_max_size_mb": 1024,
        "max_time_hrs":   72,
    }
    if not BANDS_CONFIG.exists():
        return defaults
    try:
        with open(BANDS_CONFIG) as fh:
            cfg = yaml.safe_load(fh) or {}
        section = cfg.get("clean_up", {}) or {}
        return {
            "enabled":        bool(section.get("enabled",        defaults["enabled"])),
            "interval_mins":  int(section.get("interval_mins",   defaults["interval_mins"])),
            "db_max_size_mb": int(section.get("db_max_size_mb",  defaults["db_max_size_mb"])),
            "max_time_hrs":   int(section.get("max_time_hrs",    defaults["max_time_hrs"])),
        }
    except Exception as exc:
        logging.getLogger(__name__).warning(
            "Failed to load cleanup config from %s: %s — using defaults", BANDS_CONFIG, exc
        )
        return defaults


def load_retention_config() -> dict:
    """Read retention section from config.yaml.

    Returns dict with keys: raw_hours, rollup_interval_mins, rollups.
    rollups is a list of {interval_minutes, retention_days} sorted ascending by interval.
    """
    defaults: dict = {
        "raw_hours":            2,
        "rollup_interval_mins": 15,
        "rollups":              [],
    }
    if not BANDS_CONFIG.exists():
        return defaults
    try:
        with open(BANDS_CONFIG) as fh:
            cfg = yaml.safe_load(fh) or {}
        section = cfg.get("retention", {}) or {}
        rollups = []
        for tier in (section.get("rollups") or []):
            try:
                rollups.append({
                    "interval_minutes": int(tier["interval_minutes"]),
                    "retention_days":   int(tier["retention_days"]),
                })
            except (KeyError, TypeError, ValueError):
                logging.getLogger(__name__).warning(
                    "Skipping malformed rollup tier: %r", tier
                )
        rollups.sort(key=lambda t: t["interval_minutes"])
        return {
            "raw_hours":            int(section.get("raw_hours",            defaults["raw_hours"])),
            "rollup_interval_mins": int(
                section.get("rollup_interval_mins", defaults["rollup_interval_mins"])),
            "rollups":              rollups,
        }
    except Exception as exc:
        logging.getLogger(__name__).warning(
            "Failed to load retention config from %s: %s — using defaults", BANDS_CONFIG, exc
        )
        return defaults


def _log_file_enabled() -> bool:
    """Read logs.enabled from config.yaml. Defaults to False (stdout only)."""
    if not BANDS_CONFIG.exists():
        return False
    try:
        with open(BANDS_CONFIG) as fh:
            cfg = yaml.safe_load(fh) or {}
        return bool(cfg.get("logs", {}).get("enabled", False))
    except Exception:
        logging.getLogger(__name__).warning(
            "Failed to read logs.enabled from %s — file logging disabled", BANDS_CONFIG
        )
        return False


class _JsonFormatter(logging.Formatter):
    """Emit one JSON object per log record, always on a single line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "ts":    self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "msg":   record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging() -> None:
    """Set up root logger. Always logs to stdout in JSON; adds file handler
    only when logs.enabled = true in config.yaml."""
    level = getattr(logging, LOG_LEVEL, logging.INFO)
    fmt = _JsonFormatter()

    root = logging.getLogger()
    if root.handlers:
        return  # already configured (e.g. reloader second pass)
    root.setLevel(level)

    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    root.addHandler(sh)

    if _log_file_enabled():
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(LOG_PATH)
        fh.setFormatter(fmt)
        root.addHandler(fh)
        logging.getLogger(__name__).info("File logging enabled — path=%s", LOG_PATH)

    # Silence noisy third-party loggers
    for noisy in ("werkzeug", "dash", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
