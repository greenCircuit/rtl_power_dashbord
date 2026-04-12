#!/usr/bin/env python3
"""
Export the last N sweeps per band from the live DB into demo/seed.db.

Usage (from project root):
    python demo/export_seed.py               # last 60 sweeps per band
    python demo/export_seed.py --sweeps 120  # last 120 sweeps per band
"""

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import DB_PATH, DEMO_SEED_DB


SCHEMA = """
CREATE TABLE IF NOT EXISTS band_measurements (
    band_id       TEXT NOT NULL,
    timestamp     TEXT NOT NULL,
    frequency_mhz REAL NOT NULL,
    power_db      REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_bm_band_time
    ON band_measurements (band_id, timestamp);
"""


def export(n_sweeps: int) -> None:
    if not DB_PATH.exists():
        print(f"Live DB not found: {DB_PATH}")
        sys.exit(1)

    DEMO_SEED_DB.parent.mkdir(parents=True, exist_ok=True)

    src = sqlite3.connect(str(DB_PATH))
    src.row_factory = sqlite3.Row

    dst = sqlite3.connect(str(DEMO_SEED_DB))
    dst.executescript(SCHEMA)
    dst.execute("DELETE FROM band_measurements")

    band_ids = [r[0] for r in src.execute("SELECT DISTINCT band_id FROM band_measurements")]
    if not band_ids:
        print("No band_measurements in live DB")
        sys.exit(0)

    total = 0
    for band_id in band_ids:
        # Get the last n_sweeps distinct timestamps for this band
        ts_rows = src.execute(
            "SELECT DISTINCT timestamp FROM band_measurements WHERE band_id = ? "
            "ORDER BY timestamp DESC LIMIT ?",
            (band_id, n_sweeps),
        ).fetchall()
        if not ts_rows:
            continue
        timestamps = [r[0] for r in ts_rows]
        placeholders = ",".join("?" * len(timestamps))
        rows = src.execute(
            f"SELECT band_id, timestamp, frequency_mhz, power_db FROM band_measurements "
            f"WHERE band_id = ? AND timestamp IN ({placeholders})",
            (band_id, *timestamps),
        ).fetchall()
        dst.executemany(
            "INSERT INTO band_measurements VALUES (?,?,?,?)",
            [(r["band_id"], r["timestamp"], r["frequency_mhz"], r["power_db"]) for r in rows],
        )
        print(f"  {band_id}: {len(rows)} rows ({len(timestamps)} sweeps)")
        total += len(rows)

    dst.execute("PRAGMA journal_mode=WAL")
    dst.commit()
    src.close()
    dst.close()
    print(f"\nExported {total} rows → {DEMO_SEED_DB}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Export seed data for demo mode")
    parser.add_argument("--sweeps", type=int, default=60,
                        help="Number of sweeps to export per band (default: 60)")
    args = parser.parse_args()
    export(args.sweeps)


if __name__ == "__main__":
    main()
