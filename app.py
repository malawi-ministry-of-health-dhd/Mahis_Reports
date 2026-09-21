import logging
import dash
import dash_mantine_components as dmc
import plotly.express as px
from dash import dcc, html, page_container
from config import PREFIX_NAME, DEMO_UUID, DEMO_LOCATION

logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s %(levelname)s %(name)s %(message)s',
)
logging.getLogger('mnid').setLevel(logging.INFO)

# Warm plotly's shared 'plotly_white' template once here, single-threaded,
# before the dev server starts accepting concurrent requests. Every
# px.line/px.bar call across helpers/visualizations.py passes
# template='plotly_white' as a *string*, which Plotly Express resolves by
# looking up the same shared pio.templates['plotly_white'] object each
# time; that object lazily builds an internal child-index cache on first
# property access. Two threads (e.g. a background MNID preload thread and
# a live page request) touching it for the first time at the same instant
# corrupt that cache and crash deep in plotly internals with
# "ValueError: Invalid value" (reproduced and confirmed fixed by this
# warm-up in isolation before adding it here). Belongs here, not in
# visualizations.py, since it must run exactly once at process startup.
px.line(x=[0], y=[0], template='plotly_white')

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
    # threaded=True matters a lot more than it used to now that MNID renders
    # can take several seconds on a big facility/date selection -- Flask's
    # dev server defaults to single-threaded, so one slow callback blocked
    # *every* other concurrent request on this same process, including the
    # browser's own parallel request for plotly.js's static JS bundle. That
    # showed up in the browser console as "plotly.js did not load after 30
    # seconds" (queued behind the slow callback, not actually failing to
    # load) followed by a React crash trying to render the raw figure object
    # as a fallback, and felt to the user like "the spinner never stops"
    # even though the server-side render did eventually finish. Production
    # (gunicorn --workers 4) was never affected -- concurrent requests there
    # land on different worker processes.
    app.run(host="0.0.0.0", port=8050, debug=True, threaded=True)
