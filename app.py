import dash
import dash_mantine_components as dmc
from dash import dcc, html, page_container
import threading

from config import PREFIX_NAME, DATA_FILE_NAME_
from helpers.api_routes import register_api_routes
from helpers.navigation_callbacks import register_navigation_callbacks

pathname_prefix = PREFIX_NAME if PREFIX_NAME else "/"

app = dash.Dash(
    __name__,
    use_pages=True,
    suppress_callback_exceptions=True,
    requests_pathname_prefix=pathname_prefix,
)
server = app.server

app.layout = dmc.MantineProvider(
    children=html.Div(
        [
            dcc.Location(id="url", refresh=False),
            dcc.Store(id="url-params-store", storage_type="session"),
            html.Div(id="nav-container"),
            page_container,
        ],
        style={"margin": "20px", "fontFamily": "Arial, sans-serif"},
    )
)

register_navigation_callbacks(app, pathname_prefix)
register_api_routes(server)


def _prewarm_mnid_cache():
    try:
        import pandas as pd
        from data_storage import DataStorage
        from mnid.app import _network_df_cache, _prepare_mnid_dataframe
        sql = f"SELECT * FROM 'data/{DATA_FILE_NAME_}'"
        df = DataStorage.query_duckdb(sql)
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        key = (len(df), tuple(df.columns.tolist()))
        if key not in _network_df_cache:
            _network_df_cache[key] = _prepare_mnid_dataframe(df)
    except Exception:
        pass

threading.Thread(target=_prewarm_mnid_cache, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8050, debug=True)
