import logging
import os
from pathlib import Path

# In Docker the env var is not set and /app/data is used via the volume.
# Locally it defaults to <project_root>/data so no extra setup is needed.
_default = Path(__file__).resolve().parent.parent / "data"
DATA_DIR = Path(os.environ.get("DATA_DIR", _default))
DB_PATH = DATA_DIR / "rtl_power.db"

# YAML band config — override with BANDS_CONFIG env var (e.g. in Docker)
_default_bands = Path(__file__).resolve().parent.parent / "bands.yaml"
BANDS_CONFIG = Path(os.environ.get("BANDS_CONFIG", _default_bands))

# Logging
_project_root = Path(__file__).resolve().parent.parent
LOG_PATH = Path(os.environ.get("LOG_PATH", _project_root / "log.log"))
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()


def configure_logging() -> None:
    """Set up root logger with console + file handlers. Safe to call once."""
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

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(LOG_PATH)
    fh.setFormatter(fmt)
    root.addHandler(fh)

    # Silence noisy third-party loggers
    for noisy in ("werkzeug", "dash", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
