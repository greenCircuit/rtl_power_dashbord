"""Per-frequency measurement queries and bulk insert."""

import logging
import math
import time
from datetime import datetime
from typing import Optional

from sqlalchemy import case, func

from ._engine import BandMeasurement, _session, _apply_filters

log = logging.getLogger(__name__)

_MAX_TIME_BUCKETS = 300

# ── query source routing ──────────────────────────────────────────────────────

_cfg_cache: Optional[dict] = None
_cfg_loaded_at: float = 0.0
_CFG_TTL = 60.0

# Per-(band_id, bucket_minutes) cache: has rollup data been computed yet?
# Avoids a DB round-trip on every request; entries expire after 5 minutes.
_rollup_exists_cache: dict[tuple, tuple[bool, float]] = {}
_ROLLUP_EXISTS_TTL = 300.0


def _get_retention_cfg() -> dict:
    global _cfg_cache, _cfg_loaded_at
    if _cfg_cache is None or time.monotonic() - _cfg_loaded_at > _CFG_TTL:
        from app.config import load_retention_config
        _cfg_cache     = load_retention_config()
        _cfg_loaded_at = time.monotonic()
    return _cfg_cache


def _rollup_has_data(band_id: str, bucket_minutes: int) -> bool:
    """Return True if the rollup table has at least one row for this band+tier."""
    key = (band_id, bucket_minutes)
    now = time.monotonic()
    cached = _rollup_exists_cache.get(key)
    if cached and now - cached[1] < _ROLLUP_EXISTS_TTL:
        return cached[0]
    from ._engine import BandMeasurementRollup, _session as _s
    with _s() as sess:
        exists = sess.query(BandMeasurementRollup.id).filter(
            BandMeasurementRollup.band_id        == band_id,
            BandMeasurementRollup.bucket_minutes == bucket_minutes,
        ).first() is not None
    _rollup_exists_cache[key] = (exists, now)
    return exists


def _time_range_hours(filters: dict | None) -> float:
    """Return how many hours ago time_min is, relative to now."""
    time_min = (filters or {}).get("time_min")
    if not time_min:
        return 0.0
    try:
        t0  = datetime.fromisoformat(str(time_min).replace("T", " "))
        age = (datetime.now() - t0).total_seconds() / 3600
        return max(age, 0.0)
    except (ValueError, TypeError):
        return 0.0


def _resolve_source(band_id: str, filters: dict | None) -> tuple[str, int | None]:
    """Return ('raw', None) or ('rollup', bucket_minutes).

    Routes to rollup when:
      - time_min is explicitly provided AND older than raw_hours from now
      - AND rollup data has already been computed for this band+tier
    Falls back to raw otherwise (no time filter, recent query, or rollup not yet populated).
    """
    cfg = _get_retention_cfg()
    if not cfg["rollups"] or not filters or not filters.get("time_min"):
        return "raw", None

    age_hrs = _time_range_hours(filters)
    if age_hrs <= cfg["raw_hours"]:
        return "raw", None

    for tier in cfg["rollups"]:
        if age_hrs <= tier["retention_days"] * 24:
            bm = tier["interval_minutes"]
            return ("rollup", bm) if _rollup_has_data(band_id, bm) else ("raw", None)

    bm = cfg["rollups"][-1]["interval_minutes"]
    return ("rollup", bm) if _rollup_has_data(band_id, bm) else ("raw", None)


def insert_band_measurements(conn, band_id: str, rows: list) -> None:
    """Bulk-insert measurement rows via a SQLAlchemy connection.

    *rows* is a list of (timestamp, frequency_mhz, power_db) tuples.
    *conn* must be a SQLAlchemy ``Connection`` obtained from ``get_engine()``.
    The caller is responsible for calling ``conn.commit()`` afterwards.
    """
    if not rows:
        return
    conn.execute(
        BandMeasurement.__table__.insert(),
        [{"band_id": band_id, "timestamp": ts, "frequency_mhz": freq, "power_db": pwr}
         for ts, freq, pwr in rows],
    )


# ── shared time-bucketing helpers ─────────────────────────────────────────────

def _scan_meta(sess, band_id: str, filters: dict | None):
    """Return (n_sweeps, ts_min_str, ts_max_str) for the filtered dataset."""
    q = sess.query(
        func.count(BandMeasurement.timestamp.distinct()).label("n_sweeps"),
        func.min(BandMeasurement.timestamp).label("ts_min"),
        func.max(BandMeasurement.timestamp).label("ts_max"),
    ).filter(BandMeasurement.band_id == band_id)
    q = _apply_filters(q, filters)
    meta = q.one()
    return meta.n_sweeps or 0, meta.ts_min, meta.ts_max


def _calc_bucket_s(ts_min, ts_max) -> int:
    """Return bucket width in seconds to fit the time range into _MAX_TIME_BUCKETS."""
    try:
        t0 = datetime.fromisoformat(str(ts_min).replace(" ", "T"))
        t1 = datetime.fromisoformat(str(ts_max).replace(" ", "T"))
        total_s = max((t1 - t0).total_seconds(), 1)
    except (ValueError, TypeError):
        total_s = _MAX_TIME_BUCKETS
    return max(math.ceil(total_s / _MAX_TIME_BUCKETS), 1)


def _bucket_expr(bucket_s: int):
    """SQLAlchemy expression that rounds a timestamp down to its bucket boundary."""
    epoch = func.strftime("%s", BandMeasurement.timestamp)
    return func.datetime(epoch - epoch % bucket_s, "unixepoch")


# ── query functions ───────────────────────────────────────────────────────────

def fetch_band_measurements(band_id: str, filters: dict | None = None,
                            agg: str = "avg") -> list[tuple]:
    """Return [(timestamp, frequency_mhz, power_db), ...].

    Routes to the rollup table for historical ranges; uses raw data for
    recent queries. Large raw datasets are bucketed to _MAX_TIME_BUCKETS.
    *agg*: ``"avg"`` (default) or ``"max"`` (peak-hold).
    """
    source, bucket_minutes = _resolve_source(band_id, filters)
    if source == "rollup":
        from .rollup import fetch_rollup_measurements
        return fetch_rollup_measurements(band_id, bucket_minutes, filters, agg)

    with _session() as sess:
        n_sweeps, ts_min, ts_max = _scan_meta(sess, band_id, filters)

        if n_sweeps <= _MAX_TIME_BUCKETS:
            q = sess.query(
                BandMeasurement.timestamp,
                BandMeasurement.frequency_mhz,
                BandMeasurement.power_db,
            ).filter(BandMeasurement.band_id == band_id)
            q = _apply_filters(q, filters)
            return q.order_by(BandMeasurement.timestamp).all()

        bucket_s  = _calc_bucket_s(ts_min, ts_max)
        bucket    = _bucket_expr(bucket_s)
        agg_func  = func.max if agg == "max" else func.avg

        q = sess.query(
            bucket.label("timestamp"),
            BandMeasurement.frequency_mhz,
            agg_func(BandMeasurement.power_db).label("power_db"),
        ).filter(BandMeasurement.band_id == band_id)
        q = _apply_filters(q, filters)
        q = q.group_by(bucket, BandMeasurement.frequency_mhz)
        q = q.order_by(bucket, BandMeasurement.frequency_mhz)
        return q.all()


def fetch_band_stats(band_id: str, filters: dict | None = None) -> list[dict]:
    """Return per-frequency mean and peak: [{frequency_mhz, mean_db, peak_db}]."""
    source, bucket_minutes = _resolve_source(band_id, filters)
    if source == "rollup":
        from .rollup import fetch_rollup_stats
        return fetch_rollup_stats(band_id, bucket_minutes, filters)

    with _session() as sess:
        q = sess.query(
            BandMeasurement.frequency_mhz,
            func.avg(BandMeasurement.power_db).label("mean_db"),
            func.max(BandMeasurement.power_db).label("peak_db"),
        ).filter(BandMeasurement.band_id == band_id)
        q = _apply_filters(q, filters)
        q = q.group_by(BandMeasurement.frequency_mhz).order_by(BandMeasurement.frequency_mhz)
        return [{"frequency_mhz": r.frequency_mhz, "mean_db": r.mean_db, "peak_db": r.peak_db}
                for r in q.all()]


def fetch_band_activity(band_id: str, threshold_db: float,
                        filters: dict | None = None) -> list[dict]:
    """Return per-frequency activity counts: [{frequency_mhz, active, total}]."""
    source, bucket_minutes = _resolve_source(band_id, filters)
    if source == "rollup":
        from .rollup import fetch_rollup_activity
        return fetch_rollup_activity(band_id, bucket_minutes, threshold_db, filters)

    with _session() as sess:
        active_expr = func.sum(
            case((BandMeasurement.power_db >= threshold_db, 1), else_=0)
        )
        q = sess.query(
            BandMeasurement.frequency_mhz,
            active_expr.label("active"),
            func.count(BandMeasurement.id).label("total"),
        ).filter(BandMeasurement.band_id == band_id)
        q = _apply_filters(q, filters)
        q = q.group_by(BandMeasurement.frequency_mhz).order_by(BandMeasurement.frequency_mhz)
        return [{"frequency_mhz": r.frequency_mhz, "active": r.active, "total": r.total}
                for r in q.all()]


def fetch_band_closest_freq(band_id: str, target_mhz: float) -> float | None:
    """Return the stored frequency_mhz closest to *target_mhz*, or None."""
    with _session() as sess:
        row = sess.query(BandMeasurement.frequency_mhz).filter(
            BandMeasurement.band_id == band_id
        ).order_by(
            func.abs(BandMeasurement.frequency_mhz - target_mhz)
        ).first()
        return float(row[0]) if row else None


def fetch_band_timeseries(band_id: str, freq_mhz: float,
                          filters: dict | None = None) -> list[dict]:
    """Return [{timestamp, power_db}] for one frequency."""
    source, bucket_minutes = _resolve_source(band_id, filters)
    if source == "rollup":
        from .rollup import fetch_rollup_timeseries
        return fetch_rollup_timeseries(band_id, bucket_minutes, freq_mhz, filters)

    with _session() as sess:
        freq_filters = {**(filters or {}), "freq_min": freq_mhz, "freq_max": freq_mhz}
        n_sweeps, ts_min, ts_max = _scan_meta(sess, band_id, freq_filters)

        if n_sweeps <= _MAX_TIME_BUCKETS:
            q = sess.query(
                BandMeasurement.timestamp,
                BandMeasurement.power_db,
            ).filter(
                BandMeasurement.band_id == band_id,
                BandMeasurement.frequency_mhz == freq_mhz,
            )
            q = _apply_filters(q, filters)
            q = q.order_by(BandMeasurement.timestamp)
            return [{"timestamp": r.timestamp, "power_db": r.power_db} for r in q.all()]

        bucket_s = _calc_bucket_s(ts_min, ts_max)
        bucket   = _bucket_expr(bucket_s)

        q = sess.query(
            bucket.label("timestamp"),
            func.avg(BandMeasurement.power_db).label("power_db"),
        ).filter(
            BandMeasurement.band_id == band_id,
            BandMeasurement.frequency_mhz == freq_mhz,
        )
        q = _apply_filters(q, filters)
        q = q.group_by(bucket).order_by(bucket)
        return [{"timestamp": r.timestamp, "power_db": r.power_db} for r in q.all()]


def fetch_band_latest_activity(band_id: str, threshold_db: float) -> dict | None:
    """Return {active, total, last_seen} from the most recent hour of data."""
    with _session() as sess:
        last_ts = sess.query(func.max(BandMeasurement.timestamp)).filter(
            BandMeasurement.band_id == band_id
        ).scalar()
        if not last_ts:
            return None
        cutoff = sess.query(
            func.datetime(func.max(BandMeasurement.timestamp), "-1 hour")
        ).filter(BandMeasurement.band_id == band_id).scalar_subquery()
        active_expr = func.sum(
            case((BandMeasurement.power_db >= threshold_db, 1), else_=0)
        )
        q = sess.query(
            active_expr.label("active"),
            func.count(BandMeasurement.id).label("total"),
        ).filter(
            BandMeasurement.band_id == band_id,
            BandMeasurement.timestamp >= cutoff,
        )
        row = q.first()
        return {
            "active":    int(row.active or 0),
            "total":     int(row.total or 0),
            "last_seen": last_ts,
        }


def fetch_band_alltime_peak(band_id: str, filters: dict | None = None) -> list[dict]:
    """Max power per frequency using only freq filters (ignores time window).

    Used to draw a persistent peak-hold line on the spectrum chart.
    """
    freq_filters = {k: v for k, v in (filters or {}).items()
                    if k in ("freq_min", "freq_max")}
    with _session() as sess:
        q = sess.query(
            BandMeasurement.frequency_mhz,
            func.max(BandMeasurement.power_db).label("peak_db"),
        ).filter(BandMeasurement.band_id == band_id)
        if freq_filters:
            q = _apply_filters(q, freq_filters)
        q = q.group_by(BandMeasurement.frequency_mhz).order_by(BandMeasurement.frequency_mhz)
        return [{"frequency_mhz": r.frequency_mhz, "peak_db": r.peak_db} for r in q.all()]


def fetch_band_power_histogram(band_id: str, filters: dict | None = None) -> list[float]:
    """Return power_db samples for the band (used to build a histogram)."""
    source, bucket_minutes = _resolve_source(band_id, filters)
    if source == "rollup":
        from .rollup import fetch_rollup_histogram
        return fetch_rollup_histogram(band_id, bucket_minutes, filters)

    with _session() as sess:
        n_sweeps, ts_min, ts_max = _scan_meta(sess, band_id, filters)

        if n_sweeps <= _MAX_TIME_BUCKETS:
            q = sess.query(BandMeasurement.power_db).filter(
                BandMeasurement.band_id == band_id
            )
            q = _apply_filters(q, filters)
            return [r[0] for r in q.all()]

        bucket_s = _calc_bucket_s(ts_min, ts_max)
        bucket   = _bucket_expr(bucket_s)

        q = sess.query(
            func.avg(BandMeasurement.power_db).label("power_db"),
        ).filter(BandMeasurement.band_id == band_id)
        q = _apply_filters(q, filters)
        q = q.group_by(bucket, BandMeasurement.frequency_mhz)
        return [r[0] for r in q.all()]


def fetch_band_top_channels(band_id: str, threshold_db: float,
                            limit: int = 10,
                            filters: dict | None = None) -> list[dict]:
    """Return the N most active frequencies sorted by activity %.

    [{frequency_mhz, active, total, mean_db}]
    """
    with _session() as sess:
        active_expr = func.sum(
            case((BandMeasurement.power_db >= threshold_db, 1), else_=0)
        )
        total_expr = func.count(BandMeasurement.id)
        q = sess.query(
            BandMeasurement.frequency_mhz,
            active_expr.label("active"),
            total_expr.label("total"),
            func.avg(BandMeasurement.power_db).label("mean_db"),
        ).filter(BandMeasurement.band_id == band_id)
        q = _apply_filters(q, filters)
        q = q.group_by(BandMeasurement.frequency_mhz)
        q = q.order_by((active_expr * 1.0 / total_expr).desc())
        q = q.limit(limit)
        return [
            {"frequency_mhz": r.frequency_mhz, "active": r.active,
             "total": r.total, "mean_db": r.mean_db}
            for r in q.all()
        ]


def fetch_band_signal_raw(band_id: str, threshold_db: float,
                          filters: dict | None = None) -> list[dict]:
    """Return [{timestamp, frequency_mhz, power_db}] for signal-bearing rows."""
    source, bucket_minutes = _resolve_source(band_id, filters)
    if source == "rollup":
        from .rollup import fetch_rollup_signal_raw
        return fetch_rollup_signal_raw(band_id, bucket_minutes, threshold_db, filters)

    with _session() as sess:
        n_sweeps, ts_min, ts_max = _scan_meta(sess, band_id, filters)

        if n_sweeps <= _MAX_TIME_BUCKETS:
            q = sess.query(
                BandMeasurement.timestamp,
                BandMeasurement.frequency_mhz,
                BandMeasurement.power_db,
            ).filter(
                BandMeasurement.band_id == band_id,
                BandMeasurement.power_db >= threshold_db,
            )
            q = _apply_filters(q, filters)
            q = q.order_by(BandMeasurement.frequency_mhz, BandMeasurement.timestamp)
            return [{"timestamp": r.timestamp, "frequency_mhz": r.frequency_mhz,
                     "power_db": r.power_db} for r in q.all()]

        bucket_s = _calc_bucket_s(ts_min, ts_max)
        bucket   = _bucket_expr(bucket_s)

        q = sess.query(
            bucket.label("timestamp"),
            BandMeasurement.frequency_mhz,
            func.max(BandMeasurement.power_db).label("power_db"),
        ).filter(BandMeasurement.band_id == band_id)
        q = _apply_filters(q, filters)
        q = q.group_by(bucket, BandMeasurement.frequency_mhz)
        # Keep only buckets where the peak crossed the threshold.
        q = q.having(func.max(BandMeasurement.power_db) >= threshold_db)
        q = q.order_by(BandMeasurement.frequency_mhz, bucket)
        return [{"timestamp": r.timestamp, "frequency_mhz": r.frequency_mhz,
                 "power_db": r.power_db} for r in q.all()]
