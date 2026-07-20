import dash
from dash import html, dcc, Input, Output, callback, State, no_update, ALL, callback_context, ctx
import pandas as pd
import plotly.express as px
import os
import json
import numpy as np
from dash.exceptions import PreventUpdate
from flask import request
from helpers.helpers import build_charts_section, build_metrics_section
from mnid_renderer import render_mnid_dashboard
from dashboard_layouts import build_premium_dashboard
from dash import ctx
from helpers.visualizations import create_line_list_basic_modal
from datetime import datetime
from datetime import datetime as dt
from data_storage import DataStorage
from config import DATA_PATH_,CUSTOM_GENDER_MAP
import warnings
import duckdb
warnings.filterwarnings("ignore")
from helpers.date_ranges import (
                    get_relative_date_range,
                    RELATIVE_PERIOD_LIST
            )
from helpers.navigation_callbacks import DEMO_UUID, DEMO_LOCATION
from dash_iconify import DashIconify

def nav_icon(icon_name):
    return DashIconify(icon=icon_name, className="nav-icon")

# Importing parquet file path and from config

# importing referential columns from config
from config import (actual_keys_in_data, 
                    DATA_PATH_, DEMO_UUID, DEMO_LOCATION,
                    DATE_, PERSON_ID_, ENCOUNTER_ID_,
                    FACILITY_,DISTRICT_, AGE_GROUP_, AGE_,
                    GENDER_, ENCOUNTER_, PROGRAM_,
                    NEW_REVISIT_, 
                    HOME_DISTRICT_, 
                    TA_, 
                    VILLAGE_, 
                    FACILITY_CODE_,
                    OBS_VALUE_CODED_,
                    CONCEPT_NAME_,
                    VALUE_,
                    VALUE_NUMERIC_,
                    DRUG_NAME_,
                    VALUE_NAME_)

dash.register_page(__name__, path="/home")

pd.options.mode.chained_assignment = None

path = os.getcwd()
json_path = os.path.join(path, 'data', 'visualizations', 'validated_dashboard.json')
dashboard_tabs_config_path = os.path.join(path, 'data', 'visualizations', 'dashboard_tabs_config.json')
dashboard_tabs_example_config_path = os.path.join(path, 'data', 'visualizations', 'dashboard_tabs_config.example.json')

_mnid_full_data_cache: dict = {}
_dashboard_data_cache: dict = {}
_dashboard_filter_cache: dict = {}
DEFAULT_DASHBOARD_DAYS = 7
DEFAULT_RELATIVE_PERIOD = 'Today'
_LATEST_DATA_DATE_CACHE: dict[str, pd.Timestamp | None] = {}
_MNID_FULL_CACHE_MAX = 6
_DASHBOARD_DATA_CACHE_MAX = 4
_DASHBOARD_FILTER_CACHE_MAX = 6
_MNID_PREWARM_STARTED = False
_DASHBOARD_TAB_CONFIG_DEFAULTS = {
    "mode": "default",
    "visible_reports": [],
    "default_report": None,
    "hidden_mnid_tabs": [],
    "mnh_tabs": [],
}


def _dashboard_loading_placeholder():
    return html.Div(
        className="dashboard-loading-placeholder",
        children=[
            html.Div(className="dashboard-loading-hero"),
            html.Div(
                className="dashboard-loading-grid",
                children=[
                    html.Div(className="dashboard-loading-card"),
                    html.Div(className="dashboard-loading-card"),
                    html.Div(className="dashboard-loading-card"),
                ],
            ),
            html.Div(className="dashboard-loading-wide"),
        ],
    )


def _trim_cache(cache: dict, max_entries: int) -> None:
    while len(cache) > max_entries:
        try:
            cache.pop(next(iter(cache)))
        except Exception:
            break


def _start_mnid_prewarm(version: str | None = None):
    """Kick off MNID cache pre-warm in a daemon background thread at server startup."""
    import sys
    import threading
    import logging
    global _MNID_PREWARM_STARTED
    _log = logging.getLogger(__name__)

    if _MNID_PREWARM_STARTED:
        return

    # In Werkzeug debug mode the app is imported TWICE — once in the reloader
    # parent process and once in the serving child.  Skip the parent to avoid
    # duplicate heavy work.  Gunicorn workers don't set WERKZEUG_RUN_MAIN at
    # all, so we use the gunicorn module presence to tell them apart.
    is_gunicorn = 'gunicorn' in sys.modules
    werkzeug_run_main = os.environ.get('WERKZEUG_RUN_MAIN')
    if not is_gunicorn and werkzeug_run_main is None:
        # Werkzeug reloader parent — skip; the child process will pre-warm.
        return
    if werkzeug_run_main == 'false':
        return

    def _run(v):
        try:
            from mnid.app import prewarm_cache
            prewarm_cache(dataset_version=v)
        except Exception as exc:
            _log.warning('MNID startup pre-warm thread failed: %s', exc)
            return

        # After network_df is warm, pre-render the country profile using the
        # default date window so the first user request hits a warm view cache.
        try:
            from mnid.app import _prewarm_country_profile
            _prewarm_country_profile()
        except Exception as exc:
            _log.warning('MNID country-profile pre-warm failed: %s', exc)

        # Build the aggregate parquet if it doesn't exist yet.
        # The lock file in run_aggregation_job prevents duplicate runs across workers.
        try:
            from pathlib import Path
            agg_parquet = Path(os.getcwd()) / 'data' / 'mnid_aggregates' / 'indicator_aggregates.parquet'
            if not agg_parquet.exists():
                from mnid.aggregation.scheduler import run_aggregation_job
                _log.info('No aggregate parquet found — building now (first-time startup)')
                run_aggregation_job()
        except Exception as exc:
            _log.warning('MNID startup aggregation failed: %s', exc)

    t = threading.Thread(target=_run, args=(version,), daemon=True, name='mnid-prewarm')
    t.start()
    _MNID_PREWARM_STARTED = True
    _log.info('MNID pre-warm thread started')


def _latest_available_date(route: str = 'default') -> pd.Timestamp | None:
    route_data_path = f'data/{route}/parquet'
    cache_key = f'{route_data_path}:{_dataset_version_token(route)}'
    if cache_key in _LATEST_DATA_DATE_CACHE:
        return _LATEST_DATA_DATE_CACHE[cache_key]
    try:
        latest = DataStorage.query_duckdb(f"SELECT MAX(Date) AS max_date FROM '{route_data_path}'")
        max_date = pd.to_datetime(latest.loc[0, 'max_date'], errors='coerce') if len(latest) else pd.NaT
    except Exception:
        max_date = pd.NaT
    resolved = None if pd.isna(max_date) else max_date.normalize()
    _LATEST_DATA_DATE_CACHE.clear()
    _LATEST_DATA_DATE_CACHE[cache_key] = resolved
    return resolved


def _default_date_window(route: str = 'default'):
    latest = _latest_available_date(route)
    anchor = latest.date() if latest is not None else datetime.now().date()
    start = anchor - pd.Timedelta(days=29)
    return start, anchor


def _dataset_version_token(route: str = 'default') -> str:
    timestamp_path = os.path.join(path, f'data/{route}', 'TimeStamp.csv')
    data_path = os.path.join(path, f'data/{route}', 'parquet')
    parts = []
    try:
        parts.append(str(os.path.getmtime(data_path)))
    except Exception:
        parts.append('no-data-file')
    try:
        parts.append(str(os.path.getmtime(timestamp_path)))
    except Exception:
        parts.append('no-timestamp')
    return '|'.join(parts)


# _start_mnid_prewarm(_dataset_version_token())


def clear_dashboard_state_cache() -> None:
    _mnid_full_data_cache.clear()
    _dashboard_data_cache.clear()
    _dashboard_filter_cache.clear()


def _load_user_registry(route) -> pd.DataFrame:
    user_data_path = os.path.join(path, f'data/{route}','single_tables', 'users_data.csv')

    if os.path.exists(user_data_path):
        user_data = pd.read_csv(user_data_path)
    else:
        user_data = pd.DataFrame(columns=['user_id','uuid', 'role','user_level','district','facility_name','facility_code'])
    demo_row = {
        'user_id':1000000,
        'uuid': DEMO_UUID,
        'role': 'reports_admin',
        'user_level': 'national',
        'district': ["Salima"],
        'facility_name': None,
        'facility_code': DEMO_LOCATION,
        'assigned_facility':'Biwi Health Centre'
    }

    user_data = pd.concat([user_data, pd.DataFrame([demo_row])], ignore_index=True)
    for column in ['uuid', 'role', 'user_level', 'district', 'facility_code', 'facility_name']:
        if column not in user_data.columns:
            user_data[column] = pd.NA

    def parse_list(val):
        if pd.isna(val):
            return None
        if isinstance(val, str) and ',' in val:
            return [x.strip() for x in val.split(',')]
        return val

    user_data['district'] = user_data['district'].apply(parse_list)
    user_data['facility_name'] = user_data['facility_name'].apply(parse_list)

    return user_data


def _first_non_empty(row: pd.Series, candidates: list[str]) -> str | None:
    for name in candidates:
        if name in row.index:
            value = row.get(name)
            if pd.notna(value) and str(value).strip():
                return str(value).strip()
    return None


def _normalize_level(value: str | None) -> str:
    value = str(value or '').strip().lower()
    if value in {'national', 'district', 'facility'}:
        return value
    return 'facility'


def _title_level(value: str) -> str:
    return {'national': 'National', 'district': 'District', 'facility': 'Facility'}.get(value, 'Facility')


def _load_user_properties(route) -> list:
    props_path = os.path.join(os.getcwd(), f'data/{route}', 'dcc_dropdown_json', 'user_properties.json')
    try:
        with open(props_path) as f:
            return json.load(f).get('users', [])
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return []


def _resolve_user_scope(urlparams, user_data: pd.DataFrame):
    requested_uuid = urlparams.get('uuid', [None])[0] if urlparams else None
    data_route = urlparams.get('route', ["default"])[0] if urlparams else None

    # Check user_properties.json first (GUI-configured overrides)
    for entry in _load_user_properties(data_route):
        p = entry.get('properties', {})
        if p.get('uuid') == requested_uuid:
            level     = _normalize_level(p.get('user_level'))
            districts = p.get('district')
            if isinstance(districts, str):
                districts = [districts] if districts else []
            facilities = p.get('facility_name')
            if isinstance(facilities, str):
                facilities = [facilities] if facilities else []
            scope = {
                'level':      level,
                'districts':  districts  or [],
                'facilities': facilities or [],
            }
            # Still return a dataframe row so callers that use row.get(...) don't break
            user_info = user_data[user_data['uuid'] == requested_uuid]
            row = user_info.iloc[0] if not user_info.empty else None
            return row, scope

    # Fall back to users_data dataframe
    user_info = user_data[user_data['uuid'] == requested_uuid]
    if user_info.empty:
        return None, {}
    row   = user_info.iloc[0]
    level = _normalize_level(row.get('user_level'))
    scope = {
        'level':      level,
        'districts':  row.get('district'),
        'facilities': row.get('facility_name'),
    }
    return row, scope


def _apply_scope_to_data(data: pd.DataFrame, scope: dict, district_col='district', facility_col='facility_name'):
    if data is None or data.empty:
        return data
    level = scope.get('level')
    districts = scope.get('districts')
    facilities = scope.get('facilities')
    if level == 'national':
        return data
    if level == 'district':
        if districts:
            return data[data[district_col].isin(districts)]
        return data
    if level == 'facility':
        if facilities:
            return data[data[facility_col].isin(facilities)]
        return data
    return data

def load_dashboard_menu():
    try:
        with open(json_path, 'r') as f:
            return json.load(f)
    except Exception:
        return []


def load_dashboard_tab_config():
    raw_config = {}
    config_path = json_path
    # config_path = dashboard_tabs_config_path if os.path.exists(dashboard_tabs_config_path) else dashboard_tabs_example_config_path
    try:
        with open(config_path, 'r') as f:
            raw_config = json.load(f) or {}
    except Exception:
        raw_config = {}

    config = dict(_DASHBOARD_TAB_CONFIG_DEFAULTS)
    if isinstance(raw_config, dict):
        config.update(raw_config)

    mode = str(config.get("mode") or "default").strip().lower()
    config["mode"] = mode if mode in {"default", "mnh_only"} else "default"

    visible_reports = config.get("visible_reports")
    if not isinstance(visible_reports, list):
        visible_reports = []
    config["visible_reports"] = [str(item).strip() for item in visible_reports if str(item).strip()]

    default_report = config.get("default_report")
    config["default_report"] = str(default_report).strip() if str(default_report or "").strip() else None

    hidden_mnid_tabs = config.get("hidden_mnid_tabs")
    if not isinstance(hidden_mnid_tabs, list):
        hidden_mnid_tabs = []
    config["hidden_mnid_tabs"] = [str(item).strip() for item in hidden_mnid_tabs if str(item).strip()]

    mnh_tabs = config.get("mnh_tabs")
    if not isinstance(mnh_tabs, list):
        mnh_tabs = []
    normalized_mnh_tabs = []
    for item in mnh_tabs:
        if not isinstance(item, dict):
            continue
        tab_id = str(item.get("id") or "").strip()
        label = str(item.get("label") or tab_id).strip()
        if not tab_id or not label:
            continue
        normalized_mnh_tabs.append({
            "id": tab_id,
            "label": label,
            "module": str(item.get("module") or "").strip() or None,
            "placeholder": bool(item.get("placeholder")),
        })
    config["mnh_tabs"] = normalized_mnh_tabs
    return config


def get_enabled_dashboard_menu():
    menu_json = load_dashboard_menu()
    config = load_dashboard_tab_config()

    if config["mode"] == "mnh_only":
        allowed_reports = {"Maternal Health"}
    elif config["visible_reports"]:
        allowed_reports = set(config["visible_reports"])
    else:
        allowed_reports = None

    if allowed_reports is None:
        filtered_menu = menu_json
    else:
        filtered_menu = [item for item in menu_json if item.get("report_name") in allowed_reports]

    return filtered_menu, config

def get_dashboard_names():
    menu_items = [d.get("report_name") for d in load_dashboard_menu() 
                  if d.get("report_name")]
    return menu_items

def normalize_report_name(name, menu_json):
    if not name:
        return name
    if name == "Newborn":
        if any(d.get("report_name") == "Maternal Health" for d in menu_json):
            return "Maternal Health"
    if name == "Maternal and Child Health":
        if any(d.get("report_name") == "Maternal Health" for d in menu_json):
            return "Maternal Health"
    return name


def display_report_name(name):
    if name == "Maternal Health":
        return "MNH Program"
    return name

# Load data once to get date range
min_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
max_date = datetime.now().replace(hour=23, minute=59, second=59, microsecond=0)

path = os.getcwd()

# BUILD CHARTS
PREMIUM_DASHBOARD_REPORTS = {"Maternal and Child Health"}

def _scope_where_parts(effective_level, location, districts, user_districts, facilities, age, is_network=False):
    """Return SQL WHERE clause parts for the given scope and level.

    is_network=True omits the per-facility filter so the network query covers
    the full district/national context for trend comparison.
    """
    parts = []
    if effective_level == 'facility':
        if not is_network and location:
            parts.append(f"{FACILITY_CODE_} = '{location}'")
    elif effective_level == 'district':
        active_dists = districts or user_districts
        if active_dists:
            quoted_dists = ", ".join([f"'{d}'" for d in active_dists])
            parts.append(f"{DISTRICT_} IN ({quoted_dists})")
        if not is_network and facilities:
            quoted_facilities = ", ".join([f"'{f}'" for f in facilities])
            parts.append(f"{FACILITY_} IN ({quoted_facilities})")
    elif effective_level == 'national':
        if districts:
            quoted_dists = ", ".join([f"'{d}'" for d in districts])
            parts.append(f"{DISTRICT_} IN ({quoted_dists})")
        if not is_network and facilities:
            quoted_facilities = ", ".join([f"'{f}'" for f in facilities])
            parts.append(f"{FACILITY_} IN ({quoted_facilities})")
    if age:
        parts.append(f"{AGE_GROUP_} = '{age}'")
    return parts


def build_charts_from_json(filtered_query, filtered_with_range_query, delta_days, dashboards_json, filter_summary=None,
                          start_date=None, end_date=None, data_path=DATA_PATH_, facility_code=None, scope_meta=None, url_object=None, initial_tab=None):
    
    config = dashboards_json
    count_items_per_row = config.get("count_items_per_row") or 5

    # Route MNID dashboard configs to the dedicated MNID renderer.
    if config.get('dashboard_type') == 'mnid':
        return render_mnid_dashboard(
            filtered=filtered_query,
            data_opd=filtered_with_range_query,
            data_path=data_path,
            config=config,
            facility_code=facility_code or 'Unknown',
            start_date=str(start_date)[:10] if start_date else '',
            end_date=str(end_date)[:10] if end_date else '',
            scope_meta=scope_meta,
            initial_tab=initial_tab,
        )
    if config.get("report_name") in PREMIUM_DASHBOARD_REPORTS:
        return build_premium_dashboard(filtered_query, filtered_with_range_query, delta_days, config, filter_summary=filter_summary)

    # Build metrics from counts section
    metrics = build_metrics_section(filtered_query,filtered_with_range_query, delta_days, data_path, config["visualization_types"]["counts"], url_object)
    charts = build_charts_section(filtered_query, filtered_with_range_query, delta_days, data_path, config["visualization_types"]["charts"]["sections"])

    return html.Div([
        html.Div(style={"display": "grid","gridTemplateColumns": f"repeat({count_items_per_row}, 1fr)",
                        "gap": "15px", "marginBottom": "30px","overflowX": "auto"}, children=metrics),
        charts
    ])


def _error_dashboard_content(message: str, detail: str | None = None):
    children = [
        html.P(message, style={"color": "#475569", "fontWeight": "600"}),
    ]
    if detail:
        children.append(html.P(detail, style={"color": "#94A3B8", "fontSize": "12px"}))
    return html.Div(children)


def _load_scoped_dashboard_data(
    dataset_version: str,
    user_level: str,
    effective_level: str,
    location: str | None,
    scope: dict,
    districts: list[str],
    facilities: list[str],
    end_dt: pd.Timestamp,
    default_start_date: pd.Timestamp,
    mnid_only_request: bool,
    route: str = 'default',
):
    data = None
    mnid_full_scope_data = None
    route_data_path = f'data/{route}/parquet'

    if mnid_only_request:
        district_col_for_scope = "District"
        mnid_scope_key = (
            dataset_version,
            effective_level,
            tuple(sorted(districts or [])),
            tuple(sorted(facilities or [])),
        )
        if mnid_scope_key in _mnid_full_data_cache:
            data = _mnid_full_data_cache[mnid_scope_key].copy()
        else:
            mnid_cols = ', '.join([
                'person_id', 'encounter_id', 'Date', 'Program', 'Reporting_Program',
                'Service_Area', 'Facility', 'Facility_CODE', 'District', 'Encounter',
                'obs_value_coded', 'concept_name', 'Value', 'ValueN', 'new_revisit',
                'Home_district', 'TA', 'Village', 'Age', 'Age_Group', 'Gender',
                'Source_Program',
            ])
            sql_full = f"SELECT {mnid_cols} FROM '{route_data_path}'"
            full = DataStorage.query_duckdb(sql_full)
            full[DATE_] = pd.to_datetime(full[DATE_], errors='coerce')
            full = _apply_scope_to_data(full, scope, district_col_for_scope)
            if district_col_for_scope in full.columns and districts:
                full = full[full[district_col_for_scope].isin(districts)]
            if facilities:
                full = full[full[FACILITY_].isin(facilities)]
            _mnid_full_data_cache[mnid_scope_key] = full.copy()
            _trim_cache(_mnid_full_data_cache, _MNID_FULL_CACHE_MAX)
            data = full
        mnid_full_scope_data = data

    if data is None:
        sql_comment = f"-- version:{dataset_version} scope:{user_level} level:{effective_level}"
        if user_level == 'facility':
            sql = f"{sql_comment}\nSELECT * FROM '{route_data_path}' WHERE {FACILITY_CODE_} = '{location}'"
        else:
            sql = f"{sql_comment}\nSELECT * FROM '{route_data_path}'"
        data_cache_key = (dataset_version, user_level, effective_level, location)
        if data_cache_key in _dashboard_data_cache:
            data_full = _dashboard_data_cache[data_cache_key]
        else:
            data_full = DataStorage.query_duckdb(sql)
            data_full[DATE_] = pd.to_datetime(data_full[DATE_], format='mixed').dt.normalize()
            data_full[GENDER_] = data_full[GENDER_].replace(CUSTOM_GENDER_MAP)
            _dashboard_data_cache[data_cache_key] = data_full
            _trim_cache(_dashboard_data_cache, _DASHBOARD_DATA_CACHE_MAX)
        data = data_full[
            (data_full[DATE_] >= default_start_date) &
            (data_full[DATE_] <= end_dt)
        ].copy()

    return data, mnid_full_scope_data


def _load_filter_source_data(
    dataset_version: str,
    user_level: str,
    effective_level: str,
    location: str | None,
    scope: dict,
    end_dt: pd.Timestamp,
    default_start_date: pd.Timestamp,
    route: str = 'default',
):
    filter_cols = []
    for col in [DATE_, FACILITY_, FACILITY_CODE_, AGE_GROUP_, ENCOUNTER_, HOME_DISTRICT_, 'District']:
        if col and col not in filter_cols:
            filter_cols.append(col)

    route_data_path = f'data/{route}/parquet'
    sql_comment = f"-- version:{dataset_version} scope:{user_level} level:{effective_level} filters"
    if user_level == 'facility':
        sql = f"{sql_comment}\nSELECT {', '.join(filter_cols)} FROM '{route_data_path}' WHERE {FACILITY_CODE_} = '{location}'"
    else:
        sql = f"{sql_comment}\nSELECT {', '.join(filter_cols)} FROM '{route_data_path}'"

    cache_key = (dataset_version, user_level, effective_level, location, 'filters')
    if cache_key in _dashboard_filter_cache:
        data_full = _dashboard_filter_cache[cache_key]
    else:
        data_full = DataStorage.query_duckdb(sql)
        data_full[DATE_] = pd.to_datetime(data_full[DATE_], format='mixed').dt.normalize()
        _dashboard_filter_cache[cache_key] = data_full
        _trim_cache(_dashboard_filter_cache, _DASHBOARD_FILTER_CACHE_MAX)

    data = data_full[
        (data_full[DATE_] >= default_start_date) &
        (data_full[DATE_] <= end_dt)
    ].copy()

    district_col = "District" if "District" in data.columns else (HOME_DISTRICT_ if HOME_DISTRICT_ in data.columns else None)
    return _apply_scope_to_data(data, scope, district_col)



layout = html.Div(
    className="dashboard-layout-modern",
    children=[
        dcc.Location(id='url', refresh=False),
        dcc.Store(id='active-button-store', data='General Summary'),
        dcc.Store(id='filter-drawer-open', data=False),
        dcc.Store(id='scroll-watcher', data=0),
        dcc.Store(id='kpi-modal-page', data=1),
        dcc.Store(id='kpi-modal-data', data=None),

        #Floating filter button (appears on scroll-up)
        dcc.Store(id='mnid-active-tab-store', data='country-profile', storage_type='session'),
        dcc.Store(id='dashboard-render-state'),
        
        # Left Sidebar
        html.Div(
            id="filter-float-btn-wrapper",
            style={
                "position":   "fixed",
                "top":        "56px",
                "left":       "12px",
                "zIndex":     "900",
                "opacity":    "0",
                "transform":  "translateY(-8px)",
                "transition": "opacity 0.22s ease, transform 0.22s ease",
                "pointerEvents": "none",
            },
            children=[
                html.Button(
                    "⊞",
                    id="filter-float-btn",
                    n_clicks=0,
                    title="Open filters",
                    style={
                        "background":    "#9ca3af",
                        "color":         "#ffffff",
                        "border":        "none",
                        "borderRadius":  "50%",
                        "width":         "38px",
                        "height":        "38px",
                        "fontSize":      "17px",
                        "cursor":        "pointer",
                        "boxShadow":     "0 2px 8px rgba(0,0,0,0.22)",
                        "lineHeight":    "1",
                    },
                ),
            ],
        ),

        #Backdrop (closes drawer on click)
        html.Div(
            id="filter-drawer-backdrop",
            n_clicks=0,
            style={
                "display":    "none",
                "position":   "fixed",
                "inset":      "0",
                "background": "rgba(0,0,0,0.35)",
                "zIndex":     "1100",
            },
        ),
        html.Div(
            id="filter-drawer",
            style={
                "position":        "fixed",
                "top":             "0",
                "left":            "0",
                "bottom":          "0",
                "width":           "280px",
                "background":      "#ffffff",
                "boxShadow":       "4px 0 16px rgba(0,0,0,0.15)",
                "zIndex":          "1200",
                "overflowY":       "auto",
                "transform":       "translateX(-100%)",
                "transition":      "transform 0.25s ease",
                "display":         "flex",
                "flexDirection":   "column",
            },
            children=[
                # Drawer header
                html.Div(
                    style={
                        "display":       "flex", "alignItems": "center",
                        "justifyContent": "space-between",
                        "padding":       "14px 16px 10px",
                        "borderBottom":  "1px solid #e5e7eb",
                        "background":    "#f9fafb",
                        "flexShrink":    "0",
                    },
                    children=[
                        html.Span("Filters", style={"fontWeight": "700", "fontSize": "15px",
                                                     "color": "#111827"}),
                        html.Button(
                            "✕",
                            id="filter-drawer-close-btn",
                            n_clicks=0,
                            style={
                                "background": "none", "border": "none",
                                "fontSize": "16px", "cursor": "pointer",
                                "color": "#6b7280", "lineHeight": "1",
                                "padding": "2px 6px",
                            },
                        ),
                    ],
                ),

                # Filters body
                html.Div(
                    style={"padding": "12px 14px", "flex": "1", "overflowY": "auto"},
                    children=[
                        # Level Filter
                        html.Div(className="filter-group", children=[
                            html.Label("Level", className="filter-label"),
                            dcc.Dropdown(
                                id='dashboard-level-filter',
                                options=[
                                    {'label': 'National', 'value': 'National'},
                                    {'label': 'District',  'value': 'District'},
                                    {'label': 'Facility',  'value': 'Facility'},
                                ],
                                value=None, clearable=True,
                                className="modern-dropdown", placeholder="Select level",
                            ),
                        ]),
                        # District Filter
                        html.Div(id="dashboard-district-filter-group", className="filter-group", children=[
                            html.Label("District", className="filter-label"),
                            dcc.Dropdown(
                                id='dashboard-district-filter',
                                options=[], value=[], multi=True, clearable=True,
                                className="modern-dropdown", placeholder="Select district(s)",
                            ),
                            html.Div(id="dashboard-district-note", className="filter-note",
                                     style={"fontSize": "12px", "color": "#64748b", "marginTop": "6px"}),
                        ]),
                        # Facility Filter
                        html.Div(className="filter-group", children=[
                            html.Label("Health Facility", className="filter-label"),
                            dcc.Dropdown(
                                id='dashboard-facility-filter',
                                options=[], value=[], multi=True, clearable=True,
                                className="modern-dropdown", placeholder="Select facility(ies)",
                            ),
                        ]),
                        # Relative Period Filter
                        html.Div(className="filter-group", children=[
                            html.Label("Relative Period", className="filter-label"),
                            dcc.Dropdown(
                                id='dashboard-period-type-filter',
                                options=[{'label': item, 'value': item} for item in RELATIVE_PERIOD_LIST],
                                value=DEFAULT_RELATIVE_PERIOD, clearable=True,
                                className="modern-dropdown",
                            ),
                        ]),
                        # Custom Date Range
                        html.Div(className="filter-group", children=[
                            html.Label("Custom Date Range", className="filter-label"),
                            dcc.DatePickerRange(
                                id='dashboard-date-range-picker',
                                min_date_allowed="2023-01-01",
                                max_date_allowed="2050-01-01",
                                initial_visible_month=datetime.now(),
                                start_date=_default_date_window()[0],
                                end_date=_default_date_window()[1],
                                display_format='YYYY-MM-DD',
                                className="modern-datepicker",
                            ),
                        ]),
                        # Hidden overview filter (kept for callbacks)
                        html.Div(style={"display": "none"}, children=[
                            dcc.Dropdown(
                                id='dashboard-overview-filter',
                                options=[{"label": name, "value": name}
                                         for name in get_dashboard_names()],
                                value=[], multi=True, clearable=True,
                                className="modern-dropdown",
                            ),
                        ]),
                        # Program Category Filter
                        html.Div(id="dashboard-category-filter-group", className="filter-group", children=[
                            html.Label("Program Category", className="filter-label"),
                            dcc.Dropdown(
                                id='dashboard-category-filter',
                                options=[
                                    {"label": "All",               "value": "All"},
                                    {"label": "ANC",               "value": "ANC"},
                                    {"label": "Labour & Delivery", "value": "Labour"},
                                    {"label": "PNC",               "value": "PNC"},
                                ],
                                value="All", clearable=False, className="modern-dropdown",
                            ),
                        ]),
                        # Age Group Filter
                        html.Div(id="dashboard-age-filter-group", className="filter-group", children=[
                            html.Label("Age Group", className="filter-label"),
                            dcc.Dropdown(
                                id='dashboard-age-filter',
                                options=[{'label': age, 'value': age} for age in ['Over 5', 'Under 5']],
                                value=None, clearable=True, className="modern-dropdown",
                            ),
                        ]),
                        # Facility Level Filter (MOH only)
                        html.Div(
                            id="dashboard-moh-level-filter-group",
                            className="filter-group",
                            style={'display': 'none'},
                            children=[
                                html.Label("Facility Level", className="filter-label"),
                                dcc.Dropdown(
                                id='dashboard-moh-level-filter',
                                options=[
                                    {'label': 'All', 'value': 'All'},
                                    {'label': 'Primary', 'value': 'Primary'},
                                    {'label': 'Secondary', 'value': 'Secondary'},
                                    {'label': 'Tertiary', 'value': 'Tertiary'},
                                ],
                                value='All',
                                clearable=False,
                                className="modern-dropdown"
                            )]),
                    ],
                ),

                # Action buttons pinned to bottom of drawer
                html.Div(
                    className="filter-actions",
                    style={
                        "padding":    "10px 14px",
                        "borderTop":  "1px solid #e5e7eb",
                        "background": "#f9fafb",
                        "flexShrink": "0",
                        "display":    "flex",
                        "gap":        "8px",
                    },
                    children=[
                        html.Button("Apply Filters", id="dashboard-btn-generate", n_clicks=0,
                                    className="btn-apply-modern", style={"flex": "1"}),
                        html.Button("Reset Filters", id="dashboard-btn-reset", n_clicks=0,
                                    className="btn-reset-modern", style={"flex": "1"}),
                    ],
                ),
            ],
        ),

        # Main Content (full width)
        html.Div(
            className="dashboard-main",
            style={"width": "100%"},
            children=[
                # Filter toggle button
                html.Div(
                    style={
                        "padding":       "6px 10px",
                        "borderBottom":  "1px solid #e5e7eb",
                        "background":    "#f9fafb",
                        "display":       "flex",
                        "alignItems":    "center",
                        "gap":           "8px",
                    },
                    children=[
                        html.Button(
                            [nav_icon("lucide:filter"), " Filter"],
                            id="filter-drawer-toggle-btn",
                            n_clicks=0,
                            style={
                                "display":       "flex",
                                "alignItems":    "center",
                                "gap":           "5px",
                                "padding":       "5px 12px",
                                "fontSize":      "12px",
                                "fontWeight":    "600",
                                "border":        "1px solid #d1d5db",
                                "borderRadius":  "4px",
                                "background":    "#ffffff",
                                "color":         "#374151",
                                "cursor":        "pointer",
                            },
                        ),
                        html.Div(
                            id="filter-period-text",
                            style={"fontWeight":"400",
                                   "color":"grey",
                                   "fontSize":"12px"}
                            )
                    ],
                ),
                # Menu Section
                html.Div(
                    id="dashboard-menu-section",
                    className="sidebar-menu-section",
                    children=[
                        html.Div(
                            className="menu-scroll-container",
                            children=[
                                html.Div(
                                    className="menu-buttons-wrapper",
                                    id="scrolling-menu",
                                    children=[
                                        html.Button(item, className="menu-btn-modern")
                                        for item in []
                                    ]
                                )
                            ]
                        )
                    ]
                ),
                # Dashboard Content
                dcc.Loading(
                    id="dashboard-loading",
                    parent_style={
                        "position": "relative",
                        "minHeight": "220px",
                    },
                    style={
                        "position": "absolute",
                        "inset": 0,
                        "display": "flex",
                        "alignItems": "center",
                        "justifyContent": "center",
                    },
                    custom_spinner=html.Div(
                        className="home-loading-shell",
                        role="status",
                        children=[
                            html.Div(className="home-loading-spinner"),
                            html.Div(
                                className="home-loading-copy",
                                children=[
                                    html.Div("Please wait", className="home-loading-title"),
                                    html.Div("Applying the current filters and charts.", className="home-loading-subtitle"),
                                ],
                            ),
                            html.Span(
                                "Loading...",
                                className="home-visually-hidden",
                            ),
                        ],
                    ),
                    overlay_style={
                        "visibility": "visible",
                        "opacity": 1,
                        "position": "fixed",
                        "inset": 0,
                        "backgroundColor": "transparent",
                        "borderRadius": "0",
                        "zIndex": 1200,
                    },
                    delay_show=150,
                    children=html.Div(
                        id='dashboard-container',
                        className="dashboard-content-modern",
                        children=_dashboard_loading_placeholder(),
                    )
                ),
            ]
        ),
        
        # Auto-refresh Interval
        dcc.Interval(
            id='dashboard-interval-update-today',
            interval=10*60*1000,  # 10 minutes
            n_intervals=0
        ),

        #Patient ID modal
        html.Div(
            id="kpi-patient-modal",
            style={"display": "none"},
            children=[
                # Backdrop
                html.Div(
                    id="kpi-patient-modal-backdrop",
                    n_clicks=0,
                    style={
                        "position": "fixed", "inset": "0",
                        "background": "rgba(0,0,0,0.45)", "zIndex": "2000",
                    },
                ),
                # Dialog
                html.Div(
                    style={
                        "position":      "fixed",
                        "top":           "50%",
                        "left":          "50%",
                        "transform":     "translate(-50%, -50%)",
                        "zIndex":        "2100",
                        "background":    "#ffffff",
                        "borderRadius":  "8px",
                        "boxShadow":     "0 8px 32px rgba(0,0,0,0.22)",
                        "width":         "1200px",
                        "maxWidth":      "92vw",
                        "maxHeight":     "80vh",
                        "display":       "flex",
                        "flexDirection": "column",
                    },
                    children=[
                        # Header
                        html.Div(
                            style={
                                "display":       "flex",
                                "alignItems":    "center",
                                "justifyContent": "space-between",
                                "padding":       "12px 16px",
                                "borderBottom":  "1px solid #e5e7eb",
                                "flexShrink":    "0",
                            },
                            children=[
                                html.Span(id="kpi-patient-modal-title",
                                          style={"fontWeight": "700", "fontSize": "14px",
                                                 "color": "#111827"}),
                                html.Button(
                                    "✕",
                                    id="kpi-patient-modal-close",
                                    n_clicks=0,
                                    style={
                                        "background":   "#dc2626",
                                        "color":        "#ffffff",
                                        "border":       "none",
                                        "borderRadius": "50%",
                                        "width":        "26px",
                                        "height":       "26px",
                                        "fontSize":     "13px",
                                        "fontWeight":   "700",
                                        "cursor":       "pointer",
                                        "lineHeight":   "1",
                                        "flexShrink":   "0",
                                    },
                                ),
                            ],
                        ),
                        # Table body (scrollable)
                        html.Div(
                            id="kpi-patient-modal-body",
                            style={
                                "overflowY": "auto",
                                "flex":      "1",
                                "padding":   "12px 16px",
                            },
                        ),
                        # Pagination footer
                        html.Div(
                            style={
                                "display":         "flex",
                                "alignItems":      "center",
                                "justifyContent":  "space-between",
                                "padding":         "8px 16px",
                                "borderTop":       "1px solid #e5e7eb",
                                "flexShrink":      "0",
                                "background":      "#f9fafb",
                                "borderRadius":    "0 0 8px 8px",
                            },
                            children=[
                                html.Button(
                                    "← Prev",
                                    id="kpi-modal-prev-btn",
                                    n_clicks=0,
                                    style={
                                        "background": "#525E52", "color": "#ffffff",
                                        "border": "none", "borderRadius": "4px",
                                        "padding": "4px 14px", "fontSize": "12px",
                                        "cursor": "pointer",
                                    },
                                ),
                                html.Span(
                                    id="kpi-modal-page-info",
                                    style={"fontSize": "12px", "color": "#6b7280"},
                                ),
                                html.Button(
                                    "Next →",
                                    id="kpi-modal-next-btn",
                                    n_clicks=0,
                                    style={
                                        "background": "#525E52", "color": "#ffffff",
                                        "border": "none", "borderRadius": "4px",
                                        "padding": "4px 14px", "fontSize": "12px",
                                        "cursor": "pointer",
                                    },
                                ),
                            ],
                        ),
                    ],
                ),
            ],
        ),
    ]
)

@callback(
    Output("filter-drawer", "style"),
    Output("filter-drawer-backdrop", "style"),
    Input("filter-drawer-toggle-btn", "n_clicks"),
    Input("filter-drawer-close-btn",  "n_clicks"),
    Input("filter-drawer-backdrop",   "n_clicks"),
    Input("filter-float-btn",         "n_clicks"),
    State("filter-drawer-open", "data"),
    prevent_initial_call=True,
)
def _toggle_filter_drawer(n_toggle, n_close, n_backdrop, _n_float, is_open):
    new_open = not is_open
    drawer_style = {
        "position": "fixed", "top": "0", "left": "0", "bottom": "0",
        "width": "280px", "background": "#ffffff",
        "boxShadow": "4px 0 16px rgba(0,0,0,0.15)", "zIndex": "1200",
        "overflowY": "auto", "display": "flex", "flexDirection": "column",
        "transform": "translateX(0)" if new_open else "translateX(-100%)",
        "transition": "transform 0.25s ease",
    }
    backdrop_style = {
        "display": "block" if new_open else "none",
        "position": "fixed", "inset": "0",
        "background": "rgba(0,0,0,0.35)", "zIndex": "1100",
    }
    return drawer_style, backdrop_style


@callback(
    Output("filter-drawer-open", "data"),
    Input("filter-drawer-toggle-btn", "n_clicks"),
    Input("filter-drawer-close-btn",  "n_clicks"),
    Input("filter-drawer-backdrop",   "n_clicks"),
    Input("filter-float-btn",         "n_clicks"),
    State("filter-drawer-open", "data"),
    prevent_initial_call=True,
)
def _sync_drawer_state(n_toggle, n_close, n_backdrop, _n_float, is_open):
    del n_toggle, n_close, n_backdrop, _n_float  # inputs drive trigger; only state matters
    return not is_open


_KPI_PAGE_SIZE = 15


# KPI modal — open/close + data fetch
@callback(
    Output("kpi-patient-modal",  "style"),
    Output("kpi-patient-modal-title", "children"),
    Output("kpi-modal-data",     "data"),
    Output("kpi-modal-page",     "data"),
    Input({"type": "kpi-val-click",     "index": ALL}, "n_clicks"),
    Input("kpi-patient-modal-close",   "n_clicks"),
    Input("kpi-patient-modal-backdrop","n_clicks"),
    State({"type": "kpi-patient-ids",  "index": ALL}, "data"),
    State({"type": "kpi-val-click",    "index": ALL}, "id"),
    State({"type": "kpi-name",  "index": ALL}, "data"),
    State("url-params-store", "data"),
    prevent_initial_call=True,
)
def _kpi_patient_modal(n_clicks_list, n_close, n_backdrop, ids_list, id_list,kpi_name, urlparams):
    triggered = ctx.triggered_id

    if triggered in ("kpi-patient-modal-close", "kpi-patient-modal-backdrop"):
        return {"display": "none"}, dash.no_update, dash.no_update, dash.no_update

    if not isinstance(triggered, dict) or triggered.get("type") != "kpi-val-click":
        raise PreventUpdate
    if not any(n for n in (n_clicks_list or []) if n):
        raise PreventUpdate

    clicked_index = triggered["index"]
    kpi_title = next((item[0] for item in kpi_name if item[1] == clicked_index), None)

    store_payload = {}
    for id_obj, payload in zip(id_list, ids_list):
        if id_obj.get("index") == clicked_index:
            store_payload = payload or {}
            break
    patient_ids = store_payload.get("ids", [])
    unique_col  = store_payload.get("unique_col", "") or PERSON_ID_
    if not patient_ids:
        raise PreventUpdate

    data_route = (urlparams or {}).get("route", ["default"])[0]
    data_path  = f"data/{data_route}/parquet"

    df = create_line_list_basic_modal(unique_col, data_path, patient_ids)
    title = f"Patient List — {kpi_title} - ({len(patient_ids):,} Total Records)"

    modal_data = {
        "rows":  df.to_dict("records"),
        "cols":  list(df.columns),
        "total": len(df),
    }
    return {"display": "block"}, title, modal_data, 1


# KPI modal — render current page
@callback(
    Output("kpi-patient-modal-body", "children"),
    Output("kpi-modal-page-info",    "children"),
    Input("kpi-modal-page", "data"),
    Input("kpi-modal-data", "data"),
    prevent_initial_call=True,
)
def _kpi_render_page(page, modal_data):
    if not modal_data:
        raise PreventUpdate

    rows_all = modal_data.get("rows", [])
    cols     = modal_data.get("cols", [])
    total    = modal_data.get("total", 0)

    if not rows_all:
        body = html.Div("No records found.", style={"fontSize": "13px", "color": "#6b7280"})
        return body, ""

    page = max(1, page or 1)
    total_pages = max(1, -(-total // _KPI_PAGE_SIZE))  # ceiling division
    page = min(page, total_pages)

    start = (page - 1) * _KPI_PAGE_SIZE
    end   = start + _KPI_PAGE_SIZE
    page_rows = rows_all[start:end]

    th_style  = {"padding": "6px 10px", "background": "#f3f4f6", "fontWeight": "600",
                 "fontSize": "12px", "border": "1px solid #e5e7eb", "whiteSpace": "nowrap"}
    td_style  = {"padding": "5px 10px", "fontSize": "12px", "border": "1px solid #e5e7eb"}
    num_style = {**td_style, "color": "#9ca3af", "textAlign": "center", "width": "40px"}

    header = html.Thead(html.Tr(
        [html.Th("#", style={**th_style, "width": "40px"})] +
        [html.Th(col, style=th_style) for col in cols]
    ))
    rows = [
        html.Tr(
            [html.Td(start + i + 1, style=num_style)] +
            [html.Td(str(r.get(col, "")) if r.get(col) is not None else "", style=td_style)
             for col in cols],
            style={"background": "#ffffff" if i % 2 == 0 else "#f9fafb"},
        )
        for i, r in enumerate(page_rows)
    ]
    table = html.Table(
        [header, html.Tbody(rows)],
        style={"width": "100%", "borderCollapse": "collapse",
               "fontSize": "12px", "tableLayout": "auto"},
    )
    page_info = f"Page {page} of {total_pages}  ({total:,} records)"
    return table, page_info


# KPI modal — page navigation
@callback(
    Output("kpi-modal-page", "data", allow_duplicate=True),
    Input("kpi-modal-prev-btn", "n_clicks"),
    Input("kpi-modal-next-btn", "n_clicks"),
    State("kpi-modal-page",    "data"),
    State("kpi-modal-data",    "data"),
    prevent_initial_call=True,
)
def _kpi_modal_nav(n_prev, n_next, page, modal_data):
    if not modal_data:
        raise PreventUpdate
    total       = modal_data.get("total", 0)
    total_pages = max(1, -(-total // _KPI_PAGE_SIZE))
    page        = max(1, page or 1)
    if ctx.triggered_id == "kpi-modal-prev-btn":
        page = max(1, page - 1)
    else:
        page = min(total_pages, page + 1)
    return page


# Bind scroll listener once on page load; manipulate float-btn wrapper directly via DOM
dash.clientside_callback(
    """
    function(_) {
        var lastY = 0;
        var bound = false;
        function bindScroll() {
            var wrapper = document.getElementById('filter-float-btn-wrapper');
            if (!wrapper) { setTimeout(bindScroll, 300); return; }
            window.addEventListener('scroll', function() {
                var currentY = window.scrollY || document.documentElement.scrollTop;
                if (currentY < lastY && currentY > 60) {
                    wrapper.style.opacity = '1';
                    wrapper.style.transform = 'translateY(0)';
                    wrapper.style.pointerEvents = 'auto';
                } else {
                    wrapper.style.opacity = '0';
                    wrapper.style.transform = 'translateY(-8px)';
                    wrapper.style.pointerEvents = 'none';
                }
                lastY = currentY;
            }, { passive: true });
        }
        bindScroll();
        return window.dash_clientside.no_update;
    }
    """,
    Output("scroll-watcher", "data"),
    Input("scroll-watcher", "data"),
    prevent_initial_call=False,
)


@callback(
        Output('scrolling-menu', 'children'),
        [Input('dashboard-interval-update-today', 'n_intervals'),
        Input('active-button-store', 'data'),
        Input('url-params-store', 'data')])

def update_menu(interval, color, urlparams):
    try:
        urlparams = urlparams or {}
        data_route = urlparams.get('route', ["default"])[0]
        user_data = _load_user_registry(data_route)
        user_row, scope = _resolve_user_scope(urlparams, user_data)
        if user_row is None:
            return []

        user_id = int(user_row.get('user_id', '0')) 
        user_uuid = user_row.get('uuid')
        user_programs_path = os.path.join(os.getcwd(), f"data/{data_route}/single_tables/user_programs.csv")
        dashboard_path = os.path.join(os.getcwd(), f"data/visualizations/validated_dashboard.json")
        if user_uuid == DEMO_UUID or not os.path.exists(user_programs_path):
            user_programs = []
        else:
            user_programs = duckdb.sql(
                                        f"SELECT name FROM '{user_programs_path}' WHERE user_id = {user_id}"
                                    ).df()['name'].to_list()
        
        user_props = next((user['properties'] for user in  _load_user_properties(data_route) if user.get('properties').get('uuid') == user_uuid), None)
        limited_dashboards = user_props.get('limited_dashboards', []) if user_props else []

        with open(json_path, 'r') as f:
            menu_json = json.load(f)

        general_summary_button = [
                                html.Button(
                                    "General Summary",
                                    className="menu-btn active" if color == "General Summary" else "menu-btn",
                                    id={"type": "menu-button", "name": "General Summary"}
                                )
                            ]
        
        filtered_buttons = [
                            html.Button(
                                display_report_name(d["report_name"]),
                                className="menu-btn active" if color == d["report_name"] else "menu-btn",
                                id={"type": "menu-button", "name": d["report_name"]}
                            )
                            for d in menu_json
                            if d.get("report_name") != "Newborn" and d.get('access', 'global') =='global'
                            and any(program in user_programs for program in d.get("associated_programs", []))
                        ]
        filtered_buttons_limited = [
                            html.Button(
                                display_report_name(d["report_name"]),
                                className="menu-btn-alt active" if color == d["report_name"] else "menu-btn-alt",
                                id={"type": "menu-button", "name": d["report_name"]}
                            )
                            for d in menu_json
                            if (
                                d.get("report_name") != "Newborn" 
                                and d.get('access', 'global') == 'limited'
                                and any(program in user_programs for program in d.get("associated_programs", []))
                                and any(item in display_report_name(d["report_name"]) for item in limited_dashboards)
                            )
                        ]
        all_buttons = [
                            html.Button(
                                display_report_name(d["report_name"]),
                                className="menu-btn active" if color == d["report_name"] else "menu-btn",
                                id={"type": "menu-button", "name": d["report_name"]}
                            )
                            for d in menu_json
                            if d.get("report_name") != "Newborn"
                        ]
        
        if user_uuid == DEMO_UUID:
            return all_buttons
        else:
            return general_summary_button + filtered_buttons + filtered_buttons_limited
    except Exception as e:
        import traceback
        traceback.print_exc()
        return []


@callback(
    Output('mnid-active-tab-store', 'data'),
    Input('mnid-mnh-view-tabs', 'value'),
    prevent_initial_call=True,
)
def _save_mnh_active_tab(mnh_tab_value):
    return mnh_tab_value or 'mnh-beginnings'


@callback(
    Output('mnid-active-tab-store', 'data', allow_duplicate=True),
    Input('mnid-executive-tabs', 'value'),
    prevent_initial_call=True,
)
def _save_mnid_executive_tab(tab_value):
    return tab_value or 'country-profile'


@callback(
    [Output('dashboard-container', 'children'),
     Output('dashboard-level-filter', 'value'),
     Output('dashboard-district-filter-group', 'style'),
     Output('dashboard-district-filter', 'options'),
     Output('dashboard-district-filter', 'value'),
     Output('dashboard-district-filter', 'disabled'),
     Output('dashboard-district-note', 'children'),
     Output('dashboard-facility-filter', 'options'),
     Output('dashboard-facility-filter', 'value'),
     Output('filter-period-text', 'children'),
     Output('active-button-store', 'data'),
     Output('dashboard-render-state', 'data')],
    [
        Input('dashboard-btn-generate', 'n_clicks'),
        Input('dashboard-date-range-picker', 'start_date'),
        Input('dashboard-date-range-picker', 'end_date'),
        Input('dashboard-level-filter', 'value'),
        Input('dashboard-district-filter', 'value'),
        Input('dashboard-facility-filter', 'value'),
        Input('dashboard-overview-filter', 'value'),
        Input('dashboard-category-filter', 'value'),
        Input({"type": "menu-button", "name": ALL}, "n_clicks"),
        Input('url', 'pathname'),
        Input('dashboard-moh-level-filter', 'value'),
    ],
    [
        State('url-params-store', 'data'),
        State('dashboard-age-filter', 'value'),
        State('active-button-store', 'data'),
        State('mnid-active-tab-store', 'data'),
    ],
)
def update_dashboard(gen, start_date, end_date, level,
                     districts, facilities, overview, category,
                     menu_clicks, pathname, moh_level, urlparams, age, current_active, active_mnid_tab):
    try:
        ctx = callback_context
        triggered_id = ctx.triggered[0]['prop_id'] if ctx.triggered else None

        data_route = (urlparams or {}).get('route', ["default"])[0]
        dataset_version = _dataset_version_token(data_route)

        # Determine which report to show
        clicked_name = current_active
        if triggered_id and "menu-button" in triggered_id:
            prop_dict = json.loads(triggered_id.split('.')[0])
            clicked_name = prop_dict['name']

        menu_json = load_dashboard_menu()
        if overview:
            selected_reports = overview
        else:
            default_report = "General Summary" or menu_json[0]["report_name"]
            selected_reports = [clicked_name] if clicked_name in {d.get("report_name") for d in menu_json} else [default_report]
        selected_reports = list(dict.fromkeys(normalize_report_name(r, menu_json) for r in selected_reports))
        # Date Logic
        default_start, default_end = _default_date_window(data_route)
        start_dt = pd.to_datetime(start_date or default_start).replace(hour=0, minute=0, second=0)
        end_dt = pd.to_datetime(end_date or default_end).replace(hour=23, minute=59, second=59)
        default_start_date = start_dt - pd.Timedelta(days=DEFAULT_DASHBOARD_DAYS)

        location = (urlparams.get("Location") or urlparams.get("?Location") or [None])[0]
        DATA_PATH_ = f"data/{data_route}/parquet"

        user_data = _load_user_registry(data_route)
        user_row, scope = _resolve_user_scope(urlparams, user_data)

        if user_row is None:
            return (html.Div("Unauthorized User. Please contact system administrator."), level,
                    {'display': 'none'} if level in ['National', 'Facility'] else {},
                    [], [], False, "", [],"", [], clicked_name)

        user_level = scope['level']
        user_districts = scope.get('districts') or []
        if user_level == 'facility' and scope.get('facility_code'):
            location = scope['facility_code']

        url_object = f"Location={location}&uuid={urlparams.get('uuid', [None])[0]}&user_level={user_level}"

        # Level resolution
        requested_level = _normalize_level(level) if level else user_level

        # print(user_row, scope, user_level)

        if user_level == 'national':
            effective_level = requested_level if requested_level in {'national', 'district', 'facility'} else 'national'
        elif user_level == 'district':
            effective_level = requested_level if requested_level in {'district', 'facility'} else 'district'
        else:
            effective_level = 'facility'
        level = _title_level(effective_level)

        show_district_filter = effective_level == "national"
        district_group_style = {} if show_district_filter else {"display": "none"}
        district_disabled = not show_district_filter
        district_note = ""
        if not show_district_filter:
            districts = []

        # Dropdown option lists
        facilities_path = os.path.join(path, f'data/{data_route}', 'dcc_dropdown_json', 'facilities_dropdowns.json')
        with open(facilities_path, 'r') as f:
            facilities_dict = json.load(f)
        if requested_level == "national":
            all_districts = sorted(facilities_dict.keys())
            all_facilities = sorted(set(
                facility
                for district in districts
                if district in all_districts
                for facility in facilities_dict.get(district, [])
            ))
        elif requested_level == "district":
            all_districts = sorted(set(user_districts))
            all_facilities = sorted(set(
                facility
                for district in user_districts
                if district in all_districts
                for facility in facilities_dict.get(district, [])
            ))
        else:
            all_districts = sorted(set(user_districts))
            all_facilities = scope.get('facilities') or []
        if isinstance(all_facilities, str):
            all_facilities = [all_facilities]

        # ── Shared scope & query building ────────────────────────────────────
        # active_dists: at district level fall back to user's districts when
        # nothing is selected in the UI; at national level only use UI selection.
        active_dists = (districts or user_districts) if effective_level == 'district' else (districts or [])
        delta_days = max((end_dt - start_dt).days, 1)

        filtered_parts = _scope_where_parts(effective_level, location, districts, user_districts, facilities, age, is_network=False)
        network_parts  = _scope_where_parts(effective_level, location, districts, user_districts, facilities, age, is_network=True)
        scope_suffix   = (" AND " + " AND ".join(filtered_parts)) if filtered_parts else ""
        network_suffix = (" AND " + " AND ".join(network_parts))  if network_parts  else ""

        filtered_query = (
            f"{DATE_} BETWEEN '{start_dt}'::TIMESTAMP AND '{end_dt}'::TIMESTAMP"
            + scope_suffix
        )
        network_query = (
            f"{DATE_} >= '{default_start_date}'::TIMESTAMP"
            f" AND {DATE_} <= '{end_dt}'::TIMESTAMP"
            + scope_suffix
        )

        # Scope label (used by MNID topbar; harmless for non-MNID)
        facility_names = []
        if effective_level == 'facility' and location:
            try:
                _fac_lookup = DataStorage.query_duckdb(
                    f"SELECT DISTINCT {FACILITY_} FROM '{DATA_PATH_}'"
                    f" WHERE {FACILITY_CODE_} = '{location}' LIMIT 1"
                )
                if not _fac_lookup.empty:
                    facility_names = _fac_lookup[FACILITY_].dropna().tolist()
            except Exception:
                facility_names = []
        elif facilities:
            facility_names = list(facilities)

        active_facilities = facility_names or facilities or []
        if active_facilities:
            scope_label = 'Facility' if len(active_facilities) == 1 else 'Facilities'
            scope_value = active_facilities[0] if len(active_facilities) == 1 else f'{len(active_facilities)} selected facilities'
        elif active_dists:
            scope_label = 'District' if len(active_dists) == 1 else 'Districts'
            scope_value = ', '.join(active_dists)
        else:
            scope_label = 'Districts'
            scope_value = 'All districts'

        mnid_categories = [category] if category and category != 'All' else None
        scope_meta = {
            'label':               scope_label,
            'value':               scope_value,
            'mnid_categories':     mnid_categories,
            'level':               effective_level,
            'selected_facilities': active_facilities,
            'selected_districts':  active_dists,
            'data_period_note':    None,
            'dataset_version':     dataset_version,
            'route':               data_route,
        }

        rendered = []
        for report_name in selected_reports:
            dashboard_json = next((d for d in menu_json if d['report_name'] == report_name), None)
            if not dashboard_json:
                break

            section = build_charts_from_json(
                filtered_query,
                network_query,
                delta_days,
                dashboard_json,
                start_date=start_dt,
                end_date=end_dt,
                data_path=DATA_PATH_,
                facility_code=location,
                scope_meta=scope_meta,
                url_object=url_object,
                initial_tab=active_mnid_tab,
            )
            rendered.append(html.Div([
                html.H3(report_name, style={"marginTop": "10px"}),
                section
            ]))

        dashboard_content = html.Div(rendered) if len(rendered) > 1 else (rendered[0] if rendered else html.Div("No dashboard selected."))

        
        return (
            dashboard_content,
            level,
            district_group_style,
            [{'label': d, 'value': d} for d in all_districts],
            districts,
            district_disabled,
            district_note,
            [{'label': f, 'value': f} for f in all_facilities],
            facilities,
            f"{start_dt} - {end_dt}",
            clicked_name,
            {
                'status': 'ok',
                'selected_reports': selected_reports,
                'effective_level': effective_level,
                'districts': districts,
                'facilities': facilities,
                'category': category,
                'age': age,
                'dataset_version': dataset_version,
                'user_level': user_level,
                'scope': scope,
                'location': location,
                'mnid_location': location,
                'url_object': url_object,
                'start_dt': start_dt.isoformat(),
                'end_dt': end_dt.isoformat(),
                # 'initial_mnid_tab': initial_mnid_tab,
                'mnid_only_request': False,
                'facility_level': moh_level or 'All',
            },
        )
    except PreventUpdate:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        return (
            html.Div([
                html.P("Dashboard render failed.", style={"color": "#475569", "fontWeight": "600"}),
                html.P(f"{type(e).__name__}", style={"color": "#64748b", "fontSize": "12px", "fontWeight": "600"}),
                html.P(str(e), style={"color": "#94A3B8", "fontSize": "12px"}),
            ]),
            dash.no_update,
            dash.no_update,
            dash.no_update,
            dash.no_update,
            dash.no_update,
            dash.no_update,
            dash.no_update,
            dash.no_update,
            dash.no_update,
            dash.no_update,
            dash.no_update,
        )

@callback(
    [Output('dashboard-date-range-picker', 'start_date'),
     Output('dashboard-date-range-picker', 'end_date')],
    [Input('dashboard-period-type-filter', 'value'),
     Input('dashboard-interval-update-today', 'n_intervals')],
    [State('url-params-store', 'data')],
)
def sync_picker_with_logic(period_type, n, urlparams):
    ctx = callback_context
    triggered_id = ctx.triggered[0]['prop_id'] if ctx.triggered else ""
    data_route = (urlparams or {}).get('route', ["default"])[0]
    default_start, default_end = _default_date_window(data_route)
    anchor = default_end

    if "dashboard-interval-update-today" in triggered_id:
        if period_type == "Today":
            return anchor, anchor
        raise PreventUpdate
    if period_type:
        s, e = get_relative_date_range(period_type, current_date=anchor)
        if s and e:
            return s, e
    return default_start, default_end

@callback(
    [Output('dashboard-period-type-filter', 'value', allow_duplicate=True),
     Output('dashboard-level-filter', 'value', allow_duplicate=True),
     Output('dashboard-district-filter', 'value', allow_duplicate=True),
     Output('dashboard-facility-filter', 'value', allow_duplicate=True),
     Output('dashboard-overview-filter', 'value', allow_duplicate=True),
     Output('dashboard-category-filter', 'value', allow_duplicate=True),
     Output('dashboard-age-filter', 'value', allow_duplicate=True)],
    Input('dashboard-btn-reset', 'n_clicks'),
    prevent_initial_call=True
)
def reset_ui_controls(n_clicks):
    return DEFAULT_RELATIVE_PERIOD, None, [], [], [], "All", None

@callback(
    [Output('dashboard-period-type-filter', 'style'),
     Output('dashboard-date-range-picker', 'style', allow_duplicate=True),
     Output('dashboard-level-filter', 'style'),
     Output('dashboard-district-filter', 'style'),
     Output('dashboard-facility-filter', 'style'),
     Output('dashboard-overview-filter', 'style'),
     Output('dashboard-category-filter', 'style'),
     Output('dashboard-age-filter', 'style')],
    [Input('dashboard-btn-reset', 'n_clicks'),
     Input('dashboard-btn-generate', 'n_clicks')],
    prevent_initial_call=True
)
def change_style(generate, reset):
    # Returns bold items on generate to indicate active filters
    ctx = callback_context
    triggered_id = ctx.triggered[0]['prop_id'] if ctx.triggered else None
    if triggered_id == "dashboard-btn-generate.n_clicks":
        style_active = {
                    # "display": "flex",
                    "alignItems": "center",
                    "gap": "5px",
                    "border": "3px solid green",
                    "borderRadius": "8px"
                    }
        return style_active, style_active, style_active, style_active, style_active, style_active, style_active, style_active
    else:
        style_default = {}
        return style_default, style_default, style_default, style_default, style_default, style_default, style_default, style_default


@callback(
    Output('dashboard-age-filter-group', 'style'),
    Output('dashboard-category-filter-group', 'style'),
    Input('active-button-store', 'data'),
)
def toggle_age_group_visibility(active_report):
    report = str(active_report or '').strip().lower()

    hide_for = {'maternal health', 'newborn', 'neonatal program'}
    show_program_for = {'maternal health'}
    if report in hide_for:
        age_style = {'display': 'none'}
    else:
        age_style = {}

    if report in show_program_for:
        program_style = {}
    else:
        program_style = {'display': 'none'}

    return age_style, program_style


@callback(
    Output('dashboard-moh-level-filter-group', 'style'),
    Input('active-button-store', 'data'),
)
def toggle_moh_level_visibility(active_report):
    report = str(active_report or '').strip().lower()
    if report == 'maternal health':
        return {}
    return {'display': 'none'}
