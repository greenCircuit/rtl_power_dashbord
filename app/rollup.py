"""
Background rollup scheduler — mirrors the structure of app/cleanup.py.

Each cycle: computes missing rollup buckets for every band × tier, then
cleans up rollup rows that have aged past their retention window.
Config is re-read each cycle so changes take effect without a restart.
"""

import logging
import threading

from app.config import load_retention_config
from app.data.db import list_bands
from app.data.db.rollup import cleanup_rollup_tier, compute_rollup

log = logging.getLogger(__name__)

_timer: threading.Timer | None = None


def run_rollup_once() -> None:
    """Run one full rollup pass synchronously (used at demo startup)."""
    cfg    = load_retention_config()
    bands  = list_bands()
    tiers  = cfg.get("rollups", [])

    if not tiers:
        return

    log.info("Rollup: starting one-shot pass (%d bands, %d tiers)", len(bands), len(tiers))
    for band in bands:
        bid = band["id"]
        for tier in tiers:
            try:
                compute_rollup(bid, tier["interval_minutes"])
            except Exception as exc:
                log.warning("Rollup compute error band=%r tier=%dm: %s",
                            bid, tier["interval_minutes"], exc)

    for tier in tiers:
        try:
            n = cleanup_rollup_tier(tier["interval_minutes"], tier["retention_days"])
            if n:
                log.info("Rollup cleanup: removed %d rows from %dm tier", n, tier["interval_minutes"])
        except Exception as exc:
            log.warning("Rollup cleanup error tier=%dm: %s", tier["interval_minutes"], exc)

    log.info("Rollup: one-shot pass complete")


def _run() -> None:
    cfg   = load_retention_config()
    tiers = cfg.get("rollups", [])

    if not tiers:
        log.debug("Rollup: no tiers configured — skipping")
    else:
        bands = list_bands()
        for band in bands:
            bid = band["id"]
            for tier in tiers:
                try:
                    compute_rollup(bid, tier["interval_minutes"])
                except Exception as exc:
                    log.warning("Rollup compute error band=%r tier=%dm: %s",
                                bid, tier["interval_minutes"], exc)

        for tier in tiers:
            try:
                n = cleanup_rollup_tier(tier["interval_minutes"], tier["retention_days"])
                if n:
                    log.info("Rollup cleanup: removed %d rows from %dm tier",
                             n, tier["interval_minutes"])
            except Exception as exc:
                log.warning("Rollup cleanup error tier=%dm: %s", tier["interval_minutes"], exc)

    _schedule(cfg.get("rollup_interval_mins", 15))


def _schedule(interval_mins: int) -> None:
    global _timer
    _timer = threading.Timer(interval_mins * 60, _run)
    _timer.daemon = True
    _timer.name   = "rollup-timer"
    _timer.start()


def start_rollup_scheduler() -> None:
    cfg = load_retention_config()
    if not cfg.get("rollups"):
        log.info("Rollup scheduler: no tiers configured — not starting")
        return
    interval = cfg.get("rollup_interval_mins", 15)
    log.info("Rollup scheduler started — interval=%d min, tiers=%s",
             interval,
             [(t["interval_minutes"], t["retention_days"]) for t in cfg["rollups"]])
    _schedule(interval)


def stop_rollup_scheduler() -> None:
    global _timer
    if _timer:
        _timer.cancel()
        _timer = None
