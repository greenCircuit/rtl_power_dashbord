from flask import jsonify

from app.data import db
from ._helpers import api_bp, _get_devices


@api_bp.route("/status", methods=["GET"])
def backend_status():
    from app.config import DB_PATH, DEMO_MODE
    db_info  = db.fetch_db_status()
    bands    = db.list_bands()
    name_map = {b["id"]: b["name"] for b in bands}
    for b in db_info["bands"]:
        b["name"] = name_map.get(b["band_id"], b["band_id"])
    total = sum(b["count"] for b in db_info["bands"])
    return jsonify({
        "status":             "ok",
        "demo_mode":          DEMO_MODE,
        "db_path":            str(DB_PATH),
        "db_size_mb":         db_info["db_size_mb"],
        "total_measurements": total,
        "bands":              db_info["bands"],
        "devices":            _get_devices(),
    })


@api_bp.route("/devices", methods=["GET"])
def list_devices():
    return jsonify({"devices": _get_devices()})
