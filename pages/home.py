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
from helpers import build_charts_section, build_metrics_section
from mnid_renderer import render_mnid_dashboard
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

# Load data once to get date range
min_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
max_date = datetime.now().replace(hour=23, minute=59, second=59, microsecond=0)

path = os.getcwd()
try:
    last_refreshed = pd.read_csv(f'{path}/data/TimeStamp.csv')['saving_time'].to_list()[0]
except Exception as e:
    last_refreshed = "Unknown"


# BUILD CHARTS
def build_charts_from_json(filtered, data_opd, delta_days, dashboards_json,
                           start_date=None, end_date=None, facility_code=None):
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
        )

    # Render all non-MNID dashboards with the generic chart builder.
    filtered = filtered.copy()
    filtered['Residence'] = filtered[HOME_DISTRICT_] + ', TA-' + filtered[TA_] + ', ' + filtered[VILLAGE_]
    delta_days = 7 if delta_days <= 0 else delta_days

    metrics = build_metrics_section(filtered, config["visualization_types"]["counts"])
    charts  = build_charts_section(filtered, data_opd, delta_days,
                                    config["visualization_types"]["charts"]["sections"])
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
    else:
        return None, None

layout = html.Div(className="container", children=[
    dcc.Location(id='url', refresh=False),
    dcc.Store(id='active-button-store', data='home'),
    html.Div([
        html.Div(
            [
                html.Button(item, className="menu-btn")
                for item in []
                ],
                className="horizontal-scroll",
                id="scrolling-menu"
            ),
        html.Div(className="filter-container", children=[
            html.Div([
                html.Label("Relative Period"),
                dcc.Dropdown(
                    id='dashboard-period-type-filter',
                    options=[
                        {'label': item, 'value': item}
                        for item in ['Today', 'Yesterday', 'Last 7 Days', 'Last 30 Days','This Week','Last Week', 'This Month', 'Last Month']
                    ],
                    value='Today',
                    clearable=True
                )
            ], className="filter-input"),

            html.Div([
                html.Label("Custom Date Range"),
                dcc.DatePickerRange(
                    id='dashboard-date-range-picker',
                    min_date_allowed="2023-01-01",
                    max_date_allowed="2050-01-01",
                    initial_visible_month=datetime.now(),
                    start_date=datetime.now().replace(hour=0, minute=0, second=0, microsecond=0),
                    end_date=datetime.now().replace(hour=23, minute=59, second=59, microsecond=0),
                    display_format='YYYY-MM-DD',
                )
            ], className="filter-input"),

            html.Div([
                html.Label("Health Facility"),
                dcc.Dropdown(
                    id='dashboard-hf-filter',
                    options=[
                        {'label': hf, 'value': hf}
                        for hf in []
                    ],
                    value=None,
                    clearable=True
                )
            ], className="filter-input"),

            html.Div([
                html.Label("Age Group"),
                dcc.Dropdown(
                    id='dashboard-age-filter',
                    options=[
                        {'label': age, 'value': age}
                        for age in ['Over 5','Under 5']
                    ],
                    value=None,
                    clearable=True
                )
            ], className="filter-input"),

            html.Div(
                    children=[
                        html.Button("Apply", id="dashboard-btn-generate", n_clicks=0, className="btn btn-primary"),
                        html.Button("Reset", id="dashboard-btn-reset", n_clicks=0, className="btn btn-secondary"),
                    ],
                    style={"display": "flex", "gap": "10px", "margin-bottom": "10px"}
                ),
        ]),

]),
    html.Div(id='dashboard-container'),   
    dcc.Interval(
        id='dashboard-interval-update-today',
        interval=10*60*1000,  # in milliseconds
        n_intervals=0
    ),     
])

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
     Output('dashboard-hf-filter', 'options'),
     Output('dashboard-hf-filter', 'value'),
     Output('active-button-store', 'data')],
    [
        Input('dashboard-btn-generate', 'n_clicks'),
        Input('dashboard-interval-update-today', 'n_intervals'),
        Input('dashboard-date-range-picker', 'start_date'), # New: Update when dates settle
        Input('dashboard-date-range-picker', 'end_date'),   # New: Update when dates settle
        Input({"type": "menu-button", "name": ALL}, "n_clicks"),
    ],
    [
        State('url-params-store', 'data'),
        State('dashboard-hf-filter', 'value'),
        State('dashboard-age-filter', 'value'),
        State('active-button-store', 'data')
    ]
)
def update_dashboard(gen, interval, start_date, end_date, menu_clicks, urlparams, hf, age, current_active):
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

        # Get JSON config for the report before loading data.
        with open(json_path, 'r') as f:
            menu_json = json.load(f)
        dashboard_json = next((d for d in menu_json if d['report_name'] == clicked_name), menu_json[0])
        is_mnid = dashboard_json.get('dashboard_type') == 'mnid'

        if urlparams.get('Location', [None])[0]:
            location = urlparams.get('Location', [None])[0]
        else:
            location = "LL040033"

        # Load Data
        if is_mnid:
            SQL = f"""
                SELECT *
                FROM 'data/{DATA_FILE_NAME_}'
                WHERE Date >= '{start_dt}'
                AND Date <= '{end_dt}'
                AND (
                    Program ILIKE '%Maternal%'
                    OR Program ILIKE '%Neonatal%'
                )
                """
        else:
            SQL = f"""
                SELECT *
                FROM 'data/{DATA_FILE_NAME_}'
                WHERE Date >= '{last_7_days}'
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
        data[GENDER_] = data[GENDER_].replace({"M":"Male","F":"Female"})
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
            return html.Div("Unauthorized User. Please contact system administrator."), no_update,no_update, clicked_name

        if is_mnid:
            network_mask = pd.Series(True, index=data.index)
            if age:
                network_mask &= (data[AGE_GROUP_] == age)
            network_data = data[network_mask].copy()

            facility_mask = pd.Series(True, index=network_data.index)
            facility_mask &= (network_data[FACILITY_CODE_] == location)
            if hf and hf != "This Facility":
                facility_mask &= (network_data[FACILITY_] == hf)
            filtered_data = network_data[facility_mask].copy()
            filtered_data_date = filtered_data[
                (filtered_data[DATE_] >= start_dt) &
                (filtered_data[DATE_] <= end_dt)
            ]
        else:
            # Apply Dropdown Filters
            mask = pd.Series(True, index=data.index)
            # if hf:
            #     mask &= (data[FACILITY_] == hf)
            if age:
                mask &= (data[AGE_GROUP_] == age)

            filtered_data = data[mask].copy()

            # Apply Date Mask
            filtered_data_date = filtered_data[
                (filtered_data[DATE_] >= start_dt) &
                (filtered_data[DATE_] <= end_dt)
            ]
            network_data = filtered_data

        delta_days = (end_dt - start_dt).days
        hf_values = filtered_data[FACILITY_].dropna().sort_values().unique().tolist() if FACILITY_ in filtered_data.columns else []
        hf_options = hf_values + (["This Facility"] if "This Facility" not in hf_values else [])
        hf_value = hf_options[0] if hf_options else None

        return build_charts_from_json(
            filtered_data_date, network_data, delta_days, dashboard_json,
            start_date=start_dt, end_date=end_dt, facility_code=location,
        ), hf_options, hf_value, clicked_name
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
     Output('dashboard-hf-filter', 'value', allow_duplicate=True),
     Output('dashboard-age-filter', 'value', allow_duplicate=True)],
    Input('dashboard-btn-reset', 'n_clicks'),
    prevent_initial_call=True
)
def reset_ui_controls(n_clicks):
    # Setting period to "Today" triggers the callback in Step 1
    return 'Today', None, None

@callback(
    [Output('dashboard-period-type-filter', 'style'),
     Output('dashboard-date-range-picker', 'style', allow_duplicate=True),
     Output('dashboard-hf-filter', 'style'),
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
        return style_active, style_active, style_active, style_active
    else:
        style_default = {}
        return style_default,style_default,style_default, style_default,
