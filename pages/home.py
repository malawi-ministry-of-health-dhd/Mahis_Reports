import dash
from dash import html, dcc, Input, Output, callback, State, no_update, ALL, callback_context
import pandas as pd
import plotly.express as px
import os
import json
import numpy as np
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
    charts  = build_charts_section(filtered, data_opd, delta_days,
                                    config["visualization_types"]["charts"]["sections"])

    # Build charts from sections
    charts = build_charts_section(filtered, data_opd, delta_days, config["visualization_types"]["charts"]["sections"])

    return html.Div([
        html.Div(className="card-container-5", children=metrics),
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
                                                    initial_visible_month=datetime.now(),
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
                html.Div(
                    id='dashboard-container',
                    className="dashboard-content-modern"
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
        Input('dashboard-interval-update-today', 'n_intervals'),
        Input('dashboard-date-range-picker', 'start_date'), # New: Update when dates settle
        Input('dashboard-date-range-picker', 'end_date'),   # New: Update when dates settle
        Input('dashboard-level-filter', 'value'),
        Input('dashboard-district-filter', 'value'),
        Input('dashboard-facility-filter', 'value'),
        Input('dashboard-overview-filter', 'value'),
        Input('dashboard-category-filter', 'value'),
        Input({"type": "menu-button", "name": ALL}, "n_clicks"),
    ],
    [
        State('url-params-store', 'data'),
        State('dashboard-age-filter', 'value'),
        State('active-button-store', 'data')
    ]
)
def update_dashboard(gen, interval, start_date, end_date, level, districts, facilities, overview, category, menu_clicks, urlparams, age, current_active):
    try:
        ctx = callback_context
        triggered_id = ctx.triggered[0]['prop_id'] if ctx.triggered else None

        if not urlparams:
            urlparams = {"Location": ["LL040033"], "uuid": ["m3his@dhd"]}
        if not urlparams.get("Location"):
            urlparams["Location"] = ["LL040033"]
        if not urlparams.get("uuid"):
            urlparams["uuid"] = ["m3his@dhd"]


        # Determine which report to show
        clicked_name = current_active
        if triggered_id and "menu-button" in triggered_id:
            prop_dict = json.loads(triggered_id.split('.')[0])
            clicked_name = prop_dict['name']

        # Date Logic
        start_dt = pd.to_datetime(start_date).replace(hour=0, minute=0, second=0)
        end_dt = pd.to_datetime(end_date).replace(hour=23, minute=59, second=59)
        last_7_days = start_dt - pd.Timedelta(days=7)

        if urlparams.get('Location', [None])[0]:
            location = urlparams.get('Location', [None])[0]
        else:
            location = "LL040033"
        mnid_location = urlparams.get('Location', [None])[0] if urlparams.get('Location') else None

        user_levels = ['national', 'district']
        user_level = urlparams.get('user_level', [None])[0]

        # Default level based on user_level
        if not level:
            if user_level == 'national':
                level = 'National'
            elif user_level == 'district':
                level = 'District'
            else:
                level = 'Facility'
        
        if level in ['National', 'District']:
            SQL = f"""
                SELECT *
                FROM 'data/{DATA_FILE_NAME_}'
                WHERE Date >= TIMESTAMP '{last_7_days}'
                """
        elif user_level in user_levels:
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
            import traceback
            traceback.print_exc()
            return html.Div('Missing Data. ' \
            'Ensure that the config file has correct database credentials'
            ,style={'color':'red'}), [], '', ''  # Empty DataFrame with expected columns

        data[DATE_] = pd.to_datetime(data[DATE_], format='mixed')
        data[GENDER_] = data[GENDER_].replace({"M":"Male",
                                               "F":"Female",
                                               '{"label"=>"Male", "value"=>"M"}':"Male",
                                               '{"label"=>"Female", "value"=>"F"}':"Female"})
        data["DateValue"] = pd.to_datetime(data[DATE_]).dt.date
        today = dt.today().date()
        data["months"] = data["DateValue"].apply(lambda d: (today - d).days // 30)

        # get user
        user_data_path = os.path.join(path, 'data', 'users_data.csv')
        if not os.path.exists(user_data_path):
            user_data = pd.DataFrame(columns=['user_id', 'role'])
        else:
            user_data = pd.read_csv(os.path.join(path, 'data', 'users_data.csv'))
        test_admin = pd.DataFrame(columns=['user_id', 'role'], data=[['m3his@dhd', 'reports_admin']])
        user_data = pd.concat([user_data, test_admin], ignore_index=True)

        user_info = user_data[user_data['user_id'] == urlparams.get('uuid', [None])[0]]
        if user_info.empty:
            return (
                html.Div("Unauthorized User. Please contact system administrator."),
                level,
                {'display': 'none'} if level in ['National', 'Facility'] else {},
                [],
                [],
                False,
                "",
                [],
                [],
                clicked_name
            )

        # Base filters (age + MNID program category)
        base_mask = pd.Series(True, index=data.index)
        if age:
            base_mask &= (data[AGE_GROUP_] == age)
        category = category or "All"
        if category != "All" and "Encounter" in data.columns:
            if category == "ANC":
                base_mask &= data["Encounter"].fillna('').astype(str).str.contains('ANC', case=False, na=False)
            elif category == "Labour":
                base_mask &= data["Encounter"].fillna('').astype(str).str.contains('LABOUR|DELIVERY|BIRTH', case=False, na=False)
            elif category == "PNC":
                base_mask &= data["Encounter"].fillna('').astype(str).str.contains('PNC|POSTNATAL|POST.NATAL', case=False, na=False)
        base_data = data[base_mask].copy()

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

        # Facility options based on selected districts
        if level == "National":
            facilities_pool = base_data
        elif level == "District" and district_col and not districts:
            facilities_pool = base_data
        elif district_col and districts:
            facilities_pool = base_data[base_data[district_col].isin(districts)]
        else:
            facilities_pool = base_data
        all_facilities = (
            facilities_pool[FACILITY_].dropna().sort_values().unique().tolist()
            if FACILITY_ in facilities_pool.columns else []
        )

        # Enforce facility -> district constraint
        if district_col and facilities:
            facility_districts = (
                base_data[base_data[FACILITY_].isin(facilities)][district_col]
                .dropna()
                .unique()
                .tolist()
            )
        else:
            facility_districts = []

        show_district_filter = level == "District"
        district_group_style = {} if show_district_filter else {"display": "none"}
        district_disabled = not show_district_filter
        district_note = ""
        if not show_district_filter:
            districts = []

        # Keep selected facilities consistent with selected districts
        if district_col and districts:
            allowed_facilities = set(
                base_data[base_data[district_col].isin(districts)][FACILITY_]
                .dropna()
                .unique()
                .tolist()
            )
            facilities = [f for f in facilities if f in allowed_facilities]
            all_facilities = sorted(allowed_facilities)

        # Filter network and facility data
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

        # Determine report selection
        menu_json = load_dashboard_menu()
        if overview:
            selected_reports = overview
        else:
            selected_reports = [clicked_name] if clicked_name else [menu_json[0]["report_name"] if menu_json else "Dashboard"]
        selected_reports = [normalize_report_name(r, menu_json) for r in selected_reports]

        rendered = []
        for report_name in selected_reports:
            dashboard_json = next((d for d in menu_json if d['report_name'] == report_name), None)
            if not dashboard_json:
                continue
            is_mnid = dashboard_json.get('dashboard_type') == 'mnid'

            filtered_data_date = filtered_data[
                (filtered_data[DATE_] >= start_dt) &
                (filtered_data[DATE_] <= end_dt)
            ]
            adj_start_dt, adj_end_dt = start_dt, end_dt
            if is_mnid and filtered_data_date.empty and len(filtered_data):
                adj_start_dt = filtered_data[DATE_].min()
                adj_end_dt = filtered_data[DATE_].max()
                filtered_data_date = filtered_data.copy()

            delta_days = (adj_end_dt - adj_start_dt).days
            facility_code_display = location
            if is_mnid:
                if len(facilities) == 1 and FACILITY_ in base_data.columns and FACILITY_CODE_ in base_data.columns:
                    fac_match = base_data[base_data[FACILITY_].astype(str) == str(facilities[0])]
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
                filtered_data_date, network_data, delta_days, dashboard_json,
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
                },
            )
            rendered.append(html.Div([
                html.H2(report_name, style={"marginTop": "10px"}),
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
    except Exception as e:
        import traceback
        traceback.print_exc()
        return (
            html.Div([
                html.P("Dashboard render failed.", style={"color": "#475569", "fontWeight": "600"}),
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

    if "dashboard-interval-update-today" in triggered_id:
        if period_type == "Today":
            today = datetime.now().date()
            return today, today
        raise PreventUpdate
    if period_type:
        s, e = get_relative_date_range(period_type)
        if s and e:
            return s, e
    today = datetime.now().date()
    return today, today

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
    Input({"type": "menu-button", "name": ALL}, "n_clicks"),
    State('active-button-store', 'data'),
)
def toggle_age_group_visibility(menu_clicks, active_report):
    report = str(active_report or '').strip().lower()
    ctx = callback_context
    if ctx.triggered:
        trigger = ctx.triggered[0].get('prop_id', '')
        if trigger.startswith('{') and '"type":"menu-button"' in trigger:
            try:
                report = str(json.loads(trigger.split('.')[0]).get('name', report)).strip().lower()
            except Exception:
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
