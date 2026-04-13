import numpy as np
from flask import jsonify, request

from app.data import db
from app.data.parser import (
    get_band_tod_activity,
    get_all_bands_activity_timeline,
    get_band_power_histogram,
    get_band_top_channels,
    get_band_activity_trend,
    get_band_signal_durations,
)
from ._helpers import api_bp, _parse_filters


@api_bp.route("/bands/<band_id>/tod-activity", methods=["GET"])
def band_tod_activity(band_id: str):
    filters   = _parse_filters(request.args)
    threshold = float(request.args.get("threshold", 0))
    data      = get_band_tod_activity(band_id, threshold, filters)
    if data is None:
        return jsonify({"error": "no data"}), 404
    return jsonify(data)


@api_bp.route("/bands/<band_id>/power-histogram", methods=["GET"])
def band_power_histogram(band_id: str):
    filters = _parse_filters(request.args)
    data    = get_band_power_histogram(band_id, filters)
    if data is None:
        return jsonify({"error": "no data"}), 404
    return jsonify(data)


@api_bp.route("/bands/<band_id>/top-channels", methods=["GET"])
def band_top_channels(band_id: str):
    filters   = _parse_filters(request.args)
    threshold = float(request.args.get("threshold", 0))
    limit     = int(request.args.get("limit", 10))
    data      = get_band_top_channels(band_id, threshold, limit, filters)
    if data is None:
        return jsonify({"error": "no data"}), 404
    return jsonify(data)


@api_bp.route("/bands/<band_id>/activity-trend", methods=["GET"])
def band_activity_trend(band_id: str):
    filters     = _parse_filters(request.args)
    threshold   = float(request.args.get("threshold", 0))
    granularity = request.args.get("granularity", "1h")
    data        = get_band_activity_trend(band_id, threshold, granularity, filters)
    if data is None:
        return jsonify({"error": "no data"}), 404
    return jsonify(data)


@api_bp.route("/bands/<band_id>/signal-durations", methods=["GET"])
def band_signal_durations(band_id: str):
    filters   = _parse_filters(request.args)
    threshold = float(request.args.get("threshold", 0))
    data      = get_band_signal_durations(band_id, threshold, filters)
    if data is None:
        return jsonify({"error": "no data"}), 404

    durations = data["durations_s"]
    if not durations:
        return jsonify({"error": "no data"}), 404

    n_bins       = 30
    min_d, max_d = min(durations), max(durations)
    if min_d == max_d:
        return jsonify({"bins": [min_d], "counts": [len(durations)],
                        "total": len(durations), "min_s": min_d, "max_s": max_d})

    counts_arr, edges = np.histogram(durations, bins=n_bins)
    bins = [round((edges[i] + edges[i + 1]) / 2, 2) for i in range(n_bins)]
    return jsonify({"bins": bins, "counts": counts_arr.tolist(),
                    "total": len(durations),
                    "min_s": round(min_d, 2), "max_s": round(max_d, 2)})


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
    bands     = db.list_bands()
    result    = []
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
