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


dash.register_page(__name__, path="/hmis_reports")

pd.options.mode.chained_assignment = None

relative_week = [str(week) for week in range(1, 53)]  # Can extend to 53 if needed
relative_month = RELATIVE_MONTHS
relative_quarter = RELATIVE_QUARTERS
relative_biannual = RELATIVE_BIANNUAL
relative_year = [str(year) for year in range(2024, 2051)]

path = os.getcwd()

def load_report_options(program=None):
    """Load reports from JSON and return concatenated options for dropdown"""
    try:
        with open('data/hmis_reports.json', 'r') as f:
            data = json.load(f)
        # Create concatenated options: "ID - Report Name"
        options = [
            {'label': f"{report['report_name']}", 
             'value': report['report_id']}
            for report in data['reports'] 
            if report.get('archived', 'False').lower() == 'false'
            and (program is None or program in report.get('programs', []))
        ]
        return options
    except FileNotFoundError:
        print("report.json file not found")
        return []
    except json.JSONDecodeError:
        print("Error decoding JSON from report.json")
        return []
    except KeyError as e:
        print(f"Missing key in JSON: {e}")
        return []


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
                            className="download-buttons",
                            children=[
                                html.Button(
                                    "📥 XLSX",
                                    id="report-btn-xlsx",
                                    n_clicks=0,
                                    className="btn-download-csv"
                                ),
                                html.Button(
                                    "📄 PDF",
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
        [Output('program_filter', 'options'),
         Output('report_name', 'options')],
        [Input('url-params-store', 'data'),
        Input('program_filter','value')]
)
def update_report_dropdown(urlparams, program):
    data_route = urlparams.get('route', ["default"])[0] if urlparams else None
    data_set_programs_path = os.path.join(path, f'data', 'hmis_reports.json')
    with open(data_set_programs_path) as x:
            dropdowns = json.load(x)
    prog_options = ['General Reports'] + list(set([program["programs"][0] for program in dropdowns['reports']]))
    return prog_options, load_report_options(program)

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
def update_table(clicks, urlparams, period_type, year_filter, month_filter, report_filter,pathname):
    
    ctx = dash.callback_context
    if not ctx.triggered:
        return dash.no_update, 0, None
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
    if clicks is None or clicks == 0:
        raise PreventUpdate
    
    # Handle missing inputs to prevent errors
    if not urlparams or not period_type or not year_filter or not month_filter or not report_filter:
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

    if not os.path.exists(spec_path):
        return html.Div("Report not found on Server. Request Admin to add report"), 0, None
    
    location = (urlparams.get("Location") or urlparams.get("?Location") or [None])[0]
    data_route = urlparams.get('route', ["default"])[0]
    DATA_PATH_ = f"data/{data_route}/parquet"

    # validate user
    user_data_path = os.path.join(path, f'data/{data_route}','single_tables', 'users_data.csv')
    if not os.path.exists(user_data_path):
        user_data = pd.DataFrame(columns=['uuid', 'role'])
    else:
        user_data = pd.read_csv(os.path.join(path, f'data/{data_route}','single_tables', 'users_data.csv'))
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
                                      report_design= report_design )
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
        Output('download-report-blob', 'data'),
        [
        Input('report-data-store', 'data'),
        Input('report-btn-xlsx', 'n_clicks'),
        Input('report-btn-pdf', 'n_clicks')
        ],
        prevent_initial_call=True
)
def get_data(reports_data, xlsx, pdf):
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
        # ── PDF: mirrors build_dash_components design ─────────────────────────
        from reportlab.lib.units import mm

        report_title    = meta.get("title", "HMIS DATASET REPORT").upper()
        num_cols        = int(meta.get("num_page_columns", 1) or 1)
        num_cols        = max(1, min(4, num_cols))
        is_landscape    = str(meta.get("design", "portrait")).lower() == "landscape"
        period_str      = meta.get("period", "")
        location_str    = meta.get("location", "")
        page_size       = landscape(A4) if is_landscape else portrait(A4)
        page_w, page_h  = page_size
        margin          = 18 * mm
        usable_w        = page_w - 2 * margin
        col_usable_w    = (usable_w - (num_cols - 1) * 6 * mm) / num_cols

        # ── Colour palette matching _create_modern_table ──────────────────────
        C_GREEN   = colors.HexColor("#006401")   # section title bar
        C_HEADER  = colors.HexColor("#374151")   # column header row
        C_DE_HDR  = colors.HexColor("#1f2937")   # Data Element header cell
        C_DE_CELL = colors.HexColor("#f9fafb")   # Data Element column background
        C_ODD     = colors.HexColor("#f9fafb")   # odd data rows
        C_EVEN    = colors.white
        C_BORDER  = colors.HexColor("#e5e7eb")
        C_WHITE   = colors.white

        styles     = getSampleStyleSheet()
        wrap_style = ParagraphStyle(
            "Wrap", parent=styles["Normal"],
            fontSize=7, leading=9, wordWrap="LTR", spaceBefore=1, spaceAfter=1,
        )
        de_style = ParagraphStyle(
            "DE", parent=styles["Normal"],
            fontSize=7, leading=9, wordWrap="LTR", fontName="Helvetica-Bold",
        )

        def _make_section_table(section_name: str, df: pd.DataFrame) -> list:
            """Return a list of ReportLab flowables for one report section."""
            df = df.dropna(how="all", axis=0).dropna(how="all", axis=1)
            if df.empty:
                return []

            value_cols = [c for c in df.columns if c != "Data Element"]

            # ── Dynamic column widths proportional to content ─────────────────
            de_max  = max((len(str(x)) for x in df["Data Element"].tolist()), default=12)
            de_w    = min(de_max * 4.5 + 20, col_usable_w * 0.45)
            val_total = col_usable_w - de_w
            val_w   = val_total / max(len(value_cols), 1)
            col_widths_pt = [de_w] + [val_w] * len(value_cols)

            # ── Section title bar (green, full width) ─────────────────────────
            title_data  = [[Paragraph(f"<b>{section_name.upper()}</b>",
                                      ParagraphStyle("TBar", parent=styles["Normal"],
                                                     fontSize=8, leading=10,
                                                     textColor=C_WHITE,
                                                     fontName="Helvetica-Bold"))]]
            title_table = Table(title_data, colWidths=[col_usable_w])
            title_table.setStyle(TableStyle([
                ("BACKGROUND",   (0, 0), (-1, -1), C_GREEN),
                ("LEFTPADDING",  (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING",   (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
                ("ROUNDEDCORNERS", [3, 3, 0, 0]),
            ]))

            # ── Column header row ──────────────────────────────────────────────
            hdr_row = [
                Paragraph("<b>Data Element</b>",
                          ParagraphStyle("HDR", parent=styles["Normal"],
                                         fontSize=7, leading=9, textColor=C_WHITE,
                                         fontName="Helvetica-Bold")),
            ] + [
                Paragraph(f"<b>{col.upper()}</b>",
                          ParagraphStyle("HDR", parent=styles["Normal"],
                                         fontSize=7, leading=9, textColor=C_WHITE,
                                         fontName="Helvetica-Bold", alignment=1))
                for col in value_cols
            ]

            # ── Data rows ──────────────────────────────────────────────────────
            data_rows = [hdr_row]
            for row_idx, (_, row) in enumerate(df.iterrows()):
                de_val  = str(row.get("Data Element", ""))
                de_cell = Paragraph(de_val, de_style)
                val_cells = [
                    Paragraph(str(row.get(col, "")), wrap_style)
                    for col in value_cols
                ]
                data_rows.append([de_cell] + val_cells)

            t = Table(data_rows, colWidths=col_widths_pt, repeatRows=1,
                      splitByRow=True)
            # Apply styling row by row for zebra effect
            ts = TableStyle([
                # Header row
                ("BACKGROUND",    (0, 0), (-1, 0), C_HEADER),
                ("BACKGROUND",    (0, 0), (0, 0),  C_DE_HDR),
                ("TEXTCOLOR",     (0, 0), (-1, 0), C_WHITE),
                ("ALIGN",         (1, 0), (-1, 0), "CENTER"),
                ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE",      (0, 0), (-1, 0), 7),
                # Data cells
                ("ALIGN",         (1, 1), (-1, -1), "CENTER"),
                ("FONTNAME",      (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE",      (0, 1), (-1, -1), 7),
                # Data Element column
                ("BACKGROUND",    (0, 1), (0, -1), C_DE_CELL),
                ("FONTNAME",      (0, 1), (0, -1), "Helvetica-Bold"),
                ("LINEAFTER",     (0, 0), (0, -1), 1, colors.HexColor("#d1d5db")),
                # Grid
                ("GRID",          (0, 0), (-1, -1), 0.4, C_BORDER),
                # Padding
                ("LEFTPADDING",   (0, 0), (-1, -1), 4),
                ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
                ("TOPPADDING",    (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ])
            # Zebra rows
            for row_idx in range(1, len(data_rows)):
                bg = C_ODD if row_idx % 2 == 1 else C_EVEN
                ts.add("BACKGROUND", (1, row_idx), (-1, row_idx), bg)
            t.setStyle(ts)

            return [title_table, t, Spacer(1, 6 * mm)]

        # ── Build all section flowables ────────────────────────────────────────
        all_section_flowables = []
        for item in sections_raw:
            df = pd.read_json(item["data"], orient="split")
            if len(df.columns) <= 1:
                continue
            all_section_flowables.append((item["section"], df))

        # ── Assemble PDF ───────────────────────────────────────────────────────
        buffer = io.BytesIO()
        doc    = SimpleDocTemplate(
            buffer, pagesize=page_size,
            leftMargin=margin, rightMargin=margin,
            topMargin=margin, bottomMargin=margin,
        )

        elements = []
        header_style = ParagraphStyle(
            "RptTitle", parent=styles["Normal"],
            fontSize=13, fontName="Helvetica-Bold",
            textColor=C_GREEN, alignment=1, spaceAfter=4,
        )
        sub_style = ParagraphStyle(
            "RptSub", parent=styles["Normal"],
            fontSize=8, textColor=colors.HexColor("#6b7280"), alignment=1,
        )
        elements.append(Paragraph(report_title, header_style))
        elements.append(Paragraph(
            f"{location_str}  |  {period_str}  |  "
            f"Generated: {dt.now().strftime('%Y-%m-%d %H:%M')}",
            sub_style,
        ))
        elements.append(Spacer(1, 4 * mm))
        # Divider
        elements.append(Table([[""]], colWidths=[usable_w],
                               style=TableStyle([
                                   ("LINEABOVE", (0, 0), (-1, -1), 1.5, C_GREEN),
                               ])))
        elements.append(Spacer(1, 4 * mm))

        if num_cols == 1:
            # Single column — stack sections vertically
            for sec_name, df in all_section_flowables:
                elements.extend(_make_section_table(sec_name, df))
        else:
            # Multi-column — group sections in rows of num_cols
            from reportlab.platypus import KeepInFrame
            groups = [all_section_flowables[i:i + num_cols]
                      for i in range(0, len(all_section_flowables), num_cols)]
            for group in groups:
                # Pad group to full width
                while len(group) < num_cols:
                    group.append(None)
                row_cells = []
                for item in group:
                    if item is None:
                        row_cells.append("")
                    else:
                        sec_name, df = item
                        inner = _make_section_table(sec_name, df)
                        frame = KeepInFrame(col_usable_w, 999 * mm, inner,
                                            mode="shrink")
                        row_cells.append(frame)
                col_w_list = [col_usable_w] * num_cols
                grid_gap   = 6 * mm
                col_w_list_with_gap = []
                for k, w in enumerate(col_w_list):
                    col_w_list_with_gap.append(w)
                    if k < num_cols - 1:
                        col_w_list_with_gap.append(grid_gap)
                        row_cells.insert(2 * k + 1, "")  # gap cell
                multi_table = Table(
                    [row_cells], colWidths=col_w_list_with_gap,
                )
                multi_table.setStyle(TableStyle([
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING",   (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
                    ("TOPPADDING",    (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]))
                elements.append(multi_table)
                elements.append(Spacer(1, 4 * mm))

        doc.build(elements)
        buffer.seek(0)
        return dcc.send_bytes(buffer.getvalue(), filename="MaHIS_facility_report.pdf")

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
