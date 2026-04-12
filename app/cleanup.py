"""
Background cleanup job — runs on a timer, reads config.yaml each cycle so
changes take effect without a server restart.
"""

import logging
import threading

from app.config import load_cleanup_config
from app.data.db import cleanup_old_data

log = logging.getLogger(__name__)

_timer: threading.Timer | None = None


def _run() -> None:
    cfg = load_cleanup_config()

    if not cfg["enabled"]:
        log.debug("Cleanup disabled — skipping")
    else:
        log.info(
            "Cleanup starting (max_time_hrs=%d, db_max_size_mb=%d)",
            cfg["max_time_hrs"], cfg["db_max_size_mb"],
        )
        try:
            result = cleanup_old_data(cfg["max_time_hrs"], cfg["db_max_size_mb"])
            log.info(
                "Cleanup done — deleted %d (age) + %d (size) rows, DB now %.2f MB",
                result["deleted_by_age"], result["deleted_by_size"], result["db_size_mb"],
            )
        except Exception as exc:
            log.error("Cleanup failed: %s", exc)

    # Reschedule using the current interval (re-read from config each cycle)
    cfg = load_cleanup_config()
    _schedule(cfg["interval_mins"])


def _schedule(interval_mins: int) -> None:
    global _timer
    _timer = threading.Timer(interval_mins * 60, _run)
    _timer.daemon = True
    _timer.name   = "cleanup-timer"
    _timer.start()


def start_cleanup_scheduler() -> None:
    """Start the cleanup background timer. Safe to call once at startup."""
    cfg = load_cleanup_config()
    if not cfg["enabled"]:
        log.info("Cleanup scheduler disabled (clean_up.enabled = false)")
        return
    log.info(
        "Cleanup scheduler started — interval=%d min, max_age=%d hrs, max_size=%d MB",
        cfg["interval_mins"], cfg["max_time_hrs"], cfg["db_max_size_mb"],
    )
    _schedule(cfg["interval_mins"])


def stop_cleanup_scheduler() -> None:
    global _timer
    if _timer:
        _timer.cancel()
        _timer = None
