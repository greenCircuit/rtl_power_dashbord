from flask import jsonify, request

from app.data.parser import (
    get_band_data,
    get_band_maxhold,
    get_band_noise_floor,
    get_band_stats,
    get_band_activity,
    get_band_timeseries,
)
from ._helpers import api_bp, _parse_filters


@api_bp.route("/bands/<band_id>/heatmap", methods=["GET"])
def band_heatmap(band_id: str):
    filters = _parse_filters(request.args)
    data    = get_band_data(band_id, filters)
    if data is None:
        return jsonify({"error": "no data"}), 404
    return jsonify(data)


@api_bp.route("/bands/<band_id>/heatmap-maxhold", methods=["GET"])
def band_heatmap_maxhold(band_id: str):
    filters = _parse_filters(request.args)
    data    = get_band_maxhold(band_id, filters)
    if data is None:
        return jsonify({"error": "no data"}), 404
    return jsonify(data)


@api_bp.route("/bands/<band_id>/spectrum", methods=["GET"])
def band_spectrum(band_id: str):
    filters = _parse_filters(request.args)
    data    = get_band_stats(band_id, filters)
    if data is None:
        return jsonify({"error": "no data"}), 404
    return jsonify(data)


@api_bp.route("/bands/<band_id>/activity", methods=["GET"])
def band_activity(band_id: str):
    filters   = _parse_filters(request.args)
    threshold = float(request.args.get("threshold", 0))
    data      = get_band_activity(band_id, threshold, filters)
    if data is None:
        return jsonify({"error": "no data"}), 404
    return jsonify(data)


@api_bp.route("/bands/<band_id>/timeseries", methods=["GET"])
def band_timeseries(band_id: str):
    freq_mhz = request.args.get("freq_mhz", type=float)
    if freq_mhz is None:
        return jsonify({"error": "freq_mhz required"}), 400
    filters = _parse_filters(request.args)
    data    = get_band_timeseries(band_id, freq_mhz, filters)
    if data is None:
        return jsonify({"error": "no data"}), 404
    return jsonify(data)


@api_bp.route("/bands/<band_id>/noise-floor", methods=["GET"])
def band_noise_floor(band_id: str):
    filters     = _parse_filters(request.args)
    granularity = request.args.get("granularity", "1h")
    data        = get_band_noise_floor(band_id, granularity, filters)
    if data is None:
        return jsonify({"error": "no data"}), 404
    return jsonify(data)
