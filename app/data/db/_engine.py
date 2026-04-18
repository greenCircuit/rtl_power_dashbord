"""
ORM models, engine / session factory, shared query helpers.
Everything else in this package imports from here.
"""

import logging

from sqlalchemy import (
    Boolean, Column, Float, Index, Integer, String, Text, UniqueConstraint,
    create_engine, event,
)
from sqlalchemy.pool import NullPool
from contextlib import contextmanager

from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import BANDS_CONFIG, DB_PATH  # noqa: F401 — re-exported for sub-modules

log = logging.getLogger(__name__)


# ── ORM models ────────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


class Band(Base):
    __tablename__ = "bands"

    id           = Column(String,  primary_key=True)
    name         = Column(String,  nullable=False)
    freq_start   = Column(String,  nullable=False)
    freq_end     = Column(String,  nullable=False)
    freq_step    = Column(String,  nullable=False)
    interval_s   = Column(Integer, default=10)
    min_power    = Column(Float,   default=2.0)
    device_index = Column(Integer, default=0)
    is_active    = Column(Boolean, default=False)


class BandMeasurement(Base):
    __tablename__ = "band_measurements"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    band_id       = Column(String,  nullable=False)
    timestamp     = Column(Text,    nullable=False)
    frequency_mhz = Column(Float,   nullable=False)
    power_db      = Column(Float,   nullable=False)

    __table_args__ = (
        Index("ix_bm_band_ts",   "band_id", "timestamp"),
        Index("ix_bm_band_freq", "band_id", "frequency_mhz"),
    )


class BandMeasurementRollup(Base):
    """Pre-aggregated measurements bucketed by time interval.

    One row per (band_id, bucket_minutes, bucket_ts, frequency_mhz).
    bucket_minutes identifies the tier (e.g. 15 or 60).
    INSERT OR REPLACE relies on uq_rollup_bucket for idempotency.
    """
    __tablename__ = "band_measurements_rollup"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    band_id        = Column(String,  nullable=False)
    bucket_minutes = Column(Integer, nullable=False)
    bucket_ts      = Column(Text,    nullable=False)
    frequency_mhz  = Column(Float,   nullable=False)
    avg_db         = Column(Float,   nullable=False)
    max_db         = Column(Float,   nullable=False)
    min_db         = Column(Float,   nullable=False)
    sample_count   = Column(Integer, nullable=False, default=1)

    __table_args__ = (
        UniqueConstraint(
            "band_id", "bucket_minutes", "bucket_ts", "frequency_mhz",
            name="uq_rollup_bucket",
        ),
        Index("ix_rollup_lookup", "band_id", "bucket_minutes", "bucket_ts"),
    )


# ── Engine / session factory ──────────────────────────────────────────────────

_engine = None
_session_factory: sessionmaker | None = None


def get_engine():
    global _engine
    if _engine is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(
            f"sqlite:///{DB_PATH}",
            connect_args={"check_same_thread": False},
            poolclass=NullPool,
        )
        log.info("SQLite engine initialised — db=%s poolclass=NullPool", DB_PATH)

        @event.listens_for(_engine, "connect")
        def _set_pragmas(dbapi_conn, _record):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.execute("PRAGMA cache_size=-16384")
            cur.execute("PRAGMA temp_store=MEMORY")
            cur.close()

    return _engine


def _make_session() -> Session:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=get_engine())
    return _session_factory()


@contextmanager
def _session():
    """Yield a SQLAlchemy session.

    Inside a Flask request context: reuses the single session stored on
    ``flask.g`` so all DB calls within one request share one connection.
    Cleanup is handled by the ``teardown_appcontext`` hook in
    ``app/__init__.py``.

    Outside a Flask context (startup, background threads, unit tests without
    a test client): opens a fresh session and closes it on context exit.
    """
    from flask import g, has_app_context  # lazy import — avoids coupling at module load
    if has_app_context():
        if not hasattr(g, "_db_session"):
            g._db_session = _make_session()
        yield g._db_session
    else:
        sess = _make_session()
        try:
            yield sess
        finally:
            sess.close()


# ── Schema init ───────────────────────────────────────────────────────────────

def init_db() -> None:
    Base.metadata.create_all(get_engine())
    log.info("Database tables created/verified at %s", DB_PATH)


# ── Shared query helper ───────────────────────────────────────────────────────

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
    if "power_min" in filters:
        q = q.filter(BandMeasurement.power_db >= filters["power_min"])
    return q
