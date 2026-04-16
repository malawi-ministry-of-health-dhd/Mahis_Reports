import os
import urllib.parse

import pandas as pd
from dash import Input, Output, html
from dash.exceptions import PreventUpdate

DEMO_LOCATION = "LL040033"
DEMO_UUID = "m3his@dhd"


def normalize_url_params(params):
    normalized = dict(params) if params else {}
    if not normalized.get("Location"):
        normalized["Location"] = [DEMO_LOCATION]
    if not normalized.get("uuid"):
        normalized["uuid"] = [DEMO_UUID]
    return normalized


def _build_query(location, uuid, user_level):
    if location and uuid and user_level:
        return f"?Location={location}&uuid={uuid}&user_level={user_level}"
    if location and uuid:
        return f"?Location={location}&uuid={uuid}"
    if location and user_level:
        return f"?Location={location}&user_level={user_level}"
    if uuid and user_level:
        return f"?uuid={uuid}&user_level={user_level}"
    if location:
        return f"?Location={location}"
    if uuid:
        return f"?uuid={uuid}"
    if user_level:
        return f"?user_level={user_level}"
    return ""


def _build_nav(pathname_prefix, query, last_updated, show_admin):
    items = [
        html.Li(html.A("Dashboard", href=f"{pathname_prefix}home{query}", className="nav-link")),
        html.Li(html.A("HMIS DataSet Reports", href=f"{pathname_prefix}hmis_reports{query}", className="nav-link")),
        html.Li(html.A("Program Reports", href=f"{pathname_prefix}program_reports{query}", className="nav-link")),
    ]

    if show_admin:
        items.append(
            html.Li(html.A("Configure Reports", href=f"{pathname_prefix}reports_config{query}", className="nav-link"))
        )
    else:
        items.append(
            html.Li(
                html.A(
                    "Configure Reports",
                    href=f"{pathname_prefix}reports_config{query}",
                    className="nav-link",
                    style={"visibility": "hidden", "pointer-events": "none", "cursor": "default"},
                ),
                style={"visibility": "hidden"},
            )
        )

    items.append(
        html.Div(
            f"Last updated on: {last_updated}",
            style={"color": "grey", "font-size": "0.9rem", "margin-top": "5px", "font-style": "italic"},
        )
    )

    return html.Nav([html.Ul(items, className="nav-list")], className="navbar")


def register_navigation_callbacks(app, pathname_prefix):
    @app.callback(Output("nav-container", "children"), Input("url-params-store", "data"))
    def render_nav(url_params):
        try:
            url_params = normalize_url_params(url_params)
            location = url_params.get("Location", [None])[0]
            uuid = url_params.get("uuid", [None])[0]
            user_level = url_params.get("user_level", [None])[0]

            path = os.getcwd()
            timestamp_path = os.path.join(path, "data", "TimeStamp.csv")
            users_path = os.path.join(path, "data", "users_data.csv")
            last_updated = pd.read_csv(timestamp_path)["saving_time"].to_list()[0]
            users = pd.read_csv(users_path)

            query = _build_query(location, uuid, user_level)
            is_admin = uuid == DEMO_UUID

            if uuid in users["user_id"].tolist():
                role_string = users.query(f'user_id == "{uuid}"')["role"].iloc[0]
                roles_list = [r.strip() for r in role_string.split(",")]
                is_admin = "Superuser" in roles_list

            return _build_nav(pathname_prefix, query, last_updated, is_admin)
        except Exception:
            return _build_nav(pathname_prefix, "", "Unknown", False)

    @app.callback(Output("url-params-store", "data"), Input("url", "href"))
    def store_url_params(href):
        if not href:
            raise PreventUpdate
        parsed_url = urllib.parse.urlparse(href)
        params = urllib.parse.parse_qs(parsed_url.query)
        return normalize_url_params(params)

    @app.callback(Output("url", "pathname"), Input("url", "pathname"), prevent_initial_call=True)
    def redirect_to_home(pathname):
        if pathname == "/":
            return "/home"
        return pathname

    @app.callback(
        [
            Output("home-link", "href"),
            Output("hmis-reports-link", "href"),
            Output("programs-link", "href"),
            Output("admin-link", "href"),
            Output("last_updated", "children"),
        ],
        Input("url-params-store", "data"),
    )
    def update_nav_links(url_params):
        location = url_params.get("Location", [None])[0] if url_params else None
        uuid = url_params.get("uuid", [None])[0] if url_params else None
        user_level = url_params.get("user_level", [None])[0] if url_params else None
        query = _build_query(location, uuid, user_level)

        try:
            path = os.getcwd()
            timestamp_path = os.path.join(path, "data", "TimeStamp.csv")
            last_updated = pd.read_csv(timestamp_path)["saving_time"].to_list()[0]
            status = f"Last updated on: {last_updated}"
        except Exception as exc:
            status = f"Error loading last updated: {str(exc)}"

        return (
            f"{pathname_prefix}home{query}",
            f"{pathname_prefix}hmis_reports{query}",
            f"{pathname_prefix}program_reports{query}",
            f"{pathname_prefix}reports_config{query}",
            status,
        )
