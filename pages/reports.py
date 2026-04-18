import dash
from dash import html, dcc, Input, Output, State, callback
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
from helpers.date_ranges import (
    RELATIVE_MONTHS,
    RELATIVE_QUARTERS,
    RELATIVE_BIANNUAL,
    get_month_start_end,
    get_quarter_start_end,
    get_week_start_end,
    get_biannual_start_end
)
from reportlab.lib.pagesizes import letter, A4, portrait
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
import io
import base64
from data_storage import DataStorage

from config import (DATE_, FACILITY_, AGE_GROUP_, GENDER_, 
                    NEW_REVISIT_, HOME_DISTRICT_, TA_, VILLAGE_, 
                    FACILITY_CODE_, DATA_FILE_NAME_, actual_keys_in_data)


dash.register_page(__name__, path="/hmis_reports")

relative_week = [str(week) for week in range(1, 53)]  # Can extend to 53 if needed
relative_month = RELATIVE_MONTHS
relative_quarter = RELATIVE_QUARTERS
relative_biannual = RELATIVE_BIANNUAL
relative_year = [str(year) for year in range(2024, 2051)]

path = os.getcwd()
dropdowns_json_path = os.path.join(path, 'data', 'dcc_dropdown_json', 'dropdowns.json')
with open(dropdowns_json_path) as x:
            dropdowns = json.load(x)
prog_options = dropdowns['programs'] + ['General Reports']

def load_report_options(program=None):
    """Load reports from JSON and return concatenated options for dropdown"""
    try:
        with open('data/hmis_reports.json', 'r') as f:
            data = json.load(f)
        # Create concatenated options: "ID - Report Name"
        options = [
            {'label': f"{report['report_id']} - {report['report_name']}", 
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
                                    "CSV",
                                    id="report-btn-csv",
                                    n_clicks=0,
                                    className="btn-download-csv"
                                ),
                                html.Button(
                                    "JSON",
                                    id="report-btn-json",
                                    n_clicks=0,
                                    className="btn-download-json"
                                ),
                                html.Button(
                                    "PDF",
                                    id="report-btn-pdf",
                                    n_clicks=0,
                                    className="btn-download-pdf"
                                ),
                                html.Span(id="report-run-status", className="run-status-modern")
                            ]
                        )
                    ]
                )
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
    with open(dropdowns_json_path) as x:
            dropdowns = json.load(x)
    prog_options = ['General Reports'] + dropdowns['programs']
    return prog_options, load_report_options(program)

@callback(
    [Output('standard-reports-table-container', 'children'),
     Output('generate-btn', 'n_clicks'),
     Output('report-data-store', 'data')],

    Input('generate-btn', 'n_clicks'), 
    Input('url-params-store', 'data'),
    Input('period_type-filter', 'value'),
    Input('year-filter', 'value'),
    Input('month-filter', 'value'),
    Input('report_name', 'value'),
    prevent_initial_call=True
)
def update_table(clicks, 
                 urlparams, 
                 period_type, 
                 year_filter, 
                 month_filter, 
                 report_filter):
    
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
    
    if urlparams.get('Location', [None])[0]:
        location = urlparams.get('Location', [None])[0]
    else:
        location = None
    
    SQL = f"""
        SELECT *
        FROM 'data/{DATA_FILE_NAME_}'
        WHERE {FACILITY_CODE_} = '{location}'
        """
    
    try:
        data = DataStorage.query_duckdb(SQL)
    except Exception as e:
        return html.Div('Missing Data. ' \
            'Ensure that the config file has correct database credentials.'
            ,style={'color':'red'}), 0, None # Empty DataFrame with expected columns
    
    data[GENDER_] = data[GENDER_].replace({"M":"Male",
                                               "F":"Female",
                                               '{"label"=>"Male", "value"=>"M"}':"Male",
                                               '{"label"=>"Female", "value"=>"F"}':"Female"})
    data["DateValue"] = pd.to_datetime(data[DATE_]).dt.date
    today = dt.today().date()
    data["months"] = data["DateValue"].apply(lambda d: (today - d).days // 30)
    # data_opd = data_opd.dropna(subset = ['obs_value_coded','concept_name', 'Value','ValueN', 'DrugName', 'Value_name'], how='all')
    # data_opd.to_csv('data/archive/hmis.csv')

    # validate user
    user_data_path = os.path.join(path, 'data', 'users_data.csv')
    if not os.path.exists(user_data_path):
        user_data = pd.DataFrame(columns=['user_id', 'role'])
    else:
        user_data = pd.read_csv(os.path.join(path, 'data', 'users_data.csv'))
    test_admin = pd.DataFrame(columns=['user_id', 'role'], data=[['m3his@dhd', 'reports_admin']])
    user_data = pd.concat([user_data, test_admin], ignore_index=True)
    user_info = user_data[user_data['user_id'] == urlparams.get('uuid', [None])[0]]
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
        data = prepare_mnid_dataframe(data)

    original_data = data.copy()
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
        # Convert once (avoid repeated conversions)
        data_dates = pd.to_datetime(data[DATE_])
        original_dates = pd.to_datetime(original_data[DATE_])

        filtered = data[
            (data_dates >= pd.to_datetime(start_date)) &
            (data_dates <= pd.to_datetime(end_date))
        ]

        original_data = original_data[original_dates <= pd.to_datetime(end_date)].copy()
        original_data["days_before"] = original_data["DateValue"].apply(
            lambda d: (start_date - d).days
        )

        spec_path = f"data/uploads/{report['page_name']}.xlsx"
        if not os.path.exists(spec_path):
            return html.Div("Report not found on Server. Request Admin to add report"), 0, None

        builder = ReportTableBuilder(spec_path, filtered, original_data)
        builder.load_spec()
        components = builder.build_dash_components()
        section_data = builder.build_section_tables()
        serializable_data = [
                {
                    'section': section_name,
                    'data': df.to_json(date_format='iso', orient='split')
                }
                for section_name, df in section_data
        ]
        return components, 0, serializable_data

    except ValueError as e:
        print(f"Error: {e}")
        return html.Div(f"Error: {str(e)}"), 0, None

    
@callback(
        Output('download-report-blob', 'data'),
        [
        Input('report-data-store', 'data'),
        Input('report-btn-csv', 'n_clicks'),
        Input('report-btn-json', 'n_clicks'),
        Input('report-btn-pdf', 'n_clicks')
        ],
        prevent_initial_call=True
)
def get_data(reports_data, csv, json, pdf):
    ctx = dash.callback_context
    if not ctx.triggered:
        return dash.no_update
    if not reports_data:
        return dash.no_update
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
    if trigger_id == 'report-btn-csv':
        all_dfs = []
        for item in reports_data:
            section_name = item['section']
            df = pd.read_json(item['data'], orient='split')
            df.insert(0, 'Section', section_name)  # Add a column to identify the section
            all_dfs.append(df)
        combined_df = pd.concat(all_dfs, ignore_index=True)
        return dcc.send_data_frame(combined_df.to_csv, 'MaHIS_facility_report.csv',index=False)
    elif trigger_id == 'report-btn-json':
        all_dfs = []
        for item in reports_data:
            section_name = item['section']
            df = pd.read_json(item['data'], orient='split')
            df.insert(0, 'Section', section_name)  # Add a column to identify the section
            all_dfs.append(df)
        combined_df = pd.concat(all_dfs, ignore_index=True)
        return dcc.send_data_frame(combined_df.to_json, 'MaHIS_facility_report.json')
    elif trigger_id == 'report-btn-pdf':
        all_dfs = []
        for item in reports_data:
            section_name = item['section']
            df = pd.read_json(item['data'], orient='split')
            df.insert(0, 'Section', section_name)
            all_dfs.append(df)
        combined_df = pd.concat(all_dfs, ignore_index=True)
        
        # Create PDF in memory
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer, 
            pagesize=portrait(A4), 
            leftMargin=30, 
            rightMargin=30, 
            topMargin=30, 
            bottomMargin=30
        )
        
        elements = []
        styles = getSampleStyleSheet()
        title_text = f"MAHIS FACILITY REPORT"
        title = Paragraph(title_text, styles["Title"])
        elements.append(title)
        current_date = dt.now().strftime("%Y-%m-%d %H:%M:%S")
        subtitle_text = f"Report | Generated: {current_date}"
        subtitle = Paragraph(subtitle_text, styles["Heading5"])
        elements.append(subtitle)
        elements.append(Spacer(1, 20))
        # Create wrap style for table cells
        wrap_style = ParagraphStyle(
            name='WrapStyle',
            parent=styles['Normal'],
            fontSize=8,
            leading=9,
            wordWrap='LTR',
            spaceBefore=2,
            spaceAfter=2,
        )
        pdf_columns = combined_df.columns.tolist()
        table_data = [pdf_columns]
        for _, row in combined_df.iterrows():
            table_row = []
            for col in pdf_columns:
                value = row.get(col, '')
                if isinstance(value, str) and len(str(value)) > 30:
                    table_row.append(Paragraph(str(value), wrap_style))
                else:
                    table_row.append(str(value))
            table_data.append(table_row)
        col_widths = []
        for col in pdf_columns:
            base_width = len(str(col)) * 5
            col_widths.append(min(base_width + 20, 150))  # Max 150 points
        t = Table(table_data, repeatRows=1)
        t.setStyle(TableStyle([
            # Header
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#198754')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
            
            # Data
            ('ALIGN', (0, 1), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            
            # Alternating row colors
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
            
            # Cell padding
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        
        elements.append(t)
        elements.append(Spacer(1, 20))
        footer_text = f"Page 1 of 1 | Generated through MaHIS"
        footer = Paragraph(footer_text, styles["Normal"])
        elements.append(footer)
        doc.build(elements)
        buffer.seek(0)
        filename = f"MaHIS_facility_report.pdf"
        
        return dcc.send_bytes(buffer.getvalue(), filename=filename)
    else:
        return dash.no_update
