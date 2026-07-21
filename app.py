import logging
import dash
import dash_mantine_components as dmc
from dash import dcc, html, page_container
from config import PREFIX_NAME, DEMO_UUID, DEMO_LOCATION

logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s %(levelname)s %(name)s %(message)s',
)
logging.getLogger('mnid').setLevel(logging.INFO)
from helpers.api_routes import register_api_routes
from helpers.navigation_callbacks import register_navigation_callbacks
from mnid.app import register_mnid_callbacks

pathname_prefix = PREFIX_NAME if PREFIX_NAME else "/"

# external_stylesheets = [
#     "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css"
# ]

app = dash.Dash(
    __name__,
    use_pages=True,
    suppress_callback_exceptions=True,
    requests_pathname_prefix=pathname_prefix,
    # external_stylesheets=external_stylesheets
)
app.title = "Maternal and Neonatal Outcomes Dashboard"
server = app.server

app.layout = dmc.MantineProvider(
    children=html.Div(
        [
            dcc.Location(id="url", refresh=False),
            dcc.Store(id="url-params-store", storage_type="memory"),
            html.Div(id="nav-container"),
            page_container,
        ],
        style={"margin": "20px", "fontFamily": "Arial, sans-serif"},
    )
)

register_navigation_callbacks(app, pathname_prefix)
# register_mnid_callbacks(app)
register_api_routes(server)

if __name__ == "__main__":
    print(f"Start your app on: http://localhost:8050/home?route=default&Location={DEMO_LOCATION}&uuid={DEMO_UUID}&user_level=national")
    app.run(host="0.0.0.0", port=8050, debug=True)
