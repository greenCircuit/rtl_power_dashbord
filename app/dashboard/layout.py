from dash import dcc, html
import dash_bootstrap_components as dbc


def create_layout() -> html.Div:
    return dbc.Container(
        fluid=True,
        children=[

            # ── Header ──────────────────────────────────────────────────────
            dbc.Row(
                dbc.Col(html.H2("RTL Power Dashboard", className="my-3 text-center"))
            ),

            # ── Band management card ─────────────────────────────────────────
            dbc.Card(
                dbc.CardBody([
                    dbc.Row([
                        dbc.Col(html.H6("Bands", className="mb-0 fw-bold"), width="auto",
                                className="d-flex align-items-center"),
                        dbc.Col(
                            dbc.Button("+ Add Band", id="btn-add-band", color="primary",
                                       size="sm", n_clicks=0),
                            width="auto",
                        ),
                    ], className="mb-2"),
                    html.Div(id="div-band-table"),
                ]),
                className="mb-3",
            ),

            # ── Add / Edit band modal ────────────────────────────────────────
            dbc.Modal([
                dbc.ModalHeader(dbc.ModalTitle(id="modal-band-title")),
                dbc.ModalBody([
                    dbc.Row([
                        dbc.Col([
                            dbc.Label("Name"),
                            dbc.Input(id="modal-band-name", type="text",
                                      placeholder="e.g. FM Radio", style={"fontSize": "1.1rem", "height": "2.8rem"}),
                        ], width=12, className="mb-2"),
                    ]),
                    dbc.Row([
                        dbc.Col([
                            dbc.Label("Freq Start"),
                            dbc.InputGroup([
                                dbc.Input(id="modal-freq-start", type="number",
                                          placeholder="88", style={"fontSize": "1.1rem", "height": "2.8rem"}),
                                dbc.Select(id="modal-freq-start-unit",
                                           options=[{"label": "kHz", "value": "k"},
                                                    {"label": "MHz", "value": "M"},
                                                    {"label": "GHz", "value": "G"}],
                                           value="M", style={"maxWidth": "90px", "fontSize": "1.1rem", "height": "2.8rem"}),
                            ]),
                        ], width=4),
                        dbc.Col([
                            dbc.Label("Freq End"),
                            dbc.InputGroup([
                                dbc.Input(id="modal-freq-end", type="number",
                                          placeholder="108", style={"fontSize": "1.1rem", "height": "2.8rem"}),
                                dbc.Select(id="modal-freq-end-unit",
                                           options=[{"label": "kHz", "value": "k"},
                                                    {"label": "MHz", "value": "M"},
                                                    {"label": "GHz", "value": "G"}],
                                           value="M", style={"maxWidth": "90px", "fontSize": "1.1rem", "height": "2.8rem"}),
                            ]),
                        ], width=4),
                        dbc.Col([
                            dbc.Label("Step"),
                            dbc.InputGroup([
                                dbc.Input(id="modal-freq-step", type="number",
                                          placeholder="0.2", style={"fontSize": "1.1rem", "height": "2.8rem"}),
                                dbc.Select(id="modal-freq-step-unit",
                                           options=[{"label": "kHz", "value": "k"},
                                                    {"label": "MHz", "value": "M"},
                                                    {"label": "GHz", "value": "G"}],
                                           value="M", style={"maxWidth": "90px", "fontSize": "1.1rem", "height": "2.8rem"}),
                            ]),
                        ], width=4),
                    ], className="mb-2"),
                    dbc.Row([
                        dbc.Col([
                            dbc.Label("Interval (s)"),
                            dbc.Input(id="modal-interval", type="number",
                                      value=10, min=1, style={"fontSize": "1.1rem", "height": "2.8rem"}),
                        ], width=4),
                        dbc.Col([
                            dbc.Label("Min Power (dB)"),
                            dbc.Input(id="modal-record-threshold", type="number",
                                      value=2, step=0.5, style={"fontSize": "1.1rem", "height": "2.8rem"}),
                        ], width=4),
                        dbc.Col([
                            dbc.Label("Device index"),
                            dbc.Input(id="modal-device-index", type="number",
                                      value=0, min=0, style={"fontSize": "1.1rem", "height": "2.8rem"}),
                        ], width=4),
                    ], className="mb-2"),
                    html.Div(id="modal-band-error", className="text-danger small"),
                ]),
                dbc.ModalFooter([
                    dbc.Button("Save", id="btn-modal-save", color="primary",
                               n_clicks=0),
                    dbc.Button("Cancel", id="btn-modal-cancel", color="secondary",
                               n_clicks=0, className="ms-2"),
                ]),
            ], id="modal-band", is_open=False, size="lg"),

            # ── Band selector + status ───────────────────────────────────────
            dbc.Row([
                dbc.Col([
                    dbc.Label("Viewing band"),
                    dcc.Dropdown(id="dropdown-band",
                                 placeholder="Select a band…",
                                 clearable=False),
                ], width=4),
                dbc.Col(
                    html.Div(id="div-status", className="text-muted small mt-4"),
                    width=8,
                ),
            ], className="mb-2"),

            # ── Filter panel ─────────────────────────────────────────────────
            dbc.Card(
                dbc.CardBody(html.Div([
                    dbc.Row([
                        dbc.Col(html.Span("Filters", className="fw-semibold"),
                                width="auto", className="d-flex align-items-center"),
                        dbc.Col(
                            dbc.ButtonGroup([
                                dbc.Button("15m",   id="btn-range-15m",  color="outline-secondary", size="sm", n_clicks=0),
                                dbc.Button("1h",    id="btn-range-1h",   color="outline-secondary", size="sm", n_clicks=0),
                                dbc.Button("12h",   id="btn-range-12h",  color="outline-secondary", size="sm", n_clicks=0),
                                dbc.Button("1d",    id="btn-range-1d",   color="outline-secondary", size="sm", n_clicks=0),
                                dbc.Button("7d",    id="btn-range-7d",   color="outline-secondary", size="sm", n_clicks=0),
                                dbc.Button("All",   id="btn-range-all",  color="outline-secondary", size="sm", n_clicks=0),
                            ]),
                            width="auto",
                        ),
                        dbc.Col([
                            dbc.Label("Freq Min (MHz)", className="small mb-1"),
                            dbc.Input(id="filter-freq-min", type="number",
                                      placeholder="e.g. 88", debounce=True),
                        ], width=2),
                        dbc.Col([
                            dbc.Label("Freq Max (MHz)", className="small mb-1"),
                            dbc.Input(id="filter-freq-max", type="number",
                                      placeholder="e.g. 108", debounce=True),
                        ], width=2),
                        dbc.Col([
                            dbc.Label("Time Start", className="small mb-1"),
                            dbc.Input(id="filter-time-start", type="datetime-local",
                                      debounce=True),
                        ], width=3),
                        dbc.Col([
                            dbc.Label("Time End", className="small mb-1"),
                            dbc.Input(id="filter-time-end", type="datetime-local",
                                      debounce=True),
                        ], width=3),
                        dbc.Col([
                            dbc.Label("\u00a0", className="small mb-1"),
                            dbc.Button("Clear", id="btn-filter-clear",
                                       color="secondary", size="sm",
                                       n_clicks=0, className="w-100"),
                        ], width=1, className="d-flex flex-column"),
                    ], align="end", className="mb-2"),
                    dbc.Row([
                        dbc.Col(
                            dbc.Label("Min Power (dBFS):", className="small text-muted mt-1"),
                            width="auto",
                        ),
                        dbc.Col(
                            dcc.Slider(
                                id="filter-power-min",
                                min=-20, max=20, step=1, value=-20,
                                marks={v: {"label": str(v), "style": {"color": "#ddd"}}
                                       for v in range(-20, 21, 5)},
                                tooltip={"placement": "bottom", "always_visible": True,
                                         "style": {"background": "#222", "color": "#ddd"}},
                            ),
                        ),
                    ], align="center", className="px-1"),
                ])),
                className="mb-2 border-secondary",
                style={"borderStyle": "dashed"},
            ),

            # ── Heatmap ─────────────────────────────────────────────────────
            dbc.Row(
                dbc.Col(dcc.Graph(id="graph-heatmap", style={"height": "480px"},
                                  config={"scrollZoom": True}))
            ),

            # ── Time-series for clicked frequency ────────────────────────────
            dbc.Row(
                dbc.Col(dcc.Graph(id="graph-timeseries", style={"height": "240px"})),
                className="mt-2",
            ),

            # ── Frequency usage panels ───────────────────────────────────────
            dbc.Row(dbc.Col(html.H5("Frequency Usage", className="mt-4 mb-2"))),
            dbc.Row([
                dbc.Col(
                    dcc.Graph(id="graph-spectrum", style={"height": "300px"}),
                    width=6,
                ),
                dbc.Col([
                    dcc.Graph(id="graph-activity", style={"height": "240px"}),
                    dbc.Row([
                        dbc.Col(
                            dbc.Label("Activity threshold (dBFS):",
                                      className="text-muted small mt-1"),
                            width="auto",
                        ),
                        dbc.Col(
                            dcc.Slider(
                                id="slider-threshold",
                                min=-20, max=20, step=1, value=0,
                                marks={v: {"label": str(v), "style": {"color": "#ddd"}}
                                       for v in range(-20, 21, 5)},
                                tooltip={"placement": "bottom", "always_visible": True,
                                         "style": {"background": "#222", "color": "#ddd"}},
                            ),
                        ),
                    ], align="center", className="px-3"),
                ], width=6),
            ], className="mt-2"),

            # ── Hidden plumbing ──────────────────────────────────────────────
            dcc.Interval(id="interval-poll", interval=5_000, n_intervals=0),
            dcc.Store(id="store-filters", data={}),
            dcc.Store(id="store-time-range", data="btn-range-12h"),
            # Holds the band_id being edited (None = adding new)
            dcc.Store(id="store-editing-band"),
        ],
    )
