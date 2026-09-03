import dash
from dash import html, dcc, Input, Output, callback, State, no_update, ALL, callback_context
import pandas as pd
import plotly.express as px
import os
import json
import io
import numpy as np
from dash.exceptions import PreventUpdate
import os
import traceback
from helpers.helpers import (build_single_chart, 
                             create_pivot_table_from_config, 
                             create_linelist_from_config,
                             create_crosstab_from_config)
from datetime import datetime, timedelta
from data_storage import DataStorage
import warnings
warnings.filterwarnings("ignore")
from config import (actual_keys_in_data,
                    DATA_PATH_,
                    DATE_, PERSON_ID_, ENCOUNTER_ID_,
                    FACILITY_, AGE_GROUP_, AGE_,
                    GENDER_, ENCOUNTER_, PROGRAM_,
                    DEMO_LOCATION,DEMO_UUID,
                    NEW_REVISIT_,DISTRICT_,
                    HOME_DISTRICT_,FACILITY_CODE_,
                    TA_,
                    VILLAGE_,
                    OBS_VALUE_CODED_,
                    CONCEPT_NAME_,
                    VALUE_,
                    VALUE_NUMERIC_,
                    DRUG_NAME_,
                    VALUE_NAME_)


dash.register_page(__name__, path="/program_reports")

pd.options.mode.chained_assignment = None

from datetime import datetime, timedelta
from dash import html, dcc

path = os.getcwd()
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

def _scope_where_parts(effective_level, location, districts, user_districts, facilities, age, programs=None, is_network=False):
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
    if programs:
        quoted_programs = ", ".join([f"'{p}'" for p in programs])
        parts.append(f"{PROGRAM_} IN ({quoted_programs})")
    return parts

def _load_user_properties(route) -> list:
    props_path = os.path.join(os.getcwd(), f'data/{route}', 'dcc_dropdown_json', 'user_properties.json')
    try:
        with open(props_path) as f:
            return json.load(f).get('users', [])
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return []

def _normalize_level(value: str | None) -> str:
    value = str(value or '').strip().lower()
    if value in {'national', 'district', 'facility'}:
        return value
    return 'facility'


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
                'facility_code': p.get('facility_code'),
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
        'facility_code': row.get('facility_code'),
    }
    return row, scope

report_config_panel = html.Div(
    className="report-config-modern",
    children=[
        dcc.Store(id="report-config-store"),
        
        # Parameters Card
        html.Div(
            className="config-parameters-card",
            children=[
                # html.H3("Generate a Clinical Report", className="config-parameters-title"),
                
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
                                    # className="modern-datepicker-range",
                                    style={
                                        "width": "100%",
                                        "border": "1px solid #ced4da",
                                        "borderRadius": "10px",
                                        "padding": "2px"
                                    }
                                ),
                            ]
                        ),
                        
                        # Health Facility Filter
                        html.Div(
                            id="prog-hf-filter-group",
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
                                    disabled=True,
                                    title="Available for Pivot Table and Cross Tab reports",
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
        dcc.Store(id="prog-report-export-store"),
        dcc.Download(id="download-prog-report"),
    ],
    style={"marginTop": "0px"}
)

def programs_report(filtered_query,data_route, programs_report_list, user_role):
    """Render a single program report chart from a SQL WHERE-clause string.

    Returns (component, export_df) -- export_df is the underlying DataFrame
    for PivotTable/CrossTab reports (the only types the XLSX button supports
    downloading for now), otherwise None.
    """
    if not programs_report_list:
        return html.Div(''), None
    json_data = programs_report_list[0]
    chart_type = json_data.get("type")
    filters = json_data.get("filters", {})

    if chart_type == "PivotTable":
        table, data = create_pivot_table_from_config(filtered_query, data_route, filters)
        return html.Div(table), data
    if chart_type == "CrossTab":
        table, data = create_crosstab_from_config(filtered_query, data_route, filters)
        return html.Div(table), data
    # if chart_type == "LineList":
    #     table, data = create_linelist_from_config(filtered_query, data_route, filters)
    #     return html.Div(table), data

    return html.Div(
        build_single_chart(filtered_query, filtered_query, 10, data_route, json_data, user_role, style="")
    ), None


layout = html.Div(
    html.Div(children=[
            dcc.Location(id='url', refresh=False),
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
    path_program_reports = os.path.join(path, 'data','visualizations','validated_prog_reports.json')
    program_reports_progs_path = os.path.join(path, f'data/validated_prog_reports.json')
    with open(path_program_reports) as x:
        program_reports_data = json.load(x)
    filtered_reports_list = [r for r in program_reports_data["reports"] if r.get("program") == selected_program or selected_program in (r.get("programs") or [])]
    filtered_object = {"reports":filtered_reports_list}
    program_reports = [x['report_name'] for x in filtered_object['reports']]
    default_report = program_reports[0] if program_reports else None
    return program_reports, ""

@callback(
    [Output('prog-hf-filter', 'options'),
     Output('prog-hf-filter', 'value'),
     Output('prog-hf-filter-group', 'style')],
    Input('url-params-store', 'data'),
)
def load_program_report_facilities(urlparams):
    """Health Facility filter, scoped like reports.py's own facility-filter:
    national users pick from every facility, district users pick from their
    own district(s)' facilities, and facility-level users don't get a choice
    at all -- the control is hidden and pinned to their one facility."""
    urlparams = urlparams or {}
    data_route = urlparams.get('route', ["default"])[0]
    user_data = _load_user_registry(data_route)
    user_row, scope = _resolve_user_scope(urlparams, user_data)
    if user_row is None:
        return [], None, {'display': 'none'}

    level = scope.get('level')

    assigned = scope.get('facilities')
    if isinstance(assigned, str):
        assigned = [assigned] if assigned else []
    assigned = assigned or []

    if level == 'facility':
        return assigned, (assigned or None), {'display': 'none'}

    facilities_path = os.path.join(path, f'data/{data_route}', 'dcc_dropdown_json', 'facilities_dropdowns.json')
    try:
        with open(facilities_path, 'r') as f:
            facilities_by_district = json.load(f)
    except Exception:
        facilities_by_district = {}

    if level == 'national':
        hf = [f for values in facilities_by_district.values() if isinstance(values, list) for f in values]
        return hf, None, {}

    # district level -- facilities within the user's own district(s), falling
    # back to any explicitly-assigned facility list if that lookup is empty.
    user_districts = scope.get('districts') or []
    if isinstance(user_districts, str):
        user_districts = [user_districts]
    hf = [f for d in user_districts for f in (facilities_by_district.get(d) or [])]
    return (hf or assigned), None, {}

@callback(
    [Output('program-reports-container', 'children'),
     Output("program-selector", "options"),
     Output("btn-generate-report", "n_clicks"),
     Output("prog-report-export-store", "data"),
     Output("btn-excel", "disabled")],
    [Input("btn-generate-report", "n_clicks"),
     Input('url-params-store', 'data'),
     Input("report-selector", "value"),
     Input('url', 'pathname')], # Only these trigger the update
    [State("report-selector", "value"),
     State('prog-date-range-picker', 'start_date'),
     State('prog-date-range-picker', 'end_date'),
     State('prog-hf-filter', 'value')], # These are read only when Input triggers
     running=[
        (
            Output("btn-generate-report", "children"),
            "Generating... wait",
            "Generate Report"
        ),
        (
            Output("btn-generate-report", "style"),
            {"cursor": "not-allowed","opacity": "0.7"},
            {"cursor": "pointer","opacity": "1"}
        ),
        (
            Output("btn-generate-report", "disabled"),
            True,
            False
        ),
    ]
)
def generate_chart(n_clicks, urlparams, selected_report, pathname, report_name, start_date, end_date, hf):
    urlparams = urlparams or {}
    location = (urlparams.get("Location") or urlparams.get("?Location") or [None])[0]
    data_route = urlparams.get('route', ["default"])[0]
    DATA_PATH_ = f"data/{data_route}/parquet"

    path_program_reports = os.path.join(path, 'data','visualizations','validated_prog_reports.json')
    program_reports_progs_path = os.path.join(path, f'data/visualizations/validated_prog_reports.json')

    user_data = _load_user_registry(data_route)
    user_row, scope = _resolve_user_scope(urlparams, user_data)
    if user_row is None:
        return html.Div("Unauthorized User. Please contact system administrator."), no_update, 0, None, True
    role = user_row.get('role')
    effective_level = scope.get('level')

    try:
        start_dt = pd.to_datetime(start_date).replace(hour=0, minute=0, second=0)
        end_dt   = pd.to_datetime(end_date).replace(hour=23, minute=59, second=59)

        if effective_level == 'facility' and not location:
            return html.Div("Missing Parameters"), no_update, 0, None, True

        hf_list = hf if isinstance(hf, list) else ([hf] if hf else [])
        scope_parts = _scope_where_parts(
            effective_level, location, None, scope.get('districts'), hf_list, None,
        )
        base_where = f"{DATE_} BETWEEN '{start_dt}'::TIMESTAMP AND '{end_dt}'::TIMESTAMP"
        if scope_parts:
            base_where += " AND " + " AND ".join(scope_parts)

        filtered_query = base_where
        try:
            with open(program_reports_progs_path) as x:
                dropdowns = json.load(x)
            prog_options = list(set([program['program'] for program in dropdowns['reports']])) + ["+ Create a Report"]
        except Exception:
            prog_options = []

        report_name = report_name or selected_report
        if not report_name:
            return (
                html.Div("Please select a report name and click Generate."),
                prog_options, 0, None, True,
            )

        ctx = callback_context
        if not ctx.triggered or ctx.triggered_id != "btn-generate-report":
            return no_update, prog_options, 0, no_update, no_update

        # ── Load report config and render ─────────────────────────────────────
        with open(path_program_reports) as x:
            config = json.load(x)
        report_cfg = [r for r in config.get("reports", []) if r.get("report_name") == report_name]
        content, export_df = programs_report(filtered_query, DATA_PATH_, report_cfg, role)
        export_payload = (
            {"report_name": report_name, "data": export_df.to_json(orient="split", date_format="iso")}
            if export_df is not None else None
        )
        return content, prog_options, 0, export_payload, export_df is None

    except Exception as e:
        traceback.print_exc()
        return html.Div(f"Error: {str(e)}"), [], 0, None, True
    
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


@callback(
    Output("download-prog-report", "data"),
    Input("btn-excel", "n_clicks"),
    State("prog-report-export-store", "data"),
    prevent_initial_call=True,
)
def download_excel(n_clicks, export_payload):
    if not n_clicks or not export_payload:
        raise PreventUpdate

    df = pd.read_json(io.StringIO(export_payload["data"]), orient="split")
    report_name = export_payload.get("report_name") or "report"
    safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in report_name).strip() or "report"

    xlsx_buffer = io.BytesIO()
    with pd.ExcelWriter(xlsx_buffer, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name=safe_name[:31], index=False)
    xlsx_buffer.seek(0)
    return dcc.send_bytes(xlsx_buffer.getvalue(), filename=f"{safe_name}.xlsx")
