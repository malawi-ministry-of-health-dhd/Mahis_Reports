import dash
from dash import html, dcc, page_container, page_registry, Output, Input, State, callback
import dash_mantine_components as dmc
import os
import urllib.parse
import plotly.express as px
import pandas as pd
from dash.exceptions import PreventUpdate
from config import PREFIX_NAME
from helpers.api_routes import register_api_routes

external_stylesheets = ['https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css']
DEMO_LOCATION = "LL040033"
DEMO_UUID = "m3his@dhd"


def normalize_url_params(params):
    normalized = dict(params) if params else {}
    if not normalized.get("Location"):
        normalized["Location"] = [DEMO_LOCATION]
    if not normalized.get("uuid"):
        normalized["uuid"] = [DEMO_UUID]
    return normalized

# print(list(load_stored_data())) # Load the data to ensure it's available
# Initialize the Dash app
# pathname_prefix = '/reports/' # Adjust this if your app is served from a subpath
pathname_prefix = PREFIX_NAME if PREFIX_NAME else '/'
app = dash.Dash(
                __name__,
                use_pages=True,
                suppress_callback_exceptions=True,
                requests_pathname_prefix=pathname_prefix
                )
server = app.server

# MantineProvider wraps the whole app so DMC components work on any page
app.layout = dmc.MantineProvider(
    children=html.Div([
        dcc.Location(id='url', refresh=False),
        dcc.Store(id='url-params-store', storage_type='session'),
        html.Div(id="nav-container"),
        page_container,
    ], style={'margin': '20px', 'fontFamily': 'Arial, sans-serif'})
)

@app.callback(
    Output("nav-container", "children"),
    Input("url-params-store", "data")
)
def render_nav(url_params):
    try:
        url_params = normalize_url_params(url_params)
        location = url_params.get('Location', [None])[0] if url_params else None
        uuid = url_params.get('uuid', [None])[0] if url_params else None
        user_level = url_params.get('user_level', [None])[0] if url_params else None
        path = os.getcwd()
        timestamp_path = os.path.join(path, 'data','TimeStamp.csv')
        users_path = os.path.join(path, 'data','users_data.csv')
        last_updated = pd.read_csv(timestamp_path)['saving_time'].to_list()[0]
        users = pd.read_csv(users_path)

        query = ""
        if location and uuid and user_level:
            query = f"?Location={location}&uuid={uuid}&user_level={user_level}"
        elif location and uuid:
            query = f"?Location={location}&uuid={uuid}"
        elif location:
            query = f"?Location={location}"
        elif uuid:
            query = f"?uuid={uuid}"

        nav_with_admin = html.Nav([
                            html.Ul([
                                html.Li(html.A("Dashboard", href=f"{pathname_prefix}home{query}", className="nav-link")),
                                html.Li(html.A("HMIS DataSet Reports", href=f"{pathname_prefix}hmis_reports{query}", className="nav-link")),
                                html.Li(html.A("Program Reports", href=f"{pathname_prefix}program_reports{query}", className="nav-link")),
                                html.Li(html.A("Configure Reports", href=f"{pathname_prefix}reports_config{query}", className="nav-link")),
                                html.Div(
                                    f"Last updated on: {last_updated}",
                                    style={"color":"grey","font-size":"0.9rem","margin-top":"5px","font-style":"italic"}
                                )
                            ], className="nav-list")
                        ], className="navbar")
        nav_without_admin = html.Nav([
                                html.Ul([
                                    html.Li(html.A("Dashboard", href=f"{pathname_prefix}home{query}", className="nav-link")),
                                    html.Li(html.A("HMIS DataSet Reports", href=f"{pathname_prefix}hmis_reports{query}", className="nav-link")),
                                    html.Li(html.A("Program Reports", href=f"{pathname_prefix}program_reports{query}", className="nav-link")),
                                    html.Li(html.A("Configure Reports", href=f"{pathname_prefix}reports_config{query}", className="nav-link",
                                                style={'visibility': 'hidden', 'pointer-events': 'none', 'cursor': 'default'}),
                                                    style={'visibility': 'hidden'}),
                                    html.Div(
                                        f"Last updated on: {last_updated}",
                                        style={"color":"grey","font-size":"0.9rem","margin-top":"5px","font-style":"italic"}
                                    )
                                ], className="nav-list")
                            ], className="navbar")
        
        if uuid in users['user_id'].tolist():
            role_string = users.query(f'user_id == "{uuid}"')['role'].iloc[0]
            roles_list = [r.strip() for r in role_string.split(',')]
            print(roles_list)

            if "Superuser,Superuser," in roles_list:
                return nav_with_admin
            else:
                return nav_without_admin
        elif uuid == 'm3his@dhd':
            return nav_with_admin
        else:
            return 
    except Exception as e:
        import traceback
        traceback.print_exc()
        return nav_without_admin

@callback(
    Output('url-params-store', 'data'),
    Input('url', 'href')
)
def store_url_params(href):
    if not href:
        raise PreventUpdate
    parsed_url = urllib.parse.urlparse(href)
    params = urllib.parse.parse_qs(parsed_url.query)

    return normalize_url_params(params)

@app.callback(
    Output('url', 'pathname'),
    Input('url', 'pathname'),
    prevent_initial_call=True
)
def redirect_to_home(pathname):
    if pathname == "/":
        return "/home"
    return pathname

@app.callback(
    [Output('home-link', 'href'),
     Output('hmis-reports-link', 'href'),
     Output('programs-link', 'href'),
     Output('admin-link', 'href'),
     Output('last_updated','children')
    ],
    Input('url-params-store', 'data')
)
def update_nav_links(url_params):
    try:
        location = url_params.get('Location', [None])[0] if url_params else None
        uuid = url_params.get('uuid', [None])[0] if url_params else None
        user_level = url_params.get('user_level', [None])[0] if url_params else None
        # print(f"Updating nav links with Location: {location}, UUID: {uuid}, User Level: {user_level}")
        # query = f"?Location={location}&uuid={uuid}" if location and uuid else f"?Location={location}" if location else f"?uuid={uuid}" if uuid else ""
        query = f"?Location={location}&uuid={uuid}&user_level={user_level}" if location and uuid and user_level else \
                f"?Location={location}&uuid={uuid}" if location and uuid else \
                f"?Location={location}&user_level={user_level}" if location and user_level else \
                f"?uuid={uuid}&user_level={user_level}" if uuid and user_level else \
                f"?Location={location}" if location else f"?uuid={uuid}" if uuid else f"?user_level={user_level}" if user_level else ""
        path = os.getcwd()
        json_path = os.path.join(path, 'data','TimeStamp.csv')
        last_updated = pd.read_csv(json_path)['saving_time'].to_list()[0]

        return (
            f"{pathname_prefix}home{query}",
            f"{pathname_prefix}hmis_reports{query}",
            f"{pathname_prefix}program_reports{query}",
            f"{pathname_prefix}reports_config{query}",
            f"Last updated on: {last_updated}"
        )
    except Exception as e:
        return (
            f"{pathname_prefix}home{query}",
            f"{pathname_prefix}hmis_reports{query}",
            f"{pathname_prefix}program_reports{query}",
            f"{pathname_prefix}reports_config{query}",
            f"Error loading last updated: {str(e)}"
        )

register_api_routes(server)

# Run the app
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8050, debug=True,)
