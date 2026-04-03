import dash
import dash_bootstrap_components as dbc
from flask import Flask

from app.dashboard.layout import create_layout
from app.dashboard.callbacks import register_callbacks


def create_app() -> Flask:
    server = Flask(__name__)

    # Register REST API blueprint
    from app.api.routes import api_bp
    server.register_blueprint(api_bp)

    # Mount Dash on the same Flask server at "/"
    dash_app = dash.Dash(
        __name__,
        server=server,
        url_base_pathname="/",
        external_stylesheets=[dbc.themes.DARKLY],
        title="RTL Power Dashboard",
        suppress_callback_exceptions=True,
    )
    dash_app.layout = create_layout()
    register_callbacks(dash_app)

    return server
