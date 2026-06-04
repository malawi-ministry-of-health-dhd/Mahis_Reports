import dash
from dash import html, dcc, dash_table, Input, Output, State, callback
import json
import os
import pandas as pd
from datetime import datetime
import datetime as dt
import base64
import io
import uuid
from data_storage import DataStorage
from config import (actual_keys_in_data, 
                    DATA_PATH_, 
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

path = os.getcwd()
path_dcc_json = os.path.join(path, 'data/default', 'dcc_dropdown_json','dropdowns.json')
with open(path_dcc_json) as r:
    dcc_json = json.load(r)

drop_down_programs = dcc_json['programs']
drop_down_encounters = dcc_json['encounters']
drop_down_concepts = dcc_json['concepts']
aggregations = ["nunique", "sum", "count", "mean", "min", "max","time_diff_mins","time_diff_hour","std","var","list"]
user_levels = ['national', 'district', 'facility']

# DATASET
def validate_excel_file(contents):
    """Validate the uploaded Excel file"""
    try:
        content_type, content_string = contents.split(',')
        decoded = base64.b64decode(content_string)
        
        # Read the Excel file
        excel_file = pd.ExcelFile(io.BytesIO(decoded))
        
        # Check required sheets
        required_sheets = ['VARIABLE_NAMES', 'FILTERS', 'DESIGN', 'REPORT_NAME']
        missing_sheets = [sheet for sheet in required_sheets if sheet not in excel_file.sheet_names]
        
        if missing_sheets:
            return False, f"Missing required sheets: {', '.join(missing_sheets)}", None, None
        
        # Check REPORT_NAME sheet for id and name columns
        report_name_df = pd.read_excel(excel_file, sheet_name='REPORT_NAME')
        if 'id' not in report_name_df.columns:
            return False, "REPORT_NAME sheet is missing 'id' column", None, None
        
        if 'name' not in report_name_df.columns:
            return False, "REPORT_NAME sheet is missing 'name' column", None, None
        
        if report_name_df.empty or pd.isna(report_name_df['id'].iloc[0]):
            return False, "REPORT_NAME id column is empty", None, None
        
        if report_name_df.empty or pd.isna(report_name_df['name'].iloc[0]):
            return False, "REPORT_NAME name column is empty", None, None
        
        # Check if sheet name VARIABLE_NAMES and FILTERS has at least on row
        variable_names_df = pd.read_excel(excel_file, sheet_name='VARIABLE_NAMES')
        if 'type' in variable_names_df.columns:
            variable_names_df = variable_names_df[variable_names_df['type']!='section']
        if variable_names_df.empty:
            return False, "VARIABLE_NAMES sheet is empty, add atleast 1 variable", None, None
        filters_df = pd.read_excel(excel_file, sheet_name='FILTERS')
        if filters_df.empty:
            return False, "FILTERS sheet is empty, add atleast 1 filter", None,None
        
        # Check if all filters from Column B to K of VARIABLE_NAMES exist in FILTERS Column A
        variable_filters = variable_names_df.iloc[:, 1:20].values.flatten()
        variable_filters = [str(item).strip() for item in variable_filters if pd.notna(item) and str(item).strip() != '']
        filters_list = filters_df.iloc[:, 0].astype(str).str.strip().tolist()
        missing_filters = set([vf for vf in variable_filters if vf not in filters_list])
        # print(missing_filters)
        if len(missing_filters)>0:
            return False, f"The following filters from VARIABLE_NAMES are missing in FILTERS sheet: {', '.join(missing_filters)}", None, None
        

        return True, "File validation successful", report_name_df, filters_df
        
    except Exception as e:
        return False, f"Error reading file: {str(e)}", None, None
    
def validate_dashboard_json(contents):
    """
    Validates that the uploaded JSON file:
    - Is a list
    - Contains objects with required keys
    - visualization_types must have counts or charts
    - counts objects must contain id, name, and filters
    """

    try:
        data = json.loads(contents)

        def _flatten_values(value):
            if isinstance(value, list):
                return [v for v in value if v not in (None, "")]
            if value in (None, ""):
                return []
            return [value]

        def _invalid_columns(filters, keys_to_check):
            invalid = []
            for key in keys_to_check:
                if key not in filters:
                    continue
                for value in _flatten_values(filters.get(key)):
                    if value not in actual_keys_in_data:
                        invalid.append(str(value))
            return invalid

        if not isinstance(data, list) or len(data) == 0:
            return False, "JSON must be a non-empty list of dashboard objects."

        for item in data:
            required_keys = ["report_id", "report_name", "visualization_types"]
            if not all(k in item for k in required_keys):
                return False, "One or more dashboard objects are missing required keys."

            vis = item.get("visualization_types", {})

            if not isinstance(vis, dict):
                return False, "'visualization_types' must be an object."

            counts = vis.get("counts", [])
            charts = vis.get("charts", {})
            sections = charts.get("sections", []) if isinstance(charts, dict) else []
            priority_indicators = item.get("priority_indicators", []) or vis.get("priority_indicators", [])

            if len(counts) == 0 and len(sections) == 0 and len(priority_indicators) == 0:
                return False, (
                    "Each dashboard must contain counts, chart sections, or MNID priority indicators."
                )
            for c in counts:
                if not isinstance(c, dict):
                    return False, "Each item in 'counts' must be an object."
                required_count_keys = ["id", "name", "filters"]
                if not all(k in c for k in required_count_keys):
                    return False, (
                        "Each item in 'counts' must contain 'id', 'name', and 'filters'."
                    )
                if not isinstance(c["filters"], dict):
                    return False, "'filters' in counts must be a dict."

                selected_values = _invalid_columns(
                    c["filters"],
                    ["unique", "variable1", "variable2", "variable3", "variable4", "variable5", "variable6", "variable7", "variable8"]
                )
                if len(selected_values) > 0:
                    return False, f"The following filter values in counts are invalid data columns: {', '.join(selected_values)}"

            for chart in sections:
                for ch in chart['items']:
                    if not isinstance(ch, dict):
                        return False, "Each item in 'charts' must be an object."
                    required_chart_keys = ["id", "name", "type", "filters"]
                    if not all(k in ch for k in required_chart_keys):
                        return False, (
                            "Each item in 'charts' must contain 'id', 'name', 'type', and 'filters'."
                        )
                    if not isinstance(ch["filters"], dict):
                        return False, "'filters' in charts must be a dict."

                    selected_values = _invalid_columns(
                        ch["filters"],
                        [
                            "date_col", "y_col", "label_col", "value_col", "names_col",
                            "values_col", "x_col", "index_col1", "columns", "unique_column",
                            "filter_col1", "filter_col2", "filter_col3", "filter_col4", "filter_col5",
                            "age_col", "gender_col"
                        ]
                    )
                    if len(selected_values) > 0:
                        return False, f"The following filter values in charts are invalid data columns: {', '.join(selected_values)}"

            for indicator in priority_indicators:
                if not isinstance(indicator, dict):
                    return False, "Each MNID indicator must be an object."
                required_indicator_keys = ["id", "label", "status"]
                if not all(k in indicator for k in required_indicator_keys):
                    return False, "Each MNID indicator must contain 'id', 'label', and 'status'."

                for filter_key in ["numerator_filters", "denominator_filters"]:
                    filter_value = indicator.get(filter_key)
                    if filter_value is None:
                        continue
                    if not isinstance(filter_value, dict):
                        return False, f"'{filter_key}' in MNID indicators must be a dict."
                    invalid_columns = _invalid_columns(
                        filter_value,
                        ["unique", "variable1", "variable2", "variable3", "variable4", "variable5", "variable6", "variable7", "variable8"]
                    )
                    if invalid_columns:
                        return False, f"The following MNID filter values are invalid data columns: {', '.join(invalid_columns)}"
        return True, "Dry run successful! JSON structure is valid."

    except Exception as e:
        import traceback
        traceback.print_exc()
        return False, f"Invalid JSON format: {e}"

def upload_dashboard_json(contents):
    if contents is None:
        return "No file to upload"
    dashboards_json_path = os.path.join(path, 'data','visualizations', 'validated_dashboard.json')
    try:
        content_type, content_string = contents.split(',')
        decoded_bytes = base64.b64decode(content_string)
    except Exception as e:
        return f"Failed to decode file: {e}"
    try:
        json.loads(decoded_bytes.decode('utf-8'))
    except Exception as e:
        return f"JSON validation failed before saving: {e}"
    with open(dashboards_json_path, 'wb') as f:
        f.write(decoded_bytes)

    return "Upload successful!"

# Clinical Reports Upload and Dry Run
def validate_prog_reports_json(contents):
    """
    Validates that the uploaded JSON file:
    - Is a list
    - Contains objects with required keys
    - visualization_types must have counts or charts
    - counts objects must contain id, name, and filters
    """

    actual_keys_in_data = ['person_id', 'encounter_id', 
                                       'Gender', 'Age', 'Age_Group', 
                                       'Date', 'Program', 'Facility', 
                                       'Facility_CODE', 'User', 'District', 
                                       'Encounter', 'Home_district', 'TA', 
                                       'Village', 'visit_days', 'obs_value_coded', 
                                       'concept_name', 'Value',"",
                                       'ValueN', 'DrugName', 'Value_name', 'new_revisit','count','count_set','sum']
    try:
        data = json.loads(contents)
        if not isinstance(data, dict):
            return False, "JSON must be a dict object."

        for item in data['reports']:
            required_keys = ["id", "report_name","program", "type", "filters"]
            if not all(k in item for k in required_keys):
                return False, "Report objects are missing required keys. Required: id, report_name,program, type, filters"

            vis = item.get("filters", {})
            if not isinstance(vis, dict):
                return False, "'filters' must be an object."
            
            target_keys = ["date_col","y_col","label_col","value_col",
                                "names_col","values_col","x_col","index_col1","columns",
                                "values_col","unique_column","filter_col1","filter_col2","filter_col3"]
            selected_values = []
            for key in target_keys:
                if key in vis:
                    if vis[key] not in actual_keys_in_data:
                        if isinstance(vis[key], list):
                            for v in vis[key]:
                                if v not in actual_keys_in_data:
                                    selected_values.append(v)
                        else:
                            selected_values.append(vis[key])
            if len(selected_values)>0:
                return False, f"The following filter values in charts are invalid data columns: {', '.join(selected_values)}"
        return True, "Dry run successful! JSON structure is valid."

    except Exception as e:
        import traceback
        traceback.print_exc()
        return False, f"Invalid JSON format: {e}"

def upload_prog_reports_json(contents):
    if contents is None:
        return "No file to upload"
    dashboards_json_path = os.path.join(path, 'data','visualizations', 'validated_prog_reports.json')
    try:
        content_type, content_string = contents.split(',')
        decoded_bytes = base64.b64decode(content_string)
    except Exception as e:
        return f"Failed to decode file: {e}"
    try:
        json.loads(decoded_bytes.decode('utf-8'))
    except Exception as e:
        return f"JSON validation failed before saving: {e}"
    with open(dashboards_json_path, 'wb') as f:
        f.write(decoded_bytes)

    return "Upload successful!"
    
def load_reports_data():
    """Load reports from reports.json"""
    file_path = os.path.join("data", "hmis_reports.json")
    
    if not os.path.exists(file_path):
        return {"reports": []}
    
    with open(file_path, "r") as f:
        return json.load(f)


def save_reports_data(data):
    """Save reports to reports.json"""
    file_path = os.path.join("data", "hmis_reports.json")
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    
    with open(file_path, "w") as f:
        json.dump(data, f, indent=2)


def check_existing_report(page_name):
    """Check if a report with the given page_name already exists"""
    data = load_reports_data()
    existing_reports = data.get("reports", [])
    
    for report in existing_reports:
        if report.get("page_name") == page_name:
            return True, report
    
    return False, None


def get_next_report_id():
    """Get the next incremental report_id"""
    data = load_reports_data()
    existing_reports = data.get("reports", [])
    
    if not existing_reports:
        return 1
    
    max_id = max(report.get("report_id", 0) for report in existing_reports)
    return max_id + 1


def update_or_create_report(report_name_df, is_update=False, existing_report=None):
    """Update existing report or create new one in reports.json"""
    data = load_reports_data()
    current_time = datetime.now().strftime("%Y-%m-%d")
    
    page_name = report_name_df['id'].iloc[0]
    report_name = report_name_df['name'].iloc[0]
    program_name = report_name_df['programs'].iloc[0]
    
    if is_update and existing_report:
        # Update existing report
        for report in data["reports"]:
            if report.get("page_name") == page_name:
                report["report_name"] = report_name
                report["programs"] = [program_name]
                report["date_updated"] = current_time
                report["updated_by"] = "admin"
                report["archived"] = "False"
                break
    else:
        # Create new report
        new_report = {
            "report_id": get_next_report_id(),
            "report_name": report_name,
            "date_created": current_time,
            "creator": "admin",
            "programs": [program_name],
            "date_updated": current_time,
            "updated_by": "admin",
            "page_name": page_name,
            "archived": "False"
        }
        data["reports"].append(new_report)
    
    save_reports_data(data)
    return data


def load_excel_file(page_name):
    """Load Excel file for editing"""
    file_path = os.path.join("data", "uploads", f"{page_name}.xlsx")
    if not os.path.exists(file_path):
        return None
    
    return pd.ExcelFile(file_path)


def save_excel_file(page_name, sheet_data):
    """Save edited data back to Excel file"""
    file_path = os.path.join("data", "uploads", f"{page_name}.xlsx")
    
    with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
        for sheet_name, df in sheet_data.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)

def update_report_metadata(report_id):
    """Update the date_updated and updated_by in reports.json"""
    data = load_reports_data()
    current_time = datetime.now().strftime("%Y-%m-%d")
    
    for report in data["reports"]:
        if report.get("report_id") == report_id:
            report["date_updated"] = current_time
            report["updated_by"] = "admin"
            break
    
    save_reports_data(data)


def archive_report(report_id):
    """Archive a report by setting archived to True"""
    data = load_reports_data()
    current_time = datetime.now().strftime("%Y-%m-%d")
    
    for report in data["reports"]:
        if report.get("report_id") == report_id:
            report["archived"] = "True"
            report["date_updated"] = current_time
            report["updated_by"] = "admin"
            break
    
    save_reports_data(data)

# Preview Data
def load_preview_data():
    """Load preview data from parquet file"""
    file_path = os.path.join("data", "concepts_data.csv")
    if not os.path.exists(file_path):
        return pd.DataFrame(), "Empty Reference"
    
    try:
        df = pd.read_csv(file_path)
        return df, None
    except Exception as e:
        return None, f"Error loading data: {str(e)}"

# DASHBOARDS 
def create_chart_fields(chart_type, chart_data=None, section_index=None, chart_index=None):
    chart_data = chart_data or {}
    filters = chart_data.get("filters", {})

    # if chart_type not in CHART_TEMPLATES:
    #     return html.Div("Invalid chart type")

    template = CHART_TEMPLATES["Chart"]
    dropdown_options = ['Date','person_id', 'encounter_id', 'Gender', 'Program', 'Encounter',
                        'obs_value_coded', 'concept_name', 'Value', 'ValueN', 'DrugName', 'Value_name','User']
    
    # Define which fields are relevant for each chart type
    chart_type_fields = {
        "Line": ["date_col", "y_col", "x_title", "y_title", "legend_title", "color", "unique_column"],
        "Bar": ["label_col", "value_col", "x_title", "y_title", "top_n", "unique_column"],
        "Pie": ["names_col", "values_col", "colormap", "unique_column"],
        "Column": ["x_col", "y_col", "x_title", "y_title", "legend_title", "color", "unique_column"],
        "Histogram": ["age_col", "gender_col", "bin_size", "color", "unique_column"],
        "PivotTable": ["index_col1", "columns", "values_col", "aggfunc", "unique_column"]
    }
    
    # Common fields for all chart types
    common_fields = ["title", "duration_default", "filter_col1", "filter_val1", "filter_col2", "filter_val2", 
                     "filter_col3", "filter_val3", "filter_col4", "filter_val4", "filter_col5", "filter_val5",
                     "custom_fields"]
    
    # Combine all fields that should be visible for this chart type
    visible_fields = set(chart_type_fields.get(chart_type, []) + common_fields)
    
    # All possible fields (complete list)
    all_fields = [
        "date_col", "y_col", "x_col", "label_col", "value_col", "names_col", "values_col",
        "age_col", "gender_col", "index_col1", "columns", "aggfunc",
        "x_title", "y_title", "legend_title", "color", "top_n", "bin_size", "colormap",
        "unique_column", "title", "duration_default",
        "filter_col1", "filter_val1", "filter_col2", "filter_val2", "filter_col3", "filter_val3",
        "filter_col4", "filter_val4", "filter_col5", "filter_val5","custom_fields"
    ]
    
    FIELD_CONFIG = {
        "date_col": {"type": "single", "options": ["Date"]},
        "y_col": {"type": "single", "options": dropdown_options},
        "unique_column": {"type": "single", "options": ["person_id", "encounter_id"]},
        "label_col": {"type": "single", "options": dropdown_options},
        "value_col": {"type": "single", "options": dropdown_options},
        "names_col": {"type": "single", "options": dropdown_options},
        "values_col": {"type": "single", "options": dropdown_options},
        "x_col": {"type": "single", "options": dropdown_options},
        "age_col": {"type": "single", "options": ["Age"]},
        "gender_col": {"type": "single", "options": ["Gender"]},
        "index_col1": {"type": "multi", "options": dropdown_options},
        "columns": {"type": "multi", "options": dropdown_options},
        "aggfunc": {"type": "multi", "options": aggregations},
        "filter_col1": {"type": "multi", "options": dropdown_options},
        "filter_col2": {"type": "multi", "options": dropdown_options},
        "filter_col3": {"type": "multi", "options": dropdown_options},
        "filter_col4": {"type": "multi", "options": dropdown_options},
        "filter_col5": {"type": "multi", "options": dropdown_options},
        "filter_val1": {"type": "", "options": None},
        "filter_val2": {"type": "", "options": None},
        "filter_val3": {"type": "", "options": None},
        "filter_val4": {"type": "", "options": None},
        "filter_val5": {"type": "", "options": None},
        "custom_fields": {"type": "", "options": None},
        "duration_default": {"type": "single", "options": ["any", "7days", "30days", "90days"]},
        "top_n": {"type": "single", "options": None},
        "colormap": {"type": "textarea", "options": None},
        "bin_size": {"type": "single", "options": None},
        "color": {"type": "single", "options": None},
        "x_title": {"type": "single", "options": None},
        "y_title": {"type": "single", "options": None},
        "legend_title": {"type": "single", "options": None},
        "title": {"type": "single", "options": None},
    }

    grid_items = []

    # Render ALL fields, but hide irrelevant ones with CSS
    for element in all_fields:
        if element not in template:
            continue
            
        current_value = filters.get(element, template.get(element, ""))
        
        if current_value is None:
            current_value = "" if FIELD_CONFIG.get(element, {}).get("type") == "single" else []
        
        # Use section and index for field IDs
        field_id = {"type": f"chart-{element}", "section": section_index, "index": chart_index}
        
        # Determine if this field should be visible
        is_visible = element in visible_fields
        display_style = "" if is_visible else "none"
        
        if element in FIELD_CONFIG:
            config = FIELD_CONFIG[element]
            field_type = config.get("type", "single")
            
            if field_type == "multi":
                options = config["options"] if config.get("options") else []
                dropdown_opts = [{"label": opt, "value": opt} for opt in options] if options else []
                
                if isinstance(current_value, str) and current_value:
                    current_value = [current_value]
                elif not isinstance(current_value, list):
                    current_value = []
                
                component = html.Div(
                    className="chart-field",
                    style={"display": display_style},
                    children=[
                        html.Label(element.replace("_", " ").title(), className="form-label"),
                        dcc.Dropdown(
                            id=field_id,
                            options=dropdown_opts,
                            value=current_value,
                            placeholder=f"Select {element.replace('_', ' ')}",
                            className="form-input",
                            multi=True,
                            clearable=True
                        )
                    ]
                )
            
            elif field_type == "single" and config.get("options"):
                dropdown_opts = [{"label": opt, "value": opt} for opt in config["options"]]
                
                component = html.Div(
                    className="chart-field",
                    style={"display": display_style},
                    children=[
                        html.Label(element.replace("_", " ").title(), className="form-label"),
                        dcc.Dropdown(
                            id=field_id,
                            options=dropdown_opts,
                            value=current_value if current_value else None,
                            placeholder=f"Select {element.replace('_', ' ')}",
                            className="form-input",
                            clearable=True
                        )
                    ]
                )
            
            elif field_type == "textarea":
                component = html.Div(
                    className="chart-field",
                    style={"display": display_style},
                    children=[
                        html.Label(element.replace("_", " ").title(), className="form-label"),
                        dcc.Textarea(
                            id=field_id,
                            value=json.dumps(current_value if isinstance(current_value, dict) else {}, indent=2),
                            className="form-input",
                            style={"height": "80px", "resize": "vertical"}
                        )
                    ]
                )
            
            else:
                component = html.Div(
                    className="chart-field",
                    style={"display": display_style},
                    children=[
                        html.Label(element.replace("_", " ").title(), className="form-label"),
                        dcc.Input(
                            id=field_id,
                            value=str(current_value) if current_value else "",
                            placeholder=f"Enter {element.replace('_', ' ')}",
                            className="form-input",
                            type="text"
                        )
                    ]
                )
        grid_items.append(component)
    
    return html.Div(className="chart-grid", children=grid_items)

def render_filter_rows(count_idx, filter_pairs):
    """Render the dynamic variable/value filter rows for a count item."""
    col_options = [{"label": k, "value": k} for k in actual_keys_in_data]
    rows = []
    for fi, (var, val) in enumerate(filter_pairs):
        remove_btn = html.Button(
            "×",
            id={"type": "count-remove-filter", "count": count_idx, "filter": fi},
            n_clicks=0,
            className="btn-danger btn-small",
            style={"flexShrink": "0", "height": "32px"},
        ) if len(filter_pairs) > 1 else html.Div(style={"width": "32px"})

        rows.append(html.Div(
            style={"display": "flex", "gap": "6px", "alignItems": "center", "marginBottom": "6px"},
            children=[
                dcc.Dropdown(
                    id={"type": "count-var", "count": count_idx, "filter": fi},
                    value=var if var else None,
                    options=col_options,
                    placeholder="Select column",
                    className="form-input",
                    clearable=True,
                    style={"flex": "1", "minWidth": "140px"},
                ),
                dcc.Input(
                    id={"type": "count-val", "count": count_idx, "filter": fi},
                    value=str(val) if val not in (None, "") else "",
                    placeholder="Value (use * prefix for wildcard)",
                    className="form-input",
                    type="text",
                    style={"flex": "1"},
                ),
                remove_btn,
            ]
        ))
    return rows


def create_count_item(count_data=None, index=None):
    count_data = count_data or {}
    filters = count_data.get("filters", {})

    # Collect existing variable/value pairs from the filters dict
    filter_pairs = []
    for i in range(1, 11):
        var_key = f"variable{i}"
        val_key = f"value{i}"
        if var_key in filters:
            var = filters[var_key] or ""
            val = filters.get(val_key, "")
            if isinstance(val, list):
                val = ", ".join(str(v) for v in val if v not in (None, ""))
            filter_pairs.append((var, str(val) if val not in (None, "") else ""))
    if not filter_pairs:
        filter_pairs = [("", "")]

    return html.Div(className="count-item", children=[
        # ── Close bar ────────────────────────────────────────────────────────
        html.Div(
            style={"display": "flex", "justifyContent": "space-between", "alignItems": "center",
                   "marginBottom": "8px", "paddingBottom": "6px", "borderBottom": "1px solid #e5e7eb"},
            children=[
                html.Span(
                    f"Metric: {count_data.get('name', 'New Metric') or 'New Metric'}",
                    style={"fontSize": "13px", "fontWeight": "600", "color": "#374151"},
                ),
                html.Button(
                    "✕ Close",
                    id={"type": "close-count-form", "index": index},
                    n_clicks=0,
                    className="btn-secondary btn-small",
                    title="Close this form",
                    style={"fontSize": "12px"},
                ),
            ],
        ),
        # ── Row 1: metadata ──────────────────────────────────────────────────
        html.Div(style={"display": "flex", "gap": "5px", "flexWrap": "wrap"}, children=[
            html.Div(className="count-col", style={"display": "none"}, children=[
                html.Label("ID *", className="form-label-disabled"),
                dcc.Input(
                    id={"type": "count-id", "index": index},
                    value=count_data.get("id", f"count_{uuid.uuid4().hex[:8]}"),
                    disabled=True,
                    className="form-input",
                ),
            ]),
            html.Div(className="count-col", children=[
                html.Label("Metric Title *", className="form-label"),
                dcc.Input(
                    id={"type": "count-name", "index": index},
                    value=count_data.get("name", ""),
                    placeholder="e.g. All Attendance",
                    className="form-input",
                ),
            ]),
            html.Div(className="count-col", children=[
                html.Label("Aggregation", className="form-label"),
                dcc.Dropdown(
                    id={"type": "count-aggregations", "index": index},
                    value=filters.get("measure", "nunique"),
                    options=[{"label": a, "value": a} for a in aggregations],
                    className="form-input",
                    clearable=False,
                ),
            ]),
            html.Div(className="count-col", children=[
                html.Label("Using Column", className="form-label"),
                dcc.Dropdown(
                    id={"type": "count-unique", "index": index},
                    value=filters.get("unique", "person_id"),
                    options=[{"label": k, "value": k} for k in actual_keys_in_data],
                    className="form-input",
                    clearable=False,
                ),
            ]),
            html.Div(className="count-col", children=[
                html.Label("Level", className="form-label"),
                dcc.Dropdown(
                    id={"type": "count-level", "index": index},
                    value=count_data.get("level", "facility"),
                    options=[{"label": v, "value": v} for v in ["facility", "district", "national"]],
                    className="form-input",
                    clearable=False,
                ),
            ]),
            html.Div(className="count-col", children=[
                html.Label("Flag", className="form-label"),
                dcc.Dropdown(
                    id={"type": "count-flag", "index": index},
                    value=count_data.get("flag", None),
                    options=[{"label": v, "value": v} for v in ["ok", "warn", "danger"]],
                    className="form-input",
                    clearable=True,
                    placeholder="None",
                ),
            ]),
            html.Div(className="count-col", children=[
                html.Label("Display Average", className="form-label"),
                dcc.Dropdown(
                    id={"type": "count-display-average", "index": index},
                    value=count_data.get("display_average", None),
                    options=[{"label": "Yes", "value": "True"}, {"label": "No", "value": "False"}],
                    className="form-input",
                    clearable=True,
                    placeholder="None",
                ),
            ]),
            html.Div(className="count-col", children=[
                html.Label("Link (href)", className="form-label"),
                dcc.Input(
                    id={"type": "count-href", "index": index},
                    value=count_data.get("href", ""),
                    placeholder="e.g. program_reports",
                    className="form-input",
                ),
            ]),
            html.Div(className="count-col", children=[
                html.Label("Link Label", className="form-label"),
                dcc.Input(
                    id={"type": "count-href-name", "index": index},
                    value=count_data.get("href_name", ""),
                    placeholder="e.g. view patients",
                    className="form-input",
                ),
            ]),
            html.Div(className="count-col", children=[
                html.Label("Actions", className="form-label"),
                html.Button(
                    "Save",
                    id={"type": "save-count", "index": index},
                    n_clicks=0,
                    className="btn-save btn-small",
                ),
                html.Button(
                    "🗑️",
                    id={"type": "remove-count", "index": index},
                    n_clicks=0,
                    className="btn-danger btn-small",
                ),
            ]),
        ]),

        # ── Row 2: dynamic filters ────────────────────────────────────────────
        html.Div(style={"marginTop": "10px", "padding": "10px", "background": "#f9fafb",
                         "borderRadius": "6px", "border": "1px solid #e5e7eb"}, children=[
            html.Div(style={"display": "flex", "alignItems": "center", "marginBottom": "8px",
                             "gap": "10px"}, children=[
                html.Label("Filters", className="form-label",
                           style={"margin": "0", "fontWeight": "600"}),
                html.Button(
                    "+ Add Filter",
                    id={"type": "count-add-filter", "count": index},
                    n_clicks=0,
                    className="btn-primary btn-small",
                ),
            ]),
            html.Div(
                id={"type": "count-filters-container", "count": index},
                children=render_filter_rows(index, filter_pairs),
            ),
        ]),
    ])

def create_chart_item(chart_data=None, section_index=None, chart_index=None):
    chart_data = chart_data or {}
    chart_type = chart_data.get('type', 'Bar')
    chart_id = chart_data.get('id', f'chart_{uuid.uuid4().hex[:8]}')
    
    return html.Div(className="chart-item", children=[
        html.Div(style={"display": "flex","gap":"5px"}, children=[
            html.Div(className="chart-col", children=[
                html.Label("Chart ID *", className="form-label-disabled"),
                dcc.Input(
                    id={"type": "chart-id", "section": section_index, "index": chart_index},
                    value=chart_id,
                    placeholder="chart_id",
                    disabled=True,
                    className="form-input"
                ),
            ]),
            html.Div(className="chart-col", children=[
                html.Label("Chart Name *", className="form-label"),
                dcc.Input(
                    id={"type": "chart-name", "section": section_index, "index": chart_index},
                    value=chart_data.get('name', ''),
                    placeholder="Chart Display Name",
                    className="form-input"
                ),
            ]),
            html.Div(className="chart-col", children=[
                html.Label("Chart Type *", className="form-label"),
                dcc.Dropdown(
                    id={"type": "chart-type", "section": section_index, "index": chart_index},
                    options=[{'label': t, 'value': t} for t in CHART_TEMPLATES_ORIGINAL.keys()],
                    value=chart_type,
                    className="dropdown"
                ),
            ]),
            html.Div(className="chart-col", children=[
                html.Label("Level", className="form-label"),
                dcc.Dropdown(
                    id={"type": "chart-level", "section": section_index, "index": chart_index},
                    value=chart_data.get('level', 'facility'),
                    options=[{'label': v, 'value': v} for v in ['facility', 'district', 'national']],
                    className="dropdown",
                    clearable=False,
                ),
            ]),
            html.Div(className="chart-col", children=[
                html.Label("Actions", className="form-label"),
                html.Button(
                    "Save", 
                    id={"type": "save-chart", "section": section_index, "index": chart_index},
                    n_clicks=0,
                    className="btn-save btn-small"
                ),
                html.Button(
                    "Delete", 
                    id={"type": "remove-chart", "section": section_index, "index": chart_index},
                    n_clicks=0,
                    className="btn-danger btn-small"
                )
            ]),
        ]),
        html.Div(
            id={"type": "chart-fields", "section": section_index, "index": chart_index},
            children=create_chart_fields(chart_type, chart_data, section_index, chart_index)
        ),
    ])

def create_section(section_data=None, index=None, active_chart_index=None):
    section_data = section_data or {}
    items = section_data.get('items', [])

    # Only render the one active chart (or none)
    if active_chart_index is not None and 0 <= active_chart_index < len(items):
        initial_charts = [create_chart_item(items[active_chart_index], index, active_chart_index)]
    else:
        initial_charts = []

    chart_count_label = html.Span(
        f"{len(items)} chart(s) in section — click a chart in the list to edit",
        style={"fontSize": "12px", "color": "#6b7280", "marginLeft": "8px"}
    ) if items and not initial_charts else None

    return html.Div(className="section-item", children=[
        html.Div(className="card-header", children=[
            html.Div(className="section-header", children=[
                html.Div(className="section-col", children=[
                    html.Label("Section Name *", className="form-label"),
                    dcc.Input(
                        id={"type": "section-name", "index": index},
                        value=section_data.get('section_name', ' '),
                        placeholder="e.g Attendance",
                        className="form-input"
                    ),
                ]),
                html.Div(className="section-col", children=[
                    html.Label("Charts Per Row", className="form-label"),
                    dcc.Input(
                        id={"type": "section-chart-items-per-row", "index": index},
                        value=section_data.get('chart_items_per_row', 2),
                        type="number",
                        min=1,
                        max=6,
                        placeholder="2",
                        className="form-input",
                        style={"width": "80px"},
                    ),
                ]),
                html.Div(className="section-col", children=[
                    html.Label("Actions", className="form-label"),
                    html.Button("🗑️ Remove Section",
                              id={"type": "remove-section", "index": index},
                              n_clicks=0,
                              className="btn-danger"),
                    html.Button("✕ Close",
                              id={"type": "close-section-form", "index": index},
                              n_clicks=0,
                              className="btn-secondary btn-small",
                              title="Close this form",
                              style={"marginLeft": "6px", "fontSize": "12px"}),
                ]),
            ]),
        ]),
        html.Div(className="card-body", children=[
            html.Div(style={"display": "flex", "alignItems": "center", "marginBottom": "8px"}, children=[
                html.Button("+ Add Chart",
                          id={"type": "add-chart-btn", "index": index},
                          n_clicks=0,
                          className="btn-primary"),
                chart_count_label,
            ]),
            html.Div(id={"type": "charts-container", "index": index, "section": index},
                    className="charts-container",
                    children=initial_charts),
        ]),
    ])

def _create_mnid_filter_group(filters, index, scope):
    scope_key = scope.lower()
    variable_options = [{'label': item, 'value': item} for item in actual_keys_in_data]

    rows = []
    for position in range(1, 5):
        variable_key = f"variable{position}"
        value_key = f"value{position}"
        rows.append(
            html.Div(style={"display": "flex", "gap": "8px", "marginBottom": "8px"}, children=[
                html.Div(style={"flex": "0.45"}, children=[
                    html.Label(f"{scope} Variable {position}", className="form-label"),
                    dcc.Dropdown(
                        id={"type": f"mnid-{scope_key}-var{position}", "index": index},
                        options=variable_options,
                        value=filters.get(variable_key),
                        placeholder="Select data column",
                        className="form-input",
                        clearable=True,
                    )
                ]),
                html.Div(style={"flex": "0.55"}, children=[
                    html.Label(f"{scope} Value {position}", className="form-label"),
                    dcc.Input(
                        id={"type": f"mnid-{scope_key}-val{position}", "index": index},
                        value=json.dumps(filters.get(value_key)) if isinstance(filters.get(value_key), (list, dict)) else (filters.get(value_key, "") or ""),
                        placeholder='Value or JSON array e.g. ["Yes","No"]',
                        className="form-input"
                    )
                ]),
            ])
        )
    return rows

def create_mnid_indicator_item(indicator_data=None, index=None):
    indicator_data = indicator_data or {}
    numerator_filters = indicator_data.get("numerator_filters", {})
    denominator_filters = indicator_data.get("denominator_filters", {})

    return html.Div(className="count-item", children=[
        html.Div(style={"display": "flex", "gap": "8px"}, children=[
            html.Div(className="count-col", style={"display": "none"}, children=[
                html.Label("Indicator ID", className="form-label-disabled"),
                dcc.Input(
                    id={"type": "mnid-indicator-id", "index": index},
                    value=indicator_data.get("id", f"mnid_{uuid.uuid4().hex[:8]}"),
                    disabled=True,
                    className="form-input",
                ),
            ]),
            html.Div(className="count-col", children=[
                html.Label("Indicator Label *", className="form-label"),
                dcc.Input(
                    id={"type": "mnid-indicator-label", "index": index},
                    value=indicator_data.get("label", ""),
                    placeholder="Indicator title",
                    className="form-input",
                ),
            ]),
            html.Div(className="count-col", children=[
                html.Label("Category", className="form-label"),
                dcc.Dropdown(
                    id={"type": "mnid-indicator-category", "index": index},
                    options=[{"label": item, "value": item} for item in ["ANC", "Labour", "PNC", "Newborn"]],
                    value=indicator_data.get("category"),
                    clearable=True,
                    className="form-input",
                ),
            ]),
            html.Div(className="count-col", children=[
                html.Label("Target", className="form-label"),
                dcc.Input(
                    id={"type": "mnid-indicator-target", "index": index},
                    type="number",
                    value=indicator_data.get("target", 80),
                    className="form-input",
                ),
            ]),
            html.Div(className="count-col", children=[
                html.Label("Status", className="form-label"),
                dcc.Dropdown(
                    id={"type": "mnid-indicator-status", "index": index},
                    options=[{"label": item.replace("_", " ").title(), "value": item} for item in ["tracked", "awaiting_baseline"]],
                    value=indicator_data.get("status", "tracked"),
                    clearable=False,
                    className="form-input",
                ),
            ]),
            html.Div(className="count-col", children=[
                html.Label("Unique Field", className="form-label"),
                dcc.Dropdown(
                    id={"type": "mnid-indicator-unique", "index": index},
                    options=[{"label": item, "value": item} for item in ["person_id", "encounter_id"]],
                    value=numerator_filters.get("unique", denominator_filters.get("unique", "person_id")),
                    clearable=False,
                    className="form-input",
                ),
            ]),
            html.Div(className="count-col", children=[
                html.Label("Actions", className="form-label"),
                html.Button(
                    "Save",
                    id={"type": "save-mnid-indicator", "index": index},
                    n_clicks=0,
                    className="btn-save btn-small"
                ),
                html.Button(
                    "Delete",
                    id={"type": "remove-mnid-indicator", "index": index},
                    n_clicks=0,
                    className="btn-danger btn-small"
                )
            ]),
        ]),
        html.Div(style={"display": "flex", "gap": "20px", "marginTop": "10px"}, children=[
            html.Div(style={"flex": "1"}, children=[
                html.Label("Numerator Filters", className="form-label"),
                *_create_mnid_filter_group(numerator_filters, index, "Numerator")
            ]),
            html.Div(style={"flex": "1"}, children=[
                html.Label("Denominator Filters", className="form-label"),
                *_create_mnid_filter_group(denominator_filters, index, "Denominator")
            ]),
        ]),
        html.Div(style={"marginTop": "10px"}, children=[
            html.Label("Notes", className="form-label"),
            dcc.Textarea(
                id={"type": "mnid-indicator-note", "index": index},
                value=indicator_data.get("note", ""),
                className="form-input",
                style={"width": "100%", "minHeight": "72px", "resize": "vertical"}
            )
        ])
    ])

CHART_TEMPLATES = {
    "Chart": {
        "measure": "chart",
        "unique": "any",
        "duration_default": "7days",
        "date_col": "Date",
        "y_col": "",
        "title": "",
        "x_title": "Date",
        "y_title": "Number of Patients",
        "unique_column": "person_id",
        "legend_title": "Legend",
        "color": "",
        # Bar chart fields (included but not used)
        "label_col": "",
        "value_col": "",
        "top_n": 10,
        # Pie chart fields
        "names_col": "",
        "values_col": "",
        "colormap": {},
        # Column chart fields
        "x_col": "",
        # Histogram fields
        "age_col": "Age",
        "gender_col": "Gender",
        "bin_size": 5,
        # PivotTable fields
        "index_col1": "",
        "columns": "",
        "aggfunc": "count",
        # Common filters
        "filter_col1": "",
        "filter_val1": "",
        "filter_col2": "",
        "filter_val2": "",
        "filter_col3": "",
        "filter_val3": "",
        "filter_col4": "",
        "filter_val4": "",
        "filter_col5": "",
        "filter_val5": "",
        "custom_fields": ""
    }
}

CHART_TEMPLATES_ORIGINAL = {
    "Line": {
        "measure": "chart",
        "unique": "any",
        "duration_default": "7days",
        "date_col": "Date",
        "y_col": "",
        "title": "",
        "x_title": "Date",
        "y_title": "Number of Patients",
        "unique_column": "person_id",
        "legend_title": "Legend",
        "color": "",
        "filter_col1": "",
        "filter_val1": "",
        "filter_col2": "",
        "filter_val2": "",
        "filter_col3": "",
        "filter_val3": "",
        "filter_col4": "",
        "filter_val4": "",
        "filter_col5": "",
        "filter_val5": ""
    },
    "Bar": {
        "measure": "chart",
        "unique": "any",
        "duration_default": "any",
        "label_col": "",
        "value_col": "",
        "title": "",
        "x_title": "",
        "y_title": "",
        "top_n": 10,
        "filter_col1": "",
        "filter_val1": "",
        "filter_col2": "",
        "filter_val2": "",
        "filter_col3": "",
        "filter_val3": "",
        "filter_col4": "",
        "filter_val4": "",
        "filter_col5": "",
        "filter_val5": ""
    },
    "Pie": {
        "measure": "chart",
        "unique": "any",
        "duration_default": "any",
        "names_col": "",
        "values_col": "",
        "title": "",
        "unique_column": "person_id",
        "filter_col1": "",
        "filter_val1": "",
        "filter_col2": "",
        "filter_val2": "",
        "filter_col3": "",
        "filter_val3": "",
        "filter_col4": "",
        "filter_val4": "",
        "filter_col5": "",
        "filter_val5": "",
        "colormap": {}
    },
    "Column": {
        "measure": "chart",
        "unique": "any",
        "duration_default": "any",
        "x_col": "",
        "y_col": "",
        "title": "",
        "x_title": "",
        "y_title": "",
        "unique_column": "person_id",
        "legend_title": "Legend",
        "color": "",
        "filter_col1": "",
        "filter_val1": "",
        "filter_col2": "",
        "filter_val2": "",
        "filter_col3": "",
        "filter_val3": "",
        "filter_col4": "",
        "filter_val4": "",
        "filter_col5": "",
        "filter_val5": ""
    },
    "Histogram": {
        "measure": "chart",
        "unique": "any",
        "duration_default": "any",
        "age_col": "Age",
        "gender_col": "Gender",
        "title": "",
        "x_title": "Program",
        "y_title": "Number of Patients",
        "bin_size": 5,
        "filter_col1": "",
        "filter_val1": "",
        "filter_col2": "",
        "filter_val2": "",
        "filter_col3": "",
        "filter_val3": "",
        "filter_col4": "",
        "filter_val4": "",
        "filter_col5": "",
        "filter_val5": ""
    },
    "PivotTable": {
        "measure": "chart",
        "unique": "any",
        "duration_default": "any",
        "index_col1": "",
        "columns": "",
        "values_col": "",
        "title": "",
        "unique_column": "person_id",
        "aggfunc": "count",
        "filter_col1": "",
        "filter_val1": "",
        "filter_col2": "",
        "filter_val2": "",
        "filter_col3": "",
        "filter_val3": "",
        "filter_col4": "",
        "filter_val4": "",
        "filter_col5": "",
        "filter_val5": ""
    }
}

