from flask import Blueprint, jsonify, request

from app.capture.rtl_power import capture
from app.data.parser import get_session_data, get_frequency_timeseries, list_sessions

api_bp = Blueprint("api", __name__, url_prefix="/api")


@api_bp.route("/capture/start", methods=["POST"])
def start_capture():
    body = request.get_json(silent=True) or {}
    freq_start = body.get("freq_start", "88M")
    freq_end = body.get("freq_end", "108M")
    freq_step = body.get("freq_step", "200k")
    interval = int(body.get("interval", 10))
    duration = body.get("duration")  # e.g. "1h", "30m" — None means run forever

    try:
        session_id = capture.start(freq_start, freq_end, freq_step, interval, duration)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 409

    return jsonify({"session_id": session_id, "status": "running"}), 201


@api_bp.route("/capture/stop", methods=["POST"])
def stop_capture():
    capture.stop()
    return jsonify({"status": capture.status})


@api_bp.route("/capture/status", methods=["GET"])
def capture_status():
    return jsonify({
        "status": capture.status,
        "session_id": capture.current_session,
        "error": capture.error,
    })


@api_bp.route("/sessions", methods=["GET"])
def sessions():
    return jsonify({"sessions": list_sessions()})


@api_bp.route("/data/<session_id>", methods=["GET"])
def session_data(session_id: str):
    data = get_session_data(session_id)
    if data is None:
        return jsonify({"error": "Session not found or empty"}), 404
    return jsonify(data)


@api_bp.route("/data/<session_id>/timeseries", methods=["GET"])
def session_timeseries(session_id: str):
    freq_mhz = request.args.get("freq", type=float)
    if freq_mhz is None:
        return jsonify({"error": "freq parameter required (MHz)"}), 400

    data = get_frequency_timeseries(session_id, freq_mhz)
    if data is None:
        return jsonify({"error": "Session not found or empty"}), 404
    return jsonify(data)
