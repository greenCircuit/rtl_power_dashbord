import logging
import os
from pathlib import Path

import yaml

# In Docker the env var is not set and /app/data is used via the volume.
# Locally it defaults to <project_root>/data so no extra setup is needed.
_default = Path(__file__).resolve().parent.parent / "data"
DATA_DIR = Path(os.environ.get("DATA_DIR", _default))
DB_PATH = DATA_DIR / "rtl_power.db"

# Main config file — override with BANDS_CONFIG env var (e.g. in Docker)
_default_config = Path(__file__).resolve().parent.parent / "config.yaml"
BANDS_CONFIG = Path(os.environ.get("BANDS_CONFIG", _default_config))

# Demo mode — set DEMO_MODE=true to replay recorded data without hardware
DEMO_MODE = os.environ.get("DEMO_MODE", "false").lower() == "true"
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
    except Exception:
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
        return False


def configure_logging() -> None:
    """Set up root logger. Always logs to stdout; adds file handler only when
    logs.enabled = true in config.yaml."""
    level = getattr(logging, LOG_LEVEL, logging.INFO)
    fmt = logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
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
        logging.getLogger(__name__).info("File logging enabled → %s", LOG_PATH)

    # Silence noisy third-party loggers
    for noisy in ("werkzeug", "dash", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
