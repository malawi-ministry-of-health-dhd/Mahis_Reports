import os
import urllib.parse

import pandas as pd
from dash import Input, Output, html
from dash.exceptions import PreventUpdate
from config import DEMO_UUID, DEMO_LOCATION


def normalize_url_params(params):
    normalized = dict(params) if params else {}
    if not normalized.get("Location"):
        normalized["Location"] = [DEMO_LOCATION]
    if not normalized.get("uuid"):
        normalized["uuid"] = [DEMO_UUID]
    return normalized


def _build_query(route, location, uuid, user_level):
    if route and location and uuid and user_level:
        return f"?route={route}&Location={location}&uuid={uuid}&user_level={user_level}"
    if route and location and uuid:
        return f"?route={route}&Location={location}&uuid={uuid}"
    if location and uuid:
        return f"?route={route}&Location={location}&uuid={uuid}"
    return ""


def _build_nav(pathname_prefix, query, last_updated, show_admin):
    items = [
        html.Li(html.A("Dashboard", href=f"{pathname_prefix}home{query}", className="nav-link")),
        html.Li(html.A("HMIS DataSet Reports", href=f"{pathname_prefix}hmis_reports{query}", className="nav-link")),
        html.Li(html.A("Clinical Reports", href=f"{pathname_prefix}program_reports{query}", className="nav-link")),
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
            data_route = url_params.get("route", ["default"])[0] if url_params else None

            path = os.getcwd()
            timestamp_path = os.path.join(path, f"data/{data_route}", "TimeStamp.csv")
            os.makedirs(os.path.dirname(timestamp_path), exist_ok=True)
            users_path = os.path.join(path, f"data/{data_route}", "dcc_dropdown_json", "user_properties.json")
            os.makedirs(os.path.dirname(users_path), exist_ok=True)
            last_updated = pd.read_csv(timestamp_path)["saving_time"].to_list()[0]
            with open(users_path, "r") as f:
                users = pd.read_json(f)

            query = _build_query(data_route,location, uuid, user_level)
            
            existing   = next((u for u in users.get("users", []) if u.get("properties").get("uuid") == uuid), None)
            if existing and existing.get("properties").get("role").strip() == "reports_admin":
                is_admin = True
            elif not existing:
                if uuid == DEMO_UUID:
                    is_admin = True
                else:
                    is_admin = False
            else:
                is_admin = False

            return _build_nav(pathname_prefix, query, last_updated, is_admin)
        except Exception:
            import traceback
            traceback.print_exc()
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
        data_route = url_params.get("route", ["default"])[0] if url_params else None

        query = _build_query(data_route, location, uuid, user_level)

        try:
            path = os.getcwd()
            timestamp_path = os.path.join(path, f"data/{data_route}", "TimeStamp.csv")
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
