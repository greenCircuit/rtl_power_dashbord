import logging
import uuid

from flask import jsonify, request

from app.capture.manager import band_manager
from app.data import db
from ._helpers import api_bp, _device_name

log = logging.getLogger(__name__)


@api_bp.route("/bands", methods=["GET"])
def list_bands():
    bands    = db.list_bands()
    statuses = band_manager.all_statuses()
    for b in bands:
        b["status"]      = statuses.get(b["id"], "idle")
        b["device_name"] = _device_name(b["device_index"])
    return jsonify({"bands": bands})


def _parse_band_body(body: dict, defaults: dict) -> tuple:
    """Parse and validate band fields from a JSON body.

    ``defaults`` provides fallback values for optional fields.
    Returns (name, freq_start, freq_end, freq_step, interval_s, min_power, device_index, is_active).
    Raises ValueError with a descriptive message on any type or bounds error.
    """
    name         = body.get("name",         defaults.get("name"))
    freq_start   = body.get("freq_start",   defaults.get("freq_start"))
    freq_end     = body.get("freq_end",     defaults.get("freq_end"))
    freq_step    = body.get("freq_step",    defaults.get("freq_step"))

    raw_interval = body.get("interval_s",   defaults.get("interval_s", 10))
    try:
        interval_s = int(raw_interval)
    except (ValueError, TypeError):
        raise ValueError(f"'interval_s' must be an integer, got {raw_interval!r}")
    if interval_s < 1:
        raise ValueError(f"'interval_s' must be >= 1, got {interval_s}")

    raw_power = body.get("min_power", defaults.get("min_power", 2.0))
    try:
        min_power = float(raw_power)
    except (ValueError, TypeError):
        raise ValueError(f"'min_power' must be a number, got {raw_power!r}")

    raw_device = body.get("device_index", defaults.get("device_index", 0))
    try:
        device_index = int(raw_device)
    except (ValueError, TypeError):
        raise ValueError(f"'device_index' must be an integer, got {raw_device!r}")
    if device_index < 0:
        raise ValueError(f"'device_index' must be >= 0, got {device_index}")

    raw_active = body.get("is_active", defaults.get("is_active", False))
    if isinstance(raw_active, bool):
        is_active = raw_active
    elif isinstance(raw_active, int):
        is_active = bool(raw_active)
    elif isinstance(raw_active, str):
        if raw_active.lower() in ("true", "1"):
            is_active = True
        elif raw_active.lower() in ("false", "0"):
            is_active = False
        else:
            raise ValueError(f"'is_active' must be true or false, got {raw_active!r}")
    else:
        raise ValueError(f"'is_active' must be a boolean, got {raw_active!r}")

    return name, freq_start, freq_end, freq_step, interval_s, min_power, device_index, is_active


@api_bp.route("/bands", methods=["POST"])
def create_band():
    body     = request.get_json(silent=True) or {}
    required = ("name", "freq_start", "freq_end", "freq_step")
    missing  = [f for f in required if not body.get(f)]
    if missing:
        return jsonify({"error": f"Missing fields: {missing}"}), 400
    try:
        name, freq_start, freq_end, freq_step, interval_s, min_power, device_index, is_active = (
            _parse_band_body(body, {})
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    band_id = uuid.uuid4().hex[:8]
    try:
        db.create_band(
            band_id, name, freq_start, freq_end, freq_step,
            interval_s, min_power, device_index, is_active,
        )
    except Exception as exc:
        return jsonify({"error": str(exc)}), 409
    log.info("API create_band: [%s] %s", band_id, name)
    return jsonify({"id": band_id}), 201


@api_bp.route("/bands/<band_id>", methods=["PUT"])
def update_band(band_id: str):
    body = request.get_json(silent=True) or {}
    band = db.get_band(band_id)
    if not band:
        return jsonify({"error": "Band not found"}), 404
    try:
        name, freq_start, freq_end, freq_step, interval_s, min_power, device_index, is_active = (
            _parse_band_body(body, band)
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    try:
        db.update_band(
            band_id, name, freq_start, freq_end, freq_step,
            interval_s, min_power, device_index, is_active,
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
