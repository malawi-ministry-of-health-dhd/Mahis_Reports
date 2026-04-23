import dash
from dash import html, dcc, Input, Output, callback, State, no_update, ALL, callback_context
import pandas as pd
import plotly.express as px
import os
import json
import numpy as np
from dash.exceptions import PreventUpdate
import os
import traceback
from helpers.helpers import build_single_chart
from datetime import datetime, timedelta
from data_storage import DataStorage
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

from helpers.navigation_callbacks import DEMO_UUID

dash.register_page(__name__, path="/program_reports")
# data = pd.read_parquet('data/latest_data_opd.parquet')

from datetime import datetime, timedelta
from dash import html, dcc

path = os.getcwd()
path_program_reports = os.path.join(path, 'data','visualizations','validated_prog_reports.json')
dropdowns_json_path = os.path.join(path, 'data', 'dcc_dropdown_json', 'dropdowns.json') 


report_config_panel = html.Div(
    className="report-config-modern",
    children=[
        dcc.Store(id="report-config-store"),
        
        # Parameters Card
        html.Div(
            className="config-parameters-card",
            children=[
                html.H3("Generate a Programs Report", className="config-parameters-title"),
                
                # Controls Grid
                html.Div(
                    className="config-controls-grid",
                    children=[
                        # Program Selector
                        html.Div(
                            className="config-control-group",
                            children=[
                                html.Label("Select Program", className="config-label"),
                                dcc.Dropdown(
                                    id="program-selector",
                                    options=[{"label": p, "value": p} for p in []],
                                    placeholder="Choose a program…",
                                    value="OPD Program",
                                    clearable=True,
                                    className="modern-dropdown"
                                ),
                            ]
                        ),
                        
                        # Report Selector
                        html.Div(
                            className="config-control-group",
                            children=[
                                html.Label("Select Report", className="config-label"),
                                dcc.Dropdown(
                                    id="report-selector",
                                    options=[{"label": r, "value": r} for r in []],
                                    placeholder="Choose a report…",
                                    value=None,
                                    clearable=True,
                                    className="modern-dropdown"
                                ),
                            ]
                        ),
                        
                        # Date Range Picker
                        html.Div(
                            className="config-control-group",
                            children=[
                                html.Label("Date Range", className="config-label"),
                                dcc.DatePickerRange(
                                    id="prog-date-range-picker",
                                    min_date_allowed="2023-01-01",
                                    max_date_allowed=datetime.now(),
                                    initial_visible_month=datetime.now(),
                                    start_date=datetime.now().replace(hour=0, minute=0, second=0, microsecond=0),
                                    end_date=datetime.now().replace(hour=23, minute=59, second=59, microsecond=0),
                                    display_format='YYYY-MM-DD',
                                    minimum_nights=0,
                                    className="modern-datepicker-range",
                                    style={
                                        "width": "100%",
                                        "border": "1px solid #ced4da",
                                        "borderRadius": "10px",
                                        "padding": "8px"
                                    }
                                ),
                            ]
                        ),
                        
                        # Health Facility Filter
                        html.Div(
                            className="config-control-group",
                            children=[
                                html.Label("Health Facility", className="config-label"),
                                dcc.Dropdown(
                                    id="prog-hf-filter",
                                    options=[],
                                    placeholder="All facilities",
                                    value=None,
                                    clearable=True,
                                    multi=True,
                                    className="modern-dropdown"
                                ),
                            ]
                        ),
                    ]
                ),
                
                # Action Buttons
                html.Div(
                    className="config-actions",
                    children=[
                        # Left Actions
                        html.Div(
                            className="config-left-actions",
                            children=[
                                html.Button(
                                    "Generate Report",
                                    id="btn-generate-report",
                                    n_clicks=0,
                                    className="btn-generate-modern"
                                ),
                                html.Button(
                                    "Reset",
                                    id="btn-reset-report",
                                    n_clicks=0,
                                    className="btn-reset-modern"
                                ),
                            ]
                        ),
                        
                        # Right Actions
                        html.Div(
                            className="config-right-actions",
                            children=[
                                html.Button(
                                    "CSV",
                                    id="btn-csv",
                                    n_clicks=0,
                                    className="btn-download-csv"
                                ),
                                html.Button(
                                    "XLSX",
                                    id="btn-excel",
                                    n_clicks=0,
                                    className="btn-download-excel"
                                ),
                                html.Button(
                                    "PNG",
                                    id="btn-png",
                                    n_clicks=0,
                                    className="btn-download-png"
                                ),
                                html.Span(
                                    id="report-run-status",
                                    className="run-status-modern",
                                    style={"marginLeft": "10px"}
                                )
                            ]
                        ),
                    ]
                )
            ]
        ),
        
        # Loading and Output Container
        dcc.Loading(
            id="reports-loading",
            type="circle",
            color="#006401",
            children=html.Div(
                id="reports-output",
                className="reports-output-container"
            )
        ),
    ],
    style={"marginTop": "0px"}
)

def programs_report(data, programs_report_list, user_role):
    if len(programs_report_list) == 0:
        return html.Div('')
    else:
        json_data = programs_report_list[0]
        return html.Div(
                    build_single_chart(data, data, 10, json_data, user_role, style="")
            )


layout = html.Div(
    html.Div(children=[
            report_config_panel,
            html.Div(id='program-reports-container'),
            dcc.Interval(
                    id='prog-interval-update-today',
                    interval=60*60*1000,  # in milliseconds
                    n_intervals=0,
                ),
    ],style={"marginTop":"30px","backgroundColor":"white","border-radius":"4px","border":"1px","border-color":"black"})
        
)

@callback(
         [Output("report-selector", "options"),
          Output("report-selector", "value")],
         Input("program-selector","value")
)

def update_filters(selected_program):
    with open(path_program_reports) as x:
        program_reports_data = json.load(x)
    filtered_reports_list = [r for r in program_reports_data["reports"] if r.get("program") == selected_program or selected_program in (r.get("programs") or [])]
    filtered_object = {"reports":filtered_reports_list}
    program_reports = [x['report_name'] for x in filtered_object['reports']]
    default_report = program_reports[0] if program_reports else None
    return program_reports, default_report 

@callback(
    [Output('program-reports-container', 'children'),
     Output('prog-hf-filter', 'options'),
     Output("program-selector", "options")],
    [Input("btn-generate-report", "n_clicks"),
     Input('url-params-store', 'data'),
     Input("report-selector", "value")], # Only these trigger the update
    [State("report-selector", "value"),
     State('prog-date-range-picker', 'start_date'),
     State('prog-date-range-picker', 'end_date'),
     State('prog-hf-filter', 'value')] # These are read only when Input triggers
)
def generate_chart(n_clicks, urlparams, selected_report, report_name, start_date, end_date, hf):
    user_data_path = os.path.join(path, 'data', 'users_data.csv')
    if not os.path.exists(user_data_path):
        user_data = pd.DataFrame(columns=['user_id', 'role'])
    else:
        user_data = pd.read_csv(os.path.join(path, 'data', 'users_data.csv'))
    test_admin = pd.DataFrame(columns=['user_id', 'role'], data=[[DEMO_UUID, 'reports_admin']])
    user_data = pd.concat([user_data, test_admin], ignore_index=True)

    user_info = user_data[user_data['user_id'] == urlparams.get('uuid', [None])[0]]
    if user_info.empty:
        return html.Div("Unauthorized User. Please contact system administrator."), no_update,no_update
    user_role = user_info['role'].to_list()
    if user_role:
        role = user_role[0]
    else:
        role = None

    ctx = callback_context
    triggered_id = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else None

    if triggered_id == "btn-generate-report.n_clicks" and n_clicks is None:
        return no_update, no_update, no_update

    try:
        start_dt = pd.to_datetime(start_date).replace(hour=0, minute=0, second=0)
        end_dt = pd.to_datetime(end_date).replace(hour=23, minute=59, second=59)

        if urlparams.get('Location', [None])[0]:
            location = urlparams.get('Location', [None])[0]
        else:
            return html.Div("Missing Parameters"), no_update, no_update


        SQL = f"""
                SELECT * FROM 'data/{DATA_FILE_NAME_}'
                WHERE Date BETWEEN '{start_dt}' AND '{end_dt}'
                AND {FACILITY_CODE_} = '{location}'
               """
        try:
            data = DataStorage.query_duckdb(SQL)
        except Exception as e:
            return html.Div('Missing Data. ' \
            'Ensure that the config file has correct database credentials'
            ,style={'color':'red'}), [], ''  # Empty DataFrame with expected columns
        
        data[DATE_] = pd.to_datetime(data[DATE_], format='mixed').dt.strftime('%Y-%m-%d')
        data[GENDER_] = data[GENDER_].replace({"M":"Male",
                                               "F":"Female",
                                               '{"label"=>"Male", "value"=>"M"}':"Male",
                                               '{"label"=>"Female", "value"=>"F"}':"Female"})
        data["DateValue"] = pd.to_datetime(data[DATE_]).dt.date

        # if data.empty:
        #     return html.Div("No data found for these dates."), [], []

        #Dropdown Logic (Calculate once)
        facilities = sorted(data[FACILITY_].dropna().unique().tolist())
        hf_options = facilities + (["*All health facilities"] if len(facilities) > 1 else [])

        # get list of programs for dropdowns.json
        with open(dropdowns_json_path) as x:
            dropdowns = json.load(x)

        prog_options = dropdowns['programs'] + ["+ Create a Report"]

        #Chart Generation Logic (Only if Button clicked or specific report selected)
        report_name = report_name or selected_report

        if not report_name:
             return html.Div("Please select a report name and click Generate."), hf_options, prog_options

        #Filter by Facility Selection
        if hf and hf != "*All health facilities":
            hf_list = hf if isinstance(hf, list) else [hf]
            data = data[data['Facility'].isin(hf_list)]

        if data.empty:
            return html.Div("No data for selected facility."), hf_options, prog_options

        #Get Config and Render
        with open(path_program_reports) as x:
            config = json.load(x)
        report_cfg = [r for r in config.get("reports", []) if r.get("report_name") == report_name]
        return programs_report(data, report_cfg, role), hf_options, prog_options

    except Exception as e:
        traceback.print_exc()
        return html.Div(f"Error: {str(e)}"), hf_options, prog_options
    
@callback(
    [Output('prog-date-range-picker', 'start_date'),
     Output('prog-date-range-picker', 'end_date')],
    Input('prog-interval-update-today', 'n_intervals')
)
def update_date_range(n):
    today = datetime.now()
    start = today.replace(hour=0, minute=0, second=0, microsecond=0)
    end = today.replace(hour=23, minute=59, second=59, microsecond=0)
    return start, end
