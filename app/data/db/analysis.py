"""Time-bucketed / trend analysis queries."""

from sqlalchemy import Integer, case, func

from ._engine import BandMeasurement, _session, _apply_filters

# Supported granularity labels → bucket width in seconds.
# This is the single source of truth; app/api/routes/_helpers.py derives
# VALID_GRANULARITIES from these keys at import time.
GRANULARITY_SECONDS: dict[str, int] = {
    "15m": 900,
    "30m": 1800,
    "1h":  3600,
    "6h":  21600,
    "1d":  86400,
}


def fetch_band_tod_activity(band_id: str, threshold_db: float,
                            filters: dict | None = None) -> list[dict]:
    """Return per-(day-of-week, hour) activity [{dow, hour, active, total}].

    dow: 0=Sunday … 6=Saturday  (SQLite strftime('%w')).
    """
    with _session() as sess:
        dow_expr    = func.cast(func.strftime("%w", BandMeasurement.timestamp), Integer)
        hour_expr   = func.cast(func.strftime("%H", BandMeasurement.timestamp), Integer)
        active_expr = func.sum(
            case((BandMeasurement.power_db >= threshold_db, 1), else_=0)
        )
        q = sess.query(
            dow_expr.label("dow"),
            hour_expr.label("hour"),
            active_expr.label("active"),
            func.count(BandMeasurement.id).label("total"),
        ).filter(BandMeasurement.band_id == band_id)
        q = _apply_filters(q, filters)
        q = q.group_by(dow_expr, hour_expr).order_by(dow_expr, hour_expr)
        return [
            {"dow": r.dow, "hour": r.hour, "active": r.active, "total": r.total}
            for r in q.all()
        ]


def fetch_band_activity_timeline(band_id: str, threshold_db: float,
                                 filters: dict | None = None) -> list[dict]:
    """Return time-bucketed activity [{bucket, active, total}]."""
    with _session() as sess:
        bucket_expr = func.strftime("%Y-%m-%dT%H:00", BandMeasurement.timestamp)
        active_expr = func.sum(
            case((BandMeasurement.power_db >= threshold_db, 1), else_=0)
        )
        q = sess.query(
            bucket_expr.label("bucket"),
            active_expr.label("active"),
            func.count(BandMeasurement.id).label("total"),
        ).filter(BandMeasurement.band_id == band_id)
        q = _apply_filters(q, filters)
        q = q.group_by(bucket_expr).order_by(bucket_expr)
        return [{"bucket": r.bucket, "active": r.active, "total": r.total} for r in q.all()]


def fetch_band_activity_trend(band_id: str, threshold_db: float,
                              granularity: str = "1h",
                              filters: dict | None = None) -> list[dict]:
    """Return time-bucketed overall activity percentage.

    *granularity* is one of: ``5m``, ``15m``, ``1h``, ``6h``, ``1d``
    (or legacy ``hour`` / ``day``).

    Uses Unix-epoch integer arithmetic so any bucket width is supported:
    ``datetime(epoch - epoch % width, 'unixepoch')`` truncates to the
    nearest multiple of *width* seconds.

    Returns ``[{bucket, active, total}]``.
    """
    width = GRANULARITY_SECONDS.get(granularity, 3600)
    ts_epoch = func.strftime("%s", BandMeasurement.timestamp)
    bucket_expr = func.datetime(
        ts_epoch - ts_epoch % width,
        "unixepoch",
    )
    active_expr = func.sum(
        case((BandMeasurement.power_db >= threshold_db, 1), else_=0)
    )
    with _session() as sess:
        q = sess.query(
            bucket_expr.label("bucket"),
            active_expr.label("active"),
            func.count(BandMeasurement.id).label("total"),
        ).filter(BandMeasurement.band_id == band_id)
        q = _apply_filters(q, filters)
        q = q.group_by(bucket_expr).order_by(bucket_expr)
        return [{"bucket": r.bucket, "active": r.active, "total": r.total}
                for r in q.all()]


def fetch_band_power_envelope(band_id: str, granularity: str = "1h",
                              filters: dict | None = None) -> list[dict]:
    """Return per-time-bucket min/mean/max power.

    [{bucket, min_db, mean_db, max_db}] — used for noise-floor and peak-power
    trend charts.  *granularity* uses the same keys as fetch_band_activity_trend.
    """
    width = GRANULARITY_SECONDS.get(granularity, 3600)
    ts_epoch = func.strftime("%s", BandMeasurement.timestamp)
    bucket_expr = func.datetime(
        ts_epoch - ts_epoch % width,
        "unixepoch",
    )
    with _session() as sess:
        q = sess.query(
            bucket_expr.label("bucket"),
            func.min(BandMeasurement.power_db).label("min_db"),
            func.avg(BandMeasurement.power_db).label("mean_db"),
            func.max(BandMeasurement.power_db).label("max_db"),
        ).filter(BandMeasurement.band_id == band_id)
        q = _apply_filters(q, filters)
        q = q.group_by(bucket_expr).order_by(bucket_expr)
        return [
            {"bucket": r.bucket, "min_db": r.min_db,
             "mean_db": r.mean_db, "max_db": r.max_db}
            for r in q.all()
        ]
