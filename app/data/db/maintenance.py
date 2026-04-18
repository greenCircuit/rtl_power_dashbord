"""Database maintenance — cleanup and status reporting."""

import logging

from sqlalchemy import func, text

from ._engine import BandMeasurement, DB_PATH, _session, get_engine

log = logging.getLogger(__name__)


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
    bands = [
        {"band_id": r.band_id, "count": r.count, "last_seen": r.last_seen}
        for r in rows
    ]
    log.debug("DB status: size=%.2f MB, bands=%d, total_rows=%d",
              size_mb, len(bands), sum(b["count"] for b in bands))
    return {"db_size_mb": size_mb, "bands": bands}
