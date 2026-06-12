import dash
from dash import html, dcc, Input, Output, callback, State, no_update, ALL, callback_context
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
from datetime import datetime
from datetime import datetime as dt
from data_storage import DataStorage
from config import DATA_PATH_,CUSTOM_GENDER_MAP
import warnings
warnings.filterwarnings("ignore")
from helpers.date_ranges import (
                    get_relative_date_range,
                    RELATIVE_PERIOD_LIST
            )
from helpers.navigation_callbacks import DEMO_UUID, DEMO_LOCATION

# Importing parquet file path and from config

# importing referential columns from config
from config import (actual_keys_in_data, 
                    DATA_PATH_, 
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

_mnid_full_data_cache: dict = {}
_dashboard_data_cache: dict = {}
DEFAULT_DASHBOARD_DAYS = 7
DEFAULT_RELATIVE_PERIOD = 'This Month'
_LATEST_DATA_DATE_CACHE: dict[str, pd.Timestamp | None] = {}
_MNID_FULL_CACHE_MAX = 6
_DASHBOARD_DATA_CACHE_MAX = 4


def _trim_cache(cache: dict, max_entries: int) -> None:
    while len(cache) > max_entries:
        try:
            cache.pop(next(iter(cache)))
        except Exception:
            break


def _start_mnid_prewarm(version: str | None = None):
    """Kick off MNID cache pre-warm in a daemon background thread at server startup."""
    import threading
    import logging
    _log = logging.getLogger(__name__)

    def _run(v):
        try:
            from mnid.app import prewarm_cache
            prewarm_cache(dataset_version=v)
        except Exception as exc:
            _log.warning('MNID startup pre-warm thread failed: %s', exc)

    t = threading.Thread(target=_run, args=(version,), daemon=True, name='mnid-prewarm')
    t.start()
    _log.info('MNID pre-warm thread started')


def _latest_available_date() -> pd.Timestamp | None:
    cache_key = f'{DATA_PATH_}:{_dataset_version_token()}'
    if cache_key in _LATEST_DATA_DATE_CACHE:
        return _LATEST_DATA_DATE_CACHE[cache_key]
    try:
        latest = DataStorage.query_duckdb(f"SELECT MAX(Date) AS max_date FROM '{DATA_PATH_}'")
        max_date = pd.to_datetime(latest.loc[0, 'max_date'], errors='coerce') if len(latest) else pd.NaT
    except Exception:
        max_date = pd.NaT
    resolved = None if pd.isna(max_date) else max_date.normalize()
    _LATEST_DATA_DATE_CACHE.clear()
    _LATEST_DATA_DATE_CACHE[cache_key] = resolved
    return resolved


def _default_date_window():
    latest = _latest_available_date()
    anchor = latest.date() if latest is not None else datetime.now().date()
    start = anchor - pd.Timedelta(days=29)
    return start, anchor


def _dataset_version_token() -> str:
    timestamp_path = os.path.join(path, 'data', 'TimeStamp.csv')
    data_path = os.path.join(path, 'data', DATA_PATH_)
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


_start_mnid_prewarm(_dataset_version_token())


def clear_dashboard_state_cache() -> None:
    _mnid_full_data_cache.clear()
    _dashboard_data_cache.clear()


def _load_user_registry(route) -> pd.DataFrame:
    user_data_path = os.path.join(path, f'data/{route}','single_tables', 'users_data.csv')

    if os.path.exists(user_data_path):
        user_data = pd.read_csv(user_data_path)
    else:
        user_data = pd.DataFrame(columns=['uuid', 'role','user_level','district','facility_name','facility_code'])
    demo_row = {
        'uuid': DEMO_UUID,
        'role': 'reports_admin',
        'user_level': 'national',
        'district': ["Salima"],
        'facility_name': None,
        'facility_code': DEMO_LOCATION,
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
    return 'national'


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

def get_dashboard_names():
    return [d.get("report_name") for d in load_dashboard_menu() if d.get("report_name")]

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
                          start_date=None, end_date=None, data_path=DATA_PATH_, facility_code=None, scope_meta=None, url_object=None):
    
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



layout = html.Div(
    className="dashboard-layout-modern",
    children=[
        dcc.Location(id='url', refresh=False),
        dcc.Store(id='active-button-store', data='General Summary'),
        
        # Left Sidebar
        html.Div(
            className="dashboard-sidebar",
            children=[
                
                # Filters Section
                html.Div(
                    className="sidebar-filters-section",
                    children=[
                        html.Div(
                            className="filters-card",
                            children=[
                                html.H3("Filter Data", className="filters-title"),
                                
                                html.Div(
                                    className="filters-container",
                                    children=[
                                        # Level Filter
                                        html.Div(
                                            className="filter-group",
                                            children=[
                                                html.Label("Level", className="filter-label"),
                                                dcc.Dropdown(
                                                    id='dashboard-level-filter',
                                                    options=[
                                                        {'label': 'National', 'value': 'National'},
                                                        {'label': 'District', 'value': 'District'},
                                                        {'label': 'Facility', 'value': 'Facility'},
                                                    ],
                                                    value=None,
                                                    clearable=True,
                                                    className="modern-dropdown",
                                                    placeholder="Select level"
                                                )
                                            ]
                                        ),

                                        # District Filter
                                        html.Div(
                                            id="dashboard-district-filter-group",
                                            className="filter-group",
                                            children=[
                                                html.Label("District", className="filter-label"),
                                                dcc.Dropdown(
                                                    id='dashboard-district-filter',
                                                    options=[],
                                                    value=[],
                                                    multi=True,
                                                    clearable=True,
                                                    className="modern-dropdown",
                                                    placeholder="Select district(s)"
                                                ),
                                                html.Div(
                                                    id="dashboard-district-note",
                                                    className="filter-note",
                                                    style={"fontSize": "12px", "color": "#64748b", "marginTop": "6px"}
                                                )
                                            ]
                                        ),

                                        # Facility Filter
                                        html.Div(
                                            className="filter-group",
                                            children=[
                                                html.Label("Health Facility", className="filter-label"),
                                                dcc.Dropdown(
                                                    id='dashboard-facility-filter',
                                                    options=[],
                                                    value=[],
                                                    multi=True,
                                                    clearable=True,
                                                    className="modern-dropdown",
                                                    placeholder="Select facility(ies)"
                                                )
                                            ]
                                        ),

                                        # Relative Period Filter
                                        html.Div(
                                            className="filter-group",
                                            children=[
                                                html.Label("Relative Period", className="filter-label"),
                                                dcc.Dropdown(
                                                    id='dashboard-period-type-filter',
                                                    options=[
                                                        {'label': item, 'value': item}
                                                        for item in RELATIVE_PERIOD_LIST
                                                    ],
                                                    value=DEFAULT_RELATIVE_PERIOD,
                                                    clearable=True,
                                                    className="modern-dropdown"
                                                )
                                            ]
                                        ),
                                        
                                        # Custom Date Range
                                        html.Div(
                                            className="filter-group",
                                            children=[
                                                html.Label("Custom Date Range", className="filter-label"),
                                                dcc.DatePickerRange(
                                                    id='dashboard-date-range-picker',
                                                    min_date_allowed="2023-01-01",
                                                    max_date_allowed="2050-01-01",
                                                    initial_visible_month=datetime.now(),
                                                    start_date=_default_date_window()[0],
                                                    end_date=_default_date_window()[1],
                                                    display_format='YYYY-MM-DD',
                                                    className="modern-datepicker"
                                                )
                                            ]
                                        ),

                                        html.Div(
                                            style={"display": "none"},
                                            children=[
                                                dcc.Dropdown(
                                                    id='dashboard-overview-filter',
                                                    options=[
                                                        {"label": name, "value": name}
                                                        for name in get_dashboard_names()
                                                    ],
                                                    value=[],
                                                    multi=True,
                                                    clearable=True,
                                                    className="modern-dropdown",
                                                )
                                            ]
                                        ),

                                        # Program Category Filter (MNID)
                                        html.Div(
                                            id="dashboard-category-filter-group",
                                            className="filter-group",
                                            children=[
                                                html.Label("Program Category", className="filter-label"),
                                                dcc.Dropdown(
                                                    id='dashboard-category-filter',
                                                    options=[
                                                        {"label": "All", "value": "All"},
                                                        {"label": "ANC", "value": "ANC"},
                                                        {"label": "Labour & Delivery", "value": "Labour"},
                                                        {"label": "PNC", "value": "PNC"},
                                                    ],
                                                    value="All",
                                                    clearable=False,
                                                    className="modern-dropdown",
                                                )
                                            ]
                                        ),
                                        
                                        # Age Group Filter
                                        html.Div(
                                            id="dashboard-age-filter-group",
                                            className="filter-group",
                                            children=[
                                                html.Label("Age Group", className="filter-label"),
                                                dcc.Dropdown(
                                                    id='dashboard-age-filter',
                                                    options=[
                                                        {'label': age, 'value': age}
                                                        for age in ['Over 5', 'Under 5']
                                                    ],
                                                    value=None,
                                                    clearable=True,
                                                    className="modern-dropdown"
                                                )
                                            ]
                                        ),
                                    ]
                                ),
                                
                                # Action Buttons
                                html.Div(
                                    className="filter-actions",
                                    children=[
                                        html.Button(
                                            "Apply Filters", 
                                            id="dashboard-btn-generate", 
                                            n_clicks=0, 
                                            className="btn-apply-modern"
                                        ),
                                        html.Button(
                                            "Reset Filters", 
                                            id="dashboard-btn-reset", 
                                            n_clicks=0, 
                                            className="btn-reset-modern"
                                        ),
                                    ]
                                )
                            ]
                        )
                    ]
                ),
            ]
        ),
        
        # Right Content Area
        html.Div(
            className="dashboard-main",
            children=[
                # Menu Section
                html.Div(
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
                                    html.Div("Refreshing dashboard", className="home-loading-title"),
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
                        "opacity": 0.45,
                        "backgroundColor": "rgba(255,255,255,0.82)",
                        "borderRadius": "16px",
                        "zIndex": 10,
                    },
                    delay_show=150,
                    children=html.Div(
                        id='dashboard-container',
                        className="dashboard-content-modern"
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
    ]
)

@callback(
        Output('scrolling-menu', 'children'),
        [Input('dashboard-interval-update-today', 'n_intervals'),
        Input('active-button-store', 'data')])

def update_menu(interval, color):
    with open(json_path, 'r') as f:
        menu_json = json.load(f)

    return [
        html.Button(
            display_report_name(d["report_name"]),
            className="menu-btn active" if color == d["report_name"] else "menu-btn",
            id={"type": "menu-button", "name": d["report_name"]}
        )
        for d in menu_json
        if d.get("report_name") != "Newborn"
    ]


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
     Output('active-button-store', 'data')],
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
        Input('url', 'pathname')
    ],
    [
        State('url-params-store', 'data'),
        State('dashboard-age-filter', 'value'),
        State('active-button-store', 'data')
    ],
)
def update_dashboard(gen, start_date, end_date, level,
                     districts, facilities, overview, category,
                     menu_clicks, pathname, urlparams, age, current_active):
    try:
        ctx = callback_context
        triggered_id = ctx.triggered[0]['prop_id'] if ctx.triggered else None

        dataset_version = _dataset_version_token()

        # Determine which report to show
        clicked_name = current_active
        if triggered_id and "menu-button" in triggered_id:
            prop_dict = json.loads(triggered_id.split('.')[0])
            clicked_name = prop_dict['name']

        menu_json = load_dashboard_menu()
        if overview:
            selected_reports = overview
        else:
            selected_reports = [clicked_name] if clicked_name else [menu_json[0]["report_name"] if menu_json else "Dashboard"]
        selected_reports = list(dict.fromkeys(normalize_report_name(r, menu_json) for r in selected_reports))
        # Date Logic
        default_start, default_end = _default_date_window()
        start_dt = pd.to_datetime(start_date or default_start).replace(hour=0, minute=0, second=0)
        end_dt = pd.to_datetime(end_date or default_end).replace(hour=23, minute=59, second=59)
        default_start_date = start_dt - pd.Timedelta(days=DEFAULT_DASHBOARD_DAYS)

        location = (urlparams.get("Location") or urlparams.get("?Location") or [None])[0]
        data_route = urlparams.get('route', ["default"])[0]
        DATA_PATH_ = f"data/{data_route}/parquet"

        user_data = _load_user_registry(data_route)
        user_row, scope = _resolve_user_scope(urlparams, user_data)

        if user_row is None:
            return (html.Div("Unauthorized User. Please contact system administrator."), level,
                    {'display': 'none'} if level in ['National', 'Facility'] else {},
                    [], [], False, "", [], [], clicked_name)

        user_level = scope['level']
        user_districts = scope.get('districts') or []
        if user_level == 'facility' and scope.get('facility_code'):
            location = scope['facility_code']

        url_object = f"Location={location}&uuid={urlparams.get('uuid', [None])[0]}&user_level={user_level}"

        # Level resolution
        requested_level = _normalize_level(level) if level else user_level
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
                for district in user_districts
                if district in all_districts
                for facility in facilities_dict.get(district, [])
            ))
        elif requested_level == "district":
            all_districts = sorted(set(user_districts))
            all_facilities = sorted(set(
                facility
                for district in all_districts
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
            + network_suffix
        )

        # ── Scope label (used by MNID topbar; harmless for non-MNID) ─────────
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
            clicked_name
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
        )

@callback(
    [Output('dashboard-date-range-picker', 'start_date'),
     Output('dashboard-date-range-picker', 'end_date')],
    [Input('dashboard-period-type-filter', 'value'),
     Input('dashboard-interval-update-today', 'n_intervals')],
)
def sync_picker_with_logic(period_type, n):
    ctx = callback_context
    triggered_id = ctx.triggered[0]['prop_id'] if ctx.triggered else ""
    default_start, default_end = _default_date_window()
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
