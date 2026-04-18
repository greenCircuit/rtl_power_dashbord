import pytest
import app.data.db as db_module
import app.data.db._engine as db_engine_module
from app.data.db import init_db


def _reset_engine(monkeypatch):
    """Reset the cached SQLAlchemy engine so the next call to get_engine()
    creates a fresh one pointed at the monkeypatched DB_PATH."""
    monkeypatch.setattr(db_engine_module, "_engine", None)
    monkeypatch.setattr(db_engine_module, "_session_factory", None)


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """Redirect all DB operations to a temp file and initialise the schema."""
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(db_engine_module, "DB_PATH", db_path)
    _reset_engine(monkeypatch)
    init_db()
    return db_path


@pytest.fixture
def flask_client(tmp_path, monkeypatch):
    """Flask test client with an isolated temp database.

    - DB is redirected to a fresh temp file.
    - YAML band seeding is skipped so tests control all data.
    """
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(db_engine_module, "DB_PATH", db_path)
    _reset_engine(monkeypatch)

    import app as app_module
    monkeypatch.setattr(app_module, "seed_bands_from_yaml", lambda *a, **kw: None)
    monkeypatch.setattr(app_module, "DEMO_MODE", False)

    from app import create_app
    flask_app = create_app()
    flask_app.config["TESTING"] = True
    return flask_app.test_client()


def insert_measurements(band_id: str, rows: list[tuple]) -> None:
    """Helper: write (timestamp, frequency_mhz, power_db) rows into the temp DB.

    Requires that the band already exists and that db_module.DB_PATH is patched
    to a temp path (i.e., call this inside a test that uses the flask_client or
    tmp_db fixture).
    """
    with db_module.get_engine().connect() as conn:
        db_module.insert_band_measurements(conn, band_id, rows)
        conn.commit()
