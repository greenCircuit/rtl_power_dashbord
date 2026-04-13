"""
ORM models, engine / session factory, shared query helpers.
Everything else in this package imports from here.
"""

import logging

from sqlalchemy import (
    Boolean, Column, Float, Index, Integer, String, Text,
    create_engine, event,
)
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
