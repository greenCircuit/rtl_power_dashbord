"""
SQLAlchemy database layer — band management and measurement queries.
"""

import logging
from pathlib import Path

import yaml
from sqlalchemy import (
    Boolean, Column, Float, Index, Integer, String, Text,
    case, create_engine, event, func, text,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import BANDS_CONFIG, DB_PATH

log = logging.getLogger(__name__)


# ── ORM models ────────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


class Band(Base):
    __tablename__ = "bands"

    id           = Column(String, primary_key=True)
    name         = Column(String, nullable=False)
    freq_start   = Column(String, nullable=False)
    freq_end     = Column(String, nullable=False)
    freq_step    = Column(String, nullable=False)
    interval_s   = Column(Integer, default=10)
    min_power    = Column(Float,   default=2.0)
    device_index = Column(Integer, default=0)
    is_active    = Column(Boolean, default=False)


class BandMeasurement(Base):
    __tablename__ = "band_measurements"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    band_id       = Column(String, nullable=False)
    timestamp     = Column(Text,   nullable=False)
    frequency_mhz = Column(Float,  nullable=False)
    power_db      = Column(Float,  nullable=False)

    __table_args__ = (
        Index("ix_bm_band_ts",   "band_id", "timestamp"),
        Index("ix_bm_band_freq", "band_id", "frequency_mhz"),
    )


# ── Engine / session factory ──────────────────────────────────────────────────

_engine = None
_Session: sessionmaker | None = None


def get_engine():
    global _engine
    if _engine is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(
            f"sqlite:///{DB_PATH}",
            connect_args={"check_same_thread": False},
        )

        @event.listens_for(_engine, "connect")
        def _set_pragmas(dbapi_conn, _record):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.execute("PRAGMA cache_size=-16384")
            cur.execute("PRAGMA temp_store=MEMORY")
            cur.close()

    return _engine


def _session() -> Session:
    global _Session
    if _Session is None:
        _Session = sessionmaker(bind=get_engine())
    return _Session()


# ── Init / seed ───────────────────────────────────────────────────────────────

def init_db() -> None:
    Base.metadata.create_all(get_engine())
    log.info("Database tables created/verified at %s", DB_PATH)


def seed_bands_from_yaml(config_path: Path = BANDS_CONFIG) -> None:
    if not config_path.exists():
        log.warning("Bands config not found: %s", config_path)
        return
    with open(config_path) as fh:
        cfg = yaml.safe_load(fh)
    bands = cfg.get("bands", []) if cfg else []
    with _session() as sess:
        for b in bands:
            if sess.get(Band, b["id"]) is None:
                sess.add(Band(
                    id=str(b["id"]),
                    name=str(b["name"]),
                    freq_start=str(b["freq_start"]),
                    freq_end=str(b["freq_end"]),
                    freq_step=str(b["freq_step"]),
                    interval_s=int(b.get("interval_s", 10)),
                    min_power=float(b.get("min_power", 2.0)),
                    device_index=int(b.get("device_index", 0)),
                    is_active=bool(b.get("is_active", False)),
                ))
                log.info("Seeded band: %s (%s)", b["id"], b["name"])
        sess.commit()


# ── Band CRUD ─────────────────────────────────────────────────────────────────

def _to_dict(b: Band) -> dict:
    return {
        "id":           b.id,
        "name":         b.name,
        "freq_start":   b.freq_start,
        "freq_end":     b.freq_end,
        "freq_step":    b.freq_step,
        "interval_s":   b.interval_s,
        "min_power":    b.min_power,
        "device_index": b.device_index,
        "is_active":    bool(b.is_active),
    }


def list_bands() -> list[dict]:
    with _session() as sess:
        return [_to_dict(b) for b in sess.query(Band).order_by(Band.name).all()]


def get_band(band_id: str) -> dict | None:
    with _session() as sess:
        b = sess.get(Band, band_id)
        return _to_dict(b) if b else None


def create_band(band_id, name, freq_start, freq_end, freq_step,
                interval_s, min_power, device_index, is_active) -> None:
    with _session() as sess:
        if sess.get(Band, band_id):
            raise ValueError(f"Band {band_id!r} already exists")
        sess.add(Band(
            id=band_id, name=name,
            freq_start=str(freq_start), freq_end=str(freq_end), freq_step=str(freq_step),
            interval_s=int(interval_s), min_power=float(min_power),
            device_index=int(device_index), is_active=bool(is_active),
        ))
        sess.commit()


def update_band(band_id, name, freq_start, freq_end, freq_step,
                interval_s, min_power, device_index, is_active) -> None:
    with _session() as sess:
        b = sess.get(Band, band_id)
        if not b:
            raise ValueError(f"Band {band_id!r} not found")
        b.name         = name
        b.freq_start   = str(freq_start)
        b.freq_end     = str(freq_end)
        b.freq_step    = str(freq_step)
        b.interval_s   = int(interval_s)
        b.min_power    = float(min_power)
        b.device_index = int(device_index)
        b.is_active    = bool(is_active)
        sess.commit()


def delete_band(band_id: str) -> None:
    with _session() as sess:
        sess.query(BandMeasurement).filter(BandMeasurement.band_id == band_id).delete()
        b = sess.get(Band, band_id)
        if b:
            sess.delete(b)
        sess.commit()


# ── Measurement write (called from capture thread) ────────────────────────────

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


# ── Measurement queries ───────────────────────────────────────────────────────

def _apply_filters(q, filters: dict | None):
    """Apply optional WHERE clauses to a BandMeasurement query."""
    if not filters:
        return q
    if "freq_min" in filters:
        q = q.filter(BandMeasurement.frequency_mhz >= filters["freq_min"])
    if "freq_max" in filters:
        q = q.filter(BandMeasurement.frequency_mhz <= filters["freq_max"])
    if "time_min" in filters:
        q = q.filter(BandMeasurement.timestamp >= filters["time_min"])
    if "time_max" in filters:
        q = q.filter(BandMeasurement.timestamp <= filters["time_max"])
    return q


def fetch_band_measurements(band_id: str, filters: dict | None = None) -> list[tuple]:
    """Return [(timestamp, frequency_mhz, power_db), ...]."""
    with _session() as sess:
        q = sess.query(
            BandMeasurement.timestamp,
            BandMeasurement.frequency_mhz,
            BandMeasurement.power_db,
        ).filter(BandMeasurement.band_id == band_id)
        q = _apply_filters(q, filters)
        return q.order_by(BandMeasurement.timestamp).all()


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
        # Subquery: rows within 1 hour of the latest timestamp
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
                                 filters: dict | None = None,
                                 bucket_minutes: int = 15) -> list[dict]:
    """Return time-bucketed activity [{bucket, active, total}]."""
    with _session() as sess:
        # Truncate timestamp to the hour for bucketing
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


def cleanup_old_data(max_time_hrs: int, db_max_size_mb: int) -> dict:
    """Delete measurements that are too old OR trim DB when it exceeds the size cap.

    Rules are OR — either condition triggers a delete pass.
    Returns a summary dict with rows deleted and final DB size.
    """
    deleted_age  = 0
    deleted_size = 0

    with _session() as sess:
        # ── Rule 1: delete rows older than max_time_hrs ───────────────────────
        cutoff = func.datetime("now", f"-{max_time_hrs} hours")
        deleted_age = (
            sess.query(BandMeasurement)
            .filter(BandMeasurement.timestamp < cutoff)
            .delete(synchronize_session=False)
        )
        sess.commit()

        # ── Rule 2: if DB is still over the size cap, drop oldest rows ────────
        if DB_PATH.exists():
            size_mb = DB_PATH.stat().st_size / 1_048_576
            if size_mb > db_max_size_mb:
                # Delete in chunks of 50k oldest rows until under the limit
                while size_mb > db_max_size_mb:
                    subq = (
                        sess.query(BandMeasurement.id)
                        .order_by(BandMeasurement.timestamp)
                        .limit(50_000)
                        .subquery()
                    )
                    n = (
                        sess.query(BandMeasurement)
                        .filter(BandMeasurement.id.in_(subq))
                        .delete(synchronize_session=False)
                    )
                    sess.commit()
                    deleted_size += n
                    if n == 0:
                        break
                    size_mb = DB_PATH.stat().st_size / 1_048_576

    # Reclaim space after bulk deletes
    with get_engine().connect() as conn:
        conn.execute(text("VACUUM"))

    final_mb = round(DB_PATH.stat().st_size / 1_048_576, 2) if DB_PATH.exists() else 0.0
    return {
        "deleted_by_age":  deleted_age,
        "deleted_by_size": deleted_size,
        "db_size_mb":      final_mb,
    }


def fetch_db_status() -> dict:
    """Return DB file size and per-band measurement counts / last capture time."""
    size_mb = round(DB_PATH.stat().st_size / 1_048_576, 2) if DB_PATH.exists() else 0.0
    with _session() as sess:
        rows = sess.query(
            BandMeasurement.band_id,
            func.count(BandMeasurement.id).label("count"),
            func.max(BandMeasurement.timestamp).label("last_seen"),
        ).group_by(BandMeasurement.band_id).all()
    return {
        "db_size_mb": size_mb,
        "bands": [
            {"band_id": r.band_id, "count": r.count, "last_seen": r.last_seen}
            for r in rows
        ],
    }


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
