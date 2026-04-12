import logging
import os
import subprocess
from pathlib import Path

from flask import Flask, send_from_directory

from app.config import configure_logging, BANDS_CONFIG, DEMO_MODE
from app.data.db import init_db, seed_bands_from_yaml, list_bands
from app.cleanup import start_cleanup_scheduler

UI_DIST = Path(__file__).parent.parent / 'ui' / 'dist'

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

    # Only auto-start captures in the reloader child process (or when reloader
    # is disabled) — avoids double-start and dongle contention in debug mode.
    in_reloader_child = os.environ.get("WERKZEUG_RUN_MAIN") == "true"
    reloader_active   = os.environ.get("FLASK_DEBUG", "true").lower() == "true"
    should_start = in_reloader_child or not reloader_active

    if should_start:
        if not DEMO_MODE:
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

    if should_start:
        start_cleanup_scheduler()

    log.info("Startup complete")

    server = Flask(__name__, static_folder=None)

    from app.api.routes import api_bp
    server.register_blueprint(api_bp)

    @server.route("/")
    def index():
        return send_from_directory(str(UI_DIST), 'index.html')

    @server.route("/assets/<path:filename>")
    def ui_assets(filename: str):
        return send_from_directory(str(UI_DIST / 'assets'), filename)

    return server
