import logging
import os
import subprocess

from flask import Flask, render_template

from app.config import configure_logging, DATA_DIR, BANDS_CONFIG
from app.data.db import init_db, seed_bands_from_yaml, list_bands
from app.data.parser import migrate_csv_sessions

configure_logging()
log = logging.getLogger(__name__)


def _kill_stale_rtl_power() -> None:
    """Kill any lingering rtl_power processes from a previous server run."""
    try:
        result = subprocess.run(["pkill", "-x", "rtl_power"], capture_output=True)
        if result.returncode == 0:
            log.info("Killed stale rtl_power process(es)")
    except FileNotFoundError:
        pass


def create_app() -> Flask:
    log.info("Starting RTL Power Dashboard")
    init_db()
    log.info("Database initialised")
    seed_bands_from_yaml(BANDS_CONFIG)
    migrate_csv_sessions(DATA_DIR)

    # Only auto-start captures in the reloader child process (or when reloader
    # is disabled) — avoids double-start and dongle contention in debug mode.
    in_reloader_child = os.environ.get("WERKZEUG_RUN_MAIN") == "true"
    reloader_active   = os.environ.get("FLASK_DEBUG", "true").lower() == "true"
    should_start = in_reloader_child or not reloader_active

    if should_start:
        _kill_stale_rtl_power()
        from app.capture.manager import band_manager
        active_bands = [b for b in list_bands() if b.get("is_active")]
        if active_bands:
            try:
                band_manager.start_active_bands(active_bands)
                names = ", ".join(b["name"] for b in active_bands)
                log.info("Auto-started %d band(s): %s", len(active_bands), names)
            except Exception as exc:
                log.warning("Failed to auto-start bands: %s", exc)

    log.info("Startup complete")

    server = Flask(__name__)

    from app.api.routes import api_bp
    server.register_blueprint(api_bp)

    @server.route("/")
    def index():
        return render_template("index.html")

    return server
