"""Rollup table: incremental computation, querying, and per-tier cleanup."""

import logging
import math
from datetime import datetime, timezone

from sqlalchemy import case, func, text

from ._engine import BandMeasurement, BandMeasurementRollup, _session, get_engine

log = logging.getLogger(__name__)

# ── computation ───────────────────────────────────────────────────────────────

_COMPUTE_SQL = text("""
    INSERT OR REPLACE INTO band_measurements_rollup
        (band_id, bucket_minutes, bucket_ts, frequency_mhz,
         avg_db, max_db, min_db, sample_count)
    SELECT
        :band_id,
        :bucket_minutes,
        datetime(
            strftime('%s', timestamp) - strftime('%s', timestamp) % :bucket_seconds,
            'unixepoch'
        ),
        frequency_mhz,
        AVG(power_db),
        MAX(power_db),
        MIN(power_db),
        COUNT(*)
    FROM band_measurements
    WHERE band_id   = :band_id
      AND timestamp >= :from_ts
      AND timestamp <  :to_ts
    GROUP BY
        datetime(
            strftime('%s', timestamp) - strftime('%s', timestamp) % :bucket_seconds,
            'unixepoch'
        ),
        frequency_mhz
""")


def compute_rollup(band_id: str, bucket_minutes: int) -> int:
    """Incrementally fill the rollup table for one band and one tier.

    Only computes complete buckets (bucket end <= now).  Picks up from the
    end of the last stored bucket so re-runs are safe and idempotent.
    Returns the number of rows inserted/replaced.
    """
    bucket_seconds = bucket_minutes * 60
    now_epoch      = datetime.now(timezone.utc).timestamp()
    # Exclude the currently-filling bucket
    to_epoch = (now_epoch // bucket_seconds) * bucket_seconds

    with _session() as sess:
        latest_ts = sess.query(
            func.max(BandMeasurementRollup.bucket_ts)
        ).filter(
            BandMeasurementRollup.band_id        == band_id,
            BandMeasurementRollup.bucket_minutes == bucket_minutes,
        ).scalar()

        if latest_ts:
            try:
                latest_epoch = datetime.fromisoformat(
                    latest_ts.replace(" ", "T") + "+00:00"
                ).timestamp()
                from_epoch = latest_epoch + bucket_seconds
            except ValueError:
                from_epoch = 0.0
        else:
            earliest = sess.query(
                func.min(BandMeasurement.timestamp)
            ).filter(BandMeasurement.band_id == band_id).scalar()
            if not earliest:
                return 0
            try:
                raw_epoch  = datetime.fromisoformat(
                    earliest.replace(" ", "T") + "+00:00"
                ).timestamp()
                from_epoch = (raw_epoch // bucket_seconds) * bucket_seconds
            except ValueError:
                return 0

    if from_epoch >= to_epoch:
        return 0

    from_ts = datetime.fromtimestamp(from_epoch, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    to_ts   = datetime.fromtimestamp(to_epoch,   tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    with get_engine().connect() as conn:
        result = conn.execute(_COMPUTE_SQL, {
            "band_id":        band_id,
            "bucket_minutes": bucket_minutes,
            "bucket_seconds": bucket_seconds,
            "from_ts":        from_ts,
            "to_ts":          to_ts,
        })
        conn.commit()

    rows = result.rowcount
    if rows:
        log.info("Rollup %s@%dm: +%d rows (%s → %s)", band_id, bucket_minutes, rows, from_ts, to_ts)
    return rows


def cleanup_rollup_tier(bucket_minutes: int, retention_days: int) -> int:
    """Delete rollup rows older than retention_days for this tier."""
    with _session() as sess:
        cutoff = func.datetime("now", f"-{retention_days} days")
        n = sess.query(BandMeasurementRollup).filter(
            BandMeasurementRollup.bucket_minutes == bucket_minutes,
            BandMeasurementRollup.bucket_ts      <  cutoff,
        ).delete(synchronize_session=False)
        sess.commit()
        return n


# ── shared filter helper ──────────────────────────────────────────────────────

def _apply_rollup_filters(q, filters: dict | None):
    if not filters:
        return q
    if "freq_min" in filters:
        q = q.filter(BandMeasurementRollup.frequency_mhz >= filters["freq_min"])
    if "freq_max" in filters:
        q = q.filter(BandMeasurementRollup.frequency_mhz <= filters["freq_max"])
    if "time_min" in filters:
        q = q.filter(BandMeasurementRollup.bucket_ts >= filters["time_min"])
    if "time_max" in filters:
        q = q.filter(BandMeasurementRollup.bucket_ts <= filters["time_max"])
    if "power_min" in filters:
        q = q.filter(BandMeasurementRollup.avg_db >= filters["power_min"])
    return q


_MAX_BUCKETS = 300


def _meta(sess, band_id: str, bucket_minutes: int, filters: dict | None):
    q = sess.query(
        func.count(BandMeasurementRollup.bucket_ts.distinct()).label("n"),
        func.min(BandMeasurementRollup.bucket_ts).label("ts_min"),
        func.max(BandMeasurementRollup.bucket_ts).label("ts_max"),
    ).filter(
        BandMeasurementRollup.band_id        == band_id,
        BandMeasurementRollup.bucket_minutes == bucket_minutes,
    )
    return _apply_rollup_filters(q, filters).one()


def _compress_bucket(meta, bucket_minutes: int):
    """Return a further-compressed bucket SQLAlchemy expression if n > _MAX_BUCKETS."""
    n = meta.n or 0
    if n <= _MAX_BUCKETS:
        return None, n
    try:
        t0       = datetime.fromisoformat(str(meta.ts_min).replace(" ", "T"))
        t1       = datetime.fromisoformat(str(meta.ts_max).replace(" ", "T"))
        total_s  = max((t1 - t0).total_seconds(), 1)
    except (ValueError, TypeError):
        total_s  = n * bucket_minutes * 60
    compress_s   = max(math.ceil(total_s / _MAX_BUCKETS), bucket_minutes * 60)
    epoch        = func.strftime("%s", BandMeasurementRollup.bucket_ts)
    return func.datetime(epoch - epoch % compress_s, "unixepoch"), n


# ── query functions ───────────────────────────────────────────────────────────

def fetch_rollup_measurements(band_id: str, bucket_minutes: int,
                               filters: dict | None, agg: str = "avg") -> list[tuple]:
    """Return [(timestamp, frequency_mhz, power_db)] from rollup."""
    with _session() as sess:
        meta        = _meta(sess, band_id, bucket_minutes, filters)
        bucket_expr, n = _compress_bucket(meta, bucket_minutes)
        agg_col     = BandMeasurementRollup.max_db if agg == "max" else BandMeasurementRollup.avg_db

        if bucket_expr is None:
            q = sess.query(
                BandMeasurementRollup.bucket_ts,
                BandMeasurementRollup.frequency_mhz,
                agg_col,
            ).filter(
                BandMeasurementRollup.band_id        == band_id,
                BandMeasurementRollup.bucket_minutes == bucket_minutes,
            )
            q = _apply_rollup_filters(q, filters)
            return q.order_by(BandMeasurementRollup.bucket_ts).all()

        agg_func = func.max if agg == "max" else func.avg
        q = sess.query(
            bucket_expr.label("bucket_ts"),
            BandMeasurementRollup.frequency_mhz,
            agg_func(agg_col).label("power_db"),
        ).filter(
            BandMeasurementRollup.band_id        == band_id,
            BandMeasurementRollup.bucket_minutes == bucket_minutes,
        )
        q = _apply_rollup_filters(q, filters)
        q = q.group_by(bucket_expr, BandMeasurementRollup.frequency_mhz)
        return q.order_by(bucket_expr, BandMeasurementRollup.frequency_mhz).all()


def fetch_rollup_timeseries(band_id: str, bucket_minutes: int,
                             freq_mhz: float, filters: dict | None) -> list[dict]:
    """Return [{timestamp, power_db}] from rollup for one frequency."""
    with _session() as sess:
        q = sess.query(
            BandMeasurementRollup.bucket_ts,
            BandMeasurementRollup.avg_db,
        ).filter(
            BandMeasurementRollup.band_id        == band_id,
            BandMeasurementRollup.bucket_minutes == bucket_minutes,
            BandMeasurementRollup.frequency_mhz  == freq_mhz,
        )
        q = _apply_rollup_filters(q, filters)
        return [{"timestamp": r.bucket_ts, "power_db": r.avg_db}
                for r in q.order_by(BandMeasurementRollup.bucket_ts).all()]


def fetch_rollup_stats(band_id: str, bucket_minutes: int,
                        filters: dict | None) -> list[dict]:
    """Return [{frequency_mhz, mean_db, peak_db}] from rollup."""
    with _session() as sess:
        q = sess.query(
            BandMeasurementRollup.frequency_mhz,
            func.avg(BandMeasurementRollup.avg_db).label("mean_db"),
            func.max(BandMeasurementRollup.max_db).label("peak_db"),
        ).filter(
            BandMeasurementRollup.band_id        == band_id,
            BandMeasurementRollup.bucket_minutes == bucket_minutes,
        )
        q = _apply_rollup_filters(q, filters)
        q = q.group_by(BandMeasurementRollup.frequency_mhz)
        return [
            {"frequency_mhz": r.frequency_mhz, "mean_db": r.mean_db, "peak_db": r.peak_db}
            for r in q.order_by(BandMeasurementRollup.frequency_mhz).all()
        ]


def fetch_rollup_activity(band_id: str, bucket_minutes: int,
                           threshold_db: float, filters: dict | None) -> list[dict]:
    """Return [{frequency_mhz, active, total}] from rollup.

    A bucket is counted active if max_db >= threshold_db.
    """
    with _session() as sess:
        active_expr = func.sum(
            case((BandMeasurementRollup.max_db >= threshold_db, 1), else_=0)
        )
        q = sess.query(
            BandMeasurementRollup.frequency_mhz,
            active_expr.label("active"),
            func.count(BandMeasurementRollup.id).label("total"),
        ).filter(
            BandMeasurementRollup.band_id        == band_id,
            BandMeasurementRollup.bucket_minutes == bucket_minutes,
        )
        q = _apply_rollup_filters(q, filters)
        q = q.group_by(BandMeasurementRollup.frequency_mhz)
        return [
            {"frequency_mhz": r.frequency_mhz, "active": r.active, "total": r.total}
            for r in q.order_by(BandMeasurementRollup.frequency_mhz).all()
        ]


def fetch_rollup_histogram(band_id: str, bucket_minutes: int,
                            filters: dict | None) -> list[float]:
    """Return avg_db values from rollup for histogram building."""
    with _session() as sess:
        q = sess.query(BandMeasurementRollup.avg_db).filter(
            BandMeasurementRollup.band_id        == band_id,
            BandMeasurementRollup.bucket_minutes == bucket_minutes,
        )
        q = _apply_rollup_filters(q, filters)
        return [r[0] for r in q.all()]


def fetch_rollup_signal_raw(band_id: str, bucket_minutes: int,
                             threshold_db: float, filters: dict | None) -> list[dict]:
    """Return [{timestamp, frequency_mhz, power_db}] from rollup where max_db >= threshold."""
    with _session() as sess:
        q = sess.query(
            BandMeasurementRollup.bucket_ts,
            BandMeasurementRollup.frequency_mhz,
            BandMeasurementRollup.max_db,
        ).filter(
            BandMeasurementRollup.band_id        == band_id,
            BandMeasurementRollup.bucket_minutes == bucket_minutes,
            BandMeasurementRollup.max_db         >= threshold_db,
        )
        q = _apply_rollup_filters(q, filters)
        q = q.order_by(BandMeasurementRollup.frequency_mhz, BandMeasurementRollup.bucket_ts)
        return [
            {"timestamp": r.bucket_ts, "frequency_mhz": r.frequency_mhz, "power_db": r.max_db}
            for r in q.all()
        ]
