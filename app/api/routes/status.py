import logging

from flask import jsonify

from app.data import db
from ._helpers import api_bp, _get_devices

log = logging.getLogger(__name__)


@api_bp.route("/status", methods=["GET"])
def backend_status():
    from app.config import DB_PATH, DEMO_MODE
    db_info  = db.fetch_db_status()
    bands    = db.list_bands()

    # Index measurement data by band_id — bands with no measurements are absent here
    meas_by_id = {b["band_id"]: b for b in db_info["bands"]}

    # Build per-band status for ALL configured bands, using 0/null for those
    # without any measurements yet (previously those were silently excluded)
    band_statuses = [
        {
            "band_id":  b["id"],
            "name":     b["name"],
            "count":    meas_by_id.get(b["id"], {}).get("count", 0),
            "last_seen": meas_by_id.get(b["id"], {}).get("last_seen"),
        }
        for b in bands
    ]

    total = sum(b["count"] for b in band_statuses)
    log.debug("Status: db_size=%.2f MB, bands=%d, measurements=%d",
              db_info["db_size_mb"], len(bands), total)
    return jsonify({
        "status":             "ok",
        "demo_mode":          DEMO_MODE,
        "db_path":            str(DB_PATH),
        "db_size_mb":         db_info["db_size_mb"],
        "total_measurements": total,
        "bands":              band_statuses,
        "devices":            _get_devices(),
    })


@api_bp.route("/devices", methods=["GET"])
def list_devices():
    return jsonify({"devices": _get_devices()})
