import sqlite3
import pytest
import app.data.db as db_module
from app.data.db import init_db


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """Redirect all DB operations to a temp file and initialise the schema."""
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    init_db()
    return db_path


@pytest.fixture
def flask_client(tmp_path, monkeypatch):
    """Flask test client with an isolated temp database.

    - DB is redirected to a fresh temp file.
    - YAML band seeding and CSV migration are skipped so tests control all data.
    """
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(db_module, "DB_PATH", db_path)

    import app as app_module
    monkeypatch.setattr(app_module, "seed_bands_from_yaml", lambda *a, **kw: None)
    monkeypatch.setattr(app_module, "migrate_csv_sessions", lambda *a, **kw: None)

    from app import create_app
    flask_app = create_app()
    flask_app.config["TESTING"] = True
    return flask_app.test_client()


def insert_measurements(band_id: str, rows: list[tuple]) -> None:
    """Helper: write (timestamp, frequency_mhz, power_db) rows into temp DB.

    Requires that the band already exists and that db_module.DB_PATH is patched
    to a temp path (i.e., call this inside a test that uses the flask_client or
    tmp_db fixture).
    """
    conn = sqlite3.connect(str(db_module.DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    db_module.insert_band_measurements(conn, band_id, rows)
    conn.commit()
    conn.close()
