from flask import jsonify, request

from app.data.parser import (
    get_band_data,
    get_band_maxhold,
    get_band_noise_floor,
    get_band_stats,
    get_band_activity,
    get_band_timeseries,
)
from ._helpers import api_bp, _parse_filters, _parse_float_arg, _parse_granularity


@api_bp.route("/bands/<band_id>/heatmap", methods=["GET"])
def band_heatmap(band_id: str):
    try:
        filters = _parse_filters(request.args)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    data = get_band_data(band_id, filters)
    if data is None:
        return jsonify({"error": "no data"}), 404
    return jsonify(data)


@api_bp.route("/bands/<band_id>/heatmap-maxhold", methods=["GET"])
def band_heatmap_maxhold(band_id: str):
    try:
        filters = _parse_filters(request.args)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    data = get_band_maxhold(band_id, filters)
    if data is None:
        return jsonify({"error": "no data"}), 404
    return jsonify(data)


@api_bp.route("/bands/<band_id>/spectrum", methods=["GET"])
def band_spectrum(band_id: str):
    try:
        filters = _parse_filters(request.args)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    data = get_band_stats(band_id, filters)
    if data is None:
        return jsonify({"error": "no data"}), 404
    return jsonify(data)


@api_bp.route("/bands/<band_id>/activity", methods=["GET"])
def band_activity(band_id: str):
    try:
        filters   = _parse_filters(request.args)
        threshold = _parse_float_arg(request.args, "threshold", default=0.0)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    data = get_band_activity(band_id, threshold, filters)
    if data is None:
        return jsonify({"error": "no data"}), 404
    return jsonify(data)


@api_bp.route("/bands/<band_id>/timeseries", methods=["GET"])
def band_timeseries(band_id: str):
    raw_freq = request.args.get("freq_mhz")
    if raw_freq is None:
        return jsonify({"error": "freq_mhz required"}), 400
    try:
        freq_mhz = float(raw_freq)
        filters  = _parse_filters(request.args)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    data = get_band_timeseries(band_id, freq_mhz, filters)
    if data is None:
        return jsonify({"error": "no data"}), 404
    return jsonify(data)


@api_bp.route("/bands/<band_id>/noise-floor", methods=["GET"])
def band_noise_floor(band_id: str):
    try:
        filters     = _parse_filters(request.args)
        granularity = _parse_granularity(request.args)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    data = get_band_noise_floor(band_id, granularity, filters)
    if data is None:
        return jsonify({"error": "no data"}), 404
    return jsonify(data)
