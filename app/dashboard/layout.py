from dash import dcc, html
import dash_bootstrap_components as dbc


def create_layout() -> html.Div:
    return dbc.Container(
        fluid=True,
        children=[
            # ── Header ──────────────────────────────────────────────────────
            dbc.Row(
                dbc.Col(
                    html.H2("RTL Power Dashboard", className="my-3 text-center")
                )
            ),

            # ── Control panel ───────────────────────────────────────────────
            dbc.Card(
                dbc.CardBody(
                    dbc.Row(
                        [
                            # Frequency inputs
                            dbc.Col(
                                [
                                    dbc.Label("Freq Start"),
                                    dbc.InputGroup([
                                        dbc.Input(id="input-freq-start", value="88",
                                                  type="number", placeholder="88"),
                                        dbc.Select(
                                            id="select-freq-start-unit",
                                            options=[
                                                {"label": "kHz", "value": "k"},
                                                {"label": "MHz", "value": "M"},
                                                {"label": "GHz", "value": "G"},
                                            ],
                                            value="M",
                                            style={"maxWidth": "80px"},
                                        ),
                                    ]),
                                ],
                                width=2,
                            ),
                            dbc.Col(
                                [
                                    dbc.Label("Freq End"),
                                    dbc.InputGroup([
                                        dbc.Input(id="input-freq-end", value="108",
                                                  type="number", placeholder="108"),
                                        dbc.Select(
                                            id="select-freq-end-unit",
                                            options=[
                                                {"label": "kHz", "value": "k"},
                                                {"label": "MHz", "value": "M"},
                                                {"label": "GHz", "value": "G"},
                                            ],
                                            value="M",
                                            style={"maxWidth": "80px"},
                                        ),
                                    ]),
                                ],
                                width=2,
                            ),
                            dbc.Col(
                                [
                                    dbc.Label("Step"),
                                    dbc.InputGroup([
                                        dbc.Input(id="input-freq-step", value="0.2",
                                                  type="number", placeholder="0.2"),
                                        dbc.Select(
                                            id="select-freq-step-unit",
                                            options=[
                                                {"label": "kHz", "value": "k"},
                                                {"label": "MHz", "value": "M"},
                                                {"label": "GHz", "value": "G"},
                                            ],
                                            value="M",
                                            style={"maxWidth": "80px"},
                                        ),
                                    ]),
                                ],
                                width=2,
                            ),
                            dbc.Col(
                                [
                                    dbc.Label("Interval (s)"),
                                    dbc.Input(id="input-interval", value=10,
                                              type="number", min=1),
                                ],
                                width=1,
                            ),
                            dbc.Col(
                                [
                                    dbc.Label("Duration"),
                                    dbc.Input(id="input-duration", value="",
                                              placeholder="e.g. 1h (blank=∞)"),
                                ],
                                width=2,
                            ),
                            # Start / Stop
                            dbc.Col(
                                [
                                    dbc.Label("\u00a0"),
                                    dbc.ButtonGroup(
                                        [
                                            dbc.Button("▶ Start", id="btn-start",
                                                       color="success", n_clicks=0),
                                            dbc.Button("■ Stop", id="btn-stop",
                                                       color="danger", n_clicks=0),
                                        ],
                                        className="d-flex",
                                    ),
                                ],
                                width=2,
                                className="d-flex flex-column",
                            ),
                            # Session selector
                            dbc.Col(
                                [
                                    dbc.Label("Load session"),
                                    dcc.Dropdown(
                                        id="dropdown-session",
                                        placeholder="Select a session…",
                                        clearable=False,
                                    ),
                                ],
                                width=3,
                            ),
                        ],
                        align="end",
                    )
                ),
                className="mb-3",
            ),

            # ── Status bar ──────────────────────────────────────────────────
            dbc.Row(
                dbc.Col(
                    html.Div(id="div-status", className="text-muted small mb-2")
                )
            ),

            # ── Heatmap ─────────────────────────────────────────────────────
            dbc.Row(
                dbc.Col(
                    dcc.Graph(
                        id="graph-heatmap",
                        style={"height": "480px"},
                        config={"scrollZoom": True},
                    )
                )
            ),

            # ── Time-series for clicked frequency ────────────────────────────
            dbc.Row(
                dbc.Col(
                    dcc.Graph(id="graph-timeseries", style={"height": "240px"})
                ),
                className="mt-2",
            ),

            # ── Frequency usage panels ───────────────────────────────────────
            dbc.Row(
                dbc.Col(html.H5("Frequency Usage", className="mt-4 mb-2"))
            ),
            dbc.Row(
                [
                    # Mean & peak spectrum
                    dbc.Col(
                        dcc.Graph(id="graph-spectrum", style={"height": "300px"}),
                        width=6,
                    ),
                    # Activity % with threshold slider
                    dbc.Col(
                        [
                            dcc.Graph(id="graph-activity", style={"height": "240px"}),
                            dbc.Row(
                                [
                                    dbc.Col(
                                        dbc.Label("Activity threshold (dBFS):",
                                                  className="text-muted small mt-1"),
                                        width="auto",
                                    ),
                                    dbc.Col(
                                        dcc.Slider(
                                            id="slider-threshold",
                                            min=-120, max=0, step=1, value=-70,
                                            marks={v: str(v) for v in range(-120, 1, 20)},
                                            tooltip={"placement": "bottom",
                                                     "always_visible": True},
                                        ),
                                    ),
                                ],
                                align="center",
                                className="px-3",
                            ),
                        ],
                        width=6,
                    ),
                ],
                className="mt-2",
            ),

            # ── Hidden plumbing ─────────────────────────────────────────────
            # Fires every 5 s to refresh live data and session list
            dcc.Interval(id="interval-poll", interval=5_000, n_intervals=0),
            # Stores the currently displayed session id
            dcc.Store(id="store-active-session"),
        ],
    )
