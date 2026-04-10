import uuid
from datetime import datetime, timedelta

import plotly.graph_objects as go
from dash import ALL, Input, Output, State, callback_context, html, no_update
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc

from app.capture.manager import band_manager
from app.data import db
from app.data.parser import (
    get_band_data,
    get_band_stats,
    get_band_activity,
    get_band_timeseries,
)

COLORSCALE = "Plasma"

STATUS_COLORS = {
    "running":   "success",
    "idle":      "secondary",
    "stopped":   "warning",
    "completed": "info",
    "error":     "danger",
}


def _status_badge(status: str) -> dbc.Badge:
    return dbc.Badge(status, color=STATUS_COLORS.get(status, "secondary"),
                     className="ms-1")


def _band_table(bands: list[dict]) -> html.Div:
    if not bands:
        return html.Div("No bands configured. Click '+ Add Band' to get started.",
                        className="text-muted small")
    header = html.Thead(html.Tr([
        html.Th("Name"), html.Th("Freq Range"), html.Th("Step"),
        html.Th("Interval"), html.Th("Min Power (dB)"), html.Th("Device"),
        html.Th("Status"), html.Th("Actions"),
    ]))
    rows = []
    for b in bands:
        status = band_manager.get_status(b["id"])
        is_running = status == "running"
        rows.append(html.Tr([
            html.Td(b["name"], className="fw-semibold"),
            html.Td(f"{b['freq_start']} – {b['freq_end']}"),
            html.Td(b["freq_step"]),
            html.Td(f"{b['interval_s']} s"),
            html.Td(f"{b['min_power']} dB"),
            html.Td(b["device_index"]),
            html.Td(_status_badge(status)),
            html.Td(dbc.ButtonGroup([
                dbc.Button("■ Stop" if is_running else "▶ Start",
                           id={"type": "btn-band-startstop", "index": b["id"]},
                           color="danger" if is_running else "success",
                           size="sm", n_clicks=0),
                dbc.Button("View",
                           id={"type": "btn-band-view", "index": b["id"]},
                           color="info", size="sm", n_clicks=0,
                           className="ms-1"),
                dbc.Button("Edit",
                           id={"type": "btn-band-edit", "index": b["id"]},
                           color="secondary", size="sm", n_clicks=0,
                           className="ms-1"),
                dbc.Button("Delete",
                           id={"type": "btn-band-delete", "index": b["id"]},
                           color="danger", outline=True, size="sm", n_clicks=0,
                           className="ms-1"),
            ])),
        ]))
    return dbc.Table(
        [header, html.Tbody(rows)],
        bordered=False, hover=True, responsive=True, size="sm",
        className="mb-0",
    )


def register_callbacks(app) -> None:

    # ── 1. Poll: refresh band table + dropdown ───────────────────────────────
    @app.callback(
        Output("div-band-table", "children"),
        Output("dropdown-band", "options"),
        Output("div-status", "children"),
        Input("interval-poll", "n_intervals"),
    )
    def refresh_bands(_):
        bands = db.list_bands()
        table = _band_table(bands)
        options = [{"label": b["name"], "value": b["id"]} for b in bands]
        statuses = band_manager.all_statuses()
        running = [b["name"] for b in bands if statuses.get(b["id"]) == "running"]
        status_text = f"Running: {', '.join(running)}" if running else "No active captures"
        return table, options, status_text

    # ── 2. Start / stop a band ───────────────────────────────────────────────
    @app.callback(
        Output("div-band-table", "children", allow_duplicate=True),
        Input({"type": "btn-band-startstop", "index": ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
    def handle_startstop(n_clicks_list):
        triggered = callback_context.triggered_id
        if not triggered or not any(n for n in n_clicks_list if n):
            raise PreventUpdate
        band_id = triggered["index"]
        status = band_manager.get_status(band_id)
        try:
            if status == "running":
                band_manager.stop_band(band_id)
            else:
                band_manager.start_band(band_id)
        except RuntimeError:
            pass
        return _band_table(db.list_bands())

    # ── 3. Delete a band ─────────────────────────────────────────────────────
    @app.callback(
        Output("div-band-table", "children", allow_duplicate=True),
        Output("dropdown-band", "options", allow_duplicate=True),
        Input({"type": "btn-band-delete", "index": ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
    def handle_delete(n_clicks_list):
        triggered = callback_context.triggered_id
        if not triggered or not any(n for n in n_clicks_list if n):
            raise PreventUpdate
        band_id = triggered["index"]
        band_manager.stop_band(band_id)
        db.delete_band(band_id)
        bands = db.list_bands()
        options = [{"label": b["name"], "value": b["id"]} for b in bands]
        return _band_table(bands), options

    # ── 4. View band ─────────────────────────────────────────────────────────
    @app.callback(
        Output("dropdown-band", "value", allow_duplicate=True),
        Input({"type": "btn-band-view", "index": ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
    def handle_view(n_clicks_list):
        triggered = callback_context.triggered_id
        if not triggered or not any(n for n in n_clicks_list if n):
            raise PreventUpdate
        return triggered["index"]

    # ── 5. Open modal for Add ────────────────────────────────────────────────
    @app.callback(
        Output("modal-band", "is_open", allow_duplicate=True),
        Output("store-editing-band", "data", allow_duplicate=True),
        Output("modal-band-title", "children", allow_duplicate=True),
        Output("modal-band-name", "value", allow_duplicate=True),
        Output("modal-freq-start", "value", allow_duplicate=True),
        Output("modal-freq-start-unit", "value", allow_duplicate=True),
        Output("modal-freq-end", "value", allow_duplicate=True),
        Output("modal-freq-end-unit", "value", allow_duplicate=True),
        Output("modal-freq-step", "value", allow_duplicate=True),
        Output("modal-freq-step-unit", "value", allow_duplicate=True),
        Output("modal-interval", "value", allow_duplicate=True),
        Output("modal-record-threshold", "value", allow_duplicate=True),
        Output("modal-device-index", "value", allow_duplicate=True),
        Output("modal-band-error", "children", allow_duplicate=True),
        Input("btn-add-band", "n_clicks"),
        prevent_initial_call=True,
    )
    def open_add_modal(_):
        return (True, None, "Add Band",
                "", 88, "M", 108, "M", 0.2, "M", 10, 2.0, 0, "")

    # ── 6. Open modal for Edit ───────────────────────────────────────────────
    @app.callback(
        Output("modal-band", "is_open", allow_duplicate=True),
        Output("store-editing-band", "data", allow_duplicate=True),
        Output("modal-band-title", "children", allow_duplicate=True),
        Output("modal-band-name", "value", allow_duplicate=True),
        Output("modal-freq-start", "value", allow_duplicate=True),
        Output("modal-freq-start-unit", "value", allow_duplicate=True),
        Output("modal-freq-end", "value", allow_duplicate=True),
        Output("modal-freq-end-unit", "value", allow_duplicate=True),
        Output("modal-freq-step", "value", allow_duplicate=True),
        Output("modal-freq-step-unit", "value", allow_duplicate=True),
        Output("modal-interval", "value", allow_duplicate=True),
        Output("modal-record-threshold", "value", allow_duplicate=True),
        Output("modal-device-index", "value", allow_duplicate=True),
        Output("modal-band-error", "children", allow_duplicate=True),
        Input({"type": "btn-band-edit", "index": ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
    def open_edit_modal(n_clicks_list):
        triggered = callback_context.triggered_id
        if not triggered or not any(n for n in n_clicks_list if n):
            raise PreventUpdate
        band = db.get_band(triggered["index"])
        if not band:
            raise PreventUpdate
        # Parse stored freq strings like "88M" → value=88, unit="M"
        def split_freq(s):
            for unit in ("G", "M", "k"):
                if s.endswith(unit):
                    return s[:-1], unit
            return s, "M"
        fs_val, fs_unit = split_freq(band["freq_start"])
        fe_val, fe_unit = split_freq(band["freq_end"])
        fst_val, fst_unit = split_freq(band["freq_step"])
        return (True, band["id"], f"Edit Band — {band['name']}",
                band["name"],
                fs_val, fs_unit, fe_val, fe_unit, fst_val, fst_unit,
                band["interval_s"], band["min_power"], band["device_index"],
                "")

    # ── 7. Close modal ───────────────────────────────────────────────────────
    @app.callback(
        Output("modal-band", "is_open", allow_duplicate=True),
        Input("btn-modal-cancel", "n_clicks"),
        prevent_initial_call=True,
    )
    def close_modal(_):
        return False

    # ── 8. Save band (add or update) ─────────────────────────────────────────
    @app.callback(
        Output("modal-band", "is_open", allow_duplicate=True),
        Output("modal-band-error", "children", allow_duplicate=True),
        Output("div-band-table", "children", allow_duplicate=True),
        Output("dropdown-band", "options", allow_duplicate=True),
        Input("btn-modal-save", "n_clicks"),
        State("store-editing-band", "data"),
        State("modal-band-name", "value"),
        State("modal-freq-start", "value"),
        State("modal-freq-start-unit", "value"),
        State("modal-freq-end", "value"),
        State("modal-freq-end-unit", "value"),
        State("modal-freq-step", "value"),
        State("modal-freq-step-unit", "value"),
        State("modal-interval", "value"),
        State("modal-record-threshold", "value"),
        State("modal-device-index", "value"),
        prevent_initial_call=True,
    )
    def save_band(_, editing_id, name,
                  fs_val, fs_unit, fe_val, fe_unit, fst_val, fst_unit,
                  interval, min_power, device_index):
        if not name or fs_val is None or fe_val is None or fst_val is None:
            return no_update, "All frequency fields are required.", no_update, no_update

        freq_start = f"{fs_val}{fs_unit}"
        freq_end   = f"{fe_val}{fe_unit}"
        freq_step  = f"{fst_val}{fst_unit}"

        try:
            if editing_id:
                db.update_band(editing_id, name.strip(), freq_start, freq_end,
                               freq_step, int(interval or 10),
                               float(min_power or 2.0), int(device_index or 0))
            else:
                db.create_band(uuid.uuid4().hex[:8], name.strip(),
                               freq_start, freq_end, freq_step,
                               int(interval or 10), float(min_power or 2.0),
                               int(device_index or 0))
        except Exception as exc:
            return no_update, str(exc), no_update, no_update

        bands = db.list_bands()
        options = [{"label": b["name"], "value": b["id"]} for b in bands]
        return False, "", _band_table(bands), options

    # ── 8. Quick time-range buttons ──────────────────────────────────────────
    _RANGES = {
        "btn-range-15m": timedelta(minutes=15),
        "btn-range-1h":  timedelta(hours=1),
        "btn-range-12h": timedelta(hours=12),
        "btn-range-1d":  timedelta(days=1),
        "btn-range-7d":  timedelta(days=7),
    }
    _RANGE_IDS = ["btn-range-15m", "btn-range-1h", "btn-range-12h",
                  "btn-range-1d", "btn-range-7d", "btn-range-all"]

    @app.callback(
        Output("store-time-range", "data"),
        Input("btn-range-15m", "n_clicks"),
        Input("btn-range-1h",  "n_clicks"),
        Input("btn-range-12h", "n_clicks"),
        Input("btn-range-1d",  "n_clicks"),
        Input("btn-range-7d",  "n_clicks"),
        Input("btn-range-all", "n_clicks"),
        prevent_initial_call=True,
    )
    def select_time_range(*_):
        return callback_context.triggered_id

    @app.callback(
        Output("filter-time-start", "value", allow_duplicate=True),
        Output("filter-time-end",   "value", allow_duplicate=True),
        Input("store-time-range", "data"),
        prevent_initial_call="initial_duplicate",
    )
    def apply_time_range(range_id):
        if range_id == "btn-range-all":
            return None, None
        delta = _RANGES.get(range_id)
        if not delta:
            raise PreventUpdate
        now   = datetime.now()
        start = now - delta
        fmt   = "%Y-%m-%dT%H:%M"
        return start.strftime(fmt), now.strftime(fmt)

    @app.callback(
        *[Output(rid, "color") for rid in _RANGE_IDS],
        Input("store-time-range", "data"),
    )
    def update_range_button_colors(active_id):
        return ["primary" if rid == active_id else "outline-secondary"
                for rid in _RANGE_IDS]

    # ── 9. Filter store ──────────────────────────────────────────────────────
    @app.callback(
        Output("store-filters", "data"),
        Output("filter-freq-min", "value"),
        Output("filter-freq-max", "value"),
        Output("filter-time-start", "value"),
        Output("filter-time-end", "value"),
        Output("filter-power-min", "value"),
        Input("filter-freq-min", "value"),
        Input("filter-freq-max", "value"),
        Input("filter-time-start", "value"),
        Input("filter-time-end", "value"),
        Input("filter-power-min", "value"),
        Input("btn-filter-clear", "n_clicks"),
        prevent_initial_call=True,
    )
    def update_filters(freq_min, freq_max, time_start, time_end, power_min, _clear):
        if callback_context.triggered_id == "btn-filter-clear":
            return {}, None, None, None, None, -20
        filters = {}
        if freq_min is not None:
            filters["freq_min"] = freq_min
        if freq_max is not None:
            filters["freq_max"] = freq_max
        if time_start:
            filters["time_min"] = time_start.replace("T", " ")
        if time_end:
            filters["time_max"] = time_end.replace("T", " ")
        if power_min is not None and power_min > -20:
            filters["power_min"] = power_min
        return filters, no_update, no_update, no_update, no_update, no_update

    # ── 10. Heatmap ──────────────────────────────────────────────────────────
    @app.callback(
        Output("graph-heatmap", "figure"),
        Input("dropdown-band", "value"),
        Input("interval-poll", "n_intervals"),
        Input("store-filters", "data"),
    )
    def update_heatmap(band_id, _, filters):
        if not band_id:
            return _empty_heatmap("No band selected")
        data = get_band_data(band_id, filters)
        if not data:
            band = db.get_band(band_id)
            name = band["name"] if band else band_id
            return _empty_heatmap(f"No data yet for {name}")
        band = db.get_band(band_id)
        fig = go.Figure(go.Heatmap(
            x=data["x"], y=data["y"], z=data["z"],
            colorscale=COLORSCALE,
            colorbar=dict(title="dBFS"),
            hoverongaps=False,
            hovertemplate="Time: %{x}<br>Freq: %{y:.3f} MHz<br>Power: %{z:.1f} dB<extra></extra>",
        ))
        fig.update_layout(
            title=f"Spectrum heatmap — {band['name'] if band else band_id}",
            xaxis_title="Time", yaxis_title="Frequency (MHz)",
            margin=dict(l=60, r=20, t=50, b=50),
            paper_bgcolor="#111", plot_bgcolor="#111", font=dict(color="#ddd"),
        )
        return fig

    # ── 11. Time-series on heatmap click ─────────────────────────────────────
    @app.callback(
        Output("graph-timeseries", "figure"),
        Input("graph-heatmap", "clickData"),
        State("dropdown-band", "value"),
        State("store-filters", "data"),
    )
    def update_timeseries(click_data, band_id, filters):
        if not click_data or not band_id:
            return _empty_figure("Click a frequency on the heatmap to see power over time")
        freq_mhz = click_data["points"][0]["y"]
        data = get_band_timeseries(band_id, freq_mhz, filters)
        if not data:
            return _empty_figure("No data for selected frequency")
        fig = go.Figure(go.Scatter(
            x=data["timestamps"], y=data["power_db"],
            mode="lines+markers",
            line=dict(color="#f0a500", width=1.5),
            marker=dict(size=3),
            hovertemplate="Time: %{x}<br>Power: %{y:.1f} dB<extra></extra>",
        ))
        fig.update_layout(
            title=f"Power over time — {data['frequency_mhz']:.3f} MHz",
            xaxis_title="Time", yaxis_title="Power (dBFS)",
            margin=dict(l=60, r=20, t=40, b=50),
            paper_bgcolor="#111", plot_bgcolor="#111", font=dict(color="#ddd"),
        )
        return fig

    # ── 11. Mean & peak spectrum ──────────────────────────────────────────────
    @app.callback(
        Output("graph-spectrum", "figure"),
        Input("dropdown-band", "value"),
        Input("interval-poll", "n_intervals"),
        Input("store-filters", "data"),
    )
    def update_spectrum(band_id, _, filters):
        if not band_id:
            return _empty_figure("No band selected")
        data = get_band_stats(band_id, filters)
        if not data:
            return _empty_figure("No data yet")
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=data["frequency_mhz"], y=data["mean_db"],
            mode="lines", name="Mean power",
            line=dict(color="#4fc3f7", width=1.5),
            hovertemplate="Freq: %{x:.3f} MHz<br>Mean: %{y:.1f} dBFS<extra></extra>",
        ))
        fig.add_trace(go.Scatter(
            x=data["frequency_mhz"], y=data["peak_db"],
            mode="lines", name="Peak power",
            line=dict(color="#ff7043", width=1, dash="dot"),
            hovertemplate="Freq: %{x:.3f} MHz<br>Peak: %{y:.1f} dBFS<extra></extra>",
        ))
        fig.update_layout(
            title="Mean & Peak Power per Frequency",
            xaxis_title="Frequency (MHz)", yaxis_title="Power (dBFS)",
            legend=dict(orientation="h", y=1.1),
            margin=dict(l=60, r=20, t=50, b=50),
            paper_bgcolor="#111", plot_bgcolor="#111", font=dict(color="#ddd"),
        )
        return fig

    # ── 12. Activity % per frequency ──────────────────────────────────────────
    @app.callback(
        Output("graph-activity", "figure"),
        Input("dropdown-band", "value"),
        Input("interval-poll", "n_intervals"),
        Input("slider-threshold", "value"),
        Input("store-filters", "data"),
    )
    def update_activity(band_id, _, threshold_db, filters):
        if not band_id:
            return _empty_figure("No band selected")
        data = get_band_activity(band_id, threshold_db, filters)
        if not data:
            return _empty_figure("No data yet")
        fig = go.Figure(go.Bar(
            x=data["frequency_mhz"], y=data["activity_pct"],
            marker=dict(color=data["activity_pct"], colorscale="YlOrRd",
                        showscale=True, colorbar=dict(title="%", thickness=12)),
            hovertemplate="Freq: %{x:.3f} MHz<br>Active: %{y:.1f}%<extra></extra>",
        ))
        fig.update_layout(
            title=f"Activity above {threshold_db} dBFS",
            xaxis_title="Frequency (MHz)", yaxis_title="Time active (%)",
            yaxis=dict(range=[0, 100]),
            margin=dict(l=60, r=60, t=40, b=50),
            paper_bgcolor="#111", plot_bgcolor="#111", font=dict(color="#ddd"),
        )
        return fig


# ── Empty figure helpers ──────────────────────────────────────────────────────

def _empty_figure(message: str) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=message, xref="paper", yref="paper",
                       x=0.5, y=0.5, showarrow=False,
                       font=dict(size=14, color="#888"))
    fig.update_layout(
        paper_bgcolor="#111", plot_bgcolor="#111", font=dict(color="#ddd"),
        xaxis=dict(visible=False), yaxis=dict(visible=False),
        margin=dict(l=20, r=20, t=20, b=20),
    )
    return fig


def _empty_heatmap(message: str) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=message, xref="paper", yref="paper",
                       x=0.5, y=0.5, showarrow=False,
                       font=dict(size=16, color="#888"))
    fig.update_layout(
        paper_bgcolor="#111", plot_bgcolor="#111", font=dict(color="#ddd"),
        xaxis=dict(visible=False), yaxis=dict(visible=False),
        margin=dict(l=20, r=20, t=20, b=20),
    )
    return fig
