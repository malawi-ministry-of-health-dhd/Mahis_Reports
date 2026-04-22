import diskcache
import dash
from dash import html, dcc, Input, Output, callback, State, no_update, ALL, callback_context
import pandas as pd
import plotly.express as px
import os
import json
import numpy as np
import uuid
from dash.exceptions import PreventUpdate
import os
from flask import request
from helpers.helpers import build_charts_section, build_metrics_section
from mnid_renderer import render_mnid_dashboard
from dashboard_layouts import build_premium_dashboard
from datetime import datetime
from datetime import datetime as dt
from data_storage import DataStorage
from config import DATA_FILE_NAME_

# Importing parquet file path and from config

# importing referential columns from config
from config import (actual_keys_in_data, 
                    DATA_FILE_NAME_, 
                    DATE_, PERSON_ID_, ENCOUNTER_ID_,
                    FACILITY_, AGE_GROUP_, AGE_,
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

path = os.getcwd()
json_path = os.path.join(path, 'data', 'visualizations', 'validated_dashboard.json')

# Shared cross-process cache for MNID prepared DataFrames.
# Uses diskcache so data persists across background callback worker processes.
_mnid_disk_cache = diskcache.Cache('./cache/mnid')
_dashboard_state_disk_cache = diskcache.Cache('./cache/dashboard_state')

# In-process fallback (used when background=False or within same worker)
_mnid_full_data_cache: dict = {}
_dashboard_state_cache: dict = {}
_DASHBOARD_STATE_CACHE_MAX = 8
_DASHBOARD_STATE_TTL = 900

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
    if name == "Maternal and Child Health":
        if any(d.get("report_name") == "Maternal Health" for d in menu_json):
            return "Maternal Health"
    return name


def _remember_dashboard_state(state: dict) -> str:
    key = f"dashboard_state:{uuid.uuid4().hex}"
    _dashboard_state_cache[key] = state
    while len(_dashboard_state_cache) > _DASHBOARD_STATE_CACHE_MAX:
        oldest_key = next(iter(_dashboard_state_cache))
        _dashboard_state_cache.pop(oldest_key, None)
    _dashboard_state_disk_cache.set(key, state, expire=_DASHBOARD_STATE_TTL)
    return key


def _load_dashboard_state(key: str | None) -> dict | None:
    if not key:
        return None
    state = _dashboard_state_cache.get(key)
    if state is None:
        state = _dashboard_state_disk_cache.get(key)
        if state is not None:
            _dashboard_state_cache[key] = state
    return state


def clear_dashboard_state_cache() -> None:
    _dashboard_state_cache.clear()
    try:
        _dashboard_state_disk_cache.clear()
    except Exception:
        pass


def _build_error_div(message: str, detail: str | None = None):
    children = [html.P(message, style={"color": "#475569", "fontWeight": "600"})]
    if detail:
        children.append(html.P(detail, style={"color": "#94A3B8", "fontSize": "12px"}))
    return html.Div(children)


def _prepare_dashboard_state(start_date, end_date, level, districts, facilities, overview, category, urlparams, age, current_active, triggered_id):
    if not urlparams:
        urlparams = {"Location": ["LL040033"], "uuid": ["m3his@dhd"]}
    if not urlparams.get("Location"):
        urlparams["Location"] = ["LL040033"]
    if not urlparams.get("uuid"):
        urlparams["uuid"] = ["m3his@dhd"]

    clicked_name = current_active
    if triggered_id and "menu-button" in triggered_id:
        prop_dict = json.loads(triggered_id.split('.')[0])
        clicked_name = prop_dict['name']

    start_dt = pd.to_datetime(start_date).replace(hour=0, minute=0, second=0)
    end_dt = pd.to_datetime(end_date).replace(hour=23, minute=59, second=59)
    last_7_days = start_dt - pd.Timedelta(days=7)

    location = urlparams.get('Location', [None])[0] or "LL040033"
    mnid_location = urlparams.get('Location', [None])[0] if urlparams.get('Location') else None

    user_levels = ['national', 'district']
    user_level = urlparams.get('user_level', [None])[0]

    if not level:
        if user_level == 'national':
            level = 'National'
        elif user_level == 'district':
            level = 'District'
        else:
            level = 'Facility'

    if level in ['National', 'District'] or user_level in user_levels:
        SQL = f"""
            SELECT *
            FROM 'data/{DATA_FILE_NAME_}'
            WHERE Date >= TIMESTAMP '{last_7_days}'
            """
    else:
        SQL = f"""
            SELECT *
            FROM 'data/{DATA_FILE_NAME_}'
            WHERE Date >= TIMESTAMP '{last_7_days}'
            AND {FACILITY_CODE_} = '{location}'
            """

    try:
        data = DataStorage.query_duckdb(SQL)
    except Exception as e:
        return {
            'error': ('Missing Data. Ensure that the config file has correct database credentials', None),
            'controls': {
                'level': level,
                'district_group_style': dash.no_update,
                'district_options': [],
                'districts': [],
                'district_disabled': True,
                'district_note': "",
                'facility_options': [],
                'facilities': [],
                'active_button': current_active or dash.no_update,
            },
            'exception': e,
        }

    data[DATE_] = pd.to_datetime(data[DATE_], format='mixed')
    data[GENDER_] = data[GENDER_].replace({"M":"Male",
                                           "F":"Female",
                                           '{"label"=>"Male", "value"=>"M"}':"Male",
                                           '{"label"=>"Female", "value"=>"F"}':"Female"})
    data["DateValue"] = pd.to_datetime(data[DATE_]).dt.date
    data['datetime'] = data[DATE_]
    data[DATE_] = data[DATE_].dt.normalize()

    today = dt.today().date()
    data["months"] = ((pd.Timestamp(today) - pd.to_datetime(data["DateValue"])).dt.days // 30).clip(lower=0)

    user_data_path = os.path.join(path, 'data', 'users_data.csv')
    if not os.path.exists(user_data_path):
        user_data = pd.DataFrame(columns=['user_id', 'role'])
    else:
        user_data = pd.read_csv(os.path.join(path, 'data', 'users_data.csv'))
    test_admin = pd.DataFrame(columns=['user_id', 'role'], data=[['m3his@dhd', 'reports_admin']])
    user_data = pd.concat([user_data, test_admin], ignore_index=True)

    user_info = user_data[user_data['user_id'] == urlparams.get('uuid', [None])[0]]
    if user_info.empty:
        return {
            'error': ("Unauthorized User. Please contact system administrator.", None),
            'controls': {
                'level': level,
                'district_group_style': {'display': 'none'} if level in ['National', 'Facility'] else {},
                'district_options': [],
                'districts': [],
                'district_disabled': False,
                'district_note': "",
                'facility_options': [],
                'facilities': [],
                'active_button': clicked_name,
            },
        }

    base_mask = pd.Series(True, index=data.index)
    if age:
        base_mask &= (data[AGE_GROUP_] == age)
    category = category or "All"
    base_data_mnid = data[base_mask].copy()
    encounter_mask = pd.Series(True, index=data.index)
    if category != "All" and "Encounter" in data.columns:
        if category == "ANC":
            encounter_mask = data["Encounter"].fillna('').astype(str).str.contains('ANC', case=False, na=False)
        elif category == "Labour":
            encounter_mask = data["Encounter"].fillna('').astype(str).str.contains('LABOUR|DELIVERY|BIRTH', case=False, na=False)
        elif category == "PNC":
            encounter_mask = data["Encounter"].fillna('').astype(str).str.contains('PNC|POSTNATAL|POST.NATAL', case=False, na=False)
    base_data = data[base_mask & encounter_mask].copy()

    district_col = "District" if "District" in base_data.columns else (HOME_DISTRICT_ if HOME_DISTRICT_ in base_data.columns else None)
    all_districts = (
        base_data[district_col].dropna().sort_values().unique().tolist()
        if district_col else []
    )

    districts = districts or []
    facilities = facilities or []
    overview = overview or []
    if level == 'National':
        districts = []
        facilities = []
    elif level == 'District' and facilities and district_col:
        allowed_facilities = set(
            base_data[base_data[district_col].isin(districts)][FACILITY_]
            .dropna()
            .unique()
            .tolist()
        ) if districts else set()
        facilities = [f for f in facilities if f in allowed_facilities]

    if level == "National":
        facilities_pool = base_data
    elif level == "District" and district_col and not districts:
        facilities_pool = base_data.iloc[0:0]
    elif district_col and districts:
        facilities_pool = base_data[base_data[district_col].isin(districts)]
    else:
        facilities_pool = base_data
    all_facilities = (
        facilities_pool[FACILITY_].dropna().sort_values().unique().tolist()
        if FACILITY_ in facilities_pool.columns else []
    )

    show_district_filter = level == "District"
    district_group_style = {} if show_district_filter else {"display": "none"}
    district_disabled = not show_district_filter
    district_note = ""
    if not show_district_filter:
        districts = []

    if level == "District" and district_col and districts:
        allowed_facilities = set(
            base_data[base_data[district_col].isin(districts)][FACILITY_]
            .dropna()
            .unique()
            .tolist()
        )
        facilities = [f for f in facilities if f in allowed_facilities]
        all_facilities = sorted(allowed_facilities)

    network_data = base_data.copy()
    if level != 'National' and district_col and districts:
        network_data = network_data[network_data[district_col].isin(districts)]
    filtered_data = network_data.copy()
    if level == 'Facility' and facilities:
        filtered_data = filtered_data[filtered_data[FACILITY_].isin(facilities)]
    elif level == 'District' and facilities:
        filtered_data = filtered_data[filtered_data[FACILITY_].isin(facilities)]
    if filtered_data.empty and len(network_data):
        filtered_data = network_data.copy()

    network_data_mnid = base_data_mnid.copy()
    if level != 'National' and district_col and districts:
        network_data_mnid = network_data_mnid[network_data_mnid[district_col].isin(districts)]
    filtered_data_mnid = network_data_mnid.copy()
    if level == 'Facility' and facilities:
        filtered_data_mnid = filtered_data_mnid[filtered_data_mnid[FACILITY_].isin(facilities)]
    elif level == 'District' and facilities:
        filtered_data_mnid = filtered_data_mnid[filtered_data_mnid[FACILITY_].isin(facilities)]
    if filtered_data_mnid.empty and len(network_data_mnid):
        filtered_data_mnid = network_data_mnid.copy()

    menu_json = load_dashboard_menu()
    if overview:
        selected_reports = overview
    else:
        selected_reports = [clicked_name] if clicked_name else [menu_json[0]["report_name"] if menu_json else "Dashboard"]
    selected_reports = [normalize_report_name(r, menu_json) for r in selected_reports]

    return {
        'error': None,
        'controls': {
            'level': level,
            'district_group_style': district_group_style,
            'district_options': [{'label': d, 'value': d} for d in all_districts],
            'districts': districts,
            'district_disabled': district_disabled,
            'district_note': district_note,
            'facility_options': [{'label': f, 'value': f} for f in all_facilities],
            'facilities': facilities,
            'active_button': clicked_name,
        },
        'render': {
            'start_dt': start_dt,
            'end_dt': end_dt,
            'level': level,
            'districts': districts,
            'facilities': facilities,
            'category': category,
            'location': location,
            'mnid_location': mnid_location,
            'selected_reports': selected_reports,
            'menu_json': menu_json,
            'base_data_mnid': base_data_mnid,
            'filtered_data': filtered_data,
            'filtered_data_mnid': filtered_data_mnid,
            'network_data': network_data,
            'district_col': district_col,
            'user_level': user_level,
        },
    }


def _render_dashboard_from_state(state: dict):
    if not state:
        return _build_error_div("Dashboard render failed.", "Dashboard state was not found in cache.")
    if state.get('error'):
        message, detail = state['error']
        return _build_error_div(message, detail)

    render = state['render']
    start_dt = render['start_dt']
    end_dt = render['end_dt']
    level = render['level']
    districts = render['districts']
    facilities = render['facilities']
    category = render['category']
    location = render['location']
    mnid_location = render['mnid_location']
    selected_reports = render['selected_reports']
    menu_json = render['menu_json']
    base_data_mnid = render['base_data_mnid']
    filtered_data = render['filtered_data']
    filtered_data_mnid = render['filtered_data_mnid']
    network_data = render['network_data']
    district_col = render['district_col']

    rendered = []
    for report_name in selected_reports:
        dashboard_json = next((d for d in menu_json if d['report_name'] == report_name), None)
        if not dashboard_json:
            break
        is_mnid = dashboard_json.get('dashboard_type') == 'mnid'

        _fdata = filtered_data_mnid if is_mnid else filtered_data
        if is_mnid:
            _mnid_scope_key = (
                level,
                tuple(sorted(districts or [])),
                tuple(sorted(facilities or [])),
            )
            _disk_key = f"mnid_full_{'_'.join(str(k) for k in _mnid_scope_key)}"
            if _mnid_scope_key in _mnid_full_data_cache:
                _ndata = _mnid_full_data_cache[_mnid_scope_key]
            elif _disk_key in _mnid_disk_cache:
                _ndata = _mnid_disk_cache[_disk_key]
                _mnid_full_data_cache[_mnid_scope_key] = _ndata
            else:
                _mnid_cols = ', '.join([
                    'person_id', 'encounter_id', 'Date', 'Program', 'Reporting_Program',
                    'Service_Area', 'Facility', 'Facility_CODE', 'District', 'Encounter',
                    'obs_value_coded', 'concept_name', 'Value', 'ValueN', 'new_revisit',
                    'Home_district', 'TA', 'Village', 'Age', 'Age_Group', 'Gender',
                    'Source_Program',
                ])
                _sql_full = f"SELECT {_mnid_cols} FROM 'data/{DATA_FILE_NAME_}'"
                _full = DataStorage.query_duckdb(_sql_full)
                _full[DATE_] = pd.to_datetime(_full[DATE_], errors='coerce')
                if level != 'National' and district_col and districts:
                    _full = _full[_full[district_col].isin(districts)]
                if level == 'Facility' and facilities:
                    _full = _full[_full[FACILITY_].isin(facilities)]
                _mnid_full_data_cache.clear()
                _mnid_full_data_cache[_mnid_scope_key] = _full
                _mnid_disk_cache.set(_disk_key, _full, expire=3600)
                _ndata = _full
        else:
            _ndata = network_data

        filtered_data_date = _fdata[
            (_fdata[DATE_] >= start_dt) &
            (_fdata[DATE_] <= end_dt)
        ]

        adj_start_dt, adj_end_dt = start_dt, end_dt
        data_period_note = None

        delta_days = (adj_end_dt - adj_start_dt).days
        facility_code_display = location
        if is_mnid:
            if len(facilities) == 1 and FACILITY_ in base_data_mnid.columns and FACILITY_CODE_ in base_data_mnid.columns:
                fac_match = base_data_mnid[base_data_mnid[FACILITY_].astype(str) == str(facilities[0])]
                if len(fac_match):
                    facility_code_display = str(fac_match[FACILITY_CODE_].dropna().astype(str).iloc[0])
                else:
                    facility_code_display = ''
            elif len(facilities) > 1 or level in ['National', 'District']:
                facility_code_display = ''
            else:
                facility_code_display = mnid_location or location

        if level == 'Facility' and facilities:
            scope_label = 'Facility' if len(facilities) == 1 else 'Facilities'
            scope_value = facilities[0] if len(facilities) == 1 else f'{len(facilities)} selected facilities'
        elif level == 'District' and facilities:
            scope_label = 'Facility' if len(facilities) == 1 else 'Facilities'
            scope_value = facilities[0] if len(facilities) == 1 else f'{len(facilities)} selected facilities'
        elif level == 'District' and districts:
            scope_label = 'District' if len(districts) == 1 else 'Districts'
            scope_value = ', '.join(districts)
        else:
            scope_label = 'Districts'
            scope_value = 'All districts'

        mnid_categories = None
        if category and category != "All":
            mnid_categories = [category]

        section = build_charts_from_json(
            filtered_data_date, _ndata, delta_days, dashboard_json,
            start_date=adj_start_dt,
            end_date=adj_end_dt,
            facility_code=facility_code_display,
            scope_meta={
                'label': scope_label,
                'value': scope_value,
                'mnid_categories': mnid_categories,
                'level': level,
                'selected_facilities': facilities,
                'selected_districts': districts,
                'data_period_note': data_period_note,
            },
        )
        rendered.append(html.Div([
            html.H2(report_name, style={"marginTop": "10px"}),
            section
        ]))

    return html.Div(rendered) if len(rendered) > 1 else (rendered[0] if rendered else html.Div("No dashboard selected."))

# Load data once to get date range
min_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
max_date = datetime.now().replace(hour=23, minute=59, second=59, microsecond=0)

path = os.getcwd()
try:
    last_refreshed = pd.read_csv(f'{path}/data/TimeStamp.csv')['saving_time'].to_list()[0]
except Exception as e:
    last_refreshed = "Unknown"


# BUILD CHARTS
PREMIUM_DASHBOARD_REPORTS = {"Maternal and Child Health"}


def build_charts_from_json(filtered, data_opd, delta_days, dashboards_json, filter_summary=None,
                          start_date=None, end_date=None, facility_code=None, scope_meta=None):
    config = dashboards_json
    count_items_per_row = config.get("count_items_per_row") or 5

    # Route MNID dashboard configs to the dedicated MNID renderer.
    if config.get('dashboard_type') == 'mnid':
        return render_mnid_dashboard(
            filtered=filtered,
            data_opd=data_opd,
            delta_days=delta_days,
            config=config,
            facility_code=facility_code or 'Unknown',
            start_date=str(start_date)[:10] if start_date else '',
            end_date=str(end_date)[:10] if end_date else '',
            scope_meta=scope_meta,
        )

    # Render all non-MNID dashboards with the generic chart builder.
    filtered = filtered.copy()
    filtered['Residence'] = filtered[HOME_DISTRICT_] + ', TA-' + filtered[TA_] + ', ' + filtered[VILLAGE_]
    delta_days = 7 if delta_days <= 0 else delta_days

    if config.get("report_name") in PREMIUM_DASHBOARD_REPORTS:
        return build_premium_dashboard(filtered, data_opd, delta_days, config, filter_summary=filter_summary)

    # Build metrics from counts section
    metrics = build_metrics_section(filtered, config["visualization_types"]["counts"])
    charts = build_charts_section(filtered, data_opd, delta_days, config["visualization_types"]["charts"]["sections"])

    return html.Div([
        html.Div(style={"display": "grid","gridTemplateColumns": f"repeat({count_items_per_row}, 1fr)",
                        "gap": "15px", "marginBottom": "30px","overflowX": "auto"}, children=metrics),
        charts
    ])

def get_relative_date_range(option):
    from datetime import datetime, timedelta
    today = datetime.today().date()
    
    if option == 'Today':
        return today, today
    elif option == 'Yesterday':
        yesterday = today - timedelta(days=1)
        return yesterday, yesterday
    elif option == 'Last 7 Days':
        start_date = today - timedelta(days=7)
        return start_date, today
    elif option == 'Last 30 Days':
        start_date = today - timedelta(days=30)
        return start_date, today
    elif option == 'This Week':
        start_date = today - timedelta(days=today.weekday())
        return start_date, today
    elif option == 'Last Week':
        start_date = today - timedelta(days=today.weekday() + 7)
        end_date = start_date + timedelta(days=6)
        return start_date, end_date
    elif option == 'This Month':
        start_date = today.replace(day=1)
        return start_date, today
    elif option == 'Last Month':
        first_day_this_month = today.replace(day=1)
        last_day_last_month = first_day_this_month - timedelta(days=1)
        start_date = last_day_last_month.replace(day=1)
        return start_date, last_day_last_month
    # option Last 3 Months
    elif option == 'Last 3 Months':
        first_day_this_month = today.replace(day=1)
        last_day_last_month = first_day_this_month - timedelta(days=1)
        first_day_last_month = last_day_last_month.replace(day=1)
        last_day_two_months_ago = first_day_last_month - timedelta(days=1)
        first_day_two_months_ago = last_day_two_months_ago.replace(day=1)
        start_date = first_day_two_months_ago
        end_date = last_day_last_month
        return start_date, end_date
    # option This Year
    elif option == 'This Year':
        start_date = today.replace(month=1, day=1)
        return start_date, today
    # option Last Year
    elif option == 'Last Year':
        first_day_this_year = today.replace(month=1, day=1)
        last_day_last_year = first_day_this_year - timedelta(days=1)
        start_date = last_day_last_year.replace(month=1, day=1)
        end_date = last_day_last_year
        return start_date, end_date

    else:
        return None, None

layout = html.Div(
    className="dashboard-layout-modern",
    children=[
        dcc.Location(id='url', refresh=False),
        dcc.Store(id='active-button-store', data='General Summary'),
        dcc.Store(id='dashboard-state-store'),
        
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
                                                        for item in ['Today', 'Yesterday', 'Last 7 Days', 'Last 30 Days',
                                                                   'This Week', 'Last Week', 'This Month', 'Last Month',
                                                                   'Last 3 Months', 'This Year', 'Last Year']
                                                    ],
                                                    value='Today',
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
                                                    initial_visible_month=datetime.now().date(),
                                                    start_date=datetime.now().replace(hour=0, minute=0, second=0, microsecond=0),
                                                    end_date=datetime.now().replace(hour=23, minute=59, second=59, microsecond=0),
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
            d["report_name"],
            className="menu-btn active" if color == d["report_name"] else "menu-btn",
            id={"type": "menu-button", "name": d["report_name"]}
        )
        for d in menu_json
    ]


@callback(
    [Output('dashboard-level-filter', 'value'),
     Output('dashboard-district-filter-group', 'style'),
     Output('dashboard-district-filter', 'options'),
     Output('dashboard-district-filter', 'value'),
     Output('dashboard-district-filter', 'disabled'),
     Output('dashboard-district-note', 'children'),
     Output('dashboard-facility-filter', 'options'),
     Output('dashboard-facility-filter', 'value')],
    [
        Input('dashboard-interval-update-today', 'n_intervals'),
        Input('dashboard-date-range-picker', 'start_date'),
        Input('dashboard-date-range-picker', 'end_date'),
        Input('dashboard-level-filter', 'value'),
        Input('dashboard-district-filter', 'value'),
        Input('dashboard-facility-filter', 'value'),
        Input('dashboard-category-filter', 'value'),
    ],
    [
        State('url-params-store', 'data'),
        State('dashboard-age-filter', 'value'),
    ],
)
def update_filter_controls(interval, start_date, end_date, level, districts, facilities, category, urlparams, age):
    try:
        state = _prepare_dashboard_state(
            start_date, end_date, level, districts, facilities, [], category,
            urlparams, age, None, None,
        )
        controls = state['controls']
        return (
            controls['level'],
            controls['district_group_style'],
            controls['district_options'],
            controls['districts'],
            controls['district_disabled'],
            controls['district_note'],
            controls['facility_options'],
            controls['facilities'],
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return (
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
    [Output('dashboard-state-store', 'data'),
     Output('active-button-store', 'data')],
    [
        Input('dashboard-btn-generate', 'n_clicks'),
        Input('dashboard-interval-update-today', 'n_intervals'),
        Input('dashboard-date-range-picker', 'start_date'),
        Input('dashboard-date-range-picker', 'end_date'),
        Input('dashboard-overview-filter', 'value'),
        Input('dashboard-category-filter', 'value'),
        Input({"type": "menu-button", "name": ALL}, "n_clicks"),
    ],
    [
        State('dashboard-level-filter', 'value'),
        State('dashboard-district-filter', 'value'),
        State('dashboard-facility-filter', 'value'),
        State('url-params-store', 'data'),
        State('dashboard-age-filter', 'value'),
        State('active-button-store', 'data')
    ],
)
def update_dashboard_state(gen, interval, start_date, end_date, overview, category, menu_clicks, level, districts, facilities, urlparams, age, current_active):
    try:
        ctx = callback_context
        triggered_id = ctx.triggered[0]['prop_id'] if ctx.triggered else None
        state = _prepare_dashboard_state(
            start_date, end_date, level, districts, facilities, overview, category,
            urlparams, age, current_active, triggered_id,
        )
        controls = state['controls']
        state_key = _remember_dashboard_state(state)
        return state_key, controls['active_button']
    except Exception as e:
        import traceback
        traceback.print_exc()
        return dash.no_update, dash.no_update


@callback(
    Output('dashboard-container', 'children'),
    Input('dashboard-state-store', 'data'),
)
def render_dashboard(state_key):
    try:
        return _render_dashboard_from_state(_load_dashboard_state(state_key))
    except Exception as e:
        import traceback
        traceback.print_exc()
        return _build_error_div("Dashboard render failed.", str(e))

@callback(
    [Output('dashboard-date-range-picker', 'start_date'),
     Output('dashboard-date-range-picker', 'end_date'),
     Output('dashboard-date-range-picker', 'initial_visible_month')],
    [Input('dashboard-period-type-filter', 'value'),
     Input('dashboard-interval-update-today', 'n_intervals')],
    [State('dashboard-date-range-picker', 'start_date'),
     State('dashboard-date-range-picker', 'end_date')],
)
def sync_picker_with_logic(period_type, n, current_start_date, current_end_date):
    ctx = callback_context
    triggered_id = ctx.triggered[0]['prop_id'] if ctx.triggered else ""

    if "dashboard-interval-update-today" in triggered_id:
        if period_type == "Today":
            today = datetime.now().date()
            return today, today, today.replace(day=1)
        raise PreventUpdate
    if period_type:
        s, e = get_relative_date_range(period_type)
        if s and e:
            return s, e, s.replace(day=1)
    if current_start_date and current_end_date:
        start_date = pd.to_datetime(current_start_date).date()
        end_date = pd.to_datetime(current_end_date).date()
        return start_date, end_date, start_date.replace(day=1)
    today = datetime.now().date()
    return today, today, today.replace(day=1)


@callback(
    Output('dashboard-period-type-filter', 'value', allow_duplicate=True),
    Input('dashboard-date-range-picker', 'start_date'),
    Input('dashboard-date-range-picker', 'end_date'),
    State('dashboard-period-type-filter', 'value'),
    prevent_initial_call=True,
)
def clear_relative_period_on_custom_dates(start_date, end_date, period_type):
    ctx = callback_context
    triggered_id = ctx.triggered[0]['prop_id'] if ctx.triggered else ""
    if "dashboard-date-range-picker" not in triggered_id:
        raise PreventUpdate
    if not start_date or not end_date or not period_type:
        raise PreventUpdate

    expected_start, expected_end = get_relative_date_range(period_type)
    if not expected_start or not expected_end:
        raise PreventUpdate

    chosen_start = pd.to_datetime(start_date).date()
    chosen_end = pd.to_datetime(end_date).date()
    if chosen_start == expected_start and chosen_end == expected_end:
        raise PreventUpdate
    return None

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
    # Setting period to "Today" triggers the callback in Step 1
    return 'Today', None, [], [], [], "All", None

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
