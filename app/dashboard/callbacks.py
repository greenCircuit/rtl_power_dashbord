"""
All Dash callbacks.  Import functions directly — no HTTP round-trips needed
because Dash callbacks run server-side in the same process as Flask.
"""

import plotly.graph_objects as go
from dash import Input, Output, State, callback_context, no_update
from dash.exceptions import PreventUpdate

from app.capture.rtl_power import capture
from app.data.parser import (
    get_session_data,
    get_frequency_timeseries,
    get_frequency_stats,
    get_frequency_activity,
    list_sessions,
)

# ── Colour scale for the heatmap ────────────────────────────────────────────
COLORSCALE = "Plasma"


def register_callbacks(app) -> None:

    # ── 1. Start / Stop capture ─────────────────────────────────────────────
    @app.callback(
        Output("div-status", "children"),
        Output("store-active-session", "data"),
        Input("btn-start", "n_clicks"),
        Input("btn-stop", "n_clicks"),
        State("input-freq-start", "value"),
        State("select-freq-start-unit", "value"),
        State("input-freq-end", "value"),
        State("select-freq-end-unit", "value"),
        State("input-freq-step", "value"),
        State("select-freq-step-unit", "value"),
        State("input-interval", "value"),
        State("input-duration", "value"),
        State("store-active-session", "data"),
        prevent_initial_call=True,
    )
    def handle_capture_buttons(
        _start, _stop,
        freq_start, freq_start_unit,
        freq_end, freq_end_unit,
        freq_step, freq_step_unit,
        interval, duration,
        active_session,
    ):
        triggered = callback_context.triggered_id
        if triggered == "btn-start":
            duration = duration.strip() if duration else None
            try:
                session_id = capture.start(
                    f"{freq_start or 88}{freq_start_unit or 'M'}",
                    f"{freq_end or 108}{freq_end_unit or 'M'}",
                    f"{freq_step or 0.2}{freq_step_unit or 'M'}",
                    int(interval or 10),
                    duration or None,
                )
                return f"Capturing — session {session_id}", session_id
            except RuntimeError as exc:
                return f"Error: {exc}", active_session

        if triggered == "btn-stop":
            capture.stop()
            return f"Stopped — session {active_session}", active_session

        raise PreventUpdate

    # ── 2. Refresh session dropdown + status every poll interval ────────────
    @app.callback(
        Output("dropdown-session", "options"),
        Output("dropdown-session", "value"),
        Output("div-status", "children", allow_duplicate=True),
        Input("interval-poll", "n_intervals"),
        State("store-active-session", "data"),
        prevent_initial_call=True,
    )
    def refresh_session_list(_, active_session):
        sessions = list_sessions()
        options = [
            {"label": s["id"], "value": s["id"]}
            for s in sessions
        ]

        # Auto-select the active session; otherwise keep current dropdown value
        selected = active_session if active_session else (sessions[0]["id"] if sessions else None)

        status_text = f"Capture status: {capture.status}"
        if capture.current_session:
            status_text += f"  |  Session: {capture.current_session}"
        if capture.error:
            status_text += f"  |  ⚠ {capture.error}"

        return options, selected, status_text

    # ── 3. Update heatmap when session changes or poll fires ─────────────────
    @app.callback(
        Output("graph-heatmap", "figure"),
        Input("dropdown-session", "value"),
        Input("interval-poll", "n_intervals"),
        State("store-active-session", "data"),
    )
    def update_heatmap(selected_session, _, active_session):
        session_id = selected_session or active_session
        if not session_id:
            return _empty_heatmap("No session selected")

        data = get_session_data(session_id)
        if not data:
            return _empty_heatmap(f"No data yet for {session_id}")

        fig = go.Figure(
            go.Heatmap(
                x=data["x"],
                y=data["y"],
                z=data["z"],
                colorscale=COLORSCALE,
                colorbar=dict(title="dBFS"),
                hoverongaps=False,
                hovertemplate=(
                    "Time: %{x}<br>"
                    "Freq: %{y:.3f} MHz<br>"
                    "Power: %{z:.1f} dB<extra></extra>"
                ),
            )
        )
        fig.update_layout(
            title=f"Spectrum heatmap — {session_id}",
            xaxis_title="Time",
            yaxis_title="Frequency (MHz)",
            margin=dict(l=60, r=20, t=50, b=50),
            paper_bgcolor="#111",
            plot_bgcolor="#111",
            font=dict(color="#ddd"),
        )
        return fig

    # ── 4. Time-series when user clicks a point on the heatmap ───────────────
    @app.callback(
        Output("graph-timeseries", "figure"),
        Input("graph-heatmap", "clickData"),
        State("dropdown-session", "value"),
        State("store-active-session", "data"),
        prevent_initial_call=True,
    )
    def update_timeseries(click_data, selected_session, active_session):
        if not click_data:
            raise PreventUpdate

        session_id = selected_session or active_session
        freq_mhz = click_data["points"][0]["y"]
        data = get_frequency_timeseries(session_id, freq_mhz)
        if not data:
            raise PreventUpdate

        fig = go.Figure(
            go.Scatter(
                x=data["timestamps"],
                y=data["power_db"],
                mode="lines+markers",
                line=dict(color="#f0a500", width=1.5),
                marker=dict(size=3),
                hovertemplate="Time: %{x}<br>Power: %{y:.1f} dB<extra></extra>",
            )
        )
        fig.update_layout(
            title=f"Power over time — {data['frequency_mhz']:.3f} MHz",
            xaxis_title="Time",
            yaxis_title="Power (dBFS)",
            margin=dict(l=60, r=20, t=40, b=50),
            paper_bgcolor="#111",
            plot_bgcolor="#111",
            font=dict(color="#ddd"),
        )
        return fig


    # ── 5. Mean & peak spectrum ──────────────────────────────────────────────
    @app.callback(
        Output("graph-spectrum", "figure"),
        Input("dropdown-session", "value"),
        Input("interval-poll", "n_intervals"),
        State("store-active-session", "data"),
    )
    def update_spectrum(selected_session, _, active_session):
        session_id = selected_session or active_session
        if not session_id:
            return _empty_figure("No session selected")

        data = get_frequency_stats(session_id)
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
            xaxis_title="Frequency (MHz)",
            yaxis_title="Power (dBFS)",
            legend=dict(orientation="h", y=1.1),
            margin=dict(l=60, r=20, t=50, b=50),
            paper_bgcolor="#111",
            plot_bgcolor="#111",
            font=dict(color="#ddd"),
        )
        return fig

    # ── 6. Activity % per frequency ──────────────────────────────────────────
    @app.callback(
        Output("graph-activity", "figure"),
        Input("dropdown-session", "value"),
        Input("interval-poll", "n_intervals"),
        Input("slider-threshold", "value"),
        State("store-active-session", "data"),
    )
    def update_activity(selected_session, _, threshold_db, active_session):
        session_id = selected_session or active_session
        if not session_id:
            return _empty_figure("No session selected")

        data = get_frequency_activity(session_id, threshold_db)
        if not data:
            return _empty_figure("No data yet")

        fig = go.Figure(go.Bar(
            x=data["frequency_mhz"],
            y=data["activity_pct"],
            marker=dict(
                color=data["activity_pct"],
                colorscale="YlOrRd",
                showscale=True,
                colorbar=dict(title="%", thickness=12),
            ),
            hovertemplate="Freq: %{x:.3f} MHz<br>Active: %{y:.1f}%<extra></extra>",
        ))
        fig.update_layout(
            title=f"Activity above {threshold_db} dBFS",
            xaxis_title="Frequency (MHz)",
            yaxis_title="Time active (%)",
            yaxis=dict(range=[0, 100]),
            margin=dict(l=60, r=60, t=40, b=50),
            paper_bgcolor="#111",
            plot_bgcolor="#111",
            font=dict(color="#ddd"),
        )
        return fig


def _empty_figure(message: str) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(
        text=message,
        xref="paper", yref="paper",
        x=0.5, y=0.5, showarrow=False,
        font=dict(size=14, color="#888"),
    )
    fig.update_layout(
        paper_bgcolor="#111", plot_bgcolor="#111",
        font=dict(color="#ddd"),
        xaxis=dict(visible=False), yaxis=dict(visible=False),
        margin=dict(l=20, r=20, t=20, b=20),
    )
    return fig


def _empty_heatmap(message: str) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(
        text=message,
        xref="paper", yref="paper",
        x=0.5, y=0.5,
        showarrow=False,
        font=dict(size=16, color="#888"),
    )
    fig.update_layout(
        paper_bgcolor="#111",
        plot_bgcolor="#111",
        font=dict(color="#ddd"),
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        margin=dict(l=20, r=20, t=20, b=20),
    )
    return fig
