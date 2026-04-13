import logging
import re
import subprocess
import uuid

import numpy as np
from flask import Blueprint, jsonify, request

from app.capture.manager import band_manager
from app.data import db
from app.data.parser import (
    get_band_data,
    get_band_stats,
    get_band_activity,
    get_band_timeseries,
    get_band_tod_activity,
    get_all_bands_activity_timeline,
    get_band_signal_durations,
    get_band_power_histogram,
    get_band_top_channels,
    get_band_activity_trend,
)

api_bp = Blueprint("api", __name__, url_prefix="/api")
log = logging.getLogger(__name__)

_device_cache: list[dict] | None = None


def _get_devices() -> list[dict]:
    """Return cached device list, probing rtl_test on first call."""
    global _device_cache
    if _device_cache is None:
        _device_cache = _list_rtl_devices()
        if not _device_cache:
            _device_cache = [{"index": 0, "name": "Device 0"}]
    return _device_cache


def _device_name(index: int) -> str:
    for d in _get_devices():
        if d["index"] == index:
            return d["name"]
    return f"Device {index}"


def _list_rtl_devices() -> list[dict]:
    """Return [{index, name}] for each RTL-SDR device found by rtl_test."""
    try:
        result = subprocess.run(
            ["rtl_test"], capture_output=True, text=True, timeout=3
        )
        output = result.stderr + result.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []

    devices: dict[int, str] = {}

    for line in output.splitlines():
        # "  0:  Realtek, RTL2838UHIDIR, SN: 00000001"
        m = re.match(r"^\s+(\d+):\s+.+,\s+(.+),\s+SN:\s+(\S+)", line)
        if m:
            idx, model, serial = int(m.group(1)), m.group(2).strip(), m.group(3)
            devices[idx] = f"{model} (SN: {serial})"

        # "Using device 0: Generic RTL2832U OEM" — the human-readable USB name;
        # overrides the EEPROM model string above when present.
        m = re.match(r"^Using device (\d+):\s+(.+)", line)
        if m:
            devices[int(m.group(1))] = m.group(2).strip()

    return [{"index": k, "name": v} for k, v in sorted(devices.items())]


def _parse_filters(args) -> dict:
    filters = {}
    for key in ("freq_min", "freq_max"):
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
    val = args.get("power_min")
    if val is not None and val != "":
        try:
            filters["power_min"] = float(val)
        except ValueError:
            pass
    return filters


@api_bp.route("/status", methods=["GET"])
def backend_status():
    from app.config import DB_PATH, DEMO_MODE
    db_info = db.fetch_db_status()
    bands   = db.list_bands()
    name_map = {b["id"]: b["name"] for b in bands}
    for b in db_info["bands"]:
        b["name"] = name_map.get(b["band_id"], b["band_id"])
    total = sum(b["count"] for b in db_info["bands"])
    return jsonify({
        "status":            "ok",
        "demo_mode":         DEMO_MODE,
        "db_path":           str(DB_PATH),
        "db_size_mb":        db_info["db_size_mb"],
        "total_measurements": total,
        "bands":             db_info["bands"],
        "devices":           _get_devices(),
    })


@api_bp.route("/devices", methods=["GET"])
def list_devices():
    return jsonify({"devices": _get_devices()})


@api_bp.route("/bands", methods=["GET"])
def list_bands():
    bands = db.list_bands()
    statuses = band_manager.all_statuses()
    for b in bands:
        b["status"] = statuses.get(b["id"], "idle")
        b["device_name"] = _device_name(b["device_index"])
    return jsonify({"bands": bands})


@api_bp.route("/bands", methods=["POST"])
def create_band():
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


# ── Analysis endpoints ────────────────────────────────────────────────────────

@api_bp.route("/bands/<band_id>/tod-activity", methods=["GET"])
def band_tod_activity(band_id: str):
    filters   = _parse_filters(request.args)
    threshold = float(request.args.get("threshold", 0))
    data = get_band_tod_activity(band_id, threshold, filters)
    if data is None:
        return jsonify({"error": "no data"}), 404
    return jsonify(data)


@api_bp.route("/analysis/crossband-timeline", methods=["GET"])
def crossband_timeline():
    filters   = _parse_filters(request.args)
    threshold = float(request.args.get("threshold", 0))
    ids_param = request.args.get("band_ids", "")
    all_bands = db.list_bands()
    band_ids  = [b for b in ids_param.split(",") if b] if ids_param else [b["id"] for b in all_bands]
    name_map  = {b["id"]: b["name"] for b in all_bands}

    raw = get_all_bands_activity_timeline(band_ids, threshold, filters)
    if not raw:
        return jsonify({"error": "no data"}), 404

    result = [
        {"id": bid, "name": name_map.get(bid, bid),
         "buckets": s["buckets"], "pcts": s["pcts"]}
        for bid, s in raw.items()
    ]
    return jsonify({"bands": result})


@api_bp.route("/analysis/overview", methods=["GET"])
def bands_overview():
    threshold = float(request.args.get("threshold", 0))
    bands  = db.list_bands()
    result = []
    for b in bands:
        stats = db.fetch_band_latest_activity(b["id"], threshold)
        pct   = 0.0
        if stats and stats["total"]:
            pct = round(stats["active"] / stats["total"] * 100, 1)
        result.append({
            "id":           b["id"],
            "name":         b["name"],
            "freq_range":   f"{b['freq_start']}–{b['freq_end']}",
            "activity_pct": pct,
            "last_seen":    stats["last_seen"] if stats else None,
        })
    return jsonify({"bands": result})


@api_bp.route("/bands/<band_id>/power-histogram", methods=["GET"])
def band_power_histogram(band_id: str):
    filters = _parse_filters(request.args)
    data = get_band_power_histogram(band_id, filters)
    if data is None:
        return jsonify({"error": "no data"}), 404
    return jsonify(data)


@api_bp.route("/bands/<band_id>/top-channels", methods=["GET"])
def band_top_channels(band_id: str):
    filters   = _parse_filters(request.args)
    threshold = float(request.args.get("threshold", 0))
    limit     = int(request.args.get("limit", 10))
    data = get_band_top_channels(band_id, threshold, limit, filters)
    if data is None:
        return jsonify({"error": "no data"}), 404
    return jsonify(data)


@api_bp.route("/bands/<band_id>/activity-trend", methods=["GET"])
def band_activity_trend(band_id: str):
    filters     = _parse_filters(request.args)
    threshold   = float(request.args.get("threshold", 0))
    granularity = request.args.get("granularity", "1h")
    data = get_band_activity_trend(band_id, threshold, granularity, filters)
    if data is None:
        return jsonify({"error": "no data"}), 404
    return jsonify(data)


@api_bp.route("/bands/<band_id>/signal-durations", methods=["GET"])
def band_signal_durations(band_id: str):
    filters   = _parse_filters(request.args)
    threshold = float(request.args.get("threshold", 0))
    data = get_band_signal_durations(band_id, threshold, filters)
    if data is None:
        return jsonify({"error": "no data"}), 404

    durations = data["durations_s"]
    if not durations:
        return jsonify({"error": "no data"}), 404

    n_bins    = 30
    min_d, max_d = min(durations), max(durations)
    if min_d == max_d:
        return jsonify({"bins": [min_d], "counts": [len(durations)],
                        "total": len(durations), "min_s": min_d, "max_s": max_d})

    counts_arr, edges = np.histogram(durations, bins=n_bins)
    bins = [round((edges[i] + edges[i + 1]) / 2, 2) for i in range(n_bins)]
    return jsonify({"bins": bins, "counts": counts_arr.tolist(),
                    "total": len(durations),
                    "min_s": round(min_d, 2), "max_s": round(max_d, 2)})
