import logging

from flask import Blueprint, jsonify, request

from app.capture.manager import band_manager
from app.data import db
from app.data.parser import (
    get_band_data,
    get_band_stats,
    get_band_activity,
    get_band_timeseries,
)

api_bp = Blueprint("api", __name__, url_prefix="/api")
log = logging.getLogger(__name__)


def _parse_filters(args) -> dict:
    filters = {}
    for key in ("freq_min", "freq_max", "power_min"):
        val = args.get(key)
        if val is not None and val != "":
            try:
                filters[key] = float(val)
            except ValueError:
                pass
    for key in ("time_min", "time_max"):
        val = args.get(key)
        if val:
            filters[key] = val
    return filters


@api_bp.route("/bands", methods=["GET"])
def list_bands():
    bands = db.list_bands()
    statuses = band_manager.all_statuses()
    for b in bands:
        b["status"] = statuses.get(b["id"], "idle")
    return jsonify({"bands": bands})


@api_bp.route("/bands", methods=["POST"])
def create_band():
    import uuid
    body = request.get_json(silent=True) or {}
    required = ("name", "freq_start", "freq_end", "freq_step")
    missing = [f for f in required if not body.get(f)]
    if missing:
        return jsonify({"error": f"Missing fields: {missing}"}), 400
    band_id = uuid.uuid4().hex[:8]
    try:
        db.create_band(
            band_id,
            body["name"],
            body["freq_start"],
            body["freq_end"],
            body["freq_step"],
            int(body.get("interval_s", 10)),
            float(body.get("min_power", 2.0)),
            int(body.get("device_index", 0)),
            bool(body.get("is_active", False)),
        )
    except Exception as exc:
        return jsonify({"error": str(exc)}), 409
    log.info("API create_band: [%s] %s", band_id, body.get("name"))
    return jsonify({"id": band_id}), 201


@api_bp.route("/bands/<band_id>", methods=["PUT"])
def update_band(band_id: str):
    body = request.get_json(silent=True) or {}
    band = db.get_band(band_id)
    if not band:
        return jsonify({"error": "Band not found"}), 404
    try:
        db.update_band(
            band_id,
            body.get("name", band["name"]),
            body.get("freq_start", band["freq_start"]),
            body.get("freq_end", band["freq_end"]),
            body.get("freq_step", band["freq_step"]),
            int(body.get("interval_s", band["interval_s"])),
            float(body.get("min_power", band["min_power"])),
            int(body.get("device_index", band["device_index"])),
            bool(body.get("is_active", band["is_active"])),
        )
    except Exception as exc:
        log.warning("API update_band [%s] failed: %s", band_id, exc)
        return jsonify({"error": str(exc)}), 409
    log.info("API update_band: [%s]", band_id)
    return jsonify({"status": "updated"})


@api_bp.route("/bands/<band_id>", methods=["DELETE"])
def delete_band(band_id: str):
    band_manager.stop_band(band_id)
    db.delete_band(band_id)
    log.info("API delete_band: [%s]", band_id)
    return jsonify({"status": "deleted"})


@api_bp.route("/bands/<band_id>/start", methods=["POST"])
def start_band(band_id: str):
    try:
        band_manager.start_band(band_id)
    except (ValueError, RuntimeError) as exc:
        log.warning("API start_band [%s] failed: %s", band_id, exc)
        return jsonify({"error": str(exc)}), 409
    log.info("API start_band: [%s]", band_id)
    return jsonify({"status": "running"})


@api_bp.route("/bands/<band_id>/stop", methods=["POST"])
def stop_band(band_id: str):
    band_manager.stop_band(band_id)
    status = band_manager.get_status(band_id)
    log.info("API stop_band: [%s] → %s", band_id, status)
    return jsonify({"status": status})


@api_bp.route("/bands/<band_id>/status", methods=["GET"])
def band_status(band_id: str):
    return jsonify({
        "status": band_manager.get_status(band_id),
        "error":  band_manager.get_error(band_id),
    })


@api_bp.route("/bands/<band_id>/heatmap", methods=["GET"])
def band_heatmap(band_id: str):
    filters = _parse_filters(request.args)
    data = get_band_data(band_id, filters)
    if data is None:
        return jsonify({"error": "no data"}), 404
    return jsonify(data)


@api_bp.route("/bands/<band_id>/spectrum", methods=["GET"])
def band_spectrum(band_id: str):
    filters = _parse_filters(request.args)
    data = get_band_stats(band_id, filters)
    if data is None:
        return jsonify({"error": "no data"}), 404
    return jsonify(data)


@api_bp.route("/bands/<band_id>/activity", methods=["GET"])
def band_activity(band_id: str):
    filters = _parse_filters(request.args)
    threshold = float(request.args.get("threshold", 0))
    data = get_band_activity(band_id, threshold, filters)
    if data is None:
        return jsonify({"error": "no data"}), 404
    return jsonify(data)


@api_bp.route("/bands/<band_id>/timeseries", methods=["GET"])
def band_timeseries(band_id: str):
    freq_mhz = request.args.get("freq_mhz", type=float)
    if freq_mhz is None:
        return jsonify({"error": "freq_mhz required"}), 400
    filters = _parse_filters(request.args)
    data = get_band_timeseries(band_id, freq_mhz, filters)
    if data is None:
        return jsonify({"error": "no data"}), 404
    return jsonify(data)
