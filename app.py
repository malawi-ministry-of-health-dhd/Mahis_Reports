import dash
from dash import html, dcc, page_container, page_registry, Output, Input, State, callback
import dash_mantine_components as dmc
import os
import json
import datetime
from datetime import datetime as dt
from isoweek import Week
from helpers.reports_class import ReportTableBuilder
import urllib.parse
import plotly.express as px
import pandas as pd
from flask import request, jsonify
from dash.exceptions import PreventUpdate
from config import PREFIX_NAME
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
from data_storage import DataStorage
import os

external_stylesheets = ['https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css']

# print(list(load_stored_data())) # Load the data to ensure it's available
# Initialize the Dash app
# pathname_prefix = '/reports/' # Adjust this if your app is served from a subpath
pathname_prefix = PREFIX_NAME if PREFIX_NAME else '/'
app = dash.Dash(
                __name__,
                use_pages=True,
                suppress_callback_exceptions=True,
                requests_pathname_prefix=pathname_prefix
                )
server = app.server

# MantineProvider wraps the whole app so DMC components work on any page
app.layout = dmc.MantineProvider(
    children=html.Div([
        dcc.Location(id='url', refresh=False),
        dcc.Store(id='url-params-store', storage_type='session'),
        html.Div(id="nav-container"),
        page_container,
    ], style={'margin': '20px', 'fontFamily': 'Arial, sans-serif'})
)

@app.callback(
    Output("nav-container", "children"),
    Input("url-params-store", "data")
)
def render_nav(url_params):
    try:
        location = url_params.get('Location', [None])[0] if url_params else None
        uuid = url_params.get('uuid', [None])[0] if url_params else None
        user_level = url_params.get('user_level', [None])[0] if url_params else None
        path = os.getcwd()
        timestamp_path = os.path.join(path, 'data','TimeStamp.csv')
        users_path = os.path.join(path, 'data','users_data.csv')
        last_updated = pd.read_csv(timestamp_path)['saving_time'].to_list()[0]
        users = pd.read_csv(users_path)

        query = ""
        if location and uuid and user_level:
            query = f"?Location={location}&uuid={uuid}&user_level={user_level}"
        elif location and uuid:
            query = f"?Location={location}&uuid={uuid}"
        elif location:
            query = f"?Location={location}"
        elif uuid:
            query = f"?uuid={uuid}"

        nav_with_admin = html.Nav([
                            html.Ul([
                                html.Li(html.A("Dashboard", href=f"{pathname_prefix}home{query}", className="nav-link")),
                                html.Li(html.A("HMIS DataSet Reports", href=f"{pathname_prefix}hmis_reports{query}", className="nav-link")),
                                html.Li(html.A("Program Reports", href=f"{pathname_prefix}program_reports{query}", className="nav-link")),
                                html.Li(html.A("Configure Reports", href=f"{pathname_prefix}reports_config{query}", className="nav-link")),
                                html.Div(
                                    f"Last updated on: {last_updated}",
                                    style={"color":"grey","font-size":"0.9rem","margin-top":"5px","font-style":"italic"}
                                )
                            ], className="nav-list")
                        ], className="navbar")
        nav_without_admin = html.Nav([
                                html.Ul([
                                    html.Li(html.A("Dashboard", href=f"{pathname_prefix}home{query}", className="nav-link")),
                                    html.Li(html.A("HMIS DataSet Reports", href=f"{pathname_prefix}hmis_reports{query}", className="nav-link")),
                                    html.Li(html.A("Program Reports", href=f"{pathname_prefix}program_reports{query}", className="nav-link")),
                                    html.Li(html.A("Configure Reports", href=f"{pathname_prefix}reports_config{query}", className="nav-link",
                                                style={'visibility': 'hidden', 'pointer-events': 'none', 'cursor': 'default'}),
                                                    style={'visibility': 'hidden'}),
                                    html.Div(
                                        f"Last updated on: {last_updated}",
                                        style={"color":"grey","font-size":"0.9rem","margin-top":"5px","font-style":"italic"}
                                    )
                                ], className="nav-list")
                            ], className="navbar")
        
        if uuid in users['user_id'].tolist():
            role_string = users.query(f'user_id == "{uuid}"')['role'].iloc[0]
            roles_list = [r.strip() for r in role_string.split(',')]
            print(roles_list)

            if "Superuser,Superuser," in roles_list:
                return nav_with_admin
            else:
                return nav_without_admin
        elif uuid == 'm3his@dhd':
            return nav_with_admin
        else:
            return 
    except Exception as e:
        import traceback
        traceback.print_exc()
        return nav_without_admin

@callback(
    Output('url-params-store', 'data'),
    Input('url', 'href')
)
def store_url_params(href):
    if not href:
        raise PreventUpdate
    parsed_url = urllib.parse.urlparse(href)
    params = urllib.parse.parse_qs(parsed_url.query)
    
    return params

@app.callback(
    Output('url', 'pathname'),
    Input('url', 'pathname'),
    prevent_initial_call=True
)
def redirect_to_home(pathname):
    if pathname == "/":
        return "/home"
    return pathname

@app.callback(
    [Output('home-link', 'href'),
     Output('hmis-reports-link', 'href'),
     Output('programs-link', 'href'),
     Output('admin-link', 'href'),
     Output('last_updated','children')
    ],
    Input('url-params-store', 'data')
)
def update_nav_links(url_params):
    try:
        location = url_params.get('Location', [None])[0] if url_params else None
        uuid = url_params.get('uuid', [None])[0] if url_params else None
        user_level = url_params.get('user_level', [None])[0] if url_params else None
        # print(f"Updating nav links with Location: {location}, UUID: {uuid}, User Level: {user_level}")
        # query = f"?Location={location}&uuid={uuid}" if location and uuid else f"?Location={location}" if location else f"?uuid={uuid}" if uuid else ""
        query = f"?Location={location}&uuid={uuid}&user_level={user_level}" if location and uuid and user_level else \
                f"?Location={location}&uuid={uuid}" if location and uuid else \
                f"?Location={location}&user_level={user_level}" if location and user_level else \
                f"?uuid={uuid}&user_level={user_level}" if uuid and user_level else \
                f"?Location={location}" if location else f"?uuid={uuid}" if uuid else f"?user_level={user_level}" if user_level else ""
        path = os.getcwd()
        json_path = os.path.join(path, 'data','TimeStamp.csv')
        last_updated = pd.read_csv(json_path)['saving_time'].to_list()[0]

        return (
            f"{pathname_prefix}home{query}",
            f"{pathname_prefix}hmis_reports{query}",
            f"{pathname_prefix}program_reports{query}",
            f"{pathname_prefix}reports_config{query}",
            f"Last updated on: {last_updated}"
        )
    except Exception as e:
        return (
            f"{pathname_prefix}home{query}",
            f"{pathname_prefix}hmis_reports{query}",
            f"{pathname_prefix}program_reports{query}",
            f"{pathname_prefix}reports_config{query}",
            f"Error loading last updated: {str(e)}"
        )


# Helper functions for date ranges (replicated from pages/reports.py)
relative_month = ['January', 'February', 'March', 'April', 'May', 'June','July', 'August', 'September', 'October', 'November', 'December']
relative_quarter = ["Q1Jan-Mar", "Q2Apr-June", "Q3Jul-Sep", "Q4Oct-Dec"]

def get_week_start_end(week_num, year):
    week = Week(int(year), int(week_num))
    start_date = week.monday()
    end_date = start_date + datetime.timedelta(days=6)
    return start_date, end_date

def get_month_start_end(month, year):
    month_index = relative_month.index(month) + 1
    start_date = datetime.date(int(year), month_index, 1)
    if month_index == 12:
        end_date = datetime.date(int(year) + 1, 1, 1) - datetime.timedelta(days=1)
    else:
        end_date = datetime.date(int(year), month_index + 1, 1) - datetime.timedelta(days=1)
    return start_date, end_date

def get_quarter_start_end(quarter, year):
    quarter_map = {
        "Q1Jan-Mar": (1, 3), "Q2Apr-June": (4, 6), "Q3Jul-Sep": (7, 9), "Q4Oct-Dec": (10, 12)
    }
    start_month, end_month = quarter_map[quarter]
    start_date = datetime.date(int(year), start_month, 1)
    if end_month == 12:
        end_date = datetime.date(int(year), 12, 31)
    else:
        end_date = datetime.date(int(year), end_month + 1, 1) - datetime.timedelta(days=1)
    return start_date, end_date

@server.route(f'/api/', methods=['GET'])
# this /api/route should return the following in json: /api/datasets, /api/reports, /api/indicators
def api_root():
    uuid_param = request.args.get('uuid')
    # allow certain uuids only
    allowed_uuids = ["m3his@dhd"]  # Example list of allowed UUIDs
    if uuid_param not in allowed_uuids:
        return jsonify({"error": "Unauthorized, Please supply id"}), 403
    else:
        return jsonify({
            "endpoints": {
                "datasets": "/api/datasets",
                "reports": "/api/reports",
                "indicators": "/api/indicators",
                "data_elements": "/api/dataElements"
            }
        })
    
@server.route(f'/api/reports', methods=['GET'])
def get_reports_list():
    uuid_param = request.args.get('uuid')
    # allow certain uuids only
    allowed_uuids = ["m3his@dhd"]  # Example list of allowed UUIDs
    if uuid_param not in allowed_uuids:
        return jsonify({"error": "Unauthorized, Please supply id"}), 403

    try:
        path = os.getcwd()
        reports_json = os.path.join(path, 'data', 'hmis_reports.json')
        with open(reports_json, "r") as f:
            json_data = json.load(f)

        reports = [
            {
                "report_id": r["page_name"],
                "report_name": r["report_name"],
                "date_updated": r["date_updated"]
            }
            for r in json_data.get("reports", []) 
            if r.get("archived", "").lower() == "false"
        ]

        return jsonify({"reports": reports})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@server.route(f'/api/datasets', methods=['GET'])
# example: http://localhost:8050/api/datasets?uuid=1&period=Monthly:January:2025&hf_code=SA091312&report_name=idsr_monthly
def get_report_dataset():
    # Parameters: UUID, Period (Format: "Type:Value:Year"), Health Facility ID, Report Name
    uuid_param = request.args.get('uuid')
    period_param = request.args.get('period') #Expected "Monthly:January:2025" or similar
    facility_id = request.args.get('hf_code') #MHFR
    report_name_id = request.args.get('report_name')

    if not all([period_param, facility_id, report_name_id]):
        return jsonify({"error": "Missing required parameters: Period, Health Facility ID, Report Name"}), 400

    try:
        # Parse Period
        period_parts = period_param.split(':')
        if len(period_parts) != 3:
            return jsonify({"error": "Invalid Period format. Expected 'Type:Value:Year' (e.g., 'Monthly:January:2025')"}), 400
        
        period_type, period_value, period_year = period_parts
        
        if period_type == 'Weekly':
            start_date, end_date = get_week_start_end(period_value, period_year)
        elif period_type == 'Monthly':
            start_date, end_date = get_month_start_end(period_value, period_year)
        elif period_type == 'Quarterly':
            start_date, end_date = get_quarter_start_end(period_value, period_year)
        else:
            return jsonify({"error": f"Invalid period type: {period_type}"}), 400
        
        # allow certain uuids only
        allowed_uuids = ["m3his@dhd"]  # Example list of allowed UUIDs
        if uuid_param not in allowed_uuids:
            return jsonify({"error": "Unauthorized, Please supply id"}), 403

        # Load Report Specs
        path = os.getcwd()
        reports_json = os.path.join(path, 'data', 'hmis_reports.json')
        with open(reports_json, "r") as f:
            json_data = json.load(f)
        
        
        report = next((r for r in json_data["reports"] if r['page_name'] == report_name_id and r["archived"].lower() == "false"), None)
        if not report:
            return jsonify({"error": "Report Not Found"}), 404

        # Load Data
        parquet_path = os.path.join(path, 'data', 'latest_data_opd.parquet')
        if not os.path.exists(parquet_path):
            return jsonify({"error": "Data file not found"}), 500
        
        SQL = f"""
            SELECT *
            FROM 'data/{DATA_FILE_NAME_}'
            WHERE {FACILITY_CODE_} = '{facility_id}'
            """
        data = DataStorage.query_duckdb(SQL)
        data[DATE_] = pd.to_datetime(data[DATE_], format='mixed')
        data[GENDER_] = data[GENDER_].replace({"M":"Male","F":"Female"})
        data["DateValue"] = pd.to_datetime(data[DATE_]).dt.date
        today = dt.today().date()
        data["months"] = data["DateValue"].apply(lambda d: (today - d).days // 30)

        filtered = data[
            (pd.to_datetime(data['Date']) >= pd.to_datetime(start_date)) &
            (pd.to_datetime(data['Date']) <= pd.to_datetime(end_date))
        ]
        
        original_data = data[data['Date'] <= pd.to_datetime(end_date)].copy()
        original_data["days_before"] = original_data["DateValue"].apply(lambda d: (start_date - d).days)
        # Build Report
        spec_path = os.path.join(path, "data", "uploads", f"{report['page_name']}.xlsx")
        if not os.path.exists(spec_path):
            return jsonify({"error": "Report template not found"}), 500

        builder = ReportTableBuilder(spec_path, filtered, original_data)
        builder.load_spec()
        sections = builder.build_section_tables()
        section_ids = builder.build_section_tables_with_ids()

        # Prepare Response
        test_data = []
        response_data = []
        for (section1_name, df1), (section2_name,df2) in zip(sections, section_ids):
            # Melt dataframes to ensure linear json

            # group 1df
            id1_col = 'Data Element'
            value1_cols = [col for col in df1.columns if col != id1_col and col != 'Section']
            df1_long = df1.melt(
                id_vars=[col for col in df1.columns if col in ['Section', id1_col]], 
                value_vars=value1_cols,
                var_name='Category', 
                value_name='Value'
            )
            df1_long[id1_col] = df1_long[id1_col].astype(str) + ' ' + df1_long['Category'].astype(str)
            result1 = df1_long.drop(columns=['Category'])

            # group 2df
            id2_col = 'Data Element'
            value2_cols = [col for col in df2.columns if col != id2_col and col != 'Section']
            df2_long = df2.melt(
                id_vars=[col for col in df2.columns if col in ['Section', id2_col]], 
                value_vars=value2_cols,
                var_name='Category', 
                value_name='Value'
            )
            df2_long[id2_col] = df2_long[id2_col].astype(str) + ' ' + df2_long['Category'].astype(str)
            result2 = df2_long.drop(columns=['Category']).rename(columns={"Value":"Code"})
            combined_df = pd.merge(result1, result2,on="Data Element", how='inner')
            # Ensure code is always available
            final_df = combined_df[combined_df['Code'] !=""]
            
            response_data.append({
                "section_name": section1_name,
                "data": final_df.to_dict(orient='records')
            })

        return jsonify({
            "report_id": report_name_id,
            "report_name": report['report_name'],
            "facility_id": facility_id,
            "period": period_param,
            "sections": response_data
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Run the app
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8050, debug=True,)