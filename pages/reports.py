import dash
from dash import html, dcc, Input, Output, State, callback, callback_context, ALL
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import datetime
from datetime import datetime as dt
import os
import json
from dash.exceptions import PreventUpdate
from helpers.reports_class import ReportTableBuilder
from pages.home import _resolve_user_scope, _load_user_registry, _load_user_properties
from mnid.data_utils import prepare_mnid_dataframe
import warnings
warnings.filterwarnings("ignore")
from helpers.date_ranges import (
    RELATIVE_MONTHS,
    RELATIVE_QUARTERS,
    RELATIVE_BIANNUAL,
    get_month_start_end,
    get_quarter_start_end,
    get_week_start_end,
    get_biannual_start_end,
    get_dhis2_period
)
import pdfkit
from reportlab.lib.pagesizes import letter, A4, portrait, landscape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
import io
import base64
from data_storage import DataStorage

from config import (DATE_, FACILITY_, AGE_GROUP_, GENDER_, PROGRAM_,PERSON_ID_,ENCOUNTER_ID_,
                    NEW_REVISIT_, HOME_DISTRICT_, TA_, VILLAGE_, CONCEPT_NAME_,VALUE_DATETIME_,
                    FACILITY_CODE_, DATA_PATH_, actual_keys_in_data)
from helpers.navigation_callbacks import DEMO_UUID
from dash_iconify import DashIconify

def nav_icon(icon_name):
    return DashIconify(icon=icon_name, className="nav-icon")


def _get_node_text(node):
    """Recursively extract plain text from a serialized Dash component node."""
    if node is None:
        return ""
    if isinstance(node, (str, int, float)):
        return str(node)
    if isinstance(node, list):
        return " ".join(_get_node_text(c) for c in node if c is not None)
    if isinstance(node, dict):
        children = node.get("props", {}).get("children")
        if children is not None:
            return _get_node_text(children)
    return ""


def _extract_tables_from_component(comp):
    """
    Walk a serialized Dash component dict and return
    [(section_title, DataFrame), ...] for each html.Table found.
    The first <Th> in Thead is treated as the section title.
    """
    results = []
    _walk_tables(comp, results)
    return results


def _walk_tables(node, results):
    if isinstance(node, list):
        for item in node:
            _walk_tables(item, results)
        return
    if not isinstance(node, dict):
        return
    comp_type = node.get("type", "")
    props     = node.get("props", {})
    children  = props.get("children", [])

    if comp_type == "Table":
        headers, rows = [], []
        for child in (children if isinstance(children, list) else [children]):
            if not isinstance(child, dict):
                continue
            ctype     = child.get("type", "")
            cchildren = child.get("props", {}).get("children", [])
            cchildren = cchildren if isinstance(cchildren, list) else [cchildren]
            if ctype == "Thead":
                for tr in cchildren:
                    if isinstance(tr, dict) and tr.get("type") == "Tr":
                        cells = tr.get("props", {}).get("children", [])
                        cells = cells if isinstance(cells, list) else [cells]
                        headers = [_get_node_text(c) for c in cells]
            elif ctype == "Tbody":
                for tr in cchildren:
                    if isinstance(tr, dict) and tr.get("type") == "Tr":
                        cells = tr.get("props", {}).get("children", [])
                        cells = cells if isinstance(cells, list) else [cells]
                        rows.append([_get_node_text(c) for c in cells])
        if headers and rows:
            section_title = headers[0] or f"Section {len(results) + 1}"
            df = pd.DataFrame(rows, columns=headers)
            results.append((section_title, df))
        return  # don't recurse into processed table

    _walk_tables(
        children if isinstance(children, list) else ([children] if children else []),
        results,
    )


import re as _re

_TAG_MAP = {
    "Div": "div", "Span": "span", "P": "p", "A": "a",
    "Table": "table", "Thead": "thead", "Tbody": "tbody",
    "Tr": "tr", "Th": "th", "Td": "td",
    "H1": "h1", "H2": "h2", "H3": "h3", "H4": "h4", "H5": "h5", "H6": "h6",
    "Ul": "ul", "Ol": "ol", "Li": "li",
    "B": "b", "I": "i", "Strong": "strong", "Em": "em",
    "Br": "br", "Hr": "hr", "Label": "label", "Button": "button",
    "Section": "section", "Header": "header", "Footer": "footer",
}
_SKIP_NS = {"dash_iconify", "dash_core_components", "dash_table", "plotly"}
_SELF_CLOSE = {"br", "hr", "img", "input"}


def _camel_to_kebab(name):
    s = _re.sub(r"(.)([A-Z][a-z]+)", r"\1-\2", name)
    return _re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", s).lower()


def _comp_to_html(node):
    """Convert a serialized Dash component dict to an HTML string."""
    if node is None:
        return ""
    if isinstance(node, (str, int, float)):
        return str(node)
    if isinstance(node, list):
        return "".join(_comp_to_html(c) for c in node)
    if not isinstance(node, dict):
        return ""

    namespace = node.get("namespace", "")
    if any(namespace.startswith(ns) for ns in _SKIP_NS):
        return ""

    comp_type = node.get("type", "")
    tag       = _TAG_MAP.get(comp_type, "div")
    props     = node.get("props", {})

    attrs = []
    if props.get("className"):
        attrs.append(f'class="{props["className"]}"')
    style = props.get("style") or {}
    if style:
        css = "; ".join(f"{_camel_to_kebab(k)}: {v}" for k, v in style.items())
        attrs.append(f'style="{css}"')
    for prop, attr in (("colSpan", "colspan"), ("rowSpan", "rowspan"),
                       ("id", "id"), ("href", "href"), ("src", "src")):
        val = props.get(prop)
        if val is not None:
            attrs.append(f'{attr}="{val}"')

    attr_str = (" " + " ".join(attrs)) if attrs else ""
    if tag in _SELF_CLOSE:
        return f"<{tag}{attr_str}/>"

    inner = _comp_to_html(props.get("children", []))
    return f"<{tag}{attr_str}>{inner}</{tag}>"


dash.register_page(__name__, path="/hmis_reports")

pd.options.mode.chained_assignment = None

relative_week = [str(week) for week in range(1, 53)]  # Can extend to 53 if needed
relative_month = RELATIVE_MONTHS
relative_quarter = RELATIVE_QUARTERS
relative_biannual = RELATIVE_BIANNUAL
relative_year = [str(year) for year in range(2024, 2051)]

path = os.getcwd()

layout = html.Div(
    className="reports-modern-container",
    children=[
        dcc.Location(id='url', refresh=False),
    
        # Parameters Card
        html.Div(
            className="parameters-card",
            children=[
                # html.H3("HMIS Dataset Reports: Generate and download standardized health facility reports", className="parameters-title"),
                
                # Filters Grid
                html.Div(
                    className="parameters-grid",
                    children=[
                        # Program Filter
                        html.Div(
                            className="parameter-group",
                            children=[
                                html.Label("Program", className="parameter-label"),
                                dcc.Dropdown(
                                    id='program_filter',
                                    options=[
                                        {'label': item, 'value': item}
                                        for item in []
                                    ],
                                    value='General Reports',
                                    clearable=True,
                                    className="modern-dropdown"
                                )
                            ]
                        ),
                        
                        # Report Name Filter
                        html.Div(
                            className="parameter-group",
                            children=[
                                html.Label("Report Name", className="parameter-label"),
                                dcc.Dropdown(
                                    id='report_name',
                                    options=[
                                        {'label': hf, 'value': hf}
                                        for hf in []
                                    ],
                                    value=None,
                                    clearable=True,
                                    className="modern-dropdown"
                                )
                            ]
                        ),
                        
                        # Year Filter
                        html.Div(
                            className="parameter-group",
                            children=[
                                html.Label("Year", className="parameter-label"),
                                dcc.Dropdown(
                                    id='year-filter',
                                    options=[
                                        {'label': period, 'value': period}
                                        for period in relative_year
                                    ],
                                    value=dt.now().strftime("%Y"),
                                    clearable=True,
                                    className="modern-dropdown"
                                )
                            ]
                        ),

                        # Period Type Filter
                        html.Div(
                            className="parameter-group",
                            children=[
                                html.Label("Period Type", className="parameter-label"),
                                dcc.Dropdown(
                                    id='period_type-filter',
                                    options=[
                                        {'label': period, 'value': period}
                                        for period in ['Weekly', 'Monthly', 'Quarterly', 'Bi-Annual']
                                    ],
                                    value='Monthly',
                                    clearable=True,
                                    className="modern-dropdown"
                                )
                            ]
                        ),
                        
                        # Week/Month/Quarter Filter
                        html.Div(
                            className="parameter-group",
                            children=[
                                html.Label("Week/Month/Quarter", className="parameter-label"),
                                dcc.Dropdown(
                                    id='month-filter',
                                    options=[
                                        {'label': period, 'value': period}
                                        for period in relative_month
                                    ],
                                    value=dt.now().strftime("%B"),
                                    clearable=True,
                                    className="modern-dropdown"
                                )
                            ]
                        ),

                        html.Div(
                            id ='facilities',
                            className="parameter-group",
                            children=[
                                html.Label("Select Facility", className="parameter-label"),
                                dcc.Dropdown(
                                    id='facility-filter',
                                    options=[
                                        {'label': hf, 'value': hf}
                                        for hf in []
                                    ],
                                    multi=False,
                                    value="",
                                    clearable=True,
                                    className="modern-dropdown"
                                )
                            ]
                        ),
                    ]
                ),
                
                # Action Buttons
                html.Div(
                    className="parameters-actions",
                    children=[
                        html.Button(
                            "Generate Report",
                            id="generate-btn",
                            n_clicks=0,
                            className="btn-generate-modern"
                        ),
                        html.Div(
                            id="download-buttons-group",
                            className="download-buttons",
                            style={"display": "none"},
                            children=[
                                html.Button(
                                    [nav_icon("lucide:file-spreadsheet"), " XLSX"],
                                    id="report-btn-xlsx",
                                    n_clicks=0,
                                    className="btn-download-csv"
                                ),
                                html.Button(
                                    [nav_icon("lucide:file-text"), " PDF"],
                                    id="report-btn-pdf",
                                    n_clicks=0,
                                    className="btn-download-pdf"
                                ),
                                html.Span(id="report-run-status", className="run-status-modern")
                            ]
                        )
                    ]
                ),
            ]
        ),
        
        # Report Output Container
        html.Div(
            id='standard-reports-table-container',
            className="report-output-container"
        ),
        
        # Hidden Components
        dcc.Download(id="download-report-blob"),
        dcc.Store(id="report-data-store"),
        dcc.Store(id="report-html-store"),
        dcc.Store(id="rpt-modal-page", data=1),
        dcc.Store(id="rpt-modal-data", data=None),

        # Patient ID modal
        html.Div(
            id="rpt-patient-modal",
            style={"display": "none"},
            children=[
                html.Div(
                    id="rpt-patient-modal-backdrop",
                    n_clicks=0,
                    style={
                        "position": "fixed", "inset": "0",
                        "background": "rgba(0,0,0,0.45)", "zIndex": "2000",
                    },
                ),
                html.Div(
                    style={
                        "position": "fixed", "top": "50%", "left": "50%",
                        "transform": "translate(-50%,-50%)",
                        "zIndex": "2100", "background": "#ffffff",
                        "borderRadius": "8px",
                        "boxShadow": "0 8px 32px rgba(0,0,0,0.22)",
                        "width": "1200px", "maxWidth": "92vw",
                        "maxHeight": "80vh",
                        "display": "flex", "flexDirection": "column",
                    },
                    children=[
                        # Header
                        html.Div(
                            style={
                                "display": "flex", "alignItems": "center",
                                "justifyContent": "space-between",
                                "padding": "12px 16px",
                                "borderBottom": "1px solid #e5e7eb",
                                "flexShrink": "0",
                            },
                            children=[
                                html.Span(id="rpt-patient-modal-title",
                                          style={"fontWeight": "700", "fontSize": "14px",
                                                 "color": "#111827"}),
                                html.Button(
                                    "✕",
                                    id="rpt-patient-modal-close",
                                    n_clicks=0,
                                    style={
                                        "background": "#dc2626", "color": "#ffffff",
                                        "border": "none", "borderRadius": "50%",
                                        "width": "26px", "height": "26px",
                                        "fontSize": "13px", "fontWeight": "700",
                                        "cursor": "pointer", "lineHeight": "1",
                                        "flexShrink": "0",
                                    },
                                ),
                            ],
                        ),
                        # Table body
                        html.Div(
                            id="rpt-patient-modal-body",
                            style={"overflowY": "auto", "flex": "1", "padding": "12px 16px"},
                        ),
                        # Pagination footer
                        html.Div(
                            style={
                                "display": "flex", "alignItems": "center",
                                "justifyContent": "space-between",
                                "padding": "8px 16px",
                                "borderTop": "1px solid #e5e7eb",
                                "flexShrink": "0", "background": "#f9fafb",
                                "borderRadius": "0 0 8px 8px",
                            },
                            children=[
                                html.Button(
                                    "← Prev",
                                    id="rpt-modal-prev-btn",
                                    n_clicks=0,
                                    style={
                                        "background": "#525E52", "color": "#ffffff",
                                        "border": "none", "borderRadius": "4px",
                                        "padding": "4px 14px", "fontSize": "12px",
                                        "cursor": "pointer",
                                    },
                                ),
                                html.Span(id="rpt-modal-page-info",
                                          style={"fontSize": "12px", "color": "#6b7280"}),
                                html.Button(
                                    "Next →",
                                    id="rpt-modal-next-btn",
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
    Output('month-filter', 'options'),
    Input('period_type-filter', 'value'),
)
def update_month_options(period_type):
    period_map = {
        'Weekly': relative_week,
        'Monthly': relative_month,
        'Quarterly': relative_quarter,
        'Bi-Annual': relative_biannual
    }
    return period_map.get(period_type, relative_quarter)

@callback(
        [Output('facility-filter', 'options'),
         Output('facility-filter', 'value'),
         Output('facilities', 'style')],
        Input('url-params-store', 'data'))

def load_user_facilities(urlparams):
    data_route = urlparams.get('route', ["default"])[0] if urlparams else None
    user_data = _load_user_registry(data_route)
    user_row, scope = _resolve_user_scope(urlparams, user_data)
    user_facility = user_row.get('facility_name', 'Unknown Facility')

    if scope['facilities'] and len(scope['facilities']) > 1:
        # print("here1")
        hf = scope['facilities'] if isinstance(scope['facilities'], list) else [scope['facilities']]
        return hf,user_facility, {'className': 'modern-dropdown'}
    elif scope['facilities'] and len(scope['facilities']) == 1:
        # print("here2")
        hf = scope['facilities'] if isinstance(scope['facilities'], list) else [scope['facilities']]
        return hf,user_facility, {'display':'none'}
    elif scope['level'] == 'national':
        facilities_path = os.path.join(path, f'data/{data_route}', 'dcc_dropdown_json', 'facilities_dropdowns.json')
        with open(facilities_path, 'r') as f:
            facilities_raw = json.load(f)
        hf = [item for value in facilities_raw.values() if isinstance(value, list) for item in value]
        return hf,user_facility, {'className': 'modern-dropdown'}
    else:
        # print("here3")
        return ['User Facility'],user_facility, {'display':'none'}

def load_report_options(program=None, user_data=None):
    """Load reports from JSON and return concatenated options for dropdown"""
    try:
        with open('data/hmis_reports.json', 'r') as f:
            data = json.load(f)
        # Create concatenated options: "ID - Report Name"
        options_global = [
            {'label': f"{report['report_name']}", 
             'value': report['report_id']}
            for report in data['reports'] 
            if report.get('archived', 'False').lower() == 'false'
            and report.get('access', 'global').lower() == 'global'
            and (program is None or program in report.get('programs', []))
        ]
        options_limited = [
            {'label': f"{report['report_name']}", 
            'value': report['report_id']}
            for report in data['reports'] 
            if report.get('archived', 'False').lower() == 'false'
            and report.get('page_name', '').lower() in (user_data.get('properties', {}).get('limited_hmis_reports', []) if user_data is not None else [])
            and (program is None or program in report.get('programs', []))
        ]
        return options_global + options_limited
    except FileNotFoundError:
        print("report.json file not found")
        return []
    except json.JSONDecodeError:
        print("Error decoding JSON from report.json")
        return []
    except KeyError as e:
        print(f"Missing key in JSON: {e}")
        return []
      
@callback(
        [Output('program_filter', 'options'),
         Output('report_name', 'options')],
        [Input('url-params-store', 'data'),
        Input('program_filter','value')]
)
   
def update_report_dropdown(urlparams, program):
    data_route = urlparams.get('route', ["default"])[0] if urlparams else None
    user_id = urlparams.get('uuid', ["default"])[0] if urlparams else None
    user_properties = _load_user_properties(data_route)
    user_data = next(
                    (
                        r for r in user_properties
                        if r.get('properties').get('uuid') == user_id
                    ),
                    None
                )
    
    data_set_programs_path = os.path.join(path, f'data', 'hmis_reports.json')
    with open(data_set_programs_path) as x:
            dropdowns = json.load(x)
    prog_options = ['General Reports'] + list(set([program["programs"][0] for program in dropdowns['reports']]))
    return prog_options, load_report_options(program, user_data)

@callback(
    [
        Output('standard-reports-table-container', 'children'),
        Output('generate-btn', 'n_clicks'),
        Output('report-data-store', 'data')
    ],
    Input('generate-btn', 'n_clicks'),
    Input('url-params-store', 'data'),
    Input('period_type-filter', 'value'),
    Input('year-filter', 'value'),
    Input('month-filter', 'value'),
    Input('facility-filter', 'value'),
    Input('report_name', 'value'),
    Input('url', 'pathname'),
    prevent_initial_call=True,

    running=[
        (
            Output("generate-btn", "children"),
            "Generating... wait",
            "Generate Report"
        ),
        (
            Output("generate-btn", "style"),
            {
                "cursor": "not-allowed",
                "opacity": "0.7"
            },
            {
                "cursor": "pointer",
                "opacity": "1"
            }
        ),
        (
            Output("generate-btn", "disabled"),
            True,
            False
        ),
    ]
)
def update_table(clicks, urlparams, period_type, year_filter, month_filter, facility_filter, report_filter,pathname):
    
    ctx = dash.callback_context
    if not ctx.triggered:
        return dash.no_update, 0, None
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
    if clicks is None or clicks == 0:
        raise PreventUpdate
    
    # Handle missing inputs to prevent errors
    if not urlparams or not period_type or not year_filter or not month_filter or not report_filter or not facility_filter:
        return html.Div("Missing Report Parameters"), 0, None
    reports_json = os.path.join(path, 'data', 'hmis_reports.json')
    with open(reports_json, "r") as f:
        json_data = json.load(f)
    target = report_filter
    report = next(
                    (
                        r for r in json_data["reports"]
                        if r['report_id'] == target
                        and r["archived"].lower() == "false"
                    ),
                    None
                )
    if not report:
        return html.Div("Report Not Found"), 0, None
    
    spec_path = f"data/uploads/{report['page_name']}.xlsx"

    report_design = report.get("design", {})

    report_filters = report.get("filters", {})

    if not os.path.exists(spec_path):
        return html.Div("Report not found on Server. Request Admin to add report"), 0, None
    
    location = (urlparams.get("Location") or urlparams.get("?Location") or [None])[0]
    data_route = urlparams.get('route', ["default"])[0]
    DATA_PATH_ = f"data/{data_route}/parquet"

    user_data = _load_user_registry(data_route)
    user_row, scope = _resolve_user_scope(urlparams, user_data)

    test_admin = pd.DataFrame(columns=['uuid', 'role'], data=[[DEMO_UUID, 'reports_admin']])
    user_data = pd.concat([user_data, test_admin], ignore_index=True)
    user_info = user_data[user_data['uuid'] == urlparams.get('uuid', [None])[0]]
    if user_info.empty:
        return html.Div("Unauthorized User. Please contact system administrator."), dash.no_update, dash.no_update
 #for cohort analysis this has to be moved forward to the return function
    mnh_report_pages = {
        "anc_fixed",
        "labour_and_delivery_fixed_v2",
        "pnc_fixed_v2",
        "sick_neonate",
    }
    if report.get("page_name") in mnh_report_pages:
        sql = f"""
                SELECT *
                FROM '{DATA_PATH_}'
                WHERE {FACILITY_CODE_} = '{location}'
            """
        data = DataStorage.query_duckdb(sql)
        data = prepare_mnid_dataframe(data)

    try:
        period_map = {
            'Weekly': get_week_start_end,
            'Monthly': get_month_start_end,
            'Quarterly': get_quarter_start_end,
            'Bi-Annual': get_biannual_start_end
        }
        start_date, end_date = period_map.get(period_type, get_month_start_end)(
            month_filter, year_filter
        )

        dhis2_period = get_dhis2_period(start_date, period_type)

        builder = ReportTableBuilder(excel_path=spec_path, 
                                     report_start_date= start_date, 
                                     report_end_date= end_date, 
                                     data_route= DATA_PATH_, 
                                     location=location, dhis2_period= dhis2_period,
                                     facility=facility_filter,
                                      report_design= report_design,
                                       report_filters = report_filters )
        builder.load_spec()
        components   = builder.build_dash_components()
        section_data = builder.build_section_tables()

        # Read layout meta for the PDF generator
        num_page_columns = 1
        design = "portrait"
        report_title = builder._title() or "HMIS DATASET REPORT"
        if builder.report_name is not None and not builder.report_name.empty:
            meta = builder.report_name.iloc[0]
            try:
                num_page_columns = int(meta.get("num_page_columns", 1) or 1)
            except (ValueError, TypeError):
                num_page_columns = 1
            num_page_columns = max(1, min(4, num_page_columns))
            design = str(meta.get("design", "portrait") or "portrait").lower()

        serializable_data = {
            "meta": {
                "title":            report_title,
                "num_page_columns": num_page_columns,
                "design":           design,
                "period":           f"{start_date} – {end_date}",
                "location":         location or "",
            },
            "sections": [
                {"section": name, "data": df.to_json(date_format="iso", orient="split")}
                for name, df in section_data
            ],
        }
        return components, 0, serializable_data

    except ValueError as e:
        print(f"Error: {e}")
        return html.Div(f"Error: {str(e)}"), 0, None


@callback(
    Output("download-buttons-group", "style"),
    Input("report-data-store", "data"),
    prevent_initial_call=True,
)
def toggle_download_buttons(report_data):
    if report_data:
        return {"display": "flex"}
    return {"display": "none"}


@callback(
    Output("report-html-store", "data"),
    Input("standard-reports-table-container", "children"),
    prevent_initial_call=True,
)
def _relay_html_to_store(children):
    return children


@callback(
        Output('download-report-blob', 'data'),
        [
        Input('report-data-store', 'data'),
        Input('report-btn-xlsx', 'n_clicks'),
        Input('report-btn-pdf', 'n_clicks')
        ],
        State('report-html-store', 'data'),
        prevent_initial_call=True
)
def get_data(reports_data, xlsx, pdf, comp_data):
    ctx = dash.callback_context
    if not ctx.triggered:
        return dash.no_update
    if not reports_data:
        return dash.no_update
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]

    # Support both old list format and new dict format
    if isinstance(reports_data, list):
        sections_raw = reports_data
        meta = {"title": "HMIS DATASET REPORT", "num_page_columns": 1,
                "design": "portrait", "period": "", "location": ""}
    else:
        sections_raw = reports_data.get("sections", [])
        meta         = reports_data.get("meta", {})

    if trigger_id == 'report-btn-xlsx':
        # ── XLSX: one sheet per section (unchanged) ───────────────────────────
        xlsx_buffer = io.BytesIO()
        with pd.ExcelWriter(xlsx_buffer, engine='openpyxl') as writer:
            for item in sections_raw:
                sheet_name = str(item['section'])[:31]
                df = pd.read_json(item['data'], orient='split')
                df.to_excel(writer, sheet_name=sheet_name, index=False)
        xlsx_buffer.seek(0)
        return dcc.send_bytes(xlsx_buffer.getvalue(), filename='MaHIS_facility_report.xlsx')

    elif trigger_id == 'report-btn-pdf':
        if not comp_data:
            return dash.no_update

        is_landscape = str(meta.get("design", "portrait")).lower() == "landscape"
        page_orient  = "landscape" if is_landscape else "portrait"
        report_title = meta.get("title", "HMIS DATASET REPORT").upper()
        period_str   = meta.get("period", "")
        location_str = meta.get("location", "")

        body_html = _comp_to_html(comp_data)

        html_doc = f"""<!DOCTYPE html>
            <html>
            <head>
            <meta charset="utf-8"/>
            <style>
            @page {{ size: A4 {page_orient}; margin: 18mm; @bottom-right {{ content: "Generated by MaHIS@2026"; font-size: 8px; color: #6b7280; }} }}
            body {{ font-family: Arial, Helvetica, sans-serif; font-size: 11px; color: #111; margin: 0; }}
            table {{ width: 100%; border-collapse: collapse; margin-bottom: 10px; page-break-inside: auto; }}
            tr {{ page-break-inside: avoid; }}
            th, td {{ border: 1px solid #e5e7eb; padding: 3px 6px; font-size: 9px; word-wrap: break-word; }}
            </style>
            </head>
            <body>{body_html}</body>
            </html>"""

        try:
            from weasyprint import HTML as WeasyprintHTML
            pdf_bytes = WeasyprintHTML(string=html_doc).write_pdf()
        except ImportError:
            import pdfkit
            pdf_bytes = pdfkit.from_string(html_doc, False)

        return dcc.send_bytes(pdf_bytes, filename="MaHIS_facility_report.pdf")

    else:
        return dash.no_update


_RPT_PAGE_SIZE = 15


# Report cell click — open/close modal + fetch patient data
@callback(
    Output("rpt-patient-modal",       "style"),
    Output("rpt-patient-modal-title", "children"),
    Output("rpt-modal-data",          "data"),
    Output("rpt-modal-page",          "data"),
    Input({"type": "rpt-val-click",        "index": ALL}, "n_clicks"),
    Input("rpt-patient-modal-close",   "n_clicks"),
    Input("rpt-patient-modal-backdrop","n_clicks"),
    State({"type": "rpt-cell-ids",         "index": ALL}, "data"),
    State({"type": "rpt-val-click",        "index": ALL}, "id"),
    State("url-params-store", "data"),
    prevent_initial_call=True,
)
def _rpt_patient_modal(n_clicks_list, n_close, n_backdrop, ids_list, id_list, urlparams):
    from dash import ctx
    from helpers.visualizations import create_line_list_basic_modal
    triggered = ctx.triggered_id

    if triggered in ("rpt-patient-modal-close", "rpt-patient-modal-backdrop"):
        return {"display": "none"}, dash.no_update, dash.no_update, dash.no_update

    if not isinstance(triggered, dict) or triggered.get("type") != "rpt-val-click":
        raise PreventUpdate
    if not any(n for n in (n_clicks_list or []) if n):
        raise PreventUpdate

    clicked_index = triggered["index"]
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
    title = f"Patient List — ({len(patient_ids):,} Total Records)"

    modal_data = {
        "rows":  df.to_dict("records"),
        "cols":  list(df.columns),
        "total": len(df),
    }
    return {"display": "block"}, title, modal_data, 1


# Report modal — render current page
@callback(
    Output("rpt-patient-modal-body", "children"),
    Output("rpt-modal-page-info",    "children"),
    Input("rpt-modal-page", "data"),
    Input("rpt-modal-data", "data"),
    prevent_initial_call=True,
)
def _rpt_render_page(page, modal_data):
    if not modal_data:
        raise PreventUpdate

    rows_all = modal_data.get("rows", [])
    cols     = modal_data.get("cols", [])
    total    = modal_data.get("total", 0)

    if not rows_all:
        return html.Div("No records found.", style={"fontSize": "13px", "color": "#6b7280"}), ""

    page        = max(1, page or 1)
    total_pages = max(1, -(-total // _RPT_PAGE_SIZE))
    page        = min(page, total_pages)

    start     = (page - 1) * _RPT_PAGE_SIZE
    page_rows = rows_all[start: start + _RPT_PAGE_SIZE]

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
    return table, f"Page {page} of {total_pages}  ({total:,} records)"


# Report modal — page navigation
@callback(
    Output("rpt-modal-page", "data", allow_duplicate=True),
    Input("rpt-modal-prev-btn", "n_clicks"),
    Input("rpt-modal-next-btn", "n_clicks"),
    State("rpt-modal-page",    "data"),
    State("rpt-modal-data",    "data"),
    prevent_initial_call=True,
)
def _rpt_modal_nav(n_prev, n_next, page, modal_data):
    from dash import ctx
    if not modal_data:
        raise PreventUpdate
    total       = modal_data.get("total", 0)
    total_pages = max(1, -(-total // _RPT_PAGE_SIZE))
    page        = max(1, page or 1)
    if ctx.triggered_id == "rpt-modal-prev-btn":
        page = max(1, page - 1)
    else:
        page = min(total_pages, page + 1)
    return page
