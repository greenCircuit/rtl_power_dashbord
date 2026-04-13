"""Per-frequency measurement queries and bulk insert."""

import logging
import math
from datetime import datetime

from sqlalchemy import case, func

from ._engine import BandMeasurement, _session, _apply_filters

log = logging.getLogger(__name__)

_HEATMAP_MAX_SWEEPS = 300


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


def fetch_band_measurements(band_id: str, filters: dict | None = None,
                            agg: str = "avg") -> list[tuple]:
    """Return [(timestamp, frequency_mhz, power_db), ...].

    *agg* controls how readings are combined when the dataset exceeds
    _HEATMAP_MAX_SWEEPS distinct timestamps:
      ``"avg"`` (default) — mean power per bucket (standard heatmap)
      ``"max"``           — peak power per bucket (max-hold heatmap)

    Small datasets (≤ _HEATMAP_MAX_SWEEPS sweeps) always return every raw row;
    the caller's pivot/aggfunc handles the per-cell aggregation.
    """
    with _session() as sess:
        # ── Step 1: cheap metadata scan ───────────────────────────────────────
        meta_q = sess.query(
            func.count(BandMeasurement.timestamp.distinct()).label("n_sweeps"),
            func.min(BandMeasurement.timestamp).label("ts_min"),
            func.max(BandMeasurement.timestamp).label("ts_max"),
        ).filter(BandMeasurement.band_id == band_id)
        meta_q = _apply_filters(meta_q, filters)
        meta = meta_q.one()

        n_sweeps = meta.n_sweeps or 0

        # ── Step 2a: small dataset — return every raw row ─────────────────────
        if n_sweeps <= _HEATMAP_MAX_SWEEPS:
            q = sess.query(
                BandMeasurement.timestamp,
                BandMeasurement.frequency_mhz,
                BandMeasurement.power_db,
            ).filter(BandMeasurement.band_id == band_id)
            q = _apply_filters(q, filters)
            return q.order_by(BandMeasurement.timestamp).all()

        # ── Step 2b: large dataset — aggregate into time buckets in SQL ───────
        try:
            ts_min = datetime.fromisoformat(str(meta.ts_min).replace(" ", "T"))
            ts_max = datetime.fromisoformat(str(meta.ts_max).replace(" ", "T"))
            total_s = max((ts_max - ts_min).total_seconds(), 1)
        except (ValueError, TypeError):
            total_s = n_sweeps  # fallback: treat each sweep as 1 second

        bucket_s = max(math.ceil(total_s / _HEATMAP_MAX_SWEEPS), 1)

        # Round each timestamp down to the nearest bucket boundary using modulo
        # arithmetic (avoids CAST-to-NUMERIC float-division issue in SQLAlchemy).
        ts_epoch = func.strftime("%s", BandMeasurement.timestamp)
        bucket_expr = func.datetime(
            ts_epoch - ts_epoch % bucket_s,
            "unixepoch",
        )

        agg_func = func.max if agg == "max" else func.avg
        q = sess.query(
            bucket_expr.label("timestamp"),
            BandMeasurement.frequency_mhz,
            agg_func(BandMeasurement.power_db).label("power_db"),
        ).filter(BandMeasurement.band_id == band_id)
        q = _apply_filters(q, filters)
        q = q.group_by(bucket_expr, BandMeasurement.frequency_mhz)
        q = q.order_by(bucket_expr, BandMeasurement.frequency_mhz)
        return q.all()


def fetch_band_stats(band_id: str, filters: dict | None = None) -> list[dict]:
    """Return per-frequency mean and peak: [{frequency_mhz, mean_db, peak_db}]."""
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
    """Return [{timestamp, power_db}] for the given frequency."""
    with _session() as sess:
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
    """Return all power_db values for the band (used to build a histogram)."""
    with _session() as sess:
        q = sess.query(BandMeasurement.power_db).filter(
            BandMeasurement.band_id == band_id
        )
        q = _apply_filters(q, filters)
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
        # Float division for correct sort in SQLite
        q = q.order_by((active_expr * 1.0 / total_expr).desc())
        q = q.limit(limit)
        return [
            {"frequency_mhz": r.frequency_mhz, "active": r.active,
             "total": r.total, "mean_db": r.mean_db}
            for r in q.all()
        ]


def fetch_band_signal_raw(band_id: str, threshold_db: float,
                          filters: dict | None = None) -> list[dict]:
    """Return [{timestamp, frequency_mhz, power_db}] ordered by freq then time."""
    with _session() as sess:
        q = sess.query(
            BandMeasurement.timestamp,
            BandMeasurement.frequency_mhz,
            BandMeasurement.power_db,
        ).filter(BandMeasurement.band_id == band_id)
        q = _apply_filters(q, filters)
        q = q.order_by(BandMeasurement.frequency_mhz, BandMeasurement.timestamp)
        return [{"timestamp": r.timestamp, "frequency_mhz": r.frequency_mhz,
                 "power_db": r.power_db}
                for r in q.all()]
